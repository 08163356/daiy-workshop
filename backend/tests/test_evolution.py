"""s7 自进化测试：画像预算淘汰、search_conversations、复盘触发条件、压缩 prune/replace、日报 wake gate"""
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.models.prompt_skill import PromptSkill, SkillCandidate
from app.models.time_log import TimeLog
from app.models.todo import TodoComment, TodoItem
from app.services import agent_loop, review_service, scheduler
from app.services.agent_session import append_event, create_session, derive_messages
from app.services.agent_tools import execute_tool
from app.services.ai_service import _enforce_profile_budget, update_user_profile
from app.services.compaction import _prune, maybe_compact, COMPACT_CHAR_THRESHOLD
from app.services.skill_service import seed_builtin_skills


class ProfileBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(UserProfile.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_budget_prunes_weakest(self):
        """超预算：淘汰置信度最低、最久未更新的条目"""
        # 塞入超预算的低置信度老条目 + 少量高置信度新条目
        for i in range(8):
            self.db.add(UserProfile(
                category="旧闻", key=f"老条目{i}", value="x" * 350,
                confidence=0.1, updated_at=datetime.now() - timedelta(days=100),
            ))
        self.db.add(UserProfile(category="核心", key="重要特征", value="这个必须保留", confidence=0.9))
        await self.db.commit()

        pruned = await _enforce_profile_budget(self.db, budget=500)
        await self.db.commit()
        self.assertGreater(len(pruned), 0)
        from sqlalchemy import select
        remaining = (await self.db.execute(select(UserProfile))).scalars().all()
        keys = [p.key for p in remaining]
        self.assertIn("重要特征", keys)
        self.assertLess(sum(len(p.key) + len(p.value) for p in remaining), 500 + 400)

    async def test_update_profile_calls_budget(self):
        """update_user_profile 收尾会执行预算检查"""
        with patch("app.services.ai_service._enforce_profile_budget", AsyncMock(return_value=[])) as m:
            await update_user_profile(self.db, [{"category": "c", "key": "k", "value": "v"}])
            m.assert_called_once()


class SearchConversationsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        s1 = await create_session(self.db)
        await append_event(self.db, s1.id, "user_message", {"content": "上次我们聊了四象限法则"})
        await append_event(self.db, s1.id, "assistant_message", {"content": "四象限法则是时间管理方法…"})
        s2 = await create_session(self.db)
        await append_event(self.db, s2.id, "user_message", {"content": "今天吃什么"})
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_search_finds_across_sessions(self):
        result = await execute_tool(self.db, "search_conversations", {"keyword": "四象限"})
        self.assertIn("四象限", result["content"])
        self.assertIn("会话#1", result["content"])  # 每会话自适应水合取一条

    async def test_search_no_hit(self):
        result = await execute_tool(self.db, "search_conversations", {"keyword": "不存在的东西xyz"})
        self.assertIn("没有找到", result["content"])


class ReviewTriggerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__, SkillCandidate.__table__):
                await conn.run_sync(t.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_not_enough_messages_no_review(self):
        s = await create_session(self.db)
        await append_event(self.db, s.id, "user_message", {"content": "hi"})
        with patch.object(review_service, "_run_review", AsyncMock()) as m:
            # asyncio.create_task 会被调，但我们拦 run；直接模拟 create_task 到 mock
            import asyncio
            with patch("asyncio.create_task", lambda coro: asyncio.ensure_future(_noop(coro))):
                await review_service.maybe_review_session(self.db, s)
            m.assert_not_called()

    async def test_enough_messages_triggers(self):
        s = await create_session(self.db)
        for i in range(review_service.REVIEW_MIN_USER_MSGS):
            await append_event(self.db, s.id, "user_message", {"content": f"第{i}条"})
        created = []
        import asyncio
        orig_create = asyncio.create_task
        with patch("asyncio.create_task", lambda coro: (created.append(coro), None)[1]):
            await review_service.maybe_review_session(self.db, s)
        self.assertEqual(len(created), 1)
        for c in created:
            c.close()  # 不真跑协程

    async def test_pending_candidate_blocks_duplicate(self):
        s = await create_session(self.db)
        for i in range(review_service.REVIEW_MIN_USER_MSGS):
            await append_event(self.db, s.id, "user_message", {"content": f"第{i}条"})
        self.db.add(SkillCandidate(name="x", title="t", description="d", content="c",
                                   source_session_id=s.id, status="pending"))
        await self.db.commit()
        created = []
        with patch("asyncio.create_task", lambda coro: (created.append(coro), None)[1]):
            await review_service.maybe_review_session(self.db, s)
        self.assertEqual(created, [])


async def _noop(coro):
    coro.close()


class CompactionTests(unittest.IsolatedAsyncioTestCase):
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

    def test_prune_truncates_tool_results(self):
        msgs = [
            {"role": "tool", "content": "x" * 5000, "tool_call_id": "c1"},
            {"role": "assistant", "content": "短"},
            {"role": "assistant", "content": "a" * 4000, "reasoning_content": "r" * 5000},
        ]
        out = _prune(msgs)
        self.assertLess(len(out[0]["content"]), 500)
        self.assertEqual(out[1]["content"], "短")
        self.assertLess(len(out[2]["reasoning_content"]), 500)

    async def test_below_threshold_noop(self):
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "短消息"}]
        out = await maybe_compact(self.db, self.session, messages)
        self.assertEqual(out, messages)

    async def test_over_threshold_llm_checkpoint(self):
        """超阈值且无冷却：LLM checkpoint + surface_op replace，旧事件不再投影"""
        for i in range(20):
            await append_event(self.db, self.session.id, "user_message", {"content": f"长消息{i}" + "长" * 4000})
        messages = await derive_messages(self.db, self.session.id)
        messages = [{"role": "system", "content": "sys"}] + messages

        resp = httpx.Response(
            200,
            json={"choices": [{"message": {"content": "## 目标\n用户在测试压缩。" * 5}}], "usage": {}},
            request=httpx.Request("POST", "https://example.test"),
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=resp)
        config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

        with patch("app.services.compaction.httpx.AsyncClient", return_value=client), \
             patch("app.services.ai_service.get_active_ai_config", AsyncMock(return_value=config)):
            # 也 patch compaction 里的延迟导入目标
            with patch("app.services.compaction.get_active_ai_config", AsyncMock(return_value=config), create=True):
                out = await maybe_compact(self.db, self.session, messages)

        # 投影里旧事件被折叠
        new_msgs = await derive_messages(self.db, self.session.id)
        total_chars = sum(len(m.get("content", "")) for m in new_msgs)
        self.assertLess(total_chars, 4000 * 12)  # 最近10条保留 + 摘要
        summary_msgs = [m for m in new_msgs if "压缩摘要" in (m.get("content") or "")]
        self.assertEqual(len(summary_msgs), 1)
        self.assertEqual(summary_msgs[0]["role"], "user")


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for t in (AgentSession.__table__, AgentEvent.__table__, TodoItem.__table__,
                      TodoComment.__table__, TimeLog.__table__, UserProfile.__table__,
                      PromptSkill.__table__):
                await conn.run_sync(t.create)
        self.db_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.db_factory() as db:
            await seed_builtin_skills(db)
            await db.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_wake_gate_no_records(self):
        """今天无任务记录：不生成不调 LLM"""
        from app.services.task_context import TaskContext

        async def fake_ctx(db, s, e, **kw):
            return TaskContext(items=[], text="")

        # scheduler 里是函数内局部 import，patch 源头模块才有效
        with patch("app.services.task_context.get_task_context", fake_ctx), \
             patch("app.core.database.async_session_maker", self.db_factory):
            generated = await scheduler.generate_scheduled_daily_report()
        self.assertFalse(generated)


if __name__ == "__main__":
    unittest.main()
