"""概念模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Text, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.note import NoteConcept
    from app.models.relation import ConceptRelation


class Concept(Base):
    """概念表"""

    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    importance: Mapped[int] = mapped_column(Integer, default=1)  # 重要程度 1-5
    mention_count: Mapped[int] = mapped_column(Integer, default=0)  # 被提及次数
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # 关联关系
    note_concepts: Mapped[List[NoteConcept]] = relationship(
        "NoteConcept",
        back_populates="concept",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # 作为源节点的关系
    source_relations: Mapped[List[ConceptRelation]] = relationship(
        "ConceptRelation",
        foreign_keys="ConceptRelation.source_id",
        back_populates="source",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # 作为目标节点的关系
    target_relations: Mapped[List[ConceptRelation]] = relationship(
        "ConceptRelation",
        foreign_keys="ConceptRelation.target_id",
        back_populates="target",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Concept(id={self.id}, name='{self.name}')>"
