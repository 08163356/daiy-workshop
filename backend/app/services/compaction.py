"""上下文压缩（hermes context_compressor 裁剪版）

策略（先免费后付费）：
1. 阈值触发：投影消息总字符 > COMPACT_CHAR_THRESHOLD（≈上下文 0.75 的粗略估计）
2. 确定性 prune（无 LLM）：截断超长 tool 结果和思维链（会话内反复出现的大头）
3. 还不够 → LLM 结构化 checkpoint 摘要，追加带 surface_op=replace 的 user_message
   （投影层已支持：标记范围内的事件不再进上下文，但保留在日志里可审计）
4. 冷却：上次压缩 30 分钟内不再压（防抖动）
"""
import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentEvent, AgentSession

logger = logging.getLogger(__name__)

COMPACT_CHAR_THRESHOLD = 60000   # 投影总字符阈值（中文 ~1.5 字符/token ≈ 40K tokens）
COMPACT_COOLDOWN_MINUTES = 30    # 冷却防抖动
KEEP_RECENT_EVENTS = 10          # 摘要时逐字保留的最近事件数
TOOL_RESULT_PRUNE_TO = 400       # prune 后单条工具结果上限

CHECKPOINT_PROMPT = """把下面的对话历史压缩成结构化交接摘要（供后续上下文使用）。

输出格式（Markdown，信息密度优先）：
## 目标
## 约束与偏好
## 已完成（编号列表）
## 进行中
## 未满足的用户输入
## 当前状态（关键数据/结论）

要求：已完成动作带日期过去式；密钥类信息一律 [REDACTED]；不超过 800 字。

## 对话历史
{history}"""


def _project_chars(messages: list[dict]) -> int:
    return sum(len(str(m.get("content") or "")) for m in messages)


def _prune(messages: list[dict]) -> list[dict]:
    """确定性 prune（无 LLM）：超长 tool 结果和思维链截断"""
    out = []
    for m in messages:
        m = dict(m)
        content = m.get("content")
        if isinstance(content, str):
            if m.get("role") == "tool" and len(content) > TOOL_RESULT_PRUNE_TO:
                m["content"] = content[:TOOL_RESULT_PRUNE_TO] + "\n...[已裁剪]"
            elif m.get("role") == "assistant" and len(content) > 3000:
                m["content"] = content[:1500] + "\n...[中段已裁剪]...\n" + content[-1000:]
        if isinstance(m.get("reasoning_content"), str) and len(m["reasoning_content"]) > 2000:
            m["reasoning_content"] = m["reasoning_content"][:200] + "..." + m["reasoning_content"][-200:]
        out.append(m)
    return out


async def maybe_compact(db: AsyncSession, session: AgentSession, messages: list[dict]) -> list[dict]:
    """会话过大时压缩。返回（可能被压缩/替换后的）消息列表"""
    if _project_chars(messages) < COMPACT_CHAR_THRESHOLD:
        return messages

    # 冷却检查：最近压过就先 prune 顶着（SQLite JSON 列上 is_not(None) 不可靠，直接查 op）
    result = await db.execute(
        select(AgentEvent.created_at).where(
            AgentEvent.session_id == session.id,
            AgentEvent.surface_op["op"].as_string() == "replace",
        ).order_by(AgentEvent.seq.desc()).limit(1)
    )
    last_compact = result.scalar_one_or_none()
    in_cooldown = last_compact and datetime.now() - last_compact < timedelta(minutes=COMPACT_COOLDOWN_MINUTES)

    pruned = _prune(messages)
    if _project_chars(pruned) < COMPACT_CHAR_THRESHOLD or in_cooldown:
        if in_cooldown:
            logger.info(f"会话 #{session.id} 压缩冷却中，仅 prune")
        return pruned

    # LLM 结构化摘要：压缩除最近 N 条外的全部事件
    from app.services.agent_session import append_event, derive_messages, get_session_events
    from app.services.ai_service import get_active_ai_config, _build_request

    events = await get_session_events(db, session.id)
    if len(events) <= KEEP_RECENT_EVENTS + 4:
        return pruned
    cutoff_seq = events[-KEEP_RECENT_EVENTS].seq

    history_lines = []
    for ev in events:
        if ev.seq >= cutoff_seq:
            continue
        p = ev.payload or {}
        content = (p.get("content") or "")[:300]
        if content:
            role = {"user_message": "用户", "assistant_message": "助手", "tool_result": "工具"}.get(ev.event_type, ev.event_type)
            history_lines.append(f"{role}: {content}")
    history = "\n".join(history_lines)[-20000:]

    config = await get_active_ai_config(db)
    if not config:
        return pruned

    try:
        url, headers, payload = _build_request(config, [
            {"role": "user", "content": CHECKPOINT_PROMPT.replace("{history}", history)},
        ])
        payload["max_tokens"] = min(config.max_tokens, 1500)
        payload["temperature"] = 0.2
        if config.provider == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            summary = r.json()["choices"][0]["message"]["content"] or ""
        if len(summary.strip()) < 50:
            return pruned

        # checkpoint 作为 user_message 追加，surface_op 标记旧事件范围不再投影
        await append_event(db, session.id, "user_message", {
            "content": f"【此前对话的压缩摘要】\n{summary}",
            "source": "compaction",
        }, surface_op={"op": "replace", "end": cutoff_seq})
        logger.info(f"会话 #{session.id} 已压缩：{cutoff_seq} 前的事件折叠为摘要")
        new_messages = await derive_messages(db, session.id)
        return [{"role": "system", "content": messages[0]["content"]}] + new_messages
    except Exception as e:
        logger.warning(f"会话 #{session.id} LLM 压缩失败，退回 prune: {e}")
        return pruned
