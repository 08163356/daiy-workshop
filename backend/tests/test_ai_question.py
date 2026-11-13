"""AI 提问队列测试

功能契约：
- 日记/笔记保存后异步判断是否有值得澄清的点：有才生成 1-2 条入队，没有不生成
- 回答后沉淀到用户画像（update_user_profile 收到问答证据）
- 可忽略；待答列表按时间倒序
- AI 失败/内容太短时不生成、不抛异常（不阻断保存主流程）
"""
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.ai_config import AIConfig, UserProfile
from app.models.ai_question import AIQuestion
from app.services import question_service


def _ai_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 50}},
        request=httpx.Request("POST", "https://example.test"),
    )


class AIQuestionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(AIQuestion.__table__.create)
            await conn.run_sync(UserProfile.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.config = AIConfig(provider="deepseek", model="deepseek-v4-pro", api_key="k", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def _mock_ai(self, content: str):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=_ai_response(content))
        return client

    async def test_generate_questions_when_ambiguous(self):
        client = self._mock_ai('{"questions":[{"question":"你说的「那个项目」是指什么？","context":"日记提到项目但没说明"}]}')
        with patch.object(question_service, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch("httpx.AsyncClient", return_value=client):
            qs = await question_service.maybe_generate_questions(
                self.db, "diary", 1, "今天推进了那个项目，感觉还行，但有些地方没想清楚，下午开了个会也没完全对齐，明天再看看怎么办。"
            )
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0].status, "pending")
        self.assertEqual(qs[0].source_type, "diary")
        self.assertEqual(qs[0].source_id, 1)

    async def test_no_question_when_content_clear(self):
        client = self._mock_ai('{"questions":[]}')
        with patch.object(question_service, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch("httpx.AsyncClient", return_value=client):
            qs = await question_service.maybe_generate_questions(
                self.db, "diary", 1, "今天完成了日报系统的部署，一切顺利，很有成就感。"
            )
        self.assertEqual(qs, [])

    async def test_short_content_skips_ai_call(self):
        # 内容太短不值得提问，不应调用 AI
        with patch.object(question_service, "get_active_ai_config", AsyncMock(return_value=self.config)) as cfg:
            qs = await question_service.maybe_generate_questions(self.db, "diary", 1, "挺好")
        self.assertEqual(qs, [])
        cfg.assert_not_called()

    async def test_ai_failure_does_not_raise(self):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(side_effect=httpx.TimeoutException("boom"))
        with patch.object(question_service, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch("httpx.AsyncClient", return_value=client):
            qs = await question_service.maybe_generate_questions(self.db, "diary", 1, "一段足够长的日记内容，用来测试 AI 调用失败时不会抛出异常中断主流程。")
        self.assertEqual(qs, [])

    async def test_answer_question_sinks_to_profile(self):
        q = AIQuestion(source_type="diary", source_id=1, question="那个项目指什么？", status="pending")
        self.db.add(q)
        await self.db.commit()
        # 新路径：回答先经 AI 提炼再写画像（synthesize 失败也不影响答案保存）
        with patch("app.services.clarify_service.synthesize_answers_to_profile", AsyncMock(return_value=[])) as syn:
            saved = await question_service.answer_question(self.db, q.id, "指 daily 系统的开发")
        self.assertEqual(saved.status, "answered")
        self.assertEqual(saved.answer, "指 daily 系统的开发")
        self.assertIsNotNone(saved.answered_at)
        syn.assert_awaited_once()
        qa = syn.call_args.args[2]
        self.assertEqual(qa[0]["answer"], "指 daily 系统的开发")

    async def test_dismiss_question(self):
        q = AIQuestion(source_type="diary", question="问题X", status="pending")
        self.db.add(q)
        await self.db.commit()
        saved = await question_service.dismiss_question(self.db, q.id)
        self.assertEqual(saved.status, "dismissed")

    async def test_list_pending_only(self):
        self.db.add(AIQuestion(source_type="diary", question="待答", status="pending"))
        self.db.add(AIQuestion(source_type="diary", question="已答", status="answered", answer="x"))
        await self.db.commit()
        pending = await question_service.list_questions(self.db, status="pending")
        self.assertEqual([q.question for q in pending], ["待答"])

    async def test_answer_pending_only(self):
        q = AIQuestion(source_type="diary", question="已忽略", status="dismissed")
        self.db.add(q)
        await self.db.commit()
        with self.assertRaises(ValueError):
            await question_service.answer_question(self.db, q.id, "迟到地回答")


if __name__ == "__main__":
    unittest.main()
