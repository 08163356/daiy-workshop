"""日记级联删除测试：删除日记时衍生的心力/候选/AI 提问一起删除，其它来源不受影响"""
import unittest
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.ai_question import AIQuestion
from app.models.diary import DiaryEntry
from app.models.wellbeing import WellbeingCandidate, WellbeingEntry
from app.api.diary import delete_entry, entries_by_date, entry_neighbors, get_derived_counts, list_dates


class DiaryCascadeDeleteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (DiaryEntry.__table__, WellbeingEntry.__table__,
                      WellbeingCandidate.__table__, AIQuestion.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()

        diary = DiaryEntry(date=date(2026, 10, 20), title="测试日记", content="内容")
        other_diary = DiaryEntry(date=date(2026, 10, 19), title="别的日记", content="别的")
        self.db.add_all([diary, other_diary])
        await self.db.flush()
        self.diary_id = diary.id
        self.other_id = other_diary.id

        # 本篇日记的衍生数据
        self.db.add_all([
            WellbeingEntry(type="achievement", content="来自本篇", occurred_at=date(2026, 10, 20),
                           source_type="diary", source_id=self.diary_id),
            WellbeingCandidate(source_type="diary", source_id=self.diary_id,
                               suggested_type="gratitude", suggested_content="候选"),
            AIQuestion(source_type="diary", source_id=self.diary_id, question="为什么？"),
            # 其它来源/其它日记的数据不应受影响
            WellbeingEntry(type="gratitude", content="手动记的", occurred_at=date(2026, 10, 20),
                           source_type="manual"),
            WellbeingEntry(type="achievement", content="别的日记的", occurred_at=date(2026, 10, 19),
                           source_type="diary", source_id=self.other_id),
            AIQuestion(source_type="note", source_id=99, question="笔记的问题"),
        ])
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_list_dates_unique_and_desc(self):
        self.db.add(DiaryEntry(date=date(2026, 10, 20), title="同一天第二篇", content="重复日期"))
        await self.db.commit()
        data = await list_dates(self.db)
        self.assertEqual(data["dates"], ["2026-10-20", "2026-10-19"])

    async def test_neighbors_follow_newest_first(self):
        newer = DiaryEntry(date=date(2026, 10, 21), title="更新的一篇", content="新")
        self.db.add(newer)
        await self.db.commit()
        data = await entry_neighbors(self.diary_id, self.db)
        self.assertEqual(data["prev"]["title"], "更新的一篇")
        self.assertEqual(data["next"]["title"], "别的日记")
        edge = await entry_neighbors(newer.id, self.db)
        self.assertIsNone(edge["prev"])
        self.assertEqual(edge["next"]["id"], self.diary_id)

    async def test_entries_by_date(self):
        self.db.add(DiaryEntry(date=date(2026, 10, 20), title="同一天第二篇", content="重复日期"))
        await self.db.commit()
        data = await entries_by_date(date(2026, 10, 20), self.db)
        self.assertEqual([item["title"] for item in data["items"]], ["同一天第二篇", "测试日记"])

    async def test_derived_counts(self):
        counts = await get_derived_counts(self.diary_id, self.db)
        self.assertEqual(counts, {"wellbeing_entries": 1, "wellbeing_candidates": 1, "ai_questions": 1})

    async def test_cascade_delete(self):
        result = await delete_entry(self.diary_id, self.db)
        self.assertEqual(result["deleted_derived"]["wellbeing_entries"], 1)
        await self.db.commit()

        # 日记本体没了
        self.assertIsNone(await self.db.get(DiaryEntry, self.diary_id))
        # 衍生数据没了
        self.assertEqual(len((await self.db.execute(
            select(WellbeingEntry).where(WellbeingEntry.source_type == "diary", WellbeingEntry.source_id == self.diary_id)
        )).scalars().all()), 0)
        self.assertEqual(len((await self.db.execute(
            select(AIQuestion).where(AIQuestion.source_type == "diary", AIQuestion.source_id == self.diary_id)
        )).scalars().all()), 0)
        # 其它来源/其它日记的不受影响
        remaining = (await self.db.execute(select(WellbeingEntry))).scalars().all()
        self.assertEqual(len(remaining), 2)
        questions = (await self.db.execute(select(AIQuestion))).scalars().all()
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].source_type, "note")


if __name__ == "__main__":
    unittest.main()
