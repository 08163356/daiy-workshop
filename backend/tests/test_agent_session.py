"""Agent 会话基座（事件溯源）测试

功能契约：
- agent_sessions + agent_events 两张表；事件只追加，消息从事件投影
- append_event 的 seq 在会话内单调递增
- derive_messages 只投影 user/assistant/tool_result，thinking 等展示事件不进模型历史
- 标题：首条消息后自动生成；用户改名后钉住，自动生成不再覆盖
"""
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig
from app.services import agent_session as svc


class AgentSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(AgentSession.__table__.create)
            await conn.run_sync(AgentEvent.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_create_session_defaults(self):
        s = await svc.create_session(self.db)
        self.assertIsNone(s.title)
        self.assertFalse(s.title_pinned)
        self.assertEqual(s.status, "idle")
        self.assertIsNone(s.ai_config_id)

    async def test_append_event_seq_monotonic(self):
        s = await svc.create_session(self.db)
        e1 = await svc.append_event(self.db, s.id, "user_message", {"content": "你好"})
        e2 = await svc.append_event(self.db, s.id, "assistant_message", {"content": "你好！"})
        e3 = await svc.append_event(self.db, s.id, "thinking", {"content": "思考中"})
        self.assertEqual((e1.seq, e2.seq, e3.seq), (1, 2, 3))

    async def test_derive_messages_projects_only_chat_messages(self):
        s = await svc.create_session(self.db)
        await svc.append_event(self.db, s.id, "user_message", {"content": "今天做了什么"})
        await svc.append_event(self.db, s.id, "thinking", {"content": "用户在问日报"})
        await svc.append_event(self.db, s.id, "assistant_message", {"content": "你今天完成了..."})
        # 孤儿 tool_result（无 assistant tool_calls 认领）对模型 API 非法，投影丢弃
        await svc.append_event(self.db, s.id, "tool_result", {"tool_call_id": "c1", "name": "query_todos", "content": "3条待办"})
        msgs = await svc.derive_messages(self.db, s.id)
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["user", "assistant"])
        self.assertEqual(msgs[0]["content"], "今天做了什么")

    async def test_derive_messages_with_tool_calls(self):
        s = await svc.create_session(self.db)
        await svc.append_event(self.db, s.id, "assistant_message", {
            "content": "",
            "thinking": "用户想查待办",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "query_todos", "arguments": "{}"}}],
        })
        # 新投影规则：tool_calls 必须有对应 tool_result 才保留，且思维链模式下回传 reasoning_content
        await svc.append_event(self.db, s.id, "tool_result", {
            "tool_call_id": "c1", "name": "query_todos", "content": "- 任务A",
        })
        msgs = await svc.derive_messages(self.db, s.id)
        self.assertEqual(msgs[0]["role"], "assistant")
        self.assertEqual(msgs[0]["tool_calls"][0]["function"]["name"], "query_todos")
        self.assertEqual(msgs[0]["reasoning_content"], "用户想查待办")
        self.assertEqual(msgs[1]["role"], "tool")
        self.assertEqual(msgs[1]["tool_call_id"], "c1")

    async def test_rename_pins_title(self):
        s = await svc.create_session(self.db)
        await svc.rename_session(self.db, s.id, "我的重要对话")
        s2 = await svc.get_session(self.db, s.id)
        self.assertEqual(s2.title, "我的重要对话")
        self.assertTrue(s2.title_pinned)

    async def test_auto_title_skips_pinned(self):
        s = await svc.create_session(self.db)
        await svc.rename_session(self.db, s.id, "固定标题")
        config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=100)
        with patch.object(svc, "get_active_ai_config", AsyncMock(return_value=config)) as cfg:
            await svc.auto_title(self.db, s.id, "随便一条消息")
        cfg.assert_not_called()  # 钉住后不应调 AI

    async def test_auto_title_generates_for_first_message(self):
        s = await svc.create_session(self.db)
        config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=100)
        resp = httpx.Response(
            200,
            json={"choices": [{"message": {"content": "本周任务回顾"}}], "usage": {}},
            request=httpx.Request("POST", "https://example.test"),
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=resp)
        with patch.object(svc, "get_active_ai_config", AsyncMock(return_value=config)), \
             patch("httpx.AsyncClient", return_value=client):
            await svc.auto_title(self.db, s.id, "帮我总结一下本周做了什么")
        s2 = await svc.get_session(self.db, s.id)
        self.assertEqual(s2.title, "本周任务回顾")
        self.assertFalse(s2.title_pinned)  # 自动生成的标题未钉住

    async def test_delete_session_removes_events(self):
        s = await svc.create_session(self.db)
        await svc.append_event(self.db, s.id, "user_message", {"content": "x"})
        await svc.delete_session(self.db, s.id)
        self.assertIsNone(await svc.get_session(self.db, s.id))
        self.assertEqual(await svc.get_session_events(self.db, s.id), [])

    async def test_list_sessions_recent_first(self):
        s1 = await svc.create_session(self.db)
        s2 = await svc.create_session(self.db)
        sessions = await svc.list_sessions(self.db)
        self.assertEqual([s.id for s in sessions], [s2.id, s1.id])


if __name__ == "__main__":
    unittest.main()
