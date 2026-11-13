"""知识库文章/工具收藏数据模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Article(Base):
    """知识库条目表 - 文章资讯 / 工具收藏"""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)  # 标题
    url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)  # URL 链接（可选）
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 文本内容（可选）
    item_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="article", index=True
    )  # 条目类型: article(文章资讯) / tool(工具收藏)
    content_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="url"
    )  # 内容来源类型: url / text / ai_note
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 摘要
    read_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default="unread", index=True
    )  # 阅读状态: unread / read / None(工具类不区分)
    tags: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 标签列表（JSON 数组）
    note_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 关联的读后笔记 ID（notes 表）
    source_chat_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )  # 来源对话 ID（从 AI 对话保存时记录）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, title='{self.title}', type='{self.item_type}')>"
