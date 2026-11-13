"""画像整理：去重 + 分类归一 + 同义合并（准确性优先，AI 驱动）

用法（服务器上）：
    PYTHONPATH=. venv/bin/python scripts/consolidate_profile.py [--dry-run]

三个阶段：
1. 精确去重：同 (category, key) 保留置信度最高/最新的，其余删除
2. 分类归一：AI 把 170+ 个碎片化分类映射到标准分类集合
3. 同义合并：每个分类内 AI 判断语义重复的 key，合并 value（保留信息更全的表述）

安全性：--dry-run 只打印不写库；正式运行前请先备份 db 文件。
"""
import argparse
import asyncio
import json
import logging
from collections import defaultdict

import httpx
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.ai_config import UserProfile
from app.services.ai_service import get_active_ai_config, _build_request, _parse_ai_json

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CANONICAL_CATEGORIES = [
    "基本信息", "性格特征", "职业发展", "投资风格", "学习偏好", "情绪模式",
    "核心关注", "成长目标", "个人资源", "专业技能", "人脉网络", "工具资源",
    "生活状态", "健康运动", "家庭关系", "价值观信念",
]

CATEGORY_MAP_PROMPT = """下面是一个用户画像系统里出现的全部分类名（带条目数）。它们碎片化严重（如"心理模式/心理状态/心理特征"指同一类东西）。

请把每个旧分类映射到标准分类之一：
{canonical}

规则：
- 优先映射到语义最接近的标准分类
- 实在不贴切的可以新建分类名（但要克制，能归就归）
- 输出严格 JSON 对象：{{"旧分类名": "标准分类名", ...}}，每个旧分类都必须出现

旧分类列表：
{categories}"""

MERGE_PROMPT ="""下面是用户画像「{category}」分类下的所有条目（key: value）。

请找出**语义重复**的条目组（说的是同一件事/同一个特征），合并它们。

规则：
- 只有确实是同一特征的才合并，拿不准的不动（准确性优先，宁可不合并）
- 合并后的 value 要保留各条目的全部有效信息，整合成一段完整表述
- 合并后保留信息最丰富的 key 名（或起个更准确的）
- 输出严格 JSON：{{"merges": [{{"keep_key": "保留的key", "merge_keys": ["被合并的key1", ...], "merged_value": "合并后的完整表述"}}]}}
- 没有可合并的就输出 {{"merges": []}}

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
        content = r.json()["choices"][0]["message"]["content"] or ""
    return _parse_ai_json(content)


async def phase1_exact_dedup(db, dry_run: bool) -> int:
    """同 (category, key) 去重，保留置信度最高/最新"""
    result = await db.execute(select(UserProfile))
    rows = result.scalars().all()
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r.category, r.key)].append(r)
    removed = 0
    for (cat, key), group in groups.items():
        if len(group) <= 1:
            continue
        group.sort(key=lambda r: (r.confidence, r.updated_at), reverse=True)
        for dup in group[1:]:
            removed += 1
            logger.info(f"  去重删除: [{cat}] {key}（置信度 {dup.confidence:.2f}）")
            if not dry_run:
                await db.delete(dup)
    if not dry_run:
        await db.commit()
    logger.info(f"阶段1 精确去重：删除 {removed} 条")
    return removed


async def phase2_canonicalize(db, config, dry_run: bool) -> int:
    """AI 把碎片分类映射到标准分类"""
    result = await db.execute(select(UserProfile))
    rows = result.scalars().all()
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r.category] += 1
    old_categories = sorted(counts.keys())
    if len(old_categories) <= len(CANONICAL_CATEGORIES):
        logger.info("阶段2 分类已规整，跳过")
        return 0

    cat_list = "\n".join(f"- {c}（{counts[c]} 条）" for c in old_categories)
    prompt = (CATEGORY_MAP_PROMPT
              .replace("{canonical}", " / ".join(CANONICAL_CATEGORIES))
              .replace("{categories}", cat_list))
    mapping = await _ai_json(config, prompt, max_tokens=6000)

    changed = 0
    for r in rows:
        new_cat = mapping.get(r.category)
        if new_cat and new_cat != r.category:
            changed += 1
            if changed <= 30 or changed % 50 == 0:
                logger.info(f"  归一: [{r.category}] → [{new_cat}] {r.key}")
            if not dry_run:
                r.category = new_cat
    if not dry_run:
        await db.commit()
    missing = [c for c in old_categories if c not in mapping]
    if missing:
        logger.warning(f"  AI 漏映射的分类（保持原样）: {missing[:10]}")
    logger.info(f"阶段2 分类归一：{len(old_categories)} 个旧分类 → 修改 {changed} 条")
    return changed


async def phase3_semantic_merge(db, config, dry_run: bool) -> int:
    """每个分类内 AI 同义合并"""
    result = await db.execute(select(UserProfile).order_by(UserProfile.category))
    rows = result.scalars().all()
    by_cat: dict[str, list] = defaultdict(list)
    for r in rows:
        by_cat[r.category].append(r)

    total_merged = 0
    for cat, items in by_cat.items():
        if len(items) < 2:
            continue
        entries = "\n".join(f"- {r.key}: {r.value}" for r in items)
        if len(entries) < 200:  # 太短没东西可合
            continue
        prompt = MERGE_PROMPT.replace("{category}", cat).replace("{entries}", entries)
        try:
            result_json = await _ai_json(config, prompt)
        except Exception as e:
            logger.warning(f"  [{cat}] 合并判断失败跳过: {e}")
            continue
        merges = result_json.get("merges") or []
        key_map = {r.key: r for r in items}
        for m in merges:
            keep = key_map.get(m.get("keep_key"))
            merge_rows = [key_map[k] for k in (m.get("merge_keys") or []) if k in key_map]
            if not keep or not merge_rows:
                continue
            total_merged += len(merge_rows)
            logger.info(f"  [{cat}] 合并 {len(merge_rows)} 条 → {keep.key}")
            if not dry_run:
                keep.value = (m.get("merged_value") or keep.value)[:2000]
                keep.confidence = max(keep.confidence, max(r.confidence for r in merge_rows))
                for r in merge_rows:
                    await db.delete(r)
        if not dry_run:
            await db.commit()
    logger.info(f"阶段3 同义合并：合并删除 {total_merged} 条")
    return total_merged


async def main(dry_run: bool):
    async with async_session_maker() as db:
        before = (await db.execute(select(UserProfile))).scalars().all()
        before_chars = sum(len(r.key) + len(r.value) for r in before)
        logger.info(f"整理前：{len(before)} 条 / {before_chars} 字 / {len(set(r.category for r in before))} 个分类\n")

        await phase1_exact_dedup(db, dry_run)

        config = await get_active_ai_config(db)
        if not config:
            logger.error("未配置 AI 模型，无法进行 AI 归一/合并")
            return
        await phase2_canonicalize(db, config, dry_run)
        # 归一后再跑一次精确去重（同分类下同 key 可能相撞）
        await phase1_exact_dedup(db, dry_run)
        await phase3_semantic_merge(db, config, dry_run)

        if dry_run:
            await db.rollback()
            logger.info("\n[dry-run] 未写入任何修改")
        else:
            after = (await db.execute(select(UserProfile))).scalars().all()
            after_chars = sum(len(r.key) + len(r.value) for r in after)
            logger.info(f"\n整理后：{len(after)} 条 / {after_chars} 字 / {len(set(r.category for r in after))} 个分类")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印不写库")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
