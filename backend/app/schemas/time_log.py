"""时间记录模块的 Pydantic 模式"""

from datetime import datetime, date as DateType
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class TimeLogResponse(BaseModel):
    """时间记录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    todo_id: Optional[int] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    category: Optional[str] = None
    activity_type: str = "task"
    status_label: Optional[str] = None
    status_emoji: Optional[str] = None
    created_at: datetime
    # 额外字段（关联查询时填充）
    todo_title: Optional[str] = None


class TimerStatusResponse(BaseModel):
    """当前计时状态响应"""
    is_running: bool = False
    todo_id: Optional[int] = None
    todo_title: Optional[str] = None
    todo_category: Optional[str] = None
    start_time: Optional[datetime] = None
    elapsed_seconds: int = 0
    time_log_id: Optional[int] = None
    activity_type: str = "task"
    status_label: Optional[str] = None
    status_emoji: Optional[str] = None


class StatusPreset(BaseModel):
    """预设状态"""
    label: str
    emoji: str
    color: str


class TimeStatsCategory(BaseModel):
    """按分类的时间统计"""
    category: str
    total_seconds: int = 0
    count: int = 0


class TimeDailyStats(BaseModel):
    """某一天的时间统计"""
    date: str
    total_seconds: int = 0
    categories: dict[str, int] = Field(default_factory=dict)  # category -> seconds


class TimeAnalysisResponse(BaseModel):
    """时间分析综合响应"""
    # 今日时间轴数据
    today_logs: list[TimeLogResponse] = Field(default_factory=list)
    # 按分类聚合
    category_stats: list[TimeStatsCategory] = Field(default_factory=list)
    # 今日总计
    total_seconds: int = 0
    total_tasks: int = 0
    # 最近 N 天趋势
    daily_stats: list[TimeDailyStats] = Field(default_factory=list)
