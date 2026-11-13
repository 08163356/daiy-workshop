"""第 15 批需求后端测试：日期范围解析、命名周期、任务单、核心任务按日期、评论二次编辑"""
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.ai_config import AIConfig
from app.models.todo import TodoItem


class DateRangeParseTests(unittest.TestCase):
    def test_chinese_range(self):
        from app.services.agent_loop import _parse_explicit_date_range
        self.assertEqual(
            _parse_explicit_date_range("总结10月26到10月31我做了什么，不要评价，只总结"),
            ("2026-10-26", "2026-10-31"),
        )

    def test_same_month_short(self):
        from app.services.agent_loop import _parse_explicit_date_range
        self.assertEqual(
            _parse_explicit_date_range("10月26到31的记录"), ("2026-10-26", "2026-10-31")
        )

    def test_full_iso_range(self):
        from app.services.agent_loop import _parse_explicit_date_range
        self.assertEqual(
            _parse_explicit_date_range("2026-10-26~2026-11-02 总结"),
            ("2026-10-26", "2026-11-02"),
        )

    def test_no_range(self):
        from app.services.agent_loop import _parse_explicit_date_range
        self.assertIsNone(_parse_explicit_date_range("今天做了什么"))


class PeriodResolveTests(unittest.TestCase):
    def test_named_periods(self):
        from app.services.agent_tools import _resolve_period
        for p in ("today", "this_week", "last_week", "this_month", "last_month",
                  "last_three_months", "last_7_days", "last_30_days", "yesterday"):
            s, e = _resolve_period(p, None, None)
            date.fromisoformat(s)
            date.fromisoformat(e)
            self.assertLessEqual(s, e)

    def test_explicit_dates_win(self):
        from app.services.agent_tools import _resolve_period
        self.assertEqual(
            _resolve_period("this_month", "2026-01-01", "2026-01-31"),
            ("2026-01-01", "2026-01-31"),
        )

    def test_unknown_raises(self):
        from app.services.agent_tools import _resolve_period
        with self.assertRaises(ValueError):
            _resolve_period("whatever", None, None)


class TasklistTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(TodoItem.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_split_normalizes(self):
        from app.services.tasklist_service import split_tasklist
        import httpx
        resp = httpx.Response(200, json={"choices": [{"message": {"content": '{"groups": [{"parent": "整理书房", "quadrant": 9, "children": ["擦桌子", "  "]}]}'}}], "usage": {}},
                              request=httpx.Request("POST", "https://example.test"))
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=resp)
        config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)
        with patch("app.services.tasklist_service.httpx.AsyncClient", return_value=client), \
             patch("app.services.tasklist_service.get_active_ai_config", AsyncMock(return_value=config)):
            groups = await split_tasklist(self.db, "整理书房：擦桌子、收书")
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["quadrant"], 2)  # 非法象限回退默认
        self.assertEqual(len(groups[0]["children"]), 1)  # 空子任务被过滤

    async def test_create_parent_children(self):
        from app.services.tasklist_service import create_tasklist
        result = await create_tasklist(self.db, 7, [{
            "parent": "整理书房", "description": "周末", "quadrant": 2, "category": "life",
            "children": [{"title": "擦桌子"}, {"title": "收书"}],
        }])
        self.assertEqual(result["parents"], 1)
        self.assertEqual(result["children"], 2)
        parent = (await self.db.execute(select(TodoItem).where(TodoItem.parent_id.is_(None)))).scalar_one()
        self.assertEqual(parent.source, "agent_tasklist")
        self.assertEqual(parent.source_id, 7)
        self.assertEqual(parent.status, "planned")
        children = (await self.db.execute(select(TodoItem).where(TodoItem.parent_id == parent.id))).scalars().all()
        self.assertEqual(len(children), 2)


class CoreByDateTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(TodoItem.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.db.add(TodoItem(title="10月核心", quadrant=2, core_scope="month", core_period_key="2026-10"))
        self.db.add(TodoItem(title="11月核心", quadrant=2, core_scope="month", core_period_key="2026-11"))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_get_current_core_respects_date(self):
        from app.services.todo_service import get_current_core
        oct_core = await get_current_core(self.db, date(2026, 10, 15))
        self.assertEqual([t.title for t in oct_core["month"]], ["10月核心"])
        nov_core = await get_current_core(self.db, date(2026, 11, 5))
        self.assertEqual([t.title for t in nov_core["month"]], ["11月核心"])


if __name__ == "__main__":
    unittest.main()
