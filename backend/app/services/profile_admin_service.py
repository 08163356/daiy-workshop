"""画像管理服务：CRUD + 快照/回滚 + 整理提案（consent-first）

提案流：build_consolidation_plan（AI 出方案，不写库）→ 用户确认 → apply_proposal
（先自动快照，再按 plan 逐条执行）。任何一步出错都有快照可回滚。
"""
import logging
from collections import defaultdict
from datetime import datetime

import httpx
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_config import UserProfile
from app.models.profile_admin import ProfileProposal, ProfileSnapshot
from app.services.ai_service import get_active_ai_config, _build_request, _parse_ai_json

logger = logging.getLogger(__name__)

CANONICAL_CATEGORIES = [
    "基本信息", "性格特征", "职业发展", "投资风格", "学习偏好", "情绪模式",
    "核心关注", "成长目标", "个人资源", "专业技能", "人脉网络", "工具资源",
    "生活状态", "健康运动", "家庭关系", "价值观信念",
]

# ==================== CRUD ====================

async def list_grouped(db: AsyncSession) -> dict:
    """画像按分类分组返回（设置页展示用）"""
    result = await db.execute(
        select(UserProfile).order_by(UserProfile.category, UserProfile.confidence.desc())
    )
    rows = result.scalars().all()
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[r.category].append({
            "id": r.id, "key": r.key, "value": r.value,
            "confidence": r.confidence, "source_count": r.source_count,
            "last_evidence": r.last_evidence, "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
    return {
        "total": len(rows),
        "total_chars": sum(len(r.key) + len(r.value) for r in rows),
        "groups": [{"category": c, "items": items} for c, items in groups.items()],
    }


async def update_entry(db: AsyncSession, entry_id: int, fields: dict) -> UserProfile:
    row = await db.get(UserProfile, entry_id)
    if not row:
        raise ValueError("条目不存在")
    for f in ("key", "value", "category", "confidence"):
        if f in fields and fields[f] is not None:
            setattr(row, f, fields[f])
    row.updated_at = datetime.now()
    await db.flush()
    await db.commit()
    return row


async def delete_entry(db: AsyncSession, entry_id: int) -> None:
    row = await db.get(UserProfile, entry_id)
    if not row:
        raise ValueError("条目不存在")
    await db.delete(row)
    await db.commit()


# ==================== 快照 ====================

async def snapshot_profile(db: AsyncSession, reason: str) -> ProfileSnapshot:
    """全量快照（整理前自动调用；也可手动触发）"""
    result = await db.execute(select(UserProfile))
    rows = result.scalars().all()
    snap = ProfileSnapshot(
        reason=reason,
        entry_count=len(rows),
        data=[{
            "category": r.category, "key": r.key, "value": r.value,
            "confidence": r.confidence, "source_count": r.source_count,
            "last_evidence": r.last_evidence,
        } for r in rows],
    )
    db.add(snap)
    await db.flush()
    await db.commit()
    logger.info(f"画像快照 #{snap.id}：{len(rows)} 条（{reason}）")
    return snap


async def list_snapshots(db: AsyncSession) -> list[ProfileSnapshot]:
    result = await db.execute(
        select(ProfileSnapshot).order_by(ProfileSnapshot.created_at.desc())
    )
    return list(result.scalars())


async def rollback_snapshot(db: AsyncSession, snapshot_id: int) -> int:
    """回滚到快照：清空画像层并按快照重建。返回恢复条数。操作前会自动再快照一次当前状态"""
    snap = await db.get(ProfileSnapshot, snapshot_id)
    if not snap:
        raise ValueError("快照不存在")
    # 回滚前也留一个当前状态的快照（防误回滚）
    await snapshot_profile(db, f"回滚到快照#{snapshot_id}之前的自动备份")
    await db.execute(delete(UserProfile))
    for item in snap.data:
        db.add(UserProfile(
            category=item["category"], key=item["key"], value=item["value"],
            confidence=item.get("confidence", 0.3), source_count=item.get("source_count", 1),
            last_evidence=item.get("last_evidence"),
        ))
    await db.commit()
    logger.info(f"画像已回滚到快照 #{snapshot_id}（{snap.entry_count} 条）")
    return snap.entry_count


# ==================== 整理提案（consent-first） ====================

CATEGORY_MAP_PROMPT = """下面是用户画像系统里的全部分类名（带条目数），碎片化严重。

请把每个旧分类映射到标准分类之一：
{canonical}

规则：优先映射语义最接近的标准分类；实在不贴切可新建（克制）。输出严格 JSON：{{"旧分类名": "标准分类名"}}，每个旧分类都要出现。

旧分类列表：
{categories}"""

MERGE_PROMPT = """下面是用户画像「{category}」分类下的条目（id | key: value）。

找出**语义重复**的条目组合并。规则：
- 只有确实是同一特征才合并，拿不准不动（准确性优先）
- 合并后 value 保留各条全部有效信息，整合成完整表述
- 输出严格 JSON：{{"merges": [{{"keep_id": 保留条目id, "merge_ids": [被合并id...], "merged_value": "合并后表述"}}]}}
- 没有可合并输出 {{"merges": []}}

条目列表：
{entries}"""


async def _ai_json(config, prompt: str, max_tokens: int = 4000) -> dict:
    url, headers, payload = _build_request(config, [{"role": "user", "content": prompt}])
    payload["max_tokens"] = min(config.max_tokens, max_tokens)
    payload["temperature"] = 0.1
    if config.provider == "deepseek":
        payload["thinking"] = {"type": "disabled"}
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return _parse_ai_json(r.json()["choices"][0]["message"]["content"] or "")


def _exact_dupes(rows: list[UserProfile]) -> list[int]:
    """同 (category, key) 保留置信度最高/最新，返回待删 id"""
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r.category, r.key)].append(r)
    delete_ids: list[int] = []
    for group in groups.values():
        if len(group) > 1:
            group.sort(key=lambda r: (r.confidence, r.updated_at or datetime.min), reverse=True)
            delete_ids.extend(r.id for r in group[1:])
    return delete_ids


async def build_consolidation_plan(db: AsyncSession) -> ProfileProposal:
    """AI 生成整理提案（不写画像表，只存提案）"""
    # 有 pending 提案就先拒绝重复生成
    existing = await db.execute(
        select(ProfileProposal).where(ProfileProposal.status == "pending")
    )
    if existing.scalars().first():
        raise ValueError("已有一份待确认的整理提案，请先处理它")

    rows = list((await db.execute(select(UserProfile))).scalars().all())
    if not rows:
        raise ValueError("画像为空，无需整理")
    config = await get_active_ai_config(db)
    if not config:
        raise ValueError("未配置 AI 模型")

    plan = {"dedup_delete_ids": [], "category_changes": [], "merges": []}

    # 阶段 1：精确去重
    dupes = _exact_dupes(rows)
    plan["dedup_delete_ids"] = dupes
    alive = [r for r in rows if r.id not in dupes]

    # 阶段 2：分类归一（分类数超过标准集才调 AI）
    categories = sorted(set(r.category for r in alive))
    if len(categories) > len(CANONICAL_CATEGORIES):
        cat_list = "\n".join(f"- {c}" for c in categories)
        mapping = await _ai_json(config, CATEGORY_MAP_PROMPT.replace(
            "{canonical}", " / ".join(CANONICAL_CATEGORIES)).replace("{categories}", cat_list),
            max_tokens=6000)
        for r in alive:
            new_cat = mapping.get(r.category)
            if new_cat and new_cat != r.category:
                plan["category_changes"].append({"id": r.id, "from": r.category, "to": new_cat})

    # 模拟应用分类归一后的精确去重（同分类同 key 相撞）
    sim_cat = {r.id: r.category for r in alive}
    for ch in plan["category_changes"]:
        sim_cat[ch["id"]] = ch["to"]
    groups2: dict[tuple, list] = defaultdict(list)
    for r in alive:
        groups2[(sim_cat[r.id], r.key)].append(r)
    for group in groups2.values():
        if len(group) > 1:
            group.sort(key=lambda r: (r.confidence, r.updated_at or datetime.min), reverse=True)
            plan["dedup_delete_ids"].extend(r.id for r in group[1:])
    alive = [r for r in alive if r.id not in plan["dedup_delete_ids"]]

    # 阶段 3：同义合并（按归一后的分类）
    by_cat: dict[str, list] = defaultdict(list)
    for r in alive:
        by_cat[sim_cat[r.id]].append(r)
    for cat, items in by_cat.items():
        if len(items) < 2:
            continue
        entries = "\n".join(f"- {r.id} | {r.key}: {r.value}" for r in items)
        if len(entries) < 200:
            continue
        try:
            result = await _ai_json(config, MERGE_PROMPT.replace("{category}", cat).replace("{entries}", entries))
        except Exception as e:
            logger.warning(f"[{cat}] 合并判断失败跳过: {e}")
            continue
        id_set = {r.id for r in items}
        for m in (result.get("merges") or []):
            keep_id = m.get("keep_id")
            merge_ids = [i for i in (m.get("merge_ids") or []) if i in id_set and i != keep_id]
            if keep_id in id_set and merge_ids and m.get("merged_value"):
                keep_row = next(r for r in items if r.id == keep_id)
                plan["merges"].append({
                    "keep_id": keep_id, "keep_key": keep_row.key,
                    "merge_ids": merge_ids,
                    "merge_keys": [next(r for r in items if r.id == i).key for i in merge_ids],
                    "merged_value": m["merged_value"][:2000],
                })

    after_count = len(rows) - len(plan["dedup_delete_ids"]) - sum(len(m["merge_ids"]) for m in plan["merges"])
    summary_parts = [
        f"精确去重 {len(plan['dedup_delete_ids'])} 条",
        f"分类归一 {len(plan['category_changes'])} 条",
        f"同义合并 {len(plan['merges'])} 组（{sum(len(m['merge_ids']) for m in plan['merges'])} 条并入）",
        f"预计 {len(rows)} 条 → {after_count} 条",
    ]
    proposal = ProfileProposal(
        status="pending",
        summary="；".join(summary_parts),
        plan=plan,
        stats={"before_count": len(rows), "after_count": after_count,
               "before_chars": sum(len(r.key) + len(r.value) for r in rows)},
    )
    db.add(proposal)
    await db.flush()
    await db.commit()
    logger.info(f"画像整理提案 #{proposal.id} 已生成：{proposal.summary}")
    return proposal


async def apply_proposal(db: AsyncSession, proposal_id: int) -> dict:
    """确认后执行提案：先自动快照，再按计划逐条执行"""
    proposal = await db.get(ProfileProposal, proposal_id)
    if not proposal:
        raise ValueError("提案不存在")
    if proposal.status != "pending":
        raise ValueError("提案已处理过")

    snap = await snapshot_profile(db, f"整理提案#{proposal_id}执行前自动快照")
    plan = proposal.plan
    applied = {"dedup": 0, "category": 0, "merge": 0}

    # 1. 分类归一
    for ch in plan.get("category_changes", []):
        row = await db.get(UserProfile, ch["id"])
        if row:
            row.category = ch["to"]
            applied["category"] += 1
    # 2. 精确去重删除
    for rid in plan.get("dedup_delete_ids", []):
        row = await db.get(UserProfile, rid)
        if row:
            await db.delete(row)
            applied["dedup"] += 1
    # 3. 同义合并
    for m in plan.get("merges", []):
        keep = await db.get(UserProfile, m["keep_id"])
        if not keep:
            continue
        keep.value = m["merged_value"]
        keep.updated_at = datetime.now()
        for mid in m["merge_ids"]:
            row = await db.get(UserProfile, mid)
            if row:
                keep.confidence = max(keep.confidence, row.confidence)
                await db.delete(row)
        applied["merge"] += 1

    proposal.status = "applied"
    proposal.applied_at = datetime.now()
    await db.commit()

    remaining = len((await db.execute(select(UserProfile))).scalars().all())
    logger.info(f"提案 #{proposal_id} 已执行：{applied}，剩余 {remaining} 条（快照 #{snap.id}）")
    return {"applied": applied, "remaining": remaining, "snapshot_id": snap.id}


async def reject_proposal(db: AsyncSession, proposal_id: int) -> None:
    proposal = await db.get(ProfileProposal, proposal_id)
    if not proposal:
        raise ValueError("提案不存在")
    if proposal.status != "pending":
        raise ValueError("提案已处理过")
    proposal.status = "rejected"
    await db.commit()
