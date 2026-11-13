"""Pydantic 数据模式"""

from app.schemas.note import NoteCreate, NoteUpdate, NoteResponse, NoteListResponse
from app.schemas.concept import ConceptCreate, ConceptUpdate, ConceptResponse, ConceptListResponse
from app.schemas.graph import GraphNode, GraphEdge, GraphResponse
from app.schemas.investment import (
    ReflectionCreate, ReflectionResponse, ReflectionListItem,
    PrincipleCreate, PrincipleUpdate, PrincipleResponse, PrincipleListItem,
    CognitionCreate, CognitionResponse,
    DecisionCreate, DecisionUpdate, DecisionResponse,
    EmotionCreate, EmotionResponse,
    KnowledgeCreate, KnowledgeResponse,
    QACreate, QAUpdate, QAResponse, QAListItem,
    InvestmentOverview, ListResponse,
)

__all__ = [
    # 读书模块
    "NoteCreate",
    "NoteUpdate",
    "NoteResponse",
    "NoteListResponse",
    "ConceptCreate",
    "ConceptUpdate",
    "ConceptResponse",
    "ConceptListResponse",
    "GraphNode",
    "GraphEdge",
    "GraphResponse",
    # 投资模块
    "ReflectionCreate",
    "ReflectionResponse",
    "ReflectionListItem",
    "PrincipleCreate",
    "PrincipleUpdate",
    "PrincipleResponse",
    "PrincipleListItem",
    "CognitionCreate",
    "CognitionResponse",
    "DecisionCreate",
    "DecisionUpdate",
    "DecisionResponse",
    "EmotionCreate",
    "EmotionResponse",
    "KnowledgeCreate",
    "KnowledgeResponse",
    "QACreate",
    "QAUpdate",
    "QAResponse",
    "QAListItem",
    "InvestmentOverview",
    "ListResponse",
]
