"""同步 API"""

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["同步"])


@router.post("", summary="触发同步")
async def trigger_sync(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    同步 Markdown 文件到数据库

    - 扫描配置的 Markdown 目录
    - 解析文件内容，提取概念
    - 建立概念关系
    """
    service = SyncService(db)
    stats = await service.sync_all()
    return {
        "status": "completed",
        "message": "同步完成",
        "stats": stats,
    }


@router.post("/async", summary="异步触发同步")
async def trigger_sync_async(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    异步同步（后台执行）

    立即返回，同步在后台进行
    """
    # 注意：这里简化处理，实际应该使用独立的数据库会话
    background_tasks.add_task(_sync_in_background)

    return {
        "status": "started",
        "message": "同步已在后台启动",
    }


async def _sync_in_background() -> None:
    """后台同步任务"""
    from app.core.database import async_session_maker

    async with async_session_maker() as db:
        service = SyncService(db)
        await service.sync_all()
        await db.commit()


@router.delete("", summary="清空所有数据")
async def clear_all_data(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    清空所有数据

    ⚠️ 危险操作！将删除所有笔记、概念和关系数据
    """
    service = SyncService(db)
    return await service.clear_all()


@router.get("/status", summary="获取同步状态")
async def get_sync_status(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """获取当前数据状态"""
    from sqlalchemy import select, func
    from app.models import Note, Concept, ConceptRelation

    note_count = await db.scalar(select(func.count(Note.id))) or 0
    concept_count = await db.scalar(select(func.count(Concept.id))) or 0
    relation_count = await db.scalar(select(func.count(ConceptRelation.id))) or 0

    return {
        "markdown_dir": str(settings.markdown_dir),
        "note_count": note_count,
        "concept_count": concept_count,
        "relation_count": relation_count,
    }
