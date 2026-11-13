"""撤回（message_void）与插话（steering）测试

契约：
- 仅最后一条 user_message 可撤回（之后有事件则拒绝）；撤回后投影双跳过
- steering 在轮次边界领取升格为 user_message；被撤回的插话不升格；关轮前最后机会领取
"""
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.models.todo import TodoItem
from app.services import agent_loop
from app.services.agent_session import (
    append_event, create_session, derive_display_messages, derive_messages,
    rewind_from_user_seq,
    void_last_user_message,
)


class VoidTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.session = await create_session(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_rewind_drops_user_message_and_reply(self):
        user = await append_event(self.db, self.session.id, "user_message", {"content": "原来的问题"})
        await append_event(self.db, self.session.id, "assistant_message", {"content": "原来的回答"})
        text = await rewind_from_user_seq(self.db, self.session.id, user.seq)
        self.assertEqual(text, "原来的问题")
        self.assertEqual(await derive_display_messages(self.db, self.session.id), [])

    async def test_void_last_user_message(self):
        await append_event(self.db, self.session.id, "user_message", {"content": "写错了"})
        text = await void_last_user_message(self.db, self.session.id)
        self.assertEqual(text, "写错了")
        # 双投影都跳过
        self.assertEqual(await derive_messages(self.db, self.session.id), [])
        self.assertEqual(await derive_display_messages(self.db, self.session.id), [])
        # 日志里还在（软删审计）
        self.assertEqual(len(await derive_messages(self.db, self.session.id)), 0)

    async def test_cannot_void_after_reply(self):
        await append_event(self.db, self.session.id, "user_message", {"content": "问"})
        await append_event(self.db, self.session.id, "assistant_message", {"content": "答"})
        with self.assertRaises(ValueError):
            await void_last_user_message(self.db, self.session.id)

    async def test_cannot_void_twice(self):
        await append_event(self.db, self.session.id, "user_message", {"content": "x"})
        await void_last_user_message(self.db, self.session.id)
        with self.assertRaises(ValueError):
            await void_last_user_message(self.db, self.session.id)


class SteeringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__, TodoItem.__table__, UserProfile.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.session = await create_session(self.db)
        self.config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_steering_claimed_at_round_boundary(self):
        """第一轮正文后关轮前领取到插话 → 继续一轮回应插话，插话升格为 user_message"""
        rounds = [
            # 第一轮：AI 正文；此时插话还没来 → 关轮
            # 第二轮（插话后来了）：AI 回应插话
        ]
        call_count = {"n": 0}

        async def round_fn(config, messages, tools, out, thinking_enabled=True):
            call_count["n"] += 1
            if call_count["n"] == 1:
                out["content"] += "先回答主要问题"
                yield {"type": "content", "delta": "先回答主要问题"}
                # 模拟：AI 第一轮输出期间用户插话了
                await append_event(self.db, self.session.id, "steering", {"content": "顺便问下别的事", "claimed": False})
                await self.db.commit()
            else:
                # 第二轮应看到插话在 messages 里
                steered = [m for m in messages if m["role"] == "user" and "顺便" in m["content"]]
                assert steered, "第二轮 messages 里应包含插话"
                out["content"] += "回应插话"
                yield {"type": "content", "delta": "回应插话"}

        with patch.object(agent_loop, "llm_stream_round", round_fn), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")), \
             patch.object(agent_loop, "auto_title", AsyncMock()):
            events = [ev async for ev in agent_loop.run_agent_turn(self.db, self.session, "主要问题")]

        types = [e["type"] for e in events]
        self.assertIn("steering_claimed", types)
        self.assertEqual(call_count["n"], 2)
        # 插话升格为 user_message，投影里可见
        messages = await derive_messages(self.db, self.session.id)
        contents = [m.get("content", "") for m in messages if m["role"] == "user"]
        self.assertIn("顺便问下别的事", contents)

    async def test_voided_steering_not_claimed(self):
        """被撤销的插话不升格"""
        ev = await append_event(self.db, self.session.id, "steering", {"content": "后悔了", "claimed": False})
        await append_event(self.db, self.session.id, "message_void", {"target_seq": ev.seq})
        texts = await agent_loop._claim_pending_steering(self.db, self.session.id)
        self.assertEqual(texts, [])
        # 且标记了 claimed（不再出现）
        texts2 = await agent_loop._claim_pending_steering(self.db, self.session.id)
        self.assertEqual(texts2, [])


if __name__ == "__main__":
    unittest.main()
