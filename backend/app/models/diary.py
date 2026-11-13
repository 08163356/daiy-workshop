"""日记模块数据模型"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, Date, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DiaryEntry(Base):
    """日记记录表"""

    __tablename__ = "diary_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 原始日记内容
    ai_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI 分析结果
    mood: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 整体情绪
    tags: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 标签
    key_issues: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 关键问题
    action_items: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 行动建议
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # 原始文件路径
    images: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 图片URL列表
    source: Mapped[str] = mapped_column(String(50), default="web")  # 来源：web/sync
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<DiaryEntry(id={self.id}, date='{self.date}', title='{self.title}')>"
