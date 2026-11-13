"""AI 提问队列 API"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.ai_question import AIQuestionResponse, AIQuestionAnswerRequest
from app.services.question_service import (
    list_questions, answer_question, dismiss_question, generate_proactive_questions,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai-questions", tags=["AI 提问队列"])


@router.get("", response_model=list[AIQuestionResponse])
async def list_ai_questions(
    status: Optional[str] = Query("pending", description="pending/answered/dismissed/all"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """提问列表，默认只看待答"""
    return await list_questions(db, status=None if status == "all" else status, limit=limit)


@router.get("/pending-count")
async def pending_count(db: AsyncSession = Depends(get_db)):
    """待答数量（顶栏红点用）"""
    items = await list_questions(db, status="pending", limit=100)
    return {"count": len(items)}


@router.post("/{question_id}/answer", response_model=AIQuestionResponse)
async def answer_ai_question(
    question_id: int, data: AIQuestionAnswerRequest, db: AsyncSession = Depends(get_db)
):
    """回答提问（沉淀到用户画像）"""
    try:
        return await answer_question(db, question_id, data.answer)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{question_id}/dismiss", response_model=AIQuestionResponse)
async def dismiss_ai_question(question_id: int, db: AsyncSession = Depends(get_db)):
    """忽略提问"""
    try:
        return await dismiss_question(db, question_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate", response_model=list[AIQuestionResponse])
async def generate_questions(db: AsyncSession = Depends(get_db)):
    """主动让 AI 提问（教练页「让 AI 向我提问」入口）：基于画像缺口与近期记录"""
    try:
        return await generate_proactive_questions(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"主动提问生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"生成失败: {str(e)}")
