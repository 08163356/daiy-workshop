"""投资模块数据模型"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, Date, Boolean, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InvestmentReflection(Base):
    """投资反思记录表"""

    __tablename__ = "investment_reflections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 原始内容
    ai_analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI 分析结果
    key_points: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 关键点列表
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # 原始文件路径
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<InvestmentReflection(id={self.id}, date='{self.date}', title='{self.title}')>"


class InvestmentPrinciple(Base):
    """投资原则表"""

    __tablename__ = "investment_principles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # 分类：风险管理、仓位管理、心态管理、择时策略、选标策略
    source_reflection_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 来源反思 ID
    version: Mapped[int] = mapped_column(Integer, default=1)  # 版本号
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否当前有效
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<InvestmentPrinciple(id={self.id}, title='{self.title}')>"


class InvestmentCognition(Base):
    """认知迭代表"""

    __tablename__ = "investment_cognitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    old_cognition: Mapped[str] = mapped_column(Text, nullable=False)
    new_cognition: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)  # 触发事件
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # 分类：宏观经济、行为金融、技术分析、风险管理
    related_principle_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 关联原则 ID
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<InvestmentCognition(id={self.id}, date='{self.date}')>"


class InvestmentDecision(Base):
    """决策日志表"""

    __tablename__ = "investment_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # 买入/卖出/持有/观望
    target: Mapped[str] = mapped_column(String(100), nullable=False)  # 标的
    logic: Mapped[str] = mapped_column(Text, nullable=False)  # 决策逻辑
    emotion_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # 情绪状态：冷静/焦虑/贪婪/恐惧/FOMO
    position_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 仓位百分比
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 结果复盘
    lesson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 经验教训
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<InvestmentDecision(id={self.id}, date='{self.date}', action='{self.action}')>"


class InvestmentEmotion(Base):
    """情绪复盘表"""

    __tablename__ = "investment_emotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    emotion: Mapped[str] = mapped_column(String(50), nullable=False)  # 情绪类型
    trigger: Mapped[str] = mapped_column(Text, nullable=False)  # 触发因素
    impact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 对决策的影响
    coping_strategy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 应对策略
    effectiveness: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 策略有效性 1-5
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<InvestmentEmotion(id={self.id}, date='{self.date}', emotion='{self.emotion}')>"


class InvestmentKnowledge(Base):
    """投资知识表"""

    __tablename__ = "investment_knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # 分类：宏观经济、行为金融、技术分析、基本面分析、量化策略
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # 来源
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<InvestmentKnowledge(id={self.id}, name='{self.name}')>"


class InvestmentQA(Base):
    """投资问答表"""

    __tablename__ = "investment_qa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)  # 问题
    answer: Mapped[str] = mapped_column(Text, nullable=False)  # AI 解答
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    # 分类：宏观经济、技术分析、投资策略、风险管理、心理情绪、市场观察
    source_reflection_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 来源反思 ID
    source_type: Mapped[str] = mapped_column(String(50), default="auto")  # 识别方式：auto/explicit
    tags: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 标签
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否已解答
    follow_up: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 后续追问
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<InvestmentQA(id={self.id}, question='{self.question[:30]}...')>"
