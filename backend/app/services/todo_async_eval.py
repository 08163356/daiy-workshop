"""Async AI evaluation for todos"""

import logging

logger = logging.getLogger(__name__)


async def async_evaluate_todo(todo_id: int, title: str, description: str | None):
    """Async AI evaluate and update todo quadrant/category."""
    try:
        from sqlalchemy import update
        from app.core.database import async_session_maker
        from app.services.todo_service import evaluate_batch_input
        from app.models.todo import TodoItem

        content = title +('\n' + description if description else '')
        async with async_session_maker() as db:
            result = await evaluate_batch_input(db, content)
            items = result.get("items", [])
            if items:
                ai = items[0]
                # 注意：AI 可能显式返回 null（而非缺省），此时 .get(k, default) 会拿到 None，
                # 写入 quadrant/urgency/importance 这些 NOT NULL 字段会抛 IntegrityError，
                # 导致整次评估失败。这里统一用 `or 默认值` 兜底。
                await db.execute(
                    update(TodoItem).where(TodoItem.id == todo_id).values(
                        quadrant=ai.get("quadrant") or 4,
                        category=ai.get("category"),
                        urgency=ai.get("urgency") or 3,
                        importance=ai.get("importance") or 3,
                        ai_evaluation=ai.get("evaluation") or ai.get("ai_evaluation"),
                    )
                )
                await db.commit()
                logger.info(f"Todo #{todo_id} AI evaluated: Q{ai.get('quadrant')}/{ai.get('category')}")
            else:
                logger.warning(f"Todo #{todo_id} AI returned no items: {result}")
    except Exception as e:
        logger.error(f"Todo #{todo_id} AI evaluate failed: {e}", exc_info=True)
