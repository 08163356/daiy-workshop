"""篮球反思模块 API"""
from __future__ import annotations

from datetime import date as DateType, timedelta
from typing import Optional
from collections import Counter, defaultdict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.basketball import (
    BasketballSession,
    BasketballGoal,
    BasketballSkillSnapshot,
)
from app.schemas.basketball import (
    SessionCreate, SessionUpdate, SessionResponse, SessionListItem,
    SkillHistoryResponse,
    GoalCreate, GoalResponse,
    StageGoalGenerateRequest, StageGoalGenerateResponse, GoalEvaluateResponse,
    DashboardOverview,
    RecentBasketballResponse,
)
from app.services import basketball_ai

router = APIRouter(prefix="/basketball", tags=["篮球反思"])


# ==================== 复盘 CRUD ====================

@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    data: SessionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """保存复盘 → 同步等教练点评 → 派 3 个异步任务"""
    payload = data.model_dump()
    session = BasketballSession(**payload, async_status={"tech": "pending", "highlights": "pending", "summary": "pending"})
    db.add(session)
    await db.flush()
    await db.refresh(session)

    # 习惯自动打卡（篮球复盘事件 + 标题关键词，失败不影响保存）
    try:
        from app.services.todo_service import auto_checkin_habits
        await auto_checkin_habits(db, text=session.title or "", event="basketball")
    except Exception:
        pass

    # 同步：教练点评 + 盲区
    review, blind_spots, model = await basketball_ai.coach_review_and_blind_spots(db, session)
    session.coach_review = review
    session.blind_spots = blind_spots
    session.coach_model = model
    await db.flush()
    await db.refresh(session)

    # 异步：3 个并行
    background_tasks.add_task(basketball_ai.extract_skill_dimensions_task, session.id)
    background_tasks.add_task(basketball_ai.extract_highlights_task, session.id)
    background_tasks.add_task(basketball_ai.generate_diary_summary_task, session.id)

    return SessionResponse.model_validate(session)


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    type: Optional[str] = Query(None, description="pickup / match"),
    skill: Optional[str] = Query(None, description="筛选包含某技术维度的复盘"),
    keyword: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BasketballSession)
    if type:
        stmt = stmt.where(BasketballSession.type == type)
    if keyword:
        kw = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                BasketballSession.one_line_summary.ilike(kw),
                BasketballSession.highlights.ilike(kw),
                BasketballSession.problems.ilike(kw),
                BasketballSession.opponent.ilike(kw),
            )
        )
    if skill:
        sub = (
            select(BasketballSkillSnapshot.session_id)
            .where(BasketballSkillSnapshot.skill_dimension == skill)
            .distinct()
        )
        stmt = stmt.where(BasketballSession.id.in_(sub))

    stmt = stmt.order_by(desc(BasketballSession.date), desc(BasketballSession.id)).offset(offset).limit(limit)
    res = await db.execute(stmt)
    return [SessionListItem.model_validate(s) for s in res.scalars()]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(BasketballSession).where(BasketballSession.id == session_id))
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "复盘不存在")
    return SessionResponse.model_validate(s)


@router.put("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(session_id: int, data: SessionUpdate, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(BasketballSession).where(BasketballSession.id == session_id))
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "复盘不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.flush()
    await db.refresh(s)
    return SessionResponse.model_validate(s)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(BasketballSession).where(BasketballSession.id == session_id))
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "复盘不存在")
    # 一并清理 skill snapshots
    await db.execute(
        BasketballSkillSnapshot.__table__.delete().where(BasketballSkillSnapshot.session_id == session_id)
    )
    await db.delete(s)
    return {"ok": True}


@router.post("/sessions/{session_id}/regenerate-coach", response_model=SessionResponse)
async def regenerate_coach_review(session_id: int, db: AsyncSession = Depends(get_db)):
    """让教练重新看一遍"""
    res = await db.execute(select(BasketballSession).where(BasketballSession.id == session_id))
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "复盘不存在")
    review, blind_spots, model = await basketball_ai.coach_review_and_blind_spots(db, s)
    s.coach_review = review
    s.blind_spots = blind_spots
    s.coach_model = model
    await db.flush()
    await db.refresh(s)
    return SessionResponse.model_validate(s)


# ==================== Dashboard ====================

@router.get("/dashboard", response_model=DashboardOverview)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    today = DateType.today()
    month_start = today.replace(day=1)

    # 本月场次/总时长/命中率
    res = await db.execute(
        select(BasketballSession).where(BasketballSession.date >= month_start)
    )
    month_sessions = list(res.scalars())
    month_count = len(month_sessions)
    month_minutes = sum((s.duration_min or 0) for s in month_sessions)

    total_made = sum((s.shots_made or 0) for s in month_sessions if s.shots_attempted)
    total_att = sum((s.shots_attempted or 0) for s in month_sessions if s.shots_attempted)
    avg_rate = (total_made / total_att) if total_att else None

    # 连续天数（从今天往前数有打球的连续天数）
    res2 = await db.execute(
        select(BasketballSession.date).order_by(desc(BasketballSession.date)).limit(60)
    )
    dates_set = set(d for (d,) in res2.all())
    streak = 0
    cur = today
    # 允许中间隔一天（不严格连续打）：直接看最近多少天里连续有训练日
    while cur in dates_set:
        streak += 1
        cur -= timedelta(days=1)

    # active goal
    g_res = await db.execute(
        select(BasketballGoal).where(BasketballGoal.status == "active").order_by(desc(BasketballGoal.start_date)).limit(1)
    )
    active_goal = g_res.scalar_one_or_none()
    active_goal_progress = None
    if active_goal:
        # 计算关联待办完成度
        from app.models.todo import TodoItem
        todo_ids = active_goal.related_todo_ids or []
        todos_total = len(todo_ids)
        todos_done = 0
        if todo_ids:
            t_res = await db.execute(
                select(TodoItem).where(TodoItem.id.in_(todo_ids))
            )
            for t in t_res.scalars():
                if t.status == "completed":
                    todos_done += 1
        days_total = (active_goal.end_date - active_goal.start_date).days or 1
        days_passed = max(0, (today - active_goal.start_date).days)
        active_goal_progress = {
            "todos_total": todos_total,
            "todos_done": todos_done,
            "days_passed": min(days_passed, days_total),
            "days_total": days_total,
        }

    # 近 3 场
    rec_res = await db.execute(
        select(BasketballSession).order_by(desc(BasketballSession.date), desc(BasketballSession.id)).limit(3)
    )
    recent = [SessionListItem.model_validate(s) for s in rec_res.scalars()]

    return DashboardOverview(
        month_session_count=month_count,
        month_total_minutes=month_minutes,
        avg_shooting_rate=avg_rate,
        streak_days=streak,
        active_goal=GoalResponse.model_validate(active_goal) if active_goal else None,
        active_goal_progress=active_goal_progress,
        recent_sessions=recent,
    )


# ==================== Skill History ====================

@router.get("/skill-history", response_model=SkillHistoryResponse)
async def get_skill_history(
    days: int = Query(90, ge=14, le=365),
    db: AsyncSession = Depends(get_db),
):
    """技术进化史 — 按周聚合每个维度的 problem/highlight 计数"""
    cutoff = DateType.today() - timedelta(days=days)
    res = await db.execute(
        select(BasketballSkillSnapshot)
        .where(BasketballSkillSnapshot.occurred_at >= cutoff)
        .order_by(BasketballSkillSnapshot.occurred_at)
    )
    snapshots = list(res.scalars())

    # 按周分组
    def week_key(d: DateType) -> str:
        iso_year, iso_week, _ = d.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    week_groups: dict[str, dict] = {}
    for s in snapshots:
        wk = week_key(s.occurred_at)
        if wk not in week_groups:
            # 算这一周的起止日期（从周一到周日）
            iso_year, iso_week, _ = s.occurred_at.isocalendar()
            monday = DateType.fromisocalendar(iso_year, iso_week, 1)
            sunday = monday + timedelta(days=6)
            week_groups[wk] = {
                "week_key": wk,
                "date_start": monday.isoformat(),
                "date_end": sunday.isoformat(),
                "points": defaultdict(lambda: {"problem": 0, "highlight": 0}),
            }
        week_groups[wk]["points"][s.skill_dimension][s.mention_type] += 1

    timeline = []
    for wk in sorted(week_groups.keys()):
        wg = week_groups[wk]
        points = []
        for dim, counts in wg["points"].items():
            points.append({
                "dim": dim,
                "problem": counts["problem"],
                "highlight": counts["highlight"],
            })
        timeline.append({
            "week_key": wk,
            "date_start": wg["date_start"],
            "date_end": wg["date_end"],
            "points": points,
        })

    # 进步/倒退 Top
    # 算法：把整个时间窗一分为二（前半 vs 后半），每维度看 problem 比例变化
    def score_change(snaps: list[BasketballSkillSnapshot]) -> dict[str, dict]:
        per_dim = defaultdict(lambda: {"problem": 0, "highlight": 0})
        for s in snaps:
            per_dim[s.skill_dimension][s.mention_type] += 1
        return per_dim

    mid = cutoff + timedelta(days=days // 2)
    first_half = [s for s in snapshots if s.occurred_at < mid]
    second_half = [s for s in snapshots if s.occurred_at >= mid]
    first_score = score_change(first_half)
    second_score = score_change(second_half)

    progress_changes = []
    for dim in basketball_ai.SKILL_DIMENSIONS:
        f = first_score.get(dim, {"problem": 0, "highlight": 0})
        s = second_score.get(dim, {"problem": 0, "highlight": 0})
        # 进步 = (后半 highlight - 前半 highlight) - (后半 problem - 前半 problem)
        delta = (s["highlight"] - f["highlight"]) - (s["problem"] - f["problem"])
        if delta != 0 or (f["problem"] + s["problem"] + f["highlight"] + s["highlight"] > 0):
            progress_changes.append({
                "dim": dim,
                "delta": delta,
                "before": f,
                "after": s,
            })

    progress_changes.sort(key=lambda x: x["delta"], reverse=True)
    top_progress = [p for p in progress_changes if p["delta"] > 0][:3]
    top_regress = [p for p in reversed(progress_changes) if p["delta"] < 0][:3]

    return SkillHistoryResponse(
        dimensions=basketball_ai.SKILL_DIMENSIONS,
        timeline=timeline,
        top_progress=top_progress,
        top_regress=top_regress,
    )


# ==================== Goals ====================

@router.get("/goals/active", response_model=Optional[GoalResponse])
async def get_active_goal(db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(BasketballGoal).where(BasketballGoal.status == "active").order_by(desc(BasketballGoal.start_date)).limit(1)
    )
    g = res.scalar_one_or_none()
    return GoalResponse.model_validate(g) if g else None


@router.get("/goals", response_model=list[GoalResponse])
async def list_goals(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BasketballGoal)
    if status:
        stmt = stmt.where(BasketballGoal.status == status)
    stmt = stmt.order_by(desc(BasketballGoal.start_date)).limit(limit)
    res = await db.execute(stmt)
    return [GoalResponse.model_validate(g) for g in res.scalars()]


@router.post("/goals/generate", response_model=StageGoalGenerateResponse)
async def generate_goal(
    data: StageGoalGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """让 AI 教练生成下一阶段目标 + 派单训练待办"""
    # 自动把上一个 active 设置为 done（若到期）
    today = DateType.today()
    pre_res = await db.execute(
        select(BasketballGoal).where(BasketballGoal.status == "active")
    )
    for prev in pre_res.scalars():
        if prev.end_date < today:
            prev.status = "done"
    await db.flush()

    goal, todos_created, summary = await basketball_ai.generate_stage_goal(
        db, weeks=data.weeks, create_todos=data.create_todos,
    )
    return StageGoalGenerateResponse(
        goal=GoalResponse.model_validate(goal),
        todos_created=todos_created,
        summary=summary,
    )


@router.post("/goals/{goal_id}/evaluate", response_model=GoalEvaluateResponse)
async def evaluate_goal(goal_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(BasketballGoal).where(BasketballGoal.id == goal_id))
    g = res.scalar_one_or_none()
    if not g:
        raise HTTPException(404, "目标不存在")
    summary = await basketball_ai.evaluate_stage_goal(db, g)
    g.ai_evaluation = summary
    if g.status == "active":
        g.status = "done"
    await db.flush()
    await db.refresh(g)
    return GoalEvaluateResponse(goal=GoalResponse.model_validate(g), summary=summary)


@router.delete("/goals/{goal_id}")
async def delete_goal(goal_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(BasketballGoal).where(BasketballGoal.id == goal_id))
    g = res.scalar_one_or_none()
    if not g:
        raise HTTPException(404, "目标不存在")
    await db.delete(g)
    return {"ok": True}


# ==================== /recent (供 diary-analyzer) ====================

@router.get("/recent", response_model=RecentBasketballResponse)
async def get_recent(days: int = Query(7, ge=1, le=30), db: AsyncSession = Depends(get_db)):
    cutoff = DateType.today() - timedelta(days=days)
    res = await db.execute(
        select(BasketballSession).where(BasketballSession.date >= cutoff).order_by(desc(BasketballSession.date))
    )
    sessions = list(res.scalars())
    if not sessions:
        return RecentBasketballResponse(days=days)

    avg_int = sum(s.intensity for s in sessions) / len(sessions)
    total_made = sum((s.shots_made or 0) for s in sessions if s.shots_attempted)
    total_att = sum((s.shots_attempted or 0) for s in sessions if s.shots_attempted)
    avg_rate = (total_made / total_att) if total_att else None

    # 简单情绪关键词抽取
    emotion_words = []
    keywords_pool = ["焦虑", "兴奋", "失落", "畅快", "疲惫", "恼火", "平静", "受挫", "自信", "怀疑"]
    for s in sessions:
        text = (s.emotion or "") + " " + (s.one_line_summary or "")
        for kw in keywords_pool:
            if kw in text and kw not in emotion_words:
                emotion_words.append(kw)

    last = sessions[0]
    return RecentBasketballResponse(
        days=days,
        session_count=len(sessions),
        avg_intensity=round(avg_int, 2),
        avg_shooting_rate=round(avg_rate, 3) if avg_rate is not None else None,
        emotions_keywords=emotion_words[:5],
        last_session_date=last.date,
        last_one_line=last.one_line_summary,
    )
