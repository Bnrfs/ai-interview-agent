"""自定义场景管理器 —— 场景 CRUD + 题目 CRUD"""
import json
import os
import uuid
import copy

_DB_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_SCENES_FILE = os.path.join(_DB_DIR, "custom_scenes.json")
CUSTOM_QUESTIONS_FILE = os.path.join(_DB_DIR, "custom_questions.json")


class CustomSceneManager:
    def __init__(self):
        os.makedirs(os.path.dirname(CUSTOM_SCENES_FILE), exist_ok=True)
        self._scenes: list[dict] = []
        self._questions: list[dict] = []
        self._load()

    def _load(self):
        if os.path.exists(CUSTOM_SCENES_FILE):
            with open(CUSTOM_SCENES_FILE, "r", encoding="utf-8") as f:
                self._scenes = json.load(f)
        if os.path.exists(CUSTOM_QUESTIONS_FILE):
            with open(CUSTOM_QUESTIONS_FILE, "r", encoding="utf-8") as f:
                self._questions = json.load(f)

    def _save_scenes(self):
        with open(CUSTOM_SCENES_FILE, "w", encoding="utf-8") as f:
            json.dump(self._scenes, f, ensure_ascii=False, indent=2)

    def _save_questions(self):
        with open(CUSTOM_QUESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._questions, f, ensure_ascii=False, indent=2)

    # ============ 场景 CRUD ============

    def list_scenes(self) -> list[dict]:
        return copy.deepcopy(self._scenes)

    def get_scene(self, scene_id: str) -> dict | None:
        for s in self._scenes:
            if s["id"] == scene_id:
                return copy.deepcopy(s)
        return None

    def create_scene(self, name: str, categories: list[str] = None,
                     description: str = "", opening: str = "",
                     closing: str = "", transition: str = "") -> dict:
        scene_id = f"custom_{uuid.uuid4().hex[:8]}"
        scene = {
            "id": scene_id,
            "name": name,
            "categories": categories or ["综合"],
            "description": description or f"{name}岗位面试",
            "opening": opening or f"你好，我是今天的{name}面试官。首先，请做一个简短的自我介绍。",
            "closing": closing or "面试到此结束。你还有什么想问我的吗？",
            "transition": transition or f"好的，感谢你的介绍。下面我们进入{name}正式面试环节。",
            "question_count": 0,
            "created_at": "",
        }
        import time
        scene["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._scenes.append(scene)
        self._save_scenes()
        return scene

    def update_scene(self, scene_id: str, **kwargs) -> dict | None:
        for s in self._scenes:
            if s["id"] == scene_id:
                for k, v in kwargs.items():
                    if k in s:
                        s[k] = v
                self._save_scenes()
                return copy.deepcopy(s)
        return None

    def delete_scene(self, scene_id: str) -> bool:
        before = len(self._scenes)
        self._scenes = [s for s in self._scenes if s["id"] != scene_id]
        if len(self._scenes) < before:
            self._questions = [q for q in self._questions if q.get("scene") != scene_id]
            self._save_scenes()
            self._save_questions()
            return True
        return False

    # ============ 题目 CRUD ============

    def list_questions(self, scene_id: str = "", category: str = "",
                       difficulty_min: int = 1, difficulty_max: int = 5) -> list[dict]:
        pool = self._questions
        if scene_id:
            pool = [q for q in pool if q.get("scene") == scene_id]
        if category:
            pool = [q for q in pool if q.get("category") == category]
        pool = [q for q in pool if difficulty_min <= q.get("difficulty", 3) <= difficulty_max]
        return copy.deepcopy(pool)

    def get_question(self, qid: str) -> dict | None:
        for q in self._questions:
            if q["id"] == qid:
                return copy.deepcopy(q)
        return None

    def add_question(self, scene_id: str, question: str, category: str = "",
                     difficulty: int = 3, keywords: list[str] = None,
                     model_answer: str = "") -> dict | None:
        scene = self.get_scene(scene_id)
        if not scene:
            return None

        qid = f"CQ_{uuid.uuid4().hex[:8]}"
        q = {
            "id": qid,
            "scene": scene_id,
            "category": category or (scene.get("categories", ["综合"])[0]),
            "question": question,
            "difficulty": max(1, min(5, difficulty)),
            "keywords": keywords or [],
            "model_answer": model_answer or "请根据岗位要求作答。",
        }
        self._questions.append(q)

        # 更新场景题目计数
        scene["question_count"] = len([x for x in self._questions if x.get("scene") == scene_id])
        self._save_questions()
        self._save_scenes()
        return q

    def update_question(self, qid: str, **kwargs) -> dict | None:
        for q in self._questions:
            if q["id"] == qid:
                for k, v in kwargs.items():
                    if k in q:
                        q[k] = v
                self._save_questions()
                return copy.deepcopy(q)
        return None

    def delete_question(self, qid: str) -> bool:
        target = None
        for q in self._questions:
            if q["id"] == qid:
                target = q
                break
        if not target:
            return False
        self._questions.remove(target)
        # 更新场景计数
        for s in self._scenes:
            if s["id"] == target.get("scene"):
                s["question_count"] = len([x for x in self._questions if x.get("scene") == s["id"]])
        self._save_questions()
        self._save_scenes()
        return True

    def get_questions_by_ids(self, ids: list[str]) -> list[dict]:
        id_map = {q["id"]: q for q in self._questions}
        return [copy.deepcopy(id_map[qid]) for qid in ids if qid in id_map]

    def count_questions(self, scene_id: str = "") -> int:
        if scene_id:
            return len([q for q in self._questions if q.get("scene") == scene_id])
        return len(self._questions)


custom_scene_manager = CustomSceneManager()
