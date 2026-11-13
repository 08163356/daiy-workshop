"""学习功能测试：notes 来源类型（book/course/self）+ 管线前缀路由 + 时间线过滤"""
import unittest
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.concept import Concept
from app.models.note import Note, NoteConcept
from app.models.relation import ConceptRelation
from app.models.thinking_model import ThinkingModel
from app.services.agent_loop import _match_record_pipeline
from app.services.agent_tools import _tool_save_record


class RecordPipelinePrefixTests(unittest.TestCase):
    def test_course_prefix(self):
        self.assertEqual(_match_record_pipeline("/课程 今天听了XX的课"), ("course", "今天听了XX的课"))

    def test_selfnote_prefix(self):
        self.assertEqual(_match_record_pipeline("/随笔 一个想法"), ("selfnote", "一个想法"))

    def test_existing_prefixes_unchanged(self):
        self.assertEqual(_match_record_pipeline("/日记 今天"), ("diary", "今天"))
        self.assertEqual(_match_record_pipeline("/笔记 读了本书"), ("reading", "读了本书"))

    def test_no_prefix(self):
        self.assertIsNone(_match_record_pipeline("随便聊聊"))


class NoteSourceTypeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (Note.__table__, NoteConcept.__table__, Concept.__table__,
                      ConceptRelation.__table__, ThinkingModel.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_default_source_type_is_book(self):
        n = Note(filename="a1", title="t", content="c", file_hash="h1")
        self.db.add(n)
        await self.db.commit()
        self.assertEqual(n.source_type, "book")

    async def test_save_course_record(self):
        ids = await _tool_save_record(
            self.db, "course", "2026-10-20 课程笔记", "今天听了段永平的投资课", "2026-10-20", "", {},
        )
        n = (await self.db.execute(select(Note))).scalars().first()
        self.assertEqual(n.source_type, "course")
        self.assertIn("note_id", ids)

    async def test_save_selfnote_record(self):
        await _tool_save_record(self.db, "selfnote", "随笔", "一个想法", "2026-10-20", "", {})
        n = (await self.db.execute(select(Note))).scalars().first()
        self.assertEqual(n.source_type, "self")

    async def test_save_reading_record_stays_book(self):
        await _tool_save_record(self.db, "reading", "笔记", "读书内容", "2026-10-20", "", {})
        n = (await self.db.execute(select(Note))).scalars().first()
        self.assertEqual(n.source_type, "book")


class TimelineFilterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (Note.__table__, NoteConcept.__table__, Concept.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        for i, st in enumerate(["book", "course", "self", "book"]):
            self.db.add(Note(filename=f"f{i}", title=f"标题{i}", content="c",
                             file_hash=f"h{i}", reading_date=date.today(), source_type=st))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_timeline_source_filter(self):
        from app.api.reading import get_timeline
        result = await get_timeline(skip=0, limit=10, keyword=None, source_type="course", db=self.db)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["source_type"], "course")

    async def test_timeline_no_filter_returns_all(self):
        from app.api.reading import get_timeline
        result = await get_timeline(skip=0, limit=10, keyword=None, source_type=None, db=self.db)
        self.assertEqual(result["total"], 4)


if __name__ == "__main__":
    unittest.main()
