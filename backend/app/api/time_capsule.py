"""时光胶囊信件 API"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.time_capsule import TimeCapsuleLetter, TimeCapsuleTemplate
from app.models.ai_config import AIConfig
from app.services.ai_service import get_api_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/time-capsule", tags=["时光胶囊"])


async def _get_ai_config(db: AsyncSession):
    """获取当前生效的 AI 配置（优先 is_active，其次取第一条）"""
    result = await db.execute(select(AIConfig).where(AIConfig.is_active == True).limit(1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        result = await db.execute(select(AIConfig).limit(1))
        cfg = result.scalar_one_or_none()
    return cfg


#======================== Schemas ========================

class GoalItem(BaseModel):
    text: str
    type: str = "self"  # self | ai
    completed: Optional[bool] = None
    ai_evaluation: Optional[str] = None
    ai_score: Optional[float] = None


class LetterCreate(BaseModel):
    title: str
    recipient: str = "未来的自己"
    content: str
    goals: Optional[List[GoalItem]] = None
    images: Optional[List[str]] = None
    open_date: date
    remind_days: int = 3
    template_id: Optional[str] = None
    tags: Optional[List[str]] = None


class LetterUpdate(BaseModel):
    title: Optional[str] = None
    recipient: Optional[str] = None
    content: Optional[str] = None
    goals: Optional[List[GoalItem]] = None
    images: Optional[List[str]] = None
    open_date: Optional[date] = None
    remind_days: Optional[int] = None
    tags: Optional[List[str]] = None


class LetterReflection(BaseModel):
    reflection: str


class GoalEvaluation(BaseModel):
    """用户手动评估目标"""
    goal_index: int
    completed: bool


class TemplateCreate(BaseModel):
    key: str
    name: str
    description: str
    icon: str = "✉️"
    sections: List[dict]
    suggested_goals: Optional[List[str]] = None
    category: str = "general"
    sort_order: int = 0


# ======================== 信件 CRUD ========================

@router.post("/letters", summary="创建信件")
async def create_letter(data: LetterCreate, db: AsyncSession = Depends(get_db)):
    """写一封给未来的信"""
    letter = TimeCapsuleLetter(
        title=data.title,
        recipient=data.recipient,
        content=data.content,
        goals=[g.model_dump() for g in data.goals] if data.goals else None,
        images=data.images,
        seal_date=date.today(),
        open_date=data.open_date,
        remind_days=data.remind_days,
        template_id=data.template_id,
        tags=data.tags,
        status="sealed",
    )
    db.add(letter)
    await db.flush()
    await db.refresh(letter)
    return {"id": letter.id, "message": "信件已封存，将在指定日期开封"}


@router.get("/letters", summary="获取信件列表")
async def list_letters(
    status: Optional[str] = Query(None, description="sealed/pending/opened"),
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """获取所有信件，支持按状态筛选"""
    query = select(TimeCapsuleLetter).order_by(desc(TimeCapsuleLetter.created_at))
    if status:
        query = query.where(TimeCapsuleLetter.status == status)
    
    # 总数
    count_query = select(func.count()).select_from(TimeCapsuleLetter)
    if status:
        count_query = count_query.where(TimeCapsuleLetter.status == status)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    result = await db.execute(query.offset(skip).limit(limit))
    letters = result.scalars().all()
    
    today = date.today()
    items = []
    for letter in letters:
        days_until = (letter.open_date - today).days
        items.append({
            "id": letter.id,
            "title": letter.title,
            "recipient": letter.recipient,
            "seal_date": letter.seal_date.isoformat(),
            "open_date": letter.open_date.isoformat(),
            "status": letter.status,
            "days_until_open": days_until,
            "template_id": letter.template_id,
            "tags": letter.tags,
            "goals_count": len(letter.goals) if letter.goals else 0,
            "has_reflection": bool(letter.reflection),
            "has_ai_review": bool(letter.ai_review),
            "created_at": letter.created_at.isoformat(),
        })
    
    return {"total": total, "items": items}


@router.get("/letters/pending", summary="获取待开封信件（登录检测用）")
async def get_pending_letters(db: AsyncSession = Depends(get_db)):
    """检测当前是否有可开封的信件（open_date 前后 remind_days 天内）"""
    today = date.today()
    
    # 查找状态为 sealed 且 open_date 在 [today - remind_days, today + remind_days] 范围内的信件
    result = await db.execute(
        select(TimeCapsuleLetter).where(
            TimeCapsuleLetter.status.in_(["sealed", "pending"])
        )
    )
    letters = result.scalars().all()
    
    pending = []
    for letter in letters:
        days_diff = (letter.open_date - today).days
        # 在提醒窗口内：解封日前remind_days 天到解封日后 remind_days 天
        if -letter.remind_days <= days_diff <= letter.remind_days:
            # 更新状态为 pending（如果还是 sealed）
            if letter.status == "sealed":
                letter.status = "pending"
            pending.append({
                "id": letter.id,
                "title": letter.title,
                "recipient": letter.recipient,
                "seal_date": letter.seal_date.isoformat(),
                "open_date": letter.open_date.isoformat(),
                "days_diff": days_diff,  # 负数=已过解封日，正数=还未到
                "content": letter.content,
                "goals": letter.goals,
                "images": letter.images,
                "template_id": letter.template_id,
            })
    
    return {"count": len(pending), "letters": pending}


@router.get("/letters/{letter_id}", summary="获取信件详情")
async def get_letter(letter_id: int, db: AsyncSession = Depends(get_db)):
    """获取单封信件详情（已开封的信件可查看全文）"""
    result = await db.execute(
        select(TimeCapsuleLetter).where(TimeCapsuleLetter.id == letter_id)
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=404, detail="信件不存在")
    
    today = date.today()
    days_until = (letter.open_date - today).days
    
    data = {
        "id": letter.id,
        "title": letter.title,
        "recipient": letter.recipient,
        "seal_date": letter.seal_date.isoformat(),
        "open_date": letter.open_date.isoformat(),
        "status": letter.status,
        "days_until_open": days_until,
        "remind_days": letter.remind_days,
        "template_id": letter.template_id,
        "tags": letter.tags,
        "created_at": letter.created_at.isoformat(),
    }
    
    # 已开封或在提醒窗口内 → 展示全文
    if letter.status == "opened" or days_until <= letter.remind_days:
        data.update({
            "content": letter.content,
            "goals": letter.goals,
            "images": letter.images,
            "reflection": letter.reflection,
            "reflection_at": letter.reflection_at.isoformat() if letter.reflection_at else None,
            "ai_review": letter.ai_review,
            "ai_review_at": letter.ai_review_at.isoformat() if letter.ai_review_at else None,
            "opened_at": letter.opened_at.isoformat() if letter.opened_at else None,
        })
    else:
        # 未到期 → 只展示基础信息，内容隐藏
        data["content_preview"] = letter.content[:50] + "..." if len(letter.content) > 50 else "***"
        data["is_locked"] = True
    
    return data


@router.post("/letters/{letter_id}/open", summary="开封信件")
async def open_letter(letter_id: int, db: AsyncSession = Depends(get_db)):
    """正式开封一封信"""
    result = await db.execute(
        select(TimeCapsuleLetter).where(TimeCapsuleLetter.id == letter_id)
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=404, detail="信件不存在")
    
    if letter.status == "opened":
        return {"message": "信件已经开封过了", "opened_at": letter.opened_at.isoformat()}
    
    letter.status = "opened"
    letter.opened_at = datetime.now()
    
    return {
        "message": "信件已开封",
        "content": letter.content,
        "goals": letter.goals,
        "images": letter.images,
        "seal_date": letter.seal_date.isoformat(),
        "open_date": letter.open_date.isoformat(),
        "opened_at": letter.opened_at.isoformat(),
    }


@router.post("/letters/{letter_id}/reflection", summary="写开封感想")
async def add_reflection(
    letter_id: int, data: LetterReflection, db: AsyncSession = Depends(get_db)
):
    """开封后写下当前的感想"""
    result = await db.execute(
        select(TimeCapsuleLetter).where(TimeCapsuleLetter.id == letter_id)
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=404, detail="信件不存在")
    if letter.status != "opened":
        raise HTTPException(status_code=400, detail="只有已开封的信件可以写感想")
    
    letter.reflection = data.reflection
    letter.reflection_at = datetime.now()
    
    return {"message": "感想已保存", "reflection_at": letter.reflection_at.isoformat()}


@router.post("/letters/{letter_id}/evaluate-goal", summary="手动评估目标")
async def evaluate_goal(
    letter_id: int, data: GoalEvaluation, db: AsyncSession = Depends(get_db)
):
    """用户手动勾选目标完成状态"""
    result = await db.execute(
        select(TimeCapsuleLetter).where(TimeCapsuleLetter.id == letter_id)
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=404, detail="信件不存在")
    if not letter.goals or data.goal_index >= len(letter.goals):
        raise HTTPException(status_code=400, detail="目标索引无效")
    
    goals = list(letter.goals)  # 创建副本
    goals[data.goal_index]["completed"] = data.completed
    letter.goals = goals
    
    return {"message": "目标评估已更新", "goals": letter.goals}


@router.delete("/letters/{letter_id}", summary="删除信件")
async def delete_letter(letter_id: int, db: AsyncSession = Depends(get_db)):
    """删除一封信件"""
    result = await db.execute(
        select(TimeCapsuleLetter).where(TimeCapsuleLetter.id == letter_id)
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=404, detail="信件不存在")
    
    await db.delete(letter)
    return {"message": "信件已删除"}


# ======================== Dashboard统计 ========================

@router.get("/dashboard", summary="Dashboard倒计时数据")
async def get_dashboard_data(db: AsyncSession = Depends(get_db)):
    """获取Dashboard 展示的倒计时信息"""
    today = date.today()
    
    # 查找最近一封未开封的信件
    result = await db.execute(
        select(TimeCapsuleLetter)
        .where(TimeCapsuleLetter.status.in_(["sealed", "pending"]))
        .order_by(TimeCapsuleLetter.open_date)
        .limit(1)
    )
    nearest = result.scalar_one_or_none()
    
    # 统计
    count_result = await db.execute(
        select(func.count()).select_from(TimeCapsuleLetter)
    )
    total = count_result.scalar() or 0
    
    sealed_result = await db.execute(
        select(func.count()).select_from(TimeCapsuleLetter)
        .where(TimeCapsuleLetter.status.in_(["sealed", "pending"]))
    )
    sealed_count = sealed_result.scalar() or 0
    
    opened_result = await db.execute(
        select(func.count()).select_from(TimeCapsuleLetter)
        .where(TimeCapsuleLetter.status == "opened")
    )
    opened_count = opened_result.scalar() or 0
    
    data = {
        "total": total,
        "sealed_count": sealed_count,
        "opened_count": opened_count,
        "nearest_letter": None,
    }
    
    if nearest:
        days_until = (nearest.open_date - today).days
        data["nearest_letter"] = {
            "id": nearest.id,
            "title": nearest.title,
            "recipient": nearest.recipient,
            "open_date": nearest.open_date.isoformat(),
            "days_until": days_until,
            "seal_date": nearest.seal_date.isoformat(),
        }
    
    return data


# ======================== Timeline 集成 ========================

@router.get("/timeline", summary="获取时光胶囊时间线事件")
async def get_timeline_events(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """生成 Timeline 事件节点（写信节点 + 开封节点）"""
    result = await db.execute(
        select(TimeCapsuleLetter).order_by(desc(TimeCapsuleLetter.created_at))
        .offset(skip).limit(limit)
    )
    letters = result.scalars().all()
    
    events = []
    for letter in letters:
        # 写信节点
        events.append({
            "type": "capsule_sealed",
            "date": letter.seal_date.isoformat(),
            "title": f"封存信件：{letter.title}",
            "subtitle": f"写给{letter.recipient}，将在 {letter.open_date.isoformat()} 开封",
            "letter_id": letter.id,
            "icon": "capsule",
        })
        # 开封节点（如果已开封）
        if letter.status == "opened" and letter.opened_at:
            events.append({
                "type": "capsule_opened",
                "date": letter.opened_at.strftime("%Y-%m-%d"),
                "title": f"开封信件：{letter.title}",
                "subtitle": f"来自 {letter.seal_date.isoformat()} 的你",
                "letter_id": letter.id,
                "icon": "capsule_open",
                "has_reflection": bool(letter.reflection),
                "has_ai_review": bool(letter.ai_review),
            })
    
    # 按日期倒序
    events.sort(key=lambda e: e["date"], reverse=True)
    return {"events": events}


# ======================== 模板系统 ========================

@router.get("/templates", summary="获取信件模板列表")
async def list_templates(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取可用的写信模板"""
    query = select(TimeCapsuleTemplate).order_by(TimeCapsuleTemplate.sort_order)
    if category:
        query = query.where(TimeCapsuleTemplate.category == category)
    
    result = await db.execute(query)
    templates = result.scalars().all()
    
    items = []
    for t in templates:
        items.append({
            "id": t.id,
            "key": t.key,
            "name": t.name,
            "description": t.description,
            "icon": t.icon,
            "sections": t.sections,
            "suggested_goals": t.suggested_goals,
            "category": t.category,
            "is_system": t.is_system,
        })
    
    return {"templates": items}


@router.get("/templates/{template_key}", summary="获取单个模板详情")
async def get_template(template_key: str, db: AsyncSession = Depends(get_db)):
    """获取模板详细内容"""
    result = await db.execute(
        select(TimeCapsuleTemplate).where(TimeCapsuleTemplate.key == template_key)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    return {
        "key": template.key,
        "name": template.name,
        "description": template.description,
        "icon": template.icon,
        "sections": template.sections,
        "suggested_goals": template.suggested_goals,
        "category": template.category,
    }


@router.post("/templates/init", summary="初始化系统预设模板")
async def init_system_templates(db: AsyncSession = Depends(get_db)):
    """初始化系统预设模板（仅在首次使用时调用）"""
    # 检查是否已有模板
    result = await db.execute(
        select(func.count()).select_from(TimeCapsuleTemplate)
        .where(TimeCapsuleTemplate.is_system == True)
    )
    count = result.scalar() or 0
    if count > 0:
        return {"message": f"系统模板已存在（{count}个），跳过初始化"}
    
    system_templates = _get_system_templates()
    for tpl_data in system_templates:
        tpl = TimeCapsuleTemplate(**tpl_data)
        db.add(tpl)
    
    await db.flush()
    return {"message": f"已初始化 {len(system_templates)} 个系统模板"}


@router.post("/templates/generate", summary="AI生成个性化模板")
async def generate_personalized_template(db: AsyncSession = Depends(get_db)):
    """基于用户历史数据（日记、心力等）AI 生成个性化模板引导"""
    import json
    import httpx
    from app.models.diary import DiaryEntry
    from app.models.wellbeing import WellbeingEntry
    from app.models.ai_config import AIConfig

    # 获取 AI 配置
    ai_config = await _get_ai_config(db)

    # 近期数据
    diary_result = await db.execute(
        select(DiaryEntry).order_by(desc(DiaryEntry.date)).limit(20)
    )
    recent_diaries = diary_result.scalars().all()

    wellbeing_result = await db.execute(
        select(WellbeingEntry).order_by(desc(WellbeingEntry.occurred_at)).limit(10)
    )
    recent_wellbeing = wellbeing_result.scalars().all()

    themes: set = set()
    for d in recent_diaries:
        if d.tags:
            themes.update(d.tags)

    def _fallback_result():
        sections = [
            {"section": "回顾此刻", "prompt": "此刻的你在忙什么？最近的生活主旋律是什么？", "placeholder": "描述你当前的生活状态..."},
            {"section": "给未来的期许", "prompt": "一年后的你，你希望在哪些方面有所改变？", "placeholder": "写下你的期望..."},
        ]
        if themes:
            sections.append({"section": "关于你最近关注的", "prompt": f"你最近在关注「{'、'.join(list(themes)[:5])}」这些主题，给未来的自己说说当下的想法？", "placeholder": "写下你对这些主题的当前思考..."})
        if recent_wellbeing:
            sections.append({"section": "心力状态记录", "prompt": "记录下此刻的心力状态，让未来的自己看看你曾经的能量水平", "placeholder": "描述你的心理状态和能量水平..."})
        return {
            "sections": sections,
            "suggested_goals": [f"在「{t}」领域持续深耕" for t in list(themes)[:3]],
            "data_summary": {"diary_count": len(recent_diaries), "wellbeing_count": len(recent_wellbeing), "themes": list(themes)[:10]},
        }

    if not ai_config:
        return _fallback_result()

    # 构建 AI Prompt
    diary_lines = []
    for d in recent_diaries[:10]:
        mood_str = f"心情{d.mood}" if d.mood else ""
        tags_str = "、".join((d.tags or [])[:3])
        preview = (d.content or "")[:80].replace("\n", " ")
        diary_lines.append(f"- {d.date} {mood_str} [{tags_str}] {preview}…")
    diary_summary = "\n".join(diary_lines) if diary_lines else "暂无日记记录"

    wb_lines = [
        f"- {wb.occurred_at} [{'成就' if wb.type == 'achievement' else '感恩'}] 强度{wb.intensity}/5: {wb.content[:60] if wb.content else ''}"
        for wb in recent_wellbeing[:5]
    ]
    wb_summary = "\n".join(wb_lines) if wb_lines else "暂无心力记录"

    ai_prompt = f"""你是一位善于倾听的时光引导师。
根据用户最近的生活数据，为他生成一份写给未来自己的信件引导模板。

【用户近期日记摘要】
{diary_summary}

【用户近期心力记录】
{wb_summary}

【关键词/标签】{', '.join(list(themes)[:8]) if themes else '暂无'}

请生成 3~5 个引导问题（section），每个问题要：
1. 贴合用户的实际生活状态和关注点
2. 有启发性，引导用户思考当下和未来
3. 语言温暖自然，口语化

以JSON格式返回，格式如下（只返回JSON，不要有其他文字）：
{{"sections": [{{"section": "板块名称", "prompt": "引导问题", "placeholder": "提示语"}}], "suggested_goals": ["目标1", "目标2"]}}"""

    try:
        headers = {"Content-Type": "application/json"}
        if ai_config.api_key:
            headers["Authorization"] = f"Bearer {ai_config.api_key}"

        payload = {
            "model": ai_config.model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "你是一位善于倾听的时光引导师，专注于帮助用户写给未来自己的信。"},
                {"role": "user", "content": ai_prompt},
            ],
            "temperature": 0.85,
            "max_tokens": 3000,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                get_api_url(ai_config),
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            result = json.loads(raw)

        return {
            "sections": result.get("sections", []),
            "suggested_goals": result.get("suggested_goals", []),
            "data_summary": {"diary_count": len(recent_diaries), "wellbeing_count": len(recent_wellbeing), "themes": list(themes)[:10]},
        }

    except Exception as e:
        logger.warning(f"AI 模板生成失败，降级为规则生成: {e}")
        return _fallback_result()


# ======================== AI 时光点评 ========================

@router.post("/letters/{letter_id}/ai-review", summary="生成 AI 时光点评")
async def generate_ai_review(letter_id: int, db: AsyncSession = Depends(get_db)):
    """AI 基于用户历史数据为开封信件生成个性化时光点评"""
    result = await db.execute(
        select(TimeCapsuleLetter).where(TimeCapsuleLetter.id == letter_id)
    )
    letter = result.scalar_one_or_none()
    if not letter:
        raise HTTPException(status_code=404, detail="信件不存在")
    if letter.status != "opened":
        raise HTTPException(status_code=400, detail="只有已开封的信件可以生成 AI 点评")
    
    # 收集用户历史数据
    from app.models.diary import DiaryEntry
    from app.models.wellbeing import WellbeingEntry
    from app.models.note import Note

    # 获取 AI 配置
    ai_config = await _get_ai_config(db)
    if not ai_config:
        raise HTTPException(status_code=400, detail="未配置 AI 服务，请先在设置中配置")
    
    # 获取写信到开封期间的数据
    seal_date = letter.seal_date
    open_date = letter.open_date
    
    # 日记摘要
    diary_result = await db.execute(
        select(DiaryEntry)
        .where(and_(DiaryEntry.date >= seal_date, DiaryEntry.date <= open_date))
        .order_by(DiaryEntry.date)
    )
    diaries = diary_result.scalars().all()
    
    # 心力记录
    wellbeing_result = await db.execute(
        select(WellbeingEntry)
        .where(and_(WellbeingEntry.occurred_at >= seal_date, WellbeingEntry.occurred_at <= open_date))
        .order_by(WellbeingEntry.occurred_at)
    )
    wellbeing_entries = wellbeing_result.scalars().all()
    
    # 读书笔记
    notes_result = await db.execute(
        select(Note)
        .where(and_(Note.reading_date >= seal_date, Note.reading_date <= open_date))
        .order_by(Note.reading_date)
    )
    notes = notes_result.scalars().all()
    
    # 构建 prompt
    prompt = _build_ai_review_prompt(letter, diaries, wellbeing_entries, notes)
    
    # 调用 AI
    try:
        import httpx
        
        headers = {"Content-Type": "application/json"}
        if ai_config.api_key:
            headers["Authorization"] = f"Bearer {ai_config.api_key}"
        
        payload = {
            "model": ai_config.model or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "你是一位温暖的时光见证者，负责为用户做个性化的时光回顾点评。你了解用户过去一段时间的生活轨迹，要给出真诚、有温度、有洞察的点评。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            # 点评要求 800 字左右，且模型会先产出思维链，需预留充足额度
            "max_tokens": 8000,
        }

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                get_api_url(ai_config),
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            ai_response = resp.json()
            review_text = ai_response["choices"][0]["message"]["content"]
        
        # 保存点评
        letter.ai_review = review_text
        letter.ai_review_at = datetime.now()
        
        # AI 评估目标
        if letter.goals:
            goals = list(letter.goals)
            for i, goal in enumerate(goals):
                if goal.get("type") == "ai" and goal.get("completed") is None:
                    # AI 类目标需要额外评估
                    goal_eval = await _evaluate_single_goal(
                        goal["text"], diaries, wellbeing_entries, notes, ai_config
                    )
                    goals[i]["completed"] = goal_eval.get("completed", False)
                    goals[i]["ai_evaluation"] = goal_eval.get("evaluation", "")
                    goals[i]["ai_score"] = goal_eval.get("score", 0.0)
            letter.goals = goals
        
        return {
            "ai_review": review_text,
            "goals": letter.goals,
            "data_summary": {
                "diary_count": len(diaries),
                "wellbeing_count": len(wellbeing_entries),
                "notes_count": len(notes),
                "period": f"{seal_date.isoformat()} ~ {open_date.isoformat()}",
            },
        }
    except Exception as e:
        logger.error(f"AI 点评生成失败: {e}")
        raise HTTPException(status_code=500, detail=f"AI 点评生成失败: {str(e)}")


# ======================== 辅助函数 ========================

def _build_ai_review_prompt(letter, diaries, wellbeing_entries, notes) -> str:
    """构建 AI 时光点评的 prompt"""
    parts = []
    parts.append(f"## 信件信息\n")
    parts.append(f"- 写信日期：{letter.seal_date.isoformat()}")
    parts.append(f"- 开封日期：{letter.open_date.isoformat()}")
    parts.append(f"- 收件人：{letter.recipient}")
    parts.append(f"- 标题：{letter.title}")
    parts.append(f"\n### 信件内容\n{letter.content}\n")
    
    if letter.goals:
        parts.append("### 当时设定的目标")
        for i, goal in enumerate(letter.goals, 1):
            parts.append(f"{i}. {goal['text']}（评估方式：{'AI评估' if goal.get('type') == 'ai' else '自评'}）")
    
    # 日记摘要
    if diaries:
        parts.append(f"\n## 这段时间的日记摘要（共 {len(diaries)}篇）\n")
        for d in diaries[:20]:  # 最多取20篇避免 token 过多
            summary = d.content[:200] if d.content else ""
            mood = f"[情绪: {d.mood}]" if d.mood else ""
            parts.append(f"- {d.date.isoformat()} {mood}: {summary}")
    
    # 心力记录
    if wellbeing_entries:
        parts.append(f"\n## 心力记录摘要（共 {len(wellbeing_entries)} 条）\n")
        for w in wellbeing_entries[:15]:
            parts.append(f"- {w.occurred_at.isoformat()}: {w.content[:100] if w.content else ''}")
    
    # 读书笔记
    if notes:
        parts.append(f"\n## 阅读记录（共 {len(notes)} 本）\n")
        for n in notes[:10]:
            parts.append(f"- 《{n.title}》({n.reading_date.isoformat() if n.reading_date else '未知日期'})")
    
    parts.append("""
## 你的任务

请基于以上信息，为用户写一段温暖有洞察的时光点评（800字左右），包含：

1. **时光对比**：写信时的状态 vs 现在的变化
2. **成长洞察**：从日记和心力记录中提炼出的成长轨迹
3. **目标回顾**：如果有设定目标，逐个点评完成情况（AI评估类的请给出判断依据）
4. **温暖寄语**：以朋友/见证者的语气，给出对未来的鼓励

语气要求：温暖真诚，不要说教，像一个了解你的老朋友在和你聊天。使用 Markdown 格式。
""")
    
    return "\n".join(parts)


async def _evaluate_single_goal(goal_text, diaries, wellbeing_entries, notes, ai_config) -> dict:
    """AI 评估单个目标的完成情况"""
    # 构建简短的评估 prompt
    context_parts = []
    for d in diaries[:10]:
        if d.content:
            context_parts.append(f"{d.date}: {d.content[:100]}")
    
    prompt = f"""请评估以下目标在这段时间内是否完成：

目标：{goal_text}

相关记录摘要：
{chr(10).join(context_parts[:10])}

请返回 JSON 格式：
{{"completed": true/false, "score": 0.0-1.0, "evaluation": "简要评估说明(50字内)"}}

只返回 JSON，不要其他内容。"""
    
    try:
        import httpx
        import json
        
        headers = {"Content-Type": "application/json"}
        if ai_config.api_key:
            headers["Authorization"] = f"Bearer {ai_config.api_key}"
        
        payload = {
            "model": ai_config.model or "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            # 输出虽短，但深度思考模型的思维链会占用额度，太小会导致正文为空
            "max_tokens": 2000,
        }
        
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                get_api_url(ai_config),
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            # 尝试解析 JSON（深度思考模型可能在 JSON 外包裹说明文字）
            content = (content or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            if not content.startswith("{"):
                s, e = content.find("{"), content.rfind("}")
                if s >= 0 and e > s:
                    content = content[s:e + 1]
            return json.loads(content)
    except Exception as e:
        logger.warning(f"目标评估失败: {e}")
        return {"completed": False, "score": 0.0, "evaluation": "评估失败，请手动评估"}


def _get_system_templates() -> list:
    """系统预设模板数据"""
    return [
        {
            "key": "birthday_self",
            "name": "生日寄语",
            "description": "在生日这天，给未来的自己写一封信",
            "icon": "🎂",
            "category": "birthday",
            "sort_order": 1,
            "is_system": True,
            "sections": [
                {"section": "此刻的我", "prompt": "今天是你的生日，此刻你几岁了？生活中最重要的角色是什么？", "placeholder": "今天我XX岁了，我是..."},
                {"section": "过去一年的收获", "prompt": "回顾过去一年，你最骄傲的三件事是什么？", "placeholder": "1. ...\n2. ...\n3. ..."},
                {"section": "未解的困惑", "prompt": "有什么问题你还没想通？留给未来的自己去回答", "placeholder": "我还在思考..."},
                {"section": "给未来自己的话", "prompt": "一年后的你，你希望TA变成什么样子？", "placeholder": "亲爱的未来的我..."},
            ],
            "suggested_goals": [
                "保持身体健康，坚持运动",
                "在事业上取得一个重要突破",
                "读完至少12本书",
                "学会一项新技能",
            ],
        },
        {
            "key": "year_review",
            "name": "年度回顾",
            "description": "新年之际，记录当下，留给明年的自己",
            "icon": "🎆",
            "category": "newyear",
            "sort_order": 2,
            "is_system": True,
            "sections": [
                {"section": "今年关键词", "prompt": "用三个关键词总结你的这一年", "placeholder": "关键词1、关键词2、关键词3"},
                {"section": "最大的改变", "prompt": "这一年你最大的变化是什么？是好的还是坏的？", "placeholder": "今年我最大的改变是..."},
                {"section": "遗憾与释怀", "prompt": "有什么遗憾？你愿意放下它吗？", "placeholder": "如果有什么遗憾..."},
                {"section": "明年的蓝图", "prompt": "如果明年只能做三件重要的事，你会选什么？", "placeholder": "1. ...\n2. ...\n3. ..."},
                {"section": "给明年自己的信", "prompt": "自由地写下你想对明年自己说的话", "placeholder": "亲爱的明年的我..."},
            ],
            "suggested_goals": [
                "完成年度最重要的三件事",
                "财务目标达成",
                "建立或维护一段重要关系",
                "身心健康维持",
            ],
        },
        {
            "key": "milestone",
            "name": "里程碑时刻",
            "description": "人生重要节点的记录——毕业、入职、结婚、成为父母...",
            "icon": "🏆",
            "category": "milestone",
            "sort_order": 3,
            "is_system": True,
            "sections": [
                {"section": "这是什么时刻", "prompt": "描述此刻正在发生的重大事件", "placeholder": "今天，我..."},
                {"section": "此刻的心情", "prompt": "你现在是什么感受？激动、忐忑、平静？", "placeholder": "我的心情是..."},
                {"section": "我为此付出了什么", "prompt": "为了走到这一步，你经历了什么？", "placeholder": "回想起来，这一路..."},
                {"section": "我期待什么", "prompt": "你对接下来的日子有什么期待？", "placeholder": "我希望..."},
            ],
            "suggested_goals": [
                "在新身份/新阶段中站稳脚跟",
                "不忘初心，保持当下的这份感受",
            ],
        },
        {
            "key": "five_year_letter",
            "name": "五年之约",
            "description": "写一封五年后才能打开的信，穿越时间的对话",
            "icon": "⏳",
            "category": "general",
            "sort_order": 4,
            "is_system": True,
            "sections": [
                {"section": "现在的生活全景", "prompt": "描述你现在的生活——工作、感情、兴趣、住在哪里", "placeholder": "现在的我住在...工作是..."},
                {"section": "最在乎的人", "prompt": "现在你身边最重要的人是谁？你们的关系如何？", "placeholder": "我最在乎的人是..."},
                {"section": "内心深处的愿望", "prompt": "如果不考虑现实限制，五年后你最想实现什么？", "placeholder": "如果可以，我最想..."},
                {"section": "对未来的预测", "prompt": "你觉得五年后的世界会怎样？你在其中是什么角色？", "placeholder": "我预测..."},
                {"section": "时间胶囊", "prompt": "放一些只有现在的你知道的小秘密进去", "placeholder": "只有现在的我知道..."},
            ],
            "suggested_goals": [
                "实现一个长期人生梦想",
                "建立稳定的被动收入",
                "去到一个梦想中的地方",
                "成为某个领域的专家",
                "拥有高质量的人际关系",
            ],
        },
        {
            "key": "gratitude_letter",
            "name": "感恩信",
            "description": "写给某个重要的人，记录你对TA的感谢",
            "icon": "💌",
            "category": "general",
            "sort_order": 5,
            "is_system": True,
            "sections": [
                {"section": "你想感谢谁", "prompt": "这封信是写给谁的？TA在你生命中扮演什么角色？", "placeholder": "亲爱的..."},
                {"section": "TA做了什么", "prompt": "TA做的哪件事让你特别感动？", "placeholder": "我想感谢你..."},
                {"section": "TA对你的影响", "prompt": "因为TA，你变成了怎样的人？", "placeholder": "因为你，我学会了..."},
                {"section": "你想说但没说出口的话", "prompt": "有什么话你一直想说但还没说？", "placeholder": "我想告诉你..."},
            ],
            "suggested_goals": None,
        },
        {
            "key": "anxiety_release",
            "name": "焦虑封存",
            "description": "把此刻的焦虑写下来封存，回头看看它是否真的发生了",
            "icon": "🫧",
            "category": "general",
            "sort_order": 6,
            "is_system": True,
            "sections": [
                {"section": "此刻在焦虑什么", "prompt": "写下你现在最焦虑/担心的事情", "placeholder": "我在担心..."},
                {"section": "最坏的结果", "prompt": "你设想的最坏情况是什么？", "placeholder": "如果最坏的情况发生..."},
                {"section": "你能做什么", "prompt": "面对这个焦虑，你打算做什么应对？", "placeholder": "我计划..."},
                {"section": "给未来的自己", "prompt": "如果焦虑的事并没发生，你想对自己说什么？如果发生了呢？", "placeholder": "不管结果如何..."},
            ],
            "suggested_goals": [
                "焦虑的事并没有发生（验证概率偏差）",
                "即使发生了，我也应对过来了",
            ],
        },
    ]
