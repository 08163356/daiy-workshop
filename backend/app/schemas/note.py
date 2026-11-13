"""笔记相关的 Pydantic 模式"""

from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class NoteBase(BaseModel):
    """笔记基础模式"""

    title: str = Field(..., min_length=1, max_length=255, description="笔记标题")
    summary: Optional[str] = Field(None, description="摘要")
    source_type: str = Field("book", description="来源类型: book=读书笔记 course=课程/听课 self=个人随笔")
    course_meta: Optional[dict] = Field(None, description="课程信息: {instructor, platform}")


class NoteCreate(NoteBase):
    """创建笔记"""

    filename: str = Field(..., min_length=1, max_length=255, description="文件名")
    content: str = Field(..., min_length=1, description="内容")
    reading_date: Optional[date] = Field(None, description="阅读日期")
    file_hash: str = Field(..., description="文件哈希")


class NoteUpdate(BaseModel):
    """更新笔记"""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    reading_date: Optional[date] = None
    file_hash: Optional[str] = None
    source_type: Optional[str] = None
    course_meta: Optional[dict] = None


class ConceptBrief(BaseModel):
    """概念简要信息（用于笔记响应）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: Optional[str] = None


class NoteResponse(BaseModel):
    """笔记响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    title: str
    content: str
    summary: Optional[str] = None
    reading_date: Optional[date] = None
    word_count: int = 0
    source_type: str = "book"
    course_meta: Optional[dict] = None
    images: Optional[list] = None
    created_at: datetime
    updated_at: datetime
    concepts: list[ConceptBrief] = Field(default_factory=list, description="关联的概念")


class NoteListItem(BaseModel):
    """笔记列表项（不含完整内容）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    title: str
    summary: Optional[str] = None
    reading_date: Optional[date] = None
    word_count: int = 0
    source_type: str = "book"
    course_meta: Optional[dict] = None
    created_at: datetime
    concept_count: int = Field(0, description="关联概念数量")


class NoteListResponse(BaseModel):
    """笔记列表响应"""

    total: int = Field(..., description="总数")
    items: list[NoteListItem] = Field(default_factory=list, description="笔记列表")
