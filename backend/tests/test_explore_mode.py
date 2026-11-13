"""探索模式：/探索 切模式、human3 注入、结束只出报告、确认后才写画像和日记"""
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentEvent, AgentSession
from app.models.ai_config import AIConfig, UserProfile
from app.models.diary import DiaryEntry
from app.models.prompt_skill import PromptSkill
from app.models.todo import TodoItem
from app.services import agent_loop, explore_service
from app.services.agent_session import append_event, create_session, derive_messages
from app.services.skill_service import list_enabled_skills, render_catalog, seed_builtin_skills


def _assessment_json() -> str:
    return json.dumps({
        "metatype_name": "把工作当骨架的人",
        "metatype_desc": "志业很满，其他三块被抽干。",
        "lifestyle_name": "工作吞掉生活",
        "lifestyle_desc": "时间主要在工作上。",
        "quadrants": {
            "mind": {"archetype": "分析者", "phase": "失调", "level_label": "个人化", "strengths": "看得清", "gaps": "停不下来", "lifestyle_impact": "晚上还在转", "false_transformation": ""},
            "body": {"archetype": "间歇练习", "phase": "不确定", "level_label": "个人化", "strengths": "知道要练", "gaps": "一忙就停", "lifestyle_impact": "精力不稳", "false_transformation": ""},
            "spirit": {"archetype": "自己扛", "phase": "失调", "level_label": "个人化", "strengths": "能独处", "gaps": "关系变薄", "lifestyle_impact": "意义变窄", "false_transformation": ""},
            "vocation": {"archetype": "把事做完", "phase": "发现", "level_label": "个人化", "strengths": "能交付", "gaps": "停不下来", "lifestyle_impact": "工作成为默认", "false_transformation": ""},
        },
        "primary_block": "志业抽干身体和精神",
        "unlock": "先把身体练稳",
        "hidden_pattern": "用忙代替选择",
        "cascade_warning": "身体再掉，判断会跟着掉",
        "core_problem": "工作占满之后，没有一块能反过来喂工作",
        "days_30": {"problem": "收工后还在转", "approach": "留一个固定收工动作", "practices": ["收工后走 20 分钟"], "weekly": "周末半天不看工作消息", "metric": "有三天按点走完"},
        "days_90": "让身体练习在忙的一周里还在",
        "months_6_12": "工作不再是唯一的骨架",
        "glitch_note": "先别再加码用 AI 替自己做判断",
        "warnings": ["用更忙来解决忙"],
        "next_action": "今晚收工后走 20 分钟，不带手机",
        "truth": "你不是缺方法，是只剩工作这一块还在转。",
        "profile_updates": [
            {"category": "成长目标", "key": "核心问题", "value": "工作抽干其他三块", "evidence": "用户说下班还在转"},
            {"category": "生活状态", "key": "生活方式", "value": "工作占满", "evidence": "用户说时间主要在工作上"},
        ],
    }, ensure_ascii=False)


class ExploreModeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for table in (
                AgentSession.__table__, AgentEvent.__table__, UserProfile.__table__,
                PromptSkill.__table__, TodoItem.__table__, DiaryEntry.__table__,
            ):
                await conn.run_sync(table.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        await seed_builtin_skills(self.db)
        await self.db.commit()
        self.config = AIConfig(provider="deepseek", model="m", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_explore_prefix_sets_mode_and_strips(self):
        session = await create_session(self.db)
        captured: dict = {}

        async def fake_round(config, messages, tools, out, thinking_enabled=True):
            captured["system"] = messages[0]["content"]
            out["content"] = "当你遇到一个相反的想法，第一反应是什么？"
            yield {"type": "content", "delta": out["content"]}

        with patch.object(agent_loop, "llm_stream_round", fake_round), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")), \
             patch.object(agent_loop, "auto_title", AsyncMock()):
            async for _ in agent_loop.run_agent_turn(self.db, session, "/探索 我想看看自己卡在哪"):
                pass

        await self.db.refresh(session)
        self.assertEqual(session.mode, "explore")
        self.assertIn("心智", captured["system"])
        self.assertIn("一次只问一个问题", captured["system"])
        self.assertNotIn("GROW", captured["system"])
        messages = await derive_messages(self.db, session.id)
        self.assertEqual(messages[0]["content"], "我想看看自己卡在哪")

    async def test_human3_not_in_model_catalog(self):
        skills = await list_enabled_skills(self.db)
        catalog = render_catalog(skills)
        self.assertNotIn("human3", catalog)
        self.assertIn("coach", catalog)

    async def test_finalize_does_not_write_profile_and_flags_conflict(self):
        self.db.add(UserProfile(
            category="成长目标", key="核心问题", value="旧判断", confidence=0.9, source_count=2,
        ))
        await self.db.commit()
        session = AgentSession(mode="explore")
        self.db.add(session)
        await self.db.commit()
        await append_event(self.db, session.id, "user_message", {"content": "下班之后还在想工作，其他事都挤没了"})
        await append_event(self.db, session.id, "assistant_message", {"content": "这件事持续多久了？"})

        resp = httpx.Response(
            200,
            json={"choices": [{"message": {"content": _assessment_json()}}], "usage": {}},
            request=httpx.Request("POST", "https://example.test"),
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=resp)

        with patch("app.services.explore_service.httpx.AsyncClient", return_value=client), \
             patch.object(explore_service, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(explore_service, "get_user_profile_text", AsyncMock(return_value="")):
            result = await explore_service.finalize_explore_session(self.db, session)

        self.assertIn("工作占满之后", result["summary"])
        self.assertEqual(result["core_problem"], "工作占满之后，没有一块能反过来喂工作")
        self.assertTrue(result["profile_updates"][0]["conflict"])
        self.assertEqual(result["profile_updates"][0]["existing_value"], "旧判断")
        self.assertFalse(result["profile_updates"][1]["conflict"])
        rows = (await self.db.execute(select(UserProfile))).scalars().all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].value, "旧判断")

        # 不勾选就不写，包括那条不矛盾的新画像
        skipped = await explore_service.apply_explore_profile(self.db, session, [])
        self.assertEqual(skipped["written"], [])
        rows = (await self.db.execute(select(UserProfile))).scalars().all()
        self.assertEqual(len(rows), 1)

        # 只写新的那条，矛盾项保持原值
        written = await explore_service.apply_explore_profile(self.db, session, [1])
        self.assertEqual(written["written"], [{"category": "生活状态", "key": "生活方式"}])
        rows = (await self.db.execute(select(UserProfile))).scalars().all()
        by_key = {row.key: row for row in rows}
        self.assertEqual(by_key["核心问题"].value, "旧判断")
        self.assertEqual(by_key["生活方式"].value, "工作占满")
        self.assertAlmostEqual(by_key["生活方式"].confidence, 0.65)

        normal = AgentSession(mode="normal")
        self.db.add(normal)
        await self.db.commit()
        with self.assertRaises(ValueError):
            await explore_service.finalize_explore_session(self.db, normal)

    async def test_diary_and_todo_wait_for_confirm(self):
        session = AgentSession(mode="explore", summary="一份已经生成的报告", insights=["核心问题：工作抽干其他"])
        session.followups = [{
            "kind": "explore",
            "core_problem": "工作抽干其他",
            "action_items": ["今晚走 20 分钟"],
            "diary_id": None,
            "profile_updates": [],
            "todo_draft": {"title": "今晚走 20 分钟", "description": "24 小时行动", "category": "life", "quadrant": 2},
            "todo_id": None,
        }]
        self.db.add(session)
        await self.db.commit()

        diary = await explore_service.save_explore_diary(self.db, session)
        entry = await self.db.get(DiaryEntry, diary["diary_id"])
        self.assertEqual(entry.title, "HUMAN 3.0 发展评估")
        self.assertEqual(entry.source, "explore")
        self.assertEqual(entry.key_issues, ["工作抽干其他"])
        again = await explore_service.save_explore_diary(self.db, session)
        self.assertTrue(again["already"])

        todo = await explore_service.create_explore_todo(self.db, session)
        item = await self.db.get(TodoItem, todo["todo_id"])
        self.assertEqual(item.source, "explore")
        self.assertEqual(item.title, "今晚走 20 分钟")

    async def test_coach_sees_explore_core_problem_only(self):
        old = AgentSession(
            mode="explore",
            title="第一次评估",
            summary="完整报告不该整段进教练",
            followups=[{"kind": "explore", "core_problem": "工作占满之后没有回血"}],
        )
        self.db.add(old)
        await self.db.commit()
        session = await create_session(self.db)
        captured: dict = {}

        async def fake_round(config, messages, tools, out, thinking_enabled=True):
            captured["system"] = messages[0]["content"]
            out["content"] = "这次想看清什么？"
            yield {"type": "content", "delta": out["content"]}

        with patch.object(agent_loop, "llm_stream_round", fake_round), \
             patch.object(agent_loop, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(agent_loop, "get_user_profile_text", AsyncMock(return_value="")), \
             patch.object(agent_loop, "auto_title", AsyncMock()):
            async for _ in agent_loop.run_agent_turn(self.db, session, "/教练 我想看看这周的忙"):
                pass

        self.assertIn("工作占满之后没有回血", captured["system"])
        self.assertIn("不要改成四象限问卷", captured["system"])
        self.assertNotIn("完整报告不该整段进教练", captured["system"])


if __name__ == "__main__":
    unittest.main()
