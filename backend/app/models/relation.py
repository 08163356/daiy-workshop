"""概念关系模型"""
from __future__ import annotations

from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.concept import Concept


class ConceptRelation(Base):
    """概念关系表（知识图谱核心）"""

    __tablename__ = "concept_relations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # co_occurs, related_to, belongs_to 等
    strength: Mapped[float] = mapped_column(Float, default=1.0)  # 关系强度 0-1

    # 关联关系
    source: Mapped["Concept"] = relationship(
        "Concept",
        foreign_keys=[source_id],
        back_populates="source_relations",
    )
    target: Mapped["Concept"] = relationship(
        "Concept",
        foreign_keys=[target_id],
        back_populates="target_relations",
    )

    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relation_type", name="uix_relation"),
    )

    def __repr__(self) -> str:
        return f"<ConceptRelation(source={self.source_id}, target={self.target_id}, type='{self.relation_type}')>"
