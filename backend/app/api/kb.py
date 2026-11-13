"""知识库模块 API"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.article import Article
from app.models.module_model_config import ModuleModelConfig
from app.models.ai_config import AIConfig
from app.schemas.article import (
    ArticleCreate, ArticleUpdate, ArticleResponse, ArticleListItem,
    KBSearchParams, KBOverview, TagInfo,
    PaginatedArticleResponse, ReadStatusUpdate, BatchReadStatusUpdate,
    ArticleToTodoRequest,
    ModuleModelConfigUpdate, ModuleModelConfigResponse, AllModuleConfigsResponse,
)
from app.schemas.todo import TodoResponse
from app.services import kb_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kb", tags=["知识库模块"])

# 所有支持模块模型配置的模块名称
ALL_MODULES = [
    {"name": "agent", "label": "AI 助手对话"},
    {"name": "diary", "label": "日记分析"},
    {"name": "reading", "label": "读书笔记"},
    {"name": "investment", "label": "投资分析"},
    {"name": "todo", "label": "待办评估"},
    {"name": "kb", "label": "知识库"},
    {"name": "note", "label": "随笔分析"},
    {"name": "auto_classify", "label": "智能分类"},
    {"name": "wellbeing", "label": "心力分析"},
    {"name": "coaching", "label": "教练对话"},
]


# ==================== 总览 ====================

@router.get("/overview", response_model=KBOverview)
async def get_overview(db: AsyncSession = Depends(get_db)):
    """获取知识库总览统计"""
    return await kb_service.get_overview(db)


# ==================== 标签 ====================

@router.get("/tags", response_model=list[TagInfo])
async def get_tags(db: AsyncSession = Depends(get_db)):
    """获取所有标签列表"""
    return await kb_service.get_all_tags(db)


# ==================== 搜索 ====================

@router.get("/search", response_model=PaginatedArticleResponse)
async def search_articles(
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    item_type: Optional[str] = Query(None, description="类型: article/tool"),
    tag: Optional[str] = Query(None, description="标签筛选"),
    read_status: Optional[str] = Query(None, description="阅读状态: unread/read"),
    sort_by: str = Query("created_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
):
    """搜索知识库条目"""
    params = KBSearchParams(
        keyword=keyword,
        item_type=item_type,
        tag=tag,
        read_status=read_status,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return await kb_service.list_articles(db, params)


# ==================== 批量操作 ====================

@router.patch("/batch-read-status")
async def batch_update_read_status(
    data: BatchReadStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """批量更新阅读状态"""
    count = await kb_service.batch_update_read_status(db, data)
    return {"message": f"已更新 {count} 条记录", "updated_count": count}


# ==================== CRUD ====================

@router.get("", response_model=PaginatedArticleResponse)
async def list_articles(
    keyword: Optional[str] = Query(None),
    item_type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    read_status: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取知识库列表"""
    params = KBSearchParams(
        keyword=keyword,
        item_type=item_type,
        tag=tag,
        read_status=read_status,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return await kb_service.list_articles(db, params)


@router.post("", response_model=ArticleResponse)
async def create_article(
    data: ArticleCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建知识库条目"""
    article = await kb_service.create_article(db, data)
    return ArticleResponse.model_validate(article)


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(article_id: int, db: AsyncSession = Depends(get_db)):
    """获取知识库条目详情"""
    article = await kb_service.get_article(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="知识库条目不存在")
    return ArticleResponse.model_validate(article)


@router.put("/{article_id}", response_model=ArticleResponse)
async def update_article(
    article_id: int,
    data: ArticleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新知识库条目"""
    article = await kb_service.update_article(db, article_id, data)
    if not article:
        raise HTTPException(status_code=404, detail="知识库条目不存在")
    return ArticleResponse.model_validate(article)


@router.delete("/{article_id}")
async def delete_article(article_id: int, db: AsyncSession = Depends(get_db)):
    """删除知识库条目"""
    success = await kb_service.delete_article(db, article_id)
    if not success:
        raise HTTPException(status_code=404, detail="知识库条目不存在")
    return {"message": "删除成功"}


# ==================== 阅读状态 ====================

@router.patch("/{article_id}/read-status", response_model=ArticleResponse)
async def update_read_status(
    article_id: int,
    data: ReadStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新阅读状态"""
    article = await kb_service.update_read_status(db, article_id, data.read_status)
    if not article:
        raise HTTPException(status_code=404, detail="知识库条目不存在")
    return ArticleResponse.model_validate(article)


# ==================== 转待办 ====================

@router.post("/{article_id}/to-todo", response_model=TodoResponse)
async def article_to_todo(
    article_id: int,
    data: ArticleToTodoRequest = ArticleToTodoRequest(),
    db: AsyncSession = Depends(get_db),
):
    """将知识库文章转为待办"""
    todo = await kb_service.article_to_todo(db, article_id, data)
    if not todo:
        raise HTTPException(status_code=404, detail="知识库条目不存在")
    return TodoResponse.model_validate(todo)


# ==================== 关联笔记 ====================

@router.patch("/{article_id}/link-note", response_model=ArticleResponse)
async def link_note(
    article_id: int,
    note_id: int = Query(..., description="笔记 ID"),
    db: AsyncSession = Depends(get_db),
):
    """关联读后笔记"""
    article = await kb_service.link_note(db, article_id, note_id)
    if not article:
        raise HTTPException(status_code=404, detail="知识库条目不存在")
    return ArticleResponse.model_validate(article)


# ==================== 模块模型配置 ====================

@router.get("/module-configs", response_model=AllModuleConfigsResponse)
async def get_module_configs(db: AsyncSession = Depends(get_db)):
    """获取所有模块的模型配置"""
    # 获取所有已配置的模块绑定
    result = await db.execute(select(ModuleModelConfig))
    configs = {c.module_name: c for c in result.scalars().all()}

    # 获取所有可用模型
    models_result = await db.execute(select(AIConfig))
    all_models = models_result.scalars().all()

    # 构建模块配置列表
    modules = []
    for mod in ALL_MODULES:
        config = configs.get(mod["name"])
        if config:
            # 找到绑定的模型信息
            bound_model = next(
                (m for m in all_models if m.id == config.ai_config_id), None
            )
            modules.append(ModuleModelConfigResponse(
                module_name=mod["name"],
                ai_config_id=config.ai_config_id,
                ai_config_name=bound_model.name if bound_model else None,
                model_name=bound_model.model if bound_model else None,
                provider=bound_model.provider if bound_model else None,
            ))
        else:
            modules.append(ModuleModelConfigResponse(
                module_name=mod["name"],
                ai_config_id=None,
                ai_config_name=None,
                model_name=None,
                provider=None,
            ))

    # 可选模型列表
    available = [
        {"id": m.id, "name": m.name, "model": m.model, "provider": m.provider}
        for m in all_models
    ]

    return AllModuleConfigsResponse(modules=modules, available_models=available)


@router.put("/module-configs/{module_name}")
async def set_module_config(
    module_name: str,
    data: ModuleModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """设置模块的 AI 模型配置"""
    # 验证模块名
    valid_names = [m["name"] for m in ALL_MODULES]
    if module_name not in valid_names:
        raise HTTPException(status_code=400, detail=f"无效的模块名: {module_name}")

    # 验证 AI 配置存在
    ai_config = await db.execute(
        select(AIConfig).where(AIConfig.id == data.ai_config_id)
    )
    if not ai_config.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="AI 配置不存在")

    # 查找或创建
    result = await db.execute(
        select(ModuleModelConfig).where(ModuleModelConfig.module_name == module_name)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.ai_config_id = data.ai_config_id
    else:
        config = ModuleModelConfig(
            module_name=module_name,
            ai_config_id=data.ai_config_id,
        )
        db.add(config)

    await db.flush()
    return {"message": f"模块 {module_name} 已绑定模型", "module_name": module_name, "ai_config_id": data.ai_config_id}


@router.delete("/module-configs/{module_name}")
async def delete_module_config(
    module_name: str,
    db: AsyncSession = Depends(get_db),
):
    """清除模块的模型绑定（回退到默认模型）"""
    result = await db.execute(
        select(ModuleModelConfig).where(ModuleModelConfig.module_name == module_name)
    )
    existing = result.scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="该模块没有自定义模型配置")

    await db.delete(existing)
    await db.flush()
    return {"message": f"模块 {module_name} 已清除模型绑定，将使用默认模型"}
