"""统一对话 API - 支持投资/读书/日记的 AI 分析与入库"""

import asyncio
import json
import logging
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.ai_config import AIConfig, UserProfile, ConversationLog
from app.models.diary import DiaryEntry
from app.models.investment import (
    InvestmentReflection, InvestmentPrinciple, InvestmentCognition,
    InvestmentDecision, InvestmentEmotion, InvestmentKnowledge, InvestmentQA,
)
from app.schemas.ai_config import (
    AIConfigCreate, AIConfigUpdate, AIConfigListResponse,
    UserProfileItem, UserProfileUpdate,
    ChatRequest, ChatAnalysisResult, ChatSaveRequest, ChatSaveResponse,
    ConversationLogResponse,
)
from app.schemas.investment import ListResponse
from app.services.ai_service import (
    call_ai, call_ai_stream, classify_content, get_active_ai_config,
    get_user_profile_text, update_user_profile,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["统一对话"])


# ==================== AI 配置管理 ====================

@router.get("/ai-config", response_model=list[AIConfigListResponse])
async def list_ai_configs(db: AsyncSession = Depends(get_db)):
    """获取所有 AI 配置"""
    result = await db.execute(
        select(AIConfig).order_by(desc(AIConfig.is_active), AIConfig.created_at)
    )
    configs = result.scalars().all()
    items = []
    for c in configs:
        masked = f"{c.api_key[:8]}...{c.api_key[-4:]}" if len(c.api_key) > 12 else "***"
        items.append(AIConfigListResponse(
            id=c.id, name=c.name, provider=c.provider, model=c.model,
            api_base=c.api_base, temperature=c.temperature, max_tokens=c.max_tokens,
            is_active=c.is_active, api_key_masked=masked,
            created_at=c.created_at, updated_at=c.updated_at,
        ))
    return items


@router.post("/ai-config", response_model=AIConfigListResponse)
async def create_ai_config(data: AIConfigCreate, db: AsyncSession = Depends(get_db)):
    """创建 AI 配置"""
    # 如果设为激活，先取消其他配置的激活状态
    if data.is_active:
        result = await db.execute(select(AIConfig).where(AIConfig.is_active == True))
        for existing in result.scalars():
            existing.is_active = False
    
    config = AIConfig(**data.model_dump())
    db.add(config)
    await db.flush()
    await db.refresh(config)
    
    masked = f"{config.api_key[:8]}...{config.api_key[-4:]}" if len(config.api_key) > 12 else "***"
    return AIConfigListResponse(
        id=config.id, name=config.name, provider=config.provider, model=config.model,
        api_base=config.api_base, temperature=config.temperature, max_tokens=config.max_tokens,
        is_active=config.is_active, api_key_masked=masked,
        created_at=config.created_at, updated_at=config.updated_at,
    )


@router.put("/ai-config/{config_id}", response_model=AIConfigListResponse)
async def update_ai_config(
    config_id: int, data: AIConfigUpdate, db: AsyncSession = Depends(get_db)
):
    """更新 AI 配置"""
    result = await db.execute(select(AIConfig).where(AIConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    
    update_data = data.model_dump(exclude_unset=True)
    
    # 如果设为激活，先取消其他
    if update_data.get("is_active"):
        result2 = await db.execute(
            select(AIConfig).where(AIConfig.is_active == True, AIConfig.id != config_id)
        )
        for existing in result2.scalars():
            existing.is_active = False
    
    for key, value in update_data.items():
        setattr(config, key, value)
    
    await db.flush()
    await db.refresh(config)
    
    masked = f"{config.api_key[:8]}...{config.api_key[-4:]}" if len(config.api_key) > 12 else "***"
    return AIConfigListResponse(
        id=config.id, name=config.name, provider=config.provider, model=config.model,
        api_base=config.api_base, temperature=config.temperature, max_tokens=config.max_tokens,
        is_active=config.is_active, api_key_masked=masked,
        created_at=config.created_at, updated_at=config.updated_at,
    )


@router.delete("/ai-config/{config_id}")
async def delete_ai_config(config_id: int, db: AsyncSession = Depends(get_db)):
    """删除 AI 配置"""
    result = await db.execute(select(AIConfig).where(AIConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    await db.delete(config)
    await db.flush()
    return {"message": "删除成功"}


# ==================== 用户画像 ====================

@router.get("/profile", response_model=list[UserProfileItem])
async def list_user_profiles(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取用户画像"""
    query = select(UserProfile).order_by(UserProfile.category, UserProfile.key)
    if category:
        query = query.where(UserProfile.category == category)
    result = await db.execute(query)
    return [UserProfileItem.model_validate(p) for p in result.scalars()]


@router.post("/profile", response_model=UserProfileItem)
async def create_or_update_profile(
    data: UserProfileUpdate, db: AsyncSession = Depends(get_db)
):
    """手动创建/更新用户画像"""
    result = await db.execute(
        select(UserProfile).where(
            UserProfile.category == data.category,
            UserProfile.key == data.key,
        )
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.value = data.value
        existing.source_count += 1
        await db.flush()
        await db.refresh(existing)
        return UserProfileItem.model_validate(existing)
    else:
        profile = UserProfile(
            category=data.category, key=data.key, value=data.value,
            confidence=0.8, source_count=1,
        )
        db.add(profile)
        await db.flush()
        await db.refresh(profile)
        return UserProfileItem.model_validate(profile)


@router.delete("/profile/{profile_id}")
async def delete_profile(profile_id: int, db: AsyncSession = Depends(get_db)):
    """删除画像项"""
    result = await db.execute(select(UserProfile).where(UserProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="画像项不存在")
    await db.delete(profile)
    await db.flush()
    return {"message": "删除成功"}


@router.post("/profile/batch")
async def batch_upsert_profiles(
    data: list[UserProfileUpdate],
    db: AsyncSession = Depends(get_db),
):
    """批量导入/更新用户画像"""
    results = []
    for item in data:
        existing_result = await db.execute(
            select(UserProfile).where(
                UserProfile.category == item.category,
                UserProfile.key == item.key,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.value = item.value
            existing.source_count += 1
            existing.confidence = min(1.0, existing.confidence + 0.1)
            results.append({"action": "updated", "category": item.category, "key": item.key})
        else:
            profile = UserProfile(
                category=item.category,
                key=item.key,
                value=item.value,
                confidence=0.8,
                source_count=1,
            )
            db.add(profile)
            results.append({"action": "created", "category": item.category, "key": item.key})

    await db.flush()
    return {"message": f"处理完成，共 {len(results)} 条", "results": results}


@router.get("/profile/categories")
async def get_profile_categories(db: AsyncSession = Depends(get_db)):
    """获取画像分类列表"""
    result = await db.execute(
        select(UserProfile.category, func.count(UserProfile.id))
        .group_by(UserProfile.category)
        .order_by(UserProfile.category)
    )
    return [{"category": row[0], "count": row[1]} for row in result]


# ==================== 用户画像周期性蒸馏（最小实现） ====================

@router.post("/profile/distill")
async def distill_profile(db: AsyncSession = Depends(get_db)):
    """手动触发一次画像蒸馏：整合近14天日记/待办完成/心力记录/心愿日志，产出结构化画像更新"""
    from app.services.ai_service import distill_user_profile
    try:
        result = await distill_user_profile(db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"画像蒸馏失败: {e}")
        raise HTTPException(status_code=500, detail=f"画像蒸馏失败: {str(e)}")


@router.get("/profile/distill/status")
async def get_distill_status(db: AsyncSession = Depends(get_db)):
    """获取上次画像蒸馏的运行状态，供 Settings 页展示"""
    from datetime import datetime
    from app.models.ai_config import ProfileDistillRun

    result = await db.execute(
        select(ProfileDistillRun).order_by(desc(ProfileDistillRun.created_at)).limit(1)
    )
    last_run = result.scalar_one_or_none()
    if not last_run:
        return {"last_run_at": None, "days_since": None, "last_summary": None}

    days_since = (datetime.now() - last_run.created_at).days
    return {
        "last_run_at": last_run.created_at.isoformat(),
        "days_since": days_since,
        "last_summary": last_run.summary,
        "sources_summary": last_run.sources_summary,
    }


# ==================== 统一对话核心 ====================

@router.post("/analyze", response_model=ChatAnalysisResult)
async def analyze_content(data: ChatRequest, db: AsyncSession = Depends(get_db)):
    """AI 分析内容（预览，不入库）
    
    流程：
    1. 如果 system_type 为 auto，先调用 AI 判断内容类型
    2. 调用对应系统的 AI 分析
    3. 返回分析结果供用户审核
    """
    # 检查 AI 配置
    config = await get_active_ai_config(db)
    if not config:
        raise HTTPException(status_code=400, detail="未配置 AI 模型，请先在设置页面配置")
    
    detected_types = []
    actual_type = data.system_type
    
    # 自动分类
    if data.system_type == "auto":
        try:
            classify_result = await classify_content(db, data.content)
            actual_type = classify_result.get("primary_type", "diary")
            detected_types = classify_result.get("all_types", [actual_type])
        except Exception as e:
            logger.warning(f"自动分类失败，默认使用 diary: {e}")
            actual_type = "diary"
            detected_types = ["diary"]
    else:
        detected_types = [data.system_type]
    
    # 调用 AI 分析
    try:
        result = await call_ai(db, actual_type, data.content, config, diary_date=data.diary_date)
    except Exception as e:
        logger.error(f"AI 分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"AI 分析失败: {str(e)}")
    
    return ChatAnalysisResult(
        system_type=actual_type,
        detected_types=detected_types,
        original_content=data.content,
        analysis_markdown=result.get("analysis_markdown", ""),
        structured_data=result.get("structured_data", {}),
        profile_updates=result.get("profile_updates", []),
        tokens_used=result.get("tokens_used", 0),
    )


@router.post("/analyze/stream")
async def analyze_content_stream(data: ChatRequest, db: AsyncSession = Depends(get_db)):
    """流式 AI 分析内容（SSE）
    
    返回 Server-Sent Events 流：
    - type=meta: 分类结果（system_type, detected_types）
    - type=chunk: AI 输出文本片段
    - type=done: 分析完成，附结构化结果
    - type=error: 错误信息
    """
    config = await get_active_ai_config(db)
    if not config:
        raise HTTPException(status_code=400, detail="未配置 AI 模型，请先在设置页面配置")
    
    detected_types = []
    actual_type = data.system_type
    
    # 自动分类（非流式，速度很快）
    if data.system_type == "auto":
        try:
            classify_result = await classify_content(db, data.content)
            actual_type = classify_result.get("primary_type", "diary")
            detected_types = classify_result.get("all_types", [actual_type])
        except Exception as e:
            logger.warning(f"自动分类失败，默认使用 diary: {e}")
            actual_type = "diary"
            detected_types = ["diary"]
    else:
        detected_types = [data.system_type]
    
    async def event_generator():
        # 先发送分类元数据
        meta = {
            "type": "meta",
            "system_type": actual_type,
            "detected_types": detected_types,
            "original_content": data.content,
        }
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
        
        try:
            async for chunk in call_ai_stream(db, actual_type, data.content, config, diary_date=data.diary_date):
                yield chunk
        except Exception as e:
            logger.error(f"流式 AI 分析失败: {e}")
            error_data = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/save", response_model=ChatSaveResponse)
async def save_analysis(data: ChatSaveRequest, db: AsyncSession = Depends(get_db)):
    """审核通过后保存分析结果到数据库
    
    根据 system_type 将数据分发到对应的表
    """
    saved_items = {}
    save_types = data.save_to_types or [data.system_type]
    today = date.today()
    
    for sys_type in save_types:
        if sys_type == "investment":
            saved_items["investment"] = await _save_investment_data(
                db, today, data.title, data.original_content,
                data.analysis_markdown, data.structured_data
            )
        elif sys_type == "diary" or sys_type == "note":
            saved_items[sys_type] = await _save_diary_data(
                db, today, data.title, data.original_content,
                data.analysis_markdown, data.structured_data, data.images
            )
        elif sys_type == "reading":
            saved_items["reading"] = await _save_reading_data(
                db, today, data.title, data.original_content,
                data.analysis_markdown, data.structured_data, data.images
            )
    
    # 更新用户画像
    profile_updated = []
    if data.profile_updates:
        profile_updated = await update_user_profile(db, data.profile_updates)
    
    # 保存对话日志
    log = ConversationLog(
        system_type=data.system_type,
        user_input=data.original_content,
        ai_response=data.analysis_markdown,
        detected_type=data.system_type,
        profile_updates=data.profile_updates,
        data_saved=[{"type": t, "ids": v} for t, v in saved_items.items()],
    )
    db.add(log)
    await db.flush()
    
    return ChatSaveResponse(
        success=True,
        message="保存成功",
        saved_items=saved_items,
        profile_updated=profile_updated,
    )


async def _save_investment_data(
    db: AsyncSession, today: date, title: str,
    content: str, analysis: str, structured: dict
) -> dict:
    """保存投资数据到各表"""
    ids = {}
    
    # 1. 反思记录
    reflection = InvestmentReflection(
        date=today, title=title, content=content,
        ai_analysis=analysis,
        key_points=structured.get("key_points", []),
    )
    db.add(reflection)
    await db.flush()
    await db.refresh(reflection)
    ids["reflection_id"] = reflection.id
    
    # 2. Q&A
    qa_list = structured.get("qa_list", [])
    qa_ids = []
    for qa_data in qa_list:
        qa = InvestmentQA(
            date=today,
            question=qa_data.get("question", ""),
            answer=qa_data.get("answer", ""),
            category=qa_data.get("category"),
            source_reflection_id=reflection.id,
            source_type=qa_data.get("source_type", "auto"),
            tags=qa_data.get("tags"),
        )
        db.add(qa)
        await db.flush()
        await db.refresh(qa)
        qa_ids.append(qa.id)
    if qa_ids:
        ids["qa_ids"] = qa_ids
    
    # 3. 原则
    principles = structured.get("principles", [])
    principle_ids = []
    for p_data in principles:
        p = InvestmentPrinciple(
            title=p_data.get("title", ""),
            content=p_data.get("content", ""),
            category=p_data.get("category", "心态管理"),
            source_reflection_id=reflection.id,
        )
        db.add(p)
        await db.flush()
        await db.refresh(p)
        principle_ids.append(p.id)
    if principle_ids:
        ids["principle_ids"] = principle_ids
    
    # 4. 认知迭代
    cognitions = structured.get("cognitions", [])
    cognition_ids = []
    for c_data in cognitions:
        c = InvestmentCognition(
            date=today,
            old_cognition=c_data.get("old_cognition", ""),
            new_cognition=c_data.get("new_cognition", ""),
            trigger=c_data.get("trigger", ""),
            category=c_data.get("category"),
        )
        db.add(c)
        await db.flush()
        await db.refresh(c)
        cognition_ids.append(c.id)
    if cognition_ids:
        ids["cognition_ids"] = cognition_ids
    
    # 5. 决策
    decisions = structured.get("decisions", [])
    for d_data in decisions:
        d = InvestmentDecision(
            date=today,
            action=d_data.get("action", "观望"),
            target=d_data.get("target", ""),
            logic=d_data.get("logic", ""),
            emotion_state=d_data.get("emotion_state"),
        )
        db.add(d)
    
    # 6. 情绪
    emotions = structured.get("emotions", [])
    for e_data in emotions:
        e = InvestmentEmotion(
            date=today,
            emotion=e_data.get("emotion", ""),
            trigger=e_data.get("trigger", ""),
            impact=e_data.get("impact"),
            coping_strategy=e_data.get("coping_strategy"),
            effectiveness=e_data.get("effectiveness"),
        )
        db.add(e)
    
    # 7. 知识
    knowledge_list = structured.get("knowledge", [])
    for k_data in knowledge_list:
        name = k_data.get("name", "")
        # 去重检查
        existing = await db.execute(
            select(InvestmentKnowledge).where(InvestmentKnowledge.name == name)
        )
        if not existing.scalar_one_or_none():
            k = InvestmentKnowledge(
                name=name,
                description=k_data.get("description", ""),
                category=k_data.get("category", "投资策略"),
            )
            db.add(k)
    
    await db.flush()
    return ids


async def _save_diary_data(
    db: AsyncSession, today: date, title: str,
    content: str, analysis: str, structured: dict,
    images: list[str] | None = None
) -> dict:
    """保存日记数据"""
    entry = DiaryEntry(
        date=today,
        title=title,
        content=content,
        ai_analysis=analysis,
        mood=structured.get("mood"),
        tags=structured.get("tags"),
        key_issues=structured.get("key_issues"),
        action_items=structured.get("action_items"),
        images=images or None,
        source="web",
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)

    # 异步触发心力候选提取（从日记中提取成就/感恩）
    try:
        from app.services.wellbeing_ai import extract_candidates_from_diary
        asyncio.create_task(extract_candidates_from_diary(entry.id, content))
    except Exception:
        pass

    # 异步生成 AI 澄清问题（有值得澄清的点才入队，失败不影响保存）
    try:
        from app.services.question_service import generate_questions_task
        asyncio.create_task(generate_questions_task("diary", entry.id, content))
    except Exception:
        pass

    return {"diary_id": entry.id}


async def _save_reading_data(
    db: AsyncSession, today: date, title: str,
    content: str, analysis: str, structured: dict,
    images: list[str] | None = None,
    source_type: str = "book", course_meta: dict | None = None,
) -> dict:
    """保存读书笔记数据到 notes 表，同时智能更新概念、模型和关系
    
    核心逻辑：
    1. 概念(concepts)：查重合并 + importance 递增 + 描述融合
    2. 模型(models)：查重归纳到 thinking_models 表
    3. 关系(relations)：保存到 concept_relations 表 + strength 强化
    """
    import hashlib
    import re
    from app.models.note import Note, NoteConcept
    from app.models.concept import Concept
    from app.models.relation import ConceptRelation
    from app.models.thinking_model import ThinkingModel

    # ==================== 1. 保存笔记 ====================
    content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
    from datetime import datetime as _dt
    timestamp = _dt.now().strftime("%H%M%S")
    unique_filename = f"web_{today.isoformat()}_{timestamp}_{title[:20]}"

    full_content = content
    if analysis:
        full_content = f"{content}\n\n---\n\n## AI 分析\n\n{analysis}"

    key_points = structured.get("key_points", [])
    summary_text = " | ".join(key_points) if key_points else (analysis[:500] if analysis else "")

    note = Note(
        filename=unique_filename,
        title=title,
        content=full_content,
        summary=summary_text,
        reading_date=today,
        word_count=len(content),
        file_hash=content_hash,
        images=images or None,
        source_type=source_type,
        course_meta=course_meta,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    ids: dict = {"note_id": note.id}

    # 异步生成 AI 澄清问题（读书笔记保存后，失败不影响保存）
    try:
        import asyncio as _asyncio
        from app.services.question_service import generate_questions_task
        _asyncio.create_task(generate_questions_task("note", note.id, content))
    except Exception:
        pass

    # ==================== 2. 智能处理概念（查重合并） ====================
    concepts_data = structured.get("concepts", [])
    concept_ids = []
    concept_name_to_id = {}  # 用于后续建立关系

    for c_data in concepts_data:
        concept_name = c_data.get("name", "").strip()
        if not concept_name:
            continue
        
        action = c_data.get("action", "new")
        new_description = c_data.get("description", "")
        new_category = c_data.get("category", "未分类")

        # 查找已有概念（精确匹配）
        existing_result = await db.execute(
            select(Concept).where(Concept.name == concept_name)
        )
        concept = existing_result.scalar_one_or_none()

        if concept:
            # ---- 已有概念：合并更新 ----
            # importance 递增（上限 5）
            concept.importance = min(5, concept.importance + 1)
            # mention_count 递增
            concept.mention_count = concept.mention_count + 1
            # 描述融合：如果 AI 给了 merge 后的完整描述就用它，否则保留原有
            if action == "merge" and new_description:
                concept.description = new_description
            elif new_description and (not concept.description or len(new_description) > len(concept.description)):
                concept.description = new_description
            # 分类更新（如果原来是未分类就更新）
            if concept.category in (None, "未分类") and new_category != "未分类":
                concept.category = new_category
            
            logger.info(f"概念合并: {concept_name} (importance={concept.importance}, mentions={concept.mention_count})")
        else:
            # ---- 全新概念：创建 ----
            concept = Concept(
                name=concept_name,
                description=new_description,
                category=new_category,
                importance=1,
                mention_count=1,
            )
            db.add(concept)
            await db.flush()
            await db.refresh(concept)
            logger.info(f"新概念: {concept_name}")

        # 建立笔记-概念关联（去重）
        link_exists = await db.execute(
            select(NoteConcept).where(
                NoteConcept.note_id == note.id,
                NoteConcept.concept_id == concept.id,
            )
        )
        if not link_exists.scalar_one_or_none():
            nc = NoteConcept(
                note_id=note.id,
                concept_id=concept.id,
                context=new_description[:200] if new_description else "",
            )
            db.add(nc)
        
        concept_ids.append(concept.id)
        concept_name_to_id[concept_name] = concept.id

    if concept_ids:
        ids["concept_ids"] = concept_ids

    # ==================== 3. 保存概念关系（查重 + 强化） ====================
    relations_data = structured.get("relations", [])
    relation_ids = []

    for r_data in relations_data:
        source_name = r_data.get("source", "").strip()
        target_name = r_data.get("target", "").strip()
        rel_type = r_data.get("type", "co_occurs")
        strength = r_data.get("strength", 0.5)

        # 查找概念 ID
        source_id = concept_name_to_id.get(source_name)
        target_id = concept_name_to_id.get(target_name)

        # 如果不在本次提取的概念中，尝试从数据库查找
        if not source_id:
            r = await db.execute(select(Concept).where(Concept.name == source_name))
            c = r.scalar_one_or_none()
            if c:
                source_id = c.id
        if not target_id:
            r = await db.execute(select(Concept).where(Concept.name == target_name))
            c = r.scalar_one_or_none()
            if c:
                target_id = c.id

        if not source_id or not target_id or source_id == target_id:
            continue

        # 查找已有关系
        existing_rel = await db.execute(
            select(ConceptRelation).where(
                ConceptRelation.source_id == source_id,
                ConceptRelation.target_id == target_id,
                ConceptRelation.relation_type == rel_type,
            )
        )
        rel = existing_rel.scalar_one_or_none()

        if rel:
            # 关系已存在：strength 递增（上限 1.0）
            rel.strength = min(1.0, rel.strength + 0.1)
            logger.info(f"关系强化: {source_name} -> {target_name} (strength={rel.strength:.1f})")
        else:
            # 新关系
            rel = ConceptRelation(
                source_id=source_id,
                target_id=target_id,
                relation_type=rel_type,
                strength=strength,
            )
            db.add(rel)
            await db.flush()
            await db.refresh(rel)
            logger.info(f"新关系: {source_name} -> {target_name}")
            relation_ids.append(rel.id)

    if relation_ids:
        ids["relation_ids"] = relation_ids

    # ==================== 4. 智能处理思维模型（查重归纳到数据库） ====================
    models_data = structured.get("models", [])
    model_ids = []

    for m_data in models_data:
        new_title = m_data.get("title", "").strip()
        new_desc = m_data.get("description", "")
        action = m_data.get("action", "new")

        if not new_title:
            continue

        # 查找已有模型（精确匹配 + 去 emoji 匹配）
        clean_new = re.sub(r'^[\U0001F300-\U0001F9FF\U00002600-\U000026FF]\s*', '', new_title).strip()

        existing_model = await db.scalar(
            select(ThinkingModel).where(ThinkingModel.title == new_title)
        )

        if not existing_model and clean_new:
            # 尝试模糊匹配：遍历数据库中的所有模型
            all_models = await db.execute(select(ThinkingModel))
            for m in all_models.scalars():
                clean_existing = re.sub(r'^[\U0001F300-\U0001F9FF\U00002600-\U000026FF]\s*', '', m.title).strip()
                if clean_new == clean_existing or (clean_new and clean_existing and (clean_new in clean_existing or clean_existing in clean_new)):
                    existing_model = m
                    break

        if existing_model:
            # 已有模型：合并更新
            existing_model.mention_count = existing_model.mention_count + 1
            if action == "merge" and new_desc:
                existing_model.description = new_desc
            logger.info(f"模型合并: {new_title} (mentions={existing_model.mention_count})")
            model_ids.append(existing_model.id)
        else:
            # 新模型
            model = ThinkingModel(
                title=new_title,
                description=new_desc,
                mention_count=1,
            )
            db.add(model)
            await db.flush()
            await db.refresh(model)
            logger.info(f"新模型: {new_title}")
            model_ids.append(model.id)

    if model_ids:
        ids["model_ids"] = model_ids

    # ==================== 5. 同步更新知识体系表 ====================
    try:
        from app.models.knowledge import KnowledgeCategory, KnowledgeItem, ReadingOverview

        # 5a. 同步知识条目（concepts → knowledge_items）
        for c_data in concepts_data:
            concept_name = c_data.get("name", "").strip()
            if not concept_name:
                continue
            category = c_data.get("category", "未分类")
            description = c_data.get("description", "")
            action = c_data.get("action", "new")

            # 查找已有条目
            existing_ki = await db.scalar(
                select(KnowledgeItem).where(KnowledgeItem.name == concept_name)
            )
            if existing_ki:
                # 合并
                if description and (action == "merge" or len(description) > len(existing_ki.description or '')):
                    existing_ki.description = description
                existing_ki.importance = min(5, existing_ki.importance + 1)
                existing_ki.mention_count += 1
                existing_ki.source = "ai"
            else:
                # 确保分类存在
                cat_title = category if any(ord(c) > 0x1F300 for c in category[:2]) else f"📚 {category}"
                cat = await db.scalar(
                    select(KnowledgeCategory).where(KnowledgeCategory.title == cat_title)
                )
                if not cat:
                    max_order = await db.scalar(
                        select(func.max(KnowledgeCategory.sort_order))
                    ) or 0
                    cat = KnowledgeCategory(
                        title=cat_title, sort_order=max_order + 1, item_count=0,
                    )
                    db.add(cat)
                    await db.flush()

                ki = KnowledgeItem(
                    name=concept_name,
                    description=description,
                    category_title=cat_title,
                    importance=1,
                    mention_count=1,
                    source="ai",
                )
                db.add(ki)
                cat.item_count = (cat.item_count or 0) + 1

        # 5b. 增量更新概览统计
        overview = await db.scalar(select(ReadingOverview).limit(1))
        if overview:
            overview.ai_comments = (overview.ai_comments or 0) + (1 if analysis else 0)
            total_items = await db.scalar(select(func.count(KnowledgeItem.id))) or 0
            overview.concepts_count = total_items
        else:
            total_items = await db.scalar(select(func.count(KnowledgeItem.id))) or 0
            overview = ReadingOverview(
                reading_days=1, books_count=1, concepts_count=total_items,
                ai_comments=1 if analysis else 0, progress={},
            )
            db.add(overview)

    except Exception as e:
        logger.warning(f"同步知识体系表失败（不影响主流程）: {e}")

    await db.flush()
    return ids




# ==================== 直接入库（不经 AI 分析） ====================

@router.post("/save-direct")
async def save_direct(data: ChatSaveRequest, db: AsyncSession = Depends(get_db)):
    """直接保存内容到数据库，不经过 AI 分析
    
    适用场景：用户只想入库原文，后续再补充 AI 分析
    """
    saved_items = {}
    save_types = data.save_to_types or [data.system_type]
    today = date.today()
    
    for sys_type in save_types:
        if sys_type == "reading":
            saved_items["reading"] = await _save_reading_data(
                db, today, data.title, data.original_content,
                data.analysis_markdown or "", data.structured_data or {}, data.images
            )
        elif sys_type == "diary" or sys_type == "note":
            saved_items[sys_type] = await _save_diary_data(
                db, today, data.title, data.original_content,
                data.analysis_markdown or "", data.structured_data or {}, data.images
            )
        elif sys_type == "investment":
            saved_items["investment"] = await _save_investment_data(
                db, today, data.title, data.original_content,
                data.analysis_markdown or "", data.structured_data or {}
            )
    
    await db.flush()
    
    return ChatSaveResponse(
        success=True,
        message="直接入库成功",
        saved_items=saved_items,
        profile_updated=[],
    )


# ==================== 对话日志 ====================

@router.get("/logs", response_model=ListResponse)
async def list_conversation_logs(
    system_type: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取对话日志列表"""
    query = select(ConversationLog)
    count_query = select(func.count(ConversationLog.id))
    
    if system_type:
        query = query.where(ConversationLog.system_type == system_type)
        count_query = count_query.where(ConversationLog.system_type == system_type)
    
    total = await db.scalar(count_query)
    result = await db.execute(
        query.order_by(desc(ConversationLog.created_at)).offset(skip).limit(limit)
    )
    items = [ConversationLogResponse.model_validate(log) for log in result.scalars()]
    return ListResponse(total=total or 0, items=items)


# ==================== AI 聊天历史记录 ====================

@router.get("/chat-history")
async def list_chat_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """获取近7天的 AI 聊天分析历史"""
    from datetime import timedelta, datetime as dt
    from app.models.chat_history import ChatHistory

    cutoff = dt.now() - timedelta(days=7)
    query = select(ChatHistory).where(ChatHistory.created_at >= cutoff)
    count_q = select(func.count(ChatHistory.id)).where(ChatHistory.created_at >= cutoff)

    total = await db.scalar(count_q) or 0
    result = await db.execute(
        query.order_by(desc(ChatHistory.created_at)).offset(skip).limit(limit)
    )
    items = []
    for h in result.scalars():
        items.append({
            "id": h.id,
            "title": h.title,
            "system_type": h.system_type,
            "content_preview": (h.content or "")[:80],
            "analysis_preview": (h.analysis_markdown or "")[:120],
            "saved_to": h.saved_to,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        })
    return {"total": total, "items": items}


@router.get("/chat-history/{history_id}")
async def get_chat_history_detail(
    history_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取单条聊天历史详情"""
    from app.models.chat_history import ChatHistory
    h = await db.scalar(select(ChatHistory).where(ChatHistory.id == history_id))
    if not h:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {
        "id": h.id,
        "title": h.title,
        "system_type": h.system_type,
        "content": h.content,
        "analysis_markdown": h.analysis_markdown,
        "structured_data": h.structured_data,
        "profile_updates": h.profile_updates,
        "saved_to": h.saved_to,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


@router.post("/chat-history")
async def save_chat_history(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """保存一条聊天历史"""
    from app.models.chat_history import ChatHistory
    h = ChatHistory(
        content=data.get("content", ""),
        title=data.get("title"),
        system_type=data.get("system_type"),
        analysis_markdown=data.get("analysis_markdown"),
        structured_data=data.get("structured_data"),
        profile_updates=data.get("profile_updates"),
        saved_to=data.get("saved_to"),
    )
    db.add(h)
    await db.flush()
    await db.refresh(h)
    return {"id": h.id, "created_at": h.created_at.isoformat()}


@router.delete("/chat-history/{history_id}")
async def delete_chat_history(
    history_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除一条聊天历史"""
    from app.models.chat_history import ChatHistory
    h = await db.scalar(select(ChatHistory).where(ChatHistory.id == history_id))
    if h:
        await db.delete(h)
    return {"ok": True}


# ==================== 内容转发布（AI 改写） ====================

REWRITE_PROMPTS: dict[str, str] = {
    "xiaohongshu": """你是一位资深小红书博主，擅长将内容改写为小红书风格。

要求：
1. 标题要吸引眼球，使用小红书常见句式（如"我发现了…"、"原来…才是关键"、"这个方法真的绝了"）
2. 正文用口语化表达，像在和朋友聊天
3. 适当使用 emoji 表情增加活泼感
4. 分段短小精悍，每段不超过3行
5. 结尾加互动引导（"你们觉得呢？""欢迎留言讨论~"）
6. 加上5-8个热门标签（#开头）
7. 控制在800字以内

请直接输出改写后的完整内容，不要加任何说明。""",

    "gongzhonghao": """你是一位公众号资深编辑，擅长将内容改写为微信公众号文章风格。

要求：
1. 标题有深度，能引发思考
2. 开头用一个引人入胜的故事或问题hook读者
3. 结构清晰，用小标题分节
4. 语言兼具深度和可读性，不要太学术也不要太口语
5. 结尾有总结金句或行动建议
6. 字数1000-2000字

请直接输出改写后的完整内容，不要加任何说明。""",

    "travel": """你是一位旅行博主，擅长将内容改写为游记风格。

要求：
1. 以第一人称叙述，带有感受和情绪
2. 注重画面感描写，让读者有代入感
3. 穿插个人感悟和推荐
4. 适当加入实用信息（时间、地点、费用等）
5. 结尾有旅行建议或感悟总结

请直接输出改写后的完整内容，不要加任何说明。""",

    "thread": """你是一位擅长写推特/帖子的自媒体人，擅长将内容改写为连贴风格。

要求：
1. 开头第一条要抓人眼球
2. 每条140-280字，逻辑独立但串联紧密
3. 使用编号（1/ 2/ 3/...）
4. 核心观点加粗或大写强调
5. 最后一条做总结+互动引导
6. 一共5-10条

请直接输出改写后的完整内容，不要加任何说明。""",
}


@router.post("/rewrite")
async def rewrite_content(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """将内容改写为不同平台风格"""
    content = data.get("content", "")
    platform = data.get("platform", "xiaohongshu")
    
    if not content:
        raise HTTPException(status_code=400, detail="内容不能为空")
    
    system_prompt = REWRITE_PROMPTS.get(platform)
    if not system_prompt:
        raise HTTPException(status_code=400, detail=f"不支持的平台: {platform}")
    
    config = await get_active_ai_config(db)
    if not config:
        raise HTTPException(status_code=400, detail="未配置 AI 模型")
    
    import httpx
    from app.services.ai_service import _build_request
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请将以下内容改写：\n\n{content}"},
    ]
    
    url, headers, payload = _build_request(config, messages)
    payload["max_tokens"] = min(config.max_tokens, 4096)
    
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            rewritten = result["choices"][0]["message"]["content"]
            tokens_used = result.get("usage", {}).get("total_tokens", 0)
        
        return {
            "platform": platform,
            "rewritten": rewritten,
            "tokens_used": tokens_used,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"改写失败: {str(e)}")
