"""AI 提问队列服务

日记/笔记保存后异步生成澄清问题（不阻断主流程）；
回答沉淀到用户画像；教练页可主动触发提问。
"""

import logging
from datetime import datetime

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_question import AIQuestion
from app.services.ai_service import (
    get_active_ai_config, get_user_profile_text, update_user_profile,
    _build_request, _parse_ai_json,
)

logger = logging.getLogger(__name__)

# 内容太短没有值得澄清的上下文，直接跳过（不调 AI，省 token）
MIN_CONTENT_LENGTH = 30
# 单次最多生成的问题数
MAX_QUESTIONS = 2

QUESTION_GEN_PROMPT = """你是一位了解用户的个人成长教练。请阅读用户刚保存的{source_name}，判断是否存在值得澄清的点。

## 什么值得提问（满足其一才问）
- 提到了模糊指代（如"那个项目"、"某件事"）但不影响理解大意就无法追溯
- 有关键决策/情绪/转折没有展开（如"做了个艰难的决定"但没说是什么）
- 有反复出现的模式信号值得确认（如多次提到同一个人/事但关系不明）

## 什么不要问
- 内容清楚完整的不要硬问
- 隐私性强、用户明显不想展开的不要问
- 能从小事直接理解的不问

## 输出（严格 JSON，不要其它文字）
有值得澄清的点：{{"questions": [{{"question": "自然口语化的问题，像朋友随口一问", "context": "提问依据（引用原文片段，30字内)"}}]}}
没有：{{"questions": []}}

最多提 {max_questions} 个问题。

## 用户{source_name}内容
{content}"""


async def maybe_generate_questions(
    db: AsyncSession, source_type: str, source_id: int | None, content: str
) -> list[AIQuestion]:
    """判断内容是否有值得澄清的点，有则生成问题入队。任何失败都静默返回 []。"""
    if not content or len(content.strip()) < MIN_CONTENT_LENGTH:
        return []

    try:
        import httpx

        config = await get_active_ai_config(db)
        if not config:
            return []

        source_name = {"diary": "日记", "note": "笔记"}.get(source_type, "内容")
        prompt = (
            QUESTION_GEN_PROMPT
            .replace("{source_name}", source_name)
            .replace("{max_questions}", str(MAX_QUESTIONS))
            .replace("{content}", content[:3000])
        )
        url, headers, payload = _build_request(config, [{"role": "user", "content": prompt}])
        payload["max_tokens"] = min(config.max_tokens, 2048)
        if config.provider == "deepseek":
            # 判断+短输出场景，禁用思维链提速并避免额度被耗尽
            payload["thinking"] = {"type": "disabled"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        parsed = _parse_ai_json(data["choices"][0]["message"]["content"] or "")
        questions = (parsed.get("questions") or [])[:MAX_QUESTIONS]

        created = []
        for q in questions:
            text = (q.get("question") or "").strip()
            if not text:
                continue
            item = AIQuestion(
                source_type=source_type,
                source_id=source_id,
                question=text,
                context=(q.get("context") or "")[:200],
            )
            db.add(item)
            created.append(item)
        if created:
            await db.commit()
            for item in created:
                await db.refresh(item)
            logger.info(f"AI 提问入队: source={source_type}#{source_id}, {len(created)} 条")
        return created
    except Exception as e:
        # 提问生成失败不影响保存主流程
        logger.warning(f"AI 提问生成失败（已忽略）: {e}")
        return []


async def generate_questions_task(source_type: str, source_id: int | None, content: str) -> None:
    """后台任务包装：独立 session，供 asyncio.create_task 在保存成功后异步调用"""
    from app.core.database import async_session_maker
    async with async_session_maker() as db:
        await maybe_generate_questions(db, source_type, source_id, content)


async def list_questions(db: AsyncSession, status: str | None = None, limit: int = 50) -> list[AIQuestion]:
    """提问列表，默认全部；status 过滤（pending/answered/dismissed），按时间倒序"""
    query = select(AIQuestion).order_by(desc(AIQuestion.created_at)).limit(limit)
    if status:
        query = query.where(AIQuestion.status == status)
    result = await db.execute(query)
    return list(result.scalars())


async def answer_question(db: AsyncSession, question_id: int, answer: str) -> AIQuestion:
    """回答问题：保存答案并把问答作为证据沉淀到用户画像"""
    item = await db.get(AIQuestion, question_id)
    if not item:
        raise ValueError("问题不存在")
    if item.status != "pending":
        raise ValueError("该问题已处理过")
    if not answer.strip():
        raise ValueError("回答不能为空")

    item.status = "answered"
    item.answer = answer.strip()
    item.answered_at = datetime.now()
    await db.flush()

    # 问答经 AI 提炼后沉淀画像（不再是原始问答直倒——直倒没有信息增益）
    try:
        from app.services.clarify_service import synthesize_answers_to_profile
        await synthesize_answers_to_profile(db, item.question, [{
            "question": item.question, "answer": item.answer,
        }])
    except Exception as e:
        logger.warning(f"回答提炼画像失败（答案仍已保存）: {e}")
    await db.commit()
    await db.refresh(item)
    logger.info(f"AI 提问已回答: #{question_id}")
    return item


async def dismiss_question(db: AsyncSession, question_id: int) -> AIQuestion:
    """忽略问题"""
    item = await db.get(AIQuestion, question_id)
    if not item:
        raise ValueError("问题不存在")
    item.status = "dismissed"
    await db.flush()
    await db.commit()
    await db.refresh(item)
    return item


PROACTIVE_PROMPT = """你是一位了解用户的个人成长教练。基于用户画像和近期待办，主动提出 {max_questions} 个你最想了解的问题。

## 用户画像
{user_profile}

## 近期未完成待办（标题）
{todos}

## 要求
- 问题要能填补画像缺口（价值观、目标动机、当前困扰、长期方向）或澄清近期事项的关键背景
- 像朋友随口一问，自然口语化，不要审问感
- 严格 JSON：{{"questions": [{{"question": "...", "context": "为什么问这个（20字内）"}}]}}"""


async def generate_proactive_questions(db: AsyncSession) -> list[AIQuestion]:
    """主动提问（教练页触发）：基于画像缺口与近期记录生成问题"""
    import httpx
    from app.models.todo import TodoItem

    config = await get_active_ai_config(db)
    if not config:
        raise ValueError("未配置 AI 模型")

    profile_text = await get_user_profile_text(db)
    todos_result = await db.execute(
        select(TodoItem.title)
        .where(TodoItem.status.notin_(["completed", "cancelled", "wont_fix"]))
        .order_by(desc(TodoItem.created_at))
        .limit(20)
    )
    todos_text = "\n".join(f"- {t}" for t in todos_result.scalars()) or "暂无"

    prompt = (
        PROACTIVE_PROMPT
        .replace("{max_questions}", str(MAX_QUESTIONS))
        .replace("{user_profile}", profile_text or "暂无画像")
        .replace("{todos}", todos_text)
    )
    url, headers, payload = _build_request(config, [{"role": "user", "content": prompt}])
    payload["max_tokens"] = min(config.max_tokens, 2048)
    if config.provider == "deepseek":
        payload["thinking"] = {"type": "disabled"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    parsed = _parse_ai_json(data["choices"][0]["message"]["content"] or "")
    questions = (parsed.get("questions") or [])[:MAX_QUESTIONS]
    created = []
    for q in questions:
        text = (q.get("question") or "").strip()
        if not text:
            continue
        item = AIQuestion(source_type="manual", source_id=None, question=text,
                          context=(q.get("context") or "")[:200])
        db.add(item)
        created.append(item)
    if created:
        await db.commit()
        for item in created:
            await db.refresh(item)
    logger.info(f"主动提问生成: {len(created)} 条")
    return created
