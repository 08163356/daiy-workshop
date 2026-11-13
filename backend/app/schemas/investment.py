"""投资模块的 Pydantic 模式"""

from datetime import datetime, date as DateType
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ==================== 反思记录 ====================

class ReflectionBase(BaseModel):
    """反思记录基础模式"""
    date: DateType = Field(..., description="日期")
    title: str = Field(..., min_length=1, max_length=255, description="标题")
    content: str = Field(..., description="原始内容")


class ReflectionCreate(ReflectionBase):
    """创建反思记录"""
    ai_analysis: Optional[str] = Field(None, description="AI 分析结果")
    key_points: Optional[list[str]] = Field(None, description="关键点列表")
    file_path: Optional[str] = Field(None, max_length=500, description="原始文件路径")


class ReflectionResponse(ReflectionBase):
    """反思记录响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    ai_analysis: Optional[str] = None
    key_points: Optional[list[str]] = None
    file_path: Optional[str] = None
    created_at: datetime


class ReflectionListItem(BaseModel):
    """反思记录列表项"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    date: DateType
    title: str
    key_points: Optional[list[str]] = None
    created_at: datetime


# ==================== 投资原则 ====================

class PrincipleBase(BaseModel):
    """投资原则基础模式"""
    title: str = Field(..., min_length=1, max_length=255, description="原则标题")
    content: str = Field(..., description="原则内容")
    category: str = Field(..., description="分类：风险管理/仓位管理/心态管理/择时策略/选标策略")


class PrincipleCreate(PrincipleBase):
    """创建投资原则"""
    source_reflection_id: Optional[int] = Field(None, description="来源反思 ID")


class PrincipleUpdate(BaseModel):
    """更新投资原则"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class PrincipleResponse(PrincipleBase):
    """投资原则响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    source_reflection_id: Optional[int] = None
    version: int = 1
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class PrincipleListItem(BaseModel):
    """投资原则列表项"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    title: str
    category: str
    version: int
    is_active: bool


# ==================== 认知迭代 ====================

class CognitionBase(BaseModel):
    """认知迭代基础模式"""
    date: DateType = Field(..., description="日期")
    old_cognition: str = Field(..., description="旧认知")
    new_cognition: str = Field(..., description="新认知")
    trigger: str = Field(..., description="触发事件")


class CognitionCreate(CognitionBase):
    """创建认知迭代"""
    category: Optional[str] = Field(None, description="分类")
    related_principle_id: Optional[int] = Field(None, description="关联原则 ID")


class CognitionResponse(CognitionBase):
    """认知迭代响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    category: Optional[str] = None
    related_principle_id: Optional[int] = None
    created_at: datetime


# ==================== 决策日志 ====================

class DecisionBase(BaseModel):
    """决策日志基础模式"""
    date: DateType = Field(..., description="决策日期")
    action: str = Field(..., description="操作类型：买入/卖出/持有/观望")
    target: str = Field(..., max_length=100, description="标的")
    logic: str = Field(..., description="决策逻辑")


class DecisionCreate(DecisionBase):
    """创建决策日志"""
    emotion_state: Optional[str] = Field(None, description="情绪状态")
    position_percent: Optional[float] = Field(None, ge=0, le=100, description="仓位百分比")


class DecisionUpdate(BaseModel):
    """更新决策日志（复盘）"""
    result: Optional[str] = Field(None, description="结果复盘")
    lesson: Optional[str] = Field(None, description="经验教训")


class DecisionResponse(DecisionBase):
    """决策日志响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    emotion_state: Optional[str] = None
    position_percent: Optional[float] = None
    result: Optional[str] = None
    lesson: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ==================== 情绪复盘 ====================

class EmotionBase(BaseModel):
    """情绪复盘基础模式"""
    date: DateType = Field(..., description="日期")
    emotion: str = Field(..., max_length=50, description="情绪类型")
    trigger: str = Field(..., description="触发因素")


class EmotionCreate(EmotionBase):
    """创建情绪复盘"""
    impact: Optional[str] = Field(None, description="对决策的影响")
    coping_strategy: Optional[str] = Field(None, description="应对策略")
    effectiveness: Optional[int] = Field(None, ge=1, le=5, description="策略有效性")


class EmotionResponse(EmotionBase):
    """情绪复盘响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    impact: Optional[str] = None
    coping_strategy: Optional[str] = None
    effectiveness: Optional[int] = None
    created_at: datetime


# ==================== 投资知识 ====================

class KnowledgeBase(BaseModel):
    """投资知识基础模式"""
    name: str = Field(..., min_length=1, max_length=255, description="知识点名称")
    description: str = Field(..., description="描述")
    category: str = Field(..., description="分类")


class KnowledgeCreate(KnowledgeBase):
    """创建投资知识"""
    source: Optional[str] = Field(None, max_length=255, description="来源")


class KnowledgeResponse(KnowledgeBase):
    """投资知识响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    source: Optional[str] = None
    created_at: datetime


# ==================== Q&A 问答 ====================

class QABase(BaseModel):
    """Q&A 基础模式"""
    question: str = Field(..., description="问题")
    answer: str = Field(..., description="AI 解答")


class QACreate(QABase):
    """创建 Q&A"""
    date: DateType = Field(..., description="日期")
    category: Optional[str] = Field(None, description="分类")
    source_reflection_id: Optional[int] = Field(None, description="来源反思 ID")
    source_type: str = Field("auto", description="识别方式：auto/explicit")
    tags: Optional[list[str]] = Field(None, description="标签")


class QAUpdate(BaseModel):
    """更新 Q&A"""
    answer: Optional[str] = Field(None, description="更新解答")
    category: Optional[str] = Field(None, description="更新分类")
    is_resolved: Optional[bool] = Field(None, description="是否已解答")
    follow_up: Optional[str] = Field(None, description="后续追问")
    tags: Optional[list[str]] = Field(None, description="更新标签")


class QAResponse(QABase):
    """Q&A 响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    date: DateType
    category: Optional[str] = None
    source_reflection_id: Optional[int] = None
    source_type: str = "auto"
    tags: Optional[list[str]] = None
    is_resolved: bool = True
    follow_up: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class QAListItem(BaseModel):
    """Q&A 列表项"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    date: DateType
    question: str
    category: Optional[str] = None
    is_resolved: bool = True
    tags: Optional[list[str]] = None


# ==================== 总览数据 ====================

class InvestmentOverview(BaseModel):
    """投资系统总览"""
    reflection_count: int = Field(0, description="反思记录数")
    principle_count: int = Field(0, description="投资原则数")
    cognition_count: int = Field(0, description="认知迭代次数")
    decision_count: int = Field(0, description="决策记录数")
    emotion_count: int = Field(0, description="情绪记录数")
    knowledge_count: int = Field(0, description="知识点数")
    qa_count: int = Field(0, description="问答数")
    
    # 分类统计
    principles_by_category: dict[str, int] = Field(default_factory=dict)
    emotions_by_type: dict[str, int] = Field(default_factory=dict)
    decisions_by_action: dict[str, int] = Field(default_factory=dict)
    qa_by_category: dict[str, int] = Field(default_factory=dict)
    
    # 最近数据
    recent_principles: list[PrincipleListItem] = Field(default_factory=list)
    recent_cognitions: list[CognitionResponse] = Field(default_factory=list)
    recent_qa: list[QAListItem] = Field(default_factory=list)


# ==================== 通用响应 ====================

class ListResponse(BaseModel):
    """通用列表响应"""
    total: int = Field(..., description="总数")
    items: list = Field(default_factory=list, description="数据列表")
