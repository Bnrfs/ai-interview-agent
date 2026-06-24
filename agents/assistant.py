"""面试准备助手 —— 根据目标岗位整理面试资料与回答技巧"""
import json
from core.api_abstract import get_llm
from core.config import SCENES

ASSISTANT_SYSTEM = """你是一位资深的面试辅导教练，专注于帮助求职者准备面试。

== 你的任务 ==
根据用户提供的目标岗位和补充信息，生成一份个性化面试准备指南。

== 输出结构 ==
按以下5个板块输出（用 Markdown 格式）：

## 1. 岗位核心能力拆解
- 列出该岗位最关键的3-5项核心能力
- 每项附带一句话说明

## 2. 高频面试题目（5道）
- 每道题附带简要的答题思路
- 题目要真实、有代表性

## 3. 回答技巧与框架
- 推荐2-3个适用的回答框架（如 STAR、金字塔原理等）
- 说明每个框架怎么用

## 4. 避坑指南
- 列出3个常见回答错误
- 给出正确做法

## 5. 个性化建议
- 根据用户背景给出针对性建议
- 如果没有用户背景信息，给出通用建议

== 要求 ==
- 内容专业、具体、可操作
- 避免空话套话
- 总字数控制在800-1200字
- 只输出 Markdown，不要任何额外说明"""


class InterviewAssistant:
    def __init__(self):
        self.llm = get_llm()

    def generate_guide(self, position: str, background: str = "",
                       level: str = "", focus_areas: list = None) -> str:
        """生成面试准备指南"""
        context_parts = [f"目标岗位：{position}"]
        if level:
            context_parts.append(f"级别：{level}")
        if background:
            context_parts.append(f"个人背景：{background}")
        if focus_areas:
            context_parts.append(f"重点关注领域：{'、'.join(focus_areas)}")

        context = "\n".join(context_parts)

        prompt = f"""请为以下求职者生成面试准备指南：

{context}

请严格按照系统指令中的5个板块输出，内容要针对以上信息进行个性化调整。"""

        messages = [
            {"role": "system", "content": ASSISTANT_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        result = self.llm.chat(messages, temperature=0.7, max_tokens=3072)
        return result.strip()


_assistant_instance = None


def get_assistant() -> InterviewAssistant:
    global _assistant_instance
    if _assistant_instance is None:
        _assistant_instance = InterviewAssistant()
    return _assistant_instance
