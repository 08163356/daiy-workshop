"""search_blog：本机构造小索引，命中标题 / 摘录，空格分词 AND。"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services import blog_search
from app.services.agent_tools import execute_tool, get_tool_schemas


def _write_index(dir_path: Path) -> Path:
    dest = dir_path / "blog-index.json"
    dest.write_text(
        json.dumps(
            {
                "host": "https://blog.example.com",
                "count": 3,
                "pages": [
                    {
                        "title": "onlyoffice分段加载",
                        "permalink": "/pages/0f12f3/",
                        "url": "https://blog.example.com/pages/0f12f3/",
                        "categories": ["技术", "onlyOffice"],
                        "tags": ["OnlyOffice"],
                        "excerpt": "表格很大时按可视区域分段拉取单元格。",
                    },
                    {
                        "title": "页面性能优化 前端加载时序分析",
                        "permalink": "/pages/329ee7/",
                        "url": "https://blog.example.com/pages/329ee7/",
                        "categories": ["性能优化"],
                        "tags": [],
                        "excerpt": "window.open 打开新页面时出现白屏。",
                    },
                    {
                        "title": "OnlyOffice 实践索引",
                        "permalink": "/pages/oo-index/",
                        "url": "https://blog.example.com/pages/oo-index/",
                        "categories": ["技术"],
                        "tags": ["OnlyOffice"],
                        "excerpt": "公开站先看环境搭建、Docker 编译和性能对比。",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return dest


class BlogSearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.index = _write_index(Path(self.tmp.name))
        self._old = os.environ.get("BLOG_INDEX_PATH")
        os.environ["BLOG_INDEX_PATH"] = str(self.index)
        blog_search.reset_cache()

    def tearDown(self):
        blog_search.reset_cache()
        if self._old is None:
            os.environ.pop("BLOG_INDEX_PATH", None)
        else:
            os.environ["BLOG_INDEX_PATH"] = self._old
        self.tmp.cleanup()

    def test_title_hit(self):
        hits = blog_search.search_blog("分段加载")
        self.assertEqual(hits[0]["permalink"], "/pages/0f12f3/")
        self.assertIn("https://blog.example.com/pages/0f12f3/", hits[0]["url"])

    def test_excerpt_and_tokens(self):
        hits = blog_search.search_blog("OnlyOffice 分段")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["title"], "onlyoffice分段加载")
        none = blog_search.search_blog("OnlyOffice 不存在的词xyz")
        self.assertEqual(none, [])

    async def test_agent_tool(self):
        names = {t["function"]["name"] for t in get_tool_schemas()}
        self.assertIn("search_blog", names)
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        db = async_sessionmaker(engine, expire_on_commit=False)()
        try:
            result = await execute_tool(db, "search_blog", {"keyword": "OnlyOffice 分段加载"})
            self.assertNotIn("error", result)
            self.assertIn("/pages/0f12f3/", result["content"])
            self.assertIn("onlyoffice分段加载", result["content"])
        finally:
            await db.close()
            await engine.dispose()
