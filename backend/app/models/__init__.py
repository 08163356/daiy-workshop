"""数据模型模块"""

from app.models.note import Note, NoteConcept
from app.models.concept import Concept
from app.models.relation import ConceptRelation
from app.models.thinking_model import ThinkingModel
from app.models.investment import (
    InvestmentReflection,
    InvestmentPrinciple,
    InvestmentCognition,
    InvestmentDecision,
    InvestmentEmotion,
    InvestmentKnowledge,
    InvestmentQA,
)
from app.models.diary import DiaryEntry
from app.models.ai_config import AIConfig, UserProfile, ConversationLog, ProfileDistillRun
from app.models.todo import TodoItem, RecurringTask, InboxHistory, TodoComment
from app.models.time_log import TimeLog
from app.models.knowledge import (
    KnowledgeCategory, KnowledgeItem, KnowledgeGraph, ReadingOverview,
)
from app.models.chat_history import ChatHistory
from app.models.article import Article
from app.models.module_model_config import ModuleModelConfig
from app.models.auth import AuthConfig, AuthToken
from app.models.wellbeing import (
    WellbeingEntry,
    WellbeingCandidate,
    WellbeingReport,
    WellbeingTag,
)
from app.models.basketball import (
    BasketballSession,
    BasketballGoal,
    BasketballSkillSnapshot,
)
from app.models.coaching import CoachingSession
from app.models.time_capsule import TimeCapsuleLetter, TimeCapsuleTemplate
from app.models.weread import WeReadConfig, WeReadBook
from app.models.wishlist import Wish, WishLogEntry, WishProgressCandidate
from app.models.prompt_skill import PromptSkill, SkillCandidate
from app.models.review import ReviewItem

__all__ = [
    "Note",
    "NoteConcept",
    "Concept",
    "ConceptRelation",
    "ThinkingModel",
    "InvestmentReflection",
    "InvestmentPrinciple",
    "InvestmentCognition",
    "InvestmentDecision",
    "InvestmentEmotion",
    "InvestmentKnowledge",
    "InvestmentQA",
    "DiaryEntry",
    "AIConfig",
    "UserProfile",
    "ConversationLog",
    "ProfileDistillRun",
    "TodoItem",
    "RecurringTask",
    "InboxHistory",
    "TodoComment",
    "KnowledgeCategory",
    "KnowledgeItem",
    "KnowledgeGraph",
    "ReadingOverview",
    "ChatHistory",
    "Article",
    "ModuleModelConfig",
    "AuthConfig",
    "AuthToken",
    "WellbeingEntry",
    "WellbeingCandidate",
    "WellbeingReport",
    "WellbeingTag",
    "BasketballSession",
    "BasketballGoal",
    "BasketballSkillSnapshot",
    "CoachingSession",
    "TimeCapsuleLetter",
    "TimeCapsuleTemplate",
    "WeReadConfig",
    "WeReadBook",
    "Wish",
    "WishLogEntry",
    "WishProgressCandidate",
    "PromptSkill",
    "SkillCandidate",
    "ReviewItem",
]
