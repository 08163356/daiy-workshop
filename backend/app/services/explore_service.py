"""探索模式：HUMAN 3.0 发展评估。

整段会话注入 human3 技能。结束时生成报告，日记 / 画像 / 一条待办都要用户点了才写。
不并进教练的跟进项。教练只读这里抽出的一句核心问题。
"""
from __future__ import annotations

import logging
from datetime import date

import httpx
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.agent import AgentSession
from app.models.ai_config import UserProfile
from app.models.diary import DiaryEntry
from app.services.agent_session import derive_messages
from app.services.ai_service import get_active_ai_config, get_user_profile_text, _build_request, _parse_ai_json

logger = logging.getLogger(__name__)

PROFILE_CATEGORIES = {
    "价值观信念", "健康运动", "家庭关系", "情绪模式",
    "职业发展", "生活状态", "成长目标", "工具资源",
}
QUADRANT_LABELS = (
    ("mind", "心智"),
    ("body", "身体"),
    ("spirit", "精神"),
    ("vocation", "志业"),
)

EXPLORE_FINALIZE_PROMPT = """基于下面的发展评估对话，抽出一份结构化评估。材料不够的字段用简短中文写「这次没谈清」，不要编造成已经确认的事实。

规则：
- 不要输出总分、百分比，也不要写 1.0 / 2.0 / 3.0。位置只用：顺从、个人化、综合，可以加「偏……」
- 阶段只用：失调、不确定、发现
- profile_updates 只保留用户原话能支撑的稳定判断，这次的情绪不要写。分类只能是：价值观信念、健康运动、家庭关系、情绪模式、职业发展、生活状态、成长目标、工具资源。evidence 用用户原话短句。最多 6 条，宁可少
- next_action 是 24 小时内能做完的一个动作；没有就空字符串
- days_30.practices 最多 3 条，每条是 15-30 分钟能做的事
- 语气直接，指出知道和做到的差距

严格 JSON：
{
  "metatype_name": "",
  "metatype_desc": "",
  "lifestyle_name": "",
  "lifestyle_desc": "",
  "quadrants": {
    "mind": {"archetype": "", "phase": "", "level_label": "", "strengths": "", "gaps": "", "lifestyle_impact": "", "false_transformation": ""},
    "body": {"archetype": "", "phase": "", "level_label": "", "strengths": "", "gaps": "", "lifestyle_impact": "", "false_transformation": ""},
    "spirit": {"archetype": "", "phase": "", "level_label": "", "strengths": "", "gaps": "", "lifestyle_impact": "", "false_transformation": ""},
    "vocation": {"archetype": "", "phase": "", "level_label": "", "strengths": "", "gaps": "", "lifestyle_impact": "", "false_transformation": ""}
  },
  "primary_block": "",
  "unlock": "",
  "hidden_pattern": "",
  "cascade_warning": "",
  "core_problem": "",
  "days_30": {"problem": "", "approach": "", "practices": [], "weekly": "", "metric": ""},
  "days_90": "",
  "months_6_12": "",
  "glitch_note": "",
  "warnings": [],
  "next_action": "",
  "truth": "",
  "profile_updates": [{"category": "", "key": "", "value": "", "evidence": ""}]
}

## 用户画像
{user_profile}

## 对话内容
{conversation}"""


def _explore_pack(session: AgentSession) -> dict | None:
    for item in session.followups or []:
        if isinstance(item, dict) and item.get("kind") == "explore":
            return item
    return None


def _save_pack(session: AgentSession, pack: dict) -> None:
    others = [f for f in (session.followups or []) if not (isinstance(f, dict) and f.get("kind") == "explore")]
    session.followups = others + [pack]
    flag_modified(session, "followups")


def public_result(session: AgentSession) -> dict:
    pack = _explore_pack(session) or {}
    insights = session.insights if isinstance(session.insights, list) else []
    return {
        "summary": session.summary,
        "insights": [x for x in insights if isinstance(x, str)],
        "core_problem": pack.get("core_problem") or "",
        "diary_id": pack.get("diary_id"),
        "profile_updates": pack.get("profile_updates") or [],
        "todo_draft": pack.get("todo_draft"),
        "todo_id": pack.get("todo_id"),
    }


async def get_latest_explore_brief(db: AsyncSession, exclude_session_id: int) -> str:
    """最近一次已生成的发展评估，压成一句核心问题。教练和再次探索都只用这一句。"""
    result = await db.execute(
        select(AgentSession)
        .where(
            AgentSession.mode == "explore",
            AgentSession.id != exclude_session_id,
            AgentSession.summary.is_not(None),
        )
        .order_by(desc(AgentSession.updated_at))
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if not session:
        return ""
    pack = _explore_pack(session) or {}
    problem = (pack.get("core_problem") or "").strip()
    if not problem:
        for line in session.insights or []:
            if isinstance(line, str) and line.startswith("核心问题"):
                problem = line.split("：", 1)[-1].strip()
                break
    when = session.updated_at.strftime("%m-%d") if session.updated_at else ""
    title = session.title or "发展评估"
    if problem:
        return f"[{when}] {title}：核心问题是{problem}"
    return f"[{when}] {title}：已有一份评估，这次先问上次的判断还成不成立"


def _quadrant(parsed: dict, key: str) -> dict:
    raw = (parsed.get("quadrants") or {}).get(key) or {}
    return raw if isinstance(raw, dict) else {}


def _render_markdown(parsed: dict) -> str:
    lines = [
        f"# {parsed.get('metatype_name') or '发展评估'}",
        "",
        (parsed.get("metatype_desc") or "").strip(),
        "",
        f"## 生活方式：{parsed.get('lifestyle_name') or '未命名'}",
        (parsed.get("lifestyle_desc") or "").strip(),
        "",
        "## 四象限",
    ]
    for key, label in QUADRANT_LABELS:
        q = _quadrant(parsed, key)
        lines += [
            f"### {label}：{q.get('archetype') or '这次没谈清'}",
            f"- 阶段：{q.get('phase') or '这次没谈清'}",
            f"- 位置：{q.get('level_label') or '这次没谈清'}",
            f"- 长处：{q.get('strengths') or ''}",
            f"- 缺口：{q.get('gaps') or ''}",
            f"- 对生活的影响：{q.get('lifestyle_impact') or ''}",
        ]
        false_hit = (q.get("false_transformation") or "").strip()
        if false_hit:
            lines.append(f"- 说了但没落地：{false_hit}")
        lines.append("")
    lines += [
        "## 跨象限",
        f"- 主要堵塞：{parsed.get('primary_block') or ''}",
        f"- 杠杆：{parsed.get('unlock') or ''}",
        f"- 没看见的模式：{parsed.get('hidden_pattern') or ''}",
        f"- 连锁风险：{parsed.get('cascade_warning') or ''}",
        "",
        "## 核心问题",
        (parsed.get("core_problem") or "").strip(),
        "",
        "## 接下来 30 天",
    ]
    days = parsed.get("days_30") if isinstance(parsed.get("days_30"), dict) else {}
    lines += [
        f"- 问题：{days.get('problem') or ''}",
        f"- 做法：{days.get('approach') or ''}",
    ]
    for practice in days.get("practices") or []:
        if isinstance(practice, str) and practice.strip():
            lines.append(f"- 每日：{practice.strip()}")
    if days.get("weekly"):
        lines.append(f"- 每周：{days['weekly']}")
    if days.get("metric"):
        lines.append(f"- 怎样算有进展：{days['metric']}")
    lines += [
        "",
        "## 接下来 90 天",
        (parsed.get("days_90") or "").strip(),
        "",
        "## 半年到一年",
        (parsed.get("months_6_12") or "").strip(),
        "",
        "## 加速器",
        (parsed.get("glitch_note") or "").strip(),
        "",
        "## 要当心的",
    ]
    warnings = [w.strip() for w in (parsed.get("warnings") or []) if isinstance(w, str) and w.strip()]
    if warnings:
        lines.extend(f"- {w}" for w in warnings)
    else:
        lines.append("- 这次没有单独的警告")
    lines += [
        "",
        "## 24 小时内",
        (parsed.get("next_action") or "").strip() or "这次没有收成一个动作",
        "",
        "## 直话",
        (parsed.get("truth") or "").strip(),
    ]
    return "\n".join(lines).strip()[:20000]


def _insight_lines(parsed: dict) -> list[str]:
    lines = []
    for key, label in QUADRANT_LABELS:
        q = _quadrant(parsed, key)
        position = (q.get("level_label") or "").strip()
        archetype = (q.get("archetype") or "").strip()
        text = "，".join(x for x in (position, archetype) if x)
        lines.append(f"{label}：{text or '这次没谈清'}")
    problem = (parsed.get("core_problem") or "").strip()
    if problem:
        lines.append(f"核心问题：{problem}")
    return lines


def _action_items(parsed: dict) -> list[str]:
    items = []
    next_action = (parsed.get("next_action") or "").strip()
    if next_action:
        items.append(next_action)
    days = parsed.get("days_30") if isinstance(parsed.get("days_30"), dict) else {}
    for practice in days.get("practices") or []:
        if isinstance(practice, str) and practice.strip():
            items.append(practice.strip())
        if len(items) >= 4:
            break
    return items[:4]


async def _annotate_profiles(db: AsyncSession, updates: list) -> list[dict]:
    result = await db.execute(select(UserProfile))
    existing = list(result.scalars().all())
    annotated = []
    for item in updates:
        if not isinstance(item, dict):
            continue
        category = (item.get("category") or "").strip()
        key = (item.get("key") or "").strip()
        value = (item.get("value") or "").strip()
        if category not in PROFILE_CATEGORIES or not key or not value:
            continue
        match = None
        for row in existing:
            if row.category != category:
                continue
            if row.key == key or key in row.key or row.key in key:
                match = row
                break
        conflict = bool(match and (match.value or "").strip() != value)
        annotated.append({
            "category": category,
            "key": match.key if match else key[:200],
            "value": value[:500],
            "evidence": (item.get("evidence") or "")[:300],
            "conflict": conflict,
            "existing_value": match.value if conflict else None,
            "applied": False,
        })
        if len(annotated) >= 6:
            break
    return annotated


async def finalize_explore_session(db: AsyncSession, session: AgentSession) -> dict:
    """生成评估报告并挂在会话上。不写日记、画像、待办。"""
    if session.mode != "explore":
        raise ValueError("只有探索会话可以生成评估")
    if session.summary:
        return {"message": "已生成过", **public_result(session)}

    messages = await derive_messages(db, session.id)
    conversation = "\n".join(
        f"{'用户' if m['role'] == 'user' else '评估'}：{m.get('content', '')}"
        for m in messages if m.get("content")
    )[-12000:]
    if len(conversation.strip()) < 20:
        raise ValueError("对话内容太短，还生成不了评估")

    config = await get_active_ai_config(db)
    if not config:
        raise ValueError("未配置 AI 模型")
    profile_text = await get_user_profile_text(db)
    prompt = (
        EXPLORE_FINALIZE_PROMPT
        .replace("{user_profile}", profile_text)
        .replace("{conversation}", conversation)
    )
    url, headers, payload = _build_request(config, [{"role": "user", "content": prompt}])
    payload["max_tokens"] = min(config.max_tokens, 4096)
    payload["temperature"] = 0.3
    if config.provider == "deepseek":
        payload["thinking"] = {"type": "disabled"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    parsed = _parse_ai_json(data["choices"][0]["message"]["content"] or "")

    core_problem = (parsed.get("core_problem") or "").strip()
    next_action = (parsed.get("next_action") or "").strip()
    session.summary = _render_markdown(parsed)
    session.insights = _insight_lines(parsed)
    flag_modified(session, "insights")
    pack = {
        "kind": "explore",
        "core_problem": core_problem,
        "action_items": _action_items(parsed),
        "diary_id": None,
        "profile_updates": await _annotate_profiles(db, parsed.get("profile_updates") or []),
        "todo_draft": {
            "title": next_action[:200],
            "description": f"发展评估的 24 小时行动。核心问题：{core_problem}"[:500],
            "category": "life",
            "quadrant": 2,
        } if next_action else None,
        "todo_id": None,
    }
    _save_pack(session, pack)
    await db.flush()
    logger.info(f"探索会话 #{session.id} 评估已生成，待用户确认写入")
    return {"message": "评估已生成", **public_result(session)}


async def save_explore_diary(db: AsyncSession, session: AgentSession) -> dict:
    if session.mode != "explore":
        raise ValueError("只有探索会话可以写入日记")
    pack = _explore_pack(session)
    if not pack or not session.summary:
        raise ValueError("还没有评估报告")
    if pack.get("diary_id"):
        return {"diary_id": pack["diary_id"], "already": True}
    entry = DiaryEntry(
        date=date.today(),
        title="HUMAN 3.0 发展评估",
        content=session.summary,
        tags=["自我探索", "HUMAN3.0"],
        key_issues=[pack["core_problem"]] if pack.get("core_problem") else [],
        action_items=pack.get("action_items") or [],
        source="explore",
    )
    db.add(entry)
    await db.flush()
    pack["diary_id"] = entry.id
    _save_pack(session, pack)
    await db.flush()
    return {"diary_id": entry.id, "already": False}


async def apply_explore_profile(db: AsyncSession, session: AgentSession, indices: list[int]) -> dict:
    """只写用户勾选的画像。矛盾项默认不在勾选里，勾了才覆盖。"""
    if session.mode != "explore":
        raise ValueError("只有探索会话可以写入画像")
    pack = _explore_pack(session)
    if not pack:
        raise ValueError("还没有评估报告")
    updates = pack.get("profile_updates") or []
    chosen = {i for i in indices if isinstance(i, int)}
    written = []
    for index, item in enumerate(updates):
        if index not in chosen or item.get("applied"):
            continue
        category = item.get("category") or ""
        key = item.get("key") or ""
        value = item.get("value") or ""
        if category not in PROFILE_CATEGORIES or not key or not value:
            continue
        result = await db.execute(
            select(UserProfile).where(UserProfile.category == category, UserProfile.key == key)
        )
        row = result.scalar_one_or_none()
        if row:
            row.value = value
            row.source_count = (row.source_count or 1) + 1
            row.confidence = max(row.confidence or 0, 0.65)
            row.last_evidence = item.get("evidence") or ""
        else:
            db.add(UserProfile(
                category=category, key=key, value=value,
                confidence=0.65, source_count=1,
                last_evidence=item.get("evidence") or "",
            ))
        item["applied"] = True
        written.append({"category": category, "key": key})
    pack["profile_updates"] = updates
    _save_pack(session, pack)
    await db.flush()
    return {"written": written, "profile_updates": updates}


async def create_explore_todo(db: AsyncSession, session: AgentSession) -> dict:
    if session.mode != "explore":
        raise ValueError("只有探索会话可以建成待办")
    pack = _explore_pack(session)
    if not pack:
        raise ValueError("还没有评估报告")
    if pack.get("todo_id"):
        return {"todo_id": pack["todo_id"], "already": True}
    draft = pack.get("todo_draft") or {}
    if not draft.get("title"):
        raise ValueError("这次评估没有 24 小时行动")
    from app.models.todo import TodoItem

    item = TodoItem(
        title=draft["title"][:500],
        description=draft.get("description"),
        quadrant=draft.get("quadrant") or 2,
        category=draft.get("category") or "life",
        status="planned",
        scheduled_date=date.today(),
        source="explore",
        source_id=session.id,
    )
    db.add(item)
    await db.flush()
    pack["todo_id"] = item.id
    _save_pack(session, pack)
    await db.flush()
    return {"todo_id": item.id, "title": item.title, "already": False}
