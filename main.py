"""AI模拟面试Agent —— FastAPI 主入口"""
import time
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.config import SCENES, DEFAULT_QUESTION_COUNT, DEFAULT_TIME_LIMIT, RECORDS_DIR
from core.api_abstract import get_llm
from core.session_manager import session_manager, InterviewPhase, InterviewSession
from database.chroma_client import question_db
from database.custom_scene_manager import custom_scene_manager
from agents.interviewer import get_interviewer
from agents.scorer import get_scorer
from agents.reporter import get_reporter
from agents.assistant import get_assistant
from voice.stt import stt_handler
from voice.tts import tts_handler

import os
import json

app = FastAPI(title="AI模拟面试Agent", version="1.0.0")

# 挂载静态文件目录
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ==================== 启动事件 ====================

@app.on_event("startup")
async def startup():
    """启动时加载题库到 ChromaDB"""
    count = question_db.load_from_json()
    print(f"[启动] 题库已加载，新增 {count} 题")
    total = question_db.count()
    print(f"[启动] 题库总数: {total}")
    os.makedirs(RECORDS_DIR, exist_ok=True)


# ==================== 请求/响应模型 ====================

class StartInterviewRequest(BaseModel):
    scene: str = "tech"
    question_count: int = DEFAULT_QUESTION_COUNT
    time_limit: int = DEFAULT_TIME_LIMIT
    category: str = ""
    pressure: bool = False
    pressure_level: int = 0  # 0=关闭, 1=轻度, 2=中度, 3=重度
    retry_session_id: str = ""  # 错题重练：从哪个历史会话取错题
    difficulty: str = ""  # easy / medium / hard 限定难度


class AnswerRequest(BaseModel):
    session_id: str
    answer: str = ""
    audio_data: str = ""  # base64 音频数据（可选）


class ResumeRequest(BaseModel):
    session_id: str
    remaining_time: int = 0  # 暂停时前端传来的剩余秒数


class StartResponse(BaseModel):
    session_id: str
    phase: str
    message: str  # Agent 要说的话（供TTS播放）
    total_questions: int
    current_question: int = 0


class AnswerResponse(BaseModel):
    phase: str
    message: str  # Agent 的回复（追问/过渡语/下一题）
    scores: dict | None = None
    is_last_question: bool = False
    question_index: int = 0
    total_questions: int = 0


# ==================== API 路由 ====================

@app.get("/api/scenes")
async def get_scenes():
    """获取可用面试场景列表（含自定义）"""
    builtin = [
        {"id": k, "name": v["name"], "categories": v["categories"], "builtin": True}
        for k, v in SCENES.items()
    ]
    custom = [
        {"id": s["id"], "name": s["name"], "categories": s["categories"],
         "builtin": False, "question_count": s.get("question_count", 0),
         "description": s.get("description", "")}
        for s in custom_scene_manager.list_scenes()
    ]
    return {"scenes": builtin + custom}


@app.get("/api/checkpoints")
async def get_checkpoints():
    """获取所有中断恢复存档"""
    return {"checkpoints": session_manager.list_checkpoints()}


@app.delete("/api/checkpoints/{session_id}")
async def delete_checkpoint(session_id: str):
    """删除指定存档"""
    session_manager.delete_checkpoint(session_id)
    return {"status": "deleted", "session_id": session_id}


@app.delete("/api/records")
async def delete_all_records():
    """清空所有历史记录"""
    import shutil
    if os.path.exists(RECORDS_DIR):
        shutil.rmtree(RECORDS_DIR)
        os.makedirs(RECORDS_DIR, exist_ok=True)
    return {"status": "cleared"}


@app.post("/api/interview/start", response_model=StartResponse)
async def start_interview(req: StartInterviewRequest):
    """开始一场新的面试"""
    is_builtin = req.scene in SCENES
    is_custom = custom_scene_manager.get_scene(req.scene) is not None

    if not is_builtin and not is_custom:
        raise HTTPException(400, f"不支持的场景: {req.scene}")

    # 获取场景名（自定义场景优先）
    scene_name = SCENES.get(req.scene, {}).get("name") if is_builtin else \
                 custom_scene_manager.get_scene(req.scene)["name"]

    # 错题重练模式
    actual_count = req.question_count
    if req.retry_session_id:
        record_path = os.path.join(RECORDS_DIR, f"{req.retry_session_id}_record.json")
        if not os.path.exists(record_path):
            raise HTTPException(404, "历史记录不存在，无法提取错题")
        with open(record_path, "r", encoding="utf-8") as f:
            record = json.load(f)
        wrong_ids = record.get("wrong_question_ids", [])
        if not wrong_ids:
            raise HTTPException(400, "该次面试没有错题，无需重练")
        # 用错题 ID 从内置题库 + 自定义题库取题
        retry_questions = question_db.get_by_ids(wrong_ids)
        custom_retry = custom_scene_manager.get_questions_by_ids(wrong_ids)
        questions = retry_questions + custom_retry
        question_ids = [q["id"] for q in questions]
        actual_count = min(len(questions), req.question_count)
        questions = questions[:actual_count]
        question_ids = question_ids[:actual_count]
    elif is_custom:
        # 自定义场景：从自定义题库检索
        questions = custom_scene_manager.list_questions(
            scene_id=req.scene,
            category=req.category,
        )
        if req.difficulty:
            dmap = {"easy": (1, 2), "medium": (3, 3), "hard": (4, 5)}
            dmin, dmax = dmap.get(req.difficulty, (1, 5))
            questions = [q for q in questions if dmin <= q.get("difficulty", 3) <= dmax]
        import random
        questions_copy = questions.copy()
        random.shuffle(questions_copy)
        questions = questions_copy[:req.question_count]

        if len(questions) < req.question_count:
            raise HTTPException(
                400,
                f"该自定义场景题目不足：需要{req.question_count}题，实际{len(questions)}题"
            )
        question_ids = [q["id"] for q in questions]
        actual_count = req.question_count
    else:
        # 正常模式：从题库检索题目
        questions = question_db.search(
            scene=req.scene,
            n_results=req.question_count,
            category=req.category,
        )

        if len(questions) < req.question_count:
            raise HTTPException(
                400,
                f"题库中该场景题目不足：需要{req.question_count}题，实际{len(questions)}题"
            )

        question_ids = [q["id"] for q in questions]
        actual_count = req.question_count

    # 创建会话
    session = session_manager.create_session(
        scene=req.scene,
        question_ids=question_ids,
        question_count=actual_count,
        time_limit=req.time_limit,
        category_filter=req.category,
        pressure_mode=req.pressure,
        pressure_level=req.pressure_level,
    )
    session_manager.advance_phase(session, InterviewPhase.OPENING)

    # 生成开场白
    opening = get_interviewer().generate_opening(req.scene)

    # 保存 checkpoint
    session_manager.save_checkpoint(session.session_id)

    return StartResponse(
        session_id=session.session_id,
        phase=session.phase.value,
        message=opening,
        total_questions=actual_count,
        current_question=0,
    )


@app.post("/api/interview/answer", response_model=AnswerResponse)
async def submit_answer(req: AnswerRequest):
    """用户提交回答（文字或语音转录后文字）"""
    session = session_manager.get(req.session_id)
    if not session:
        raise HTTPException(404, "会话不存在或已过期")

    user_answer = req.answer.strip()

    # 处理空答案
    if not user_answer:
        return AnswerResponse(
            phase=session.phase.value,
            message="我没有听清你的回答，请再说一次。",
            question_index=session.current_question_index,
            total_questions=session.question_count,
        )

    phase = session.phase

    # --- 阶段：自我介绍回答 ---
    if phase == InterviewPhase.OPENING:
        transition = get_interviewer().handle_intro_response(user_answer, session.scene)
        session_manager.advance_phase(session, InterviewPhase.QUESTIONING)

        # 出第一题
        qids = session.question_ids
        if not qids:
            raise HTTPException(400, "题库为空")

        first_q_data = question_db.get_by_ids([qids[0]])
        if not first_q_data:
            first_q_data = custom_scene_manager.get_questions_by_ids([qids[0]])
        if not first_q_data:
            raise HTTPException(400, f"题目不存在: {qids[0]}")
        first_q = first_q_data[0]
        question_text = get_interviewer().ask_question(
            session.scene, first_q["question"], 1, session.question_count,
            session.pressure_mode, session.pressure_level
        )

        session_manager.save_checkpoint(session.session_id)

        return AnswerResponse(
            phase=session.phase.value,
            message=f"{transition}\n\n{question_text}",
            question_index=1,
            total_questions=session.question_count,
        )

    # --- 阶段：正式提问回答 ---
    if phase == InterviewPhase.QUESTIONING:
        idx = session.current_question_index
        if idx >= len(session.question_ids):
            # 所有题目答完，进入结束阶段
            session_manager.advance_phase(session, InterviewPhase.CLOSING)
            closing = get_interviewer().generate_closing()

            session_manager.save_checkpoint(session.session_id)

            return AnswerResponse(
                phase=session.phase.value,
                message=closing,
                is_last_question=True,
                question_index=idx,
                total_questions=session.question_count,
            )

        # 获取当前题目
        current_qid = session.question_ids[idx]
        qdata = question_db.get_by_ids([current_qid])
        if not qdata:
            qdata = custom_scene_manager.get_questions_by_ids([current_qid])
        if not qdata:
            raise HTTPException(400, f"题目不存在: {current_qid}")
        q = qdata[0]

        # 判断是否需要追问
        if session.current_followup_round < 2:
            keywords = q.get("keywords", [])
            followup = get_interviewer().generate_followup(
                user_answer, keywords, session.current_followup_round,
                session.pressure_mode, session.pressure_level
            )
            if followup:
                session.current_followup_round += 1
                session_manager.save_checkpoint(session.session_id)
                return AnswerResponse(
                    phase="followup",
                    message=followup,
                    question_index=idx + 1,
                    total_questions=session.question_count,
                )

        # 不再追问，进入评分
        session_manager.advance_phase(session, InterviewPhase.SCORING)

        # 评分
        timed_out = "[TIMEOUT]" in user_answer
        clean_answer = user_answer.replace("[TIMEOUT]", "").strip()
        scores = get_scorer().score(q["question"], q.get("model_answer", ""), clean_answer, timed_out)

        # 记录
        session_manager.record_answer(
            session, current_qid, q["question"], q.get("model_answer", ""),
            clean_answer, [], timed_out
        )
        session_manager.set_scores(session, scores, scores.get("comment", ""))

        # 判断是否还有题
        is_last = (idx + 1) >= session.question_count

        if is_last:
            # 进入结束
            session_manager.advance_phase(session, InterviewPhase.CLOSING)
            closing = get_interviewer().generate_closing()

            session_manager.save_checkpoint(session.session_id)

            return AnswerResponse(
                phase=session.phase.value,
                message=f"【评分】{scores.get('comment', '')}\n\n{closing}",
                scores=scores,
                is_last_question=True,
                question_index=idx + 1,
                total_questions=session.question_count,
            )
        else:
            # 出下一题
            session_manager.advance_phase(session, InterviewPhase.QUESTIONING)
            next_idx = idx + 1
            next_qid = session.question_ids[next_idx]
            next_q_data = question_db.get_by_ids([next_qid])
            if not next_q_data:
                next_q_data = custom_scene_manager.get_questions_by_ids([next_qid])
            next_q = next_q_data[0] if next_q_data else {"question": "请回答下一题。"}
            question_text = get_interviewer().ask_question(
                session.scene, next_q["question"], next_idx + 1, session.question_count,
                session.pressure_mode, session.pressure_level
            )

            session_manager.save_checkpoint(session.session_id)

            return AnswerResponse(
                phase=session.phase.value,
                message=f"【评分】{scores.get('comment', '')}\n\n{question_text}",
                scores=scores,
                question_index=next_idx + 1,
                total_questions=session.question_count,
            )

    # --- 阶段：结束反问 ---
    if phase == InterviewPhase.CLOSING:
        session.closing_answer = user_answer
        session_manager.advance_phase(session, InterviewPhase.REPORT)

        # 计算总分
        total = session_manager.calculate_total(session)

        # 生成报告
        scene_config = SCENES.get(session.scene)
        if scene_config:
            scene_name = scene_config["name"]
        else:
            cs = custom_scene_manager.get_scene(session.scene)
            scene_name = cs["name"] if cs else "面试"
        answered = session.answered_questions
        wrong_ids = session.wrong_question_ids
        report = get_reporter().generate_report(session.scene, scene_name, total, answered, wrong_ids)
        session.report = report

        # 保存记录
        record_path = os.path.join(RECORDS_DIR, f"{session.session_id}_record.json")
        with open(record_path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2, default=str)

        # 清理 checkpoint
        session_manager.delete_checkpoint(session.session_id)

        return AnswerResponse(
            phase=session.phase.value,
            message=report,
            question_index=session.question_count,
            total_questions=session.question_count,
        )

    # --- 兜底 ---
    return AnswerResponse(
        phase=session.phase.value,
        message="面试流程异常，请重新开始。",
        question_index=session.current_question_index,
        total_questions=session.question_count,
    )


@app.post("/api/interview/pause")
async def pause_interview(req: ResumeRequest):
    """暂停面试，保存进度"""
    session = session_manager.get(req.session_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    session_manager.advance_phase(session, InterviewPhase.PAUSED)
    # 从请求体读取剩余时间（前端可选传入）
    session.remaining_time = getattr(req, "remaining_time", 0) or 0
    session_manager.save_checkpoint(req.session_id)
    return {"status": "paused", "session_id": req.session_id}


@app.post("/api/interview/resume")
async def resume_interview(req: ResumeRequest):
    """恢复暂停的面试"""
    session = session_manager.load_checkpoint(req.session_id)
    if not session:
        raise HTTPException(404, "未找到存档")

    session_manager.advance_phase(session, InterviewPhase.QUESTIONING)

    # 返回当前题目
    idx = session.current_question_index
    if idx >= len(session.question_ids):
        return {"phase": "closing", "message": get_interviewer().generate_closing()}

    qid = session.question_ids[idx]
    qdata = question_db.get_by_ids([qid])
    if not qdata:
        qdata = custom_scene_manager.get_questions_by_ids([qid])
    q = qdata[0] if qdata else {"question": "请继续回答。"}
    question_text = get_interviewer().ask_question(
        session.scene, q["question"], idx + 1, session.question_count,
        session.pressure_mode, session.pressure_level
    )

    rt = session.remaining_time if session.remaining_time > 0 else session.time_limit
    print(f"[DEBUG resume] session_id={req.session_id}, remaining_time(saved)={session.remaining_time}, time_limit={session.time_limit}, returning={rt}")

    return {
        "phase": session.phase.value,
        "message": question_text,
        "question_index": idx + 1,
        "total_questions": session.question_count,
        "remaining_time": rt,
    }


@app.get("/api/interview/status/{session_id}")
async def interview_status(session_id: str):
    """查询面试状态"""
    session = session_manager.get(session_id)
    if not session:
        return {"exists": False}
    return {
        "exists": True,
        "session_id": session.session_id,
        "scene": session.scene,
        "phase": session.phase.value,
        "progress": f"{session.current_question_index}/{session.question_count}",
        "pressure": session.pressure_mode,
        "time_limit": session.time_limit,
        "question_count": session.question_count,
    }


@app.get("/api/records")
async def list_records():
    """列出历史面试记录"""
    records = []
    if not os.path.exists(RECORDS_DIR):
        return {"records": records}
    for fname in sorted(os.listdir(RECORDS_DIR), reverse=True):
        if fname.endswith("_record.json"):
            path = os.path.join(RECORDS_DIR, fname)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            records.append({
                "session_id": data.get("session_id", ""),
                "scene": data.get("scene", ""),
                "total_score": data.get("total_score", 0),
                "question_count": data.get("question_count", 0),
                "wrong_count": len(data.get("wrong_question_ids", [])),
                "start_time": data.get("start_time", 0),
            })
    return {"records": records}


@app.get("/api/record/{session_id}")
async def get_record(session_id: str):
    """获取单次面试记录详情"""
    path = os.path.join(RECORDS_DIR, f"{session_id}_record.json")
    if not os.path.exists(path):
        raise HTTPException(404, "记录不存在")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================== 自定义场景 API ====================

class CreateSceneRequest(BaseModel):
    name: str
    categories: list[str] = []
    description: str = ""


class AddQuestionRequest(BaseModel):
    scene_id: str
    question: str
    category: str = ""
    difficulty: int = 3
    keywords: list[str] = []
    model_answer: str = ""


@app.get("/api/custom/scenes")
async def list_custom_scenes():
    """列出所有自定义场景"""
    return {"scenes": custom_scene_manager.list_scenes()}


@app.post("/api/custom/scenes")
async def create_custom_scene(req: CreateSceneRequest):
    """创建自定义面试场景"""
    if not req.name.strip():
        raise HTTPException(400, "场景名称不能为空")
    scene = custom_scene_manager.create_scene(
        name=req.name.strip(),
        categories=req.categories if req.categories else None,
        description=req.description,
    )
    return {"scene": scene}


@app.put("/api/custom/scenes/{scene_id}")
async def update_custom_scene(scene_id: str, req: CreateSceneRequest):
    """更新自定义场景"""
    updates = {}
    if req.name.strip():
        updates["name"] = req.name.strip()
    if req.categories:
        updates["categories"] = req.categories
    if req.description:
        updates["description"] = req.description
    scene = custom_scene_manager.update_scene(scene_id, **updates)
    if not scene:
        raise HTTPException(404, "场景不存在")
    return {"scene": scene}


@app.delete("/api/custom/scenes/{scene_id}")
async def delete_custom_scene(scene_id: str):
    """删除自定义场景（含关联题目）"""
    ok = custom_scene_manager.delete_scene(scene_id)
    if not ok:
        raise HTTPException(404, "场景不存在")
    return {"status": "deleted"}


@app.get("/api/custom/questions/{scene_id}")
async def list_custom_questions(scene_id: str):
    """列出某场景的自定义题目"""
    questions = custom_scene_manager.list_questions(scene_id=scene_id)
    return {"questions": questions}


@app.post("/api/custom/questions")
async def add_custom_question(req: AddQuestionRequest):
    """添加自定义题目"""
    if not req.question.strip():
        raise HTTPException(400, "题目内容不能为空")
    q = custom_scene_manager.add_question(
        scene_id=req.scene_id,
        question=req.question.strip(),
        category=req.category,
        difficulty=req.difficulty,
        keywords=req.keywords,
        model_answer=req.model_answer,
    )
    if not q:
        raise HTTPException(404, "场景不存在")
    return {"question": q}


@app.put("/api/custom/questions/{qid}")
async def update_custom_question(qid: str, req: AddQuestionRequest):
    """更新自定义题目"""
    updates = {}
    if req.question.strip():
        updates["question"] = req.question.strip()
    if req.category:
        updates["category"] = req.category
    if req.difficulty:
        updates["difficulty"] = req.difficulty
    if req.keywords:
        updates["keywords"] = req.keywords
    if req.model_answer:
        updates["model_answer"] = req.model_answer
    q = custom_scene_manager.update_question(qid, **updates)
    if not q:
        raise HTTPException(404, "题目不存在")
    return {"question": q}


@app.delete("/api/custom/questions/{qid}")
async def delete_custom_question(qid: str):
    """删除自定义题目"""
    ok = custom_scene_manager.delete_question(qid)
    if not ok:
        raise HTTPException(404, "题目不存在")
    return {"status": "deleted"}


class AutoGenerateRequest(BaseModel):
    scene_id: str
    count: int = 5


@app.post("/api/custom/questions/auto-generate")
async def auto_generate_questions(req: AutoGenerateRequest):
    """根据场景职业自动搜索并生成真实面试题目（基于DeepSeek知识库）"""
    scene = custom_scene_manager.get_scene(req.scene_id)
    if not scene:
        raise HTTPException(404, "场景不存在")

    if req.count < 1 or req.count > 20:
        raise HTTPException(400, "题目数量需在1-20之间")

    scene_name = scene["name"]
    categories = scene.get("categories", ["综合"])
    categories_str = "、".join(categories)

    prompt = f"""你是一位资深{scene_name}面试官，拥有大量真实面试经验。请从你的知识库中检索{scene_name}岗位的真实面试题，生成{req.count}道题目。

该岗位核心面试类别：{categories_str}

== 生成要求 ==
1. 题目必须真实、专业，来源于该岗位实际面试中的高频考题
2. 难度分布合理：1-2道基础概念题、2-3道应用场景题、1-2道深度思考题
3. 题目覆盖不同类别，不重复，不冗余
4. 追问关键词需精准，能直接嵌入追问模板（如"你提到了{{关键词}}，能否展开说说"）
5. 模范回答要点列出关键得分点（3-5条），而非完整答案

== 输出格式 ==
严格输出JSON数组，每个元素字段如下：
- question: 题目内容
- category: 类别（从给定类别中选择）
- difficulty: 难度1-5
- keywords: 关键词数组（3-5个）
- model_answer: 模范回答要点（分条列出关键得分点）

只输出JSON数组，不要任何其他文本。"""

    try:
        llm = get_llm()
        messages = [
            {"role": "system", "content": "你是一位专业的面试题目生成器。你从真实面试经验中提取题目。严格输出JSON数组，不添加任何解释或markdown标记。"},
            {"role": "user", "content": prompt},
        ]
        response = llm.chat(messages, temperature=0.8, max_tokens=4096)
        print(f"[DEBUG auto-gen] response type: {type(response).__name__}, len: {len(response) if hasattr(response, '__len__') else 'N/A'}")

        # 加固：response 可能是 string 或 list
        if isinstance(response, list):
            response = json.dumps(response, ensure_ascii=False)
        if not isinstance(response, str):
            raise ValueError(f"LLM返回异常类型: {type(response).__name__}")

        # 清理可能的 markdown 代码块
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        questions_data = json.loads(cleaned)

        # 兼容 {"questions": [...]} 格式
        if isinstance(questions_data, dict):
            for key in ("questions", "data", "results"):
                if key in questions_data:
                    questions_data = questions_data[key]
                    break
            else:
                raise ValueError(f"LLM返回JSON对象，但未找到题目数组。keys: {list(questions_data.keys())}")

        if not isinstance(questions_data, list):
            raise ValueError("LLM返回格式不是JSON数组")

        # 校验并保存
        saved = []
        for q in questions_data:
            question_text = (q.get("question") or "").strip() if isinstance(q.get("question"), str) else ""
            if not question_text:
                continue

            # 防御：字段可能是 list 或 string
            model_answer_raw = q.get("model_answer", "")
            if isinstance(model_answer_raw, list):
                model_answer_raw = "\n".join(model_answer_raw)
            if not isinstance(model_answer_raw, str):
                model_answer_raw = ""

            keywords_raw = q.get("keywords") or []
            if isinstance(keywords_raw, str):
                keywords_raw = [k.strip() for k in keywords_raw.split(",") if k.strip()]

            category_raw = q.get("category", "")
            if isinstance(category_raw, list):
                category_raw = category_raw[0] if category_raw else ""
            if not isinstance(category_raw, str):
                category_raw = categories[0] if categories else "综合"

            difficulty_raw = q.get("difficulty", 3)
            if isinstance(difficulty_raw, str):
                try:
                    difficulty_raw = int(difficulty_raw)
                except ValueError:
                    difficulty_raw = 3

            result = custom_scene_manager.add_question(
                scene_id=req.scene_id,
                question=question_text,
                category=category_raw or (categories[0] if categories else "综合"),
                difficulty=max(1, min(5, difficulty_raw)),
                keywords=keywords_raw,
                model_answer=model_answer_raw.strip(),
            )
            if result:
                saved.append(result)

        return {
            "status": "success",
            "generated": len(saved),
            "questions": saved,
        }

    except json.JSONDecodeError as e:
        raw_preview = response[:300] if 'response' in dir() else "(无响应)"
        raise HTTPException(500, f"题目解析失败，AI返回格式异常。原始内容前300字: {raw_preview}")
    except Exception as e:
        raise HTTPException(500, f"自动生成失败: {str(e)}")


# ==================== 面试准备助手 API ====================

class PrepareGuideRequest(BaseModel):
    position: str
    background: str = ""
    level: str = ""
    focus_areas: list[str] = []
    session_id: str = ""  # 可选：基于哪次历史面试生成


@app.post("/api/assistant/prepare-guide")
async def prepare_guide(req: PrepareGuideRequest):
    """生成面试准备指南"""
    if not req.position.strip():
        raise HTTPException(400, "请填写目标岗位")
    try:
        guide = get_assistant().generate_guide(
            position=req.position.strip(),
            background=req.background.strip(),
            level=req.level.strip(),
            focus_areas=req.focus_areas,
            session_id=req.session_id,
        )
        return {"guide": guide}
    except Exception as e:
        raise HTTPException(500, f"生成失败: {str(e)}")


@app.post("/api/assistant/usage-guide")
async def usage_guide():
    """生成智能体使用说明"""
    try:
        guide = get_assistant().generate_usage_guide()
        return {"guide": guide}
    except Exception as e:
        raise HTTPException(500, f"生成失败: {str(e)}")


# ==================== 前端页面 ====================

@app.get("/", response_class=HTMLResponse)
async def index():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    with open(os.path.join(static_dir, "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/interview", response_class=HTMLResponse)
async def interview_page():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    with open(os.path.join(static_dir, "interview.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/report", response_class=HTMLResponse)
async def report_page():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    with open(os.path.join(static_dir, "report.html"), "r", encoding="utf-8") as f:
        return f.read()


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
