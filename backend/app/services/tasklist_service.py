"""任务单：把一段自然语言（收集箱内容/本周打算）拆成父子任务草稿。

只产出草稿，不写库；用户在对话里编辑确认后才由 create_tasklist 落库（fail-closed）。
"""
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_service import get_active_ai_config, _build_request, _parse_ai_json

logger = logging.getLogger(__name__)

SPLIT_PROMPT = """把用户下面这段内容拆成一个任务单草稿（父子结构），输出严格 JSON。

## 拆分规则
- 判断哪些是**独立的父任务**、哪些是某个父任务下的**子任务**（子任务是父任务的具体步骤/组成部分）
- 用户没明确层级时按语义归类；实在没有从属关系的就各自作为没有子任务的父任务
- 标题用可执行的一句话（动词开头），不改写用户原意、不丢信息
- 象限 quadrant：1重要紧急 2重要不紧急 3紧急不重要 4不重要不紧急，默认 2
- 紧急度 urgency：1-5，默认 3；子任务可与父任务不同
- 分类 category：work/learning/life/health/social/finance/creative，按内容判断
- 最多 8 个父任务，每个最多 8 个子任务

## 输出格式
{"groups": [{"parent": "父任务标题", "description": "补充说明（可空）", "quadrant": 2, "urgency": 3, "category": "work", "children": [{"title": "子任务1", "quadrant": 2, "urgency": 3}]}]}

## 用户内容
{content}"""


def _as_urgency(value, default: int = 3) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if 1 <= n <= 5 else default


def _normalize_child(c, parent_quadrant: int, parent_urgency: int) -> dict | None:
    if isinstance(c, dict):
        title = str(c.get("title") or "").strip()[:500]
        if not title:
            return None
        q = c.get("quadrant") if c.get("quadrant") in (1, 2, 3, 4) else parent_quadrant
        return {"title": title, "quadrant": q, "urgency": _as_urgency(c.get("urgency"), parent_urgency)}
    title = str(c or "").strip()[:500]
    if not title:
        return None
    return {"title": title, "quadrant": parent_quadrant, "urgency": parent_urgency}


def _normalize(parsed: dict) -> list[dict]:
    groups = []
    for g in (parsed.get("groups") or [])[:8]:
        parent = str(g.get("parent") or "").strip()[:500]
        if not parent:
            continue
        pq = g.get("quadrant") if g.get("quadrant") in (1, 2, 3, 4) else 2
        pu = _as_urgency(g.get("urgency"), 3)
        children = []
        for c in (g.get("children") or [])[:8]:
            child = _normalize_child(c, pq, pu)
            if child:
                children.append(child)
        groups.append({
            "parent": parent,
            "description": str(g.get("description") or "")[:2000],
            "quadrant": pq,
            "urgency": pu,
            "category": g.get("category") or None,
            "children": children,
        })
    return groups


async def split_tasklist(db: AsyncSession, content: str) -> list[dict]:
    """LLM 拆分，返回可编辑的 groups；失败抛异常由调用方降级"""
    config = await get_active_ai_config(db)
    if not config:
        raise ValueError("未配置 AI 模型")
    prompt = SPLIT_PROMPT.replace("{content}", content[:6000])
    url, headers, payload = _build_request(config, [{"role": "user", "content": prompt}])
    payload["max_tokens"] = min(config.max_tokens, 2048)
    payload["temperature"] = 0.2
    if config.provider == "deepseek":
        payload["thinking"] = {"type": "disabled"}
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
    groups = _normalize(_parse_ai_json(r.json()["choices"][0]["message"]["content"] or ""))
    if not groups:
        raise ValueError("没拆出任务，请写得更具体一些")
    return groups


async def create_tasklist(db: AsyncSession, session_id: int | None, groups: list[dict]) -> dict:
    """用户确认后落库：父任务 + 子任务（parent_id），来源记 agent_tasklist"""
    from app.models.todo import TodoItem
    created_parents = 0
    created_children = 0
    ids: list[int] = []
    for g in groups[:20]:
        title = str(g.get("parent") or "").strip()[:500]
        if not title:
            continue
        parent = TodoItem(
            title=title,
            description=g.get("description") or None,
            quadrant=g.get("quadrant") if g.get("quadrant") in (1, 2, 3, 4) else 2,
            urgency=_as_urgency(g.get("urgency"), 3),
            category=g.get("category") or None,
            status="planned",
            source="agent_tasklist",
            source_id=session_id,
        )
        db.add(parent)
        await db.flush()
        ids.append(parent.id)
        created_parents += 1
        for c in (g.get("children") or [])[:20]:
            child_title = str(c.get("title") if isinstance(c, dict) else c or "").strip()[:500]
            if not child_title:
                continue
            cq = c.get("quadrant") if isinstance(c, dict) and c.get("quadrant") in (1, 2, 3, 4) else parent.quadrant
            cu = _as_urgency(c.get("urgency") if isinstance(c, dict) else None, parent.urgency)
            db.add(TodoItem(
                title=child_title,
                parent_id=parent.id,
                quadrant=cq,
                urgency=cu,
                category=parent.category,
                status="planned",
                source="agent_tasklist",
                source_id=session_id,
            ))
            created_children += 1
    await db.commit()
    logger.info(f"任务单已创建：{created_parents} 个父任务 / {created_children} 个子任务")
    return {"parents": created_parents, "children": created_children, "ids": ids}
