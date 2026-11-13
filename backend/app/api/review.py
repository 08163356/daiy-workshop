"""审批中心 API — 管理 AI 自动化产出的审批流

提供 CRUD + 审批/拒绝 + JSON 导出（迁移用）。
外部自动化脚本通过 POST /api/review/items 写入待审批条目，
用户在 daily 前端审核后点"同意"，前端再调 POST .../approve。
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.review import ReviewItem

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/review", tags=["review"])


# ==================== Schema ====================

class ReviewCreate(BaseModel):
    type: str = Field(..., description="resume | blog | gbrain | deploy | general")
    title: str
    summary: str = ""
    content: str = ""
    source: str = "manual"
    metadata: dict = Field(default_factory=dict)
    syncCommand: str = ""


class ReviewAction(BaseModel):
    note: str = ""


# ==================== CRUD ====================

@router.get("/items")
async def list_items(
    status: str | None = Query(None, description="过滤状态：pending/approved/rejected/expired"),
    type: str | None = Query(None, description="过滤类型：resume/blog/gbrain/deploy/general"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """获取审批条目列表"""
    q = select(ReviewItem).order_by(desc(ReviewItem.created_at))
    if status:
        q = q.where(ReviewItem.status == status)
    if type:
        q = q.where(ReviewItem.type == type)
    q = q.offset(offset).limit(limit)

    result = await db.execute(q)
    items = result.scalars().all()

    # 统计
    count_q = select(func.count(ReviewItem.id))
    if status:
        count_q = count_q.where(ReviewItem.status == status)
    if type:
        count_q = count_q.where(ReviewItem.type == type)
    total = (await db.execute(count_q)).scalar() or 0

    return {"items": [i.to_dict() for i in items], "total": total}


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """获取各状态数量统计（侧栏徽标用）"""
    result = await db.execute(
        select(ReviewItem.status, func.count(ReviewItem.id)).group_by(ReviewItem.status)
    )
    counts = {row[0]: row[1] for row in result}
    return {
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "expired": counts.get("expired", 0),
        "total": sum(counts.values()),
    }


@router.get("/items/{item_id}")
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """获取单条审批详情"""
    result = await db.execute(select(ReviewItem).where(ReviewItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "审批条目不存在")
    return item.to_dict()


@router.post("/items")
async def create_item(data: ReviewCreate, db: AsyncSession = Depends(get_db)):
    """创建待审批条目（AI/自动化脚本调用）"""
    item = ReviewItem(
        type=data.type,
        title=data.title,
        summary=data.summary,
        content=data.content,
        source=data.source,
        metadata_json=data.metadata,
        sync_command=data.syncCommand,
    )
    db.add(item)
    await db.flush()
    await db.commit()
    await db.refresh(item)
    logger.info(f"[Review] 新建审批: #{item.id} {item.type}/{item.title} from {item.source}")
    return item.to_dict()


@router.put("/items/{item_id}")
async def update_item(item_id: int, data: ReviewCreate, db: AsyncSession = Depends(get_db)):
    """更新审批条目（仅 pending 状态可改）"""
    result = await db.execute(select(ReviewItem).where(ReviewItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "审批条目不存在")
    if item.status != "pending":
        raise HTTPException(400, f"状态为 {item.status}，不可修改")

    item.type = data.type
    item.title = data.title
    item.summary = data.summary
    item.content = data.content
    item.source = data.source
    item.metadata_json = data.metadata
    item.sync_command = data.syncCommand
    await db.flush()
    await db.commit()
    return item.to_dict()


# ==================== 审批动作 ====================

@router.post("/items/{item_id}/approve")
async def approve_item(item_id: int, action: ReviewAction, db: AsyncSession = Depends(get_db)):
    """审批通过"""
    result = await db.execute(select(ReviewItem).where(ReviewItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "审批条目不存在")
    if item.status != "pending":
        raise HTTPException(400, f"状态为 {item.status}，不可审批")

    item.status = "approved"
    item.reviewed_at = datetime.utcnow()
    item.reviewer_note = action.note
    await db.flush()
    await db.commit()
    logger.info(f"[Review] 已通过: #{item.id} {item.title}")
    return {
        **item.to_dict(),
        "message": "已通过，请执行同步",
        "syncCommand": item.sync_command,
    }


@router.post("/items/{item_id}/reject")
async def reject_item(item_id: int, action: ReviewAction, db: AsyncSession = Depends(get_db)):
    """审批拒绝"""
    result = await db.execute(select(ReviewItem).where(ReviewItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "审批条目不存在")
    if item.status != "pending":
        raise HTTPException(400, f"状态为 {item.status}，不可拒绝")

    item.status = "rejected"
    item.reviewed_at = datetime.utcnow()
    item.reviewer_note = action.note
    await db.flush()
    await db.commit()
    logger.info(f"[Review] 已拒绝: #{item.id} {item.title}")
    return item.to_dict()


@router.delete("/items/{item_id}")
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """删除审批条目"""
    result = await db.execute(select(ReviewItem).where(ReviewItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "审批条目不存在")
    await db.delete(item)
    await db.flush()
    await db.commit()
    return {"message": "已删除"}


# ==================== 导出（迁移用） ====================

@router.get("/export")
async def export_items(db: AsyncSession = Depends(get_db)):
    """导出全部审批条目为 JSON（一键迁移用）"""
    result = await db.execute(select(ReviewItem).order_by(ReviewItem.created_at))
    items = result.scalars().all()
    return {
        "exportedAt": datetime.utcnow().isoformat(),
        "count": len(items),
        "items": [i.to_dict() for i in items],
    }
