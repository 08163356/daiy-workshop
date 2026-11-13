"""todo_evaluate prompt 防误判回归测试

复现的问题：刚新建的任务被评估说"与已有待办重复"，且凭空判断"属于某系统的功能修复"。
"""
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.ai_config import AIConfig
from app.models.todo import TodoItem
from app.services import todo_service


class TodoEvaluatePromptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(TodoItem.__table__.create)
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.db.add(TodoItem(title="ugc编辑有bug，提交后重进没清理草稿", status="planned"))
        await self.db.commit()
        self.config = AIConfig(provider="deepseek", model="deepseek-v4-pro", api_key="test-key", temperature=0.7, max_tokens=8192)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def _capture_prompt(self) -> str:
        response = httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"items":[{"original_text":"x","ai_category":"actionable","title":"t","quadrant":2,"urgency":3,"importance":3}],"summary":"s"}'}}], "usage": {"total_tokens": 10}},
            request=httpx.Request("POST", "https://example.test"),
        )
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=response)
        with patch.object(todo_service, "get_active_ai_config", AsyncMock(return_value=self.config)), \
             patch.object(todo_service, "get_user_profile_text", AsyncMock(return_value="")), \
             patch("httpx.AsyncClient", return_value=client):
            await todo_service.evaluate_batch_input(self.db, "修复一个播放器崩溃问题")
        return json.dumps(client.post.call_args.kwargs["json"]["messages"], ensure_ascii=False)

    async def test_prompt_does_not_prompt_for_duplicates(self):
        prompt = await self._capture_prompt()
        # 旧的引导语会鼓励 AI 主动找重复，必须移除
        self.assertNotIn("有关联或冲突，请在评估中说明", prompt)
        # 新约束：默认视为新事项，只有高度相似才提示"可能相关"
        self.assertIn("默认把用户输入视为新事项", prompt)
        self.assertIn("若非同一事项请忽略", prompt)

    async def test_prompt_constrains_category_and_attribution(self):
        prompt = await self._capture_prompt()
        # 分类必须严格从枚举中选
        self.assertIn("只能从", prompt)
        # 评估文字不得凭空推断归属（如"属于XX系统的功能修复"）
        self.assertIn("不得推断任务归属", prompt)


if __name__ == "__main__":
    unittest.main()
