"""会话管理 —— 面试状态机 + 超时监控 + 中断恢复"""
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum

from core.config import CHECKPOINTS_DIR, DEFAULT_TIME_LIMIT, MAX_FOLLOWUP_ROUNDS


class InterviewPhase(Enum):
    IDLE = "idle"
    OPENING = "opening"          # 开场自我介绍
    INTRO_ANSWER = "intro_answer"  # 用户回答自我介绍（热身）
    QUESTIONING = "questioning"   # 正式提问
    FOLLOWUP = "followup"        # 追问中
    SCORING = "scoring"          # 评分中
    CLOSING = "closing"          # 结束反问
    REPORT = "report"            # 报告展示
    PAUSED = "paused"            # 已暂停


@dataclass
class QuestionResult:
    question_id: str
    question_text: str
    model_answer: str
    user_answer: str = ""
    followup_rounds: int = 0
    followup_exchanges: list = field(default_factory=list)
    scores: dict = field(default_factory=dict)
    comment: str = ""
    timed_out: bool = False


@dataclass
class InterviewSession:
    session_id: str
    scene: str
    question_ids: list = field(default_factory=list)
    current_question_index: int = 0
    current_followup_round: int = 0
    phase: InterviewPhase = InterviewPhase.IDLE
    question_count: int = 5
    time_limit: int = DEFAULT_TIME_LIMIT
    category_filter: str = ""
    pressure_mode: bool = False
    pressure_level: int = 0  # 0=关闭, 1=轻度, 2=中度, 3=重度
    start_time: float = 0.0
    answered_questions: list = field(default_factory=list)
    total_score: float = 0.0
    wrong_question_ids: list = field(default_factory=list)
    closing_answer: str = ""
    report: str = ""
    remaining_time: int = 0  # 暂停时剩余的倒计时秒数

    def to_dict(self) -> dict:
        d = asdict(self)
        d["phase"] = self.phase.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "InterviewSession":
        d["phase"] = InterviewPhase(d["phase"])
        answered = []
        for aq in d.get("answered_questions", []):
            answered.append(QuestionResult(**aq))
        d["answered_questions"] = answered
        return cls(**d)


class SessionManager:
    """全局会话管理器"""

    def __init__(self):
        self._sessions: dict[str, InterviewSession] = {}
        os.makedirs(CHECKPOINTS_DIR, exist_ok=True)

    def create_session(self, scene: str, question_ids: list[str],
                       question_count: int = 5, time_limit: int = DEFAULT_TIME_LIMIT,
                       category_filter: str = "", pressure_mode: bool = False,
                       pressure_level: int = 0) -> InterviewSession:
        sid = f"S{uuid.uuid4().hex[:8].upper()}"
        session = InterviewSession(
            session_id=sid,
            scene=scene,
            question_ids=question_ids[:question_count],
            question_count=question_count,
            time_limit=time_limit,
            category_filter=category_filter,
            pressure_mode=pressure_mode,
            pressure_level=pressure_level,
            start_time=time.time(),
        )
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> InterviewSession | None:
        return self._sessions.get(session_id)

    def save_checkpoint(self, session_id: str):
        session = self._sessions.get(session_id)
        if not session:
            return
        path = os.path.join(CHECKPOINTS_DIR, f"{session_id}_checkpoint.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)

    def load_checkpoint(self, session_id: str) -> InterviewSession | None:
        path = os.path.join(CHECKPOINTS_DIR, f"{session_id}_checkpoint.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        session = InterviewSession.from_dict(data)
        self._sessions[session_id] = session
        return session

    def list_checkpoints(self) -> list[dict]:
        result = []
        if not os.path.exists(CHECKPOINTS_DIR):
            return result
        for fname in os.listdir(CHECKPOINTS_DIR):
            if fname.endswith("_checkpoint.json"):
                path = os.path.join(CHECKPOINTS_DIR, fname)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                result.append({
                    "session_id": data["session_id"],
                    "scene": data["scene"],
                    "progress": f"{len(data['answered_questions'])}/{data['question_count']}",
                    "timestamp": data.get("start_time", 0),
                })
        return result

    def delete_checkpoint(self, session_id: str):
        path = os.path.join(CHECKPOINTS_DIR, f"{session_id}_checkpoint.json")
        if os.path.exists(path):
            os.remove(path)

    def advance_phase(self, session: InterviewSession, next_phase: InterviewPhase):
        session.phase = next_phase

    def record_answer(self, session: InterviewSession, question_id: str,
                      question_text: str, model_answer: str,
                      user_answer: str, followup_exchanges: list,
                      timed_out: bool = False):
        result = QuestionResult(
            question_id=question_id,
            question_text=question_text,
            model_answer=model_answer,
            user_answer=user_answer,
            followup_rounds=len(followup_exchanges),
            followup_exchanges=followup_exchanges,
            timed_out=timed_out,
        )
        session.answered_questions.append(result)
        session.current_question_index += 1
        session.current_followup_round = 0

    def set_scores(self, session: InterviewSession, scores: dict, comment: str):
        if session.answered_questions:
            qr = session.answered_questions[-1]
            qr.scores = scores
            qr.comment = comment
            numeric = [v for v in scores.values() if isinstance(v, (int, float))]
            avg = sum(numeric) / len(numeric) if numeric else 0
            if avg < 6.0:
                session.wrong_question_ids.append(qr.question_id)

    def calculate_total(self, session: InterviewSession) -> float:
        if not session.answered_questions:
            return 0.0
        total = 0.0
        count = 0
        for aq in session.answered_questions:
            if aq.scores:
                numeric_vals = [v for v in aq.scores.values() if isinstance(v, (int, float))]
                if numeric_vals:
                    total += sum(numeric_vals) / len(numeric_vals)
                count += 1
        session.total_score = round(total / count, 1) if count else 0.0
        return session.total_score


# 全局单例
session_manager = SessionManager()
