"""教练模式测试：/教练 前缀切模式+前缀剥离、coach skill 注入、跨会话记忆、结束沉淀"""
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.models.prompt_skill import PromptSkill
from app.models.todo import TodoItem
from app.services import agent_loop, coach_service
from app.services.agent_session import create_session, derive_messages
from app.services.skill_service import seed_builtin_skills


class CoachModeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__, UserProfile.__table__,
                      PromptSkill.__table__, TodoItem.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        await seed_builtin_skills(self.db)
        await self.db.commit()
        self.config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_coach_prefix_sets_mode_and_strips(self):
        """/教练 前缀：会话切 coach 模式，日志里不含前缀"""
        session = await create_session(self.db)
        captured: dict = {}

        async def fake_round(config, messages, tools, out, thinking_enabled=True):
            captured["system"] = messages[0]["content"]
            out["content"] = "你最近最被什么困扰？"
            yield {"type": "content", "delta": "你最近最被什么困扰？"}

        with patch.object(agent_loop, "llm_stream_round", fake_round), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")), \
             patch.object(agent_loop, "auto_title", AsyncMock()):
            async for _ in agent_loop.run_agent_turn(self.db, session, "/教练 我最近总拖延"):
                pass

        await self.db.refresh(session)
        self.assertEqual(session.mode, "coach")
        # 系统提示词注入 coach skill（GROW 骨架与开场核对在里头）
        self.assertIn("GROW", captured["system"])
        self.assertIn("一次只问一个问题", captured["system"])
        self.assertIn("未关闭的跟进项", captured["system"])
        # 日志中用户消息不含前缀
        messages = await derive_messages(self.db, session.id)
        self.assertEqual(messages[0]["content"], "我最近总拖延")

    async def test_recent_coach_summaries(self):
        """跨会话记忆：返回其它教练会话的摘要"""
        old = AgentSession(mode="coach", summary="上次聊到拖延与完美主义", title="拖延")
        self.db.add(old)
        await self.db.commit()
        new = await create_session(self.db)
        text = await coach_service.get_recent_coach_summaries(self.db, new.id)
        self.assertIn("拖延与完美主义", text)

    async def test_finalize_coach_session(self):
        """结束沉淀：summary/insights 写回会话，画像更新被调用"""
        session = AgentSession(mode="coach")
        self.db.add(session)
        await self.db.commit()
        from app.services.agent_session import append_event
        await append_event(self.db, session.id, "user_message", {"content": "我总觉得自己做得不够好"})
        await append_event(self.db, session.id, "assistant_message", {"content": "这个「不够好」的参照是什么？"})

        resp = httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"summary":"聊了自我苛责","insights":["参照系来自外界"],"coaching_type":"emotion","profile_updates":[]}'}}], "usage": {}},
            request=httpx.Request("POST", "https://example.test"),
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=resp)

        with patch("app.services.coach_service.httpx.AsyncClient", return_value=client), \
             patch.object(coach_service, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(coach_service, "get_user_profile_text", AsyncMock(return_value="")):
            result = await coach_service.finalize_coach_session(self.db, session)

        self.assertEqual(result["summary"], "聊了自我苛责")
        self.assertEqual(result["insights"], ["参照系来自外界"])
        await self.db.refresh(session)
        self.assertEqual(session.summary, "聊了自我苛责")


if __name__ == "__main__":
    unittest.main()
