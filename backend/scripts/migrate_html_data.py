"""从现有 HTML 迁移数据到数据库

功能：
1. 解析读书管理系统.html，提取：
   - 总览数据（统计信息）
   - 时间线条目
   - 思维模型
   - 知识分类
2. 导入到 SQLite 数据库
3. 建立概念之间的关联关系
"""

import os
import re
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime, date
from dataclasses import dataclass, field, asdict
from typing import Optional

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.database import Base
from app.models.note import Note, NoteConcept
from app.models.concept import Concept
from app.models.relation import ConceptRelation


# ============================================
# 数据结构定义
# ============================================

@dataclass
class OverviewData:
    """总览数据"""
    reading_days: int = 0
    books_count: int = 0
    concepts_count: int = 0
    ai_comments: int = 0
    progress: dict = field(default_factory=dict)  # 学习进度


@dataclass
class TimelineItem:
    """时间线条目"""
    date: str  # 2024.12.30 格式
    title: str
    content: str  # HTML 内容
    key_points: list[str] = field(default_factory=list)  # 提取的关键点


@dataclass
class ThinkingModel:
    """思维模型"""
    title: str
    description: str  # HTML 描述


@dataclass
class KnowledgeCategory:
    """知识分类"""
    title: str  # 分类标题，如 "🎲 不确定性科学"
    items: list[dict] = field(default_factory=list)  # [{name, description}]


@dataclass
class MigratedData:
    """迁移数据汇总"""
    overview: OverviewData = field(default_factory=OverviewData)
    timeline: list[TimelineItem] = field(default_factory=list)
    models: list[ThinkingModel] = field(default_factory=list)
    knowledge: list[KnowledgeCategory] = field(default_factory=list)


# ============================================
# HTML 解析器
# ============================================

class HTMLDataParser:
    """HTML 数据解析器"""

    def __init__(self, html_path: Path):
        self.html_path = html_path
        self.html_content = html_path.read_text(encoding="utf-8")

    def parse_all(self) -> MigratedData:
        """解析所有数据"""
        data = MigratedData()
        data.overview = self.parse_overview()
        data.timeline = self.parse_timeline()
        data.models = self.parse_models()
        data.knowledge = self.parse_knowledge()
        return data

    def parse_overview(self) -> OverviewData:
        """解析总览数据"""
        overview = OverviewData()

        # 提取统计数字
        patterns = {
            'reading_days': r'id="reading-days">(\d+)<',
            'books_count': r'id="books-count">(\d+)<',
            'concepts_count': r'id="concepts-count">(\d+)<',
            'ai_comments': r'id="ai-comments">(\d+)<',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, self.html_content)
            if match:
                setattr(overview, key, int(match.group(1)))

        # 提取学习进度
        progress_pattern = r'<div class="progress-item">\s*<span>([^<]+)</span>\s*<div class="progress-bar">\s*<div class="progress-fill" style="width:\s*(\d+)%"'
        for match in re.finditer(progress_pattern, self.html_content):
            overview.progress[match.group(1).strip()] = int(match.group(2))

        return overview

    def parse_timeline(self) -> list[TimelineItem]:
        """解析时间线"""
        timeline = []

        # 匹配时间线条目
        item_pattern = r'<div class="timeline-item">\s*<div class="timeline-date">([^<]+)</div>\s*<div class="timeline-title">([^<]+)</div>\s*<div class="timeline-content">(.*?)</div>\s*</div>'

        for match in re.finditer(item_pattern, self.html_content, re.DOTALL):
            date_str = match.group(1).strip()
            title = match.group(2).strip()
            content = match.group(3).strip()

            # 提取关键点（<strong>标签内容）
            key_points = re.findall(r'<strong>([^<]+)</strong>', content)

            timeline.append(TimelineItem(
                date=date_str,
                title=title,
                content=content,
                key_points=key_points
            ))

        return timeline

    def parse_models(self) -> list[ThinkingModel]:
        """解析思维模型"""
        models = []

        # 匹配思维模型卡片
        card_pattern = r'<div class="model-card"[^>]*>\s*<div class="model-title">([^<]+)</div>\s*<div class="model-description">(.*?)</div>\s*</div>'

        for match in re.finditer(card_pattern, self.html_content, re.DOTALL):
            title = match.group(1).strip()
            description = match.group(2).strip()

            models.append(ThinkingModel(
                title=title,
                description=description
            ))

        return models

    def parse_knowledge(self) -> list[KnowledgeCategory]:
        """解析知识分类"""
        knowledge = []

        # 匹配知识分类区块
        category_pattern = r'<div class="knowledge-category">\s*<div class="category-title">([^<]+)</div>(.*?)</div>\s*(?=<div class="knowledge-category">|</div>\s*</section>)'

        for match in re.finditer(category_pattern, self.html_content, re.DOTALL):
            category_title = match.group(1).strip()
            items_html = match.group(2)

            # 提取知识条目
            item_pattern = r'<div class="knowledge-item">\s*<strong>([^<]+)</strong><br>\s*([^<]+)'
            items = []
            for item_match in re.finditer(item_pattern, items_html):
                items.append({
                    'name': item_match.group(1).strip(),
                    'description': item_match.group(2).strip()
                })

            knowledge.append(KnowledgeCategory(
                title=category_title,
                items=items
            ))

        return knowledge


# ============================================
# 数据库导入器
# ============================================

class DataImporter:
    """数据导入器"""

    # 知识分类到概念分类的映射
    CATEGORY_MAPPING = {
        "🎲 不确定性科学": "不确定性科学",
        "🚀 个人效能": "个人效能",
        "🧠 认知框架": "认知框架",
        "💰 投资理财": "投资理财",
        "🚨 生命安全": "生命安全",
        "⚖️ 实用技能": "实用技能",
        "💡 创新与技术": "创新与技术",
        "📝 内容创作": "内容创作",
        "🏥 健康科学": "健康科学",
        "💡 人生智慧": "人生智慧",
        "🎰 行为设计": "行为设计",
        "💬 沟通技能": "沟通技能",
        "🏃 运动科学": "运动科学",
    }

    def __init__(self, db_path: str):
        self.db_url = f"sqlite+aiosqlite:///{db_path}"
        self.engine = create_async_engine(self.db_url, echo=False)
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def init_db(self):
        """初始化数据库"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def clear_data(self):
        """清空现有数据（谨慎使用）"""
        async with self.session_maker() as session:
            await session.execute(text("DELETE FROM concept_relations"))
            await session.execute(text("DELETE FROM note_concepts"))
            await session.execute(text("DELETE FROM concepts"))
            # 不删除 notes 表，保留 MD 文件同步的数据
            await session.commit()

    async def import_all(self, data: MigratedData):
        """导入所有数据"""
        print("=" * 50)
        print("开始数据迁移...")
        print("=" * 50)

        # 1. 从知识分类导入概念
        concepts_map = await self.import_concepts_from_knowledge(data.knowledge)
        print(f"✓ 导入概念: {len(concepts_map)} 个")

        # 2. 从思维模型补充概念
        models_concepts = await self.import_concepts_from_models(data.models, concepts_map)
        concepts_map.update(models_concepts)
        print(f"✓ 从模型补充概念: {len(models_concepts)} 个")

        # 3. 建立概念关系（同分类内的概念互相关联）
        relations_count = await self.create_concept_relations(data.knowledge, concepts_map)
        print(f"✓ 建立概念关系: {relations_count} 个")

        # 4. 导出为 JSON（供前端静态使用）
        await self.export_to_json(data, concepts_map)
        print("✓ 导出 JSON 完成")

        print("=" * 50)
        print("数据迁移完成！")
        print("=" * 50)

        return concepts_map

    async def import_concepts_from_knowledge(
        self, knowledge: list[KnowledgeCategory]
    ) -> dict[str, int]:
        """从知识分类导入概念"""
        concepts_map = {}  # name -> id

        async with self.session_maker() as session:
            for category in knowledge:
                category_name = self.CATEGORY_MAPPING.get(category.title, category.title)

                for item in category.items:
                    name = item['name']
                    description = item['description']

                    # 检查是否已存在
                    result = await session.execute(
                        select(Concept).where(Concept.name == name)
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        concepts_map[name] = existing.id
                        # 更新描述和分类
                        existing.description = description
                        existing.category = category_name
                    else:
                        concept = Concept(
                            name=name,
                            description=description,
                            category=category_name,
                            importance=2,  # 知识分类中的概念默认重要度 2
                            mention_count=1,
                        )
                        session.add(concept)
                        await session.flush()
                        concepts_map[name] = concept.id

            await session.commit()

        return concepts_map

    async def import_concepts_from_models(
        self,
        models: list[ThinkingModel],
        existing_map: dict[str, int]
    ) -> dict[str, int]:
        """从思维模型提取并导入概念"""
        new_concepts = {}

        async with self.session_maker() as session:
            for model in models:
                # 提取模型名称（去掉 emoji）
                name = re.sub(r'^[^\u4e00-\u9fff\w]+', '', model.title).strip()

                if not name or name in existing_map or name in new_concepts:
                    continue

                # 从描述中提取第一句作为简短描述
                desc_text = re.sub(r'<[^>]+>', '', model.description)
                desc_text = re.sub(r'\s+', ' ', desc_text).strip()
                short_desc = desc_text[:200] if len(desc_text) > 200 else desc_text

                concept = Concept(
                    name=name,
                    description=short_desc,
                    category="思维模型",
                    importance=3,  # 思维模型重要度更高
                    mention_count=1,
                )
                session.add(concept)
                await session.flush()
                new_concepts[name] = concept.id

            await session.commit()

        return new_concepts

    async def create_concept_relations(
        self,
        knowledge: list[KnowledgeCategory],
        concepts_map: dict[str, int]
    ) -> int:
        """建立概念关系"""
        relations_count = 0

        async with self.session_maker() as session:
            # 同一分类下的概念建立 belongs_to_same_category 关系
            for category in knowledge:
                items = category.items
                for i, item1 in enumerate(items):
                    name1 = item1['name']
                    if name1 not in concepts_map:
                        continue

                    for item2 in items[i + 1:]:
                        name2 = item2['name']
                        if name2 not in concepts_map:
                            continue

                        # 创建双向关系
                        relation = ConceptRelation(
                            source_id=concepts_map[name1],
                            target_id=concepts_map[name2],
                            relation_type="same_category",
                            strength=0.5,
                        )
                        session.add(relation)
                        relations_count += 1

            await session.commit()

        return relations_count

    async def export_to_json(self, data: MigratedData, concepts_map: dict[str, int]):
        """导出数据为 JSON 文件"""
        output_dir = Path(__file__).parent.parent.parent / "data"
        output_dir.mkdir(exist_ok=True)

        # 1. 导出总览数据
        overview_path = output_dir / "overview.json"
        overview_dict = asdict(data.overview)
        overview_path.write_text(json.dumps(overview_dict, ensure_ascii=False, indent=2), encoding="utf-8")

        # 2. 导出时间线
        timeline_path = output_dir / "timeline.json"
        timeline_list = [asdict(item) for item in data.timeline]
        timeline_path.write_text(json.dumps(timeline_list, ensure_ascii=False, indent=2), encoding="utf-8")

        # 3. 导出思维模型
        models_path = output_dir / "models.json"
        models_list = [asdict(model) for model in data.models]
        models_path.write_text(json.dumps(models_list, ensure_ascii=False, indent=2), encoding="utf-8")

        # 4. 导出知识分类
        knowledge_path = output_dir / "knowledge.json"
        knowledge_list = [asdict(cat) for cat in data.knowledge]
        knowledge_path.write_text(json.dumps(knowledge_list, ensure_ascii=False, indent=2), encoding="utf-8")

        # 5. 导出知识图谱数据
        await self.export_graph_json(output_dir, concepts_map)

    async def export_graph_json(self, output_dir: Path, concepts_map: dict[str, int]):
        """导出知识图谱 JSON"""
        graph_data = {"nodes": [], "edges": []}

        async with self.session_maker() as session:
            # 获取所有概念
            result = await session.execute(select(Concept))
            concepts = result.scalars().all()

            for concept in concepts:
                graph_data["nodes"].append({
                    "id": str(concept.id),
                    "label": concept.name,
                    "category": concept.category or "未分类",
                    "description": concept.description,
                    "importance": concept.importance,
                    "size": 20 + concept.importance * 5,
                })

            # 获取所有关系
            result = await session.execute(select(ConceptRelation))
            relations = result.scalars().all()

            for rel in relations:
                graph_data["edges"].append({
                    "source": str(rel.source_id),
                    "target": str(rel.target_id),
                    "type": rel.relation_type,
                    "strength": rel.strength,
                })

        graph_path = output_dir / "graph.json"
        graph_path.write_text(json.dumps(graph_data, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================
# 主函数
# ============================================

async def main():
    """主函数"""
    # 路径配置
    html_path = Path(os.environ.get("LEGACY_READING_HTML", "./user-data/legacy-reading.html"))
    db_path = Path(__file__).parent.parent / "reading_system.db"

    if not html_path.exists():
        print(f"错误: HTML 文件不存在: {html_path}")
        return

    # 1. 解析 HTML
    print("正在解析 HTML...")
    parser = HTMLDataParser(html_path)
    data = parser.parse_all()

    print(f"  - 总览: 读书天数={data.overview.reading_days}, 书籍={data.overview.books_count}")
    print(f"  - 时间线条目: {len(data.timeline)} 个")
    print(f"  - 思维模型: {len(data.models)} 个")
    print(f"  - 知识分类: {len(data.knowledge)} 个")

    # 2. 导入数据库
    importer = DataImporter(str(db_path))
    await importer.init_db()

    # 清空旧数据（可选）
    print("\n清空旧的概念数据...")
    await importer.clear_data()

    # 导入新数据
    await importer.import_all(data)


if __name__ == "__main__":
    asyncio.run(main())
