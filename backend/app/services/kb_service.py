"""知识库业务逻辑层"""

import logging
import math
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.article import Article
from app.models.todo import TodoItem
from app.schemas.article import (
    ArticleCreate, ArticleUpdate, ArticleResponse,
    ArticleListItem, KBSearchParams, KBOverview,
    TagInfo, PaginatedArticleResponse, ReadStatusUpdate,
    BatchReadStatusUpdate, ArticleToTodoRequest,
)

logger = logging.getLogger(__name__)


# ==================== CRUD ====================

async def create_article(db: AsyncSession, data: ArticleCreate) -> Article:
    """创建知识库条目"""
    article = Article(
        title=data.title,
        url=data.url,
        content=data.content,
        item_type=data.item_type,
        content_type=data.content_type,
        summary=data.summary,
        tags=data.tags,
        source_chat_id=data.source_chat_id,
        # 工具类不设置阅读状态
        read_status="unread" if data.item_type == "article" else None,
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)
    logger.info(f"创建知识库条目: id={article.id}, title={article.title}, type={article.item_type}")
    return article


async def get_article(db: AsyncSession, article_id: int) -> Optional[Article]:
    """获取单个条目详情"""
    result = await db.execute(
        select(Article).where(Article.id == article_id)
    )
    return result.scalar_one_or_none()


async def update_article(db: AsyncSession, article_id: int, data: ArticleUpdate) -> Optional[Article]:
    """更新知识库条目"""
    article = await get_article(db, article_id)
    if not article:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(article, field, value)

    # 如果类型从 article 改为 tool，清除阅读状态
    if data.item_type == "tool":
        article.read_status = None
    # 如果类型从 tool 改为 article，设置默认阅读状态
    elif data.item_type == "article" and article.read_status is None:
        article.read_status = "unread"

    await db.flush()
    await db.refresh(article)
    logger.info(f"更新知识库条目: id={article_id}")
    return article


async def delete_article(db: AsyncSession, article_id: int) -> bool:
    """删除知识库条目"""
    article = await get_article(db, article_id)
    if not article:
        return False

    await db.delete(article)
    await db.flush()
    logger.info(f"删除知识库条目: id={article_id}")
    return True


# ==================== 列表与搜索 ====================

async def list_articles(db: AsyncSession, params: KBSearchParams) -> PaginatedArticleResponse:
    """获取知识库列表（支持搜索、筛选、排序、分页）"""
    query = select(Article)

    # 关键词搜索
    if params.keyword:
        keyword = f"%{params.keyword}%"
        query = query.where(
            or_(
                Article.title.ilike(keyword),
                Article.content.ilike(keyword),
                Article.summary.ilike(keyword),
                Article.url.ilike(keyword),
            )
        )

    # 类型筛选
    if params.item_type:
        query = query.where(Article.item_type == params.item_type)

    # 阅读状态筛选（仅对 article 类型有效）
    if params.read_status:
        query = query.where(Article.read_status == params.read_status)

    # 标签筛选（JSON 数组中查找）
    if params.tag:
        # SQLite 中 JSON 数组查找：用 LIKE 模糊匹配
        query = query.where(Article.tags.ilike(f'%"{params.tag}"%'))

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 排序
    sort_column = getattr(Article, params.sort_by, Article.created_at)
    if params.sort_order == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    # 分页
    offset = (params.page - 1) * params.page_size
    query = query.offset(offset).limit(params.page_size)

    result = await db.execute(query)
    articles = result.scalars().all()

    total_pages = math.ceil(total / params.page_size) if params.page_size > 0 else 0

    return PaginatedArticleResponse(
        items=[ArticleListItem.model_validate(a) for a in articles],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


# ==================== 阅读状态 ====================

async def update_read_status(db: AsyncSession, article_id: int, status: str) -> Optional[Article]:
    """更新阅读状态"""
    article = await get_article(db, article_id)
    if not article:
        return None
    if article.item_type != "article":
        logger.warning(f"工具类条目不支持阅读状态: id={article_id}")
        return article

    article.read_status = status
    await db.flush()
    await db.refresh(article)
    return article


async def batch_update_read_status(db: AsyncSession, data: BatchReadStatusUpdate) -> int:
    """批量更新阅读状态"""
    updated_count = 0
    for article_id in data.ids:
        article = await get_article(db, article_id)
        if article and article.item_type == "article":
            article.read_status = data.read_status
            updated_count += 1
    await db.flush()
    return updated_count


# ==================== 标签 ====================

async def get_all_tags(db: AsyncSession) -> list[TagInfo]:
    """获取所有标签及其使用次数"""
    result = await db.execute(select(Article.tags).where(Article.tags.isnot(None)))
    all_tags_rows = result.scalars().all()

    tag_counter: dict[str, int] = {}
    for tags_list in all_tags_rows:
        if isinstance(tags_list, list):
            for tag in tags_list:
                if isinstance(tag, str) and tag.strip():
                    tag_counter[tag.strip()] = tag_counter.get(tag.strip(), 0) + 1

    # 按使用次数降序排列
    sorted_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)
    return [TagInfo(name=name, count=count) for name, count in sorted_tags]


# ==================== 总览统计 ====================

async def get_overview(db: AsyncSession) -> KBOverview:
    """获取知识库总览统计"""
    # 总条目数
    total_result = await db.execute(select(func.count(Article.id)))
    total_count = total_result.scalar() or 0

    # 文章数
    article_result = await db.execute(
        select(func.count(Article.id)).where(Article.item_type == "article")
    )
    article_count = article_result.scalar() or 0

    # 工具数
    tool_result = await db.execute(
        select(func.count(Article.id)).where(Article.item_type == "tool")
    )
    tool_count = tool_result.scalar() or 0

    # 未读文章数
    unread_result = await db.execute(
        select(func.count(Article.id)).where(
            Article.item_type == "article",
            Article.read_status == "unread"
        )
    )
    unread_count = unread_result.scalar() or 0

    # 已读文章数
    read_result = await db.execute(
        select(func.count(Article.id)).where(
            Article.item_type == "article",
            Article.read_status == "read"
        )
    )
    read_count = read_result.scalar() or 0

    # 标签统计
    tags = await get_all_tags(db)
    tag_count = len(tags)

    # 最近收集（6 条）
    recent_result = await db.execute(
        select(Article).order_by(desc(Article.created_at)).limit(6)
    )
    recent_articles = [
        ArticleListItem.model_validate(a) for a in recent_result.scalars().all()
    ]

    # 热门标签（前 10）
    popular_tags = [{"name": t.name, "count": t.count} for t in tags[:10]]

    return KBOverview(
        total_count=total_count,
        article_count=article_count,
        tool_count=tool_count,
        unread_count=unread_count,
        read_count=read_count,
        tag_count=tag_count,
        recent_articles=recent_articles,
        popular_tags=popular_tags,
    )


# ==================== AI 上下文检索 ====================

async def search_for_ai_context(db: AsyncSession, query: str, limit: int = 5) -> str:
    """搜索知识库内容，供 AI 对话注入上下文

    返回格式化的文本，包含最匹配的知识库条目摘要。
    """
    if not query or not query.strip():
        return ""

    keyword = f"%{query.strip()}%"
    result = await db.execute(
        select(Article)
        .where(
            or_(
                Article.title.ilike(keyword),
                Article.content.ilike(keyword),
                Article.summary.ilike(keyword),
            )
        )
        .order_by(desc(Article.created_at))
        .limit(limit)
    )
    articles = result.scalars().all()

    if not articles:
        return ""

    parts = ["## 用户知识库相关内容（供参考回答）\n"]
    for i, a in enumerate(articles, 1):
        type_label = "📄文章" if a.item_type == "article" else "🔧工具"
        parts.append(f"### {i}. [{type_label}] {a.title}")
        if a.url:
            parts.append(f"- 链接: {a.url}")
        if a.summary:
            parts.append(f"- 摘要: {a.summary}")
        if a.content:
            # 截取前 500 字符
            content_preview = a.content[:500]
            if len(a.content) > 500:
                content_preview += "..."
            parts.append(f"- 内容: {content_preview}")
        if a.tags:
            parts.append(f"- 标签: {', '.join(a.tags)}")
        parts.append("")

    return "\n".join(parts)


# ==================== 转待办 ====================

async def article_to_todo(
    db: AsyncSession, article_id: int, data: ArticleToTodoRequest
) -> Optional[TodoItem]:
    """将知识库文章转为待办"""
    article = await get_article(db, article_id)
    if not article:
        return None

    todo_title = data.title or f"阅读：{article.title}"
    todo_description = data.description or ""
    if article.url:
        todo_description += f"\n链接: {article.url}" if todo_description else f"链接: {article.url}"
    if article.summary:
        todo_description += f"\n摘要: {article.summary}"

    todo = TodoItem(
        title=todo_title,
        description=todo_description.strip(),
        source="kb",
        source_id=article.id,
        status="inbox",
        quadrant=4,
        urgency=2,
        importance=3,
        category="learning",
    )

    # 如果有截止日期
    if data.due_date:
        from datetime import date as date_type
        try:
            todo.due_date = date_type.fromisoformat(data.due_date)
        except ValueError:
            pass

    db.add(todo)
    await db.flush()
    await db.refresh(todo)
    logger.info(f"文章转待办: article_id={article_id} -> todo_id={todo.id}")
    return todo


# ==================== 关联笔记 ====================

async def link_note(db: AsyncSession, article_id: int, note_id: int) -> Optional[Article]:
    """关联读后笔记到文章"""
    article = await get_article(db, article_id)
    if not article:
        return None

    article.note_id = note_id
    await db.flush()
    await db.refresh(article)
    logger.info(f"文章关联笔记: article_id={article_id}, note_id={note_id}")
    return article
