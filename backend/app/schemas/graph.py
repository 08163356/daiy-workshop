"""知识图谱相关的 Pydantic 模式"""

from typing import Optional
from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """图谱节点"""

    id: str = Field(..., description="节点 ID")
    label: str = Field(..., description="节点标签")
    category: Optional[str] = Field(None, description="分类")
    size: int = Field(20, description="节点大小（基于重要程度和提及次数）")
    importance: int = Field(1, description="重要程度")
    mention_count: int = Field(0, description="提及次数")


class GraphEdge(BaseModel):
    """图谱边"""

    source: str = Field(..., description="源节点 ID")
    target: str = Field(..., description="目标节点 ID")
    type: str = Field("co_occurs", description="关系类型")
    strength: float = Field(1.0, ge=0, le=1, description="关系强度")


class GraphResponse(BaseModel):
    """知识图谱响应"""

    nodes: list[GraphNode] = Field(default_factory=list, description="节点列表")
    edges: list[GraphEdge] = Field(default_factory=list, description="边列表")
    node_count: int = Field(0, description="节点总数")
    edge_count: int = Field(0, description="边总数")


class GraphFilterParams(BaseModel):
    """图谱过滤参数"""

    category: Optional[str] = Field(None, description="按分类过滤")
    min_importance: int = Field(1, ge=1, le=5, description="最小重要程度")
    min_mention_count: int = Field(0, ge=0, description="最小提及次数")
    limit: int = Field(100, ge=1, le=500, description="最大节点数")
