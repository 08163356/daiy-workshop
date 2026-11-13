"""Agent 修复回归测试（2026-10-19）

复现的问题：
1. 确认中断时同一消息的其它 tool_calls 永远没有 tool_result → 历史投影缺 tool 消息，
   DeepSeek 400 "insufficient tool messages following tool_calls"
2. add_wellbeing 传了不存在的 source= 参数 → TypeError
3. create_diary/create_note/create_investment 写工具存在且能落库
"""
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.models.diary import DiaryEntry
from app.models.investment import InvestmentReflection
from app.models.note import Note, NoteConcept
from app.models.concept import Concept
from app.models.todo import TodoItem
from app.models.wellbeing import WellbeingEntry
from app.services import agent_loop
from app.services.agent_session import append_event, create_session, derive_messages
from app.services.agent_tools import execute_tool


def fake_round(content: str = "", tool_calls: list | None = None, thinking: str = ""):
    async def _gen(config, messages, tools, out, thinking_enabled=True):
        if thinking:
            out["thinking"] += thinking
        if content:
            out["content"] += content
            yield {"type": "content", "delta": content}
        out["tool_calls"] = tool_calls or []
    return _gen


class DeriveMessagesRepairTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_dangling_tool_call_dropped(self):
        """存量断裂会话：assistant 有两个 tool_calls，只有一个有 tool_result → 只保留有响应的"""
        await append_event(self.db, self.session.id, "user_message", {"content": "hi"})
        await append_event(self.db, self.session.id, "assistant_message", {
            "content": "",
            "thinking": "思考一下",
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "add_wellbeing", "arguments": "{}"}},
                {"id": "c2", "type": "function", "function": {"name": "query_todos", "arguments": "{}"}},
            ],
        })
        await append_event(self.db, self.session.id, "tool_result", {
            "tool_call_id": "c1", "name": "add_wellbeing", "content": "ok",
        })
        messages = await derive_messages(self.db, self.session.id)
        assistant = messages[1]
        # 只剩 c1，c2 被丢弃；c1 的 tool 消息紧随其后 → 对 DeepSeek 合法
        self.assertEqual([c["id"] for c in assistant["tool_calls"]], ["c1"])
        self.assertEqual(messages[2]["role"], "tool")
        self.assertEqual(messages[2]["tool_call_id"], "c1")

    async def test_tool_call_without_thinking_degrades_to_text(self):
        """管线合成的调用没有思维链：降级为纯文本，不带 tool_calls 也不产 tool 消息"""
        await append_event(self.db, self.session.id, "assistant_message", {
            "content": "分析全文",
            "tool_calls": [
                {"id": "s1", "type": "function", "function": {"name": "__save_record", "arguments": "{}"}},
            ],
        })
        await append_event(self.db, self.session.id, "tool_result", {
            "tool_call_id": "s1", "name": "__save_record", "content": "已保存日记",
        })
        messages = await derive_messages(self.db, self.session.id)
        self.assertEqual(len(messages), 1)
        self.assertNotIn("tool_calls", messages[0])
        self.assertIn("已保存日记", messages[0]["content"])

    async def test_all_dangling_drops_tool_calls_key(self):
        """全部 tool_calls 都没响应 → assistant 消息不带 tool_calls 字段"""
        await append_event(self.db, self.session.id, "assistant_message", {
            "content": "我想想",
            "tool_calls": [
                {"id": "c9", "type": "function", "function": {"name": "create_todo", "arguments": "{}"}},
            ],
        })
        messages = await derive_messages(self.db, self.session.id)
        self.assertNotIn("tool_calls", messages[0])
        self.assertEqual(messages[0]["content"], "我想想")


class ConfirmInterruptSkipsRestTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_confirm_interrupt_fills_skipped_results(self):
        """确认中断时，排在确认之后的 tool_calls 自动补占位 tool_result，投影完整"""
        calls = [
            {"id": "c1", "type": "function", "function": {"name": "query_todos", "arguments": "{}"}},
            {"id": "c2", "type": "function", "function": {"name": "create_todo", "arguments": '{"title":"x"}'}},
            {"id": "c3", "type": "function", "function": {"name": "query_diaries", "arguments": "{}"}},
        ]
        with patch.object(agent_loop, "llm_stream_round", fake_round(tool_calls=calls, thinking="先查后记")), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")), \
             patch.object(agent_loop, "auto_title", AsyncMock()):
            async for _ in agent_loop.run_agent_turn(self.db, self.session, "查一下然后记一个"):
                pass

        # c2 触发确认中断；c1 正常执行，c3 应有占位结果
        result = await self.db.execute(
            select(AgentEvent).where(AgentEvent.event_type == "tool_result")
        )
        answered = {ev.payload["tool_call_id"] for ev in result.scalars()}
        self.assertEqual(answered, {"c1", "c3"})

        messages = await derive_messages(self.db, self.session.id)
        assistant = next(m for m in messages if m["role"] == "assistant" and m.get("tool_calls"))
        # 三个调用都有响应（c2 的响应要等确认后才有，但投影只允许有响应的调用）
        self.assertEqual(
            [c["id"] for c in assistant["tool_calls"]],
            ["c1", "c3"],
        )


class WriteToolsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (WellbeingEntry.__table__, DiaryEntry.__table__,
                      Note.__table__, NoteConcept.__table__, Concept.__table__,
                      InvestmentReflection.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_add_wellbeing(self):
        """source_type=agent，occurred_at 是 date"""
        result = await execute_tool(self.db, "add_wellbeing", {
            "entry_type": "gratitude", "content": "朋友陪我打台球", "intensity": 4,
        })
        self.assertIn("已记录感恩", result["content"])
        entry = (await self.db.execute(select(WellbeingEntry))).scalar_one()
        self.assertEqual(entry.source_type, "agent")
        self.assertEqual(entry.intensity, 4)

    async def test_create_diary(self):
        with patch("app.services.wellbeing_ai.extract_candidates_from_diary", AsyncMock()), \
             patch("app.services.question_service.generate_questions_task", AsyncMock()):
            result = await execute_tool(self.db, "create_diary", {
                "content": "今天很充实", "title": "充实的一天",
            })
        self.assertIn("已保存日记", result["content"])
        entry = (await self.db.execute(select(DiaryEntry))).scalar_one()
        self.assertEqual(entry.title, "充实的一天")
        self.assertEqual(entry.content, "今天很充实")

    async def test_create_note(self):
        with patch("app.services.question_service.generate_questions_task", AsyncMock()):
            result = await execute_tool(self.db, "create_note", {
                "title": "原子习惯读后感", "content": "习惯的复利效应",
            })
        self.assertIn("已保存", result["content"])
        note = (await self.db.execute(select(Note))).scalar_one()
        self.assertEqual(note.source_type, "self")  # 不指定类型时默认随笔
        self.assertTrue(note.filename)
        self.assertTrue(note.file_hash)

    async def test_create_investment(self):
        result = await execute_tool(self.db, "create_investment", {
            "content": "今天加仓了纳指，逻辑是...", "title": "加仓记录",
        })
        self.assertIn("已保存投资反思", result["content"])
        entry = (await self.db.execute(select(InvestmentReflection))).scalar_one()
        self.assertEqual(entry.title, "加仓记录")


class RecordPipelineTests(unittest.IsolatedAsyncioTestCase):
    """ /日记 等记录管线：分析流式透传 → 确认卡 → 保存落库（含分析） """

    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__, DiaryEntry.__table__,
                      UserProfile.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.session = await create_session(self.db)
        self.config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    @staticmethod
    async def _fake_stream(db, system_type, content, config=None, **kw):
        """模拟 call_ai_stream：思维链 + 两段 chunk + done（含结构化数据）"""
        yield 'data: {"type": "reasoning", "content": "用户写了条短日记"}\n\n'
        yield 'data: {"type": "chunk", "content": "分析上半。"}\n\n'
        yield 'data: {"type": "chunk", "content": "分析下半。"}\n\n'
        yield 'data: {"type": "done", "result": {"analysis_markdown": "分析上半。分析下半。", "structured_data": {"mood": "开心", "tags": ["测试"]}}}\n\n'

    async def test_pipeline_round_degrades_when_history_lacks_thinking(self):
        """存量无思维链的会话：后续轮次自动禁用思维链（防 400），消息正常投影"""
        await append_event(self.db, self.session.id, "user_message", {"content": "旧消息"})
        await append_event(self.db, self.session.id, "assistant_message", {"content": "旧回复（无思维链）"})
        captured: dict = {}

        async def capture_round(config, messages, tools, out, thinking_enabled=True):
            captured["thinking_enabled"] = thinking_enabled
            out["content"] = "好的"
            yield {"type": "content", "delta": "好的"}

        with patch.object(agent_loop, "llm_stream_round", capture_round), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")), \
             patch.object(agent_loop, "auto_title", AsyncMock()):
            async for _ in agent_loop.run_agent_turn(self.db, self.session, "继续"):
                pass
        self.assertFalse(captured["thinking_enabled"])

    async def test_diary_pipeline_full_flow(self):
        with patch("app.services.ai_service.call_ai_stream", self._fake_stream), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")), \
             patch.object(agent_loop, "auto_title", AsyncMock()), \
             patch("app.services.wellbeing_ai.extract_candidates_from_diary", AsyncMock()), \
             patch("app.services.question_service.generate_questions_task", AsyncMock()):
            events = [ev async for ev in agent_loop.run_agent_turn(self.db, self.session, "/日记 今天很开心")]

        types = [e["type"] for e in events]
        # 思维链透传 + 分析内容流式透传 + 确认卡 + done
        self.assertIn("thinking", types)
        self.assertIn("content", types)
        self.assertIn("confirm_required", types)
        self.assertEqual(types[-1], "done")
        confirm = next(e for e in events if e["type"] == "confirm_required")
        self.assertEqual(confirm["name"], "__save_record")

        # 思维链入事件日志（投影回传 reasoning_content 的前提）
        result = await self.db.execute(
            select(AgentEvent).where(AgentEvent.event_type == "assistant_message")
        )
        am = result.scalar_one()
        self.assertEqual(am.payload.get("thinking"), "用户写了条短日记")

        # 确认后保存，日记含 AI 分析和结构化字段
        with patch("app.services.wellbeing_ai.extract_candidates_from_diary", AsyncMock()), \
             patch("app.services.question_service.generate_questions_task", AsyncMock()), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")), \
             patch.object(agent_loop, "llm_stream_round", fake_round(content="已帮你保存好啦")):
            resume_events = [ev async for ev in agent_loop.resume_after_confirm(self.db, self.session, True)]

        self.assertEqual(resume_events[0]["type"], "tool_result")
        entry = (await self.db.execute(select(DiaryEntry))).scalar_one()
        self.assertEqual(entry.content, "今天很开心")
        self.assertEqual(entry.ai_analysis, "分析上半。分析下半。")
        self.assertEqual(entry.mood, "开心")
        self.assertEqual(entry.tags, ["测试"])

    async def test_pipeline_ai_failure_offers_direct_save(self):
        """AI 挂了：提示降级，确认卡仍可保存原文"""
        async def failing_stream(db, system_type, content, config=None, **kw):
            raise RuntimeError("AI 服务不可用")
            yield  # 使其成为生成器

        with patch("app.services.ai_service.call_ai_stream", failing_stream), \
             patch.object(agent_loop, "auto_title", AsyncMock()):
            events = [ev async for ev in agent_loop.run_agent_turn(self.db, self.session, "/日记 原文内容")]

        types = [e["type"] for e in events]
        self.assertIn("confirm_required", types)
        self.assertEqual(types[-1], "done")
        # 事件里 confirm_pending 的 analysis 应为空
        result = await self.db.execute(
            select(AgentEvent).where(AgentEvent.event_type == "confirm_pending")
        )
        pending = result.scalar_one()
        self.assertEqual(pending.payload["args"]["analysis"], "")
        self.assertEqual(pending.payload["args"]["content"], "原文内容")


class DelayedConfirmOrderingTests(unittest.IsolatedAsyncioTestCase):
    """用户聊了几轮才点确认：tool 消息在投影中必须紧跟其 assistant 消息"""

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

    async def test_tool_result_reordered_after_its_assistant(self):
        await append_event(self.db, self.session.id, "user_message", {"content": "/日记 内容"})
        await append_event(self.db, self.session.id, "assistant_message", {
            "content": "分析…",
            "thinking": "用户在存日记",
            "tool_calls": [{"id": "s1", "type": "function", "function": {"name": "__save_record", "arguments": "{}"}}],
        })
        # 用户继续聊了两轮才点确认
        await append_event(self.db, self.session.id, "user_message", {"content": "先聊聊"})
        await append_event(self.db, self.session.id, "assistant_message", {"content": "好啊"})
        await append_event(self.db, self.session.id, "tool_result", {
            "tool_call_id": "s1", "name": "__save_record", "content": "已保存",
        })
        messages = await derive_messages(self.db, self.session.id)
        roles = [m["role"] for m in messages]
        # tool 消息归位到其 assistant 之后，而不是日志末尾
        self.assertEqual(roles, ["user", "assistant", "tool", "user", "assistant"])
        self.assertEqual(messages[2]["tool_call_id"], "s1")


if __name__ == "__main__":
    unittest.main()
