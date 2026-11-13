"""Agent 会话 Schema"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentSessionCreate(BaseModel):
    """创建会话"""
    ai_config_id: Optional[int] = Field(None, description="绑定模型配置 ID，空=跟随全局")


class AgentSessionRename(BaseModel):
    """改名（钉住标题）"""
    title: str = Field(..., min_length=1, max_length=100)


class AgentSessionUpdate(BaseModel):
    """更新会话（改名/切换模型绑定，至少给一个字段）"""
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    ai_config_id: Optional[int] = None


class AgentSessionResponse(BaseModel):
    """会话"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: Optional[str] = None
    title_pinned: bool = False
    ai_config_id: Optional[int] = None
    mode: str = "normal"
    status: str = "idle"
    summary: Optional[str] = None
    insights: Optional[list] = None
    followups: Optional[list] = None  # 教练跟进项（含 todo_draft 待建任务草稿）
    created_at: datetime
    updated_at: datetime


class AgentSessionDetail(BaseModel):
    """会话详情（含投影出的消息历史，供前端恢复）"""
    session: AgentSessionResponse
    messages: list[dict]


class AgentChatRequest(BaseModel):
    """对话请求"""
    session_id: Optional[int] = Field(None, description="会话 ID，空则新建")
    content: str = Field("", max_length=10000, description="用户消息；只有图片时可以空")
    images: Optional[list[str]] = Field(None, description="随消息保存的图片 URL，不送给模型分析")
    ai_config_id: Optional[int] = Field(None, description="新建会话时绑定的模型配置")
    origin_type: Optional[str] = Field(None, description="深挖入口来源: diary/note/question（仅新建会话时生效）")
    origin_id: Optional[int] = Field(None, description="来源记录 id")

    @model_validator(mode="after")
    def text_or_images(self):
        cleaned: list[str] = []
        for url in self.images or []:
            if isinstance(url, str) and url.startswith("/api/uploads/images/") and ".." not in url:
                cleaned.append(url)
        self.images = cleaned[:9] or None
        if not self.content.strip() and not self.images:
            raise ValueError("请输入文字或粘贴图片")
        return self


class AgentConfirmRequest(BaseModel):
    """写操作确认"""
    session_id: int
    approved: bool = Field(..., description="true=允许执行 false=拒绝")


class AgentVoidRequest(BaseModel):
    """撤回最后一条用户消息"""
    session_id: int


class AgentRewindRequest(BaseModel):
    """从某条用户消息起重写：作废这条和它之后的回复"""
    session_id: int
    seq: int


class AgentSteerRequest(BaseModel):
    """生成中插话"""
    session_id: int
    content: str = Field(..., min_length=1, max_length=5000)


class AgentSteerCancelRequest(BaseModel):
    """撤销排队中的插话"""
    session_id: int
    seq: int


class AgentClarifyAnswerItem(BaseModel):
    """单条澄清回答"""
    question: str = Field(..., min_length=1, max_length=500)
    answer: str = Field(..., min_length=1, max_length=2000)


class AgentClarifyRequest(BaseModel):
    """澄清提问的回答（对应 clarify_questions 事件批次）"""
    session_id: int
    batch_id: str = Field(..., min_length=1, max_length=50)
    answers: list[AgentClarifyAnswerItem] = Field(..., min_length=1)
