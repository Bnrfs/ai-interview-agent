"""主考官Agent —— 面试流程控制 + 开场/结束 + 追问 + 压力模式"""
import json
import re
from core.api_abstract import get_llm
from core.config import MAX_FOLLOWUP_ROUNDS, SCENES, PRESSURE_TTS_SPEED

INTERVIEWER_SYSTEM = """你是一名专业的面试官。请根据用户的岗位选择进行面试。

== 你的身份 ==
{scene_name}的面试官，经验丰富，风格{style}。

== 面试流程 ==
1. 开场：简短自我介绍，然后说"请先做一下自我介绍"
2. 正式提问：按题目列表依次提问
3. 追问：根据用户回答中的关键词，进行1-2轮追问
4. 结束：所有题目完成后，说"面试到此结束。你还有什么想问我的吗？"

== 追问规则 ==
当用户回答中提到具体项目/数据/观点时，从以下模板中选择最合适的进行追问：
- 模板A："你提到了{keyword}，能否展开说说你在其中的具体角色？"
- 模板B："{keyword}这个环节，你遇到了什么困难，怎么解决的？"
- 模板C："如果让你重新做{keyword}，你会怎么优化？"
- 模板D："你从{keyword}中学到了什么，它如何帮助你胜任这个岗位？"

追问不超过2轮。追问不得超出用户回答中已出现的关键词范围。

{pressure_rules}

== 超时处理 ==
每题有限时，超时后说"时间到，我们进入下一题"。在回答末尾附加 [TIMEOUT] 标记。

== 输出信号 ==
每道题（含追问）全部结束后，以单独一行 "---ANSWER_COMPLETE---" 结束，触发评分。"""

FOLLOWUP_TEMPLATES = [
    "你提到了「{keyword}」，能否展开说说你在其中的具体角色？",
    "「{keyword}」这个环节，你遇到了什么困难，怎么解决的？",
    "如果让你重新做「{keyword}」，你会怎么优化？",
    "你从「{keyword}」中学到了什么，它如何帮助你胜任这个岗位？",
]

OPENING_TEMPLATES = {
    "tech": "你好，我是今天的技术面试官。这次面试主要考察你的技术能力和项目经验。首先，请做一个简短的自我介绍。",
    "civil": "你好，我是今天的面试考官。这次是结构化面试，我会从几个方面和你交流。首先，请做一个自我介绍。",
    "postgrad": "各位老师好，欢迎参加今天的硕士研究生复试。首先，请用中文做一个简短的自我介绍。",
}

CLOSING_TEMPLATE = "面试到此结束。你还有什么想问我的吗？"


class InterviewerAgent:
    def __init__(self):
        self.llm = get_llm()

    def build_system_prompt(self, scene: str, pressure: bool = False, pressure_level: int = 0) -> str:
        from core.config import SCENES
        from database.custom_scene_manager import custom_scene_manager

        scene_config = SCENES.get(scene)
        if scene_config:
            scene_name = scene_config["name"]
        else:
            cs = custom_scene_manager.get_scene(scene)
            scene_name = cs["name"] if cs else "面试"
        if not pressure:
            style = "专业严谨"
            pressure_rules = ""
        elif pressure_level == 1:
            style = "偏快节奏，适当催促"
            pressure_rules = """== 压力模式（轻度） ==
- 追问间隔较短，用户回答后立即追问
- 追问只保留核心，去掉"好的""明白了"等过渡语"""
        elif pressure_level == 3:
            style = "极度严厉，持续施压，不给喘息空间"
            pressure_rules = """== 压力模式（重度） ==
- 用户话音刚落立刻打断追问，不给思考时间
- 语气严厉直接，可质疑用户回答的深度
- 追问模板精简为反问句
- 连续追问时不等待，最多追问2轮"""
        else:  # level 2 (default)
            style = "严肃直接，语速快，不给思考时间"
            pressure_rules = """== 压力模式（中度·已开启） ==
- 追问间隔极短，用户话音刚落立刻追问
- 语气直接、不铺垫、不客气
- 追问模板精简，去掉铺垫句
- 不要在追问时说"好的""明白了"等过渡语"""
        return INTERVIEWER_SYSTEM.format(
            scene_name=scene_name,
            style=style,
            pressure_rules=pressure_rules,
        )

    def generate_opening(self, scene: str) -> str:
        template = OPENING_TEMPLATES.get(scene)
        if template:
            return template
        # 自定义场景：从 custom_scene_manager 获取开场白
        from database.custom_scene_manager import custom_scene_manager
        cs = custom_scene_manager.get_scene(scene)
        if cs:
            return cs.get("opening", f"你好，我是今天的{cs['name']}面试官。首先，请做一个简短的自我介绍。")
        return OPENING_TEMPLATES["tech"]

    def generate_closing(self) -> str:
        return CLOSING_TEMPLATE

    def generate_followup(self, user_answer: str, keywords: list[str],
                          round_num: int, pressure: bool = False,
                          pressure_level: int = 0) -> str | None:
        """根据用户回答生成追问。返回追问文本或 None（不再追问）"""
        if round_num >= MAX_FOLLOWUP_ROUNDS:
            return None

        # 从用户回答中提取匹配的关键词
        matched = [kw for kw in keywords if kw in user_answer]
        if not matched:
            return None

        # 用 LLM 选择最合适的追问
        keyword = matched[0]
        templates_text = "\n".join(
            f"{i+1}. {t.format(keyword=keyword)}" for i, t in enumerate(FOLLOWUP_TEMPLATES)
        )
        prompt = f"""用户回答：{user_answer[:500]}

可选追问模板（关键词已替换为 "{keyword}"）：
{templates_text}

请选择最合适的一个追问（只输出追问文本，不要加任何其他内容）："""

        messages = [
            {"role": "system", "content": "你是一个面试追问生成器。根据用户回答选择最合适的追问。"},
            {"role": "user", "content": prompt},
        ]
        followup = self.llm.chat(messages, temperature=0.5, max_tokens=200).strip()
        return followup if followup else None

    def ask_question(self, scene: str, question: str, question_num: int,
                     total: int, pressure: bool = False,
                     pressure_level: int = 0) -> str:
        """生成提问文本"""
        prefix = f"第{question_num}题（共{total}题）：\n" if not pressure else f"第{question_num}题："
        return f"{prefix}{question}"

    def handle_intro_response(self, user_answer: str, scene: str) -> str:
        """处理自我介绍的回答，自然过渡到第一题"""
        transitions = {
            "tech": "好的，感谢你的介绍。下面我们进入正式的技术面试环节。",
            "civil": "好的，感谢你的介绍。下面我们开始结构化面试。",
            "postgrad": "好的，感谢你的介绍。下面我们进入复试问答环节。",
        }
        default = transitions.get(scene)
        if default:
            return default
        from database.custom_scene_manager import custom_scene_manager
        cs = custom_scene_manager.get_scene(scene)
        if cs:
            return cs.get("transition", f"好的，感谢你的介绍。下面我们进入{cs['name']}正式面试环节。")
        return "好的，我们开始正式面试。"

    def extract_keywords(self, question: dict) -> list[str]:
        """从题目数据中提取追问关键词"""
        return question.get("keywords", [])


_interviewer_instance = None

def get_interviewer() -> InterviewerAgent:
    global _interviewer_instance
    if _interviewer_instance is None:
        _interviewer_instance = InterviewerAgent()
    return _interviewer_instance
