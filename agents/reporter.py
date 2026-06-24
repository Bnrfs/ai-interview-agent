"""报告生成Agent —— 总分汇总 + 改进建议 + 错题归档"""
from core.api_abstract import get_llm

REPORTER_SYSTEM = """你是一名专业的面试报告分析师。请根据用户的面试记录生成一份综合报告。

== 报告结构 ==
1. 总分概览（一句话总结整体表现）
2. 各维度表现分析（逻辑/内容/组织/匹配四个维度的强弱项）
3. 3条具体改进建议（每条建议对应具体题目中的具体问题）
4. 鼓励性收尾（肯定优点，鼓励继续练习）

== 输出格式 ==
请用 Markdown 格式输出报告，包含清晰的标题和分段。"""


class ReporterAgent:
    def __init__(self):
        self.llm = get_llm()

    def generate_report(self, scene: str, scene_name: str, total_score: float,
                        answered: list, wrong_ids: list[str]) -> str:
        """生成面试报告"""

        # 构建答题详情
        details = []
        for aq in answered:
            details.append({
                "question": aq.question_text[:200],
                "answer": aq.user_answer[:300],
                "scores": aq.scores,
                "comment": aq.comment,
                "followup_rounds": aq.followup_rounds,
            })

        # 计算各维度平均分
        dimension_avgs = {"logic": 0, "completeness": 0, "organization": 0, "match": 0}
        count = 0
        for aq in answered:
            if aq.scores:
                for k in dimension_avgs:
                    dimension_avgs[k] += aq.scores.get(k, 0)
                count += 1
        if count:
            for k in dimension_avgs:
                dimension_avgs[k] = round(dimension_avgs[k] / count, 1)

        prompt = f"""面试场景：{scene_name}
总分：{total_score}/10
各维度平均分：逻辑{dimension_avgs['logic']} / 内容{dimension_avgs['completeness']} / 组织{dimension_avgs['organization']} / 匹配{dimension_avgs['match']}
错题数：{len(wrong_ids)}
答题详情：
{details}

请生成面试报告。"""

        messages = [
            {"role": "system", "content": REPORTER_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        report = self.llm.chat(messages, temperature=0.5, max_tokens=1500)
        return report


_reporter_instance = None

def get_reporter() -> ReporterAgent:
    global _reporter_instance
    if _reporter_instance is None:
        _reporter_instance = ReporterAgent()
    return _reporter_instance
