"""AI 提问队列 Schema"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AIQuestionResponse(BaseModel):
    """提问队列项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    source_id: Optional[int] = None
    question: str
    context: Optional[str] = None
    status: str = "pending"
    answer: Optional[str] = None
    created_at: datetime
    answered_at: Optional[datetime] = None


class AIQuestionAnswerRequest(BaseModel):
    """回答提问"""
    answer: str = Field(..., min_length=1, max_length=2000, description="回答内容")
