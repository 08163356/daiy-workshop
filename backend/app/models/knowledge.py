"""知识体系模型 — 替代 knowledge.json / models.json / graph.json / overview.json

设计思路：
- KnowledgeCategory: 知识分类（如 🎲 不确定性科学），对应 knowledge.json 的 top-level
- KnowledgeItem: 知识条目（如 "黑天鹅事件"），对应 knowledge.json 的 items
- KnowledgeGraph: 知识图谱节点和边（合并 graph.json 的 nodes+edges）
- ReadingOverview: 阅读概览统计（对应 overview.json）

核心能力：
1. 种子数据从 JSON 一次性导入
2. AI 分析后增量更新（新增 / 合并 / 重要性递增）
3. 前端 API 直接读取这些表
4. AI 分析时注入已有知识作为上下文
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, Float, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KnowledgeCategory(Base):
    """知识分类表（替代 knowledge.json 的 top-level 分类）"""

    __tablename__ = "knowledge_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # 例如: "🎲 不确定性科学", "🚀 个人效能"
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    item_count: Mapped[int] = mapped_column(Integer, default=0)  # 缓存条目数
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<KnowledgeCategory(id={self.id}, title='{self.title}')>"


class KnowledgeItem(Base):
    """知识条目表（替代 knowledge.json 的 items）"""

    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # 冗余存储分类标题，方便查询
    importance: Mapped[int] = mapped_column(Integer, default=1)  # 1-5
    mention_count: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(50), default="seed")
    # "seed" = JSON导入, "ai" = AI分析新增, "manual" = 手动添加
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<KnowledgeItem(id={self.id}, name='{self.name}', category='{self.category_title}')>"


class KnowledgeGraph(Base):
    """知识图谱表（替代 graph.json 的 nodes + edges）
    
    type='node': 图谱节点
    type='edge': 图谱边
    """

    __tablename__ = "knowledge_graph"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_type: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    # "node" 或 "edge"

    # ---- 节点字段 (entry_type='node') ----
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    importance: Mapped[int] = mapped_column(Integer, default=2)
    node_size: Mapped[int] = mapped_column(Integer, default=30)
    original_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # graph.json 中的原始 id

    # ---- 边字段 (entry_type='edge') ----
    source_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    edge_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    strength: Mapped[float] = mapped_column(Float, default=0.5)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        if self.entry_type == "node":
            return f"<KnowledgeGraph(node, label='{self.label}')>"
        return f"<KnowledgeGraph(edge, {self.source_id}->{self.target_id})>"


class ReadingOverview(Base):
    """阅读概览统计表（替代 overview.json，单行记录）"""

    __tablename__ = "reading_overview"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_days: Mapped[int] = mapped_column(Integer, default=0)
    books_count: Mapped[int] = mapped_column(Integer, default=0)
    concepts_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_comments: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # JSON 格式的进度数据
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<ReadingOverview(books={self.books_count}, days={self.reading_days})>"
