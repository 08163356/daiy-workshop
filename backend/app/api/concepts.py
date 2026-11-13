"""概念 API"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Concept, NoteConcept, Note, ConceptRelation
from app.schemas.concept import (
    ConceptResponse,
    ConceptListResponse,
    ConceptListItem,
    RelatedNote,
    RelatedConcept,
)

router = APIRouter(prefix="/concepts", tags=["概念"])


@router.get("", response_model=ConceptListResponse, summary="获取概念列表")
async def list_concepts(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
    category: Optional[str] = Query(None, description="按分类过滤"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    min_importance: int = Query(1, ge=1, le=5, description="最小重要程度"),
    db: AsyncSession = Depends(get_db),
) -> ConceptListResponse:
    """获取概念列表"""
    query = select(Concept)

    if category:
        query = query.where(Concept.category == category)

    if keyword:
        query = query.where(Concept.name.contains(keyword))

    if min_importance > 1:
        query = query.where(Concept.importance >= min_importance)

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # 分页查询（按重要程度和提及次数排序）
    query = query.order_by(
        Concept.importance.desc(),
        Concept.mention_count.desc(),
        Concept.name,
    )
    query = query.offset(skip).limit(limit)

    concepts = await db.scalars(query)

    items = [
        ConceptListItem(
            id=c.id,
            name=c.name,
            category=c.category,
            importance=c.importance,
            mention_count=c.mention_count,
        )
        for c in concepts
    ]

    return ConceptListResponse(total=total, items=items)


@router.get("/categories", summary="获取概念分类列表")
async def list_categories(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """获取所有概念分类"""
    query = (
        select(Concept.category, func.count(Concept.id).label("count"))
        .where(Concept.category.isnot(None))
        .group_by(Concept.category)
        .order_by(func.count(Concept.id).desc())
    )

    result = await db.execute(query)
    return [{"category": row.category, "count": row.count} for row in result]


@router.get("/{concept_id}", response_model=ConceptResponse, summary="获取概念详情")
async def get_concept(
    concept_id: int,
    db: AsyncSession = Depends(get_db),
) -> ConceptResponse:
    """获取概念详情"""
    concept = await db.get(Concept, concept_id)

    if not concept:
        raise HTTPException(status_code=404, detail="概念不存在")

    # 获取关联笔记
    notes_query = (
        select(Note)
        .join(NoteConcept, NoteConcept.note_id == Note.id)
        .where(NoteConcept.concept_id == concept_id)
    )
    notes = await db.scalars(notes_query)
    related_notes = [
        RelatedNote(id=n.id, title=n.title, filename=n.filename)
        for n in notes
    ]

    # 获取关联概念
    relations_query = select(ConceptRelation).where(
        (ConceptRelation.source_id == concept_id)
        | (ConceptRelation.target_id == concept_id)
    )
    relations = await db.scalars(relations_query)

    related_concepts = []
    seen_ids = set()

    for rel in relations:
        other_id = rel.target_id if rel.source_id == concept_id else rel.source_id
        if other_id not in seen_ids:
            seen_ids.add(other_id)
            other_concept = await db.get(Concept, other_id)
            if other_concept:
                related_concepts.append(
                    RelatedConcept(
                        id=other_concept.id,
                        name=other_concept.name,
                        relation_type=rel.relation_type,
                        strength=rel.strength,
                    )
                )

    return ConceptResponse(
        id=concept.id,
        name=concept.name,
        description=concept.description,
        category=concept.category,
        importance=concept.importance,
        mention_count=concept.mention_count,
        created_at=concept.created_at,
        related_notes=related_notes,
        related_concepts=related_concepts,
    )
