"""笔记 API"""

import hashlib
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Note, NoteConcept, Concept
from app.schemas.note import NoteResponse, NoteListResponse, NoteListItem, ConceptBrief

router = APIRouter(prefix="/notes", tags=["笔记"])


@router.get("", response_model=NoteListResponse, summary="获取笔记列表")
async def list_notes(
    skip: int = Query(0, ge=0, description="跳过数量"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    source_type: Optional[str] = Query(None, description="来源类型过滤: book/course/self"),
    db: AsyncSession = Depends(get_db),
) -> NoteListResponse:
    """获取笔记列表"""
    # 基础查询
    query = select(Note)

    if keyword:
        query = query.where(
            Note.title.contains(keyword) | Note.content.contains(keyword)
        )

    if source_type:
        query = query.where(Note.source_type == source_type)

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # 分页查询
    query = query.order_by(Note.reading_date.desc(), Note.created_at.desc())
    query = query.offset(skip).limit(limit)

    notes = await db.scalars(query)

    items = []
    for note in notes:
        # 统计关联概念数量
        concept_count = await db.scalar(
            select(func.count()).where(NoteConcept.note_id == note.id)
        )

        items.append(
            NoteListItem(
                id=note.id,
                filename=note.filename,
                title=note.title,
                summary=note.summary,
                reading_date=note.reading_date,
                word_count=note.word_count,
                source_type=note.source_type,
                course_meta=note.course_meta,
                created_at=note.created_at,
                concept_count=concept_count or 0,
            )
        )

    return NoteListResponse(total=total, items=items)


class PlainNoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    source_type: str = Field("self", description="book/course/self")


@router.post("/plain", summary="不经过 AI，直接保存一篇笔记")
async def create_plain_note(data: PlainNoteCreate, db: AsyncSession = Depends(get_db)):
    source_type = data.source_type if data.source_type in ("book", "course", "self") else "self"
    now = datetime.now()
    content = data.content.strip()
    note = Note(
        filename=f"plain-{now.strftime('%Y%m%d%H%M%S')}-{hashlib.md5(content.encode()).hexdigest()[:8]}.md",
        title=data.title.strip()[:255],
        content=content,
        reading_date=date.today(),
        word_count=len(content),
        file_hash=hashlib.md5(f"plain-{now.isoformat()}-{content[:80]}".encode()).hexdigest(),
        source_type=source_type,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return {"id": note.id, "title": note.title}


@router.get("/{note_id}", response_model=NoteResponse, summary="获取笔记详情")
async def get_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
) -> NoteResponse:
    """获取笔记详情"""
    # 加载笔记和关联概念
    query = (
        select(Note)
        .where(Note.id == note_id)
        .options(selectinload(Note.note_concepts).selectinload(NoteConcept.concept))
    )

    note = await db.scalar(query)

    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")

    # 构建概念列表
    concepts = [
        ConceptBrief(
            id=nc.concept.id,
            name=nc.concept.name,
            category=nc.concept.category,
        )
        for nc in note.note_concepts
    ]

    return NoteResponse(
        id=note.id,
        filename=note.filename,
        title=note.title,
        content=note.content,
        summary=note.summary,
        reading_date=note.reading_date,
        word_count=note.word_count,
        created_at=note.created_at,
        updated_at=note.updated_at,
        concepts=concepts,
    )


@router.get("/{note_id}/concepts", summary="获取笔记关联的概念")
async def get_note_concepts(
    note_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[ConceptBrief]:
    """获取笔记关联的概念"""
    # 检查笔记是否存在
    note = await db.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")

    # 查询关联概念
    query = (
        select(Concept)
        .join(NoteConcept, NoteConcept.concept_id == Concept.id)
        .where(NoteConcept.note_id == note_id)
    )

    concepts = await db.scalars(query)

    return [
        ConceptBrief(id=c.id, name=c.name, category=c.category)
        for c in concepts
    ]
