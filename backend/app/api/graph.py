"""知识图谱 API"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.graph_service import GraphService
from app.schemas.graph import GraphResponse, GraphFilterParams

router = APIRouter(prefix="/graph", tags=["知识图谱"])


@router.get("", response_model=GraphResponse, summary="获取知识图谱")
async def get_graph(
    category: Optional[str] = Query(None, description="按分类过滤"),
    min_importance: int = Query(1, ge=1, le=5, description="最小重要程度"),
    min_mention_count: int = Query(0, ge=0, description="最小提及次数"),
    limit: int = Query(100, ge=1, le=500, description="最大节点数"),
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    """
    获取知识图谱数据

    返回格式适配前端可视化库（如 vis.js, echarts, d3.js）
    """
    params = GraphFilterParams(
        category=category,
        min_importance=min_importance,
        min_mention_count=min_mention_count,
        limit=limit,
    )

    service = GraphService(db)
    return await service.get_graph(params)


@router.get("/concept/{concept_id}", response_model=GraphResponse, summary="获取概念邻居图谱")
async def get_concept_neighbors(
    concept_id: int,
    depth: int = Query(1, ge=1, le=3, description="遍历深度"),
    db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    """获取指定概念的邻居节点图谱"""
    service = GraphService(db)
    return await service.get_concept_neighbors(concept_id, depth)


@router.get("/categories", summary="获取图谱分类统计")
async def get_categories(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """获取所有概念分类及数量统计"""
    service = GraphService(db)
    return await service.get_categories()
