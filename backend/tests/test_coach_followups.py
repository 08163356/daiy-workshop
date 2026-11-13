"""教练跟进项测试（第一期）：沉淀写 followups、开场注入、待办完成闭环"""
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.models.prompt_skill import PromptSkill
from app.models.todo import TodoItem
from app.services import coach_service
from app.services.agent_session import append_event, create_session


def _mock_client(content: str):
    resp = httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}], "usage": {}},
        request=httpx.Request("POST", "https://example.test"),
    )
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post = AsyncMock(return_value=resp)
    return client


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        from app.models.diary import DiaryEntry
        from app.models.note import Note, NoteConcept
        from app.models.concept import Concept
        from app.models.ai_question import AIQuestion
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__, UserProfile.__table__,
                      PromptSkill.__table__, TodoItem.__table__, DiaryEntry.__table__,
                      Note.__table__, NoteConcept.__table__, Concept.__table__,
                      AIQuestion.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()


class FinalizeFollowupTests(Base):
    async def test_finalize_writes_followups(self):
        """沉淀产出 commitment/check_question/review_on → 写入会话 followups"""
        session = await create_session(self.db)
        session.mode = "coach"
        await self.db.commit()
        await append_event(self.db, session.id, "user_message", {"content": "我想聊聊拖延的问题，上次说要把那句话写下来"})
        await append_event(self.db, session.id, "assistant_message", {"content": "写下来了吗？"})
        await append_event(self.db, session.id, "user_message", {"content": "写了，写完感觉轻松多了，决定每周三晚上都写一次"})

        client = _mock_client('''{
          "summary": "从拖延到兑现：用户把没说出口的话写了下来",
          "insights": ["写下来之后这件事就没那么重了"],
          "coaching_type": "emotion",
          "commitment": "每周三晚上写一次「没说出口的话」",
          "check_question": "这周三写了吗？写完感觉如何？",
          "review_on": "2026-10-28",
          "proposed_todos": [],
          "profile_updates": []
        }''')
        with patch("app.services.coach_service.httpx.AsyncClient", return_value=client), \
             patch("app.services.coach_service.get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch("app.services.coach_service.get_user_profile_text", AsyncMock(return_value="")):
            result = await coach_service.finalize_coach_session(self.db, session)

        await self.db.refresh(session)
        self.assertEqual(len(session.followups), 1)
        f = session.followups[0]
        self.assertEqual(f["status"], "open")
        self.assertEqual(f["review_on"], "2026-10-28")
        self.assertIsNone(f["todo_id"])
        self.assertEqual(result["commitment"], "每周三晚上写一次「没说出口的话」")

    async def test_finalize_no_commitment_no_followup(self):
        session = await create_session(self.db)
        session.mode = "coach"
        await self.db.commit()
        await append_event(self.db, session.id, "user_message", {"content": "就是随便聊聊最近状态，没什么特别想解决的事，就是随便聊聊最近状态"})
        await append_event(self.db, session.id, "assistant_message", {"content": "嗯，我听着呢，最近有什么想聊的吗"})

        client = _mock_client('''{
          "summary": "闲聊", "insights": [], "coaching_type": "life",
          "commitment": null, "check_question": null, "review_on": null,
          "proposed_todos": [], "profile_updates": []
        }''')
        with patch("app.services.coach_service.httpx.AsyncClient", return_value=client), \
             patch("app.services.coach_service.get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch("app.services.coach_service.get_user_profile_text", AsyncMock(return_value="")):
            await coach_service.finalize_coach_session(self.db, session)
        await self.db.refresh(session)
        self.assertFalse(session.followups)


class OpenFollowupsTests(Base):
    async def test_open_followups_only_open_and_no_todo(self):
        """开场材料：只收 open 且未建成待办的跟进项"""
        s1 = await create_session(self.db)
        s1.mode = "coach"
        s1.followups = [
            {"text": "周三前写下来", "check_question": "写了吗", "review_on": "2026-10-24", "todo_id": None, "status": "open"},
            {"text": "已完成的", "check_question": "", "review_on": None, "todo_id": None, "status": "done"},
            {"text": "已建成待办的", "check_question": "", "review_on": None, "todo_id": 5, "status": "open"},
        ]
        await self.db.commit()

        text = await coach_service.get_open_followups(self.db, exclude_session_id=999)
        self.assertIn("周三前写下来", text)
        self.assertIn("写了吗", text)
        self.assertNotIn("已完成的", text)
        self.assertNotIn("已建成待办的", text)


class FollowupCloseLoopTests(Base):
    async def test_complete_coach_todo_closes_followup(self):
        """完成 source=coach 待办 → 会话上对应跟进项标 done"""
        session = await create_session(self.db)
        session.mode = "coach"
        todo = TodoItem(title="写下来", source="coach", source_id=session.id, status="planned", quadrant=2)
        self.db.add(todo)
        await self.db.flush()
        session.followups = [
            {"text": "周三前写下来", "check_question": "写了吗", "review_on": None, "todo_id": todo.id, "status": "open"},
        ]
        await self.db.commit()

        await coach_service.close_followup_by_todo(self.db, todo.id)
        # 不用 refresh（同事务内 refresh 读到的是 flush 前快照），新鲜查询验证
        fresh = (await self.db.execute(select(AgentSession).where(AgentSession.id == session.id))).scalar_one()
        self.assertEqual(fresh.followups[0]["status"], "done")

    async def test_non_coach_todo_noop(self):
        todo = TodoItem(title="普通待办", source="manual", status="planned", quadrant=2)
        self.db.add(todo)
        await self.db.commit()
        # 不应报错也不应改任何会话
        await coach_service.close_followup_by_todo(self.db, todo.id)


class FollowupTodoTests(Base):
    async def _session_with_draft(self):
        session = await create_session(self.db)
        session.mode = "coach"
        session.followups = [{
            "text": "每周三写下来", "check_question": "写了吗", "review_on": "2026-10-28",
            "todo_id": None,
            "todo_draft": {"title": "每周三晚写「没说出口的话」", "description": "核对：写了吗", "category": "life", "quadrant": 2},
            "status": "open",
        }]
        await self.db.commit()
        return session

    async def test_create_todo_from_followup(self):
        """建成待办：source=coach、关联会话、回看日入计划日期、回写 todo_id"""
        session = await self._session_with_draft()
        result = await coach_service.create_todo_from_followup(self.db, session, 0)
        todo = (await self.db.execute(select(TodoItem))).scalar_one()
        self.assertEqual(todo.source, "coach")
        self.assertEqual(todo.source_id, session.id)
        self.assertEqual(todo.quadrant, 2)
        self.assertEqual(todo.scheduled_date, date(2026, 10, 28))
        await self.db.refresh(session)
        self.assertEqual(session.followups[0]["todo_id"], result["todo_id"])

    async def test_create_twice_rejected(self):
        session = await self._session_with_draft()
        await coach_service.create_todo_from_followup(self.db, session, 0)
        await self.db.refresh(session)
        with self.assertRaises(ValueError):
            await coach_service.create_todo_from_followup(self.db, session, 0)

    async def test_create_todo_tool_source_params(self):
        """create_todo 工具支持 source/source_id，默认 manual 不变"""
        from app.services.agent_tools import execute_tool
        result = await execute_tool(self.db, "create_todo", {"title": "普通任务"})
        self.assertIn("已创建", result["content"])
        todo = (await self.db.execute(select(TodoItem))).scalar_one()
        self.assertEqual(todo.source, "manual")

        result2 = await execute_tool(self.db, "create_todo", {
            "title": "教练任务", "source": "coach", "source_id": 7, "quadrant": 2,
        })
        self.assertIn("已创建", result2["content"])
        todos = (await self.db.execute(select(TodoItem).order_by(TodoItem.id))).scalars().all()
        self.assertEqual(todos[1].source, "coach")
        self.assertEqual(todos[1].source_id, 7)

    async def test_open_followups_reads_coach_todos_first(self):
        """开场材料：未完成的 coach 待办排最前"""
        todo = TodoItem(title="教练建的待办", source="coach", source_id=1,
                        status="planned", quadrant=2, description="核对：写了吗")
        self.db.add(todo)
        await self.db.commit()
        text = await coach_service.get_open_followups(self.db, exclude_session_id=999)
        self.assertIn("待办未完成：教练建的待办", text)


class OriginExcerptTests(Base):
    async def test_diary_excerpt(self):
        """日记来源：服务端注入日期+标题+关键问题+摘录"""
        from app.models.diary import DiaryEntry
        self.db.add(DiaryEntry(date=date(2026, 10, 20), title="那天", content="日记正文内容" * 50,
                               key_issues=["为什么害怕表达"]))
        await self.db.commit()
        session = await create_session(self.db)
        session.origin_type = "diary"
        session.origin_id = 1
        await self.db.commit()
        text = await coach_service.get_origin_excerpt(self.db, session)
        self.assertIn("2026-10-20", text)
        self.assertIn("为什么害怕表达", text)
        self.assertIn("日记正文内容", text)

    async def test_note_excerpt(self):
        from app.models.note import Note
        self.db.add(Note(filename="n1", title="原子习惯", content="笔记内容", file_hash="h"))
        await self.db.commit()
        session = await create_session(self.db)
        session.origin_type = "note"
        session.origin_id = 1
        text = await coach_service.get_origin_excerpt(self.db, session)
        self.assertIn("原子习惯", text)

    async def test_question_excerpt(self):
        from app.models.ai_question import AIQuestion
        self.db.add(AIQuestion(source_type="diary", question="那个项目指什么？", status="pending"))
        await self.db.commit()
        session = await create_session(self.db)
        session.origin_type = "question"
        session.origin_id = 1
        text = await coach_service.get_origin_excerpt(self.db, session)
        self.assertIn("那个项目指什么", text)

    async def test_no_origin_empty(self):
        session = await create_session(self.db)
        self.assertEqual(await coach_service.get_origin_excerpt(self.db, session), "")

    async def test_chat_endpoint_records_origin(self):
        """建会话带 origin → 写入会话字段"""
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient
        from app.api.agent import router
        from app.core.database import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api")

        async def override_db():
            yield self.db
        app.dependency_overrides[get_db] = override_db

        # 记录管线/对话循环会真调 AI，用 /教练 进 coach 模式后立刻结束流也行；
        # 这里只验证会话字段写入：用假 rounds 短路
        async def fake_rounds(db, session, messages, config, tools):
            yield {"type": "content", "delta": "ok"}
            yield {"type": "done", "session_id": session.id}

        config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)
        with patch("app.services.agent_loop._run_rounds", side_effect=fake_rounds), \
             patch("app.services.agent_loop.get_active_ai_config", AsyncMock(return_value=config)), \
             patch("app.services.ai_service.get_user_profile_text", AsyncMock(return_value="")), \
             patch("app.services.agent_loop.get_user_profile_text", AsyncMock(return_value="")), \
             patch("app.services.compaction.maybe_compact", AsyncMock(side_effect=lambda db, s, m: m)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                async with c.stream("POST", "/api/agent/chat", json={
                    "content": "我想就这篇日记深挖", "origin_type": "diary", "origin_id": 7,
                }) as r:
                    self.assertEqual(r.status_code, 200)
                    async for _ in r.aiter_lines():
                        pass
        session = (await self.db.execute(select(AgentSession))).scalars().first()
        self.assertEqual(session.origin_type, "diary")
        self.assertEqual(session.origin_id, 7)


if __name__ == "__main__":
    unittest.main()
