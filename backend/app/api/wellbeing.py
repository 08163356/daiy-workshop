"""心力模块（成就 + 感恩）API"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.wellbeing import (
    WellbeingEntry,
    WellbeingCandidate,
    WellbeingReport,
)
from app.schemas.wellbeing import (
    WellbeingEntryCreate,
    WellbeingEntryUpdate,
    WellbeingEntryResponse,
    WellbeingListResponse,
    WellbeingCandidateResponse,
    CandidateReviewAction,
    WellbeingReportResponse,
    ComfortCardResponse,
    ComfortCardEntry,
    WellbeingOverviewResponse,
    TrendPoint,
    CategoryStat,
    WellbeingInsightsResponse,
    CorrelationItem,
)
from app.services import wellbeing_ai

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wellbeing", tags=["心力模块"])


# ==================== 工具函数 ====================

def _iso_week_key(d: date) -> tuple[str, date, date]:
    """返回 (period_key, period_start, period_end)；周以周一开始"""
    y, w, _ = d.isocalendar()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return f"{y}-W{w:02d}", monday, sunday


def _month_key(d: date) -> tuple[str, date, date]:
    start = d.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
    return f"{start.year}-{start.month:02d}", start, end


# ==================== 总览看板 ====================

@router.get("/overview", response_model=WellbeingOverviewResponse)
async def get_overview(db: AsyncSession = Depends(get_db)):
    """心力模块总览：累计/趋势/分类/雷达/连续天数/候选数"""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    trend_start = today - timedelta(days=89)

    # 累计
    total_ach = await db.scalar(
        select(func.count(WellbeingEntry.id)).where(WellbeingEntry.type == "achievement")
    ) or 0
    total_grat = await db.scalar(
        select(func.count(WellbeingEntry.id)).where(WellbeingEntry.type == "gratitude")
    ) or 0

    # 本周新增
    week_new = await db.scalar(
        select(func.count(WellbeingEntry.id)).where(WellbeingEntry.occurred_at >= week_start)
    ) or 0

    # 待审候选数
    pending = await db.scalar(
        select(func.count(WellbeingCandidate.id)).where(WellbeingCandidate.status == "pending")
    ) or 0

    # 90 天趋势
    result = await db.execute(
        select(
            WellbeingEntry.occurred_at,
            WellbeingEntry.type,
            func.count(WellbeingEntry.id),
        )
        .where(WellbeingEntry.occurred_at >= trend_start)
        .group_by(WellbeingEntry.occurred_at, WellbeingEntry.type)
        .order_by(WellbeingEntry.occurred_at)
    )
    trend_map: dict[date, dict[str, int]] = {}
    for d, t, n in result:
        trend_map.setdefault(d, {"achievement": 0, "gratitude": 0})[t] = n
    trend_90d = [
        TrendPoint(date=d, achievement=v.get("achievement", 0), gratitude=v.get("gratitude", 0))
        for d, v in sorted(trend_map.items())
    ]

    # 分类分布
    cat_result = await db.execute(
        select(
            WellbeingEntry.category,
            func.count(WellbeingEntry.id),
            func.avg(WellbeingEntry.intensity),
        )
        .where(WellbeingEntry.category.isnot(None))
        .group_by(WellbeingEntry.category)
        .order_by(desc(func.count(WellbeingEntry.id)))
    )
    cat_distribution = [
        CategoryStat(category=c, count=n, avg_intensity=round(float(avg or 0), 2))
        for c, n, avg in cat_result
    ]

    # 强度雷达（按分类平均）
    intensity_radar = {c.category: c.avg_intensity for c in cat_distribution[:8]}

    # 连续天数（包含今天）
    streak = 0
    cursor = today
    distinct_days_result = await db.execute(
        select(WellbeingEntry.occurred_at).distinct().order_by(desc(WellbeingEntry.occurred_at)).limit(60)
    )
    distinct_days = {row[0] for row in distinct_days_result}
    while cursor in distinct_days:
        streak += 1
        cursor -= timedelta(days=1)

    # 关联洞察一句话
    all_recent_result = await db.execute(
        select(WellbeingEntry).where(WellbeingEntry.occurred_at >= trend_start)
    )
    insight = wellbeing_ai.analyze_correlations(list(all_recent_result.scalars())).get("summary")

    return WellbeingOverviewResponse(
        total_achievement=total_ach,
        total_gratitude=total_grat,
        week_new=week_new,
        streak_days=streak,
        trend_90d=trend_90d,
        category_distribution=cat_distribution,
        intensity_radar=intensity_radar,
        pending_candidates=pending,
        insight=insight,
    )


# ==================== 条目 CRUD ====================

@router.get("/dates")
async def list_dates(db: AsyncSession = Depends(get_db)):
    """有心力记录的日期，新的在前。同一天多条只出现一次。"""
    result = await db.execute(
        select(WellbeingEntry.occurred_at).distinct().order_by(desc(WellbeingEntry.occurred_at))
    )
    dates = []
    for row in result:
        value = row[0]
        if value is None:
            continue
        dates.append(value.isoformat() if hasattr(value, "isoformat") else str(value)[:10])
    return {"dates": dates}


@router.get("/entries", response_model=WellbeingListResponse)
async def list_entries(
    type: Optional[str] = Query(None, description="achievement / gratitude"),
    category: Optional[str] = None,
    min_intensity: Optional[int] = Query(None, ge=1, le=5),
    keyword: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(WellbeingEntry)
    count_query = select(func.count(WellbeingEntry.id))

    conditions = []
    if type:
        conditions.append(WellbeingEntry.type == type)
    if category:
        conditions.append(WellbeingEntry.category == category)
    if min_intensity:
        conditions.append(WellbeingEntry.intensity >= min_intensity)
    if keyword:
        conditions.append(WellbeingEntry.content.contains(keyword))
    if start_date:
        conditions.append(WellbeingEntry.occurred_at >= start_date)
    if end_date:
        conditions.append(WellbeingEntry.occurred_at <= end_date)

    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    total = await db.scalar(count_query) or 0
    result = await db.execute(
        query.order_by(desc(WellbeingEntry.occurred_at), desc(WellbeingEntry.id)).offset(skip).limit(limit)
    )
    items = [WellbeingEntryResponse.model_validate(e) for e in result.scalars()]
    return WellbeingListResponse(total=total, items=items)


@router.post("/entries", response_model=WellbeingEntryResponse)
async def create_entry(data: WellbeingEntryCreate, db: AsyncSession = Depends(get_db)):
    if data.type not in ("achievement", "gratitude"):
        raise HTTPException(400, "type 必须为 achievement 或 gratitude")
    entry = WellbeingEntry(**data.model_dump())
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return WellbeingEntryResponse.model_validate(entry)


@router.get("/entries/{entry_id}", response_model=WellbeingEntryResponse)
async def get_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await db.get(WellbeingEntry, entry_id)
    if not entry:
        raise HTTPException(404, "条目不存在")
    return WellbeingEntryResponse.model_validate(entry)


@router.put("/entries/{entry_id}", response_model=WellbeingEntryResponse)
async def update_entry(entry_id: int, data: WellbeingEntryUpdate, db: AsyncSession = Depends(get_db)):
    entry = await db.get(WellbeingEntry, entry_id)
    if not entry:
        raise HTTPException(404, "条目不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(entry, k, v)
    await db.flush()
    await db.refresh(entry)
    return WellbeingEntryResponse.model_validate(entry)


@router.delete("/entries/{entry_id}")
async def delete_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await db.get(WellbeingEntry, entry_id)
    if not entry:
        raise HTTPException(404, "条目不存在")
    await db.delete(entry)
    await db.flush()
    return {"message": "删除成功"}


# ==================== 候选审核 ====================

@router.get("/candidates", response_model=list[WellbeingCandidateResponse])
async def list_candidates(
    status: str = Query("pending", description="pending / accepted / rejected / all"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(WellbeingCandidate)
    if status != "all":
        query = query.where(WellbeingCandidate.status == status)
    query = query.order_by(desc(WellbeingCandidate.created_at)).limit(limit)
    result = await db.execute(query)
    return [WellbeingCandidateResponse.model_validate(c) for c in result.scalars()]


@router.post("/candidates/{candidate_id}/review")
async def review_candidate(
    candidate_id: int,
    action: CandidateReviewAction,
    db: AsyncSession = Depends(get_db),
):
    cand = await db.get(WellbeingCandidate, candidate_id)
    if not cand:
        raise HTTPException(404, "候选不存在")
    if cand.status != "pending":
        raise HTTPException(400, f"候选已被处理（{cand.status}）")

    if action.action == "reject":
        cand.status = "rejected"
        cand.reviewed_at = datetime.now()
        await db.flush()
        return {"message": "已忽略"}

    if action.action != "accept":
        raise HTTPException(400, "action 必须为 accept 或 reject")

    # 创建条目 - 保留原始来源信息（日记/笔记）
    entry = WellbeingEntry(
  type=cand.suggested_type,
        content=action.content or cand.suggested_content,
        category=action.category if action.category is not None else cand.suggested_category,
        intensity=action.intensity or cand.suggested_intensity or 3,
        occurred_at=action.occurred_at or date.today(),
        source_type=cand.source_type,  # 保留原始来源：diary/note
        source_id=cand.source_id,      # 保留原始日记/笔记ID
        source_excerpt=cand.source_excerpt,  # 保留原文片段
        ai_tags=cand.suggested_tags,
        ai_reason=cand.ai_reason,      # 保留 AI 识别理由
  )
    db.add(entry)
    await db.flush()

    cand.status = "accepted"
    cand.reviewed_at = datetime.now()
    cand.accepted_entry_id = entry.id
    await db.flush()
    await db.refresh(entry)

    return {
        "message": "已采纳并入库",
        "entry": WellbeingEntryResponse.model_validate(entry).model_dump(mode="json"),
    }


# ==================== 周报 / 月报 ====================

@router.get("/reports", response_model=WellbeingReportResponse)
async def get_report(
    period_type: str = Query("week", description="week / month"),
    period_key: Optional[str] = Query(None, description="如 2026-W17 或 2026-04，缺省为本期"),
    force_refresh: bool = Query(False, description="强制重新生成"),
    db: AsyncSession = Depends(get_db),
):
    if period_type not in ("week", "month"):
        raise HTTPException(400, "period_type 必须为 week 或 month")

    # 解析 period_key
    today = date.today()
    if period_type == "week":
        if period_key:
            try:
                y, w = period_key.split("-W")
                # 从 ISO 周计算周一
                jan4 = date(int(y), 1, 4)
                week1_monday = jan4 - timedelta(days=jan4.weekday())
                period_start = week1_monday + timedelta(weeks=int(w) - 1)
                period_end = period_start + timedelta(days=6)
            except Exception:
                raise HTTPException(400, "period_key 格式错误，应如 2026-W17")
        else:
            period_key, period_start, period_end = _iso_week_key(today)
    else:
        if period_key:
            try:
                y, m = period_key.split("-")
                start = date(int(y), int(m), 1)
                _, period_start, period_end = _month_key(start)
            except Exception:
                raise HTTPException(400, "period_key 格式错误，应如 2026-04")
        else:
            period_key, period_start, period_end = _month_key(today)

    # 查询缓存
    if not force_refresh:
        cached = await db.execute(
            select(WellbeingReport).where(
                WellbeingReport.period_type == period_type,
                WellbeingReport.period_key == period_key,
            )
        )
        existing = cached.scalar_one_or_none()
        if existing:
            return WellbeingReportResponse.model_validate(existing)

    # 拉取本期数据
    entries_result = await db.execute(
        select(WellbeingEntry).where(
            WellbeingEntry.occurred_at >= period_start,
            WellbeingEntry.occurred_at <= period_end,
        ).order_by(WellbeingEntry.occurred_at)
    )
    entries = list(entries_result.scalars())
    achievements = [e for e in entries if e.type == "achievement"]
    gratitudes = [e for e in entries if e.type == "gratitude"]

    # 调 AI 生成
    content, model, tokens = await wellbeing_ai.generate_period_report(
        db,
        period_type=period_type,
        period_start=period_start,
        period_end=period_end,
        achievements=achievements,
        gratitudes=gratitudes,
    )

    # 入库（upsert）
    cached = await db.execute(
        select(WellbeingReport).where(
            WellbeingReport.period_type == period_type,
            WellbeingReport.period_key == period_key,
        )
    )
    report = cached.scalar_one_or_none()
    if report:
        report.content = content
        report.achievement_count = len(achievements)
        report.gratitude_count = len(gratitudes)
        report.model_used = model
        report.tokens_used = tokens
        report.generated_at = datetime.now()
    else:
        report = WellbeingReport(
            period_type=period_type,
            period_key=period_key,
            period_start=period_start,
            period_end=period_end,
            content=content,
            achievement_count=len(achievements),
            gratitude_count=len(gratitudes),
            model_used=model,
            tokens_used=tokens,
        )
        db.add(report)
    await db.flush()
    await db.refresh(report)
    return WellbeingReportResponse.model_validate(report)


@router.get("/reports/history", response_model=list[WellbeingReportResponse])
async def list_reports(
    period_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(WellbeingReport)
    if period_type:
        query = query.where(WellbeingReport.period_type == period_type)
    query = query.order_by(desc(WellbeingReport.period_start)).limit(limit)
    result = await db.execute(query)
    return [WellbeingReportResponse.model_validate(r) for r in result.scalars()]


# ==================== 焦虑模式：安抚卡 ====================

@router.get("/comfort", response_model=ComfortCardResponse)
async def get_comfort_card(
    achievements_n: int = Query(3, ge=1, le=8),
    gratitudes_n: int = Query(2, ge=0, le=8),
    db: AsyncSession = Depends(get_db),
):
    """随机抽样历史成就 + 感恩，并由 AI 生成安抚语"""
    # 优先抽高强度（intensity >= 3）
    ach_result = await db.execute(
        select(WellbeingEntry)
        .where(WellbeingEntry.type == "achievement")
        .order_by(func.random())
        .limit(achievements_n)
    )
    achievements = list(ach_result.scalars())

    grat_result = await db.execute(
        select(WellbeingEntry)
        .where(WellbeingEntry.type == "gratitude")
        .order_by(func.random())
        .limit(gratitudes_n)
    )
    gratitudes = list(grat_result.scalars())

    message, fallback = await wellbeing_ai.generate_comfort_message(
        db, achievements=achievements, gratitudes=gratitudes,
    )

    return ComfortCardResponse(
        soothing_message=message,
        achievements=[
            ComfortCardEntry(
                id=e.id, type=e.type, content=e.content, category=e.category,
                intensity=e.intensity, occurred_at=e.occurred_at,
            ) for e in achievements
        ],
        gratitudes=[
            ComfortCardEntry(
                id=e.id, type=e.type, content=e.content, category=e.category,
                intensity=e.intensity, occurred_at=e.occurred_at,
            ) for e in gratitudes
        ],
        fallback=fallback,
    )


# ==================== 关联分析 ====================

@router.get("/insights", response_model=WellbeingInsightsResponse)
async def get_insights(
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
):
    start = date.today() - timedelta(days=days)
    result = await db.execute(
        select(WellbeingEntry).where(WellbeingEntry.occurred_at >= start)
    )
    entries = list(result.scalars())
    data = wellbeing_ai.analyze_correlations(entries)
    return WellbeingInsightsResponse(
        summary=data["summary"],
        correlations=[CorrelationItem(**c) for c in data.get("correlations", [])],
        suggestions=data.get("suggestions", []),
    )
