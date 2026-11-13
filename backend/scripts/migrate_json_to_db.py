"""
一次性迁移脚本：将所有 JSON 静态文件数据导入数据库
- knowledge.json → knowledge_categories + knowledge_items
- models.json → thinking_models (更新)
- graph.json → knowledge_graph
- overview.json → reading_overview
- timeline.json → 确保 notes 表有对应记录

运行方式：
  cd reading-system/backend
  python scripts/migrate_json_to_db.py
"""

import asyncio
import json
import os
import sys
import re

# 将 backend 根目录加入路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from app.core.database import engine, async_session_maker, init_db
from app.models.knowledge import (
    KnowledgeCategory, KnowledgeItem, KnowledgeGraph, ReadingOverview,
)
from app.models.thinking_model import ThinkingModel


def load_json(filename: str) -> any:
    """从多个可能的位置加载 JSON 文件"""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    paths = [
        os.path.join(base_dir, 'frontend', 'public', 'data', filename),
        os.path.join(base_dir, 'data', filename),
        os.path.join(base_dir, '..', 'data', filename),
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"  ✅ 从 {p} 加载了 {filename}")
            return data
    print(f"  ❌ 未找到 {filename}")
    return None


def clean_html(text: str) -> str:
    """清理 HTML 标签"""
    return re.sub(r'<[^>]+>', ' ', text).strip()


async def migrate_knowledge(session):
    """迁移 knowledge.json → knowledge_categories + knowledge_items"""
    print("\n📚 迁移 knowledge.json ...")
    data = load_json('knowledge.json')
    if not data:
        return

    cat_count = 0
    item_count = 0

    for idx, category in enumerate(data):
        title = category.get('title', f'未分类_{idx}')
        items = category.get('items', [])

        # 检查分类是否已存在
        existing = await session.scalar(
            select(KnowledgeCategory).where(KnowledgeCategory.title == title)
        )
        if existing:
            existing.item_count = len(items)
            existing.sort_order = idx
            cat_obj = existing
            print(f"  📂 更新分类: {title} ({len(items)} 条)")
        else:
            cat_obj = KnowledgeCategory(
                title=title,
                sort_order=idx,
                item_count=len(items),
            )
            session.add(cat_obj)
            cat_count += 1
            print(f"  📂 新建分类: {title} ({len(items)} 条)")

        # 导入条目
        for item in items:
            name = item.get('name', '').strip()
            if not name:
                continue
            desc = item.get('description', '')

            # 检查同分类下是否已有同名条目
            existing_item = await session.scalar(
                select(KnowledgeItem).where(
                    KnowledgeItem.name == name,
                    KnowledgeItem.category_title == title,
                )
            )
            if existing_item:
                if desc and len(desc) > len(existing_item.description or ''):
                    existing_item.description = desc
                continue

            ki = KnowledgeItem(
                name=name,
                description=desc,
                category_title=title,
                importance=1,
                mention_count=1,
                source='seed',
            )
            session.add(ki)
            item_count += 1

    await session.flush()
    print(f"  ✅ 导入 {cat_count} 个新分类, {item_count} 个新知识条目")


async def migrate_models(session):
    """迁移 models.json → thinking_models"""
    print("\n🧠 迁移 models.json ...")
    data = load_json('models.json')
    if not data:
        return

    imported = 0
    updated = 0

    for m in data:
        title = m.get('title', '').strip()
        if not title:
            continue
        desc = m.get('description', '')

        existing = await session.scalar(
            select(ThinkingModel).where(ThinkingModel.title == title)
        )
        if existing:
            if desc and len(desc) > len(existing.description or ''):
                existing.description = desc
                updated += 1
            continue

        model = ThinkingModel(
            title=title,
            description=desc,
            mention_count=1,
        )
        session.add(model)
        imported += 1

    await session.flush()
    print(f"  ✅ 新增 {imported} 个模型, 更新 {updated} 个模型")


async def migrate_graph(session):
    """迁移 graph.json → knowledge_graph"""
    print("\n🔗 迁移 graph.json ...")
    data = load_json('graph.json')
    if not data:
        return

    # 先检查表里有没有数据，有的话清空（图谱数据是全量替换）
    existing_count = await session.scalar(
        select(__import__('sqlalchemy').func.count(KnowledgeGraph.id))
    )
    if existing_count and existing_count > 0:
        print(f"  ⚠️  knowledge_graph 表已有 {existing_count} 条记录，跳过（如需重导请手动清空）")
        return

    nodes = data.get('nodes', [])
    edges = data.get('edges', [])
    node_count = 0
    edge_count = 0

    for n in nodes:
        entry = KnowledgeGraph(
            entry_type='node',
            original_id=str(n.get('id', '')),
            label=n.get('label', ''),
            category=n.get('category', ''),
            description=n.get('description', ''),
            importance=n.get('importance', 2),
            node_size=n.get('size', 30),
        )
        session.add(entry)
        node_count += 1

    for e in edges:
        entry = KnowledgeGraph(
            entry_type='edge',
            source_id=str(e.get('source', '')),
            target_id=str(e.get('target', '')),
            edge_type=e.get('type', 'same_category'),
            strength=e.get('strength', 0.5),
        )
        session.add(entry)
        edge_count += 1

    await session.flush()
    print(f"  ✅ 导入 {node_count} 个节点, {edge_count} 条边")


async def migrate_overview(session):
    """迁移 overview.json → reading_overview"""
    print("\n📊 迁移 overview.json ...")
    data = load_json('overview.json')
    if not data:
        return

    # 查找或创建唯一的概览记录
    existing = await session.scalar(select(ReadingOverview).limit(1))
    if existing:
        existing.reading_days = data.get('reading_days', 0)
        existing.books_count = data.get('books_count', 0)
        existing.concepts_count = data.get('concepts_count', 0)
        existing.ai_comments = data.get('ai_comments', 0)
        existing.progress = data.get('progress', {})
        print(f"  ✅ 更新概览: {data.get('books_count', 0)} 本书, {data.get('reading_days', 0)} 天")
    else:
        overview = ReadingOverview(
            reading_days=data.get('reading_days', 0),
            books_count=data.get('books_count', 0),
            concepts_count=data.get('concepts_count', 0),
            ai_comments=data.get('ai_comments', 0),
            progress=data.get('progress', {}),
        )
        session.add(overview)
        print(f"  ✅ 创建概览: {data.get('books_count', 0)} 本书, {data.get('reading_days', 0)} 天")

    await session.flush()


async def main():
    print("=" * 60)
    print("🚀 JSON → 数据库 全量迁移")
    print("=" * 60)

    # 初始化数据库（确保新表已创建）
    await init_db()
    print("✅ 数据库表初始化完成")

    async with async_session_maker() as session:
        try:
            await migrate_knowledge(session)
            await migrate_models(session)
            await migrate_graph(session)
            await migrate_overview(session)

            await session.commit()
            print("\n" + "=" * 60)
            print("🎉 全部迁移完成！")
            print("=" * 60)
        except Exception as e:
            await session.rollback()
            print(f"\n❌ 迁移失败: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
