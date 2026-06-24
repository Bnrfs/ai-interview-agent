"""题库存储 —— 基于 JSON 的轻量级检索（无需 ChromaDB embedding）"""
import json
import os
import random

from core.config import QUESTIONS_FILE


class QuestionDB:
    def __init__(self):
        self._questions: list[dict] = []
        self._by_scene: dict[str, list[dict]] = {}

    def load_from_json(self, filepath: str = None) -> int:
        """从 JSON 文件加载种子题库"""
        path = filepath or QUESTIONS_FILE
        if not os.path.exists(path):
            return 0

        with open(path, "r", encoding="utf-8") as f:
            questions = json.load(f)

        existing_ids = {q["id"] for q in self._questions}
        new_count = 0
        for q in questions:
            if q["id"] not in existing_ids:
                self._questions.append(q)
                scene = q["scene"]
                if scene not in self._by_scene:
                    self._by_scene[scene] = []
                self._by_scene[scene].append(q)
                new_count += 1

        return new_count

    def search(self, scene: str, n_results: int = 5, category: str = "",
               difficulty_min: int = 1, difficulty_max: int = 5) -> list[dict]:
        """按场景检索题目，支持类别和难度过滤"""
        pool = self._by_scene.get(scene, [])

        if category:
            pool = [q for q in pool if q.get("category", "") == category]

        pool = [q for q in pool if difficulty_min <= q.get("difficulty", 3) <= difficulty_max]

        # 随机打乱取所需数量
        pool = pool.copy()
        random.shuffle(pool)
        return pool[:n_results]

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """按 ID 批量获取题目"""
        id_map = {q["id"]: q for q in self._questions}
        return [id_map[qid] for qid in ids if qid in id_map]

    def count(self, scene: str = "") -> int:
        if scene:
            return len(self._by_scene.get(scene, []))
        return len(self._questions)


# 全局单例
question_db = QuestionDB()
