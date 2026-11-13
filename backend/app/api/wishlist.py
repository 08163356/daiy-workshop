"""心愿清单 API"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.wishlist import Wish, WishLogEntry, WishProgressCandidate
from app.services import wishlist_ai

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wishlist", tags=["心愿清单"])

CATEGORIES = ["health", "career", "wealth", "relationship", "growth", "material", "custom"]


# ======================== Schemas ========================

class MilestoneItem(BaseModel):
    text: str
    type: str = "self"  # self | ai
    completed: Optional[bool] = None
    ai_evaluation: Optional[str] = None
    ai_score: Optional[float] = None


class WishCreate(BaseModel):
    content: str
    category: str = "growth"
    milestones: Optional[list[MilestoneItem]] = None
    linked_todo_category: Optional[str] = None
    progress_step: int = 10


class WishUpdate(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    linked_todo_category: Optional[str] = None
    progress_step: Optional[int] = None
    progress: Optional[int] = Field(None, ge=0, le=100)


class MilestoneCreate(BaseModel):
    text: str
    type: str = "self"


class LogCreate(BaseModel):
    content: str


class CandidateReviewAction(BaseModel):
    action: str = Field(..., description="accept / reject")


class AchieveRequest(BaseModel):
    note: Optional[str] = None


# ======================== 工具函数 ========================

def _recompute_progress(wish: Wish) -> None:
    """里程碑存在时，进度按完成比例自动计算；否则保持手动/AI建议值"""
    if wish.milestones:
        total = len(wish.milestones)
        done = sum(1 for m in wish.milestones if m.get("completed") is True)
        if total:
            wish.progress = round(done / total * 100)


def _wish_to_summary(wish: Wish) -> dict:
    milestones = wish.milestones or []
    return {
        "id": wish.id,
        "content": wish.content,
        "category": wish.category,
        "status": wish.status,
        "progress": wish.progress,
        "milestones_count": len(milestones),
        "completed_milestones_count": sum(1 for m in milestones if m.get("completed") is True),
        "linked_todo_category": wish.linked_todo_category,
        "achieved_at": wish.achieved_at.isoformat() if wish.achieved_at else None,
        "created_at": wish.created_at.isoformat(),
    }


def _wish_to_detail(wish: Wish) -> dict:
    data = _wish_to_summary(wish)
    data.update({
        "milestones": wish.milestones,
        "progress_step": wish.progress_step,
        "achieved_note": wish.achieved_note,
        "updated_at": wish.updated_at.isoformat(),
    })
    return data


async def _get_wish_or_404(db: AsyncSession, wish_id: int) -> Wish:
    result = await db.execute(select(Wish).where(Wish.id == wish_id))
    wish = result.scalar_one_or_none()
    if not wish:
        raise HTTPException(status_code=404, detail="心愿不存在")
    return wish


# ======================== 心愿 CRUD ========================

@router.get("", summary="心愿列表")
async def list_wishes(
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="active/achieved/archived"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Wish).order_by(desc(Wish.created_at))
    count_query = select(func.count()).select_from(Wish)
    if category:
        query = query.where(Wish.category == category)
        count_query = count_query.where(Wish.category == category)
    if status:
        query = query.where(Wish.status == status)
        count_query = count_query.where(Wish.status == status)

    total = await db.scalar(count_query) or 0
    result = await db.execute(query.offset(skip).limit(limit))
    items = [_wish_to_summary(w) for w in result.scalars()]
    return {"total": total, "items": items}


@router.post("", summary="创建心愿")
async def create_wish(data: WishCreate, db: AsyncSession = Depends(get_db)):
    wish = Wish(
        content=data.content,
        category=data.category,
        milestones=[m.model_dump() for m in data.milestones] if data.milestones else None,
        linked_todo_category=data.linked_todo_category,
        progress_step=data.progress_step,
        status="active",
        progress=0,
    )
    db.add(wish)
    await db.flush()
    await db.refresh(wish)
    return _wish_to_detail(wish)


@router.get("/dashboard", summary="心愿墙 Dashboard 统计")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count()).select_from(Wish)) or 0
    active_count = await db.scalar(
        select(func.count()).select_from(Wish).where(Wish.status == "active")
    ) or 0
    achieved_count = await db.scalar(
        select(func.count()).select_from(Wish).where(Wish.status == "achieved")
    ) or 0
    pending_candidates = await db.scalar(
        select(func.count()).select_from(WishProgressCandidate).where(WishProgressCandidate.status == "pending")
    ) or 0

    cat_result = await db.execute(
        select(Wish.category, func.count(Wish.id))
        .where(Wish.status == "active")
        .group_by(Wish.category)
    )
    by_category = {row[0]: row[1] for row in cat_result}

    return {
        "total": total,
        "active_count": active_count,
        "achieved_count": achieved_count,
        "pending_candidates": pending_candidates,
        "by_category": by_category,
    }


@router.get("/candidates", summary="进度候选列表")
async def list_candidates(
    status: str = Query("pending", description="pending/accepted/rejected/all"),
    wish_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(WishProgressCandidate)
    if status != "all":
        query = query.where(WishProgressCandidate.status == status)
    if wish_id:
        query = query.where(WishProgressCandidate.wish_id == wish_id)
    query = query.order_by(desc(WishProgressCandidate.created_at)).limit(limit)
    result = await db.execute(query)
    items = []
    for c in result.scalars():
        items.append({
            "id": c.id,
            "wish_id": c.wish_id,
            "source_id": c.source_id,
            "suggested_progress": c.suggested_progress,
            "suggested_milestone_index": c.suggested_milestone_index,
            "ai_confidence": c.ai_confidence,
            "ai_reason": c.ai_reason,
            "status": c.status,
            "extract_status": c.extract_status,
            "created_at": c.created_at.isoformat(),
        })
    return {"items": items}


@router.post("/candidates/{candidate_id}/review", summary="审核进度候选")
async def review_candidate(
    candidate_id: int, action: CandidateReviewAction, db: AsyncSession = Depends(get_db)
):
    cand = await db.get(WishProgressCandidate, candidate_id)
    if not cand:
        raise HTTPException(status_code=404, detail="候选不存在")
    if cand.status != "pending":
        raise HTTPException(status_code=400, detail=f"候选已被处理（{cand.status}）")

    if action.action == "reject":
        cand.status = "rejected"
        cand.reviewed_at = datetime.now()
        await db.flush()
        return {"message": "已忽略"}

    if action.action != "accept":
        raise HTTPException(status_code=400, detail="action 必须为 accept 或 reject")

    wish = await _get_wish_or_404(db, cand.wish_id)

    if cand.suggested_milestone_index is not None and wish.milestones:
        idx = cand.suggested_milestone_index
        if 0 <= idx < len(wish.milestones):
            milestones = list(wish.milestones)
            milestones[idx]["completed"] = True
            wish.milestones = milestones

    if wish.milestones:
        _recompute_progress(wish)
    elif cand.suggested_progress is not None:
        wish.progress = max(0, min(100, max(wish.progress, cand.suggested_progress)))

    cand.status = "accepted"
    cand.reviewed_at = datetime.now()
    await db.flush()
    await db.refresh(wish)
    return {"message": "已采纳", "wish": _wish_to_detail(wish)}


@router.get("/{wish_id}", summary="心愿详情")
async def get_wish(wish_id: int, db: AsyncSession = Depends(get_db)):
    wish = await _get_wish_or_404(db, wish_id)
    return _wish_to_detail(wish)


@router.put("/{wish_id}", summary="更新心愿")
async def update_wish(wish_id: int, data: WishUpdate, db: AsyncSession = Depends(get_db)):
    wish = await _get_wish_or_404(db, wish_id)
    if data.content is not None:
        wish.content = data.content
    if data.category is not None:
        wish.category = data.category
    if data.linked_todo_category is not None:
        wish.linked_todo_category = data.linked_todo_category
    if data.progress_step is not None:
        wish.progress_step = data.progress_step
    if data.progress is not None:
        if wish.milestones:
            # 有里程碑时进度由里程碑完成比例自动计算，忽略手动输入
            pass
        else:
            wish.progress = data.progress
    await db.flush()
    await db.refresh(wish)
    return _wish_to_detail(wish)


@router.delete("/{wish_id}", summary="删除心愿")
async def delete_wish(wish_id: int, db: AsyncSession = Depends(get_db)):
    wish = await _get_wish_or_404(db, wish_id)

    logs_result = await db.execute(select(WishLogEntry).where(WishLogEntry.wish_id == wish_id))
    for log in logs_result.scalars():
        await db.delete(log)

    cands_result = await db.execute(select(WishProgressCandidate).where(WishProgressCandidate.wish_id == wish_id))
    for cand in cands_result.scalars():
        await db.delete(cand)

    await db.delete(wish)
    await db.flush()
    return {"message": "心愿已删除"}


# ======================== 里程碑 ========================

@router.post("/{wish_id}/milestones", summary="新增里程碑")
async def add_milestone(wish_id: int, data: MilestoneCreate, db: AsyncSession = Depends(get_db)):
    wish = await _get_wish_or_404(db, wish_id)
    milestones = list(wish.milestones or [])
    milestones.append({
        "text": data.text,
        "type": data.type,
        "completed": None,
        "ai_evaluation": None,
        "ai_score": None,
    })
    wish.milestones = milestones
    _recompute_progress(wish)
    await db.flush()
    await db.refresh(wish)
    return _wish_to_detail(wish)


@router.patch("/{wish_id}/milestones/{index}/toggle", summary="切换里程碑完成状态")
async def toggle_milestone(wish_id: int, index: int, db: AsyncSession = Depends(get_db)):
    wish = await _get_wish_or_404(db, wish_id)
    if not wish.milestones or index < 0 or index >= len(wish.milestones):
        raise HTTPException(status_code=400, detail="里程碑索引无效")
    milestones = list(wish.milestones)
    current = milestones[index].get("completed")
    milestones[index]["completed"] = not bool(current)
    wish.milestones = milestones
    _recompute_progress(wish)
    await db.flush()
    await db.refresh(wish)
    return _wish_to_detail(wish)


@router.delete("/{wish_id}/milestones/{index}", summary="删除里程碑")
async def delete_milestone(wish_id: int, index: int, db: AsyncSession = Depends(get_db)):
    wish = await _get_wish_or_404(db, wish_id)
    if not wish.milestones or index < 0 or index >= len(wish.milestones):
        raise HTTPException(status_code=400, detail="里程碑索引无效")
    milestones = list(wish.milestones)
    milestones.pop(index)
    wish.milestones = milestones
    _recompute_progress(wish)
    await db.flush()
    await db.refresh(wish)
    return _wish_to_detail(wish)


# ======================== 进展日志 ========================

@router.post("/{wish_id}/logs", summary="写进展日志（异步触发AI分析）")
async def create_log(wish_id: int, data: LogCreate, db: AsyncSession = Depends(get_db)):
    await _get_wish_or_404(db, wish_id)
    log = WishLogEntry(wish_id=wish_id, content=data.content)
    db.add(log)
    await db.flush()
    await db.refresh(log)

    # 后台异步触发 AI 分析，不阻塞本次请求
    asyncio.create_task(wishlist_ai.analyze_wish_log(wish_id, log.id, log.content))

    return {
        "id": log.id,
        "wish_id": log.wish_id,
        "content": log.content,
        "ai_processed": log.ai_processed,
        "created_at": log.created_at.isoformat(),
    }


@router.get("/{wish_id}/logs", summary="进展日志列表")
async def list_logs(
    wish_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    await _get_wish_or_404(db, wish_id)
    result = await db.execute(
        select(WishLogEntry)
        .where(WishLogEntry.wish_id == wish_id)
        .order_by(desc(WishLogEntry.created_at))
        .offset(skip).limit(limit)
    )
    logs = list(result.scalars())

    # 附带每条日志是否有待审候选
    cand_result = await db.execute(
        select(WishProgressCandidate).where(
            WishProgressCandidate.wish_id == wish_id,
            WishProgressCandidate.status == "pending",
        )
    )
    pending_by_log = {c.source_id: c for c in cand_result.scalars()}

    items = []
    for log in logs:
        cand = pending_by_log.get(log.id)
        items.append({
            "id": log.id,
            "wish_id": log.wish_id,
            "content": log.content,
            "ai_processed": log.ai_processed,
            "created_at": log.created_at.isoformat(),
            "pending_candidate": ({
                "id": cand.id,
                "suggested_progress": cand.suggested_progress,
                "suggested_milestone_index": cand.suggested_milestone_index,
                "ai_confidence": cand.ai_confidence,
                "ai_reason": cand.ai_reason,
            } if cand else None),
        })
    return {"items": items}


# ======================== 实现仪式 ========================

@router.post("/{wish_id}/achieve", summary="实现这个心愿")
async def achieve_wish(wish_id: int, data: AchieveRequest, db: AsyncSession = Depends(get_db)):
    wish = await _get_wish_or_404(db, wish_id)
    wish.status = "achieved"
    wish.achieved_at = datetime.now()
    wish.achieved_note = data.note
    wish.progress = 100
    await db.flush()

    # 联动 1：心力模块成就记录
    try:
        from app.models.wellbeing import WellbeingEntry
        entry = WellbeingEntry(
            type="achievement",
            content=f"实现了心愿：{wish.content[:100]}",
            category="其他",
            intensity=5,
            occurred_at=date.today(),
            source_type="wish",
            source_id=wish.id,
            source_excerpt=data.note,
        )
        db.add(entry)
        await db.flush()
    except Exception as e:
        logger.warning(f"心愿实现联动心力模块失败: wish_id={wish_id} err={e}")

    # 联动 2：反哺用户画像
    try:
        from app.services.ai_service import update_user_profile
        await update_user_profile(db, [{
            "category": "成长目标",
            "key": f"心愿达成-{wish.content[:30]}",
            "value": f"实现了「{wish.content[:60]}」，感悟：{data.note or '无'}",
            "action": "create",
            "evidence": data.note or wish.content,
        }])
    except Exception as e:
        logger.warning(f"心愿实现联动用户画像失败: wish_id={wish_id} err={e}")

    await db.refresh(wish)
    return {"message": "心愿已实现，恭喜！", "wish": _wish_to_detail(wish)}
