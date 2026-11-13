"""习惯自动打卡逻辑测试

覆盖：
- 关键词命中（中文逗号/顿号分隔、大小写不敏感）
- 事件触发（diary/basketball）
- 当天已打卡跳过（不重复打）
- 撤销打卡回滚 streak/total
"""
import unittest
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.todo import RecurringTask
from app.services.todo_service import (
    auto_checkin_habits, check_in_habit, undo_check_in, _split_keywords,
)


class HabitAutoCheckinTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(RecurringTask.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()

        def habit(title, **kw):
            h = RecurringTask(
                title=title,
                frequency=kw.pop("frequency", "daily"),
                next_due=date.today(),
                **kw,
            )
            self.db.add(h)
            return h

        habit("写日记", auto_event="diary")
        habit("洗澡", auto_keywords="洗澡,冲凉")
        habit("爬山", auto_keywords="爬山、徒步、登山")
        habit("打篮球", auto_event="basketball", auto_keywords="篮球")
        habit("无自动规则")
        habit("已打卡的习惯", auto_keywords="跑步", last_checked_at=datetime.now(), streak=3, total_completed=10)
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_keyword_match(self):
        """日记正文提到'冲凉' → 洗澡习惯自动打卡"""
        checked = await auto_checkin_habits(self.db, text="今天加班到很晚，回家冲凉后睡了")
        titles = [h.title for h in checked]
        self.assertEqual(titles, ["洗澡"])

    async def test_event_match(self):
        """写日记事件 → 写日记习惯打卡；正文中的'篮球'也命中关键词"""
        checked = await auto_checkin_habits(self.db, text="今天打了场篮球", event="diary")
        self.assertCountEqual([h.title for h in checked], ["打篮球", "写日记"])

    async def test_basketball_event(self):
        """篮球复盘事件 → 打篮球习惯（event 和关键词都命中也只打一次）"""
        checked = await auto_checkin_habits(self.db, text="周末篮球复盘", event="basketball")
        titles = [h.title for h in checked]
        self.assertEqual(titles, ["打篮球"])
        # auto 标记
        self.assertTrue(checked[0].last_checkin_auto)

    async def test_already_checked_skipped(self):
        """当天已打卡的习惯不重复打"""
        checked = await auto_checkin_habits(self.db, text="今天去跑步了")
        self.assertEqual(checked, [])

    async def test_no_rule_no_match(self):
        """无自动规则的习惯永不自动打卡"""
        checked = await auto_checkin_habits(self.db, text="无自动规则", event="diary")
        titles = [h.title for h in checked]
        self.assertNotIn("无自动规则", titles)

    async def test_undo_checkin(self):
        """撤销打卡回滚计数"""
        h = await check_in_habit(self.db, 2, auto=True)  # 洗澡
        self.assertEqual(h.total_completed, 1)
        self.assertEqual(h.streak, 1)

        undone = await undo_check_in(self.db, 2)
        self.assertEqual(undone.total_completed, 0)
        self.assertEqual(undone.streak, 0)
        self.assertIsNone(undone.last_checked_at)
        self.assertFalse(undone.last_checkin_auto)
        self.assertEqual(undone.next_due, date.today())

        # 撤销后可重新打卡
        h2 = await check_in_habit(self.db, 2)
        self.assertEqual(h2.total_completed, 1)

    async def test_undo_not_checked_raises(self):
        """未打卡的习惯撤销报错"""
        with self.assertRaises(ValueError):
            await undo_check_in(self.db, 3)

    async def test_streak_continues_after_yesterday(self):
        """昨天打过卡的习惯今天自动打卡，streak 连续"""
        h = RecurringTask(
            title="阅读", frequency="daily", next_due=date.today(),
            auto_keywords="阅读", last_checked_at=datetime.now() - timedelta(days=1),
            streak=5, total_completed=5,
        )
        self.db.add(h)
        await self.db.commit()

        checked = await auto_checkin_habits(self.db, text="今天阅读了30分钟")
        self.assertEqual(len(checked), 1)
        self.assertEqual(checked[0].streak, 6)

    def test_split_keywords(self):
        self.assertEqual(_split_keywords("洗澡,冲凉、淋浴;泡澡 温泉"), ["洗澡", "冲凉", "淋浴", "泡澡", "温泉"])
        self.assertEqual(_split_keywords(None), [])
        self.assertEqual(_split_keywords(""), [])


if __name__ == "__main__":
    unittest.main()
