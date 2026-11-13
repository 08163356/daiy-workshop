"""微信读书数据模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WeReadConfig(Base):
    """微信读书配置（API Key +同步状态）"""

    __tablename__ = "weread_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key: Mapped[str] = mapped_column(String(200), nullable=False)
    sync_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    total_books: Mapped[int] = mapped_column(Integer, default=0)
    total_notes_synced: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<WeReadConfig(id={self.id})>"


class WeReadBook(Base):
    """微信读书书目元数据"""

    __tablename__ = "weread_books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    cover: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    intro: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reading_progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0-100
    is_finished: Mapped[bool] = mapped_column(Boolean, default=False)
    note_count: Mapped[int] = mapped_column(Integer, default=0)   # 已同步笔记数
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<WeReadBook(id={self.id}, title='{self.title}')>"
