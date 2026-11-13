"""AI 聊天历史记录模型"""

from datetime import datetime
from typing import Optional, Any
from sqlalchemy import Integer, Text, DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ChatHistory(Base):
    """AI 聊天分析历史表 - 记录每次 AI 对话分析结果"""

    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)          # 用户输入内容
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # 标题
    system_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 类型
    analysis_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI 分析 markdown
    structured_data: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)   # 结构化数据
    profile_updates: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)   # 画像更新
    saved_to: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)          # 保存到哪些系统
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<ChatHistory(id={self.id}, system_type='{self.system_type}', created_at='{self.created_at}')>"
