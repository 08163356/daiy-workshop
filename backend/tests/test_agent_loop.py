"""Agent 对话循环测试

功能契约：
- 用户消息先入事件日志；一轮无工具调用时直接产出正文并写入日志
- 有工具调用时：assistant(tool_calls) 与 tool_result 都入日志，下一轮继续
- SSE 事件序列：content/thinking 增量 → tool_call/tool_result → done
- 超过最大轮数兜底
"""
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.models.todo import TodoItem
from app.services import agent_loop
from app.services.agent_session import create_session, derive_messages


def fake_llm_round(content: str = "", tool_calls: list | None = None):
    """伪造一轮 LLM 流式调用（有工具调用时带思维链——真实模型在思维链模式下如此，
    投影规则要求带 tool_calls 的消息必须有 reasoning_content 可回传）"""
    async def _gen(config, messages, tools, out, thinking_enabled=True):
        if tool_calls and thinking_enabled:
            out["thinking"] += "思考一下"
        if content:
            out["content"] += content
            yield {"type": "content", "delta": content}
        out["tool_calls"] = tool_calls or []
    return _gen


class AgentLoopTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(AgentSession.__table__.create)
            await conn.run_sync(AgentEvent.__table__.create)
            await conn.run_sync(TodoItem.__table__.create)
            await conn.run_sync(UserProfile.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.db.add(TodoItem(title="写周报", status="planned", quadrant=2))
        await self.db.commit()
        self.session = await create_session(self.db)
        self.config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _patches(self, round_fn):
        return (
            patch.object(agent_loop, "llm_stream_round", round_fn),
            patch("app.services.agent_session.get_active_ai_config", AsyncMock(return_value=self.config)),
            patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)),
            patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")),
        )

    async def _collect(self, gen):
        return [ev async for ev in gen]

    async def test_simple_turn_no_tools(self):
        p1, p2, p3, p4 = self._patches(fake_llm_round(content="你好，我是助手"))
        # auto_title 也会调 AI，一并 mock 掉
        with p1, p2, p3, p4, \
             patch.object(agent_loop, "auto_title", AsyncMock()):
            events = await self._collect(
                agent_loop.run_agent_turn(self.db, self.session, "你好")
            )
        types = [e["type"] for e in events]
        self.assertEqual(types, ["content", "done"])

        msgs = await derive_messages(self.db, self.session.id)
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])
        self.assertEqual(msgs[1]["content"], "你好，我是助手")

    async def test_turn_with_tool_call(self):
        call = {"id": "c1", "type": "function",
                "function": {"name": "query_todos", "arguments": '{"status":"planned"}'}}
        rounds = [
            fake_llm_round(tool_calls=[call]),      # 第一轮：要调工具
            fake_llm_round(content="你有 1 条计划中的任务：写周报"),  # 第二轮：正文
        ]
        state = {"i": 0}

        async def round_router(config, messages, tools, out, thinking_enabled=True):
            gen = rounds[state["i"]]
            state["i"] += 1
            async for ev in gen(config, messages, tools, out):
                yield ev

        p1, p2, p3, p4 = self._patches(round_router)
        with p1, p2, p3, p4, patch.object(agent_loop, "auto_title", AsyncMock()):
            events = await self._collect(
                agent_loop.run_agent_turn(self.db, self.session, "我有哪些计划中的任务？")
            )

        types = [e["type"] for e in events]
        self.assertEqual(types, ["tool_call", "tool_result", "content", "done"])
        # 工具真实执行：结果里应有写周报
        tool_result = events[1]
        self.assertEqual(tool_result["name"], "query_todos")
        self.assertIn("写周报", tool_result["summary"])

        msgs = await derive_messages(self.db, self.session.id)
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["user", "assistant", "tool", "assistant"])
        self.assertEqual(msgs[1]["tool_calls"][0]["function"]["name"], "query_todos")

    async def test_max_rounds_fallback(self):
        call = {"id": "c1", "type": "function",
                "function": {"name": "query_todos", "arguments": "{}"}}

        async def always_tool(config, messages, tools, out, thinking_enabled=True):
            out["tool_calls"] = [call]
            if False:
                yield  # 使其成为异步生成器

        p1, p2, p3, p4 = self._patches(always_tool)
        with p1, p2, p3, p4, patch.object(agent_loop, "auto_title", AsyncMock()):
            events = await self._collect(
                agent_loop.run_agent_turn(self.db, self.session, "循环测试")
            )
        self.assertEqual(events[-1]["type"], "done")
        self.assertIn("最大工具调用轮数", [e.get("delta", "") for e in events if e["type"] == "content"][-1])


if __name__ == "__main__":
    unittest.main()
