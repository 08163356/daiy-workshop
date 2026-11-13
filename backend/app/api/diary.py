"""日记模块 API"""

from datetime import date as date_cls
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import and_, desc, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.diary import DiaryEntry
from app.schemas.diary import (
    DiaryCreate, DiaryResponse, DiaryListItem, DiaryOverview,
)
from app.schemas.investment import ListResponse
from app.services import wellbeing_ai

router = APIRouter(prefix="/diary", tags=["日记模块"])


@router.get("/overview", response_model=DiaryOverview)
async def get_overview(db: AsyncSession = Depends(get_db)):
    """获取日记系统总览"""
    total = await db.scalar(select(func.count(DiaryEntry.id)))
    
    # 情绪分布
    mood_dist = {}
    result = await db.execute(
        select(DiaryEntry.mood, func.count(DiaryEntry.id))
        .where(DiaryEntry.mood.isnot(None))
        .group_by(DiaryEntry.mood)
    )
    for row in result:
        mood_dist[row[0]] = row[1]
    
    # 最近日记
    result = await db.execute(
        select(DiaryEntry)
        .order_by(desc(DiaryEntry.date))
        .limit(10)
    )
    recent = [DiaryListItem.model_validate(e) for e in result.scalars()]
    
    # 月度统计
    monthly = {}
    result = await db.execute(
        select(
            func.strftime('%Y-%m', DiaryEntry.date).label('month'),
            func.count(DiaryEntry.id)
        )
        .group_by('month')
        .order_by(desc('month'))
        .limit(12)
    )
    for row in result:
        monthly[row[0]] = row[1]
    
    # 标签分布（从 JSON 字段统计）
    tag_dist = {}
    result = await db.execute(
        select(DiaryEntry.tags).where(DiaryEntry.tags.isnot(None))
    )
    for row in result:
        tags = row[0]
        if isinstance(tags, list):
            for tag in tags:
                tag_dist[tag] = tag_dist.get(tag, 0) + 1
    
    return DiaryOverview(
        total_count=total or 0,
        mood_distribution=mood_dist,
        tag_distribution=tag_dist,
        recent_entries=recent,
        monthly_count=monthly,
    )


@router.get("/years")
async def list_years(db: AsyncSession = Depends(get_db)):
    """有日记的年份，新的在前"""
    result = await db.execute(
        select(extract("year", DiaryEntry.date))
        .distinct()
        .order_by(desc(extract("year", DiaryEntry.date)))
    )
    years = []
    for row in result:
        if row[0] is not None:
            years.append(int(row[0]))
    return {"years": years}


@router.get("/dates")
async def list_dates(db: AsyncSession = Depends(get_db)):
    """有日记的日期，新的在前。同一天多篇只出现一次。"""
    result = await db.execute(
        select(DiaryEntry.date).distinct().order_by(desc(DiaryEntry.date))
    )
    dates = []
    for row in result:
        value = row[0]
        if value is None:
            continue
        dates.append(value.isoformat() if hasattr(value, "isoformat") else str(value)[:10])
    return {"dates": dates}


@router.get("/by-date")
async def entries_by_date(
    day: date_cls = Query(..., alias="date"),
    db: AsyncSession = Depends(get_db),
):
    """某一天的日记，新的在前。同一天可能有多篇。"""
    result = await db.execute(
        select(DiaryEntry)
        .where(DiaryEntry.date == day)
        .order_by(desc(DiaryEntry.id))
    )
    items = [_diary_brief(entry) | {"mood": entry.mood} for entry in result.scalars()]
    return {"items": items}


def _diary_brief(entry: DiaryEntry | None) -> dict | None:
    if entry is None:
        return None
    raw = entry.date
    return {
        "id": entry.id,
        "title": entry.title,
        "date": raw.isoformat() if hasattr(raw, "isoformat") else str(raw)[:10],
    }


@router.get("", response_model=ListResponse)
async def list_entries(
    mood: Optional[str] = None,
    keyword: Optional[str] = None,
    start_date: Optional[date_cls] = None,
    end_date: Optional[date_cls] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取日记列表，可按情绪、关键词和日期范围筛选"""
    query = select(DiaryEntry)
    count_query = select(func.count(DiaryEntry.id))

    if mood:
        query = query.where(DiaryEntry.mood == mood)
        count_query = count_query.where(DiaryEntry.mood == mood)
    if keyword:
        query = query.where(DiaryEntry.content.contains(keyword))
        count_query = count_query.where(DiaryEntry.content.contains(keyword))
    if start_date:
        query = query.where(DiaryEntry.date >= start_date)
        count_query = count_query.where(DiaryEntry.date >= start_date)
    if end_date:
        query = query.where(DiaryEntry.date <= end_date)
        count_query = count_query.where(DiaryEntry.date <= end_date)

    total = await db.scalar(count_query)
    result = await db.execute(
        query.order_by(desc(DiaryEntry.date), desc(DiaryEntry.id)).offset(skip).limit(limit)
    )
    items = [DiaryListItem.model_validate(e) for e in result.scalars()]
    return ListResponse(total=total or 0, items=items)


@router.get("/{entry_id}/neighbors")
async def entry_neighbors(entry_id: int, db: AsyncSession = Depends(get_db)):
    """按列表顺序（新的在前）给出相邻日记。prev 是更新的一篇，next 是更早的一篇。"""
    current = await db.get(DiaryEntry, entry_id)
    if current is None:
        raise HTTPException(status_code=404, detail="日记不存在")
    newer = (await db.execute(
        select(DiaryEntry)
        .where(or_(
            DiaryEntry.date > current.date,
            and_(DiaryEntry.date == current.date, DiaryEntry.id > current.id),
        ))
        .order_by(DiaryEntry.date.asc(), DiaryEntry.id.asc())
        .limit(1)
    )).scalar_one_or_none()
    older = (await db.execute(
        select(DiaryEntry)
        .where(or_(
            DiaryEntry.date < current.date,
            and_(DiaryEntry.date == current.date, DiaryEntry.id < current.id),
        ))
        .order_by(desc(DiaryEntry.date), desc(DiaryEntry.id))
        .limit(1)
    )).scalar_one_or_none()
    return {"prev": _diary_brief(newer), "next": _diary_brief(older)}


@router.get("/{entry_id}", response_model=DiaryResponse)
async def get_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    """获取日记详情"""
    result = await db.execute(
        select(DiaryEntry).where(DiaryEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="日记不存在")
    return DiaryResponse.model_validate(entry)


@router.post("", response_model=DiaryResponse)
async def create_entry(
    data: DiaryCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """创建日记"""
    entry = DiaryEntry(**data.model_dump())
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    # 习惯自动打卡（写日记事件 + 标题正文关键词，失败不影响保存）
    try:
        from app.services.todo_service import auto_checkin_habits
        await auto_checkin_habits(db, text=f"{entry.title or ''} {entry.content or ''}", event="diary")
    except Exception:
        pass
    # 异步触发心力候选提取（失败不影响日记保存）
    try:
        background_tasks.add_task(
            wellbeing_ai.extract_candidates_from_diary,
            entry.id,
            entry.content,
        )
    except Exception:
        pass
    # 异步生成 AI 澄清问题（有值得澄清的点才入队，失败不影响保存）
    try:
        import asyncio
        from app.services.question_service import generate_questions_task
        asyncio.create_task(generate_questions_task("diary", entry.id, entry.content))
    except Exception:
        pass
    return DiaryResponse.model_validate(entry)


async def _derived_counts(db: AsyncSession, entry_id: int) -> dict:
    """统计日记的衍生数据（心力条目/候选/AI 提问，均按 source 追溯）"""
    from sqlalchemy import delete as sql_delete, func as sql_func
    from app.models.wellbeing import WellbeingEntry, WellbeingCandidate
    from app.models.ai_question import AIQuestion

    counts = {}
    for model, key in (
        (WellbeingEntry, "wellbeing_entries"),
        (WellbeingCandidate, "wellbeing_candidates"),
        (AIQuestion, "ai_questions"),
    ):
        result = await db.execute(
            select(sql_func.count()).select_from(model).where(
                model.source_type == "diary", model.source_id == entry_id
            )
        )
        counts[key] = result.scalar() or 0
    return counts


@router.get("/{entry_id}/derived-counts")
async def get_derived_counts(entry_id: int, db: AsyncSession = Depends(get_db)):
    """删除前预览：这篇日记衍生了多少心力记录/候选/AI 提问"""
    return await _derived_counts(db, entry_id)


@router.delete("/{entry_id}")
async def delete_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    """删除日记，级联删除可追踪的衍生数据（心力条目/候选/AI 提问）。

    注意：画像更新是合并式写入（不带日记来源），无法精确撤销，
    靠 30 天置信度衰减和 14 天蒸馏自愈，不做删除。
    """
    result = await db.execute(
        select(DiaryEntry).where(DiaryEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="日记不存在")

    # 先统计再级联删除（响应里带回删除明细，前端可提示）
    counts = await _derived_counts(db, entry_id)

    from sqlalchemy import delete as sql_delete
    from app.models.wellbeing import WellbeingEntry, WellbeingCandidate
    from app.models.ai_question import AIQuestion

    for model in (WellbeingEntry, WellbeingCandidate, AIQuestion):
        await db.execute(
            sql_delete(model).where(model.source_type == "diary", model.source_id == entry_id)
        )
    await db.delete(entry)
    await db.flush()
    return {"message": "删除成功", "deleted_derived": counts}
