"""对话内澄清提问（参考 harness AskUserQuestion / hermes clarify 的裁剪版）

理念：AI 分析日记/笔记时，**真正被内容触发**需要了解用户的地方，才在对话里提问
（带快捷选项 + 自由输入）。用户回答后，答案先经 AI 提炼成画像增量再入库，
不做「原始问答直倒画像」这种没有信息增益的事。
"""
import logging
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_service import (
    get_active_ai_config, _build_request, _parse_ai_json, update_user_profile,
)

logger = logging.getLogger(__name__)

QUESTION_PROMPT = """你在分析用户的一篇{label}。分析过程中，如果有些地方**只有问用户本人才能真正理解**（比如动机、感受、背景、意图），提出最多 2 个澄清问题。

## 严格标准（宁缺毋滥）
- 问题必须是从这段内容里**真实长出来的**（"他说和朋友打球很开心——是哪个朋友/什么场合"这类能加深理解的）
- 不要问内容里已经有答案的、不要问无关痛痒的、不要硬凑
- 没有问题就输出 {{"questions": []}}——大部分内容都不需要问

## 每个问题
- question：自然口语化的问法（像朋友好奇追问，不像问卷）
- options：2-4 个快捷选项（覆盖常见可能，让用户点一下就答完）；实在给不出好选项就空数组

## 输出严格 JSON
{{"questions": [{{"question": "...", "options": ["...", "..."]}}]}}

## 用户的{label}原文
{content}

## 你的分析
{analysis}"""

SYNTHESIZE_PROMPT = """用户回答了你之前的澄清问题。请把问答提炼成用户画像增量。

## 原始内容摘录
{content}

## 问答
{qa}

## 输出严格 JSON
{{"learned": [
  {{"category": "分类（优先用：基本信息/性格特征/职业发展/投资风格/学习偏好/情绪模式/核心关注/成长目标/个人资源/专业技能/人脉网络/生活状态/价值观信念）", "key": "特征名", "value": "提炼后的完整表述（不是照抄答案）", "confidence": 0.6}}
]}}

要求：value 是经过理解提炼的陈述句（如"重视与固定球友的深度联结"），不是问答原文；没有实质新信息就输出空数组。"""


async def generate_clarify_questions(
    db: AsyncSession, label: str, content: str, analysis: str
) -> dict | None:
    """分析后判断是否需要在对话中向用户提问。返回 {"batch_id": ..., "questions": [...]} 或 None"""
    config = await get_active_ai_config(db)
    if not config:
        return None
    prompt = (QUESTION_PROMPT
              .replace("{label}", label)
              .replace("{content}", content[:3000])
              .replace("{analysis}", analysis[:3000]))
    try:
        url, headers, payload = _build_request(config, [{"role": "user", "content": prompt}])
        payload["max_tokens"] = min(config.max_tokens, 800)
        payload["temperature"] = 0.3
        if config.provider == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            parsed = _parse_ai_json(r.json()["choices"][0]["message"]["content"] or "")
    except Exception as e:
        logger.warning(f"澄清问题生成失败（跳过不影响保存）: {e}")
        return None

    questions = [
        {"question": q["question"][:300], "options": [str(o)[:100] for o in (q.get("options") or [])][:4]}
        for q in (parsed.get("questions") or [])[:2]
        if q.get("question")
    ]
    if not questions:
        return None
    return {"batch_id": uuid.uuid4().hex[:12], "questions": questions}


async def synthesize_answers_to_profile(
    db: AsyncSession, content: str, qa_pairs: list[dict]
) -> list[dict]:
    """把澄清问答经 AI 提炼后写入画像。返回实际写入的条目"""
    config = await get_active_ai_config(db)
    if not config:
        return []
    qa_text = "\n".join(f"问：{p['question']}\n答：{p['answer']}" for p in qa_pairs if p.get("answer"))
    if not qa_text.strip():
        return []
    prompt = (SYNTHESIZE_PROMPT
              .replace("{content}", content[:1500])
              .replace("{qa}", qa_text[:1500]))
    try:
        url, headers, payload = _build_request(config, [{"role": "user", "content": prompt}])
        payload["max_tokens"] = min(config.max_tokens, 800)
        payload["temperature"] = 0.2
        if config.provider == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            parsed = _parse_ai_json(r.json()["choices"][0]["message"]["content"] or "")
    except Exception as e:
        logger.warning(f"澄清答案提炼失败（不写画像）: {e}")
        return []

    learned = [
        item for item in (parsed.get("learned") or [])
        if item.get("key") and item.get("value")
    ]
    if not learned:
        return []
    return await update_user_profile(db, learned)
