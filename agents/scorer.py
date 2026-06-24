"""评分员Agent —— 4维度打分 + 点评生成"""
import json
from core.api_abstract import get_llm

SCORER_SYSTEM = """你是一名专业的面试评分员。请对用户的回答从4个维度评分（满分10分）：

1. 逻辑清晰度（logic）：回答是否有框架、有层次，论证是否有条理
2. 内容完整性（completeness）：是否覆盖了关键要点，是否有遗漏
3. 语言组织力（organization）：句子结构是否紧凑、逻辑是否连贯、是否有冗余表达
4. 岗位匹配度（match）：回答是否踩中了岗位需要的核心能力

== 评分参照 ==
每题都提供了"模范回答"作为评分参照。请参照模范回答进行对比打分。

== 超时处理 ==
若回答末尾包含 [TIMEOUT] 标记，每个维度额外扣1分（最低0分），并在 comment 中注明"回答超时"。

== 输出格式（严格 JSON） ==
{"logic": 7.0, "completeness": 8.0, "organization": 6.5, "match": 7.5, "comment": "一句话点评"}

注意：comment 控制在30字以内，给出最核心的改进建议。"""


class ScorerAgent:
    def __init__(self):
        self.llm = get_llm()

    def score(self, question: str, model_answer: str, user_answer: str,
              timed_out: bool = False) -> dict:
        """对用户回答评分，返回 {logic, completeness, organization, match, comment}"""

        if not user_answer.strip():
            return {
                "logic": 0,
                "completeness": 0,
                "organization": 0,
                "match": 0,
                "comment": "未作答"
            }

        prompt = f"""题目：{question}

模范回答参考：
{model_answer}

用户回答：
{user_answer[:2000]}

请评分。严格输出 JSON。"""

        messages = [
            {"role": "system", "content": SCORER_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        try:
            raw = self.llm.chat_json(messages, temperature=0.3, max_tokens=512)
            # 清理可能的 Markdown 代码块包裹
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
            scores = json.loads(raw)
        except (json.JSONDecodeError, Exception):
            # 评分失败时的兜底
            scores = {
                "logic": 5.0,
                "completeness": 5.0,
                "organization": 5.0,
                "match": 5.0,
                "comment": "评分系统异常，已使用默认分"
            }

        # 超时扣分
        if timed_out:
            for key in ["logic", "completeness", "organization", "match"]:
                scores[key] = max(0, scores.get(key, 5.0) - 1)
            scores["comment"] = (scores.get("comment", "") + "（回答超时）").strip()

        # 确保所有维度存在
        for key in ["logic", "completeness", "organization", "match", "comment"]:
            if key not in scores:
                scores[key] = 5.0 if key != "comment" else "无法评分"

        return scores


_scorer_instance = None

def get_scorer() -> ScorerAgent:
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = ScorerAgent()
    return _scorer_instance
