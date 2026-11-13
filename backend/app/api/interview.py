"""interview 作品集/面试材料检索 API（助手 search_interview / 调试）"""
from fastapi import APIRouter, HTTPException, Query

from app.services.interview_search import search_interview

router = APIRouter(prefix="/interview", tags=["interview"])


@router.get("/search")
async def search_interview_materials(
    q: str = Query(..., min_length=1, description="关键词"),
    limit: int = Query(8, ge=1, le=20),
):
    try:
        hits = search_interview(q, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"query": q, "count": len(hits), "items": hits}
