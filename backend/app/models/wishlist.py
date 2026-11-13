"""心愿清单数据模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, JSON, Float, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Wish(Base):
    """心愿主表：健康/事业/财富/关系/个人成长/物质 六大维度愿望"""

    __tablename__ = "wishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 愿望描述
    category: Mapped[str] = mapped_column(String(50), default="growth", index=True)  # health/career/wealth/relationship/growth/material/custom
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active/achieved/archived
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    # 里程碑清单: [{"text":str,"type":"self|ai","completed":bool|None,"ai_evaluation":str|None,"ai_score":float|None}]
    milestones: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    linked_todo_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # 关联待办分类，用于保底自动推进
    progress_step: Mapped[int] = mapped_column(Integer, default=10)  # 关联待办完成时的自动推进步长
    achieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    achieved_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 实现时的感恩留言
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("ix_wishes_status_category", "status", "category"),
    )

    def __repr__(self) -> str:
        return f"<Wish(id={self.id}, category='{self.category}', status='{self.status}')>"


class WishLogEntry(Base):
    """心愿进展日志：用户随时记录"做了什么"，AI 异步分析生成进度候选"""

    __tablename__ = "wish_log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wish_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    ai_processed: Mapped[bool] = mapped_column(default=False)  # 是否已触发过 AI 分析
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<WishLogEntry(id={self.id}, wish_id={self.wish_id})>"


class WishProgressCandidate(Base):
    """AI 从进展日志中分析出的进度更新候选，待用户审核采纳"""

    __tablename__ = "wish_progress_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wish_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 对应 WishLogEntry.id

    suggested_progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    suggested_milestone_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    ai_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending/accepted/rejected
    extract_status: Mapped[str] = mapped_column(String(20), default="success")  # success/failed
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<WishProgressCandidate(id={self.id}, wish_id={self.wish_id}, status='{self.status}')>"
