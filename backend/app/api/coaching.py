"""教练对话 API - 支持多轮对话、跨 session 记忆、自动沉淀洞察"""

import json
import uuid
import logging
from typing import Optional
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.coaching import CoachingSession
from app.models.ai_config import UserProfile
from app.services.ai_service import get_active_ai_config, get_user_profile_text, update_user_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat/coaching", tags=["coaching"])


# ==================== Schema ====================

class CoachingChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    history: Optional[list] = None


class CoachingEndRequest(BaseModel):
    session_id: Optional[str] = None
    messages: list


# ==================== System Prompt ====================

COACHING_SYSTEM_PROMPT = """你是用户的专属 AI 教练。你的角色是帮助用户「看见」自己看不见的盲区，激发自我觉察和深层成长。

## 用户画像
{user_profile}

## 最近教练对话摘要
{recent_sessions}

## 教练风格
你能自动识别用户当前需要的教练类型并灵活切换：
- **情商教练**：情绪觉察、人际关系、自我认知
- **绩效教练**：目标设定、执行力提升、时间管理
- **关系教练**：沟通技巧、边界设定、冲突处理
- **愿景教练**：方向探索、价值观澄清、人生规划
- **生活教练**：习惯养成、精力管理、生活平衡

## 对话原则
1. **多提问、少说教**：用有力量的问题引导用户自我觉察，而不是直接给答案
2. **积极关注**：承认用户的感受和处境，先共情后探索
3. **看见模式**：帮用户识别反复出现的行为/思维模式
4. **挑战盲区**：温和但坚定地指出用户可能忽略的视角
5. **行动导向**：每轮对话尝试引导到一个小的可执行步骤
6. **保持简洁**：每次回复控制在中等长度，不要长篇大论

## 回复格式
- 自然对话，不需要 Markdown 格式化（除非引用或列举）
- 可以适当使用 emoji 表达温度
- 回复结尾可以抛出一个引导性问题，推进对话深入"""


COACHING_END_PROMPT = """基于以下教练对话，请生成：

1. **对话总结**（summary）：2-3 句话概括本次对话的核心主题和进展
2. **关键洞察**（insights）：提取 1-3 条用户在本次对话中获得的自我觉察或新认知
3. **画像更新**（profile_updates）：基于本次对话提取可更新到用户画像的特征

输出严格 JSON 格式：
```json
{{
  "summary": "本次对话总结",
  "insights": ["洞察1", "洞察2"],
  "coaching_type": "识别到的教练类型：emotion/performance/relationship/vision/life",
  "profile_updates": [
    {{"category": "分类", "key": "特征键", "value": "特征值", "action": "create/update"}}
  ]
}}
```

## 用户画像
{user_profile}

## 对话内容
{conversation}"""


# ==================== API Endpoints ====================

@router.post("/chat")
async def coaching_chat(req: CoachingChatRequest, db: AsyncSession = Depends(get_db)):
    """教练对话 - 流式多轮对话"""

    async def stream_response():
        try:
            # 获取 AI 配置
            config = await get_active_ai_config(db, module_name="coaching")
            if not config:
                config = await get_active_ai_config(db)
            if not config:
                yield f"data: {json.dumps({'type': 'error', 'message': '未配置 AI 模型'}, ensure_ascii=False)}\n\n"
                return

            # 生成或复用 session_id
            session_id = req.session_id or str(uuid.uuid4())[:8]
            yield f"data: {json.dumps({'type': 'session_id', 'session_id': session_id}, ensure_ascii=False)}\n\n"

            # 获取用户画像
            user_profile = await get_user_profile_text(db)

            # 获取最近教练对话摘要（跨 session 记忆）
            recent_sessions_text = await _get_recent_sessions_summary(db, session_id)

            # 构建 system prompt
            system_prompt = COACHING_SYSTEM_PROMPT.format(
                user_profile=user_profile,
                recent_sessions=recent_sessions_text or "（这是第一次教练对话）",
            )

            # 构建消息列表
            messages = [{"role": "system", "content": system_prompt}]

            # 添加历史消息
            if req.history:
                for msg in req.history:
                    role = msg.get("role", "user") if isinstance(msg, dict) else msg.role
                    content = msg.get("content", "") if isinstance(msg, dict) else msg.content
                    messages.append({"role": role, "content": content})

            # 添加当前用户消息
            messages.append({"role": "user", "content": req.message})

            # 调用 AI（流式）
            url = (config.api_base or "https://api.deepseek.com") + "/chat/completions"
            headers = {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": config.model,
                "messages": messages,
                "temperature": config.temperature or 0.8,
                "max_tokens": config.max_tokens or 2048,
                "stream": True,
            }

            full_response = ""
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            chunk = delta.get("content", "")
                            if chunk:
                                full_response += chunk
                                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
                        except json.JSONDecodeError:
                            continue

            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

            # 保存/更新 session（异步，不阻塞流）
            try:
                await _save_session_messages(db, session_id, req.history or [], req.message, full_response)
            except Exception as e:
                logger.warning(f"保存教练对话 session 失败: {e}")

        except httpx.HTTPStatusError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'AI 服务错误: {e.response.status_code}'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"教练对话异常: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/end")
async def coaching_end(req: CoachingEndRequest, db: AsyncSession = Depends(get_db)):
    """结束教练对话 - 生成总结 + 沉淀洞察 + 更新画像"""

    config = await get_active_ai_config(db, module_name="coaching")
    if not config:
        config = await get_active_ai_config(db)
    if not config:
        return {"summary": "对话已结束", "insights": [], "profile_updates": []}

    # 构建对话文本
    conversation_text = ""
    for msg in req.messages:
        role_label = "用户" if msg.get("role") == "user" else "教练"
        conversation_text += f"【{role_label}】{msg.get('content', '')}\n\n"

    # 获取用户画像
    user_profile = await get_user_profile_text(db)

    # 调用 AI 生成总结
    prompt = COACHING_END_PROMPT.format(
        user_profile=user_profile,
        conversation=conversation_text,
    )

    try:
        url = (config.api_base or "https://api.deepseek.com") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": "你是一个教练对话分析助手，请严格按要求输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # 解析 JSON
            result = _parse_json_response(content)

            # 更新画像
            profile_updates = result.get("profile_updates", [])
            if profile_updates:
                try:
                    await update_user_profile(db, profile_updates)
                except Exception as e:
                    logger.warning(f"教练对话更新画像失败: {e}")

            # 保存 session 总结
            if req.session_id:
                try:
                    await _finalize_session(
                        db, req.session_id, result.get("summary", ""),
                        result.get("insights", []),
                        result.get("coaching_type", ""),
                        profile_updates,
                    )
                except Exception as e:
                    logger.warning(f"保存 session 总结失败: {e}")

            await db.commit()
            return result

    except Exception as e:
        logger.error(f"教练对话结束分析失败: {e}", exc_info=True)
        return {"summary": "对话已结束（分析失败）", "insights": [], "profile_updates": []}


@router.get("/sessions")
async def list_coaching_sessions(
    skip: int = 0, limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """获取历史教练对话列表"""
    result = await db.execute(
        select(CoachingSession)
        .order_by(desc(CoachingSession.created_at))
        .offset(skip)
        .limit(limit)
    )
    sessions = result.scalars().all()
    return [
        {
            "session_id": s.session_id,
            "coaching_type": s.coaching_type,
            "summary": s.summary,
            "insights": s.insights,
            "message_count": len(s.messages) if s.messages else 0,
            "is_ended": s.is_ended,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in sessions
    ]


# ==================== Helper Functions ====================

async def _get_recent_sessions_summary(db: AsyncSession, current_session_id: str) -> str:
    """获取最近 5 次教练对话的摘要，用于跨 session 记忆"""
    result = await db.execute(
        select(CoachingSession)
        .where(
            CoachingSession.is_ended == True,
            CoachingSession.session_id != current_session_id,
        )
        .order_by(desc(CoachingSession.created_at))
        .limit(5)
    )
    sessions = result.scalars().all()

    if not sessions:
        return ""

    parts = []
    for s in sessions:
        date_str = s.created_at.strftime("%Y-%m-%d") if s.created_at else "未知日期"
        summary = s.summary or "（无总结）"
        insights = ", ".join(s.insights) if s.insights else ""
        parts.append(f"- [{date_str}] {summary}" + (f" | 洞察: {insights}" if insights else ""))

    return "### 最近教练对话记录\n" + "\n".join(parts)


async def _save_session_messages(
    db: AsyncSession,
    session_id: str,
    history: list,
    user_message: str,
    ai_response: str,
):
    """保存/更新教练对话 session 消息"""
    result = await db.execute(
        select(CoachingSession).where(CoachingSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()

    messages = []
    # 添加历史
    for msg in history:
        if isinstance(msg, dict):
            messages.append(msg)
    # 添加最新一轮
    messages.append({"role": "user", "content": user_message, "timestamp": datetime.now().isoformat()})
    messages.append({"role": "assistant", "content": ai_response, "timestamp": datetime.now().isoformat()})

    if session:
        session.messages = messages
        session.updated_at = datetime.now()
    else:
        session = CoachingSession(
            session_id=session_id,
            messages=messages,
        )
        db.add(session)

    await db.commit()


async def _finalize_session(
    db: AsyncSession,
    session_id: str,
    summary: str,
    insights: list,
    coaching_type: str,
    profile_updates: list,
):
    """标记 session 为已结束并保存总结"""
    result = await db.execute(
        select(CoachingSession).where(CoachingSession.session_id == session_id)
    )
    session = result.scalar_one_or_none()

    if session:
        session.summary = summary
        session.insights = insights
        session.coaching_type = coaching_type
        session.profile_updates = profile_updates
        session.is_ended = True
        session.updated_at = datetime.now()
    else:
        # 如果没有找到 session（可能前端没有正确传 session_id），创建一个
        session = CoachingSession(
            session_id=session_id,
            messages=[],
            summary=summary,
            insights=insights,
            coaching_type=coaching_type,
            profile_updates=profile_updates,
            is_ended=True,
        )
        db.add(session)


def _parse_json_response(content: str) -> dict:
    """解析 AI 返回的 JSON（兼容 markdown 代码块包裹）"""
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        # 移除首尾的 ``` 行
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 尝试找到 JSON 部分
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(content[start:end])
            except json.JSONDecodeError:
                pass
        return {"summary": "对话已结束", "insights": [], "profile_updates": []}
