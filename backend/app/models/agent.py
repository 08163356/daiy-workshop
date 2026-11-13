"""统一 AI 助手会话模型（事件溯源）"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentSession(Base):
    """AI 助手会话表"""

    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 首条消息后自动生成
    title_pinned: Mapped[bool] = mapped_column(Boolean, default=False)  # 用户改名后钉住，自动生成不再覆盖
    ai_config_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 会话绑定模型，null=跟随全局
    mode: Mapped[str] = mapped_column(String(20), default="normal")  # normal / coach / explore
    status: Mapped[str] = mapped_column(String(20), default="idle")  # idle/running
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 教练会话结束沉淀的对话总结
    insights: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # 结束沉淀的关键洞察
    # 教练跟进项与来源（coach-dialogue-skill 方案）：followups=[{text,check_question,review_on,todo_id,status}]
    followups: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # 结束沉淀抽出的跟进项
    origin_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 入口来源: diary/note/question
    origin_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 来源记录 id
    origin_extra: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # 对话中转到的其它日记/笔记 id
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<AgentSession(id={self.id}, title='{self.title}')>"


class AgentEvent(Base):
    """会话事件日志 —— 唯一事实源，消息从事件投影派生（借鉴 harness SessionEvent 设计）"""

    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # 会话内单调递增
    event_type: Mapped[str] = mapped_column(String(30))  # user_message/assistant_message/thinking/tool_call/tool_result
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    surface_op: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # 预留：compaction 的 replace 操作
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<AgentEvent(id={self.id}, session={self.session_id}, seq={self.seq}, type='{self.event_type}')>"
