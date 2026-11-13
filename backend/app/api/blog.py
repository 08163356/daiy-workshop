"""个人博客检索 API（给助手工具和以后的 MCP / 调试用）"""
from fastapi import APIRouter, HTTPException, Query

from app.services.blog_search import search_blog

router = APIRouter(prefix="/blog", tags=["个人博客"])


@router.get("/search")
async def search_public_blog(
    q: str = Query(..., min_length=1, description="关键词"),
    limit: int = Query(8, ge=1, le=20),
):
    try:
        hits = search_blog(q, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"query": q, "count": len(hits), "items": hits}
