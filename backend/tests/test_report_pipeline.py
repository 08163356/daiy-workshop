"""报告管线测试：skill 模板渲染、wake gate、全文直注（不经工具截断）、思维链入日志"""
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.models.prompt_skill import PromptSkill
from app.models.time_log import TimeLog
from app.models.todo import TodoComment, TodoItem
from app.services import agent_loop
from app.services.agent_session import create_session, derive_messages
from app.services.skill_service import seed_builtin_skills


class ReportPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__, TodoItem.__table__,
                      TodoComment.__table__, TimeLog.__table__, UserProfile.__table__,
                      PromptSkill.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        await seed_builtin_skills(self.db)
        await self.db.commit()
        self.session = await create_session(self.db)
        self.config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _collect(self, gen):
        return [ev async for ev in gen]

    def _fake_llm(self, captured: dict):
        async def _gen(config, messages, tools, out, thinking_enabled=True):
            captured["system"] = messages[0]["content"]
            out["thinking"] += "整理今天的记录"
            out["content"] += "日报正文"
            yield {"type": "thinking", "delta": "整理今天的记录"}
            yield {"type": "content", "delta": "日报正文"}
        return _gen

    async def test_daily_report_full_context_injected(self):
        """日报：任务全文（含子任务嵌套/描述）直注 system prompt，不经工具截断"""
        self.db.add(TodoItem(title="父任务", status="completed", quadrant=1,
                             description="这是描述", original_text="原始想法"))
        await self.db.commit()
        parent = (await self.db.execute(select(TodoItem))).scalar_one()
        self.db.add(TodoItem(title="子任务", status="completed", parent_id=parent.id, quadrant=1))
        await self.db.commit()

        captured: dict = {}
        with patch.object(agent_loop, "llm_stream_round", self._fake_llm(captured)), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")), \
             patch.object(agent_loop, "auto_title", AsyncMock()):
            events = await self._collect(agent_loop.run_agent_turn(self.db, self.session, "/日报"))

        types = [e["type"] for e in events]
        self.assertEqual(types[-1], "done")
        self.assertIn("thinking", types)
        # 模板正文被渲染且任务全文直注（父子嵌套结构在里头）
        system = captured["system"]
        self.assertIn("父任务", system)
        self.assertIn("子任务", system)
        self.assertIn("这是描述", system)
        self.assertIn("综合评估", system)  # daily-report skill 的要求文字在
        # 思维链入日志
        result = await self.db.execute(
            select(AgentEvent).where(AgentEvent.event_type == "assistant_message")
        )
        am = result.scalars().all()[-1]
        self.assertEqual(am.payload.get("thinking"), "整理今天的记录")

    async def test_wake_gate_no_records(self):
        """本期无记录：不调 LLM 直接回复（wake gate）"""
        called = {"llm": False}

        async def _gen(config, messages, tools, out, thinking_enabled=True):
            called["llm"] = True
            yield {"type": "content", "delta": "x"}

        with patch.object(agent_loop, "llm_stream_round", _gen), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")):
            events = await self._collect(agent_loop.run_agent_turn(self.db, self.session, "/日报"))
        self.assertFalse(called["llm"])
        self.assertIn("没有任务记录", "".join(e.get("delta", "") for e in events if e["type"] == "content"))

    async def test_skill_disabled_guides_user(self):
        """模板被禁用：提示去设置页启用"""
        skill = (await self.db.execute(
            select(PromptSkill).where(PromptSkill.name == "daily-report")
        )).scalar_one()
        skill.enabled = False
        await self.db.commit()
        events = await self._collect(agent_loop.run_agent_turn(self.db, self.session, "/日报"))
        text = "".join(e.get("delta", "") for e in events if e["type"] == "content")
        self.assertIn("Skill 管理", text)

    async def test_report_messages_projectable(self):
        """报告轮次后投影合法（user + assistant）"""
        self.db.add(TodoItem(title="任务A", status="planned", quadrant=2))
        await self.db.commit()
        with patch.object(agent_loop, "llm_stream_round", self._fake_llm({})), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")), \
             patch.object(agent_loop, "auto_title", AsyncMock()):
            await self._collect(agent_loop.run_agent_turn(self.db, self.session, "/周报"))
        messages = await derive_messages(self.db, self.session.id)
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])


if __name__ == "__main__":
    unittest.main()
