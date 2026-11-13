"""检索个人博客公开索引（blog-index.json）。

优先读 BLOG_INDEX_PATH 指定的本机文件；
没有文件时可读取 BLOG_INDEX_URL 指定的公开索引。
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

logger = logging.getLogger(__name__)

DEFAULT_INDEX_PATH = "./user-data/blog-index.json"
DEFAULT_INDEX_URL = ""
HTTP_TTL_SECONDS = 300

_cache_pages: list[dict[str, Any]] | None = None
_cache_key: str = ""
_cache_mtime: float = 0.0
_cache_fetched_at: float = 0.0


def _index_path() -> Path:
    return Path(os.environ.get("BLOG_INDEX_PATH", DEFAULT_INDEX_PATH))


def _index_url() -> str:
    return os.environ.get("BLOG_INDEX_URL", DEFAULT_INDEX_URL).strip()


def reset_cache() -> None:
    global _cache_pages, _cache_key, _cache_mtime, _cache_fetched_at
    _cache_pages = None
    _cache_key = ""
    _cache_mtime = 0.0
    _cache_fetched_at = 0.0


def _parse_payload(raw: str) -> list[dict[str, Any]]:
    data = json.loads(raw)
    pages = data.get("pages") if isinstance(data, dict) else data
    if not isinstance(pages, list):
        return []
    return [p for p in pages if isinstance(p, dict)]


def _load_pages() -> list[dict[str, Any]]:
    global _cache_pages, _cache_key, _cache_mtime, _cache_fetched_at
    path = _index_path()
    if path.is_file():
        key = str(path.resolve())
        mtime = path.stat().st_mtime
        if _cache_pages is not None and _cache_key == key and _cache_mtime == mtime:
            return _cache_pages
        pages = _parse_payload(path.read_text(encoding="utf-8"))
        _cache_pages = pages
        _cache_key = key
        _cache_mtime = mtime
        _cache_fetched_at = time.time()
        return pages

    url = _index_url()
    if not url:
        raise FileNotFoundError(
            f"博客索引不可用：{path}。请配置 BLOG_INDEX_PATH 或 BLOG_INDEX_URL"
        )
    now = time.time()
    if _cache_pages is not None and _cache_key == url and now - _cache_fetched_at < HTTP_TTL_SECONDS:
        return _cache_pages
    try:
        with urlopen(url, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("读取博客索引失败 %s: %s", url, exc)
        if _cache_pages is not None:
            return _cache_pages
        raise FileNotFoundError(f"博客索引不可用：{path} 和 {url}") from exc
    pages = _parse_payload(raw)
    _cache_pages = pages
    _cache_key = url
    _cache_fetched_at = now
    return pages


def _haystack(page: dict[str, Any]) -> str:
    parts = [
        str(page.get("title") or ""),
        str(page.get("excerpt") or ""),
        " ".join(page.get("tags") or []),
        " ".join(page.get("categories") or []),
    ]
    return " ".join(parts).lower()


def search_blog(keyword: str, limit: int = 8) -> list[dict[str, str]]:
    query = (keyword or "").strip()
    if not query:
        raise ValueError("关键词不能为空")
    tokens = [t.lower() for t in query.split() if t.strip()]
    if not tokens:
        raise ValueError("关键词不能为空")
    pages = _load_pages()
    hits: list[dict[str, str]] = []
    for page in pages:
        text = _haystack(page)
        if not all(token in text for token in tokens):
            continue
        excerpt = str(page.get("excerpt") or "").replace("\n", " ").strip()
        hits.append(
            {
                "title": str(page.get("title") or "").strip() or "（无标题）",
                "url": str(page.get("url") or page.get("permalink") or "").strip(),
                "permalink": str(page.get("permalink") or "").strip(),
                "excerpt": excerpt[:180],
            }
        )
        if len(hits) >= max(1, min(int(limit or 8), 20)):
            break
    return hits


def format_search_result(keyword: str, limit: int = 8) -> str:
    hits = search_blog(keyword, limit=limit)
    if not hits:
        return f"个人博客公开稿里没有找到「{keyword.strip()}」。"
    lines = [f"个人博客命中 {len(hits)} 条："]
    for item in hits:
        url = item["url"] or item["permalink"]
        snippet = item["excerpt"]
        tail = f"：{snippet}" if snippet else ""
        lines.append(f"- {item['title']} {url}{tail}")
    return "\n".join(lines)
