"""篮球反思 AI 服务

封装 6 个 AI 任务：
1. coach_review_and_blind_spots - 同步：严师点评 + 盲区识别（保存复盘后立即返回）
2. extract_skill_dimensions - 异步：抽取技术维度（受 20 词表约束），写入 SkillSnapshot
3. extract_highlights_to_wellbeing - 异步：抽取高光时刻，写入 WellbeingCandidate
4. generate_diary_summary - 异步：生成 120 字摘要，同步到当天日记
5. generate_stage_goal - 同步：生成阶段训练目标，可派单到 todo
6. evaluate_stage_goal - 同步：阶段结束 AI 评估

复用 ai_service 的模型选择/画像注入；失败均降级。
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, date as DateType, timedelta
from typing import Optional, Any

import httpx
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.basketball import (
    BasketballSession,
    BasketballGoal,
    BasketballSkillSnapshot,
)
from app.models.diary import DiaryEntry
from app.models.wellbeing import WellbeingCandidate
from app.models.todo import TodoItem
from app.services.ai_service import (
    get_active_ai_config,
    get_user_profile_text,
    _build_request,
    _parse_ai_json,
)

logger = logging.getLogger(__name__)

MODULE_NAME = "basketball"


# ==================== 固定技术维度词表（受控抽取）====================

SKILL_DIMENSIONS = [
    "投篮", "三分", "中投", "罚球", "上篮", "突破", "低位", "面框",
    "防守", "横移", "协防", "篮板", "传球", "控球", "挡拆", "无球跑动",
    "对抗", "体能", "心态", "阅读比赛",
]

FOCUS_AREAS = ["投篮", "防守", "脚步", "体能", "心态", "对抗", "其他"]


# ==================== 严师 Prompt ====================

COACH_SYSTEM_PROMPT = """你是用户的篮球私人教练，风格严苛、冷峻、直接，参考马刺主帅波波维奇——不温情、不鸡汤，但内核是真的为他/她好。

## 用户画像
{user_profile}

## 用户最近 30 天复盘历史（按时间倒序）
{history_30d}

## 严苛六条规则（必须全部遵守）
1. 永远先指出问题，不做鼓励式开场
2. 抓住用户描述里的借口、模糊词（"防不住"、"今天状态不好"、"对方太强"）、归因外部，直接戳穿
3. 对比 30 天历史，重复出现的问题用「你又一次……」开头
4. 每次最多给 1-2 条具体改进建议，多了等于没说
5. 用户文字里如果只有情绪没有事实，要求他/她下次写具体回合
6. 风格冷峻犀利，不许出现"加油"、"继续努力"、"做得不错"这种话；可以用反问和短句

## 任务
对用户这场复盘做点评，并识别盲区（重复模式 + 用户没意识到的问题）。

## 输出 JSON 格式
```json
{
  "coach_review": "教练点评的 Markdown，3-6 段，遵守上面六条规则",
  "blind_spots": [
    {
      "title": "盲区一句话标题（如：又一次只描述结果不复盘过程）",
      "evidence": "证据：从原文/历史里挑出关键句",
      "repeat_count": 3
    }
  ]
}
```

要求：
- coach_review 至少 200 字、最多 600 字
- blind_spots 0-3 条，没有就空数组
- 只输出 JSON，不要任何前后缀
"""

SKILL_EXTRACT_PROMPT = """从下面这场篮球复盘中，抽取「技术维度提及」。

## 受控词表（必须从这 20 个里选）
{dimensions}

## 复盘原文
{content}

## 任务
找出原文中明确涉及的技术维度，标记是「亮点 highlight」还是「问题 problem」。

## 规则
1. 只允许使用受控词表中的词，不允许出现"打得好"等泛词
2. 同一维度可以同时是 highlight 和 problem（如果原文同时提到正反面）
3. 原文没有明确涉及的维度不要编
4. extracted_text 是原文中的支持片段（不超过 50 字）
5. 最多 8 条，按重要性排序

## 输出 JSON 格式
```json
{
  "items": [
    {"skill_dimension": "横移", "mention_type": "problem", "extracted_text": "原文支持片段"},
    {"skill_dimension": "三分", "mention_type": "highlight", "extracted_text": "原文支持片段"}
  ]
}
```

只输出 JSON。如果完全没有可识别的维度，items 为 []。
"""

HIGHLIGHTS_PROMPT = """从下面这场篮球复盘中，挑出 0-3 个值得记入「成就账户」或「感恩账户」的瞬间。

## 用户画像
{user_profile}

## 复盘原文
{content}

## 规则
1. 成就（achievement）：用户场上做到的事——一次防住、一次关键投篮、一次坚持训练完
2. 感恩（gratitude）：被善待的瞬间——队友的传球、对手的尊重、有球场可以打
3. 强度 intensity 1-5
4. 分类（category）固定为「健康」（因为这是体育类成就）
5. 没有明确的积极瞬间就返回空数组，不要硬挖

## 输出 JSON 格式
```json
{
  "items": [
    {
      "type": "achievement",
      "content": "你今天在 X 时做到了 Y（用第二人称）",
      "category": "健康",
      "intensity": 3,
      "ai_confidence": 0.85,
      "ai_reason": "为什么算积极瞬间",
      "excerpt": "原文支持片段（30字内）"
    }
  ]
}
```

只输出 JSON。最多 3 条。
"""

DIARY_SUMMARY_PROMPT = """请用 80-120 字总结下面这场篮球复盘，第三人称、客观陈述，便于回流到当天日记。

## 复盘原文
类型：{type_label}
日期：{date}
一句话总结：{one_line}
亮点：{highlights}
问题：{problems}
情绪：{emotion}

## 任务
直接输出一段 80-120 字的中文摘要，包含场次类型、关键技术亮点/问题、情绪状态。不要标题，不要 Markdown。
"""

STAGE_GOAL_PROMPT = """你是用户的篮球教练，现在要给他/她制定**接下来 {weeks} 周**的训练目标。

## 用户画像
{user_profile}

## 用户最近 30 天复盘摘要
{history_30d}

## 上一阶段目标（如果有）
{last_goal}

## 任务
基于上面的复盘历史，找出**最该补的一项短板**，制定一个具体、可执行、可量化的阶段目标，并配套 2-4 条训练待办。

## 严格要求
1. 目标必须聚焦**一项**技术维度（不要贪多）
2. 目标必须**具体可量化**（"提升投篮"不行，"罚球命中率提升到 60%"才行）
3. 训练待办必须可执行（"每周三次罚球训练 50 个" 这种）
4. 焦点维度（focus_area）从 {focus_areas} 中选一个
5. 训练待办的 scheduled_date 在阶段周期内合理分布（开始日期 {start_date}，结束日期 {end_date}）

## 输出 JSON 格式
```json
{
  "title": "阶段目标标题（一句话）",
  "description": "为什么是这个目标（基于历史复盘的诊断，2-3 句）",
  "focus_area": "投篮",
  "todos": [
    {
      "title": "训练待办标题",
      "description": "具体怎么做",
      "scheduled_date": "2026-06-08",
      "estimated_minutes": 30
    }
  ],
  "summary": "教练对这个阶段目标的简短解释（给用户看的 1-2 句）"
}
```

只输出 JSON。
"""

EVALUATE_GOAL_PROMPT = """阶段训练已经结束，请基于实际复盘情况，对用户上一阶段的训练目标做评价。

## 阶段目标
{goal_title}
焦点：{focus_area}
周期：{start_date} 到 {end_date}

## 阶段内的复盘记录摘要
{sessions_summary}

## 任务
用严师风格，对完成度做客观评价（120-200 字）。指出：
1. 这一阶段他/她做到了什么、没做到什么（要具体引用）
2. 焦点维度是否真的有改善（看复盘里这个维度的提及变化）
3. 下一步应该往哪个方向走

直接输出文字，不要 JSON 不要 Markdown 标题。冷峻犀利。
"""


# ==================== 降级文案 ====================

FALLBACK_COACH_REVIEWS = [
    "教练今天暂时不在线。但你的复盘已经保存。\n\n建议你回看一下这场最不舒服的那个回合，把它写得更具体——是脚步迟了？还是判断错了？模糊的反思等于没反思。",
    "AI 教练今天罢工。先自己问一遍：今天这场，你借口最多的是哪一句？把它划掉，重新写一句不带借口的。",
    "技术问题，教练点评稍后再来。这段时间你可以做一件事：把这场你最不满意的一个动作，明天去球场重复练 20 次。",
]


# ==================== 工具函数 ====================

async def _ai_call_json(db: AsyncSession, prompt: str, *, max_tokens: int = 1500, temperature: float = 0.3) -> tuple[dict, str, int]:
    config = await get_active_ai_config(db, module_name=MODULE_NAME)
    if not config:
        raise RuntimeError("未配置 AI 模型")
    messages = [
        {"role": "system", "content": "你是一个严谨的 JSON 输出助手，只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]
    url, headers, payload = _build_request(config, messages)
    payload["max_tokens"] = min(config.max_tokens, max_tokens)
    payload["temperature"] = temperature
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    content = data["choices"][0]["message"]["content"]
    tokens = int(data.get("usage", {}).get("total_tokens", 0) or 0)
    parsed = _parse_ai_json(content)
    return parsed, f"{config.provider}/{config.model}", tokens


async def _ai_call_text(db: AsyncSession, prompt: str, *, max_tokens: int = 800, temperature: float = 0.5) -> tuple[str, str, int]:
    config = await get_active_ai_config(db, module_name=MODULE_NAME)
    if not config:
        raise RuntimeError("未配置 AI 模型")
    messages = [{"role": "user", "content": prompt}]
    url, headers, payload = _build_request(config, messages)
    payload["max_tokens"] = min(config.max_tokens, max_tokens)
    payload["temperature"] = temperature
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    content = (data["choices"][0]["message"]["content"] or "").strip()
    tokens = int(data.get("usage", {}).get("total_tokens", 0) or 0)
    return content, f"{config.provider}/{config.model}", tokens


def _format_session_for_prompt(s: BasketballSession) -> str:
    """把一场复盘格式化为 prompt 可读的文本（保留关键反思字段）"""
    parts = [
        f"日期: {s.date} | 类型: {'比赛' if s.type == 'match' else '散场'}",
        f"一句话: {s.one_line_summary or ''}",
    ]
    if s.highlights:
        parts.append(f"亮点: {s.highlights}")
    if s.problems:
        parts.append(f"问题: {s.problems}")
    if s.key_moments:
        parts.append(f"关键回合: {s.key_moments}")
    if s.emotion:
        parts.append(f"情绪: {s.emotion}")
    if s.type == "match":
        if s.opponent:
            parts.append(f"对手: {s.opponent}")
        if s.matchup:
            parts.append(f"对位: {s.matchup}")
        if s.decisive_moment:
            parts.append(f"决胜时刻: {s.decisive_moment}")
        if s.team_observation:
            parts.append(f"团队观察: {s.team_observation}")
    if s.shots_attempted:
        rate = (s.shots_made or 0) / s.shots_attempted * 100 if s.shots_attempted else 0
        parts.append(f"命中率: {s.shots_made}/{s.shots_attempted} ({rate:.0f}%)")
    return "\n".join(parts)


async def _get_history_30d_text(db: AsyncSession, exclude_id: Optional[int] = None) -> str:
    """拉取近 30 天复盘摘要"""
    cutoff = DateType.today() - timedelta(days=30)
    stmt = (
        select(BasketballSession)
        .where(BasketballSession.date >= cutoff)
        .order_by(desc(BasketballSession.date))
        .limit(20)
    )
    if exclude_id:
        stmt = stmt.where(BasketballSession.id != exclude_id)
    res = await db.execute(stmt)
    sessions = list(res.scalars())
    if not sessions:
        return "（这是最近 30 天的第一场记录）"
    lines = []
    for s in sessions:
        date_str = s.date.isoformat()
        type_str = "比赛" if s.type == "match" else "散场"
        snippet = (s.problems or "")[:80] or (s.one_line_summary or "")[:80]
        lines.append(f"- {date_str} [{type_str}] {snippet}")
    return "\n".join(lines)


# ==================== 任务 1：教练点评 + 盲区（同步）====================

async def coach_review_and_blind_spots(
    db: AsyncSession, session: BasketballSession,
) -> tuple[Optional[str], list[dict], Optional[str]]:
    """同步生成教练点评 + 盲区。失败降级。
    返回 (coach_review, blind_spots_list, model_name)
    """
    profile_text = await get_user_profile_text(db)
    history_text = await _get_history_30d_text(db, exclude_id=session.id)
    session_text = _format_session_for_prompt(session)

    prompt = (
        COACH_SYSTEM_PROMPT
        .replace("{user_profile}", profile_text)
        .replace("{history_30d}", history_text)
    ) + "\n\n## 本场复盘\n" + session_text + "\n\n现在请按 JSON 格式输出点评和盲区。"

    try:
        parsed, model, _tokens = await _ai_call_json(db, prompt, max_tokens=2000, temperature=0.4)
        review = (parsed.get("coach_review") or "").strip()
        blind_spots_raw = parsed.get("blind_spots") or []
        if not isinstance(blind_spots_raw, list):
            blind_spots_raw = []
        blind_spots = []
        for bs in blind_spots_raw[:3]:
            if not isinstance(bs, dict):
                continue
            title = (bs.get("title") or "").strip()
            if not title:
                continue
            blind_spots.append({
                "title": title[:200],
                "evidence": (bs.get("evidence") or "")[:300],
                "repeat_count": int(bs.get("repeat_count") or 1),
            })
        if not review:
            return random.choice(FALLBACK_COACH_REVIEWS), [], "fallback"
        return review, blind_spots, model
    except Exception as e:
        logger.warning(f"教练点评失败，降级: {e}")
        return random.choice(FALLBACK_COACH_REVIEWS), [], "fallback"


# ==================== 任务 2：抽取技术维度（异步）====================

async def _extract_skill_dimensions(db: AsyncSession, session: BasketballSession) -> list[BasketballSkillSnapshot]:
    session_text = _format_session_for_prompt(session)
    prompt = (
        SKILL_EXTRACT_PROMPT
        .replace("{dimensions}", " / ".join(SKILL_DIMENSIONS))
        .replace("{content}", session_text)
    )
    snapshots: list[BasketballSkillSnapshot] = []
    parsed, _model, _tokens = await _ai_call_json(db, prompt, max_tokens=1000, temperature=0.2)
    items = parsed.get("items") or []
    if not isinstance(items, list):
        items = []
    for raw in items[:8]:
        if not isinstance(raw, dict):
            continue
        dim = (raw.get("skill_dimension") or "").strip()
        if dim not in SKILL_DIMENSIONS:
            continue
        mtype = (raw.get("mention_type") or "").strip()
        if mtype not in ("highlight", "problem"):
            continue
        snap = BasketballSkillSnapshot(
            session_id=session.id,
            occurred_at=session.date,
            skill_dimension=dim,
            mention_type=mtype,
            extracted_text=(raw.get("extracted_text") or "")[:300] or None,
        )
        db.add(snap)
        snapshots.append(snap)
    await db.flush()
    return snapshots


async def extract_skill_dimensions_task(session_id: int) -> None:
    """BackgroundTask 入口"""
    try:
        async with async_session_maker() as db:
            res = await db.execute(select(BasketballSession).where(BasketballSession.id == session_id))
            session = res.scalar_one_or_none()
            if not session:
                return
            snapshots = await _extract_skill_dimensions(db, session)
            await _mark_async_status(db, session_id, "tech", "ok" if snapshots else "empty")
            await db.commit()
            logger.info(f"篮球技术维度抽取完成: session={session_id}, {len(snapshots)} 条")
    except Exception as e:
        logger.warning(f"extract_skill_dimensions_task 失败: {e}")
        try:
            async with async_session_maker() as db:
                await _mark_async_status(db, session_id, "tech", "failed")
                await db.commit()
        except Exception:
            pass


# ==================== 任务 3：抽取高光 → 心力候选（异步）====================

async def _extract_highlights_to_wellbeing(db: AsyncSession, session: BasketballSession) -> int:
    profile_text = await get_user_profile_text(db)
    session_text = _format_session_for_prompt(session)
    prompt = (
        HIGHLIGHTS_PROMPT
        .replace("{user_profile}", profile_text)
        .replace("{content}", session_text)
    )
    parsed, model, _tokens = await _ai_call_json(db, prompt, max_tokens=1000, temperature=0.4)
    items = parsed.get("items") or []
    if not isinstance(items, list):
        return 0
    created = 0
    for raw in items[:3]:
        if not isinstance(raw, dict):
            continue
        stype = (raw.get("type") or "").strip()
        if stype not in ("achievement", "gratitude"):
            continue
        content_text = (raw.get("content") or "").strip()
        if not content_text:
            continue
        cand = WellbeingCandidate(
            source_type="basketball",
            source_id=session.id,
            source_excerpt=(raw.get("excerpt") or "")[:500] or None,
            suggested_type=stype,
            suggested_content=content_text[:500],
            suggested_category=(raw.get("category") or "健康"),
            suggested_intensity=int(raw.get("intensity") or 3),
            ai_confidence=float(raw.get("ai_confidence") or 0.6),
            ai_reason=(raw.get("ai_reason") or None),
            status="pending",
            extract_status="success",
            model_used=model,
        )
        db.add(cand)
        created += 1
    await db.flush()
    return created


async def extract_highlights_task(session_id: int) -> None:
    """BackgroundTask 入口"""
    try:
        async with async_session_maker() as db:
            res = await db.execute(select(BasketballSession).where(BasketballSession.id == session_id))
            session = res.scalar_one_or_none()
            if not session:
                return
            n = await _extract_highlights_to_wellbeing(db, session)
            await _mark_async_status(db, session_id, "highlights", "ok")
            await db.commit()
            logger.info(f"篮球高光提取完成: session={session_id}, {n} 条候选")
    except Exception as e:
        logger.warning(f"extract_highlights_task 失败: {e}")
        try:
            async with async_session_maker() as db:
                await _mark_async_status(db, session_id, "highlights", "failed")
                await db.commit()
        except Exception:
            pass


# ==================== 任务 4：生成日记摘要并回流（异步）====================

async def _generate_diary_summary_text(db: AsyncSession, session: BasketballSession) -> str:
    type_label = "比赛" if session.type == "match" else "散场"
    prompt = (
        DIARY_SUMMARY_PROMPT
        .replace("{type_label}", type_label)
        .replace("{date}", session.date.isoformat())
        .replace("{one_line}", session.one_line_summary or "")
        .replace("{highlights}", (session.highlights or "")[:200])
        .replace("{problems}", (session.problems or "")[:200])
        .replace("{emotion}", (session.emotion or "")[:200])
    )
    text, _model, _tokens = await _ai_call_text(db, prompt, max_tokens=400, temperature=0.5)
    return (text or "").strip().strip('"').strip("「").strip("」")


async def generate_diary_summary_task(session_id: int) -> None:
    """BackgroundTask 入口：生成摘要 + 回流到当天日记"""
    try:
        async with async_session_maker() as db:
            res = await db.execute(select(BasketballSession).where(BasketballSession.id == session_id))
            session = res.scalar_one_or_none()
            if not session:
                return

            summary = await _generate_diary_summary_text(db, session)
            if not summary:
                summary = f"今天打了一场{'比赛' if session.type == 'match' else '散场'}：{session.one_line_summary}"

            session.ai_summary = summary[:500]

            # 找当天日记，没有就创建占位
            d_res = await db.execute(select(DiaryEntry).where(DiaryEntry.date == session.date))
            diary = d_res.scalar_one_or_none()
            type_label = "比赛" if session.type == "match" else "散场"
            block = f"\n\n---\n## 🏀 今天打篮球（{type_label}）\n{summary}\n"

            if diary:
                # 追加（避免重复追加：检测已包含特征）
                marker = f"## 🏀 今天打篮球"
                if marker not in (diary.content or ""):
                    diary.content = (diary.content or "") + block
                    # 在 tags 加 basketball
                    tags = list(diary.tags or [])
                    if "basketball" not in tags:
                        tags.append("basketball")
                    diary.tags = tags
            else:
                new_diary = DiaryEntry(
                    date=session.date,
                    title=f"{session.date.isoformat()} 篮球反思",
                    content=f"# {session.date.isoformat()}\n{block}",
                    tags=["basketball"],
                    source="basketball",
                )
                db.add(new_diary)

            await _mark_async_status(db, session_id, "summary", "ok")
            await db.commit()
            logger.info(f"篮球摘要回流日记完成: session={session_id}")
    except Exception as e:
        logger.warning(f"generate_diary_summary_task 失败: {e}")
        try:
            async with async_session_maker() as db:
                await _mark_async_status(db, session_id, "summary", "failed")
                await db.commit()
        except Exception:
            pass


# ==================== 任务 5：生成阶段目标 + 派单待办 ====================

async def generate_stage_goal(
    db: AsyncSession,
    *,
    weeks: int = 2,
    create_todos: bool = True,
) -> tuple[BasketballGoal, int, str]:
    """生成阶段目标。同步。返回 (goal, todos_created, summary)"""
    profile_text = await get_user_profile_text(db)
    history_text = await _get_history_30d_text(db)

    # 上一目标
    last_res = await db.execute(
        select(BasketballGoal).order_by(desc(BasketballGoal.start_date)).limit(1)
    )
    last_goal = last_res.scalar_one_or_none()
    last_goal_text = "（无）"
    if last_goal:
        last_goal_text = (
            f"标题: {last_goal.title}\n"
            f"焦点: {last_goal.focus_area}\n"
            f"周期: {last_goal.start_date} 到 {last_goal.end_date}\n"
            f"状态: {last_goal.status}\n"
            f"评价: {last_goal.ai_evaluation or '（未评价）'}"
        )

    today = DateType.today()
    end_date = today + timedelta(days=7 * weeks)
    prompt = (
        STAGE_GOAL_PROMPT
        .replace("{weeks}", str(weeks))
        .replace("{user_profile}", profile_text)
        .replace("{history_30d}", history_text)
        .replace("{last_goal}", last_goal_text)
        .replace("{focus_areas}", " / ".join(FOCUS_AREAS))
        .replace("{start_date}", today.isoformat())
        .replace("{end_date}", end_date.isoformat())
    )

    parsed, model, _tokens = await _ai_call_json(db, prompt, max_tokens=1500, temperature=0.5)
    title = (parsed.get("title") or "").strip()
    if not title:
        title = "下一阶段训练目标"
    description = (parsed.get("description") or "").strip()
    focus_area = (parsed.get("focus_area") or "其他").strip()
    if focus_area not in FOCUS_AREAS:
        focus_area = "其他"
    summary = (parsed.get("summary") or "").strip()

    goal = BasketballGoal(
        title=title[:200],
        description=description or None,
        focus_area=focus_area,
        start_date=today,
        end_date=end_date,
        status="active",
        ai_model=model,
    )
    db.add(goal)
    await db.flush()

    todos_created = 0
    related_todo_ids: list[int] = []
    if create_todos:
        todos_raw = parsed.get("todos") or []
        if isinstance(todos_raw, list):
            for t in todos_raw[:6]:
                if not isinstance(t, dict):
                    continue
                t_title = (t.get("title") or "").strip()
                if not t_title:
                    continue
                # 解析 scheduled_date
                sched = t.get("scheduled_date")
                sched_date = None
                if sched and isinstance(sched, str):
                    try:
                        sched_date = DateType.fromisoformat(sched[:10])
                    except Exception:
                        sched_date = None
                est = t.get("estimated_minutes")
                try:
                    est = int(est) if est else None
                except Exception:
                    est = None
                todo = TodoItem(
                    title=f"🏀 {t_title}"[:500],
                    description=(t.get("description") or "")[:1000] or None,
                    quadrant=2,
                    status="planned" if sched_date else "evaluated",
                    urgency=3,
                    importance=4,
                    category="health",
                    tags=["basketball", "training", focus_area],
                    source="basketball",
                    source_id=goal.id,
                    scheduled_date=sched_date,
                    estimated_minutes=est,
                    ai_evaluation=f"由篮球阶段目标「{title}」自动派单",
                    ai_category="actionable",
                )
                db.add(todo)
                await db.flush()
                related_todo_ids.append(todo.id)
                todos_created += 1

    goal.related_todo_ids = related_todo_ids or None
    await db.flush()
    return goal, todos_created, summary or description or "下一阶段训练目标已制定"


# ==================== 任务 6：阶段目标评价 ====================

async def evaluate_stage_goal(db: AsyncSession, goal: BasketballGoal) -> str:
    """对一个 goal 给出阶段评价文字"""
    # 拉阶段内的 sessions
    sess_res = await db.execute(
        select(BasketballSession).where(
            and_(
                BasketballSession.date >= goal.start_date,
                BasketballSession.date <= goal.end_date,
            )
        ).order_by(BasketballSession.date)
    )
    sessions = list(sess_res.scalars())
    if not sessions:
        return "这个阶段一场球都没打。目标失败 — 但失败本身也是数据。下一阶段先把『出现在球场』作为唯一目标。"

    sessions_summary = "\n".join(_format_session_for_prompt(s)[:300] for s in sessions[:10])
    prompt = (
        EVALUATE_GOAL_PROMPT
        .replace("{goal_title}", goal.title)
        .replace("{focus_area}", goal.focus_area)
        .replace("{start_date}", goal.start_date.isoformat())
        .replace("{end_date}", goal.end_date.isoformat())
        .replace("{sessions_summary}", sessions_summary)
    )
    try:
        text, _model, _tokens = await _ai_call_text(db, prompt, max_tokens=600, temperature=0.4)
        return text or "评价生成失败，请稍后重试。"
    except Exception as e:
        logger.warning(f"evaluate_stage_goal 失败: {e}")
        return "AI 评价暂时不可用。简单看：这个阶段你打了 {} 场球，自己回看每场的『问题』字段，看看焦点维度有没有出现进步。".format(len(sessions))


# ==================== 工具：标记异步任务状态 ====================

async def _mark_async_status(db: AsyncSession, session_id: int, key: str, value: str) -> None:
    res = await db.execute(select(BasketballSession).where(BasketballSession.id == session_id))
    s = res.scalar_one_or_none()
    if not s:
        return
    status = dict(s.async_status or {})
    status[key] = value
    s.async_status = status
