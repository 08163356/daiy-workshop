"""AI 配置与对话模块的 Pydantic 模式"""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ==================== AI 配置 ====================

class AIConfigBase(BaseModel):
    """AI 配置基础模式"""
    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    provider: str = Field(..., description="提供商：openai/deepseek/moonshot/zhipu/qwen/custom")
    api_key: str = Field(..., min_length=1, description="API Key")
    api_base: Optional[str] = Field(None, description="自定义 API 地址")
    model: str = Field(..., description="模型名称")
    temperature: float = Field(0.7, ge=0, le=2, description="温度")
    max_tokens: int = Field(4096, ge=256, le=32768, description="最大 token 数")


class AIConfigCreate(AIConfigBase):
    """创建 AI 配置"""
    is_active: bool = Field(True, description="是否为当前使用的配置")


class AIConfigUpdate(BaseModel):
    """更新 AI 配置"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    provider: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, ge=256, le=32768)
    is_active: Optional[bool] = None


class AIConfigResponse(AIConfigBase):
    """AI 配置响应（隐藏 API Key）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    api_key: str = Field(exclude=True)  # 不返回完整 key

    def model_post_init(self, __context) -> None:
        """隐藏 API Key，只显示前8位和后4位"""
        if self.api_key and len(self.api_key) > 12:
            object.__setattr__(self, 'api_key_masked', f"{self.api_key[:8]}...{self.api_key[-4:]}")
        else:
            object.__setattr__(self, 'api_key_masked', "***")


class AIConfigListResponse(BaseModel):
    """AI 配置列表响应（带掩码 Key）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    provider: str
    model: str
    api_base: Optional[str] = None
    temperature: float
    max_tokens: int
    is_active: bool
    api_key_masked: str = ""
    created_at: datetime
    updated_at: datetime


# ==================== 用户画像 ====================

class UserProfileItem(BaseModel):
    """用户画像项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    key: str
    value: str
    confidence: float
    source_count: int
    last_evidence: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(BaseModel):
    """手动更新用户画像"""
    category: str = Field(..., description="分类")
    key: str = Field(..., description="特征键")
    value: str = Field(..., description="特征值")


# ==================== 统一对话 ====================

class ChatRequest(BaseModel):
    """统一对话请求"""
    content: str = Field(..., min_length=1, description="用户输入内容")
    system_type: str = Field("auto", description="系统类型：investment/reading/diary/auto")
    title: Optional[str] = Field(None, description="标题（可选，不填则 AI 自动生成）")
    diary_date: Optional[date] = Field(None, description="日记任务参考日期，默认今天")


class ChatAnalysisResult(BaseModel):
    """AI 分析结果（预览，未入库）"""
    system_type: str = Field(..., description="实际使用的系统类型")
    detected_types: list[str] = Field(default_factory=list, description="AI 检测到的所有类型")
    original_content: str = Field(..., description="原始输入")
    analysis_markdown: str = Field(..., description="AI 分析报告（Markdown）")
    structured_data: dict = Field(default_factory=dict, description="结构化数据")
    profile_updates: list[dict] = Field(default_factory=list, description="画像更新建议")
    tokens_used: int = Field(0, description="消耗 token 数")


class ChatSaveRequest(BaseModel):
    """审核通过后保存数据的请求"""
    system_type: str = Field(..., description="系统类型")
    title: str = Field(..., description="标题")
    original_content: str = Field(..., description="原始内容")
    analysis_markdown: str = Field(..., description="AI 分析报告")
    structured_data: dict = Field(default_factory=dict, description="结构化数据")
    profile_updates: list[dict] = Field(default_factory=list, description="画像更新")
    save_to_types: Optional[list[str]] = Field(None, description="保存到哪些系统（多类型时）")
    images: Optional[list[str]] = Field(None, description="图片URL列表")


class ChatSaveResponse(BaseModel):
    """保存结果"""
    success: bool
    message: str
    saved_items: dict = Field(default_factory=dict, description="各系统保存的数据 ID")
    profile_updated: list[dict] = Field(default_factory=list, description="更新的画像项")


# ==================== 对话日志 ====================

class ConversationLogResponse(BaseModel):
    """对话日志响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    system_type: str
    user_input: str
    ai_response: str
    detected_type: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    created_at: datetime
