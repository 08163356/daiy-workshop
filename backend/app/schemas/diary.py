"""日记模块的 Pydantic 模式"""

from datetime import datetime, date as DateType
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class DiaryBase(BaseModel):
    """日记基础模式"""
    date: DateType = Field(..., description="日期")
    title: str = Field(..., min_length=1, max_length=255, description="标题")
    content: str = Field(..., description="日记内容")


class DiaryCreate(DiaryBase):
    """创建日记（审核通过后提交）"""
    ai_analysis: Optional[str] = Field(None, description="AI 分析结果")
    mood: Optional[str] = Field(None, max_length=50, description="整体情绪")
    tags: Optional[list[str]] = Field(None, description="标签")
    key_issues: Optional[list[str]] = Field(None, description="关键问题")
    action_items: Optional[list[str]] = Field(None, description="行动建议")
    file_path: Optional[str] = Field(None, max_length=500, description="原始文件路径")
    images: Optional[list[str]] = Field(None, description="图片 URL")
    source: str = Field("web", description="来源：web/sync")


class DiaryResponse(DiaryBase):
    """日记响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ai_analysis: Optional[str] = None
    mood: Optional[str] = None
    tags: Optional[list[str]] = None
    key_issues: Optional[list[str]] = None
    action_items: Optional[list[str]] = None
    images: Optional[list[str]] = None
    file_path: Optional[str] = None
    source: str = "web"
    created_at: datetime
    updated_at: datetime


class DiaryListItem(BaseModel):
    """日记列表项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: DateType
    title: str
    mood: Optional[str] = None
    tags: Optional[list[str]] = None
    source: str = "web"
    created_at: datetime


class DiaryOverview(BaseModel):
    """日记系统总览"""
    total_count: int = Field(0, description="日记总数")
    mood_distribution: dict[str, int] = Field(default_factory=dict, description="情绪分布")
    tag_distribution: dict[str, int] = Field(default_factory=dict, description="标签分布")
    recent_entries: list[DiaryListItem] = Field(default_factory=list, description="最近日记")
    monthly_count: dict[str, int] = Field(default_factory=dict, description="月度统计")
