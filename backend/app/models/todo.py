"""待办模块数据模型"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, Date, JSON, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TodoItem(Base):
    """待办事项表"""

    __tablename__ = "todo_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quadrant: Mapped[int] = mapped_column(Integer, default=4, index=True)  # 1=重要紧急 2=重要不紧急 3=紧急不重要 4=不重要不紧急
    status: Mapped[str] = mapped_column(String(20), default="inbox", index=True)  # inbox/evaluated/planned/in_progress/completed/cancelled/deferred
    urgency: Mapped[int] = mapped_column(Integer, default=3)  # 紧急度 1-5
    importance: Mapped[int] = mapped_column(Integer, default=3)  # 重要度 1-5
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # 任务分类: work/learning/life/health/social/finance/creative
    tags: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    ai_evaluation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI 评估说明
    ai_category: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # AI 分类: actionable/answerable/splittable/questionable/low_value
    ai_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI 直接解答内容
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 用户原始输入文本
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual/ai_split/diary/ai_suggest
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 来源 ID（如日记 ID）
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 父任务 ID（拆分关系）
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    scheduled_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)  # 计划执行日期
    scheduled_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # 计划结束日期（跨天任务）
    sort_order: Mapped[int] = mapped_column(Integer, default=0)  # 排序顺序（同一天内）
    estimated_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 预估耗时（分钟）
    actual_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 实际耗时（分钟）
    deferred_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # 推迟到（冰箱机制）
    completion_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 完成备注（旧，保留兼容）
    completion_notes: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 完成备注列表（新，JSON数组）
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 核心任务标记：week/month/year + 周期 key（如 2026-W43 / 2026-10 / 2026）
    core_scope: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, index=True)
    core_period_key: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<TodoItem(id={self.id}, title='{self.title}', status='{self.status}')>"


class InboxHistory(Base):
    """收集箱对话历史表 - 记录每次收集箱的AI评估对话"""

    __tablename__ = "inbox_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)  # 用户原始输入
    ai_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI原始Markdown回复
    structured_items: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 结构化提取的items
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI总结
    saved_count: Mapped[int] = mapped_column(Integer, default=0)  # 最终保存了几条
    elapsed_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 耗时
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<InboxHistory(id={self.id}, created_at='{self.created_at}')>"


class RecurringTask(Base):
    """重复任务/习惯追踪表"""

    __tablename__ = "recurring_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    frequency: Mapped[str] = mapped_column(String(20), default="daily")  # daily/weekly/custom
    frequency_detail: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 自定义周期详情（如 "mon,wed,fri"）
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    next_due: Mapped[date] = mapped_column(Date, nullable=False)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    total_completed: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_event: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 自动打卡事件: diary/basketball
    auto_keywords: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # 自动打卡关键词（逗号分隔）
    last_checkin_auto: Mapped[bool] = mapped_column(Boolean, default=False)  # 最近一次打卡是否为自动打卡
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<RecurringTask(id={self.id}, title='{self.title}', streak={self.streak})>"


class TodoComment(Base):
    """待办评论表 — 想法记录 / 经验沉淀"""

    __tablename__ = "todo_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    todo_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="idea", nullable=False)  # idea=想法 lesson=经验
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<TodoComment(id={self.id}, todo_id={self.todo_id})>"
