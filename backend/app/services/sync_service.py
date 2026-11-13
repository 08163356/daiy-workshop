"""MD 文件同步服务"""

import logging
from pathlib import Path
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Note, Concept, NoteConcept, ConceptRelation
from app.parsers import MarkdownParser, ConceptExtractor

logger = logging.getLogger(__name__)


class SyncService:
    """MD 文件同步服务"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.md_parser = MarkdownParser()
        self.concept_extractor = ConceptExtractor()

    async def sync_all(self, markdown_dir: Optional[Path] = None) -> dict:
        """同步所有 MD 文件"""
        md_dir = markdown_dir or settings.markdown_dir

        if not md_dir.exists():
            raise FileNotFoundError(f"Markdown 目录不存在: {md_dir}")

        # 获取所有 MD 文件
        md_files = list(md_dir.glob("*.md"))
        logger.info(f"发现 {len(md_files)} 个 MD 文件")

        stats = {
            "total_files": len(md_files),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "concepts_created": 0,
            "relations_created": 0,
        }

        for file_path in md_files:
            try:
                result = await self._sync_file(file_path)
                stats[result] += 1
            except Exception as e:
                logger.error(f"同步文件失败 {file_path}: {e}")
                stats["errors"] += 1

        # 更新概念统计
        await self._update_concept_stats()

        # 统计最终数据
        from sqlalchemy import func
        concept_count = await self.db.scalar(select(func.count(Concept.id)))
        relation_count = await self.db.scalar(select(func.count(ConceptRelation.id)))
        stats["total_concepts"] = concept_count or 0
        stats["total_relations"] = relation_count or 0

        logger.info(f"同步完成: {stats}")
        return stats

    async def _sync_file(self, file_path: Path) -> str:
        """同步单个文件"""
        # 解析 MD 文件
        parsed = self.md_parser.parse_file(file_path)

        # 检查是否已存在
        existing = await self.db.scalar(
            select(Note).where(Note.filename == parsed.filename)
        )

        if existing:
            # 检查是否有变化
            if existing.file_hash == parsed.file_hash:
                return "skipped"

            # 更新笔记
            existing.title = parsed.title
            existing.content = parsed.content
            existing.summary = parsed.summary
            existing.reading_date = parsed.reading_date
            existing.word_count = parsed.word_count
            existing.file_hash = parsed.file_hash

            # 删除旧的概念关联
            await self.db.execute(
                delete(NoteConcept).where(NoteConcept.note_id == existing.id)
            )

            note = existing
            result = "updated"
        else:
            # 创建新笔记
            note = Note(
                filename=parsed.filename,
                title=parsed.title,
                content=parsed.content,
                summary=parsed.summary,
                reading_date=parsed.reading_date,
                word_count=parsed.word_count,
                file_hash=parsed.file_hash,
            )
            self.db.add(note)
            await self.db.flush()  # 获取 ID
            result = "created"

        # 提取并关联概念
        await self._extract_and_link_concepts(note, parsed.content)

        return result

    async def _extract_and_link_concepts(self, note: Note, content: str) -> None:
        """提取概念并建立关联"""
        extraction = self.concept_extractor.extract(content)

        concept_ids: list[int] = []

        for extracted in extraction.concepts:
            # 查找或创建概念
            concept = await self.db.scalar(
                select(Concept).where(Concept.name == extracted.name)
            )

            if not concept:
                concept = Concept(
                    name=extracted.name,
                    category=extracted.category,
                    importance=1,
                    mention_count=1,
                )
                self.db.add(concept)
                await self.db.flush()
            else:
                concept.mention_count += 1

            concept_ids.append(concept.id)

            # 创建笔记-概念关联
            note_concept = NoteConcept(
                note_id=note.id,
                concept_id=concept.id,
                context=extracted.context,
            )
            self.db.add(note_concept)

        # 创建概念关系
        for source_name, target_name, rel_type, strength in extraction.relations:
            source = await self.db.scalar(
                select(Concept).where(Concept.name == source_name)
            )
            target = await self.db.scalar(
                select(Concept).where(Concept.name == target_name)
            )

            if source and target:
                # 检查关系是否存在
                existing_rel = await self.db.scalar(
                    select(ConceptRelation).where(
                        ConceptRelation.source_id == source.id,
                        ConceptRelation.target_id == target.id,
                        ConceptRelation.relation_type == rel_type,
                    )
                )

                if existing_rel:
                    # 增强关系强度
                    existing_rel.strength = min(1.0, existing_rel.strength + strength * 0.1)
                else:
                    relation = ConceptRelation(
                        source_id=source.id,
                        target_id=target.id,
                        relation_type=rel_type,
                        strength=strength,
                    )
                    self.db.add(relation)

    async def _update_concept_stats(self) -> None:
        """更新概念统计信息"""
        # 更新重要程度（基于提及次数）
        concepts = await self.db.scalars(select(Concept))
        for concept in concepts:
            # 根据提及次数计算重要程度
            if concept.mention_count >= 5:
                concept.importance = 5
            elif concept.mention_count >= 3:
                concept.importance = 4
            elif concept.mention_count >= 2:
                concept.importance = 3
            else:
                concept.importance = 1

    async def clear_all(self) -> dict:
        """清空所有数据"""
        await self.db.execute(delete(NoteConcept))
        await self.db.execute(delete(ConceptRelation))
        await self.db.execute(delete(Note))
        await self.db.execute(delete(Concept))

        return {"message": "已清空所有数据"}
