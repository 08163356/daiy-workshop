"""统一 AI 助手 API（会话管理 + 对话）"""

import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.agent import (
    AgentSessionCreate, AgentSessionResponse, AgentSessionDetail,
    AgentChatRequest, AgentSessionUpdate, AgentConfirmRequest,
    AgentVoidRequest, AgentRewindRequest, AgentSteerRequest, AgentSteerCancelRequest,
    AgentClarifyRequest,
)
from app.services import agent_session as session_svc
from app.services.agent_loop import run_agent_turn, resume_after_confirm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["AI 助手"])


@router.get("/sessions", response_model=list[AgentSessionResponse])
async def list_agent_sessions(db: AsyncSession = Depends(get_db)):
    """会话列表（最近更新在前）"""
    return await session_svc.list_sessions(db)


@router.post("/sessions", response_model=AgentSessionResponse)
async def create_agent_session(data: AgentSessionCreate, db: AsyncSession = Depends(get_db)):
    """创建会话"""
    return await session_svc.create_session(db, ai_config_id=data.ai_config_id)


@router.get("/sessions/{session_id}", response_model=AgentSessionDetail)
async def get_agent_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """会话详情 + 从事件日志投影出的消息历史"""
    session = await session_svc.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 前端恢复用展示投影（含思维链摘要和工具卡片）
    messages = await session_svc.derive_display_messages(db, session_id)
    return AgentSessionDetail(
        session=AgentSessionResponse.model_validate(session),
        messages=messages,
    )


@router.patch("/sessions/{session_id}", response_model=AgentSessionResponse)
async def update_agent_session(
    session_id: int, data: AgentSessionUpdate, db: AsyncSession = Depends(get_db)
):
    """更新会话：改名（钉住标题）/ 切换绑定模型"""
    try:
        if data.title is not None:
            return await session_svc.rename_session(db, session_id, data.title)
        return await session_svc.set_session_config(db, session_id, data.ai_config_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/finalize-coach")
async def finalize_coach(session_id: int, db: AsyncSession = Depends(get_db)):
    """教练会话结束沉淀：生成总结/洞察/画像更新"""
    session = await session_svc.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.mode != "coach":
        raise HTTPException(status_code=400, detail="只有教练会话可以沉淀")
    if session.summary:
        return {"message": "已沉淀过", "summary": session.summary, "insights": session.insights}
    from app.services.coach_service import finalize_coach_session
    try:
        result = await finalize_coach_session(db, session)
        await db.commit()
        return {"message": "沉淀完成", **result, "followups": session.followups}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class TasklistCreateRequest(BaseModel):
    session_id: Optional[int] = None
    groups: list = Field(..., min_length=1, max_length=20)


@router.post("/tasklist/create")
async def create_tasklist_from_draft(data: TasklistCreateRequest, db: AsyncSession = Depends(get_db)):
    """任务单草稿经用户编辑确认后创建待办（父任务 + 子任务，fail-closed）"""
    from app.services.tasklist_service import create_tasklist
    try:
        result = await create_tasklist(db, data.session_id, data.groups)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"创建失败: {e}")
    if data.session_id:
        note = f"已按你的修改创建任务单：{result['parents']} 个父任务、{result['children']} 个子任务。"
        await session_svc.append_event(db, data.session_id, "assistant_message", {"content": note})
    return result


class FollowupTodoRequest(BaseModel):
    followup_index: int = Field(..., ge=0)


class ExploreProfileRequest(BaseModel):
    indices: list[int] = Field(default_factory=list, description="要写入的画像下标，矛盾项需用户勾选后才传入")


@router.post("/sessions/{session_id}/finalize-explore")
async def finalize_explore(session_id: int, db: AsyncSession = Depends(get_db)):
    """探索会话结束：生成评估报告，不写日记/画像/待办"""
    session = await session_svc.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.mode != "explore":
        raise HTTPException(status_code=400, detail="只有探索会话可以生成评估")
    from app.services.explore_service import finalize_explore_session
    try:
        result = await finalize_explore_session(db, session)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/explore-diary")
async def save_explore_diary(session_id: int, db: AsyncSession = Depends(get_db)):
    """确认后把评估报告写入日记"""
    session = await session_svc.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    from app.services.explore_service import save_explore_diary as write_diary
    try:
        return await write_diary(db, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/explore-profile")
async def apply_explore_profile(session_id: int, data: ExploreProfileRequest, db: AsyncSession = Depends(get_db)):
    """确认后只写入勾选的画像"""
    session = await session_svc.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    from app.services.explore_service import apply_explore_profile as write_profile
    try:
        return await write_profile(db, session, data.indices)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/explore-todo")
async def create_explore_todo(session_id: int, db: AsyncSession = Depends(get_db)):
    """确认后把 24 小时行动建成一条待办"""
    session = await session_svc.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    from app.services.explore_service import create_explore_todo as write_todo
    try:
        return await write_todo(db, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/followup-todo")
async def create_followup_todo(session_id: int, data: FollowupTodoRequest, db: AsyncSession = Depends(get_db)):
    """沉淀卡片「建成待办」：跟进项上的草稿真正建成待办（source=coach 关联会话）"""
    session = await session_svc.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.mode != "coach":
        raise HTTPException(status_code=400, detail="只有教练会话有跟进项")
    from app.services.coach_service import create_todo_from_followup
    try:
        return await create_todo_from_followup(db, session, data.followup_index)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_agent_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """删除会话及其全部事件"""
    session = await session_svc.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    await session_svc.delete_session(db, session_id)
    return {"message": "已删除"}


@router.post("/chat")
async def agent_chat(data: AgentChatRequest, db: AsyncSession = Depends(get_db)):
    """SSE 对话端点：流式返回 thinking/content/tool_call/tool_result/done/error 事件"""
    if data.session_id:
        session = await session_svc.get_session(db, data.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        session = await session_svc.create_session(db, ai_config_id=data.ai_config_id)
        # 深挖入口来源（日记/笔记/提问），记在会话上供上下文注入
        if data.origin_type and data.origin_id:
            session.origin_type = data.origin_type
            session.origin_id = data.origin_id
            await db.flush()
            # 用户选择「深挖」进对话讨论 → 右上角队列不再重复弹这条
            if data.origin_type == "question":
                from app.models.ai_question import AIQuestion
                q = await db.get(AIQuestion, data.origin_id)
                if q and q.status == "pending":
                    q.status = "answered"
                    q.answer = "（已在教练对话中讨论）"
                    await db.flush()

    async def event_stream():
        # 首先告知会话 ID（前端新建会话时需要）
        yield f"data: {json.dumps({'type': 'session', 'session_id': session.id}, ensure_ascii=False)}\n\n"
        async for ev in run_agent_turn(db, session, data.content, data.images):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/void")
async def agent_void_message(data: AgentVoidRequest, db: AsyncSession = Depends(get_db)):
    """撤回最后一条用户消息（软删入日志），返回被撤回文本供前端回填输入框"""
    session = await session_svc.get_session(db, data.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.status == "running":
        raise HTTPException(status_code=409, detail="AI 正在生成中，请先停止再撤回")
    try:
        content = await session_svc.void_last_user_message(db, data.session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "已撤回", "content": content}


@router.post("/rewind")
async def agent_rewind_message(data: AgentRewindRequest, db: AsyncSession = Depends(get_db)):
    """从指定用户消息起作废后续内容，返回原文供编辑或重新生成"""
    session = await session_svc.get_session(db, data.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.status == "running":
        raise HTTPException(status_code=409, detail="AI 正在生成中，请先停止")
    try:
        content = await session_svc.rewind_from_user_seq(db, data.session_id, data.seq)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "已回退", "content": content}


@router.post("/steer")
async def agent_steer(data: AgentSteerRequest, db: AsyncSession = Depends(get_db)):
    """生成中插话：追加 steering 事件，AI 在下一个轮次边界看到"""
    session = await session_svc.get_session(db, data.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if session.status != "running":
        raise HTTPException(status_code=409, detail="当前没有在生成，直接发送即可")
    ev = await session_svc.append_event(db, session.id, "steering", {"content": data.content, "claimed": False})
    return {"message": "已排队，AI 本轮结束后会看到", "seq": ev.seq}


@router.post("/steer/cancel")
async def agent_steer_cancel(data: AgentSteerCancelRequest, db: AsyncSession = Depends(get_db)):
    """撤销排队中的插话（软删，已被 AI 读取的不能撤）"""
    from app.models.agent import AgentEvent
    from sqlalchemy import select as _select
    session = await session_svc.get_session(db, data.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    result = await db.execute(
        _select(AgentEvent).where(
            AgentEvent.session_id == data.session_id,
            AgentEvent.seq == data.seq,
            AgentEvent.event_type == "steering",
        )
    )
    ev = result.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="插话不存在")
    if (ev.payload or {}).get("claimed"):
        raise HTTPException(status_code=400, detail="AI 已经看到这条插话了，撤不回")
    await session_svc.append_event(db, data.session_id, "message_void", {"target_seq": data.seq})
    return {"message": "已撤销"}


@router.post("/clarify")
async def agent_clarify(data: AgentClarifyRequest, db: AsyncSession = Depends(get_db)):
    """澄清提问的回答：问答记入对话 + AI 提炼后写画像（不是原始问答直倒）"""
    from sqlalchemy import select
    from app.models.agent import AgentEvent
    from app.services.clarify_service import synthesize_answers_to_profile

    session = await session_svc.get_session(db, data.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 找对应批次的提问事件，且未回答过（幂等：重复提交直接返回已处理）
    result = await db.execute(
        select(AgentEvent).where(
            AgentEvent.session_id == data.session_id,
            AgentEvent.event_type.in_(["clarify_questions", "clarify_answered"]),
        )
    )
    events = result.scalars().all()
    question_events = [e for e in events if e.event_type == "clarify_questions"
                       and (e.payload or {}).get("batch_id") == data.batch_id]
    answered = [e for e in events if e.event_type == "clarify_answered"
                and (e.payload or {}).get("batch_id") == data.batch_id]
    if not question_events:
        raise HTTPException(status_code=404, detail="提问批次不存在")

    def sse(ev: dict) -> str:
        return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    if answered:
        return StreamingResponse(
            iter([sse({"type": "done", "session_id": data.session_id}), "data: [DONE]\n\n"]),
            media_type="text/event-stream")

    source_content = (question_events[-1].payload or {}).get("source_content", "")
    qa_pairs = [a.model_dump() for a in data.answers]

    # 1. 问答作为用户消息进对话日志（上下文连贯，后续聊天能看到）
    qa_text = "\n".join(f"**{p['question']}**\n{p['answer']}" for p in qa_pairs)
    await session_svc.append_event(db, data.session_id, "user_message", {
        "content": f"【澄清回答】\n{qa_text}", "source": "clarify",
    })

    # 2. AI 提炼后写画像（提炼失败/无实质信息则不进画像）
    learned = await synthesize_answers_to_profile(db, source_content, qa_pairs)

    # 3. 对话里答过的问题，右上角「AI 想了解你」队列不再重复弹（容错：队列不可用时不影响主流程）
    try:
        from app.models.ai_question import AIQuestion
        pending_q = list((await db.execute(
            select(AIQuestion).where(AIQuestion.status == "pending")
        )).scalars())
        for q in pending_q:
            for p in qa_pairs:
                if q.question[:8] in p["question"] or p["question"][:8] in q.question:
                    q.status = "answered"
                    q.answer = p["answer"]
                    break
        await db.flush()
    except Exception as e:
        logger.debug(f"同步右上角提问队列失败（不影响澄清回答）: {e}")

    # 4. 标记批次已回答
    await session_svc.append_event(db, data.session_id, "clarify_answered", {
        "batch_id": data.batch_id, "answers": qa_pairs, "learned_count": len(learned),
    })

    # 5. 继续对话：AI 给一句反馈并接着聊（不再只是静态确认语）
    from app.services.agent_loop import _prepare_context, _run_rounds
    try:
        config, messages, tools = await _prepare_context(db, session)
    except Exception as e:
        return StreamingResponse(
            iter([sse({"type": "error", "message": str(e)}), "data: [DONE]\n\n"]),
            media_type="text/event-stream")
    if not config:
        return StreamingResponse(
            iter([sse({"type": "error", "message": "未配置 AI 模型"}), "data: [DONE]\n\n"]),
            media_type="text/event-stream")
    keys = "、".join(item["key"] for item in learned[:3])
    messages[0]["content"] += (
        f"\n\n## 用户刚回答了你的澄清问题\n{qa_text}\n"
        f"请先用一句话确认你记下了{('（已提炼进画像：' + keys + '）') if learned else ''}，"
        "再自然地继续对话（教练模式一次只问一个问题）。不要重复整段分析。"
    )

    async def event_stream():
        try:
            async for ev in _run_rounds(db, session, messages, config, tools):
                yield sse(ev)
        except Exception as e:
            logger.error(f"澄清后继续对话失败: {e}", exc_info=True)
            yield sse({"type": "error", "message": str(e)})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })


@router.post("/confirm")
async def agent_confirm(data: AgentConfirmRequest, db: AsyncSession = Depends(get_db)):
    """写操作确认：允许/拒绝后恢复对话循环（SSE 流式返回后续事件）"""
    session = await session_svc.get_session(db, data.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    async def event_stream():
        try:
            async for ev in resume_after_confirm(db, session, data.approved):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
