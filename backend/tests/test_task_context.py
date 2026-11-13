import json
import unittest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.ai_config import AIConfig
from app.models.todo import TodoItem, TodoComment
from app.models.time_log import TimeLog
from app.services import ai_service, todo_service


class TaskContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            for table in (TodoItem.__table__, TodoComment.__table__, TimeLog.__table__):
                await conn.run_sync(table.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.config = AIConfig(provider="deepseek", model="deepseek-v4-pro", api_key="test-key", temperature=0.7, max_tokens=8192)
        self.day = date(2026, 10, 16)
        self.parent = TodoItem(title="完成交付", description="检查协议编辑计划", original_text="原始想法：先核对数据", status="completed", scheduled_date=self.day, completed_at=datetime(2026, 10, 16, 14), created_at=datetime(2026, 9, 1), ai_evaluation="禁止读取的AI分析", ai_answer="禁止读取的AI回答", completion_notes=[{"content": "实际完成部署", "timestamp": "2026-10-16T14:00:00"}])
        self.db.add(self.parent)
        await self.db.flush()
        self.child = TodoItem(title="子任务核对数据", parent_id=self.parent.id, status="completed", created_at=datetime(2026, 9, 1), completed_at=datetime(2026, 10, 16, 13))
        self.plan = TodoItem(title="跨天计划", status="planned", scheduled_date=date(2026, 10, 15), scheduled_end_date=date(2026, 10, 18), created_at=datetime(2026, 9, 1))
        self.old = TodoItem(title="过期无关任务", status="completed", scheduled_date=date(2026, 9, 1), completed_at=datetime(2026, 9, 1), created_at=datetime(2026, 9, 1))
        self.timed = TodoItem(title="今天实际计时任务", status="in_progress", created_at=datetime(2026, 9, 1))
        self.db.add_all([self.child, self.plan, self.old, self.timed])
        await self.db.flush()
        self.db.add(TimeLog(todo_id=self.timed.id, start_time=datetime(2026, 10, 16, 9), end_time=datetime(2026, 10, 16, 10), duration_seconds=3600))
        self.db.add(TodoComment(todo_id=self.parent.id, content="补充想法：下一步检查兼容性", created_at=datetime(2026, 10, 16, 15)))
        await self.db.commit()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def context_module(self):
        from importlib.util import find_spec
        self.assertIsNotNone(find_spec("app.services.task_context"), "缺少共享的任务原始记录上下文")
        from app.services import task_context
        return task_context

    def test_selected_day_and_explicit_today(self):
        resolve = self.context_module().resolve_question_scope
        selected = date(2026, 9, 10)
        self.assertEqual(resolve("总结这天做了什么", selected, self.day).start_date, selected)
        self.assertEqual(resolve("总结今天做了什么", selected, self.day).start_date, self.day)

    def test_week_month_and_year_boundaries(self):
        resolve = self.context_module().resolve_question_scope
        scope = resolve("总结本周做了什么", date(2026, 10, 14), self.day)
        self.assertEqual((scope.start_date, scope.end_date), (date(2026, 10, 12), date(2026, 10, 18)))
        scope = resolve("回顾本月", date(2024, 2, 20), self.day)
        self.assertEqual(scope.end_date, date(2024, 2, 29))
        scope = resolve("总结上月", date(2026, 1, 1), self.day)
        self.assertEqual((scope.start_date, scope.end_date), (date(2025, 12, 1), date(2025, 12, 31)))

    def test_daily_weekly_recent_keywords(self):
        # 提问快捷按钮：日报/周报/近一周/近一个月
        resolve = self.context_module().resolve_question_scope
        scope = resolve("生成本周周报", date(2026, 10, 14), self.day)  # 周三
        self.assertEqual(scope.intent, "summary")
        self.assertEqual((scope.start_date, scope.end_date), (date(2026, 10, 12), date(2026, 10, 18)))
        scope = resolve("总结近一周", self.day, self.day)
        self.assertEqual((scope.start_date, scope.end_date), (date(2026, 10, 10), date(2026, 10, 16)))
        scope = resolve("看看近一个月做了什么", self.day, self.day)
        self.assertEqual((scope.start_date, scope.end_date), (date(2026, 9, 17), date(2026, 10, 16)))
        scope = resolve("生成日报", self.day, self.day)
        self.assertEqual(scope.intent, "summary")
        self.assertEqual((scope.start_date, scope.end_date), (self.day, self.day))

    def test_search_stays_global_without_time_words(self):
        scope = self.context_module().resolve_question_scope("查找协议相关的任务", date(2026, 9, 10), self.day)
        self.assertEqual(scope.intent, "search")
        self.assertIsNone(scope.start_date)

    async def test_context_includes_raw_records_not_ai_analysis(self):
        context = await self.context_module().get_task_context(self.db, self.day, self.day)
        text = context.text
        for evidence in ("检查协议编辑计划", "原始想法", "实际完成部署", "子任务核对数据", "跨天计划", "今天实际计时任务", "下一步检查兼容性"):
            self.assertIn(evidence, text)
        for excluded in ("禁止读取的AI分析", "禁止读取的AI回答", "过期无关任务"):
            self.assertNotIn(excluded, text)
        self.assertIn("计划不等于完成", text)
        self.assertIn("2026-10-16", text)

    async def test_future_comments_are_not_used_for_past_summary(self):
        self.db.add(TodoComment(todo_id=self.parent.id, content="下个月才发生的补充", created_at=datetime(2026, 11, 1)))
        await self.db.commit()
        context = await self.context_module().get_task_context(self.db, self.day, self.day)
        self.assertNotIn("下个月才发生的补充", context.text)

    def test_invalid_and_oversized_ranges_are_rejected(self):
        module = self.context_module()
        with self.assertRaises(ValueError):
            module.resolve_question_scope("总结2026-02-30", self.day)
        with self.assertRaises(ValueError):
            module.validate_question_scope(module.QuestionScope("summary", date(2024, 1, 1), self.day))

    async def test_task_limit_is_disclosed(self):
        context = await self.context_module().get_task_context(self.db, self.day, self.day, limit=1)
        self.assertTrue(context.truncated)
        self.assertIn("部分记录", context.text)

    async def test_old_task_with_only_new_comment_is_included(self):
        self.db.add(TodoComment(todo_id=self.old.id, content="今天完成了兼容性检查", created_at=datetime(2026, 10, 16, 15)))
        await self.db.commit()
        context = await self.context_module().get_task_context(self.db, self.day, self.day)
        self.assertIn("今天完成了兼容性检查", context.text)

    async def test_active_timer_across_midnight_is_included(self):
        self.db.add(TimeLog(todo_id=self.old.id, start_time=datetime(2026, 10, 15, 23, 50)))
        await self.db.commit()
        context = await self.context_module().get_task_context(self.db, self.day, self.day, now=datetime(2026, 10, 16, 0, 20))
        self.assertIn("本期计时秒数", context.text)
        self.assertIn("1200", context.text)
        self.assertIn("过期无关任务", context.text)

    async def test_large_record_does_not_drop_other_tasks(self):
        self.timed.description = "长内容" * 40000
        await self.db.commit()
        context = await self.context_module().get_task_context(self.db, self.day, self.day)
        self.assertIn("完成交付", context.text)
        self.assertIn("今天实际计时任务", context.text)
        self.assertTrue(context.truncated)

    async def test_children_endpoint_returns_subtasks_of_old_parent(self):
        # 复现线上bug：详情弹窗依赖"最新50条父任务"列表导致老任务子任务查空
        from app.api.todo import get_todo_children
        children = await get_todo_children(self.parent.id, self.db)
        self.assertEqual([c.title for c in children], ["子任务核对数据"])

    async def test_empty_period_is_explicit(self):
        context = await self.context_module().get_task_context(self.db, date(2030, 1, 1), date(2030, 1, 1))
        self.assertEqual(context.items, [])
        self.assertIn("没有", context.text)

    async def test_summary_includes_completed_and_deduplicates_matched_ids(self):
        reply = {"choices": [{"message": {"content": json.dumps({"answer": "已完成交付，跨天计划尚未完成", "matched_ids": [self.parent.id, self.parent.id, 999999]})}}], "usage": {"total_tokens": 12}}
        response = httpx.Response(200, json=reply, request=httpx.Request("POST", "https://example.test"))
        post = AsyncMock(return_value=response)
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = post
        with patch.object(todo_service, "get_active_ai_config", AsyncMock(return_value=self.config)), patch.object(todo_service, "get_user_profile_text", AsyncMock(return_value="")), patch("httpx.AsyncClient", return_value=client):
            result = await todo_service.ask_todos(self.db, "总结这天做了什么", reference_date=self.day)
        self.assertEqual([t.id for t in result["matched_todos"]], [self.parent.id])
        messages = post.call_args.kwargs["json"]["messages"]
        prompt = json.dumps(messages, ensure_ascii=False)
        self.assertIn("检查协议编辑计划", prompt)
        self.assertNotIn("禁止读取的AI分析", prompt)
        self.assertEqual(result["start_date"], self.day)

    async def test_diary_nonstream_has_daily_context(self):
        response = httpx.Response(200, json={"choices": [{"message": {"content": '{"analysis_markdown":"日记分析"}'}}]}, request=httpx.Request("POST", "https://example.test"))
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response
        with patch.object(ai_service, "get_user_profile_text", AsyncMock(return_value="")), patch("httpx.AsyncClient", return_value=client):
            await ai_service.call_ai(self.db, "diary", "今天有点累", self.config, diary_date=self.day)
        prompt = json.dumps(client.post.call_args.kwargs["json"]["messages"], ensure_ascii=False)
        self.assertIn("完成交付", prompt)
        self.assertIn("计划不等于完成", prompt)
        self.assertNotIn("禁止读取的AI分析", prompt)

    async def test_diary_stream_and_extraction_share_context(self):
        stream_response = AsyncMock()
        stream_response.raise_for_status = unittest.mock.Mock()
        async def lines():
            yield 'data: {"choices":[{"delta":{"content":"日记分析"}}]}'
            yield 'data: [DONE]'
        stream_response.aiter_lines = lines
        stream_cm = AsyncMock()
        stream_cm.__aenter__.return_value = stream_response
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.stream = unittest.mock.Mock(return_value=stream_cm)
        client.post.return_value = httpx.Response(200, json={"choices": [{"message": {"content": '{"structured_data":{},"profile_updates":[]}'}}]}, request=httpx.Request("POST", "https://example.test"))
        with patch.object(ai_service, "get_user_profile_text", AsyncMock(return_value="")), patch("httpx.AsyncClient", return_value=client):
            events = [event async for event in ai_service.call_ai_stream(self.db, "diary", "今天有点累", self.config, diary_date=self.day)]
        self.assertTrue(any('"type": "done"' in event for event in events))
        for request in (client.stream.call_args, client.post.call_args):
            prompt = json.dumps(request.kwargs["json"]["messages"], ensure_ascii=False)
            self.assertIn("完成交付", prompt)
            self.assertNotIn("禁止读取的AI分析", prompt)


if __name__ == "__main__":
    unittest.main()
