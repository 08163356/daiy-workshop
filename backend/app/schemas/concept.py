"""概念相关的 Pydantic 模式"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ConceptBase(BaseModel):
    """概念基础模式"""

    name: str = Field(..., min_length=1, max_length=255, description="概念名称")
    description: Optional[str] = Field(None, description="描述")
    category: Optional[str] = Field(None, max_length=100, description="分类")


class ConceptCreate(ConceptBase):
    """创建概念"""

    importance: int = Field(1, ge=1, le=5, description="重要程度")


class ConceptUpdate(BaseModel):
    """更新概念"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    importance: Optional[int] = Field(None, ge=1, le=5)


class RelatedNote(BaseModel):
    """关联笔记简要信息"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    filename: str


class RelatedConcept(BaseModel):
    """关联概念（用于概念详情）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    relation_type: str
    strength: float


class ConceptResponse(BaseModel):
    """概念响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    importance: int = 1
    mention_count: int = 0
    created_at: datetime
    related_notes: list[RelatedNote] = Field(default_factory=list, description="关联笔记")
    related_concepts: list[RelatedConcept] = Field(default_factory=list, description="关联概念")


class ConceptListItem(BaseModel):
    """概念列表项"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: Optional[str] = None
    importance: int = 1
    mention_count: int = 0


class ConceptListResponse(BaseModel):
    """概念列表响应"""

    total: int = Field(..., description="总数")
    items: list[ConceptListItem] = Field(default_factory=list, description="概念列表")
