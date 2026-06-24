"""面试准备助手 —— 根据目标岗位整理面试资料与回答技巧（支持历史记录分析）"""
import json
import os
from core.api_abstract import get_llm
from core.config import SCENES, RECORDS_DIR

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

ASSISTANT_SYSTEM_WITH_HISTORY = """你是一位资深的面试辅导教练，专注于帮助求职者准备面试。你能够分析用户的历史面试记录，发现薄弱环节，给出针对性建议。

== 你的任务 ==
根据用户提供的目标岗位、补充信息、以及历史面试记录，生成一份个性化面试准备指南。

== 输出结构 ==
按以下6个板块输出（用 Markdown 格式）：

## 1. 历史表现诊断
- 根据历史面试记录，分析用户在逻辑/内容/组织/匹配四个维度的强弱项
- 指出最薄弱的维度，给出具体数据

## 2. 岗位核心能力拆解
- 列出该岗位最关键的3-5项核心能力
- 结合用户历史表现，标注哪些能力已达标、哪些需要加强

## 3. 错题复盘与针对性练习
- 从历史错题中提取共性问题
- 给出2-3道针对性练习题目

## 4. 回答技巧与框架
- 针对用户弱项推荐2-3个适用的回答框架（如 STAR、金字塔原理等）
- 说明如何用框架弥补具体短板

## 5. 避坑指南
- 基于用户历史回答中的常见错误，列出3个需要避免的问题
- 给出正确做法

## 6. 个性化提升计划
- 根据用户背景和历史表现，给出未来1-2周的提升计划
- 包含每日练习建议

== 要求 ==
- 内容必须基于用户历史数据，不能泛泛而谈
- 引用具体数据（分数、维度）来支撑诊断
- 总字数控制在1000-1500字
- 只输出 Markdown，不要任何额外说明"""


class InterviewAssistant:
    def __init__(self):
        self.llm = get_llm()

    def _load_history(self, session_id: str = "") -> dict | None:
        """加载历史面试记录，session_id 为空则取最近一次"""
        if not os.path.exists(RECORDS_DIR):
            return None

        records = []
        for fname in os.listdir(RECORDS_DIR):
            if fname.endswith("_record.json"):
                path = os.path.join(RECORDS_DIR, fname)
                with open(path, "r", encoding="utf-8") as f:
                    records.append(json.load(f))

        if not records:
            return None

        if session_id:
            for r in records:
                if r.get("session_id") == session_id:
                    return r
            return None

        # 取最近一次
        records.sort(key=lambda r: r.get("start_time", 0), reverse=True)
        return records[0]

    def _format_history_context(self, record: dict) -> str:
        """将历史记录格式化为 prompt 上下文"""
        parts = []

        scene_name = record.get("scene", "未知")
        total_score = record.get("total_score", 0)
        parts.append(f"面试场景：{scene_name}")
        parts.append(f"总分：{total_score}/10")

        answered = record.get("answered_questions", [])
        dims = {"logic": [], "completeness": [], "organization": [], "match": []}
        dim_labels = {"logic": "逻辑清晰度", "completeness": "内容完整性",
                      "organization": "语言组织力", "match": "岗位匹配度"}

        for aq in answered:
            scores = aq.get("scores", {})
            for k in dims:
                if k in scores and scores[k] is not None:
                    dims[k].append(scores[k])

        parts.append("\n维度平均分：")
        for k, label in dim_labels.items():
            if dims[k]:
                avg = round(sum(dims[k]) / len(dims[k]), 1)
                parts.append(f"- {label}：{avg}/10")

        wrong_ids = record.get("wrong_question_ids", [])
        if wrong_ids:
            parts.append(f"\n错题数：{len(wrong_ids)}")
            parts.append("错题详情：")
            for aq in answered:
                if aq.get("question_id") in wrong_ids:
                    parts.append(f"- 题目：{aq.get('question_text', '')[:200]}")
                    parts.append(f"  用户回答：{aq.get('user_answer', '')[:300]}")
                    parts.append(f"  评分：{aq.get('scores', {})}")
                    parts.append(f"  点评：{aq.get('comment', '')}")

        parts.append("\n各题分数：")
        for i, aq in enumerate(answered):
            s = aq.get("scores", {})
            if s:
                avg_q = round(sum(v for v in s.values() if isinstance(v, (int, float))) / max(len(s), 1), 1)
                parts.append(f"- 第{i+1}题：均分{avg_q} | {aq.get('comment', '')[:80]}")

        return "\n".join(parts)

    def generate_guide(self, position: str, background: str = "",
                       level: str = "", focus_areas: list = None,
                       session_id: str = "") -> str:
        """生成面试准备指南，可选基于历史记录"""
        context_parts = [f"目标岗位：{position}"]
        if level:
            context_parts.append(f"级别：{level}")
        if background:
            context_parts.append(f"个人背景：{background}")
        if focus_areas:
            context_parts.append(f"重点关注领域：{'、'.join(focus_areas)}")

        # 尝试加载历史记录（仅当用户明确选择了某次记录时）
        history_record = self._load_history(session_id) if session_id else None

        if history_record:
            history_context = self._format_history_context(history_record)
            context_parts.append(f"\n=== 用户历史面试记录 ===\n{history_context}")

            context = "\n".join(context_parts)
            prompt = f"""请为以下求职者生成面试准备指南（必须基于历史记录进行分析）：

{context}

请严格按照系统指令中的6个板块输出，历史表现诊断和错题复盘必须引用具体数据。"""

            messages = [
                {"role": "system", "content": ASSISTANT_SYSTEM_WITH_HISTORY},
                {"role": "user", "content": prompt},
            ]
            result = self.llm.chat(messages, temperature=0.7, max_tokens=4096)
            return result.strip()

        # 无历史记录，走通用模式
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


USAGE_GUIDE_SYSTEM = """你是一个AI面试智能体的使用说明助手。你需要帮助用户快速上手这个智能体。

== 智能体功能清单 ==
1. 面试模拟：支持3个内置场景（大厂技术岗/公务员结构化面试/考研复试），每个场景5个子类别，共225道题
2. 自定义场景：用户可创建自己的面试场景，手动添加题目或AI自动生成
3. 压力模式：3级强度（轻度/中度/重度），模拟高压面试环境，追问更紧逼
4. 追问机制：每次回答后自动判断是否需要追问（最多2轮），挖掘深度
5. 四维评分：逻辑清晰度/内容完整性/语言组织力/岗位匹配度，每题即时评分
6. 面试报告：结束后生成完整报告，含总分、各维度分析、错题列表
7. 暂停恢复：面试中可随时暂停，下次继续
8. 错题重练：历史记录中的错题可一键重练
9. 面试准备助手：输入目标岗位和个人背景，生成个性化准备指南（含岗位拆解、高频题、回答框架、避坑指南）。支持选择历史面试记录，自动分析薄弱环节生成针对性提升计划
10. 语音输入：支持语音回答（需Chrome浏览器）
11. 自定义题目AI生成：输入数量，自动生成真实面试题

== 输出要求 ==
按以下结构输出 Markdown，总字数控制在600-900字：

## 快速开始
- 3步上手：选择场景 → 设置题数和时限 → 点击开始

## 核心功能详解
- 简要介绍3-4个最核心的功能，每个用1-2句话

## 小技巧
- 3-4个实用技巧，帮用户获得更好的面试体验

## 常见问题
- 3个常见问题及解答

要求：语气亲切、直接、不啰嗦。只输出 Markdown，不要额外说明。"""

    def generate_usage_guide(self) -> str:
        """生成智能体使用说明"""
        prompt = "请根据系统指令中的功能清单，生成一份智能体使用说明。"
        messages = [
            {"role": "system", "content": USAGE_GUIDE_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        result = self.llm.chat(messages, temperature=0.7, max_tokens=2048)
        return result.strip()


_assistant_instance = None


def get_assistant() -> InterviewAssistant:
    global _assistant_instance
    if _assistant_instance is None:
        _assistant_instance = InterviewAssistant()
    return _assistant_instance