"""心力模块的 Pydantic 模式"""

from datetime import datetime, date as DateType
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


# ---------- 条目（Entry）----------

class WellbeingEntryBase(BaseModel):
    type: str = Field(..., description="achievement / gratitude")
    content: str = Field(..., min_length=1, description="主体内容")
    category: Optional[str] = Field(None, max_length=50, description="分类")
    intensity: int = Field(3, ge=1, le=5, description="强度 1-5")
    occurred_at: DateType = Field(..., description="发生日期")
    mood_tag: Optional[str] = Field(None, max_length=50)
    image_url: Optional[str] = Field(None, max_length=500)
    ai_tags: Optional[list[str]] = None


class WellbeingEntryCreate(WellbeingEntryBase):
    source_type: str = Field("manual", description="manual / diary / note / todo / candidate")
    source_id: Optional[int] = None


class WellbeingEntryUpdate(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    intensity: Optional[int] = Field(None, ge=1, le=5)
    occurred_at: Optional[DateType] = None
    mood_tag: Optional[str] = None
    image_url: Optional[str] = None
    ai_tags: Optional[list[str]] = None


class WellbeingEntryResponse(WellbeingEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    source_id: Optional[int] = None
    source_excerpt: Optional[str] = None
    ai_reason: Optional[str] = None   # AI 识别理由（候选采纳时保留）
    created_at: datetime
    updated_at: datetime


# ---------- 候选（Candidate）----------

class WellbeingCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    source_id: int
    source_excerpt: Optional[str] = None
    suggested_type: str
    suggested_content: str
    suggested_category: Optional[str] = None
    suggested_intensity: int = 3
    suggested_tags: Optional[list[str]] = None
    ai_confidence: float = 0.5
    ai_reason: Optional[str] = None
    status: str = "pending"
    reviewed_at: Optional[datetime] = None
    accepted_entry_id: Optional[int] = None
    created_at: datetime


class CandidateReviewAction(BaseModel):
    action: str = Field(..., description="accept / reject")
    # accept 时可选地覆盖 AI 建议
    content: Optional[str] = None
    category: Optional[str] = None
    intensity: Optional[int] = Field(None, ge=1, le=5)
    occurred_at: Optional[DateType] = None


# ---------- 报告（Report）----------

class WellbeingReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_type: str
    period_key: str
    period_start: DateType
    period_end: DateType
    content: str
    structured_data: Optional[dict] = None
    achievement_count: int = 0
    gratitude_count: int = 0
    model_used: Optional[str] = None
    tokens_used: int = 0
    generated_at: datetime


# ---------- 安抚卡（Comfort）----------

class ComfortCardEntry(BaseModel):
    id: int
    type: str
    content: str
    category: Optional[str] = None
    intensity: int = 3
    occurred_at: DateType


class ComfortCardResponse(BaseModel):
    soothing_message: str = Field(..., description="AI 个性化安抚语")
    achievements: list[ComfortCardEntry] = Field(default_factory=list)
    gratitudes: list[ComfortCardEntry] = Field(default_factory=list)
    fallback: bool = Field(False, description="是否使用了降级文案")


# ---------- 总览看板（Dashboard）----------

class TrendPoint(BaseModel):
    date: DateType
    achievement: int = 0
    gratitude: int = 0


class CategoryStat(BaseModel):
    category: str
    count: int
    avg_intensity: float = 0.0


class WellbeingOverviewResponse(BaseModel):
    total_achievement: int = 0
    total_gratitude: int = 0
    week_new: int = 0
    streak_days: int = 0
    trend_90d: list[TrendPoint] = Field(default_factory=list)
    category_distribution: list[CategoryStat] = Field(default_factory=list)
    intensity_radar: dict[str, float] = Field(default_factory=dict)
    pending_candidates: int = 0
    insight: Optional[str] = None  # AI 关联洞察一句话


# ---------- 关联分析（Insights）----------

class CorrelationItem(BaseModel):
    label: str
    score: float = 0.0
    note: Optional[str] = None


class WellbeingInsightsResponse(BaseModel):
    summary: str
    correlations: list[CorrelationItem] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


# ---------- 列表 ----------

class WellbeingListResponse(BaseModel):
    total: int
    items: list[WellbeingEntryResponse]
