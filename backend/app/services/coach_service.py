"""教练模式服务：跨会话记忆 + 结束沉淀（总结/洞察/画像更新）

迁移自老 coaching.py 的三段式能力，挂到统一 AI 助手会话（mode='coach'）上。
"""
import json
import logging
from datetime import date, datetime

import httpx
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentSession
from app.services.agent_session import derive_messages
from app.services.ai_service import (
    get_active_ai_config, get_user_profile_text, update_user_profile,
    get_api_url, _build_request, _parse_ai_json,
)

logger = logging.getLogger(__name__)


async def get_recent_coach_summaries(db: AsyncSession, exclude_session_id: int, limit: int = 3) -> str:
    """最近几次教练会话的摘要（跨会话记忆）"""
    result = await db.execute(
        select(AgentSession)
        .where(
            AgentSession.mode == "coach",
            AgentSession.id != exclude_session_id,
            AgentSession.summary.is_not(None),
        )
        .order_by(desc(AgentSession.updated_at))
        .limit(limit)
    )
    sessions = result.scalars().all()
    if not sessions:
        return ""
    lines = []
    for s in sessions:
        lines.append(f"- [{s.updated_at.strftime('%m-%d')}] {s.title or '教练对话'}：{s.summary}")
    return "\n".join(lines)


COACH_FINALIZE_PROMPT = """基于以下教练对话，生成结构化沉淀：

1. summary：2-3 句话概括本次对话的核心主题和进展
2. insights：1-3 条用户获得的自我觉察或新认知（每条一句话，优先保留用户自己的原话）
3. coaching_type：本次最接近的教练类型 emotion/performance/relationship/vision/life
4. commitment：对话收敛出的一个可观察的下一步；没有就 null
5. check_question：下次开场要核对的那一句（如「那句写下来了吗？写下之后你怎么看？」）；没有承诺就 null
6. review_on：回看日 YYYY-MM-DD；用户说了时间用用户的，没说就对话结束三天后
7. proposed_todos：0-1 条待建任务草稿（用户当次明确要拆成两件小事时最多 2 条）。每条：{"title": "可执行的一句话", "description": "核对问题+用户原话+来源说明", "category": "work/learning/life/health/social/finance/creative", "quadrant": 2, "due_date": null 或用户说的截止日, "scheduled_date": review_on}
8. profile_updates：值得写入长期画像的特征。规则：有对话原话作证据才写；用户认领的稳定模式可写/更新；这一次的情绪留在 insights 不写进「性格特征」；只出现一次、用户没认领的推断不写；和已有画像矛盾用 delete 再 create；宁可空列表

严格 JSON：
{
  "summary": "...",
  "insights": ["..."],
  "coaching_type": "...",
  "commitment": "...或 null",
  "check_question": "...或 null",
  "review_on": "YYYY-MM-DD 或 null",
  "proposed_todos": [],
  "profile_updates": [{"category": "分类", "key": "特征键", "value": "特征值", "action": "create"}]
}

## 用户画像
{user_profile}

## 对话内容
{conversation}"""


async def get_origin_excerpt(db: AsyncSession, session: AgentSession) -> str:
    """深挖来源摘录：按 origin_type/id 从服务端取该篇内容（用户气泡不再塞全文，防模型搜错篇）"""
    if not session.origin_type or not session.origin_id:
        return ""
    try:
        if session.origin_type == "diary":
            from app.models.diary import DiaryEntry
            entry = await db.get(DiaryEntry, session.origin_id)
            if not entry:
                return ""
            issues = "、".join(entry.key_issues or [])
            return (
                f"## 本次来源：{entry.date} 的日记「{entry.title or ''}」\n"
                + (f"已提取的关键问题：{issues}\n" if issues else "")
                + f"原文摘录：\n{(entry.content or '')[:2000]}"
            )
        if session.origin_type == "note":
            from app.models.note import Note
            note = await db.get(Note, session.origin_id)
            if not note:
                return ""
            return (
                f"## 本次来源：笔记「{note.title}」（{note.reading_date or ''}）\n"
                f"原文摘录：\n{(note.content or '')[:2000]}"
            )
        if session.origin_type == "question":
            from app.models.ai_question import AIQuestion
            q = await db.get(AIQuestion, session.origin_id)
            if not q:
                return ""
            return f"## 本次来源：一条待答的 AI 提问\n问题：{q.question}"
    except Exception as e:
        logger.warning(f"来源摘录组装失败（不影响对话）: {e}")
    return ""


async def get_open_followups(db: AsyncSession, exclude_session_id: int) -> str:
    """开场核对材料（按方案顺序）：
    1. 未完成的 source=coach 待办（完成状态以待办为准，描述里带核对问题）
    2. 还没有 todo_id、状态 open 的跟进项
    """
    from app.models.todo import TodoItem

    lines: list[str] = []
    # 1. 未完成的教练待办
    todo_result = await db.execute(
        select(TodoItem).where(
            TodoItem.source == "coach",
            TodoItem.status != "completed",
        ).order_by(desc(TodoItem.created_at)).limit(5)
    )
    for t in todo_result.scalars():
        when = t.scheduled_date or t.due_date
        lines.append(f"- 待办未完成：{t.title}{f'（回看日 {when}）' if when else ''}"
                     + (f"\n  核对问法参考描述：{(t.description or '')[:80]}" if t.description else ""))

    # 2. 未关联待办的 open 跟进项
    if len(lines) < 5:
        result = await db.execute(
            select(AgentSession).where(
                AgentSession.mode == "coach",
                AgentSession.id != exclude_session_id,
                AgentSession.followups.is_not(None),
            ).order_by(desc(AgentSession.updated_at))
        )
        for s in result.scalars():
            for f in (s.followups or []):
                if f.get("status") == "open" and not f.get("todo_id"):
                    review = f"（回看日 {f['review_on']}）" if f.get("review_on") else ""
                    lines.append(f"- 上次承诺：{f.get('text', '')}{review}\n  核对问法：{f.get('check_question', '做到了吗？')}")
            if len(lines) >= 5:
                break
    return "\n".join(lines[:5])


async def finalize_coach_session(db: AsyncSession, session: AgentSession) -> dict:
    """教练会话结束沉淀：生成总结/洞察/画像更新，写回 session 和画像"""
    messages = await derive_messages(db, session.id)
    conversation = "\n".join(
        f"{'用户' if m['role'] == 'user' else '教练'}：{m.get('content', '')}"
        for m in messages if m.get("content")
    )[-8000:]
    if len(conversation.strip()) < 20:
        raise ValueError("对话内容太短，没什么可沉淀的")

    config = await get_active_ai_config(db, module_name="coaching")
    if not config:
        config = await get_active_ai_config(db)
    if not config:
        raise ValueError("未配置 AI 模型")

    profile_text = await get_user_profile_text(db)
    prompt = COACH_FINALIZE_PROMPT.replace("{user_profile}", profile_text).replace("{conversation}", conversation)
    url, headers, payload = _build_request(config, [{"role": "user", "content": prompt}])
    payload["max_tokens"] = min(config.max_tokens, 2048)
    payload["temperature"] = 0.3
    # 结构化提取禁思维链（省钱省时）
    if config.provider == "deepseek":
        payload["thinking"] = {"type": "disabled"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    parsed = _parse_ai_json(data["choices"][0]["message"]["content"] or "")

    session.summary = (parsed.get("summary") or "")[:500] or None
    session.insights = parsed.get("insights") or []

    # 跟进项：承诺+核对问题+回看日+待建任务草稿（session.followups 追加，open 状态）
    commitment = parsed.get("commitment")
    proposed_todos = parsed.get("proposed_todos") or []
    if commitment:
        followup = {
            "text": commitment,
            "check_question": parsed.get("check_question") or "做到了吗？",
            "review_on": parsed.get("review_on"),
            "todo_id": None,
            "todo_draft": proposed_todos[0] if proposed_todos else None,  # 待建任务草稿，用户点才真建
            "status": "open",
            "created_at": datetime.now().isoformat(),
        }
        session.followups = (session.followups or []) + [followup]
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(session, "followups")  # JSON 列显式标脏，确保落库
    await db.flush()

    profile_updated = []
    updates = parsed.get("profile_updates") or []
    if updates:
        try:
            profile_updated = await update_user_profile(db, updates)
        except Exception as e:
            logger.warning(f"教练沉淀画像更新失败: {e}")

    logger.info(f"教练会话 #{session.id} 沉淀完成: summary={bool(session.summary)} insights={len(session.insights or [])} followups={len(session.followups or [])} proposed={len(proposed_todos)}")
    return {
        "summary": session.summary,
        "insights": session.insights,
        "coaching_type": parsed.get("coaching_type"),
        "commitment": commitment,
        "proposed_todos": proposed_todos,
        "profile_updates": profile_updated,
    }


async def create_todo_from_followup(db: AsyncSession, session: AgentSession, followup_index: int) -> dict:
    """沉淀卡片「建成待办」：把跟进项上的草稿真正建成待办（source=coach 关联本会话），回写 todo_id"""
    from app.models.todo import TodoItem

    followups = session.followups or []
    if followup_index < 0 or followup_index >= len(followups):
        raise ValueError("跟进项不存在")
    f = followups[followup_index]
    if f.get("todo_id"):
        raise ValueError("这条跟进已经建成待办了")
    draft = f.get("todo_draft")
    if not draft or not draft.get("title"):
        raise ValueError("这条跟进没有待建任务草稿")

    item = TodoItem(
        title=draft["title"][:500],
        description=draft.get("description"),
        quadrant=draft.get("quadrant") or 2,  # 默认重要不紧急
        category=draft.get("category"),
        due_date=date.fromisoformat(draft["due_date"]) if draft.get("due_date") else None,
        # 用户没说截止时，回看日写进计划日期
        scheduled_date=date.fromisoformat(draft["scheduled_date"]) if draft.get("scheduled_date") else (
            date.fromisoformat(f["review_on"]) if f.get("review_on") else None
        ),
        status="planned",
        source="coach",
        source_id=session.id,
    )
    db.add(item)
    await db.flush()
    f["todo_id"] = item.id
    # JSON 列就地/重赋变更检测均不可靠（实测两种都不发 UPDATE），必须显式 flag_modified
    from sqlalchemy.orm.attributes import flag_modified
    session.followups = json.loads(json.dumps(followups, ensure_ascii=False))
    flag_modified(session, "followups")
    await db.commit()
    logger.info(f"会话 #{session.id} 跟进项 #{followup_index} 建成待办 #{item.id}")
    return {"todo_id": item.id, "title": item.title}


async def close_followup_by_todo(db: AsyncSession, todo_id: int) -> None:
    """待办完成时回写：source=coach 待办关联会话里的同 todo_id 跟进项标 done（评审补充的闭环）"""
    from app.models.todo import TodoItem
    todo = await db.get(TodoItem, todo_id)
    if not todo or todo.source != "coach" or not todo.source_id:
        return
    session = await db.get(AgentSession, todo.source_id)
    if not session or not session.followups:
        return
    changed = False
    for f in session.followups:
        if f.get("todo_id") == todo_id and f.get("status") == "open":
            f["status"] = "done"
            changed = True
    if changed:
        # JSON 列变更必须显式 flag_modified（重赋新对象也未必发 UPDATE，实测）
        from sqlalchemy.orm.attributes import flag_modified
        session.followups = json.loads(json.dumps(session.followups, ensure_ascii=False))
        flag_modified(session, "followups")
        await db.flush()
        logger.info(f"待办 #{todo_id} 完成，会话 #{session.id} 的跟进项已标 done")
