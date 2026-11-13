"""search_interview：临时目录构造 seed + knowledge，关键词 AND 命中。"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from app.services import interview_search
from app.services.agent_tools import get_tool_schemas


def _write_fixture(root: Path) -> None:
    seed = root / "seed_data"
    knowledge = root / "interview_knowledge"
    seed.mkdir(parents=True)
    knowledge.mkdir(parents=True)
    (seed / "projects.json").write_text(
        json.dumps(
            [
                {
                    "id": "sgame-tools",
                    "name": "游戏配置中台",
                    "oneLiner": "AI配表效率提升",
                    "description": "承载配置表管理",
                    "tags": ["Vue 3", "WebSocket"],
                    "highlights": [
                        {
                            "title": "AI配表系统",
                            "summary": "5分钟完成",
                            "detail": "SSE 流式接收",
                        }
                    ],
                    "interviewQA": [
                        {
                            "question": "WebSocket三级降级的触发条件是什么？",
                            "answer": "SDK失败→Direct，连接失败→SSE，SSE异常→轮询。",
                        }
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (knowledge / "tech_qa.json").write_text(
        json.dumps(
            [
                {
                    "id": "sse-stream",
                    "category": "技术深度",
                    "question": "SSE 流式解析的技术细节是什么？",
                    "answer": "ReadableStream 分片与 TextDecoder 边界处理。",
                    "key_points": ["ReadableStream", "TextDecoder"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (knowledge / "star_stories.json").write_text(
        json.dumps(
            [
                {
                    "id": "ai-config-system",
                    "title": "AI 配表系统 - 从1-2小时到5分钟",
                    "situation": "策划手动配表慢",
                    "task": "做 AI 配表",
                    "action": "SSE + Handsontable",
                    "result": "效率提升90%+",
                    "tags": ["AI工程化"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class InterviewSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "backend"
        self.root.mkdir()
        _write_fixture(self.root)
        self._old = os.environ.get("INTERVIEW_DATA_ROOT")
        os.environ["INTERVIEW_DATA_ROOT"] = str(self.root)
        interview_search.reset_cache()

    def tearDown(self):
        interview_search.reset_cache()
        if self._old is None:
            os.environ.pop("INTERVIEW_DATA_ROOT", None)
        else:
            os.environ["INTERVIEW_DATA_ROOT"] = self._old
        self.tmp.cleanup()

    def test_project_and_qa_hit(self):
        hits = interview_search.search_interview("WebSocket 三级")
        self.assertTrue(hits)
        self.assertTrue(any("WebSocket" in h["title"] or "WebSocket" in h["excerpt"] for h in hits))

    def test_tech_qa_hit(self):
        hits = interview_search.search_interview("SSE TextDecoder")
        self.assertTrue(hits)
        self.assertTrue(any(h["kind"] == "技术问答" for h in hits))
        self.assertIn("ReadableStream", hits[0]["excerpt"] + hits[0]["title"])

    def test_star_hit(self):
        hits = interview_search.search_interview("配表 90%")
        self.assertTrue(any(h["kind"] == "STAR" for h in hits))

    def test_no_match(self):
        hits = interview_search.search_interview("不存在的词xyzabc")
        self.assertEqual(hits, [])

    def test_tool_registered(self):
        names = {t["function"]["name"] for t in get_tool_schemas()}
        self.assertIn("search_interview", names)


if __name__ == "__main__":
    unittest.main()
