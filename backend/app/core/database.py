"""数据库连接管理"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


# 创建异步引擎
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

# 创建异步会话工厂
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """ORM 基类"""
    pass


async def get_db() -> AsyncSession:
    """获取数据库会话（依赖注入）"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库表"""
    # 确保所有模型被导入，以便注册到 Base.metadata
    from app.models import (
        Note, NoteConcept, Concept, ConceptRelation, ThinkingModel,
        InvestmentReflection, InvestmentPrinciple, InvestmentCognition,
        InvestmentDecision, InvestmentEmotion, InvestmentKnowledge, InvestmentQA,
        DiaryEntry, AIConfig, UserProfile, ConversationLog,
        TodoItem, RecurringTask, InboxHistory, TodoComment, TimeLog,
        KnowledgeCategory, KnowledgeItem, KnowledgeGraph, ReadingOverview,
        Article, ModuleModelConfig,
    )
    from app.models.auth import AuthConfig, AuthToken, LockSettings
    from app.models.wellbeing import (
        WellbeingEntry, WellbeingCandidate, WellbeingReport, WellbeingTag,
    )
    from app.models.basketball import (
        BasketballSession, BasketballGoal, BasketballSkillSnapshot,
    )
    from app.models.time_capsule import TimeCapsuleLetter, TimeCapsuleTemplate
    from app.models.wishlist import Wish, WishLogEntry, WishProgressCandidate
    from app.models.ai_config import ProfileDistillRun
    from app.models.ai_question import AIQuestion
    from app.models.agent import AgentSession, AgentEvent
    from app.models.prompt_skill import PromptSkill, SkillCandidate
    from app.models.profile_admin import ProfileSnapshot, ProfileProposal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 安全添加新列（SQLite 的 create_all 不会自动添加已有表的新列）
    import logging
    logger = logging.getLogger(__name__)
    alter_statements = [
        ("todo_items", "ai_answer", "TEXT"),
        ("todo_items", "original_text", "TEXT"),
        ("todo_items", "scheduled_date", "DATE"),
        ("todo_items", "estimated_minutes", "INTEGER"),
        ("todo_items", "actual_minutes", "INTEGER"),
        ("todo_items", "completion_note", "TEXT"),
        ("todo_items", "completion_notes", "TEXT"),
        ("todo_items", "sort_order", "INTEGER DEFAULT 0"),
        ("todo_items", "scheduled_end_date", "DATE"),
        ("todo_items", "core_scope", "VARCHAR(10)"),
        ("todo_items", "core_period_key", "VARCHAR(10)"),
        ("time_logs", "activity_type", "VARCHAR(20) DEFAULT 'task'"),
        ("time_logs", "status_label", "VARCHAR(50)"),
        ("time_logs", "status_emoji", "VARCHAR(10)"),
        ("diary_entries", "images", "JSON"),
  ("notes", "images", "JSON"),
  ("wellbeing_entries", "source_excerpt", "TEXT"),
        ("recurring_tasks", "auto_event", "VARCHAR(20)"),
        ("recurring_tasks", "auto_keywords", "VARCHAR(500)"),
        ("recurring_tasks", "last_checkin_auto", "BOOLEAN DEFAULT 0"),
        ("agent_sessions", "mode", "VARCHAR(20) DEFAULT 'normal'"),
        ("agent_sessions", "summary", "TEXT"),
        ("agent_sessions", "insights", "JSON"),
        ("agent_sessions", "followups", "JSON"),
        ("agent_sessions", "origin_type", "VARCHAR(20)"),
        ("agent_sessions", "origin_id", "INTEGER"),
        ("agent_sessions", "origin_extra", "JSON"),
        ("notes", "source_type", "VARCHAR(20) DEFAULT 'book'"),
        ("notes", "course_meta", "JSON"),
        ("todo_comments", "kind", "VARCHAR(20) DEFAULT 'idea'"),
    ]
    import sqlalchemy
    async with engine.begin() as conn:
        for table, column, col_type in alter_statements:
            try:
                # 先检查列是否已存在
                result = await conn.execute(
                    sqlalchemy.text(f"PRAGMA table_info({table})")
                )
                existing_columns = [row[1] for row in result.fetchall()]
                if column in existing_columns:
                    continue  # 列已存在，跳过

                await conn.execute(
                    sqlalchemy.text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                    )
                )
                logger.info(f"Added column {table}.{column} ({col_type})")
            except Exception as e:
                logger.warning(f"Failed to add column {table}.{column}: {e}")

        # 修复 time_logs.todo_id NOT NULL 约束（状态记录时 todo_id 应为 NULL）
        try:
            result = await conn.execute(
                sqlalchemy.text("PRAGMA table_info(time_logs)")
            )
            columns = {row[1]: row for row in result.fetchall()}
            if "todo_id" in columns and columns["todo_id"][3] == 1:  # notnull=1
                logger.info("Fixing time_logs.todo_id: changing NOT NULL to nullable")
                await conn.execute(sqlalchemy.text(
                    "CREATE TABLE time_logs_new ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "todo_id INTEGER, "
                    "start_time DATETIME NOT NULL, "
                    "end_time DATETIME, "
                    "duration_seconds INTEGER, "
                    "category VARCHAR(50), "
                    "created_at DATETIME NOT NULL, "
                    "activity_type VARCHAR(20) DEFAULT 'task', "
                    "status_label VARCHAR(50), "
                    "status_emoji VARCHAR(10))"
                ))
                await conn.execute(sqlalchemy.text(
                    "INSERT INTO time_logs_new SELECT * FROM time_logs"
                ))
                await conn.execute(sqlalchemy.text("DROP TABLE time_logs"))
                await conn.execute(sqlalchemy.text(
                    "ALTER TABLE time_logs_new RENAME TO time_logs"
                ))
                await conn.execute(sqlalchemy.text(
                    "CREATE INDEX ix_time_logs_todo_id ON time_logs (todo_id)"
                ))
                await conn.execute(sqlalchemy.text(
                    "CREATE INDEX ix_time_logs_category ON time_logs (category)"
                ))
                logger.info("time_logs.todo_id NOT NULL constraint removed successfully")
        except Exception as e:
            logger.warning(f"Failed to fix time_logs.todo_id: {e}")

    # 启动时补齐内置 prompt skill（不覆盖用户已修改的）
    try:
        from app.services.skill_service import seed_builtin_skills
        async with async_session_maker() as session:
            async with session.begin():
                await seed_builtin_skills(session)
    except Exception as e:
        logger.warning(f"Seed 内置 skill 失败: {e}")


async def close_db() -> None:
    """关闭数据库连接"""
    await engine.dispose()
