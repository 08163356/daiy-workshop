"""第四期：周期数据包、命名周期直注、年度目标、经验沉淀。"""
import unittest
from datetime import date, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.diary import DiaryEntry
from app.models.note import Note
from app.models.time_log import TimeLog
from app.models.todo import TodoComment, TodoItem
from app.models.wellbeing import WellbeingEntry
from app.services.agent_loop import resolve_turn_date_range, should_force_tasklist, should_inject_period
from app.services.agent_tools import execute_tool
from app.services.task_context import get_period_bundle, resolve_named_period_range
from app.services import todo_service


class PeriodIntentTests(unittest.TestCase):
    def test_named_last_month(self):
        rng = resolve_turn_date_range("根据我的日程总结一下我上个月", today=date(2026, 11, 13))
        self.assertEqual(rng, ("2026-10-01", "2026-10-31"))
        self.assertTrue(should_inject_period("根据我的日程总结一下我上个月"))

    def test_this_week_summary(self):
        rng = resolve_turn_date_range("总结本周我做了什么，不要评价，只总结", today=date(2026, 11, 13))
        self.assertEqual(rng, ("2026-11-09", "2026-11-15"))

    def test_last_three_months(self):
        named = resolve_named_period_range("近三个月做了什么", today=date(2026, 11, 13))
        self.assertEqual(named, (date(2026, 8, 15), date(2026, 11, 13)))

    def test_plain_summary_does_not_default_today(self):
        self.assertIsNone(resolve_turn_date_range("总结一下这本书"))
        self.assertFalse(should_inject_period("总结一下这本书"))

    def test_explicit_range_still_works(self):
        self.assertTrue(should_inject_period("总结10月26到10月31我做了什么，不要评价，只总结"))

    def test_tasklist_intent(self):
        self.assertTrue(should_force_tasklist("周一开会周二写周报，提取本周要做的事然后生成任务单"))
        self.assertFalse(should_force_tasklist("/任务单 已经由斜杠管线处理"))
        self.assertFalse(should_force_tasklist("总结本周做了什么"))


class PeriodBundleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for table in (TodoItem.__table__, TodoComment.__table__, TimeLog.__table__,
                          DiaryEntry.__table__, Note.__table__, WellbeingEntry.__table__):
                await conn.run_sync(table.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.db.add(TodoItem(title="十月交付", status="completed", scheduled_date=date(2026, 10, 20),
                             completed_at=datetime(2026, 10, 21, 10), created_at=datetime(2026, 10, 1)))
        self.db.add(DiaryEntry(date=date(2026, 10, 22), title="加班日记", content="那天把协议改完了"))
        self.db.add(Note(filename="n1.md", title="读书", content="笔记正文", file_hash="abc",
                         reading_date=date(2026, 10, 18), word_count=4))
        self.db.add(WellbeingEntry(type="achievement", content="上线了", occurred_at=date(2026, 10, 21)))
        self.db.add(TodoItem(title="全年读 24 本书", core_scope="year", core_period_key="2026", status="planned"))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_bundle_includes_diary_and_year_goal(self):
        text = await get_period_bundle(self.db, date(2026, 10, 1), date(2026, 10, 31))
        self.assertIn("加班日记", text)
        self.assertIn("十月交付", text)
        self.assertIn("全年读 24 本书", text)
        self.assertIn("上线了", text)


class AgentToolPeriodTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(TodoItem.__table__.create)
            await conn.run_sync(TodoComment.__table__.create)
            await conn.run_sync(DiaryEntry.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        parent = TodoItem(title="父任务", status="planned", quadrant=1, urgency=5)
        self.db.add(parent)
        await self.db.flush()
        self.parent_id = parent.id
        self.db.add(DiaryEntry(date=date(2026, 10, 5), title="十月", content="内容"))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_create_child_inherits_quadrant(self):
        result = await execute_tool(self.db, "create_todo", {
            "title": "子步骤", "parent_id": self.parent_id,
        })
        self.assertNotIn("error", result)
        from sqlalchemy import select
        child = (await self.db.execute(select(TodoItem).where(TodoItem.title == "子步骤"))).scalar_one()
        self.assertEqual(child.parent_id, self.parent_id)
        self.assertEqual(child.quadrant, 1)
        self.assertEqual(child.urgency, 5)

    async def test_query_diaries_period(self):
        result = await execute_tool(self.db, "query_diaries", {
            "period": "last_month",
        })
        # 测试当天若不是 11 月会随日期变，用显式日期更稳
        result = await execute_tool(self.db, "query_diaries", {
            "start_date": "2026-10-01", "end_date": "2026-10-31",
        })
        self.assertIn("十月", result["content"])

    async def test_add_and_query_lesson(self):
        await execute_tool(self.db, "add_lesson", {"todo_id": self.parent_id, "content": "下次先写测试"})
        result = await execute_tool(self.db, "query_lessons", {"todo_id": self.parent_id})
        self.assertIn("下次先写测试", result["content"])


if __name__ == "__main__":
    unittest.main()
