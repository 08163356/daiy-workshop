"""写工具确认流测试（借鉴 harness 审批门：fail-closed）

功能契约：
- 写工具（requires_confirm）触发时：不入库执行，产出 confirm_required 事件并落 confirm_pending 日志，本轮结束
- 用户批准：执行工具、结果入日志、循环继续
- 用户拒绝：tool_result 记"已拒绝"，不执行，循环继续让 AI 回应
- 无待确认项时 resume 报错
"""
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.models.todo import TodoItem
from app.models.wellbeing import WellbeingEntry
from app.services import agent_loop
from app.services.agent_session import create_session


def fake_round(content: str = "", tool_calls: list | None = None):
    async def _gen(config, messages, tools, out, thinking_enabled=True):
        if tool_calls and thinking_enabled:
            out["thinking"] += "思考一下"
        if content:
            out["content"] += content
            yield {"type": "content", "delta": content}
        out["tool_calls"] = tool_calls or []
    return _gen


class AgentConfirmTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__, TodoItem.__table__,
                      WellbeingEntry.__table__, UserProfile.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.session = await create_session(self.db)
        self.config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _ctx(self, round_fn):
        return (
            patch.object(agent_loop, "llm_stream_round", round_fn),
            patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)),
            patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")),
            patch.object(agent_loop, "auto_title", AsyncMock()),
        )

    async def _collect(self, gen):
        return [ev async for ev in gen]

    async def _todos(self):
        result = await self.db.execute(select(TodoItem))
        return list(result.scalars())

    async def test_write_tool_triggers_confirm_not_execute(self):
        call = {"id": "c1", "type": "function",
                "function": {"name": "create_todo", "arguments": '{"title":"买牛奶"}'}}
        p1, p2, p3, p4 = self._ctx(fake_round(tool_calls=[call]))
        with p1, p2, p3, p4:
            events = await self._collect(
                agent_loop.run_agent_turn(self.db, self.session, "帮我记一个待办：买牛奶")
            )
        types = [e["type"] for e in events]
        self.assertIn("confirm_required", types)
        self.assertEqual(types[-1], "done")
        # 未执行：没有新待办
        self.assertEqual(await self._todos(), [])
        # 日志里有 confirm_pending
        result = await self.db.execute(
            select(AgentEvent).where(AgentEvent.event_type == "confirm_pending")
        )
        self.assertIsNotNone(result.scalar_one_or_none())

    async def test_approved_confirm_executes_tool(self):
        call = {"id": "c1", "type": "function",
                "function": {"name": "create_todo", "arguments": '{"title":"买牛奶"}'}}
        # 第一轮触发确认；批准后循环的下一轮直接给正文
        rounds = [fake_round(tool_calls=[call]), fake_round(content="好的，已帮你记下「买牛奶」")]
        state = {"i": 0}

        async def router(config, messages, tools, out, thinking_enabled=True):
            gen = rounds[min(state["i"], len(rounds) - 1)]
            state["i"] += 1
            async for ev in gen(config, messages, tools, out):
                yield ev

        p1, p2, p3, p4 = self._ctx(router)
        with p1, p2, p3, p4:
            await self._collect(agent_loop.run_agent_turn(self.db, self.session, "记个待办：买牛奶"))
            events = await self._collect(agent_loop.resume_after_confirm(self.db, self.session, True))

        types = [e["type"] for e in events]
        self.assertEqual(types, ["tool_result", "content", "done"])
        todos = await self._todos()
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0].title, "买牛奶")

    async def test_rejected_confirm_skips_execution(self):
        call = {"id": "c1", "type": "function",
                "function": {"name": "create_todo", "arguments": '{"title":"买牛奶"}'}}
        rounds = [fake_round(tool_calls=[call]), fake_round(content="好的，那我不记了")]
        state = {"i": 0}

        async def router(config, messages, tools, out, thinking_enabled=True):
            gen = rounds[min(state["i"], len(rounds) - 1)]
            state["i"] += 1
            async for ev in gen(config, messages, tools, out):
                yield ev

        p1, p2, p3, p4 = self._ctx(router)
        with p1, p2, p3, p4:
            await self._collect(agent_loop.run_agent_turn(self.db, self.session, "记个待办：买牛奶"))
            events = await self._collect(agent_loop.resume_after_confirm(self.db, self.session, False))

        self.assertEqual(events[0]["type"], "tool_result")
        self.assertTrue(events[0].get("rejected"))
        self.assertEqual(await self._todos(), [])

    async def test_resume_without_pending_raises(self):
        with self.assertRaises(ValueError):
            async for _ in agent_loop.resume_after_confirm(self.db, self.session, True):
                pass


if __name__ == "__main__":
    unittest.main()
