"""复盘服务（hermes background_review 裁剪版）：对话结束后蒸馏经验为候选 skill

触发：会话累计 ≥6 条用户消息且尚无待审候选 → 后台异步复盘一次。
产出：skill_candidates（pending）→ 用户在设置页确认才转正（consent-first）。

复盘四铁律（写进 prompt）：
1. patch 优先于新建（先看有没有可改进的现有 skill）
2. 记 Lesson 不记 log：祈使句规则 + 一句 why，不写事件叙事
3. Do-NOT-capture：环境性失败、瞬时错误、失败尝试不沉淀
4. 用户纠正是头等信号（"别这么啰嗦"这类反馈直接进技能）
"""
import json
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentEvent, AgentSession
from app.models.prompt_skill import SkillCandidate
from app.services.ai_service import get_active_ai_config, _build_request, _parse_ai_json

logger = logging.getLogger(__name__)

REVIEW_MIN_USER_MSGS = 6  # 触发复盘的最少用户消息数

REVIEW_PROMPT = """你是复盘代理。回看下面这段 AI 助手与用户的对话，判断有没有值得沉淀的"可复用方法论"（程序性知识）。

## 现有技能（patch 优先：能改进旧的就不新建）
{existing_skills}

## 对话记录
{conversation}

## 铁律
1. **patch 优先于新建**：现有技能能覆盖的，输出 action=patch 改进它（target_name 指过去）；只有全新一类任务才 create
2. **记 Lesson 不记 log**：内容是祈使句规则 + 一句 why（"做 X 因为 Y"），禁止"某年某月发生了什么"式叙事
3. **不要沉淀**：环境性失败（接口挂了/没配置）、对话内已解决的瞬时错误、没找到方法的失败尝试
4. **用户纠正是头等信号**：用户说"别这样/以后那样"的反馈最值得进技能
5. 没有什么值得沉淀的就输出 {"action": "none"}——宁缺毋滥

## 输出严格 JSON
{
  "action": "none | create | patch",
  "name": "kebab-case 技能名（一类任务的抽象，禁止一次性任务名）",
  "title": "显示名",
  "description": "触发语：一句话说清什么时候用它（前 57 字符自包含）",
  "content": "技能正文（prompt，100-200 行以内）",
  "target_name": "patch 时的目标技能名",
  "reason": "一句话：这段对话里的什么经验让你沉淀它"
}"""


async def maybe_review_session(db: AsyncSession, session: AgentSession) -> None:
    """检查是否该复盘，是则异步执行（不阻塞对话返回）"""
    # 统计用户消息数
    result = await db.execute(
        select(AgentEvent).where(
            AgentEvent.session_id == session.id, AgentEvent.event_type == "user_message"
        )
    )
    user_msgs = result.scalars().all()
    if len(user_msgs) < REVIEW_MIN_USER_MSGS:
        return
    # 本会话已有待审候选 → 不重复复盘
    result = await db.execute(
        select(SkillCandidate).where(
            SkillCandidate.source_session_id == session.id, SkillCandidate.status == "pending"
        )
    )
    if result.scalars().first():
        return
    # 防止同一回合重复触发：简单用最新用户消息 seq 作为幂等键（候选 reason 里带上）
    import asyncio
    asyncio.create_task(_run_review(session.id))


async def _run_review(session_id: int) -> None:
    """后台复盘：读会话投影 → LLM 判断 → 写候选（独立 db 会话）"""
    from app.core.database import async_session_maker
    from app.services.agent_session import derive_messages
    from app.services.skill_service import list_enabled_skills

    try:
        async with async_session_maker() as db:
            session = await db.get(AgentSession, session_id)
            if not session:
                return
            messages = await derive_messages(db, session_id)
            conversation = "\n".join(
                f"{'用户' if m['role'] == 'user' else '助手'}：{(m.get('content') or '')[:400]}"
                for m in messages if m.get("content")
            )[-6000:]
            if len(conversation.strip()) < 100:
                return

            skills = await list_enabled_skills(db)
            existing = "\n".join(f"- {s.name}: {s.description}" for s in skills) or "（暂无）"

            config = await get_active_ai_config(db)
            if not config:
                return
            prompt = (REVIEW_PROMPT
                      .replace("{existing_skills}", existing)
                      .replace("{conversation}", conversation))
            url, headers, payload = _build_request(config, [{"role": "user", "content": prompt}])
            payload["max_tokens"] = min(config.max_tokens, 2048)
            payload["temperature"] = 0.2
            if config.provider == "deepseek":
                payload["thinking"] = {"type": "disabled"}

            async with httpx.AsyncClient(timeout=90.0) as client:
                r = await client.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
            parsed = _parse_ai_json(data["choices"][0]["message"]["content"] or "")

            if parsed.get("action") not in ("create", "patch"):
                logger.info(f"复盘会话 #{session_id}：无可沉淀")
                return
            if not parsed.get("name") or not parsed.get("content"):
                return
            if parsed["action"] == "patch" and not parsed.get("target_name"):
                return

            db.add(SkillCandidate(
                name=parsed["name"][:60],
                title=(parsed.get("title") or parsed["name"])[:100],
                description=(parsed.get("description") or "")[:300],
                content=parsed["content"],
                reason=(parsed.get("reason") or "")[:500],
                action=parsed["action"],
                target_name=parsed.get("target_name"),
                source_session_id=session_id,
            ))
            await db.commit()
            logger.info(f"复盘会话 #{session_id}：产出候选 skill {parsed['name']}（{parsed['action']}）")
    except Exception as e:
        logger.warning(f"复盘会话 #{session_id} 失败（不影响对话）: {e}")
