"""心力模块（成就 + 感恩）数据模型"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, Date, JSON, Float, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WellbeingEntry(Base):
    """心力条目（成就 / 感恩）"""

    __tablename__ = "wellbeing_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # achievement / gratitude
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 主体内容
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # 工作/家庭/健康/关系/学习/其他
    intensity: Mapped[int] = mapped_column(Integer, default=3)  # 强度 1-5
    occurred_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # 发生日期

    # 来源追踪
    source_type: Mapped[str] = mapped_column(String(20), default="manual")  # manual / diary / note / todo
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 原文片段

    # 富信息
    mood_tag: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ai_tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # AI 自动标签
    ai_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI 识别理由（从候选采纳时保留）

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("ix_wellbeing_entries_occurred_type", "occurred_at", "type"),
    )

    def __repr__(self) -> str:
        return f"<WellbeingEntry(id={self.id}, type='{self.type}', occurred_at='{self.occurred_at}')>"


class WellbeingCandidate(Base):
    """AI 从日记/笔记中提取的候选成就/感恩条目，待用户审核"""

    __tablename__ = "wellbeing_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 来源
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # diary / note
    source_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 原文片段

    # AI 建议
    suggested_type: Mapped[str] = mapped_column(String(20), nullable=False)  # achievement / gratitude
    suggested_content: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    suggested_intensity: Mapped[int] = mapped_column(Integer, default=3)
    suggested_tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    ai_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    ai_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 审核状态
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending / accepted / rejected
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_entry_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 提取过程
    extract_status: Mapped[str] = mapped_column(String(20), default="success")  # success / failed
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<WellbeingCandidate(id={self.id}, status='{self.status}', source={self.source_type}/{self.source_id})>"


class WellbeingReport(Base):
    """AI 生成的周报/月报，按 period_key 缓存"""

    __tablename__ = "wellbeing_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # week / month
    period_key: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # 2026-W17 / 2026-04
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    # AI 报告内容（杂志式排版的 Markdown）
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # 关键指标/亮点/洞察

    # 元信息
    achievement_count: Mapped[int] = mapped_column(Integer, default=0)
    gratitude_count: Mapped[int] = mapped_column(Integer, default=0)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)

    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("ix_wellbeing_reports_period", "period_type", "period_key", unique=True),
    )

    def __repr__(self) -> str:
        return f"<WellbeingReport(id={self.id}, type='{self.period_type}', key='{self.period_key}')>"


class WellbeingTag(Base):
    """心力标签库（用于自动补全 + 统计）"""

    __tablename__ = "wellbeing_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # achievement / gratitude / both
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<WellbeingTag(id={self.id}, name='{self.name}', type='{self.type}')>"
