"""Skill 调用链测试：use_skill 工具 + /skill: 前缀显式路由"""
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.models.prompt_skill import PromptSkill
from app.services.agent_loop import run_agent_turn
from app.services.agent_session import create_session, get_session_events
from app.services.agent_tools import execute_tool


class UseSkillToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (PromptSkill.__table__, UserProfile.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.db.add(PromptSkill(
            name="morning-plan", title="晨间规划", description="每天早上规划任务",
            content="你是规划师。画像：{user_profile}", enabled=True, model_invocable=True,
        ))
        self.db.add(PromptSkill(
            name="off-skill", title="停用", description="x", content="x", enabled=False,
        ))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_loads_content_and_counts(self):
        with patch("app.services.ai_service.get_user_profile_text", AsyncMock(return_value="画像文本")):
            result = await execute_tool(self.db, "use_skill", {"name": "morning-plan"})
        self.assertIn("晨间规划", result["content"])
        self.assertIn("你是规划师", result["content"])
        skill = (await self.db.execute(select(PromptSkill).where(PromptSkill.name == "morning-plan"))).scalar_one()
        self.assertEqual(skill.use_count, 1)

    async def test_disabled_skill_rejected(self):
        result = await execute_tool(self.db, "use_skill", {"name": "off-skill"})
        self.assertIn("error", result)
        self.assertIn("未启用", result["error"])

    async def test_unknown_skill_rejected(self):
        result = await execute_tool(self.db, "use_skill", {"name": "not-exist"})
        self.assertIn("error", result)
        self.assertIn("不存在", result["error"])


class ExplicitSkillPrefixTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (PromptSkill.__table__, AgentSession.__table__, AgentEvent.__table__,
                      UserProfile.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.db.add(PromptSkill(
            name="coach-pro", title="教练Pro", description="x", content="技能正文内容",
            enabled=True, user_invocable=True,
        ))
        await self.db.commit()
        self.session = await create_session(self.db)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _collect(self, gen):
        return [ev async for ev in gen]

    async def test_unknown_skill_gives_notice(self):
        events = await self._collect(run_agent_turn(self.db, self.session, "/skill:not-exist 你好"))
        contents = [e for e in events if e["type"] == "content"]
        self.assertTrue(any("不存在" in e["delta"] for e in contents))

    async def test_known_skill_injects_into_system(self):
        """/skill:coach-pro → 技能正文注入 system 段，走正常对话循环"""
        captured = {}

        async def fake_rounds(db, session, messages, config, tools):
            captured["system"] = messages[0]["content"]
            yield {"type": "content", "delta": "ok"}
            yield {"type": "done", "session_id": session.id}

        config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)
        with patch("app.services.agent_loop._run_rounds", side_effect=fake_rounds), \
             patch("app.services.agent_loop.get_active_ai_config", AsyncMock(return_value=config)), \
             patch("app.services.compaction.maybe_compact", AsyncMock(side_effect=lambda db, s, m: m)), \
             patch("app.services.ai_service.get_user_profile_text", AsyncMock(return_value="")):
            await self._collect(run_agent_turn(self.db, self.session, "/skill:coach-pro 帮我开始"))

        self.assertIn("技能正文内容", captured.get("system", ""))
        self.assertIn("用户本轮指定技能", captured.get("system", ""))
        # 技能使用计数 +1
        skill = (await self.db.execute(select(PromptSkill).where(PromptSkill.name == "coach-pro"))).scalar_one()
        self.assertEqual(skill.use_count, 1)


if __name__ == "__main__":
    unittest.main()
