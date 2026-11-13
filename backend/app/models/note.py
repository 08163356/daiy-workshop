"""笔记模型"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, Integer, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.concept import Concept


class Note(Base):
    """笔记表"""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reading_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    images: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 图片URL列表
    source_type: Mapped[str] = mapped_column(String(20), default="book", nullable=False)  # book=读书笔记 course=课程/听课 self=个人随笔
    course_meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # 课程信息：{"instructor": "讲师", "platform": "平台"}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    note_concepts: Mapped[List[NoteConcept]] = relationship(
        "NoteConcept",
        back_populates="note",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Note(id={self.id}, title='{self.title}')>"


class NoteConcept(Base):
    """笔记-概念关联表"""

    __tablename__ = "note_concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    concept_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 概念出现的上下文

    # 关联关系
    note: Mapped["Note"] = relationship("Note", back_populates="note_concepts")
    concept: Mapped["Concept"] = relationship("Concept", back_populates="note_concepts")

    __table_args__ = (
        # 唯一约束：同一笔记中不重复关联同一概念
        {"sqlite_autoincrement": True},
    )

    def __repr__(self) -> str:
        return f"<NoteConcept(note_id={self.note_id}, concept_id={self.concept_id})>"
