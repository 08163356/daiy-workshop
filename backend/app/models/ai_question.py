"""AI 提问队列模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AIQuestion(Base):
    """AI 提问队列表 —— AI 读完内容后主动向用户澄清/了解的问题"""

    __tablename__ = "ai_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(20))  # diary/note/manual（主动提问）
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 生成依据摘要
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending/answered/dismissed
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<AIQuestion(id={self.id}, status='{self.status}', question='{self.question[:30]}')>"
