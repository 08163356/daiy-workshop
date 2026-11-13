"""篮球反思模块数据模型

三张表：
- BasketballSession: 一场打球的复盘记录（散场 pickup / 比赛 match）
- BasketballGoal: 阶段训练目标（含派单待办关联）
- BasketballSkillSnapshot: 技术维度时间序列（驱动技术进化史）
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import String, Text, Integer, DateTime, Date, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BasketballSession(Base):
    """一场打球记录（散场 / 比赛）"""

    __tablename__ = "basketball_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ---------- 基础 ----------
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # pickup / match
    duration_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    venue: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    partners_desc: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ---------- 强度 / 体感 ----------
    intensity: Mapped[int] = mapped_column(Integer, default=3)  # 1-5
    fatigue: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 轻微/中等/严重
    injury_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---------- 命中率（可选）----------
    shots_made: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shots_attempted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ---------- 反思五要素（散场 + 比赛通用）----------
    highlights: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    problems: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_moments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emotion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    one_line_summary: Mapped[str] = mapped_column(String(500), nullable=False)  # 必填

    # ---------- 比赛专属 ----------
    opponent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    matchup: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    team_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    opp_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    my_play_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    decisive_moment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    team_observation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---------- AI 产物 ----------
    coach_review: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blind_spots: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # blind_spots JSON: [{"title": "...", "evidence": "...", "repeat_count": 3}, ...]
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    async_status: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # async_status JSON: {"tech": "ok|failed", "highlights": "ok|failed", "summary": "ok|failed"}
    coach_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("ix_basketball_sessions_date_type", "date", "type"),
    )

    def __repr__(self) -> str:
        return f"<BasketballSession(id={self.id}, date={self.date}, type='{self.type}')>"


class BasketballGoal(Base):
    """阶段训练目标"""

    __tablename__ = "basketball_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    focus_area: Mapped[str] = mapped_column(String(50), nullable=False)
    # focus_area: 投篮 / 防守 / 脚步 / 体能 / 心态 / 对抗 / 其他

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # status: active / done / abandoned

    ai_evaluation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    related_todo_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    ai_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index("ix_basketball_goals_status_start", "status", "start_date"),
    )

    def __repr__(self) -> str:
        return f"<BasketballGoal(id={self.id}, focus='{self.focus_area}', status='{self.status}')>"


class BasketballSkillSnapshot(Base):
    """技术维度时间序列（每场复盘抽出 N 条，驱动技术进化史）"""

    __tablename__ = "basketball_skill_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    occurred_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    skill_dimension: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # 受 SKILL_DIMENSIONS 词表约束（20 个）
    mention_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # highlight / problem
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("ix_bb_skill_dim_date", "skill_dimension", "occurred_at"),
    )

    def __repr__(self) -> str:
        return f"<SkillSnapshot(dim='{self.skill_dimension}', type='{self.mention_type}')>"
