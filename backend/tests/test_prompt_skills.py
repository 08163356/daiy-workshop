"""PromptSkill 基座测试：seed 幂等、目录渲染、占位符、候选审核"""
import unittest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.prompt_skill import PromptSkill, SkillCandidate
from app.services import skill_service


class SkillBaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(PromptSkill.__table__.create)
            await conn.run_sync(SkillCandidate.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_seed_idempotent(self):
        """seed 两次不重复，且不覆盖用户修改"""
        n1 = await skill_service.seed_builtin_skills(self.db)
        await self.db.commit()
        self.assertEqual(n1, len(skill_service.BUILTIN_SKILLS))

        # 用户改了日报模板
        skill = await skill_service.get_skill(self.db, "daily-report")
        skill.content = "用户自定义内容"
        await self.db.commit()

        n2 = await skill_service.seed_builtin_skills(self.db)
        await self.db.commit()
        self.assertEqual(n2, 0)
        skill2 = await skill_service.get_skill(self.db, "daily-report")
        self.assertEqual(skill2.content, "用户自定义内容")

    async def test_catalog_only_has_name_and_desc(self):
        """目录注入渐进式披露：只有 name+description，正文不进目录；人格/管线绑定不进目录"""
        await skill_service.seed_builtin_skills(self.db)
        await self.db.commit()
        skills = await skill_service.list_enabled_skills(self.db)
        catalog = skill_service.render_catalog(skills)
        self.assertIn("coach", catalog)
        self.assertIn("多提问少说教", catalog)  # description 里
        self.assertNotIn("日报", catalog)  # daily-report 绑了管线不出现在目录
        self.assertNotIn("persona-buddy", catalog)  # 人格不进模型目录
        self.assertNotIn("对话原则", catalog)  # 正文不进目录

    async def test_render_content_placeholders(self):
        skill = PromptSkill(
            name="t", title="t", description="d",
            content="今天是 {today}，画像：{user_profile}",
        )
        out = skill_service.render_content(skill, user_profile="喜欢简洁")
        self.assertIn("画像：喜欢简洁", out)
        self.assertNotIn("{today}", out)

    async def test_candidate_approve_create_and_patch(self):
        await skill_service.seed_builtin_skills(self.db)
        await self.db.commit()

        # create 型候选
        c1 = SkillCandidate(name="meeting-notes", title="会议纪要", description="整理会议纪要", content="正文")
        self.db.add(c1)
        # patch 型候选（改 coach）
        c2 = SkillCandidate(name="coach-patch", title="教练改进", description="更好的教练", content="新正文",
                            action="patch", target_name="coach")
        self.db.add(c2)
        await self.db.commit()

        old_rev = (await skill_service.get_skill(self.db, "coach")).revision
        s1 = await skill_service.approve_candidate(self.db, c1.id)
        self.assertEqual(s1.name, "meeting-notes")
        s2 = await skill_service.approve_candidate(self.db, c2.id)
        self.assertEqual(s2.content, "新正文")
        self.assertEqual(s2.revision, old_rev + 1)

        # 重复审核报错
        with self.assertRaises(ValueError):
            await skill_service.approve_candidate(self.db, c1.id)

    async def test_candidate_reject(self):
        c = SkillCandidate(name="x", title="x", description="d", content="c")
        self.db.add(c)
        await self.db.commit()
        await skill_service.reject_candidate(self.db, c.id)
        await self.db.commit()
        result = await self.db.execute(select(SkillCandidate).where(SkillCandidate.status == "pending"))
        self.assertEqual(list(result.scalars()), [])


if __name__ == "__main__":
    unittest.main()
