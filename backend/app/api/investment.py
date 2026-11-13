"""投资模块 API"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.investment import (
    InvestmentReflection,
    InvestmentPrinciple,
    InvestmentCognition,
    InvestmentDecision,
    InvestmentEmotion,
    InvestmentKnowledge,
    InvestmentQA,
)
from app.schemas.investment import (
    ReflectionCreate, ReflectionResponse, ReflectionListItem,
    PrincipleCreate, PrincipleUpdate, PrincipleResponse, PrincipleListItem,
    CognitionCreate, CognitionResponse,
    DecisionCreate, DecisionUpdate, DecisionResponse,
    EmotionCreate, EmotionResponse,
    KnowledgeCreate, KnowledgeResponse,
    QACreate, QAUpdate, QAResponse, QAListItem,
    InvestmentOverview, ListResponse,
)

router = APIRouter(prefix="/investment", tags=["投资模块"])


# ==================== 总览 ====================

@router.get("/overview", response_model=InvestmentOverview)
async def get_overview(db: AsyncSession = Depends(get_db)):
    """获取投资系统总览数据"""
    
    # 统计各表数量
    reflection_count = await db.scalar(select(func.count(InvestmentReflection.id)))
    principle_count = await db.scalar(
        select(func.count(InvestmentPrinciple.id)).where(InvestmentPrinciple.is_active == True)
    )
    cognition_count = await db.scalar(select(func.count(InvestmentCognition.id)))
    decision_count = await db.scalar(select(func.count(InvestmentDecision.id)))
    emotion_count = await db.scalar(select(func.count(InvestmentEmotion.id)))
    knowledge_count = await db.scalar(select(func.count(InvestmentKnowledge.id)))
    qa_count = await db.scalar(select(func.count(InvestmentQA.id)))
    
    # 原则分类统计
    principles_by_category = {}
    result = await db.execute(
        select(InvestmentPrinciple.category, func.count(InvestmentPrinciple.id))
        .where(InvestmentPrinciple.is_active == True)
        .group_by(InvestmentPrinciple.category)
    )
    for row in result:
        principles_by_category[row[0]] = row[1]
    
    # 情绪类型统计
    emotions_by_type = {}
    result = await db.execute(
        select(InvestmentEmotion.emotion, func.count(InvestmentEmotion.id))
        .group_by(InvestmentEmotion.emotion)
    )
    for row in result:
        emotions_by_type[row[0]] = row[1]
    
    # 决策操作统计
    decisions_by_action = {}
    result = await db.execute(
        select(InvestmentDecision.action, func.count(InvestmentDecision.id))
        .group_by(InvestmentDecision.action)
    )
    for row in result:
        decisions_by_action[row[0]] = row[1]
    
    # Q&A 分类统计
    qa_by_category = {}
    result = await db.execute(
        select(InvestmentQA.category, func.count(InvestmentQA.id))
        .where(InvestmentQA.category.isnot(None))
        .group_by(InvestmentQA.category)
    )
    for row in result:
        qa_by_category[row[0]] = row[1]
    
    # 最近原则
    result = await db.execute(
        select(InvestmentPrinciple)
        .where(InvestmentPrinciple.is_active == True)
        .order_by(desc(InvestmentPrinciple.created_at))
        .limit(5)
    )
    recent_principles = [PrincipleListItem.model_validate(p) for p in result.scalars()]
    
    # 最近认知迭代
    result = await db.execute(
        select(InvestmentCognition)
        .order_by(desc(InvestmentCognition.created_at))
        .limit(5)
    )
    recent_cognitions = [CognitionResponse.model_validate(c) for c in result.scalars()]
    
    # 最近 Q&A
    result = await db.execute(
        select(InvestmentQA)
        .order_by(desc(InvestmentQA.created_at))
        .limit(5)
    )
    recent_qa = [QAListItem.model_validate(q) for q in result.scalars()]
    
    return InvestmentOverview(
        reflection_count=reflection_count or 0,
        principle_count=principle_count or 0,
        cognition_count=cognition_count or 0,
        decision_count=decision_count or 0,
        emotion_count=emotion_count or 0,
        knowledge_count=knowledge_count or 0,
        qa_count=qa_count or 0,
        principles_by_category=principles_by_category,
        emotions_by_type=emotions_by_type,
        decisions_by_action=decisions_by_action,
        qa_by_category=qa_by_category,
        recent_principles=recent_principles,
        recent_cognitions=recent_cognitions,
        recent_qa=recent_qa,
    )


# ==================== 反思记录 ====================

@router.get("/reflections", response_model=ListResponse)
async def list_reflections(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取反思记录列表"""
    total = await db.scalar(select(func.count(InvestmentReflection.id)))
    result = await db.execute(
        select(InvestmentReflection)
        .order_by(desc(InvestmentReflection.date))
        .offset(skip)
        .limit(limit)
    )
    items = [ReflectionListItem.model_validate(r) for r in result.scalars()]
    return ListResponse(total=total or 0, items=items)


@router.get("/reflections/{reflection_id}", response_model=ReflectionResponse)
async def get_reflection(reflection_id: int, db: AsyncSession = Depends(get_db)):
    """获取反思记录详情"""
    result = await db.execute(
        select(InvestmentReflection).where(InvestmentReflection.id == reflection_id)
    )
    reflection = result.scalar_one_or_none()
    if not reflection:
        raise HTTPException(status_code=404, detail="反思记录不存在")
    return ReflectionResponse.model_validate(reflection)


@router.post("/reflections", response_model=ReflectionResponse)
async def create_reflection(data: ReflectionCreate, db: AsyncSession = Depends(get_db)):
    """创建反思记录"""
    reflection = InvestmentReflection(**data.model_dump())
    db.add(reflection)
    await db.flush()
    await db.refresh(reflection)
    return ReflectionResponse.model_validate(reflection)


@router.delete("/reflections/{reflection_id}")
async def delete_reflection(reflection_id: int, db: AsyncSession = Depends(get_db)):
    """删除反思记录"""
    result = await db.execute(
        select(InvestmentReflection).where(InvestmentReflection.id == reflection_id)
    )
    reflection = result.scalar_one_or_none()
    if not reflection:
        raise HTTPException(status_code=404, detail="反思记录不存在")
    await db.delete(reflection)
    await db.flush()
    return {"message": "删除成功"}


# ==================== 投资原则 ====================

@router.get("/principles", response_model=ListResponse)
async def list_principles(
    category: Optional[str] = None,
    active_only: bool = True,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取投资原则列表"""
    query = select(InvestmentPrinciple)
    count_query = select(func.count(InvestmentPrinciple.id))
    
    if active_only:
        query = query.where(InvestmentPrinciple.is_active == True)
        count_query = count_query.where(InvestmentPrinciple.is_active == True)
    if category:
        query = query.where(InvestmentPrinciple.category == category)
        count_query = count_query.where(InvestmentPrinciple.category == category)
    
    total = await db.scalar(count_query)
    result = await db.execute(
        query.order_by(desc(InvestmentPrinciple.created_at)).offset(skip).limit(limit)
    )
    items = [PrincipleResponse.model_validate(p) for p in result.scalars()]
    return ListResponse(total=total or 0, items=items)


@router.get("/principles/{principle_id}", response_model=PrincipleResponse)
async def get_principle(principle_id: int, db: AsyncSession = Depends(get_db)):
    """获取投资原则详情"""
    result = await db.execute(
        select(InvestmentPrinciple).where(InvestmentPrinciple.id == principle_id)
    )
    principle = result.scalar_one_or_none()
    if not principle:
        raise HTTPException(status_code=404, detail="投资原则不存在")
    return PrincipleResponse.model_validate(principle)


@router.post("/principles", response_model=PrincipleResponse)
async def create_principle(data: PrincipleCreate, db: AsyncSession = Depends(get_db)):
    """创建投资原则"""
    principle = InvestmentPrinciple(**data.model_dump())
    db.add(principle)
    await db.flush()
    await db.refresh(principle)
    return PrincipleResponse.model_validate(principle)


@router.put("/principles/{principle_id}", response_model=PrincipleResponse)
async def update_principle(
    principle_id: int,
    data: PrincipleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新投资原则（会增加版本号）"""
    result = await db.execute(
        select(InvestmentPrinciple).where(InvestmentPrinciple.id == principle_id)
    )
    principle = result.scalar_one_or_none()
    if not principle:
        raise HTTPException(status_code=404, detail="投资原则不存在")
    
    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(principle, key, value)
        principle.version += 1
    
    await db.flush()
    await db.refresh(principle)
    return PrincipleResponse.model_validate(principle)


# ==================== 认知迭代 ====================

@router.get("/cognitions", response_model=ListResponse)
async def list_cognitions(
    category: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取认知迭代列表"""
    query = select(InvestmentCognition)
    count_query = select(func.count(InvestmentCognition.id))
    
    if category:
        query = query.where(InvestmentCognition.category == category)
        count_query = count_query.where(InvestmentCognition.category == category)
    
    total = await db.scalar(count_query)
    result = await db.execute(
        query.order_by(desc(InvestmentCognition.date)).offset(skip).limit(limit)
    )
    items = [CognitionResponse.model_validate(c) for c in result.scalars()]
    return ListResponse(total=total or 0, items=items)


@router.post("/cognitions", response_model=CognitionResponse)
async def create_cognition(data: CognitionCreate, db: AsyncSession = Depends(get_db)):
    """创建认知迭代记录"""
    cognition = InvestmentCognition(**data.model_dump())
    db.add(cognition)
    await db.flush()
    await db.refresh(cognition)
    return CognitionResponse.model_validate(cognition)


# ==================== 决策日志 ====================

@router.get("/decisions", response_model=ListResponse)
async def list_decisions(
    action: Optional[str] = None,
    target: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取决策日志列表"""
    query = select(InvestmentDecision)
    count_query = select(func.count(InvestmentDecision.id))
    
    if action:
        query = query.where(InvestmentDecision.action == action)
        count_query = count_query.where(InvestmentDecision.action == action)
    if target:
        query = query.where(InvestmentDecision.target.contains(target))
        count_query = count_query.where(InvestmentDecision.target.contains(target))
    
    total = await db.scalar(count_query)
    result = await db.execute(
        query.order_by(desc(InvestmentDecision.date)).offset(skip).limit(limit)
    )
    items = [DecisionResponse.model_validate(d) for d in result.scalars()]
    return ListResponse(total=total or 0, items=items)


@router.post("/decisions", response_model=DecisionResponse)
async def create_decision(data: DecisionCreate, db: AsyncSession = Depends(get_db)):
    """创建决策日志"""
    decision = InvestmentDecision(**data.model_dump())
    db.add(decision)
    await db.flush()
    await db.refresh(decision)
    return DecisionResponse.model_validate(decision)


@router.put("/decisions/{decision_id}", response_model=DecisionResponse)
async def update_decision(
    decision_id: int,
    data: DecisionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新决策日志（复盘）"""
    result = await db.execute(
        select(InvestmentDecision).where(InvestmentDecision.id == decision_id)
    )
    decision = result.scalar_one_or_none()
    if not decision:
        raise HTTPException(status_code=404, detail="决策记录不存在")
    
    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(decision, key, value)
    
    await db.flush()
    await db.refresh(decision)
    return DecisionResponse.model_validate(decision)


# ==================== 情绪复盘 ====================

@router.get("/emotions", response_model=ListResponse)
async def list_emotions(
    emotion: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取情绪复盘列表"""
    query = select(InvestmentEmotion)
    count_query = select(func.count(InvestmentEmotion.id))
    
    if emotion:
        query = query.where(InvestmentEmotion.emotion == emotion)
        count_query = count_query.where(InvestmentEmotion.emotion == emotion)
    
    total = await db.scalar(count_query)
    result = await db.execute(
        query.order_by(desc(InvestmentEmotion.date)).offset(skip).limit(limit)
    )
    items = [EmotionResponse.model_validate(e) for e in result.scalars()]
    return ListResponse(total=total or 0, items=items)


@router.post("/emotions", response_model=EmotionResponse)
async def create_emotion(data: EmotionCreate, db: AsyncSession = Depends(get_db)):
    """创建情绪复盘记录"""
    emotion = InvestmentEmotion(**data.model_dump())
    db.add(emotion)
    await db.flush()
    await db.refresh(emotion)
    return EmotionResponse.model_validate(emotion)


# ==================== 投资知识 ====================

@router.get("/knowledge", response_model=ListResponse)
async def list_knowledge(
    category: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """获取投资知识列表"""
    query = select(InvestmentKnowledge)
    count_query = select(func.count(InvestmentKnowledge.id))
    
    if category:
        query = query.where(InvestmentKnowledge.category == category)
        count_query = count_query.where(InvestmentKnowledge.category == category)
    
    total = await db.scalar(count_query)
    result = await db.execute(
        query.order_by(InvestmentKnowledge.category, InvestmentKnowledge.name)
        .offset(skip).limit(limit)
    )
    items = [KnowledgeResponse.model_validate(k) for k in result.scalars()]
    return ListResponse(total=total or 0, items=items)


@router.post("/knowledge", response_model=KnowledgeResponse)
async def create_knowledge(data: KnowledgeCreate, db: AsyncSession = Depends(get_db)):
    """创建投资知识"""
    # 检查是否已存在
    result = await db.execute(
        select(InvestmentKnowledge).where(InvestmentKnowledge.name == data.name)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="该知识点已存在")
    
    knowledge = InvestmentKnowledge(**data.model_dump())
    db.add(knowledge)
    await db.flush()
    await db.refresh(knowledge)
    return KnowledgeResponse.model_validate(knowledge)


# ==================== 知识分类 ====================

@router.get("/knowledge/categories")
async def get_knowledge_categories(db: AsyncSession = Depends(get_db)):
    """获取知识分类列表"""
    result = await db.execute(
        select(InvestmentKnowledge.category, func.count(InvestmentKnowledge.id))
        .group_by(InvestmentKnowledge.category)
        .order_by(InvestmentKnowledge.category)
    )
    return [{"category": row[0], "count": row[1]} for row in result]


@router.get("/principles/categories")
async def get_principle_categories(db: AsyncSession = Depends(get_db)):
    """获取原则分类列表"""
    result = await db.execute(
        select(InvestmentPrinciple.category, func.count(InvestmentPrinciple.id))
        .where(InvestmentPrinciple.is_active == True)
        .group_by(InvestmentPrinciple.category)
        .order_by(InvestmentPrinciple.category)
    )
    return [{"category": row[0], "count": row[1]} for row in result]


# ==================== Q&A 问答 ====================

@router.get("/qa", response_model=ListResponse)
async def list_qa(
    category: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取 Q&A 列表"""
    query = select(InvestmentQA)
    count_query = select(func.count(InvestmentQA.id))
    
    if category:
        query = query.where(InvestmentQA.category == category)
        count_query = count_query.where(InvestmentQA.category == category)
    if is_resolved is not None:
        query = query.where(InvestmentQA.is_resolved == is_resolved)
        count_query = count_query.where(InvestmentQA.is_resolved == is_resolved)
    
    total = await db.scalar(count_query)
    result = await db.execute(
        query.order_by(desc(InvestmentQA.date)).offset(skip).limit(limit)
    )
    items = [QAResponse.model_validate(q) for q in result.scalars()]
    return ListResponse(total=total or 0, items=items)


@router.get("/qa/{qa_id}", response_model=QAResponse)
async def get_qa(qa_id: int, db: AsyncSession = Depends(get_db)):
    """获取 Q&A 详情"""
    result = await db.execute(
        select(InvestmentQA).where(InvestmentQA.id == qa_id)
    )
    qa = result.scalar_one_or_none()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A 不存在")
    return QAResponse.model_validate(qa)


@router.post("/qa", response_model=QAResponse)
async def create_qa(data: QACreate, db: AsyncSession = Depends(get_db)):
    """创建 Q&A"""
    qa = InvestmentQA(**data.model_dump())
    db.add(qa)
    await db.flush()
    await db.refresh(qa)
    return QAResponse.model_validate(qa)


@router.post("/qa/batch", response_model=list[QAResponse])
async def create_qa_batch(data: list[QACreate], db: AsyncSession = Depends(get_db)):
    """批量创建 Q&A"""
    qa_list = []
    for item in data:
        qa = InvestmentQA(**item.model_dump())
        db.add(qa)
        qa_list.append(qa)
    await db.flush()
    for qa in qa_list:
        await db.refresh(qa)
    return [QAResponse.model_validate(q) for q in qa_list]


@router.put("/qa/{qa_id}", response_model=QAResponse)
async def update_qa(
    qa_id: int,
    data: QAUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新 Q&A（追问、更新解答等）"""
    result = await db.execute(
        select(InvestmentQA).where(InvestmentQA.id == qa_id)
    )
    qa = result.scalar_one_or_none()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A 不存在")
    
    update_data = data.model_dump(exclude_unset=True)
    if update_data:
        for key, value in update_data.items():
            setattr(qa, key, value)
    
    await db.flush()
    await db.refresh(qa)
    return QAResponse.model_validate(qa)


@router.delete("/qa/{qa_id}")
async def delete_qa(qa_id: int, db: AsyncSession = Depends(get_db)):
    """删除 Q&A"""
    result = await db.execute(
        select(InvestmentQA).where(InvestmentQA.id == qa_id)
    )
    qa = result.scalar_one_or_none()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A 不存在")
    
    await db.delete(qa)
    await db.flush()
    return {"message": "删除成功"}


@router.get("/qa/categories/list")
async def get_qa_categories(db: AsyncSession = Depends(get_db)):
    """获取 Q&A 分类列表"""
    result = await db.execute(
        select(InvestmentQA.category, func.count(InvestmentQA.id))
        .where(InvestmentQA.category.isnot(None))
        .group_by(InvestmentQA.category)
        .order_by(InvestmentQA.category)
    )
    return [{"category": row[0], "count": row[1]} for row in result]
