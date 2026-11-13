"""教练对话数据模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Any, List
from sqlalchemy import String, Text, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CoachingSession(Base):
    """教练对话 Session 表 - 记录每次教练对话"""

    __tablename__ = "coaching_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    messages: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)  # 消息历史
    coaching_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # AI 检测到的教练类型
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 对话总结
    insights: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)  # 关键洞察
    profile_updates: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)  # 画像更新
    is_ended: Mapped[bool] = mapped_column(default=False)  # 是否已结束
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<CoachingSession(id={self.id}, session_id='{self.session_id}')>"
