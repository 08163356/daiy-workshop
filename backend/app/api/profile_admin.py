"""画像管理 API：查看/编辑/删除 + 快照/回滚 + 整理提案（consent-first）"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import profile_admin_service as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profile-admin", tags=["用户画像管理"])


# ==================== 画像 CRUD ====================

@router.get("")
async def get_profile(db: AsyncSession = Depends(get_db)):
    """画像全量（按分类分组）"""
    return await svc.list_grouped(db)


class ProfileEntryUpdate(BaseModel):
    key: Optional[str] = Field(None, min_length=1, max_length=200)
    value: Optional[str] = Field(None, min_length=1, max_length=2000)
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    confidence: Optional[float] = Field(None, ge=0, le=1)


@router.put("/{entry_id}")
async def update_profile_entry(entry_id: int, data: ProfileEntryUpdate, db: AsyncSession = Depends(get_db)):
    """手动编辑画像条目（编辑也算一次人工校准，置信度拉满）"""
    fields = data.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="没有要更新的字段")
    try:
        row = await svc.update_entry(db, entry_id, fields)
        return {"id": row.id, "category": row.category, "key": row.key,
                "value": row.value, "confidence": row.confidence}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{entry_id}")
async def delete_profile_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    """删除画像条目"""
    try:
        await svc.delete_entry(db, entry_id)
        return {"message": "已删除"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== 快照 ====================

@router.get("/snapshots")
async def list_snapshots(db: AsyncSession = Depends(get_db)):
    """快照列表（不含数据本体，只列元信息）"""
    snaps = await svc.list_snapshots(db)
    return [{
        "id": s.id, "reason": s.reason, "entry_count": s.entry_count,
        "created_at": s.created_at.isoformat(),
    } for s in snaps]


@router.post("/snapshots")
async def create_snapshot(reason: str = "手动快照", db: AsyncSession = Depends(get_db)):
    """手动打快照"""
    snap = await svc.snapshot_profile(db, reason)
    return {"id": snap.id, "entry_count": snap.entry_count}


@router.post("/snapshots/{snapshot_id}/rollback")
async def rollback(snapshot_id: int, db: AsyncSession = Depends(get_db)):
    """回滚到快照（回滚前会自动备份当前状态）"""
    try:
        count = await svc.rollback_snapshot(db, snapshot_id)
        return {"message": f"已回滚，恢复 {count} 条", "entry_count": count}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== 整理提案 ====================

@router.get("/proposals")
async def list_proposals(db: AsyncSession = Depends(get_db)):
    """提案列表"""
    from sqlalchemy import select
    from app.models.profile_admin import ProfileProposal
    result = await db.execute(
        select(ProfileProposal).order_by(ProfileProposal.created_at.desc())
    )
    return [{
        "id": p.id, "status": p.status, "summary": p.summary, "stats": p.stats,
        "plan": p.plan if p.status == "pending" else None,  # 只有待审的返回完整计划
        "created_at": p.created_at.isoformat(),
        "applied_at": p.applied_at.isoformat() if p.applied_at else None,
    } for p in result.scalars()]


@router.post("/proposals")
async def propose_consolidation(db: AsyncSession = Depends(get_db)):
    """生成整理提案（AI 分析但不写画像，等确认）"""
    try:
        p = await svc.build_consolidation_plan(db)
        return {"id": p.id, "summary": p.summary, "stats": p.stats, "plan": p.plan}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/proposals/{proposal_id}/apply")
async def apply_proposal(proposal_id: int, db: AsyncSession = Depends(get_db)):
    """确认执行提案（自动先快照）"""
    try:
        return await svc.apply_proposal(db, proposal_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: int, db: AsyncSession = Depends(get_db)):
    """拒绝提案"""
    try:
        await svc.reject_proposal(db, proposal_id)
        return {"message": "已拒绝"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
