"""心愿清单 AI 服务

从用户的"进展日志"中异步分析出进度更新候选（建议新进度 / 建议完成的里程碑），
供用户在心愿详情页审核采纳，避免 AI 单方面改写心愿进度。

复用 app.services.ai_service 的模型调用与画像注入能力，所有失败都降级为落一条
失败候选记录，不阻断主流程（对齐 wellbeing_ai.py 的容错模式）。
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.wishlist import Wish, WishLogEntry, WishProgressCandidate
from app.services.ai_service import (
    get_active_ai_config,
    _build_request,
    _parse_ai_json,
)

logger = logging.getLogger(__name__)

MODULE_NAME = "wishlist"

ANALYZE_WISH_PROMPT = """你是用户的心愿达成教练，善于从琐碎的日常记录中发现"心愿正在被推进"的证据。

## 心愿内容
{wish_content}

## 当前进度
{current_progress}%

## 当前里程碑清单
{milestones_text}

## 本次进展日志
{log_content}

## 任务
基于本次进展日志，判断：
1. 是否有证据表明某个里程碑已经完成？如果有，给出该里程碑在列表中的索引（从0开始），否则为 null
2. 心愿的整体进度是否应该更新？给出一个 0-100 的建议进度值，**不应低于当前进度**（除非日志明确说明退步/放弃），如果日志内容无法支撑任何进度判断，给 null
3. 给出你的判断置信度（0-1）和理由（一句话，20字以内）

## 输出 JSON 格式
```json
{{
  "suggested_progress": 45,
  "suggested_milestone_index": 1,
  "ai_confidence": 0.8,
  "ai_reason": "日志描述已完成里程碑2对应的行动"
}}
```

如果没有足够证据支撑判断，`suggested_progress` 和 `suggested_milestone_index` 都填 null，`ai_confidence` 给较低值（如 0.2）。
重要：只输出 JSON，不要输出其他内容。
"""


def _format_milestones(milestones: Optional[list]) -> str:
    if not milestones:
        return "（暂无里程碑）"
    lines = []
    for i, m in enumerate(milestones):
        state = "已完成" if m.get("completed") is True else ("未完成" if m.get("completed") is False else "待定")
        lines.append(f"{i}. [{state}] {m.get('text', '')}")
    return "\n".join(lines)


async def analyze_wish_log(wish_id: int, log_id: int, log_content: str) -> None:
    """BackgroundTask 入口：从进展日志分析心愿进度候选。
    使用独立 session，避免与原请求 session 冲突。
    """
    try:
        async with async_session_maker() as db:
            await _analyze_wish_log_impl(db, wish_id=wish_id, log_id=log_id, log_content=log_content)
            await db.commit()
    except Exception as e:
        logger.warning(f"analyze_wish_log 顶层失败: wish_id={wish_id} log_id={log_id} err={e}")


async def _analyze_wish_log_impl(db: AsyncSession, *, wish_id: int, log_id: int, log_content: str) -> None:
    if not log_content or len(log_content.strip()) < 2:
        return

    result = await db.execute(select(Wish).where(Wish.id == wish_id))
    wish = result.scalar_one_or_none()
    if not wish:
        logger.warning(f"analyze_wish_log: 心愿不存在 wish_id={wish_id}")
        return

    prompt = (
        ANALYZE_WISH_PROMPT
        .replace("{wish_content}", wish.content or "")
        .replace("{current_progress}", str(wish.progress or 0))
        .replace("{milestones_text}", _format_milestones(wish.milestones))
        .replace("{log_content}", log_content[:3000])
    )

    candidate: Optional[WishProgressCandidate] = None
    try:
        config = await get_active_ai_config(db, module_name=MODULE_NAME)
        if not config:
            raise RuntimeError("未配置 AI 模型")

        messages = [
            {"role": "system", "content": "你是一个严谨的 JSON 输出助手，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ]
        url, headers, payload = _build_request(config, messages)
        payload["max_tokens"] = min(config.max_tokens, 500)
        payload["temperature"] = 0.3

        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        model_name = f"{config.provider}/{config.model}"
        parsed = _parse_ai_json(content)

        suggested_progress = parsed.get("suggested_progress")
        suggested_milestone_index = parsed.get("suggested_milestone_index")

        candidate = WishProgressCandidate(
            wish_id=wish_id,
            source_id=log_id,
            suggested_progress=int(suggested_progress) if suggested_progress is not None else None,
            suggested_milestone_index=int(suggested_milestone_index) if suggested_milestone_index is not None else None,
            ai_confidence=float(parsed.get("ai_confidence") or 0.5),
            ai_reason=(parsed.get("ai_reason") or None),
            status="pending",
            extract_status="success",
            model_used=model_name,
        )
        db.add(candidate)
        logger.info(f"心愿进度候选提取成功: wish_id={wish_id} log_id={log_id}")
    except Exception as e:
        logger.warning(f"心愿进度候选提取失败: wish_id={wish_id} log_id={log_id} err={e}")
        candidate = WishProgressCandidate(
            wish_id=wish_id,
            source_id=log_id,
            status="rejected",
            extract_status="failed",
            error_msg=str(e)[:500],
        )
        db.add(candidate)

    # 标记该日志已处理过 AI 分析
    try:
        log_result = await db.execute(select(WishLogEntry).where(WishLogEntry.id == log_id))
        log_entry = log_result.scalar_one_or_none()
        if log_entry:
            log_entry.ai_processed = True
    except Exception as e:
        logger.warning(f"标记 WishLogEntry.ai_processed 失败: {e}")

    await db.flush()
