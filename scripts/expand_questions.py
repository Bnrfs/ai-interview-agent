"""扩充题库：每个子类别补到 15 题"""
import json
import os
import sys
import time

# 确保能找到项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.api_abstract import get_llm

QUESTIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "questions.json")

SCENES = {
    "tech": {"name": "大厂技术岗", "categories": ["算法", "项目经历", "系统设计", "行为面试", "技术视野"]},
    "civil": {"name": "公务员结构化面试", "categories": ["综合分析", "组织协调", "应急处理", "人际关系", "岗位认知"]},
    "postgrad": {"name": "考研复试", "categories": ["英文自我介绍", "专业基础", "研究计划", "导师匹配", "综合素养"]},
}

ID_PREFIX = {"tech": "T", "civil": "C", "postgrad": "P"}

def load_existing():
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_questions(questions):
    with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

def count_existing(questions, scene, category):
    return len([q for q in questions if q["scene"] == scene and q["category"] == category])

def get_existing_in_category(questions, scene, category):
    return [q for q in questions if q["scene"] == scene and q["category"] == category]

def generate_questions_for_category(scene, scene_name, category, existing_qs, need_count):
    """调用 DeepSeek 生成指定数量的题目"""
    llm = get_llm()

    existing_text = ""
    for i, q in enumerate(existing_qs):
        existing_text += f"- {q['question']} (难度{q['difficulty']})\n"

    prompt = f"""你是一位资深面试官，请为「{scene_name}」场景的「{category}」子类别生成 {need_count} 道面试题。

已有题目（请勿重复）：
{existing_text}

== 生成要求 ==
1. 题目覆盖该子类别的不同角度和深度，不重复、不冗余
2. 难度分布合理：简单(1-2) 约30%、中等(3) 约40%、困难(4-5) 约30%
3. 追问关键词 3-5 个，精准且可嵌入追问模板
4. 模范回答要点列出 3-5 条关键得分点

== 输出格式 ==
严格输出 JSON 数组，每个元素：
- question: 题目内容
- category: "{category}"
- difficulty: 难度 1-5
- keywords: 关键词数组
- model_answer: 模范回答要点

只输出 JSON 数组，不要任何其他文本。"""

    try:
        messages = [
            {"role": "system", "content": "你是一位专业的面试题目生成器。严格输出 JSON 数组，不添加任何解释或 markdown 标记。"},
            {"role": "user", "content": prompt},
        ]
        response = llm.chat(messages, temperature=0.8, max_tokens=8192)
        print(f"  [raw] type={type(response).__name__}, len={len(response) if isinstance(response, str) else 'N/A'}")

        if isinstance(response, list):
            response = json.dumps(response, ensure_ascii=False)
        if not isinstance(response, str):
            raise ValueError(f"LLM返回异常类型: {type(response).__name__}")

        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        questions_data = json.loads(cleaned)

        if isinstance(questions_data, dict):
            for key in ("questions", "data", "results"):
                if key in questions_data:
                    questions_data = questions_data[key]
                    break
            else:
                raise ValueError(f"LLM返回JSON对象但无题目数组: {list(questions_data.keys())}")

        if not isinstance(questions_data, list):
            raise ValueError(f"LLM返回格式不是JSON数组: {type(questions_data)}")

        return questions_data

    except Exception as e:
        print(f"  [ERROR] {e}")
        print(f"  [raw response preview] {response[:500] if 'response' in dir() else 'N/A'}")
        return []


def main():
    all_questions = load_existing()
    max_id = 0
    for q in all_questions:
        num = int(q["id"][1:])
        if num > max_id:
            max_id = num

    print(f"现有题目: {len(all_questions)}，最大 ID: {max_id}")

    for scene, info in SCENES.items():
        scene_name = info["name"]
        prefix = ID_PREFIX[scene]
        print(f"\n{'='*60}")
        print(f"场景: {scene_name} ({scene})")
        print(f"{'='*60}")

        for category in info["categories"]:
            existing = get_existing_in_category(all_questions, scene, category)
            current_count = len(existing)
            need = 15 - current_count

            if need <= 0:
                print(f"  [{category}] 已有 {current_count} 题，无需补充")
                continue

            print(f"  [{category}] 已有 {current_count} 题，需补充 {need} 题...")

            new_qs = generate_questions_for_category(scene, scene_name, category, existing, need)

            if not new_qs:
                print(f"  [{category}] 生成失败，跳过")
                continue

            added = 0
            for q in new_qs:
                question_text = (q.get("question") or "").strip()
                if not question_text:
                    continue

                model_answer_raw = q.get("model_answer", "")
                if isinstance(model_answer_raw, list):
                    model_answer_raw = "\n".join(model_answer_raw)

                keywords_raw = q.get("keywords") or []
                if isinstance(keywords_raw, str):
                    keywords_raw = [k.strip() for k in keywords_raw.split(",") if k.strip()]

                difficulty_raw = q.get("difficulty", 3)
                if isinstance(difficulty_raw, str):
                    try:
                        difficulty_raw = int(difficulty_raw)
                    except ValueError:
                        difficulty_raw = 3

                max_id += 1
                new_q = {
                    "id": f"{prefix}{max_id:03d}",
                    "scene": scene,
                    "category": category,
                    "question": question_text,
                    "difficulty": max(1, min(5, difficulty_raw)),
                    "keywords": keywords_raw[:5],
                    "model_answer": model_answer_raw.strip() if isinstance(model_answer_raw, str) else "",
                }
                all_questions.append(new_q)
                added += 1

            print(f"  [{category}] 成功添加 {added} 题，当前共 {current_count + added} 题")

            # 每生成一个类别后保存一次（防止中断丢失）
            save_questions(all_questions)
            time.sleep(1)  # 避免 API 限流

    print(f"\n{'='*60}")
    print(f"完成！总题目数: {len(all_questions)}")

    # 统计
    for scene in SCENES:
        for cat in SCENES[scene]["categories"]:
            count = len([q for q in all_questions if q["scene"] == scene and q["category"] == cat])
            print(f"  {SCENES[scene]['name']} / {cat}: {count} 题")


if __name__ == "__main__":
    main()