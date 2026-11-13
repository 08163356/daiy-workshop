"""知识库模块的 Pydantic 模式"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ==================== Article Schemas ====================

class ArticleBase(BaseModel):
    """知识库条目基础模式"""
    title: str = Field(..., min_length=1, max_length=500, description="标题")
    url: Optional[str] = Field(None, max_length=2000, description="URL 链接")
    content: Optional[str] = Field(None, description="文本内容")
    item_type: str = Field("article", description="条目类型: article(文章资讯) / tool(工具收藏)")
    content_type: str = Field("url", description="内容来源类型: url / text / ai_note")
    summary: Optional[str] = Field(None, description="摘要")
    tags: Optional[list[str]] = Field(None, description="标签列表")


class ArticleCreate(ArticleBase):
    """创建知识库条目"""
    source_chat_id: Optional[int] = Field(None, description="来源对话 ID（从 AI 对话保存时）")


class ArticleUpdate(BaseModel):
    """更新知识库条目"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    url: Optional[str] = Field(None, max_length=2000)
    content: Optional[str] = None
    item_type: Optional[str] = None
    content_type: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[list[str]] = None


class ArticleResponse(ArticleBase):
    """知识库条目详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    read_status: Optional[str] = None
    note_id: Optional[int] = None
    source_chat_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ArticleListItem(BaseModel):
    """知识库列表项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    url: Optional[str] = None
    item_type: str = "article"
    content_type: str = "url"
    summary: Optional[str] = None
    read_status: Optional[str] = None
    tags: Optional[list[str]] = None
    note_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# ==================== 搜索与筛选 ====================

class KBSearchParams(BaseModel):
    """知识库搜索参数"""
    keyword: Optional[str] = Field(None, description="搜索关键词")
    item_type: Optional[str] = Field(None, description="条目类型筛选: article / tool")
    tag: Optional[str] = Field(None, description="标签筛选")
    read_status: Optional[str] = Field(None, description="阅读状态筛选: unread / read")
    sort_by: str = Field("created_at", description="排序字段: created_at / updated_at / title")
    sort_order: str = Field("desc", description="排序方向: asc / desc")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


# ==================== 总览统计 ====================

class KBOverview(BaseModel):
    """知识库总览统计"""
    total_count: int = Field(0, description="总条目数")
    article_count: int = Field(0, description="文章数")
    tool_count: int = Field(0, description="工具数")
    unread_count: int = Field(0, description="未读文章数")
    read_count: int = Field(0, description="已读文章数")
    tag_count: int = Field(0, description="标签总数")
    recent_articles: list[ArticleListItem] = Field(default_factory=list, description="最近收集")
    popular_tags: list[dict] = Field(default_factory=list, description="热门标签")


# ==================== 标签 ====================

class TagInfo(BaseModel):
    """标签信息"""
    name: str = Field(..., description="标签名")
    count: int = Field(0, description="使用次数")


# ==================== 操作 ====================

class ReadStatusUpdate(BaseModel):
    """阅读状态更新"""
    read_status: str = Field(..., description="阅读状态: unread / read")


class BatchReadStatusUpdate(BaseModel):
    """批量阅读状态更新"""
    ids: list[int] = Field(..., description="条目 ID 列表")
    read_status: str = Field(..., description="阅读状态: unread / read")


class ArticleToTodoRequest(BaseModel):
    """文章转待办请求"""
    title: Optional[str] = Field(None, description="待办标题（不填则用文章标题）")
    description: Optional[str] = Field(None, description="待办描述")
    due_date: Optional[str] = Field(None, description="截止日期 YYYY-MM-DD")


# ==================== 分页响应 ====================

class PaginatedArticleResponse(BaseModel):
    """分页文章列表响应"""
    items: list[ArticleListItem] = Field(default_factory=list, description="条目列表")
    total: int = Field(0, description="总数")
    page: int = Field(1, description="当前页")
    page_size: int = Field(20, description="每页数量")
    total_pages: int = Field(0, description="总页数")


# ==================== 模块模型配置 ====================

class ModuleModelConfigSchema(BaseModel):
    """模块模型配置"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    module_name: str
    ai_config_id: int
    created_at: datetime
    updated_at: datetime


class ModuleModelConfigUpdate(BaseModel):
    """更新模块模型配置"""
    ai_config_id: int = Field(..., description="AI 配置 ID")


class ModuleModelConfigResponse(BaseModel):
    """模块模型配置响应（带模型名称）"""
    module_name: str = Field(..., description="模块名")
    ai_config_id: Optional[int] = Field(None, description="绑定的 AI 配置 ID")
    ai_config_name: Optional[str] = Field(None, description="绑定的 AI 配置名称")
    model_name: Optional[str] = Field(None, description="模型名称")
    provider: Optional[str] = Field(None, description="提供商")


class AllModuleConfigsResponse(BaseModel):
    """所有模块配置响应"""
    modules: list[ModuleModelConfigResponse] = Field(
        default_factory=list, description="各模块配置列表"
    )
    available_models: list[dict] = Field(
        default_factory=list, description="可选模型列表"
    )
