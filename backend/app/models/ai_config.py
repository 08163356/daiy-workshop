"""AI 配置与用户画像数据模型"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, JSON, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AIConfig(Base):
    """AI 模型配置表"""

    __tablename__ = "ai_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)  # 配置名称
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # 提供商：openai/deepseek/moonshot/custom
    api_key: Mapped[str] = mapped_column(String(500), nullable=False)  # API Key
    api_base: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # 自定义 API 地址
    model: Mapped[str] = mapped_column(String(100), nullable=False)  # 模型名称
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否为当前使用的配置
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<AIConfig(id={self.id}, name='{self.name}', provider='{self.provider}')>"


class UserProfile(Base):
    """用户画像表 - 记录用户的关键特征，AI 分析时携带"""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # 分类：基本信息/性格特征/职业发展/投资风格/学习偏好/情绪模式/核心关注/成长目标
    key: Mapped[str] = mapped_column(String(200), nullable=False)  # 特征键
    value: Mapped[str] = mapped_column(Text, nullable=False)  # 特征值
    confidence: Mapped[float] = mapped_column(Float, default=0.5)  # 置信度 0-1，多次验证后提高
    source_count: Mapped[int] = mapped_column(Integer, default=1)  # 来源数量（被多少篇分析佐证）
    last_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 最近一次的佐证内容
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<UserProfile(category='{self.category}', key='{self.key}')>"


class ProfileDistillRun(Base):
    """用户画像蒸馏运行记录 - 周期性综合复盘的最小实现"""

    __tablename__ = "profile_distill_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # 数据来源统计: {"diary_count":n,"todo_completed":n,"wellbeing_count":n,"wish_log_count":n}
    sources_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    profile_updates: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # update_user_profile 返回的结果列表
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI 一句话总结
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<ProfileDistillRun(id={self.id}, created_at='{self.created_at}')>"


class ConversationLog(Base):
    """对话日志表 - 记录每次与 AI 的对话"""

    __tablename__ = "conversation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    system_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 系统类型：investment/reading/diary/auto
    user_input: Mapped[str] = mapped_column(Text, nullable=False)  # 用户输入
    ai_response: Mapped[str] = mapped_column(Text, nullable=False)  # AI 完整响应
    detected_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # AI 自动检测的类型
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 使用的模型
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 消耗的 token 数
    profile_updates: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 本次画像更新
    data_saved: Mapped[Optional[List]] = mapped_column(JSON, nullable=True)  # 本次保存的数据摘要
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<ConversationLog(id={self.id}, type='{self.system_type}')>"
