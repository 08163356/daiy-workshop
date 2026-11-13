"""导出 JSON 数据脚本（用于前端静态构建）"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import date, datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.models import Note, Concept, NoteConcept, ConceptRelation
from app.services.graph_service import GraphService


class DateTimeEncoder(json.JSONEncoder):
    """日期时间 JSON 编码器"""

    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


async def export_json():
    """导出所有数据为 JSON"""
    print("=" * 50)
    print("读书管理系统 - 数据导出")
    print("=" * 50)

    output_dir = project_root / "exports"
    output_dir.mkdir(exist_ok=True)

    await init_db()

    async with async_session_maker() as db:
        # 导出笔记列表
        print("\n导出笔记列表...")
        notes = await db.scalars(
            select(Note).order_by(Note.reading_date.desc())
        )
        notes_data = []
        for note in notes:
            # 获取关联概念
            note_concepts = await db.scalars(
                select(NoteConcept).where(NoteConcept.note_id == note.id)
            )
            concept_ids = [nc.concept_id for nc in note_concepts]

            notes_data.append({
                "id": note.id,
                "filename": note.filename,
                "title": note.title,
                "summary": note.summary,
                "reading_date": note.reading_date,
                "word_count": note.word_count,
                "concept_ids": concept_ids,
            })

        with open(output_dir / "notes.json", "w", encoding="utf-8") as f:
            json.dump(notes_data, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
        print(f"  ✅ 导出 {len(notes_data)} 篇笔记")

        # 导出概念列表
        print("\n导出概念列表...")
        concepts = await db.scalars(
            select(Concept).order_by(Concept.importance.desc())
        )
        concepts_data = [
            {
                "id": c.id,
                "name": c.name,
                "category": c.category,
                "importance": c.importance,
                "mention_count": c.mention_count,
            }
            for c in concepts
        ]

        with open(output_dir / "concepts.json", "w", encoding="utf-8") as f:
            json.dump(concepts_data, f, ensure_ascii=False, indent=2)
        print(f"  ✅ 导出 {len(concepts_data)} 个概念")

        # 导出知识图谱
        print("\n导出知识图谱...")
        graph_service = GraphService(db)
        graph = await graph_service.get_graph()

        graph_data = {
            "nodes": [node.model_dump() for node in graph.nodes],
            "edges": [edge.model_dump() for edge in graph.edges],
        }

        with open(output_dir / "graph.json", "w", encoding="utf-8") as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)
        print(f"  ✅ 导出 {len(graph_data['nodes'])} 个节点，{len(graph_data['edges'])} 条边")

        # 导出完整笔记内容（可选）
        print("\n导出笔记完整内容...")
        notes_full = await db.scalars(select(Note))
        notes_content = {
            str(note.id): {
                "title": note.title,
                "content": note.content,
            }
            for note in notes_full
        }

        with open(output_dir / "notes_content.json", "w", encoding="utf-8") as f:
            json.dump(notes_content, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 50)
    print(f"✅ 导出完成！文件保存在: {output_dir}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(export_json())
