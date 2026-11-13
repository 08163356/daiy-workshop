"""读书模块 API — 数据库优先架构（v2）

数据源：
- 知识分类 → knowledge_categories + knowledge_items 表
- 思维模型 → thinking_models 表
- 知识图谱 → knowledge_graph 表
- 概览统计 → reading_overview 表（增量更新）
- 时间线 → notes 表

特点：
1. 种子数据从 JSON 一次性导入（migrate_json_to_db.py）
2. AI 分析后自动增量更新（新增/合并/importance递增）
3. 知识查询 API 供 AI 分析时注入上下文
"""

import re
import json
import logging
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, distinct, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.note import Note, NoteConcept
from app.models.concept import Concept
from app.models.thinking_model import ThinkingModel
from app.models.knowledge import (
    KnowledgeCategory, KnowledgeItem, ReadingOverview,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reading", tags=["读书模块"])


def _clean_html(text: str) -> str:
    """去除 HTML 标签"""
    return re.sub(r'<[^>]+>', ' ', text).strip()


# ==================== 知识分类 API ====================

@router.get("/knowledge", summary="获取知识分类列表")
async def get_knowledge(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    从 knowledge_categories + knowledge_items 表读取。
    返回格式兼容前端 KnowledgeView。
    """
    # 获取分类列表
    cat_result = await db.execute(
        select(KnowledgeCategory).order_by(KnowledgeCategory.sort_order)
    )
    categories = cat_result.scalars().all()

    knowledge_list = []
    for cat in categories:
        # 获取该分类下的所有条目
        items_result = await db.execute(
            select(KnowledgeItem)
            .where(KnowledgeItem.category_title == cat.title)
            .order_by(KnowledgeItem.importance.desc(), KnowledgeItem.name)
        )
        items = items_result.scalars().all()

        knowledge_list.append({
            "title": cat.title,
            "items": [
                {
                    "name": item.name,
                    "description": item.description or "",
                }
                for item in items
            ],
        })

    return knowledge_list


# ==================== 思维模型 API ====================

@router.get("/models", summary="获取思维模型列表")
async def get_models(
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """从 thinking_models 表读取思维模型列表"""
    query = select(ThinkingModel).order_by(
        ThinkingModel.mention_count.desc(), ThinkingModel.id
    )

    if keyword:
        query = query.where(
            ThinkingModel.title.contains(keyword) |
            ThinkingModel.description.contains(keyword)
        )

    result = await db.execute(query)
    models = result.scalars().all()

    return [
        {
            "title": m.title,
            "description": m.description or "",
        }
        for m in models
    ]


# ==================== 概览 API ====================

@router.get("/overview", summary="获取读书系统概览")
async def get_overview(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """实时统计读书系统概览数据，兼容 reading_overview 缓存表中的阅读天数/进度"""
    # 实时统计核心数字
    notes_count = await db.scalar(select(func.count(Note.id))) or 0
    concepts_count = await db.scalar(select(func.count(Concept.id))) or 0

    # 知识条目数（knowledge_items）
    from app.models.knowledge import KnowledgeItem
    knowledge_count = await db.scalar(select(func.count(KnowledgeItem.id))) or 0

    # 总知识点 = 概念 + 知识条目
    total_knowledge = concepts_count + knowledge_count

    # reading_days / progress / ai_comments 仍从缓存表读取
    overview = await db.scalar(select(ReadingOverview).limit(1))
    reading_days = overview.reading_days if overview else 0
    ai_comments = overview.ai_comments if overview else 0
    progress = (overview.progress or {}) if overview else {}

    return {
        "reading_days": reading_days,
        "books_count": notes_count,          # 实时：已读书籍/笔记数
        "notes_count": notes_count,          # 同上，供前端直接用
        "concepts_count": total_knowledge,   # 实时：总知识点（概念+知识条目）
        "knowledge_count": total_knowledge,  # 同上
        "raw_concepts": concepts_count,      # 纯概念数
        "raw_knowledge_items": knowledge_count,  # 纯知识条目数
        "ai_comments": ai_comments,
        "progress": progress,
    }


# ==================== 时间线 API ====================

@router.get("/timeline", summary="获取阅读时间线")
async def get_timeline(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=500),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    source_type: Optional[str] = Query(None, description="来源类型过滤: book/course/self"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """从 notes 表读取阅读时间线（分页）"""
    # 计算总数
    count_query = select(func.count(Note.id))
    if keyword:
        count_query = count_query.where(
            Note.title.contains(keyword) | Note.content.contains(keyword)
        )
    if source_type:
        count_query = count_query.where(Note.source_type == source_type)
    total = await db.scalar(count_query) or 0

    query = select(Note).order_by(Note.reading_date.desc(), Note.created_at.desc())

    if keyword:
        query = query.where(
            Note.title.contains(keyword) | Note.content.contains(keyword)
        )
    if source_type:
        query = query.where(Note.source_type == source_type)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    notes = result.scalars().all()

    timeline = []
    for note in notes:
        # 分离原文和 AI 分析
        original_content = note.content or ""
        ai_analysis = ""
        separator = "\n\n---\n\n## AI 分析\n\n"
        if separator in original_content:
            parts = original_content.split(separator, 1)
            original_content = parts[0]
            ai_analysis = parts[1]

        # key_points 从 summary 恢复
        key_points = []
        if note.summary:
            key_points = [p.strip() for p in note.summary.split(" | ") if p.strip()]

        # 构建 HTML content（兼容前端摘要展示）
        html_points = "".join(
            f"<strong>{p}</strong><br>" for p in key_points
        ) if key_points else f"<strong>{note.title}</strong>"

        timeline.append({
            "id": note.id,
            "date": note.reading_date.strftime("%Y.%m.%d") if note.reading_date else "",
            "title": note.title,
            "content": html_points,
            "key_points": key_points,
            "original_content": original_content,
            "ai_analysis": ai_analysis,
            "structured_data": {},
            "source_type": note.source_type or "book",
            "course_meta": note.course_meta,
            "images": note.images or [],
        })

    return {"total": total, "items": timeline}


# ==================== 删除笔记 API ====================

@router.delete("/notes/{note_id}", summary="删除阅读笔记")
async def delete_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """删除指定阅读笔记及其关联数据"""
    note = await db.scalar(select(Note).where(Note.id == note_id))
    if not note:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="笔记不存在")
    
    # 删除关联的 NoteConcept
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(NoteConcept).where(NoteConcept.note_id == note_id))
    
    # 删除笔记本身
    await db.delete(note)
    await db.flush()
    
    return {"message": "删除成功", "id": note_id}


# ==================== 补充 AI 分析 API ====================

@router.post("/notes/{note_id}/analyze", summary="为已有笔记补充 AI 分析")
async def analyze_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """为没有 AI 分析的笔记补充分析"""
    note = await db.scalar(select(Note).where(Note.id == note_id))
    if not note:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="笔记不存在")
    
    # 检查是否已有 AI 分析
    content = note.content or ""
    separator = "\n\n---\n\n## AI 分析\n\n"
    if separator in content:
        return {"status": "already_analyzed", "message": "该笔记已有 AI 分析"}
    
    # 获取 AI 配置
    from app.services.ai_service import get_active_ai_config, call_ai
    config = await get_active_ai_config(db)
    if not config:
        return {"status": "no_ai_config", "message": "未配置 AI 模型"}
    
    try:
        # 调用 AI 分析
        result = await call_ai(db, "reading", content, config)
        analysis_md = result.get("analysis_markdown", "")
        structured = result.get("structured_data", {})
        
        if not analysis_md:
            return {"status": "error", "message": "AI 未返回分析内容"}
        
        # 更新笔记内容（追加 AI 分析）
        note.content = f"{content}{separator}{analysis_md}"
        
        # 更新 key_points
        key_points = structured.get("key_points", [])
        if key_points:
            note.summary = " | ".join(key_points)
        
        await db.flush()
        
        # ✅ 写入 concepts / thinking_models / knowledge_items（之前这里漏掉了）
        if structured:
            try:
                from app.api.chat import _save_reading_data
                today = note.created_at.date() if note.created_at else date.today()
                await _save_reading_data(
                    db=db,
                    today=today,
                    title=note.title or "",
                    content=content,
                    analysis=analysis_md,
                    structured=structured,
                )
                logger.info(f"笔记 {note.id} 结构化数据已写入 concepts/models")
            except Exception as e:
                logger.warning(f"写入结构化数据失败（非致命）: {e}")
        
        return {
            "status": "success",
            "message": "AI 分析完成",
            "ai_analysis": analysis_md,
            "tokens_used": result.get("tokens_used", 0),
        }
    except Exception as e:
        logger.error(f"补充 AI 分析失败: {e}", exc_info=True)
        return {"status": "error", "message": f"分析失败: {str(e)}"}



# ==================== 知识查询 API（供 AI 分析注入上下文） ====================

@router.get("/knowledge-context", summary="获取知识体系摘要（供AI分析使用）")
async def get_knowledge_context(
    db: AsyncSession = Depends(get_db),
    max_items: int = Query(200, description="最大返回条目数"),
) -> dict:
    """
    返回知识体系的紧凑摘要文本，注入到 AI Prompt 中让 AI 参考已有知识。
    包含：知识分类列表 + 高频思维模型 + 分类下的知识条目
    """
    lines = []

    # 1. 知识分类 + 条目（按 importance 排序取 top）
    lines.append("## 已有知识分类：")
    cat_result = await db.execute(
        select(KnowledgeCategory).order_by(KnowledgeCategory.sort_order)
    )
    categories = cat_result.scalars().all()

    item_total = 0
    for cat in categories:
        items_result = await db.execute(
            select(KnowledgeItem)
            .where(KnowledgeItem.category_title == cat.title)
            .order_by(KnowledgeItem.importance.desc())
            .limit(20)  # 每个分类最多20个
        )
        items = items_result.scalars().all()
        item_names = [f"{it.name}" for it in items]
        lines.append(f"- {cat.title}: {', '.join(item_names)}")
        item_total += len(items)
        if item_total >= max_items:
            break

    # 2. 思维模型（按提及次数排序取 top 30）
    lines.append("\n## 已有思维模型（按重要性排序）：")
    models_result = await db.execute(
        select(ThinkingModel)
        .order_by(ThinkingModel.mention_count.desc())
        .limit(30)
    )
    models = models_result.scalars().all()
    for m in models:
        lines.append(f"- {m.title}")

    return {
        "text": "\n".join(lines),
        "category_count": len(categories),
        "item_count": item_total,
        "model_count": len(models),
    }


# ==================== 增量更新 API ====================

@router.post("/knowledge/update", summary="增量更新知识体系")
async def update_knowledge(
    data: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    AI 分析后调用此接口增量更新知识体系。
    
    data 格式：
    {
        "concepts": [
            {"name": "xxx", "description": "...", "category": "🎲 不确定性科学", "action": "new|merge"}
        ],
        "models": [
            {"title": "xxx", "description": "...", "action": "new|merge"}  
        ],
        "relations": [
            {"source": "xxx", "target": "yyy", "type": "co_occurs", "strength": 0.5}
        ]
    }
    """
    results = {"concepts_added": 0, "concepts_merged": 0, "models_added": 0, "models_merged": 0}

    # 1. 更新知识条目
    for c_data in data.get("concepts", []):
        name = c_data.get("name", "").strip()
        if not name:
            continue
        category = c_data.get("category", "")
        description = c_data.get("description", "")
        action = c_data.get("action", "new")

        # 查找已有条目（同名）
        existing = await db.scalar(
            select(KnowledgeItem).where(KnowledgeItem.name == name)
        )

        if existing:
            # 合并：更新描述（取更长的）、提升重要性
            if description and (action == "merge" or len(description) > len(existing.description or '')):
                existing.description = description
            existing.importance = min(5, existing.importance + 1)
            existing.mention_count += 1
            existing.source = "ai"
            results["concepts_merged"] += 1
        else:
            # 新增：确保分类存在
            if category:
                cat = await db.scalar(
                    select(KnowledgeCategory).where(KnowledgeCategory.title == category)
                )
                if not cat:
                    # 自动创建新分类
                    max_order = await db.scalar(
                        select(func.max(KnowledgeCategory.sort_order))
                    ) or 0
                    cat = KnowledgeCategory(
                        title=category,
                        sort_order=max_order + 1,
                        item_count=0,
                    )
                    db.add(cat)
                    await db.flush()

                cat.item_count = (cat.item_count or 0) + 1
            
            ki = KnowledgeItem(
                name=name,
                description=description,
                category_title=category or "📚 未分类",
                importance=1,
                mention_count=1,
                source="ai",
            )
            db.add(ki)
            results["concepts_added"] += 1

    # 2. 更新思维模型
    for m_data in data.get("models", []):
        title = m_data.get("title", "").strip()
        if not title:
            continue
        description = m_data.get("description", "")
        action = m_data.get("action", "new")

        existing = await db.scalar(
            select(ThinkingModel).where(ThinkingModel.title == title)
        )
        if existing:
            if description and (action == "merge" or len(description) > len(existing.description or '')):
                existing.description = description
            existing.mention_count += 1
            results["models_merged"] += 1
        else:
            model = ThinkingModel(
                title=title,
                description=description,
                mention_count=1,
            )
            db.add(model)
            results["models_added"] += 1

    # 3. 更新概览统计
    overview = await db.scalar(select(ReadingOverview).limit(1))
    if overview:
        # 增量更新概念数
        total_items = await db.scalar(
            select(func.count(KnowledgeItem.id))
        ) or 0
        overview.concepts_count = total_items

    await db.flush()
    return {"status": "success", "results": results}


# ==================== 数据迁移 API（一次性使用）====================

@router.post("/migrate-models-json", summary="迁移 models.json 到数据库")
async def migrate_models_json(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """一次性迁移：从 models.json 导入思维模型到数据库"""
    import os
    import json

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    possible_paths = [
        os.path.join(base_dir, 'data', 'models.json'),
        os.path.join(base_dir, 'frontend', 'public', 'data', 'models.json'),
    ]

    models_data = None
    for path in possible_paths:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                models_data = json.load(f)
            break

    if not models_data:
        return {"status": "error", "message": "models.json 未找到"}

    imported = 0
    skipped = 0

    for m in models_data:
        title = m.get("title", "").strip()
        if not title:
            continue

        existing = await db.scalar(
            select(ThinkingModel).where(ThinkingModel.title == title)
        )
        if existing:
            skipped += 1
            continue

        model = ThinkingModel(
            title=title,
            description=m.get("description", ""),
            mention_count=1,
        )
        db.add(model)
        imported += 1

    await db.flush()

    return {
        "status": "success",
        "imported": imported,
        "skipped": skipped,
        "total_in_json": len(models_data),
    }


# ==================== 每日知识复利播报 API ====================

# 内存缓存：{日期字符串: 播报内容}
_daily_insight_cache: dict[str, dict] = {}


DAILY_INSIGHT_PROMPT = """你是用户的知识复利助手。你的任务是基于用户过往积累的全部知识，发现深层连接，制造"知识涌现"的惊喜时刻。

## 用户的知识体系

### 时间线笔记摘要（按时间倒序）
{timeline_summary}

### 知识分类和概念
{knowledge_summary}

### 思维模型
{models_summary}

## 你的任务

生成一段「今日知识复利」播报（200-350字），要求：

1. **发现跨领域连接**：从用户不同时间、不同书籍中学到的知识点之间，找出一条深层的联系链条
2. **制造涌现惊喜**：这个连接应该是用户自己可能没意识到的，但一听就觉得"哇，有道理！"
3. **具体而有启发**：引用具体的笔记内容和日期，让用户感受到知识的积累是有回报的
4. **可实践**：最后给出一个基于这个洞察的具体小行动或思考实验
5. **语气**：像一个智慧的朋友在早晨咖啡时间跟你分享一个有趣的发现，轻松但有深度

## 输出格式
直接输出 Markdown 格式的播报文本，不要包裹在 JSON 中。不要输出标题（前端会自己加标题）。"""


@router.get("/daily-insight", summary="获取每日知识复利播报")
async def get_daily_insight(
    force_refresh: bool = Query(False, description="强制刷新（忽略缓存）"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    每日知识复利播报：基于用户全部笔记，AI 发现跨领域知识连接。
    同一天只生成一次（内存缓存），避免重复调用 AI。
    """
    today_str = date.today().isoformat()
    
    # 检查缓存
    if not force_refresh and today_str in _daily_insight_cache:
        cached = _daily_insight_cache[today_str]
        return {**cached, "cached": True}
    
    try:
        # 1. 收集时间线笔记摘要
        notes_result = await db.execute(
            select(Note)
            .order_by(Note.reading_date.desc(), Note.created_at.desc())
            .limit(50)
        )
        notes = notes_result.scalars().all()
        
        if len(notes) < 3:
            return {
                "status": "insufficient_data",
                "message": "笔记数量不足（至少需要 3 篇），继续积累知识吧！",
                "insight": "",
                "cached": False,
            }
        
        timeline_lines = []
        for note in notes:
            date_str = note.reading_date.strftime("%Y.%m.%d") if note.reading_date else "未知日期"
            # 提取 key_points
            key_points = ""
            if note.summary:
                key_points = note.summary[:200]
            # 提取原文摘要（去掉 AI 分析部分）
            content_preview = note.content or ""
            separator = "\n\n---\n\n## AI 分析\n\n"
            if separator in content_preview:
                content_preview = content_preview.split(separator, 1)[0]
            content_preview = content_preview[:300]
            
            timeline_lines.append(f"- [{date_str}] **{note.title}**：{key_points or content_preview}")
        
        timeline_summary = "\n".join(timeline_lines)
        
        # 2. 收集知识分类
        cat_result = await db.execute(
            select(KnowledgeCategory).order_by(KnowledgeCategory.sort_order)
        )
        categories = cat_result.scalars().all()
        
        knowledge_lines = []
        for cat in categories:
            items_result = await db.execute(
                select(KnowledgeItem)
                .where(KnowledgeItem.category_title == cat.title)
                .order_by(KnowledgeItem.importance.desc())
                .limit(15)
            )
            items = items_result.scalars().all()
            item_names = [it.name for it in items]
            if item_names:
                knowledge_lines.append(f"- {cat.title}: {', '.join(item_names)}")
        
        knowledge_summary = "\n".join(knowledge_lines) if knowledge_lines else "暂无知识分类数据"
        
        # 3. 收集思维模型
        models_result = await db.execute(
            select(ThinkingModel)
            .order_by(ThinkingModel.mention_count.desc())
            .limit(30)
        )
        models = models_result.scalars().all()
        models_summary = "\n".join(f"- {m.title}" for m in models) if models else "暂无思维模型"
        
        # 4. 构建 prompt 并调用 AI
        from app.services.ai_service import get_active_ai_config, _build_request, _get_api_url
        import httpx
        
        config = await get_active_ai_config(db)
        if not config:
            return {
                "status": "no_ai_config",
                "message": "未配置 AI 模型，请先在设置页面配置",
                "insight": "",
                "cached": False,
            }
        
        prompt = DAILY_INSIGHT_PROMPT.replace("{timeline_summary}", timeline_summary) \
                                      .replace("{knowledge_summary}", knowledge_summary) \
                                      .replace("{models_summary}", models_summary)
        
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"今天是 {today_str}，请生成今日知识复利播报。"},
        ]
        
        url, headers, payload = _build_request(config, messages)
        # 使用较少的 token 和低温度
        payload["max_tokens"] = min(config.max_tokens, 1024)
        payload["temperature"] = 0.8  # 稍高温度增加创造性
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            insight_content = data["choices"][0]["message"]["content"]
            tokens_used = data.get("usage", {}).get("total_tokens", 0)
        
        # 清理可能的 markdown 代码块包裹
        insight_content = insight_content.strip()
        if insight_content.startswith("```"):
            lines = insight_content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            insight_content = "\n".join(lines)
        
        result = {
            "status": "success",
            "insight": insight_content,
            "generated_at": datetime.now().isoformat(),
            "note_count": len(notes),
            "tokens_used": tokens_used,
        }
        
        # 写入缓存（清除旧缓存）
        _daily_insight_cache.clear()
        _daily_insight_cache[today_str] = result
        
        return {**result, "cached": False}
        
    except httpx.HTTPStatusError as e:
        logger.error(f"AI 调用失败: {e}")
        return {
            "status": "error",
            "message": f"AI 调用失败: {e.response.status_code}",
            "insight": "",
            "cached": False,
        }
    except Exception as e:
        logger.error(f"生成知识复利播报失败: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"生成失败: {str(e)}",
            "insight": "",
            "cached": False,
        }
