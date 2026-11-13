"""Agent 会话基座服务（事件溯源）

事件日志是唯一事实源：消息历史从事件投影派生（derive_messages），
fork/恢复/审计都能从同一份日志重建。thinking 等展示类事件不进投影。
"""

import logging
from datetime import datetime

from sqlalchemy import select, delete, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentEvent, AgentSession
from app.services.ai_service import get_active_ai_config, _build_request

logger = logging.getLogger(__name__)

# 会进入模型消息历史的事件类型（thinking/tool_call 纯展示，不进投影）
MESSAGE_EVENT_TYPES = {"user_message", "assistant_message", "tool_result"}


async def create_session(db: AsyncSession, ai_config_id: int | None = None) -> AgentSession:
    """创建会话"""
    session = AgentSession(ai_config_id=ai_config_id)
    db.add(session)
    await db.flush()
    await db.commit()
    await db.refresh(session)
    return session


async def get_session(db: AsyncSession, session_id: int) -> AgentSession | None:
    return await db.get(AgentSession, session_id)


async def list_sessions(db: AsyncSession, limit: int = 50) -> list[AgentSession]:
    """会话列表，最近更新在前"""
    result = await db.execute(
        select(AgentSession).order_by(desc(AgentSession.updated_at)).limit(limit)
    )
    return list(result.scalars())


async def append_event(db: AsyncSession, session_id: int, event_type: str, payload: dict,
                       surface_op: dict | None = None) -> AgentEvent:
    """追加事件（seq 会话内单调递增），并触摸会话 updated_at。surface_op 用于压缩 replace 标记"""
    result = await db.execute(
        select(func.max(AgentEvent.seq)).where(AgentEvent.session_id == session_id)
    )
    next_seq = (result.scalar() or 0) + 1
    event = AgentEvent(session_id=session_id, seq=next_seq, event_type=event_type, payload=payload,
                       surface_op=surface_op)
    db.add(event)
    session = await db.get(AgentSession, session_id)
    if session:
        session.updated_at = datetime.now()
    await db.flush()
    await db.commit()
    await db.refresh(event)
    return event


async def get_session_events(db: AsyncSession, session_id: int) -> list[AgentEvent]:
    """按 seq 顺序取会话全部事件"""
    result = await db.execute(
        select(AgentEvent).where(AgentEvent.session_id == session_id).order_by(AgentEvent.seq)
    )
    return list(result.scalars())


async def derive_messages(db: AsyncSession, session_id: int) -> list[dict]:
    """从事件日志投影出模型消息历史

    规则：
    - user_message → {"role": "user", "content": ...}
    - assistant_message → {"role": "assistant", "content": ...[, "tool_calls": ...]}
    - tool_result → {"role": "tool", "tool_call_id": ..., "content": ...}
    - thinking / tool_call（展示用）不进投影
    - surface_op replace：预留 compaction 口子（被 replace 的范围跳过）
    """
    events = await get_session_events(db, session_id)
    # tool_result 按 call_id 建索引：投影时归位到其 assistant 消息之后
    # （用户可能隔了几轮才点确认，事件在日志末尾，但模型 API 要求 tool 消息紧跟 tool_calls）
    tool_results_by_call: dict[str, dict] = {}
    for ev in events:
        if ev.event_type == "tool_result":
            cid = (ev.payload or {}).get("tool_call_id")
            if cid:
                tool_results_by_call[cid] = ev.payload
    voided = await get_voided_seqs(events)

    # 先全量收集 replace 标记的截止 seq（replace 事件在被替代事件之后，顺序扫描会漏掉前面的）
    replaced_until = 0
    for ev in events:
        if ev.surface_op and ev.surface_op.get("op") == "replace":
            replaced_until = max(replaced_until, int(ev.surface_op.get("end", 0)))

    messages = []
    for ev in events:
        if ev.seq <= replaced_until or ev.seq in voided:
            continue
        if ev.event_type not in MESSAGE_EVENT_TYPES:
            continue
        p = ev.payload
        if ev.event_type == "user_message":
            messages.append({"role": "user", "content": p.get("content", "")})
        elif ev.event_type == "assistant_message":
            msg = {"role": "assistant", "content": p.get("content", "")}
            # 思维链模式：所有 assistant 消息都必须回传 reasoning_content，否则 400
            if p.get("thinking"):
                msg["reasoning_content"] = p["thinking"]
            # 防御：只保留已有 tool_result 响应的 tool_calls，否则模型 API 会因
            # "tool_calls 后缺少 tool 消息"拒绝整个请求（400）；一条都不剩就不带 tool_calls
            calls = [c for c in (p.get("tool_calls") or []) if c.get("id") in tool_results_by_call]
            if calls and p.get("thinking"):
                msg["tool_calls"] = calls
                messages.append(msg)
                # tool 消息紧跟其后
                for c in calls:
                    tr = tool_results_by_call[c["id"]]
                    messages.append({
                        "role": "tool",
                        "tool_call_id": c["id"],
                        "content": tr.get("content", ""),
                    })
            elif calls:
                # 没有思维链可回传（如管线合成的调用）：降级为纯文本历史，保证投影合法
                results_text = "；".join(
                    (tool_results_by_call[c["id"]].get("content") or "")[:100] for c in calls
                )
                msg["content"] = (msg["content"] + f"\n\n（后续操作结果：{results_text}）").strip()
                messages.append(msg)
            else:
                messages.append(msg)
        elif ev.event_type == "tool_result":
            continue  # 已在 assistant 消息处归位，跳过自然位置
    return messages


async def set_session_config(db: AsyncSession, session_id: int, ai_config_id: int | None) -> AgentSession:
    """切换会话绑定的模型配置（None=跟随全局）"""
    session = await db.get(AgentSession, session_id)
    if not session:
        raise ValueError("会话不存在")
    session.ai_config_id = ai_config_id
    await db.flush()
    await db.commit()
    await db.refresh(session)
    return session


async def derive_display_messages(db: AsyncSession, session_id: int) -> list[dict]:
    """供前端展示的消息投影：assistant 消息带 thinking 摘要和 toolCalls 卡片

    与 derive_messages（模型历史投影）区分：展示投影保留思维链摘要与工具调用信息。
    """
    events = await get_session_events(db, session_id)
    voided = await get_voided_seqs(events)
    messages: list[dict] = []
    for ev in events:
        if ev.seq in voided:
            continue
        p = ev.payload
        if ev.event_type == "user_message":
            messages.append({
                "role": "user",
                "content": p.get("content", ""),
                "images": p.get("images") or [],
                "seq": ev.seq,
            })
        elif ev.event_type == "assistant_message":
            messages.append({
                "role": "assistant",
                "content": p.get("content", ""),
                "thinking": p.get("thinking") or None,
                "toolCalls": [],
            })
        elif ev.event_type == "tool_result":
            if messages and messages[-1]["role"] == "assistant":
                messages[-1]["toolCalls"].append({
                    "name": p.get("name"),
                    "summary": (p.get("content") or "")[:1200],
                })
    return messages


async def rename_session(db: AsyncSession, session_id: int, title: str) -> AgentSession:
    """用户改名 —— 钉住标题，自动生成不再覆盖"""
    session = await db.get(AgentSession, session_id)
    if not session:
        raise ValueError("会话不存在")
    title = title.strip()
    if not title:
        raise ValueError("标题不能为空")
    session.title = title[:100]
    session.title_pinned = True
    await db.flush()
    await db.commit()
    await db.refresh(session)
    return session


async def void_last_user_message(db: AsyncSession, session_id: int) -> str:
    """撤回最后一条用户消息（软删，保审计）。

    规则：仅当它是最后一条消息（之后没有任何事件）才可撤回——AI 已回复的消息
    撤回会破坏上下文完整性（回复可能已被记住/工具已执行）。
    返回被撤回的文本（前端回填输入框）。
    """
    events = await get_session_events(db, session_id)
    if not events:
        raise ValueError("会话为空，没有可撤回的消息")
    last = events[-1]
    if last.event_type == "message_void":
        raise ValueError("上一条消息已撤回")
    if last.event_type != "user_message":
        raise ValueError("只能撤回最后一条你发送的消息（AI 已回复的不能撤回）")
    await append_event(db, session_id, "message_void", {"target_seq": last.seq})
    return (last.payload or {}).get("content", "")


async def rewind_from_user_seq(db: AsyncSession, session_id: int, seq: int) -> str:
    """从某条用户消息起整段作废（含这条和之后的回复），便于编辑后重发或重新生成。"""
    events = await get_session_events(db, session_id)
    voided = await get_voided_seqs(events)
    target = next((ev for ev in events if ev.seq == seq and ev.seq not in voided), None)
    if target is None or target.event_type != "user_message":
        raise ValueError("找不到这条消息")
    content = (target.payload or {}).get("content", "")
    await append_event(db, session_id, "message_void", {"from_seq": seq})
    return content


async def get_voided_seqs(events: list[AgentEvent]) -> set[int]:
    voided: set[int] = set()
    for ev in events:
        if ev.event_type != "message_void":
            continue
        payload = ev.payload or {}
        if payload.get("from_seq") is not None:
            start = int(payload["from_seq"])
            voided.update(other.seq for other in events if start <= other.seq < ev.seq)
        else:
            voided.add(int(payload.get("target_seq", 0)))
    voided.discard(0)
    return voided


async def delete_session(db: AsyncSession, session_id: int) -> None:
    """删除会话及其全部事件"""
    await db.execute(delete(AgentEvent).where(AgentEvent.session_id == session_id))
    session = await db.get(AgentSession, session_id)
    if session:
        await db.delete(session)
    await db.flush()
    await db.commit()


async def auto_title(db: AsyncSession, session_id: int, first_message: str) -> None:
    """首条消息后用 AI 生成会话标题；已钉住或已有标题则跳过"""
    session = await db.get(AgentSession, session_id)
    if not session or session.title_pinned or session.title:
        return

    config = await get_active_ai_config(db)
    if not config:
        return

    try:
        import httpx
        prompt = f"为以下对话生成一个 10 字以内的简短标题，只输出标题文字，不要标点不要引号：\n\n{first_message[:300]}"
        url, headers, payload = _build_request(config, [{"role": "user", "content": prompt}])
        payload["max_tokens"] = 64
        if config.provider == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            title = (response.json()["choices"][0]["message"]["content"] or "").strip().strip("\"'")[:100]
        if title:
            session.title = title
            await db.flush()
            await db.commit()
            logger.info(f"会话 #{session_id} 自动标题: {title}")
    except Exception as e:
        logger.warning(f"会话 #{session_id} 自动标题失败（已忽略）: {e}")
