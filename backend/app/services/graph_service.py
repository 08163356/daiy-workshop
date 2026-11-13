"""知识图谱服务"""

import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Concept, ConceptRelation
from app.schemas.graph import GraphNode, GraphEdge, GraphResponse, GraphFilterParams

logger = logging.getLogger(__name__)


class GraphService:
    """知识图谱服务"""

    # 节点大小基数
    BASE_SIZE = 15
    SIZE_MULTIPLIER = 5

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_graph(
        self, params: Optional[GraphFilterParams] = None
    ) -> GraphResponse:
        """获取知识图谱数据"""
        params = params or GraphFilterParams()

        # 构建查询条件
        query = select(Concept)

        if params.category:
            query = query.where(Concept.category == params.category)

        if params.min_importance > 1:
            query = query.where(Concept.importance >= params.min_importance)

        if params.min_mention_count > 0:
            query = query.where(Concept.mention_count >= params.min_mention_count)

        # 按重要程度和提及次数排序
        query = query.order_by(
            Concept.importance.desc(),
            Concept.mention_count.desc(),
        ).limit(params.limit)

        concepts = await self.db.scalars(query)
        concept_list = list(concepts)

        # 构建节点
        nodes: list[GraphNode] = []
        concept_ids: set[int] = set()

        for concept in concept_list:
            concept_ids.add(concept.id)
            node = GraphNode(
                id=str(concept.id),
                label=concept.name,
                category=concept.category,
                size=self._calculate_size(concept.importance, concept.mention_count),
                importance=concept.importance,
                mention_count=concept.mention_count,
            )
            nodes.append(node)

        # 获取这些概念之间的关系
        edges: list[GraphEdge] = []

        if concept_ids:
            relations_query = select(ConceptRelation).where(
                ConceptRelation.source_id.in_(concept_ids),
                ConceptRelation.target_id.in_(concept_ids),
            )
            relations = await self.db.scalars(relations_query)

            for rel in relations:
                edge = GraphEdge(
                    source=str(rel.source_id),
                    target=str(rel.target_id),
                    type=rel.relation_type,
                    strength=rel.strength,
                )
                edges.append(edge)

        return GraphResponse(
            nodes=nodes,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
        )

    async def get_concept_neighbors(
        self, concept_id: int, depth: int = 1
    ) -> GraphResponse:
        """获取概念的邻居节点"""
        visited_ids: set[int] = {concept_id}
        current_ids: set[int] = {concept_id}

        # BFS 遍历
        for _ in range(depth):
            # 获取当前节点的邻居
            relations = await self.db.scalars(
                select(ConceptRelation).where(
                    (ConceptRelation.source_id.in_(current_ids))
                    | (ConceptRelation.target_id.in_(current_ids))
                )
            )

            next_ids: set[int] = set()
            for rel in relations:
                if rel.source_id not in visited_ids:
                    next_ids.add(rel.source_id)
                if rel.target_id not in visited_ids:
                    next_ids.add(rel.target_id)

            visited_ids.update(next_ids)
            current_ids = next_ids

            if not next_ids:
                break

        # 获取所有访问过的概念
        concepts = await self.db.scalars(
            select(Concept).where(Concept.id.in_(visited_ids))
        )

        nodes: list[GraphNode] = []
        for concept in concepts:
            node = GraphNode(
                id=str(concept.id),
                label=concept.name,
                category=concept.category,
                size=self._calculate_size(concept.importance, concept.mention_count),
                importance=concept.importance,
                mention_count=concept.mention_count,
            )
            nodes.append(node)

        # 获取这些概念之间的关系
        relations = await self.db.scalars(
            select(ConceptRelation).where(
                ConceptRelation.source_id.in_(visited_ids),
                ConceptRelation.target_id.in_(visited_ids),
            )
        )

        edges: list[GraphEdge] = []
        for rel in relations:
            edge = GraphEdge(
                source=str(rel.source_id),
                target=str(rel.target_id),
                type=rel.relation_type,
                strength=rel.strength,
            )
            edges.append(edge)

        return GraphResponse(
            nodes=nodes,
            edges=edges,
            node_count=len(nodes),
            edge_count=len(edges),
        )

    async def get_categories(self) -> list[dict]:
        """获取所有概念分类"""
        from sqlalchemy import func

        query = (
            select(Concept.category, func.count(Concept.id).label("count"))
            .where(Concept.category.isnot(None))
            .group_by(Concept.category)
            .order_by(func.count(Concept.id).desc())
        )

        result = await self.db.execute(query)
        return [{"category": row.category, "count": row.count} for row in result]

    def _calculate_size(self, importance: int, mention_count: int) -> int:
        """计算节点大小"""
        return self.BASE_SIZE + (importance * self.SIZE_MULTIPLIER) + (mention_count * 2)
