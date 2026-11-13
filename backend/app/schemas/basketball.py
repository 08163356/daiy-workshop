"""篮球反思模块的 Pydantic schema"""
from __future__ import annotations

from datetime import datetime, date as DateType
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


# ==================== Session ====================

class SessionBase(BaseModel):
    """复盘基础字段"""
    date: DateType
    type: str = Field("pickup", description="pickup 散场 | match 比赛")
    duration_min: Optional[int] = Field(None, ge=1, le=600)
    venue: Optional[str] = None
    partners_desc: Optional[str] = None

    intensity: int = Field(3, ge=1, le=5)
    fatigue: Optional[str] = None
    injury_note: Optional[str] = None

    shots_made: Optional[int] = Field(None, ge=0)
    shots_attempted: Optional[int] = Field(None, ge=0)

    highlights: Optional[str] = None
    problems: Optional[str] = None
    key_moments: Optional[str] = None
    emotion: Optional[str] = None
    one_line_summary: str = Field(..., min_length=1, max_length=500)

    # 比赛字段
    opponent: Optional[str] = None
    matchup: Optional[str] = None
    team_score: Optional[int] = None
    opp_score: Optional[int] = None
    my_play_minutes: Optional[int] = Field(None, ge=0, le=120)
    decisive_moment: Optional[str] = None
    team_observation: Optional[str] = None


class SessionCreate(SessionBase):
    pass


class SessionUpdate(BaseModel):
    """允许部分更新"""
    duration_min: Optional[int] = None
    venue: Optional[str] = None
    partners_desc: Optional[str] = None
    intensity: Optional[int] = Field(None, ge=1, le=5)
    fatigue: Optional[str] = None
    injury_note: Optional[str] = None
    shots_made: Optional[int] = None
    shots_attempted: Optional[int] = None
    highlights: Optional[str] = None
    problems: Optional[str] = None
    key_moments: Optional[str] = None
    emotion: Optional[str] = None
    one_line_summary: Optional[str] = None
    opponent: Optional[str] = None
    matchup: Optional[str] = None
    team_score: Optional[int] = None
    opp_score: Optional[int] = None
    my_play_minutes: Optional[int] = None
    decisive_moment: Optional[str] = None
    team_observation: Optional[str] = None


class BlindSpot(BaseModel):
    title: str
    evidence: Optional[str] = None
    repeat_count: int = 1


class SessionResponse(SessionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    coach_review: Optional[str] = None
    blind_spots: Optional[list[dict]] = None
    ai_summary: Optional[str] = None
    async_status: Optional[dict] = None
    coach_model: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SessionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    date: DateType
    type: str
    duration_min: Optional[int] = None
    intensity: int = 3
    one_line_summary: str
    shots_made: Optional[int] = None
    shots_attempted: Optional[int] = None
    coach_review: Optional[str] = None  # 列表只回首句，前端裁剪
    created_at: datetime


# ==================== Skill ====================

class SkillSnapshotItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int
    occurred_at: DateType
    skill_dimension: str
    mention_type: str  # highlight / problem
    extracted_text: Optional[str] = None


class SkillHistoryResponse(BaseModel):
    """按维度 + 周聚合的历史"""
    dimensions: list[str]  # 20 词表
    timeline: list[dict]
    # timeline: [{week_key: "2026-W23", date_start, date_end, points: [{dim, problem, highlight}]}]
    top_progress: list[dict]  # 进步 Top
    top_regress: list[dict]   # 倒退 Top


# ==================== Goals ====================

class GoalCreate(BaseModel):
    title: str
    description: Optional[str] = None
    focus_area: str
    start_date: DateType
    end_date: DateType


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: Optional[str] = None
    focus_area: str
    start_date: DateType
    end_date: DateType
    status: str
    ai_evaluation: Optional[str] = None
    related_todo_ids: Optional[list[int]] = None
    ai_model: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StageGoalGenerateRequest(BaseModel):
    weeks: int = Field(2, ge=1, le=8, description="阶段长度（周）")
    create_todos: bool = Field(True, description="是否自动创建训练待办")


class StageGoalGenerateResponse(BaseModel):
    goal: GoalResponse
    todos_created: int
    summary: str  # AI 生成时的解释


class GoalEvaluateResponse(BaseModel):
    goal: GoalResponse
    summary: str


# ==================== Dashboard ====================

class DashboardOverview(BaseModel):
    month_session_count: int = 0
    month_total_minutes: int = 0
    avg_shooting_rate: Optional[float] = None  # 0.0 - 1.0
    streak_days: int = 0
    active_goal: Optional[GoalResponse] = None
    active_goal_progress: Optional[dict] = None
    # active_goal_progress: {todos_total, todos_done, days_passed, days_total}
    recent_sessions: list[SessionListItem] = []


# ==================== Recent (供 diary-analyzer 使用) ====================

class RecentBasketballResponse(BaseModel):
    days: int = 7
    session_count: int = 0
    avg_intensity: Optional[float] = None
    avg_shooting_rate: Optional[float] = None
    emotions_keywords: list[str] = []
    last_session_date: Optional[DateType] = None
    last_one_line: Optional[str] = None
