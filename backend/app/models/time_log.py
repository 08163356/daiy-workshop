"""时间记录模块数据模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimeLog(Base):
    """时间记录表 - 记录每个任务/状态的计时段"""

    __tablename__ = "time_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    todo_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)  # 关联的待办 ID（状态记录时为 NULL）
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # 开始时间
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # 结束时间（null 表示正在计时）
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 时长（秒），停止时自动计算
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # 冗余存储分类，方便聚合
    activity_type: Mapped[str] = mapped_column(String(20), nullable=False, default="task")  # "task" 或 "status"
    status_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 状态标签（如"通勤"、"运动"）
    status_emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # 状态 emoji
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        if self.activity_type == "status":
            return f"<TimeLog(id={self.id}, status={self.status_label}, start={self.start_time})>"
        return f"<TimeLog(id={self.id}, todo_id={self.todo_id}, start={self.start_time})>"
