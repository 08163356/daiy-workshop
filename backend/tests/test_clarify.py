"""澄清提问测试：问题生成、答案提炼进画像、clarify 端点幂等"""
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.services.agent_session import append_event, create_session, get_session_events
from app.services import clarify_service


def _mock_response(content: str):
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}], "usage": {}},
        request=httpx.Request("POST", "https://example.test"),
    )


class ClarifyBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__, UserProfile.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _client(self, content: str):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=_mock_response(content))
        return client


class GenerateQuestionsTests(ClarifyBase):
    async def test_generates_questions_with_options(self):
        client = self._client('{"questions": [{"question": "和谁打球这么开心？", "options": ["固定球友", "同事", "新朋友"]}]}')
        with patch("app.services.clarify_service.httpx.AsyncClient", return_value=client), \
             patch("app.services.clarify_service.get_active_ai_config", AsyncMock(return_value=self.config)):
            result = await clarify_service.generate_clarify_questions(self.db, "日记", "今天打球很开心", "分析内容")
        self.assertIsNotNone(result)
        self.assertEqual(len(result["questions"]), 1)
        self.assertEqual(result["questions"][0]["options"], ["固定球友", "同事", "新朋友"])
        self.assertTrue(result["batch_id"])

    async def test_no_questions_returns_none(self):
        client = self._client('{"questions": []}')
        with patch("app.services.clarify_service.httpx.AsyncClient", return_value=client), \
             patch("app.services.clarify_service.get_active_ai_config", AsyncMock(return_value=self.config)):
            result = await clarify_service.generate_clarify_questions(self.db, "日记", "平淡的一天", "没什么特别")
        self.assertIsNone(result)

    async def test_ai_failure_returns_none(self):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(side_effect=httpx.HTTPError("boom"))
        with patch("app.services.clarify_service.httpx.AsyncClient", return_value=client), \
             patch("app.services.clarify_service.get_active_ai_config", AsyncMock(return_value=self.config)):
            result = await clarify_service.generate_clarify_questions(self.db, "日记", "内容", "分析")
        self.assertIsNone(result)


class SynthesizeTests(ClarifyBase):
    async def test_answers_synthesized_into_profile(self):
        """回答经 AI 提炼后写画像，不是原始问答直倒"""
        client = self._client('{"learned": [{"category": "人脉网络", "key": "固定球友", "value": "有一群每周固定打球的公司朋友，是重要的高能量社交来源", "confidence": 0.7}]}')
        with patch("app.services.clarify_service.httpx.AsyncClient", return_value=client), \
             patch("app.services.clarify_service.get_active_ai_config", AsyncMock(return_value=self.config)):
            learned = await clarify_service.synthesize_answers_to_profile(
                self.db, "今天打球很开心", [{"question": "和谁打球？", "answer": "公司的朋友"}],
            )
        self.assertEqual(len(learned), 1)
        rows = (await self.db.execute(select(UserProfile))).scalars().all()
        self.assertEqual(rows[0].category, "人脉网络")
        self.assertNotEqual(rows[0].value, "公司的朋友")  # 提炼后的表述，不是照抄

    async def test_no_substance_no_write(self):
        client = self._client('{"learned": []}')
        with patch("app.services.clarify_service.httpx.AsyncClient", return_value=client), \
             patch("app.services.clarify_service.get_active_ai_config", AsyncMock(return_value=self.config)):
            learned = await clarify_service.synthesize_answers_to_profile(
                self.db, "内容", [{"question": "q", "answer": "没什么"}],
            )
        self.assertEqual(learned, [])
        rows = (await self.db.execute(select(UserProfile))).scalars().all()
        self.assertEqual(rows, [])


class ClarifyEndpointTests(ClarifyBase):
    async def test_clarify_flow_and_idempotency(self):
        """端点（流式）：问答进日志 + 画像提炼 + AI 继续对话反馈 + 批次幂等"""
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient
        from app.api.agent import router
        from app.core.database import get_db

        session = await create_session(self.db)
        await append_event(self.db, session.id, "clarify_questions", {
            "batch_id": "b1", "questions": [{"question": "和谁打球？", "options": []}],
            "source_content": "今天打球很开心",
        })

        app = FastAPI()
        app.include_router(router, prefix="/api")
        async def override_db():
            yield self.db
        app.dependency_overrides[get_db] = override_db

        client = self._client('{"learned": [{"category": "人脉网络", "key": "球友", "value": "和公司朋友打球是重要的高能量社交", "confidence": 0.7}]}')

        # 继续对话走 _prepare_context/_run_rounds，测试里用假的替身避免真调 LLM
        async def fake_prepare(db, s):
            return self.config, [{"role": "system", "content": "sys"}], []

        async def fake_rounds(db, s, messages, config, tools):
            yield {"type": "content", "delta": "收到，我记住了。"}
            yield {"type": "done", "session_id": s.id}

        with patch("app.services.clarify_service.httpx.AsyncClient", return_value=client), \
             patch("app.services.clarify_service.get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch("app.services.agent_loop._prepare_context", fake_prepare), \
             patch("app.services.agent_loop._run_rounds", fake_rounds):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                r = await c.post("/api/agent/clarify", json={
                    "session_id": session.id, "batch_id": "b1",
                    "answers": [{"question": "和谁打球？", "answer": "公司朋友"}],
                })
                self.assertEqual(r.status_code, 200)
                # SSE 流里带 content 反馈事件，说明答完后继续了对话
                self.assertIn('"type": "content"', r.text)
                self.assertIn("收到，我记住了", r.text)

                # 幂等：再提交直接返回 done，不重复处理
                r2 = await c.post("/api/agent/clarify", json={
                    "session_id": session.id, "batch_id": "b1",
                    "answers": [{"question": "和谁打球？", "answer": "公司朋友"}],
                })
                self.assertIn('"type": "done"', r2.text)

        # 日志里有问答用户消息 + answered 标记
        events = await get_session_events(self.db, session.id)
        types = [e.event_type for e in events]
        self.assertIn("user_message", types)
        self.assertIn("clarify_answered", types)
        profiles = (await self.db.execute(select(UserProfile))).scalars().all()
        self.assertEqual(len(profiles), 1)


if __name__ == "__main__":
    unittest.main()
