"""Agent 工具注册表

每个工具 = name + description（给模型看的触发说明）+ JSON Schema 参数 + async execute。
第一批全部只读。execute 结果会被截断回填给模型，防止上下文爆炸。
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 回填给模型的工具结果最大长度（保护上下文；报告类全量数据走管线直注，不经过这里）
MAX_TOOL_RESULT_CHARS = 8000


@dataclass
class AgentTool:
    name: str
    description: str
    parameters: dict
    execute: Callable[..., Awaitable[Any]]
    requires_confirm: bool = False
    hidden: bool = False  # 不暴露给模型（仅由系统编排触发，如 /日记 保存管线）


TOOLS: dict[str, AgentTool] = {}


def register(tool: AgentTool) -> None:
    TOOLS[tool.name] = tool


def get_tool_schemas() -> list[dict]:
    """OpenAI 兼容的 tools 参数格式（hidden 工具不暴露给模型）"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in TOOLS.values()
        if not t.hidden
    ]


async def execute_tool(db: AsyncSession, name: str, args: dict) -> dict:
    """执行工具并截断结果。未知工具/参数错误不抛给模型循环外，作为错误结果回填。"""
    tool = TOOLS.get(name)
    if not tool:
        return {"error": f"未知工具: {name}"}
    try:
        result = await tool.execute(db, **args)
        text = result if isinstance(result, str) else _to_text(result)
        truncated = len(text) > MAX_TOOL_RESULT_CHARS
        if truncated:
            text = text[:MAX_TOOL_RESULT_CHARS] + f"\n...(结果共 {len(text)} 字符，已截断——可分多次、缩小范围查询)"
        out = {"content": text, "truncated": truncated}
        # 特殊工具（任务单草稿）把结构化数据透传给 agent_loop 生成专属 SSE 事件
        if isinstance(result, dict) and "draft" in result:
            out["draft"] = result["draft"]
        return out
    except TypeError as e:
        return {"error": f"参数错误: {e}"}
    except Exception as e:
        logger.error(f"工具 {name} 执行失败: {e}", exc_info=True)
        return {"error": f"工具执行失败: {e}"}


def _to_text(result: Any) -> str:
    import json
    return json.dumps(result, ensure_ascii=False, default=str)


def _lines(items: list[str]) -> str:
    return "\n".join(items) if items else "（无记录）"


# ==================== 只读工具 ====================

async def _tool_query_todos(db: AsyncSession, status: str | None = None, quadrant: int | None = None,
                            limit: int = 50, period: str | None = None,
                            start_date: str | None = None, end_date: str | None = None) -> str:
    from datetime import datetime as _dt, time as _time
    from sqlalchemy import and_, or_, func as sql_func
    from app.models.todo import TodoItem
    q_names = {1: "重要紧急", 2: "重要不紧急", 3: "紧急不重要", 4: "不重要不紧急"}

    def _fmt(t, prefix: str = "- ") -> str:
        return (
            f"{prefix}[{q_names.get(t.quadrant, '?')}][{t.status}] [{t.title}](todo:{t.id})"
            + (f"（截止 {t.due_date}）" if t.due_date else "")
            + (f"（计划 {t.scheduled_date}）" if t.scheduled_date else "")
            + (f"（紧急{t.urgency}）" if t.urgency else "")
        )

    # 只查父任务，子任务挂到父任务下方，避免父子分离导致模型误读为独立任务
    base = select(TodoItem).where(TodoItem.parent_id.is_(None))
    if status:
        base = base.where(TodoItem.status == status)
    if quadrant:
        base = base.where(TodoItem.quadrant == quadrant)
    if period or (start_date and end_date):
        s, e = _resolve_period(period, start_date, end_date)
        sd, ed = date.fromisoformat(s), date.fromisoformat(e)
        lower = _dt.combine(sd, _time.min)
        upper = _dt.combine(ed + timedelta(days=1), _time.min)
        base = base.where(or_(
            and_(TodoItem.scheduled_date <= ed, or_(TodoItem.scheduled_end_date >= sd, and_(TodoItem.scheduled_end_date.is_(None), TodoItem.scheduled_date >= sd))),
            and_(TodoItem.due_date >= sd, TodoItem.due_date <= ed),
            and_(TodoItem.completed_at >= lower, TodoItem.completed_at < upper),
            and_(TodoItem.created_at >= lower, TodoItem.created_at < upper),
        ))
    total = (await db.execute(select(sql_func.count()).select_from(base.subquery()))).scalar() or 0
    query = base.order_by(desc(TodoItem.created_at)).limit(min(limit, 100))
    parents = list((await db.execute(query)).scalars())
    if not parents:
        return "（无记录）"
    child_rows = list((await db.execute(
        select(TodoItem).where(TodoItem.parent_id.in_([p.id for p in parents])).order_by(TodoItem.id)
    )).scalars())
    children_map: dict[int, list] = {}
    for c in child_rows:
        children_map.setdefault(c.parent_id, []).append(c)
    lines: list[str] = []
    for p in parents:
        lines.append(_fmt(p))
        for c in children_map.get(p.id, []):
            lines.append(_fmt(c, prefix="  └ 子任务: "))
    header = f"共 {total} 条父任务" + (f"（已返回前 {len(parents)} 条，可调大 limit 或加筛选）" if total > len(parents) else "")
    return header + "\n" + "\n".join(lines)


async def _tool_query_diaries(db: AsyncSession, start_date: str | None = None,
                              end_date: str | None = None, keyword: str | None = None,
                              limit: int = 10, period: str | None = None) -> str:
    from app.models.diary import DiaryEntry
    query = select(DiaryEntry).order_by(desc(DiaryEntry.date)).limit(min(limit, 20))
    if period or (start_date and end_date):
        s, e = _resolve_period(period, start_date, end_date)
        start_date, end_date = s, e
    if start_date:
        query = query.where(DiaryEntry.date >= date.fromisoformat(start_date))
    if end_date:
        query = query.where(DiaryEntry.date <= date.fromisoformat(end_date))
    if keyword:
        query = query.where(DiaryEntry.content.contains(keyword))
    result = await db.execute(query)
    return _lines([
        f"- [{d.date}] {d.title or '无标题'}：{(d.content or '')[:150]}"
        for d in result.scalars()
    ])


async def _tool_query_notes(db: AsyncSession, keyword: str | None = None,
                            source_type: str | None = None, limit: int = 10) -> str:
    from app.models.note import Note
    query = select(Note).order_by(desc(Note.reading_date)).limit(min(limit, 20))
    if keyword:
        query = query.where(Note.content.contains(keyword) | Note.title.contains(keyword))
    if source_type:
        query = query.where(Note.source_type == source_type)
    result = await db.execute(query)
    type_labels = {"book": "读书", "course": "课程", "self": "随笔"}
    return _lines([
        f"- [{n.reading_date}][{type_labels.get(n.source_type, n.source_type)}] {n.title}：{(n.summary or (n.content or ''))[:150]}"
        for n in result.scalars()
    ])


async def _tool_query_wellbeing(db: AsyncSession, entry_type: str | None = None, limit: int = 20) -> str:
    from app.models.wellbeing import WellbeingEntry
    query = select(WellbeingEntry).order_by(desc(WellbeingEntry.occurred_at)).limit(min(limit, 50))
    if entry_type:
        query = query.where(WellbeingEntry.type == entry_type)
    result = await db.execute(query)
    type_names = {"achievement": "成就", "gratitude": "感恩"}
    return _lines([
        f"- [{e.occurred_at}][{type_names.get(e.type, e.type)}·强度{e.intensity}] {(e.content or '')[:100]}"
        for e in result.scalars()
    ])


async def _tool_query_investments(db: AsyncSession, limit: int = 10) -> str:
    from app.models.investment import InvestmentReflection
    result = await db.execute(
        select(InvestmentReflection).order_by(desc(InvestmentReflection.date)).limit(min(limit, 20))
    )
    return _lines([
        f"- [{r.date}] {r.title or '反思'}：{(r.content or '')[:150]}"
        for r in result.scalars()
    ])


async def _tool_get_profile(db: AsyncSession) -> str:
    from app.services.ai_service import get_user_profile_text
    return await get_user_profile_text(db)


def _resolve_period(period: str | None, start: str | None, end: str | None) -> tuple[str, str]:
    """命名周期 → 日期区间（服务端确定性计算，不靠模型算日期）"""
    from datetime import timedelta
    if start and end:
        return start, end
    today = date.today()
    if period == "today":
        s, e = today, today
    elif period == "yesterday":
        s = e = today - timedelta(days=1)
    elif period == "this_week":
        s, e = today - timedelta(days=today.weekday()), today
    elif period == "last_week":
        monday = today - timedelta(days=today.weekday())
        s, e = monday - timedelta(days=7), monday - timedelta(days=1)
    elif period == "last_7_days":
        s, e = today - timedelta(days=6), today
    elif period == "this_month":
        s = today.replace(day=1)
        e = (s.replace(month=s.month % 12 + 1, year=s.year + (s.month == 12)) - timedelta(days=1))
    elif period == "last_month":
        first = today.replace(day=1)
        e = first - timedelta(days=1)
        s = e.replace(day=1)
    elif period == "last_three_months":
        s, e = today - timedelta(days=90), today
    elif period == "last_30_days":
        s, e = today - timedelta(days=29), today
    else:
        raise ValueError(f"未知周期: {period}；请给 start_date/end_date")
    return s.isoformat(), e.isoformat()


async def _tool_get_period_summary(db: AsyncSession, start_date: str | None = None,
                                   end_date: str | None = None,
                                   period: str | None = None) -> str:
    from app.services.task_context import get_period_bundle
    s, e = _resolve_period(period, start_date, end_date)
    return await get_period_bundle(db, date.fromisoformat(s), date.fromisoformat(e))


# ==================== 写工具（需要用户确认，fail-closed） ====================

async def _tool_create_todo(db: AsyncSession, title: str, description: str | None = None,
                            quadrant: int = 4, category: str | None = None,
                            due_date: str | None = None,
                            source: str = "manual", source_id: int | None = None,
                            parent_id: int | None = None,
                            urgency: int | None = None) -> str:
    from app.models.todo import TodoItem
    if not title.strip():
        raise ValueError("标题不能为空")
    q = quadrant if 1 <= quadrant <= 4 else 4
    parent = None
    if parent_id:
        parent = await db.get(TodoItem, parent_id)
        if not parent:
            raise ValueError(f"父任务 #{parent_id} 不存在")
        if parent.parent_id is not None:
            raise ValueError("不能给子任务再加子任务")
        if q == 4:
            q = parent.quadrant
    item = TodoItem(
        title=title.strip()[:500],
        description=description,
        quadrant=q,
        urgency=min(max(urgency or (parent.urgency if parent else 3), 1), 5),
        category=category or (parent.category if parent else None),
        due_date=date.fromisoformat(due_date) if due_date else None,
        status="planned",
        source=source,
        source_id=source_id,
        parent_id=parent.id if parent else None,
    )
    db.add(item)
    await db.flush()
    await db.commit()
    rel = f"，父任务 [{parent.title}](todo:{parent.id})" if parent else ""
    return f"已创建待办 [{item.title}](todo:{item.id})（状态：已计划{rel}）"


async def _tool_complete_todo(db: AsyncSession, todo_id: int | None = None,
                              title_keyword: str | None = None) -> str:
    from datetime import datetime as _dt
    from app.models.todo import TodoItem
    item = None
    if todo_id:
        item = await db.get(TodoItem, todo_id)
    elif title_keyword:
        result = await db.execute(
            select(TodoItem)
            .where(TodoItem.status.notin_(["completed", "cancelled", "wont_fix"]))
            .where(TodoItem.title.contains(title_keyword))
            .order_by(desc(TodoItem.created_at))
            .limit(1)
        )
        item = result.scalar_one_or_none()
    if not item:
        raise ValueError("没找到对应任务")
    item.status = "completed"
    item.completed_at = _dt.now()
    await db.flush()
    await db.commit()
    return f"已完成待办 #{item.id}「{item.title}」"


async def _tool_add_wellbeing(db: AsyncSession, entry_type: str, content: str,
                              intensity: int = 3) -> str:
    from datetime import datetime as _dt
    from app.models.wellbeing import WellbeingEntry
    if entry_type not in ("achievement", "gratitude"):
        raise ValueError("entry_type 只能是 achievement（成就）或 gratitude（感恩）")
    if not content.strip():
        raise ValueError("内容不能为空")
    entry = WellbeingEntry(
        type=entry_type,
        content=content.strip()[:2000],
        intensity=min(max(intensity, 1), 5),
        occurred_at=_dt.now().date(),
        source_type="agent",
    )
    db.add(entry)
    await db.flush()
    await db.commit()
    type_name = "成就" if entry_type == "achievement" else "感恩"
    return f"已记录{type_name} #{entry.id}：{entry.content[:50]}"


async def _tool_create_diary(db: AsyncSession, content: str, title: str | None = None,
                             diary_date: str | None = None) -> str:
    from app.models.diary import DiaryEntry
    if not content.strip():
        raise ValueError("日记内容不能为空")
    entry_date = date.fromisoformat(diary_date) if diary_date else date.today()
    entry = DiaryEntry(
        date=entry_date,
        title=(title or "").strip()[:255] or f"{entry_date.isoformat()} 日记",
        content=content.strip(),
    )
    db.add(entry)
    await db.flush()
    await db.commit()
    # 与日记页保存保持同一条链路：心力候选提取 + AI 澄清问题（异步，失败不影响）
    try:
        import asyncio
        from app.services import wellbeing_ai
        asyncio.create_task(wellbeing_ai.extract_candidates_from_diary(entry.id, entry.content))
    except Exception:
        pass
    try:
        import asyncio
        from app.services.question_service import generate_questions_task
        asyncio.create_task(generate_questions_task("diary", entry.id, entry.content))
    except Exception:
        pass
    return f"已保存日记 #{entry.id}（{entry.date}「{entry.title}」）。心力提取和澄清问题会在后台自动生成。"


async def _tool_create_note(db: AsyncSession, title: str, content: str,
                            source_type: str = "self",
                            instructor: str | None = None, platform: str | None = None) -> str:
    import hashlib
    from datetime import datetime as _dt
    from app.models.note import Note
    if not title.strip() or not content.strip():
        raise ValueError("标题和内容都不能为空")
    if source_type not in ("book", "course", "self"):
        source_type = "self"
    now = _dt.now()
    # filename 唯一约束 + file_hash 非空是笔记表的既有要求
    note = Note(
        filename=f"agent-{now.strftime('%Y%m%d%H%M%S')}-{hashlib.md5(content.encode()).hexdigest()[:8]}.md",
        title=title.strip()[:255],
        content=content.strip(),
        reading_date=date.today(),
        word_count=len(content.strip()),
        file_hash=hashlib.md5(f"agent-{now.isoformat()}-{content[:100]}".encode()).hexdigest(),
        source_type=source_type,
        course_meta={"instructor": instructor, "platform": platform} if (instructor or platform) else None,
    )
    db.add(note)
    await db.flush()
    await db.commit()
    try:
        import asyncio
        from app.services.question_service import generate_questions_task
        asyncio.create_task(generate_questions_task("note", note.id, note.content))
    except Exception:
        pass
    type_labels = {"book": "读书笔记", "course": "课程笔记", "self": "随笔"}
    return f"已保存{type_labels[source_type]} #{note.id}「{note.title}」"


async def _tool_create_investment(db: AsyncSession, content: str, title: str | None = None) -> str:
    from app.models.investment import InvestmentReflection
    if not content.strip():
        raise ValueError("内容不能为空")
    entry = InvestmentReflection(
        date=date.today(),
        title=(title or "").strip()[:255] or "投资反思",
        content=content.strip(),
    )
    db.add(entry)
    await db.flush()
    await db.commit()
    return f"已保存投资反思 #{entry.id}（{entry.date}「{entry.title}」）"


async def _tool_save_record(db: AsyncSession, record_type: str, title: str, content: str,
                            record_date: str, analysis: str = "", structured: dict | None = None,
                            images: list | None = None) -> str:
    """/日记 /笔记 /投资 管线的确定性保存（复用老 ChatView 入库函数，分析结果一并落库）"""
    from app.api.chat import _save_diary_data, _save_reading_data, _save_investment_data
    d = date.fromisoformat(record_date)
    structured = structured or {}
    saved_images = [u for u in (images or []) if isinstance(u, str) and u.startswith("/api/uploads/images/")] or None
    if record_type == "diary":
        ids = await _save_diary_data(db, d, title, content, analysis, structured, images=saved_images)
        label = "日记"
    elif record_type == "reading":
        ids = await _save_reading_data(db, d, title, content, analysis, structured, images=saved_images)
        label = "笔记"
    elif record_type == "course":
        ids = await _save_reading_data(db, d, title, content, analysis, structured, images=saved_images, source_type="course")
        label = "课程笔记"
    elif record_type == "selfnote":
        ids = await _save_reading_data(db, d, title, content, analysis, structured, images=saved_images, source_type="self")
        label = "随笔"
    elif record_type == "investment":
        ids = await _save_investment_data(db, d, title, content, analysis, structured)
        label = "投资反思"
    else:
        raise ValueError(f"未知记录类型: {record_type}")
    suffix = "（含 AI 分析）" if analysis else "（原文，AI 分析可之后在详情页补）"
    return f"已保存{label}{suffix}，ID: {ids}"


async def _tool_search_conversations(db: AsyncSession, keyword: str, limit: int = 5) -> str:
    """跨会话回忆：在 AI 助手历史对话里搜关键词（hermes session_search 裁剪版，LIKE 够用）"""
    from sqlalchemy import or_
    from app.models.agent import AgentEvent, AgentSession
    if not keyword.strip():
        raise ValueError("关键词不能为空")
    kw = f"%{keyword.strip()}%"
    result = await db.execute(
        select(AgentEvent, AgentSession.title)
        .join(AgentSession, AgentSession.id == AgentEvent.session_id)
        .where(
            AgentEvent.event_type.in_(["user_message", "assistant_message"]),
            or_(
                AgentEvent.payload["content"].as_string().like(kw),
                AgentEvent.payload["thinking"].as_string().like(kw),
            ),
        )
        .order_by(desc(AgentEvent.created_at))
        .limit(min(limit, 20) * 2)  # 可能同一会话多条命中，多取再去重
    )
    rows = result.all()
    if not rows:
        return "历史对话里没有找到相关内容"
    seen_sessions: dict[int, int] = {}
    lines: list[str] = []
    for ev, title in rows:
        p = ev.payload or {}
        content = (p.get("content") or "").strip()
        if not content:
            continue
        seen_sessions[ev.session_id] = seen_sessions.get(ev.session_id, 0) + 1
        if seen_sessions[ev.session_id] > 1:
            continue  # 每个会话只取第一条命中（自适应水合的裁剪）
        who = "我" if ev.event_type == "user_message" else "AI"
        snippet = content[:150].replace("\n", " ")
        lines.append(f"- [{ev.created_at.strftime('%m-%d %H:%M')}] 会话#{ev.session_id}「{title or '未命名'}」 {who}: {snippet}")
        if len(lines) >= limit:
            break
    return "历史对话命中：\n" + "\n".join(lines) + "\n\n（需要看完整对话可让用户打开对应会话）"


async def _tool_search_blog(db: AsyncSession, keyword: str, limit: int = 8) -> str:
    """检索个人博客公开索引（blog-index.json），不是知识库。"""
    from app.services.blog_search import format_search_result
    return format_search_result(keyword, limit=limit)


async def _tool_search_interview(db: AsyncSession, keyword: str, limit: int = 8) -> str:
    """检索 interview 作品集/面试材料（项目、STAR、技术问答、简历等）。"""
    from app.services.interview_search import format_search_result
    return format_search_result(keyword, limit=limit)


async def _tool_search_kb(db: AsyncSession, keyword: str | None = None,
                          item_type: str | None = None, limit: int = 8) -> str:
    """检索知识库（文章 / 工具收藏）"""
    from sqlalchemy import or_
    from app.models.article import Article
    query = select(Article).order_by(desc(Article.created_at)).limit(min(limit or 8, 20))
    if keyword and keyword.strip():
        kw = keyword.strip()
        query = query.where(or_(
            Article.title.contains(kw),
            Article.content.contains(kw),
            Article.summary.contains(kw),
        ))
    if item_type in ("article", "tool"):
        query = query.where(Article.item_type == item_type)
    rows = list((await db.execute(query)).scalars())
    if not rows:
        return "知识库没有匹配的条目。"
    lines = []
    for a in rows:
        kind = "工具" if a.item_type == "tool" else "文章"
        snippet = (a.summary or a.content or "")[:120].replace("\n", " ")
        url = f" {a.url}" if a.url else ""
        lines.append(f"- #{a.id} [{kind}] {a.title}{url}" + (f"：{snippet}" if snippet else ""))
    return "知识库检索结果：\n" + "\n".join(lines)


async def _tool_save_knowledge(db: AsyncSession, title: str, content: str | None = None,
                               url: str | None = None, summary: str | None = None,
                               item_type: str = "article", tags: list | None = None) -> str:
    """把一条知识写入知识库（需用户确认）"""
    from app.schemas.article import ArticleCreate
    from app.services.kb_service import create_article
    if not (title or "").strip():
        raise ValueError("标题不能为空")
    if not (content or "").strip() and not (url or "").strip():
        raise ValueError("内容和链接至少填一个")
    kind = item_type if item_type in ("article", "tool") else "article"
    tag_list = tags
    if isinstance(tag_list, str):
        tag_list = [t.strip() for t in tag_list.split(",") if t.strip()]
    elif tag_list is not None and not isinstance(tag_list, list):
        tag_list = None
    article = await create_article(db, ArticleCreate(
        title=title.strip()[:500],
        url=(url or "").strip() or None,
        content=(content or "").strip() or None,
        summary=(summary or "").strip() or None,
        item_type=kind,
        content_type="url" if (url or "").strip() else "text",
        tags=tag_list or None,
    ))
    await db.commit()
    label = "工具" if kind == "tool" else "文章"
    return f"已收入知识库 #{article.id}「{article.title}」（{label}）"


async def _tool_scan_todos(db: AsyncSession) -> str:
    """待办体检：复用日历页的扫描，只返回值得看的建议，不改数据"""
    from app.services.todo_service import ai_scan_todos
    data = await ai_scan_todos(db)
    labels = {
        "can_analyze": "可分析", "can_plan": "可细化", "unnecessary": "建议关闭",
        "wrong_priority": "优先级偏差", "can_answer": "可直接解答", "healthy": "状态良好",
    }
    items = data.get("items") or []
    interesting = [i for i in items if i.get("category") != "healthy"]
    lines = [
        data.get("scan_summary") or "扫描完成。",
        f"共扫描 {data.get('total_scanned', len(items))} 条，状态良好 {data.get('healthy_count', 0)} 条。",
    ]
    for item in interesting[:12]:
        cat = labels.get(item.get("category"), item.get("category") or "建议")
        advice = (item.get("suggestion") or item.get("reason") or "").replace("\n", " ")
        lines.append(f"- [{cat}] {item.get('todo_title')}: {advice[:180]}")
    if len(interesting) > 12:
        lines.append(f"另有 {len(interesting) - 12} 条建议未展开。")
    lines.append("以上只是建议，没有改任何任务。用户明确同意关闭、改优先级或标完成时，再调用对应写工具并等确认。")
    return "\n".join(lines)


async def _tool_propose_schedule(db: AsyncSession, days: int = 7) -> str:
    """给出排期建议，不写入。用户同意后再 apply_schedule。"""
    import json
    from app.services.todo_service import ai_schedule_todos
    span = max(1, min(int(days or 7), 30))
    data = await ai_schedule_todos(db, days=span)
    schedule = data.get("schedule") or []
    lines = [data.get("summary") or "排期建议如下。"]
    tips = data.get("tips") or []
    for tip in tips[:3]:
        lines.append(f"提示：{tip}")
    for item in schedule[:20]:
        minutes = item.get("estimated_minutes")
        minute_text = f"{minutes}分钟" if minutes else "未估时"
        lines.append(
            f"- #{item.get('todo_id')} → {item.get('scheduled_date')}（{minute_text}）{item.get('reason') or ''}"
        )
    if len(schedule) > 20:
        lines.append(f"另有 {len(schedule) - 20} 条。")
    compact = [
        {
            "todo_id": item.get("todo_id"),
            "scheduled_date": item.get("scheduled_date"),
            "estimated_minutes": item.get("estimated_minutes"),
        }
        for item in schedule
        if item.get("todo_id") and item.get("scheduled_date")
    ]
    lines.append("先把安排告诉用户。用户同意后，把下面这份数据原样传给 apply_schedule，不要自己改日期。")
    lines.append(json.dumps(compact, ensure_ascii=False))
    return "\n".join(lines)


async def _tool_apply_schedule(db: AsyncSession, schedules: list | str, summary: str | None = None) -> str:
    """把已确认的排期写入待办"""
    import json
    from app.models.todo import TodoItem
    rows = schedules
    if isinstance(rows, str):
        rows = json.loads(rows)
    if not isinstance(rows, list) or not rows:
        raise ValueError("没有可写入的排期")
    applied = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        todo_id = item.get("todo_id")
        scheduled = item.get("scheduled_date")
        if not todo_id or not scheduled:
            continue
        todo = await db.get(TodoItem, int(todo_id))
        if not todo:
            continue
        todo.scheduled_date = date.fromisoformat(str(scheduled)[:10])
        minutes = item.get("estimated_minutes")
        if minutes and int(minutes) > 0:
            todo.estimated_minutes = int(minutes)
        if todo.status in ("inbox", "evaluated"):
            todo.status = "planned"
        applied += 1
    await db.flush()
    await db.commit()
    head = f"{summary}。" if summary else ""
    return f"{head}已写入 {applied} 条排期"


async def _tool_use_skill(db: AsyncSession, name: str) -> str:
    """按需加载 skill 正文（模型读到目录后，觉得哪个适用就加载哪个）"""
    from app.services.skill_service import get_skill, render_content
    from app.services.ai_service import get_user_profile_text
    skill = await get_skill(db, name)
    if not skill or not skill.enabled:
        raise ValueError(f"技能「{name}」不存在或未启用")
    if not skill.model_invocable:
        raise ValueError(f"技能「{name}」不允许 AI 调用")
    # 使用计数（skill 改进度量的一环）
    skill.use_count = (skill.use_count or 0) + 1
    await db.flush()
    profile_text = await get_user_profile_text(db)
    return f"# 技能：{skill.title}\n\n{render_content(skill, user_profile=profile_text)}"


async def _tool_draft_tasklist(db: AsyncSession, content: str) -> dict:
    """把一段内容拆成父子任务草稿（不写库，用户编辑确认后才创建）"""
    from app.services.tasklist_service import split_tasklist
    groups = await split_tasklist(db, content)
    return {
        "content": f"已生成任务单草稿：{len(groups)} 个父任务、{sum(len(g['children']) for g in groups)} 个子任务。等待用户编辑确认。",
        "draft": {"groups": groups},
    }


async def _tool_write_analysis(db: AsyncSession, record_type: str, record_id: int,
                               analysis: str, mood: str | None = None) -> str:
    """把事后分析写回已保存的日记/笔记，而不是只留在对话里。"""
    if not analysis.strip():
        raise ValueError("分析内容不能为空")
    if record_type == "diary":
        from app.models.diary import DiaryEntry
        entry = await db.get(DiaryEntry, record_id)
        if not entry:
            raise ValueError(f"日记 #{record_id} 不存在")
        entry.ai_analysis = analysis.strip()
        if mood:
            entry.mood = mood.strip()[:50]
        await db.flush()
        await db.commit()
        return f"已把分析写回日记 #{entry.id}「{entry.title}」"
    if record_type == "note":
        from app.models.note import Note
        note = await db.get(Note, record_id)
        if not note:
            raise ValueError(f"笔记 #{record_id} 不存在")
        note.summary = analysis.strip()[:4000]
        await db.flush()
        await db.commit()
        return f"已把分析写回笔记 #{note.id}「{note.title}」"
    raise ValueError("record_type 只能是 diary 或 note")


async def _tool_query_lessons(db: AsyncSession, todo_id: int | None = None, limit: int = 20) -> str:
    from app.models.todo import TodoComment, TodoItem
    query = select(TodoComment).where(TodoComment.kind == "lesson").order_by(desc(TodoComment.created_at)).limit(min(limit, 50))
    if todo_id:
        query = query.where(TodoComment.todo_id == todo_id)
    rows = list((await db.execute(query)).scalars())
    if not rows:
        return "（无经验沉淀）"
    todo_ids = {c.todo_id for c in rows}
    titles = {t.id: t.title for t in (await db.execute(select(TodoItem).where(TodoItem.id.in_(todo_ids)))).scalars()}
    return "\n".join(
        f"- [{c.created_at.strftime('%Y-%m-%d')}][{titles.get(c.todo_id, '?')}](todo:{c.todo_id}) {c.content[:200]}"
        for c in rows
    )


async def _tool_add_lesson(db: AsyncSession, todo_id: int, content: str) -> str:
    from app.models.todo import TodoComment, TodoItem
    if not content.strip():
        raise ValueError("内容不能为空")
    todo = await db.get(TodoItem, todo_id)
    if not todo:
        raise ValueError(f"待办 #{todo_id} 不存在")
    comment = TodoComment(todo_id=todo_id, content=content.strip()[:4000], kind="lesson")
    db.add(comment)
    await db.flush()
    await db.commit()
    return f"已在 [{todo.title}](todo:{todo_id}) 记下一条经验沉淀"


def _register_defaults() -> None:
    register(AgentTool(
        name="draft_tasklist",
        description="把用户给的一段内容（收集箱内容、本周打算、零散事情）拆成父子任务草稿，不写库；用户确认后才创建。用户说「拆成任务」「收集箱」「生成任务单」「把这段整理成待办」「本周要做的事」时调用。",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "需要拆分的完整内容（保留用户原文）"},
            },
            "required": ["content"],
        },
        execute=_tool_draft_tasklist,
    ))
    register(AgentTool(
        name="use_skill",
        description="加载一个技能（skill）的正文到当前对话。系统提示词里有可用技能目录，当用户任务匹配某个技能的触发条件时调用。",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "技能名（kebab-case，目录里列出）"},
            },
            "required": ["name"],
        },
        execute=_tool_use_skill,
    ))
    register(AgentTool(
        name="query_todos",
        description="查询待办任务。可按状态、四象限或日期周期过滤。用户问任务/待办/计划/某段时间的日程时调用。优先用 period 命名周期。",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "状态过滤，如 planned/completed/in_progress"},
                "quadrant": {"type": "integer", "description": "象限过滤 1-4"},
                "period": {"type": "string", "enum": ["today", "yesterday", "this_week", "last_week", "last_7_days", "this_month", "last_month", "last_three_months", "last_30_days"],
                           "description": "命名周期，服务端算日期"},
                "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "返回条数，默认 20", "default": 20},
            },
        },
        execute=_tool_query_todos,
    ))
    register(AgentTool(
        name="query_diaries",
        description="查询日记。可按命名周期、日期范围或关键词过滤。用户问某天/某段时间的记录、心情、经历时调用。优先用 period。",
        parameters={
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["today", "yesterday", "this_week", "last_week", "last_7_days", "this_month", "last_month", "last_three_months", "last_30_days"],
                           "description": "命名周期，服务端算日期"},
                "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                "keyword": {"type": "string", "description": "内容关键词"},
                "limit": {"type": "integer", "default": 10},
            },
        },
        execute=_tool_query_diaries,
    ))
    register(AgentTool(
        name="query_notes",
        description="查询笔记（读书笔记/课程笔记/随笔）。用户问读过的书、听过的课、笔记内容、学过什么时调用。",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "标题或内容关键词"},
                "source_type": {"type": "string", "description": "来源过滤: book=读书 course=课程 self=随笔"},
                "limit": {"type": "integer", "default": 10},
            },
        },
        execute=_tool_query_notes,
    ))
    register(AgentTool(
        name="query_wellbeing",
        description="查询心力记录（成就/感恩）。用户问成就感、感恩、能量来源时调用。",
        parameters={
            "type": "object",
            "properties": {
                "entry_type": {"type": "string", "description": "achievement=成就 gratitude=感恩"},
                "limit": {"type": "integer", "default": 20},
            },
        },
        execute=_tool_query_wellbeing,
    ))
    register(AgentTool(
        name="query_investments",
        description="查询投资反思记录。用户问投资、交易、市场观察时调用。",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 10}},
        },
        execute=_tool_query_investments,
    ))
    register(AgentTool(
        name="get_user_profile",
        description="获取用户画像（用户的价值观、目标、习惯、偏好等长期特征）。回答关于用户本人的问题、或需要个性化建议时调用。",
        parameters={"type": "object", "properties": {}},
        execute=_tool_get_profile,
    ))
    register(AgentTool(
        name="get_period_summary",
        description="获取某个日期范围内任务的完整原始记录（做了什么、计时、备注）。只要用户问「某段时间/某天/本月/本周/上周/近三个月做了什么、总结、日报、周报」就必须调用，绝不凭空编造或只查待办列表。优先用 period 命名周期（服务端算日期，不会算错）；用户给了明确日期才用 start_date/end_date。",
        parameters={
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["today", "yesterday", "this_week", "last_week", "last_7_days", "this_month", "last_month", "last_three_months", "last_30_days"],
                           "description": "命名周期：当天/昨天/本周/上周/近7天/本月/上月/近三个月/近30天"},
                "start_date": {"type": "string", "description": "明确日期范围的开始 YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "明确日期范围的结束 YYYY-MM-DD"},
            },
        },
        execute=_tool_get_period_summary,
    ))
    register(AgentTool(
        name="search_conversations",
        description="搜索 AI 助手的历史对话（跨会话回忆）。用户问「我们之前聊过 X 吗」「上次说的那个…」时调用。",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "default": 5, "description": "最多返回几条"},
            },
            "required": ["keyword"],
        },
        execute=_tool_search_conversations,
    ))
    register(AgentTool(
        name="search_knowledge",
        description="检索知识库里收藏的文章和工具。用户问「我收藏过的」「知识库里有没有」「之前存的那篇」时调用。",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "标题、摘要或正文关键词，可空表示最近收藏"},
                "item_type": {"type": "string", "description": "article=文章 tool=工具，不填则都查"},
                "limit": {"type": "integer", "default": 8},
            },
        },
        execute=_tool_search_kb,
    ))
    register(AgentTool(
        name="search_blog",
        description="检索用户配置的个人博客公开索引。用户问「博客里有没有」「我写过 XX 吗」时调用。不要和 search_knowledge（知识库收藏）搞混。",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "标题、标签、分类或摘录关键词，空格分词且全部命中"},
                "limit": {"type": "integer", "default": 8, "description": "最多返回几条"},
            },
            "required": ["keyword"],
        },
        execute=_tool_search_blog,
    ))
    register(AgentTool(
        name="search_interview",
        description="检索 interview 作品集与面试材料（项目亮点、STAR、技术问答、自我介绍、简历、面试策略）。用户问「面试怎么答」「作品集里某项目」「STAR 故事」「自我介绍」「简历里写了什么」时调用。不要和 search_blog / search_knowledge 搞混。",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "项目名、技术点、问题关键词，空格分词且全部命中"},
                "limit": {"type": "integer", "default": 8, "description": "最多返回几条"},
            },
            "required": ["keyword"],
        },
        execute=_tool_search_interview,
    ))
    register(AgentTool(
        name="scan_todos",
        description="体检全部未完成待办：找出可关闭、优先级不准、可以拆细或可以直接解答的任务。用户说「体检待办」「看看任务健不健康」时调用。只给建议，不改数据。",
        parameters={"type": "object", "properties": {}},
        execute=_tool_scan_todos,
    ))
    register(AgentTool(
        name="propose_schedule",
        description="为未排期待办生成未来几天的排期建议，不写入日历。用户说「帮我排期」「安排这周」时调用。把结果告诉用户，同意后再调用 apply_schedule。",
        parameters={
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "排期天数 1-30，默认 7", "default": 7},
            },
        },
        execute=_tool_propose_schedule,
    ))
    # ---- 写工具：全部 requires_confirm ----
    register(AgentTool(
        name="create_todo",
        description="创建一条新待办任务。用户明确说「帮我记/加/新建任务」时调用。拆子任务时传 parent_id。",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "任务标题"},
                "description": {"type": "string", "description": "补充描述"},
                "quadrant": {"type": "integer", "description": "四象限 1-4，默认 4", "default": 4},
                "urgency": {"type": "integer", "description": "紧急度 1-5"},
                "category": {"type": "string", "description": "分类 work/learning/life/health 等"},
                "due_date": {"type": "string", "description": "截止日期 YYYY-MM-DD"},
                "parent_id": {"type": "integer", "description": "父任务 ID，创建子任务时填写"},
            },
            "required": ["title"],
        },
        execute=_tool_create_todo,
        requires_confirm=True,
    ))
    register(AgentTool(
        name="save_knowledge",
        description="把一条知识收进知识库。用户说「记到知识库」「收藏这篇」「/知识」时调用。文章用 item_type=article，工具用 tool。",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "条目标题"},
                "content": {"type": "string", "description": "正文或摘录"},
                "url": {"type": "string", "description": "链接，没有就空着"},
                "summary": {"type": "string", "description": "一两句摘要"},
                "item_type": {"type": "string", "description": "article 或 tool", "default": "article"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"},
            },
            "required": ["title"],
        },
        execute=_tool_save_knowledge,
        requires_confirm=True,
    ))
    register(AgentTool(
        name="apply_schedule",
        description="把用户已经同意的排期写入日历。schedules 必须用 propose_schedule 返回的那份数据，不要改日期。summary 写一句给用户确认的话。",
        parameters={
            "type": "object",
            "properties": {
                "schedules": {
                    "type": "array",
                    "description": "propose_schedule 给出的排期列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "todo_id": {"type": "integer"},
                            "scheduled_date": {"type": "string"},
                            "estimated_minutes": {"type": "integer"},
                        },
                        "required": ["todo_id", "scheduled_date"],
                    },
                },
                "summary": {"type": "string", "description": "给用户看的一句话，例如「把 6 条未排期任务排进未来 7 天」"},
            },
            "required": ["schedules"],
        },
        execute=_tool_apply_schedule,
        requires_confirm=True,
    ))
    register(AgentTool(
        name="complete_todo",
        description="把一条待办标记为已完成。用户说「某某任务做完了/完成了」时调用。",
        parameters={
            "type": "object",
            "properties": {
                "todo_id": {"type": "integer", "description": "任务 ID（知道才填）"},
                "title_keyword": {"type": "string", "description": "标题关键词（找不到 ID 时用）"},
            },
        },
        execute=_tool_complete_todo,
        requires_confirm=True,
    ))
    register(AgentTool(
        name="add_wellbeing",
        description="记录一条心力：成就（achievement）或感恩（gratitude）。用户说「记一笔成就/感恩」时调用。",
        parameters={
            "type": "object",
            "properties": {
                "entry_type": {"type": "string", "description": "achievement=成就 gratitude=感恩"},
                "content": {"type": "string", "description": "记录内容"},
                "intensity": {"type": "integer", "description": "强度 1-5，默认 3", "default": 3},
            },
            "required": ["entry_type", "content"],
        },
        execute=_tool_add_wellbeing,
        requires_confirm=True,
    ))
    register(AgentTool(
        name="create_diary",
        description="保存一篇日记。用户以 /日记 开头发消息、或明确说「帮我记日记/写进日记」时调用。保存后会自动触发心力提取等后续链路。",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "日记正文（完整保留用户原文，不要改写）"},
                "title": {"type": "string", "description": "标题，不给则自动生成"},
                "diary_date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天"},
            },
            "required": ["content"],
        },
        execute=_tool_create_diary,
        requires_confirm=True,
    ))
    register(AgentTool(
        name="create_note",
        description="保存一条笔记。用户以 /笔记 /随笔 开头发消息、或明确说「帮我记笔记」时调用；课程听课内容用 source_type=course 并尽量带上讲师/平台。",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "笔记标题"},
                "content": {"type": "string", "description": "笔记内容（完整保留用户原文）"},
                "source_type": {"type": "string", "description": "book=读书 course=课程/听课 self=个人随笔，默认 self"},
                "instructor": {"type": "string", "description": "课程讲师（source_type=course 时）"},
                "platform": {"type": "string", "description": "课程平台（source_type=course 时）"},
            },
            "required": ["title", "content"],
        },
        execute=_tool_create_note,
        requires_confirm=True,
    ))
    register(AgentTool(
        name="create_investment",
        description="保存一条投资反思/交易记录。用户以 /投资 开头发消息、或明确说「帮我记一笔投资」时调用。",
        parameters={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "反思/记录内容（完整保留用户原文）"},
                "title": {"type": "string", "description": "标题，不给则自动生成"},
            },
            "required": ["content"],
        },
        execute=_tool_create_investment,
        requires_confirm=True,
    ))
    register(AgentTool(
        name="write_analysis",
        description="把对已保存日记/笔记的分析写回记录（用户事后说「分析这篇」时用）。先 query_diaries/query_notes 拿到原文，值得分析才写；没有值得说的点就不要调用。",
        parameters={
            "type": "object",
            "properties": {
                "record_type": {"type": "string", "description": "diary 或 note"},
                "record_id": {"type": "integer", "description": "记录 ID"},
                "analysis": {"type": "string", "description": "分析正文，只写真正值得说的点，不要凑条数"},
                "mood": {"type": "string", "description": "日记情绪，可选"},
            },
            "required": ["record_type", "record_id", "analysis"],
        },
        execute=_tool_write_analysis,
        requires_confirm=True,
    ))
    register(AgentTool(
        name="query_lessons",
        description="查询待办上的经验沉淀（心得/教训）。用户问「上次这件事的教训」「经验沉淀」时调用。",
        parameters={
            "type": "object",
            "properties": {
                "todo_id": {"type": "integer", "description": "只看某一条待办时填写"},
                "limit": {"type": "integer", "default": 20},
            },
        },
        execute=_tool_query_lessons,
    ))
    register(AgentTool(
        name="add_lesson",
        description="在某条待办下记录一条经验沉淀（心得/教训）。用户说「记下这条教训/经验」时调用。",
        parameters={
            "type": "object",
            "properties": {
                "todo_id": {"type": "integer", "description": "待办 ID"},
                "content": {"type": "string", "description": "心得或教训原文"},
            },
            "required": ["todo_id", "content"],
        },
        execute=_tool_add_lesson,
        requires_confirm=True,
    ))
    register(AgentTool(
        name="__save_record",
        description="（系统编排专用，不对模型暴露）/日记 /笔记 /投资 管线的保存动作",
        parameters={"type": "object", "properties": {}},
        execute=_tool_save_record,
        requires_confirm=True,
        hidden=True,
    ))


_register_defaults()
