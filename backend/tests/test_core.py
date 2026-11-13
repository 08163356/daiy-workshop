"""核心任务（本周/本月核心）测试

功能契约：
- 任务可标记为本周核心或本月核心，各最多 3 条，分开计算
- 标记时记录周期 key（ISO 周 '2026-W42' / 月 '2026-10'），查询按当前周期过滤，过期自动失效
- 子任务不能设为核心
- 对齐检查 core_review 用 AI 对照本期实际记录产出 Markdown 分析（禁用思维链）
"""
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.ai_config import AIConfig, UserProfile
from app.models.time_log import TimeLog
from app.models.todo import TodoComment, TodoItem
from app.services import todo_service


class CoreTaskTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            # get_task_context 联查 time_logs / todo_comments；画像查询读 user_profiles
            await conn.run_sync(TodoItem.__table__.create)
            await conn.run_sync(TimeLog.__table__.create)
            await conn.run_sync(TodoComment.__table__.create)
            await conn.run_sync(UserProfile.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        # 固定"今天"为 2026-10-19（周一，ISO 2026-W43）
        self.today = date(2026, 10, 19)
        for title in ["任务A", "任务B", "任务C", "任务D"]:
            self.db.add(TodoItem(title=title, status="planned"))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _id_of(self, title: str) -> int:
        from sqlalchemy import select
        result = await self.db.execute(select(TodoItem).where(TodoItem.title == title))
        return result.scalar_one().id

    async def test_set_core_week_marks_current_period(self):
        todo_id = await self._id_of("任务A")
        item = await todo_service.set_core(self.db, todo_id, "week", today=self.today)
        self.assertEqual(item.core_scope, "week")
        self.assertEqual(item.core_period_key, "2026-W43")

    async def test_set_core_month_marks_current_month(self):
        todo_id = await self._id_of("任务A")
        item = await todo_service.set_core(self.db, todo_id, "month", today=self.today)
        self.assertEqual(item.core_scope, "month")
        self.assertEqual(item.core_period_key, "2026-10")

    async def test_set_core_limit_three_per_scope(self):
        for t in ["任务A", "任务B", "任务C"]:
            await todo_service.set_core(self.db, await self._id_of(t), "week", today=self.today)
        with self.assertRaises(ValueError):
            await todo_service.set_core(self.db, await self._id_of("任务D"), "week", today=self.today)

    async def test_week_and_month_quota_are_separate(self):
        # 本周满 3 条后，本月核心仍可标记
        for t in ["任务A", "任务B", "任务C"]:
            await todo_service.set_core(self.db, await self._id_of(t), "week", today=self.today)
        item = await todo_service.set_core(self.db, await self._id_of("任务D"), "month", today=self.today)
        self.assertEqual(item.core_scope, "month")

    async def test_unmark_core_clears_fields(self):
        todo_id = await self._id_of("任务A")
        await todo_service.set_core(self.db, todo_id, "week", today=self.today)
        item = await todo_service.set_core(self.db, todo_id, None, today=self.today)
        self.assertIsNone(item.core_scope)
        self.assertIsNone(item.core_period_key)

    async def test_remark_same_task_does_not_consume_quota(self):
        # 同一任务重复标记本周核心不占用额外名额
        todo_id = await self._id_of("任务A")
        await todo_service.set_core(self.db, todo_id, "week", today=self.today)
        await todo_service.set_core(self.db, todo_id, "week", today=self.today)
        core = await todo_service.get_current_core(self.db, today=self.today)
        self.assertEqual(len(core["week"]), 1)

    async def test_set_core_rejects_child_task(self):
        parent_id = await self._id_of("任务A")
        child = TodoItem(title="子任务", status="planned", parent_id=parent_id)
        self.db.add(child)
        await self.db.commit()
        with self.assertRaises(ValueError):
            await todo_service.set_core(self.db, child.id, "week", today=self.today)

    async def test_get_current_core_expires_old_periods(self):
        # 上周（2026-W42）的核心任务本周不再出现
        todo_id = await self._id_of("任务A")
        await todo_service.set_core(self.db, todo_id, "week", today=date(2026, 10, 12))
        core = await todo_service.get_current_core(self.db, today=self.today)
        self.assertEqual(len(core["week"]), 0)
        self.assertEqual(len(core["month"]), 0)

    async def test_get_current_core_splits_week_and_month(self):
        await todo_service.set_core(self.db, await self._id_of("任务A"), "week", today=self.today)
        await todo_service.set_core(self.db, await self._id_of("任务B"), "month", today=self.today)
        core = await todo_service.get_current_core(self.db, today=self.today)
        self.assertEqual([t.title for t in core["week"]], ["任务A"])
        self.assertEqual([t.title for t in core["month"]], ["任务B"])
        self.assertEqual(core["year"], [])

    async def test_set_core_year(self):
        item = await todo_service.set_core(self.db, await self._id_of("任务A"), "year", today=self.today)
        self.assertEqual(item.core_scope, "year")
        self.assertEqual(item.core_period_key, "2026")
        core = await todo_service.get_current_core(self.db, today=self.today)
        self.assertEqual([t.title for t in core["year"]], ["任务A"])

    async def test_core_review_calls_ai_and_returns_markdown(self):
        await todo_service.set_core(self.db, await self._id_of("任务A"), "week", today=self.today)
        config = AIConfig(provider="deepseek", model="deepseek-v4-pro", api_key="k", temperature=0.7, max_tokens=8192)
        response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": "## 对齐分析\n本周核心推进良好"}}], "usage": {"total_tokens": 100}},
            request=httpx.Request("POST", "https://example.test"),
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=response)
        with patch.object(todo_service, "get_active_ai_config", AsyncMock(return_value=config)), \
             patch("httpx.AsyncClient", return_value=client):
            result = await todo_service.core_review(self.db, "week", today=self.today)
        self.assertIn("对齐分析", result["analysis"])
        self.assertEqual(result["scope"], "week")
        self.assertEqual(result["core_titles"], ["任务A"])
        # 大上下文调用必须禁用思维链，避免正文为空
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload.get("thinking"), {"type": "disabled"})

    async def test_core_review_without_core_raises(self):
        with self.assertRaises(ValueError):
            await todo_service.core_review(self.db, "week", today=self.today)


if __name__ == "__main__":
    unittest.main()
