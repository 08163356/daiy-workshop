"""时光胶囊信件数据模型"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, Date, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TimeCapsuleLetter(Base):
    """时光胶囊信件表"""

    __tablename__ = "time_capsule_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient: Mapped[str] = mapped_column(String(100), default="未来的自己")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 目标清单: [{"text": "...", "type": "self|ai", "completed": null|true|false, "ai_evaluation": "...", "ai_score": null|0.0-1.0}]
    goals: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    images: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    # 解封相关
    seal_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # 写信日期
    open_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # 解封日期
    remind_days: Mapped[int] = mapped_column(Integer, default=3)  # 提前N天开始提醒
    # 状态
    status: Mapped[str] = mapped_column(String(20), default="sealed")  # sealed/pending/opened
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 开封后的回应
    reflection: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reflection_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # AI 时光点评
    ai_review: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 使用的模板
    template_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # 元数据
    tags: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<TimeCapsuleLetter(id={self.id}, title='{self.title}', open_date='{self.open_date}')>"


class TimeCapsuleTemplate(Base):
    """信件模板表"""

    __tablename__ = "time_capsule_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # 模板标识
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    icon: Mapped[str] = mapped_column(String(10), default="✉️")
    # 模板结构：引导问题列表
    # [{"section": "回顾过去", "prompt": "过去一年最骄傲的事是什么？", "placeholder": "..."}]
    sections: Mapped[List] = mapped_column(JSON, nullable=False)
    # 预设目标建议
    suggested_goals: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)
    # 适用场景
    category: Mapped[str] = mapped_column(String(50), default="general")  # general/birthday/newyear/milestone
    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)  # 系统预设/用户自定义
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<TimeCapsuleTemplate(key='{self.key}', name='{self.name}')>"
