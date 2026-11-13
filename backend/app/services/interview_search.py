"""检索 interview 作品集/面试材料（只读）。

数据源读取 INTERVIEW_DATA_ROOT 指定的目录：
  <root>/seed_data/projects.json、resume.md、ai_profile.json
  <root>/interview_knowledge/*.json
  <root>/../.. 下若干面试准备 .md（与 portfolio 仓库布局一致）

"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60

_cache_docs: list[dict[str, str]] | None = None
_cache_key: str = ""
_cache_loaded_at: float = 0.0


def reset_cache() -> None:
    global _cache_docs, _cache_key, _cache_loaded_at
    _cache_docs = None
    _cache_key = ""
    _cache_loaded_at = 0.0


def _site_base() -> str:
    value = os.environ.get("INTERVIEW_SITE_BASE", "").strip()
    return value.rstrip("/") + "/" if value else ""


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    env_root = (os.environ.get("INTERVIEW_DATA_ROOT") or "").strip()
    if env_root:
        roots.append(Path(env_root))
    return roots


def _resolve_root() -> Path | None:
    for root in _candidate_roots():
        if not root or str(root) in ("", "."):
            continue
        if (root / "seed_data" / "projects.json").is_file() or (root / "interview_knowledge").is_dir():
            return root.resolve()
    return None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _add_doc(docs: list[dict[str, str]], *, kind: str, title: str, text: str, url: str = "") -> None:
    body = (text or "").strip()
    if not body and not title:
        return
    docs.append(
        {
            "kind": kind,
            "title": (title or "（无标题）").strip(),
            "excerpt": body[:220].replace("\n", " "),
            "url": url or _site_base(),
            "haystack": f"{kind} {title} {body}".lower(),
        }
    )


def _load_projects(seed: Path, docs: list[dict[str, str]]) -> None:
    path = seed / "projects.json"
    if not path.is_file():
        return
    projects = _read_json(path)
    if not isinstance(projects, list):
        return
    for proj in projects:
        if not isinstance(proj, dict):
            continue
        pid = str(proj.get("id") or "")
        name = str(proj.get("name") or proj.get("shortName") or pid or "项目")
        parts = [
            str(proj.get("oneLiner") or ""),
            str(proj.get("description") or ""),
            str(proj.get("role") or ""),
            " ".join(proj.get("tags") or []),
        ]
        for h in proj.get("highlights") or []:
            if isinstance(h, dict):
                parts.append(str(h.get("title") or ""))
                parts.append(str(h.get("summary") or ""))
                parts.append(str(h.get("detail") or ""))
        _add_doc(
            docs,
            kind="项目",
            title=name,
            text="\n".join(p for p in parts if p),
            url=f"{_site_base()}#/projects/{pid}" if pid else _site_base(),
        )
        for qa in proj.get("interviewQA") or []:
            if not isinstance(qa, dict):
                continue
            q = str(qa.get("question") or "").strip()
            a = str(qa.get("answer") or "").strip()
            if not q and not a:
                continue
            _add_doc(
                docs,
                kind="项目问答",
                title=f"{name} · {q[:60] or '问答'}",
                text=f"Q: {q}\nA: {a}",
                url=f"{_site_base()}#/projects/{pid}" if pid else _site_base(),
            )


def _load_tech_qa(knowledge: Path, docs: list[dict[str, str]]) -> None:
    path = knowledge / "tech_qa.json"
    if not path.is_file():
        return
    rows = _read_json(path)
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        q = str(row.get("question") or "").strip()
        a = str(row.get("answer") or "").strip()
        cat = str(row.get("category") or "")
        keys = " ".join(row.get("key_points") or [])
        _add_doc(
            docs,
            kind="技术问答",
            title=q or str(row.get("id") or "技术问答"),
            text=f"[{cat}] {a}\n要点: {keys}".strip(),
        )


def _load_star_stories(knowledge: Path, docs: list[dict[str, str]]) -> None:
    path = knowledge / "star_stories.json"
    if not path.is_file():
        return
    rows = _read_json(path)
    if not isinstance(rows, list):
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("id") or "STAR")
        text = "\n".join(
            [
                f"S: {row.get('situation') or ''}",
                f"T: {row.get('task') or ''}",
                f"A: {row.get('action') or ''}",
                f"R: {row.get('result') or ''}",
                " ".join(row.get("tags") or []),
            ]
        )
        _add_doc(docs, kind="STAR", title=title, text=text)


def _load_json_blob(path: Path, docs: list[dict[str, str]], *, kind: str, title: str) -> None:
    if not path.is_file():
        return
    try:
        data = _read_json(path)
    except Exception as exc:
        logger.warning("读取 %s 失败: %s", path, exc)
        return
    text = json.dumps(data, ensure_ascii=False)
    _add_doc(docs, kind=kind, title=title, text=text)


def _load_markdown(path: Path, docs: list[dict[str, str]], *, kind: str) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    # 大文件按 ## 标题切块，避免整篇灌进一条
    chunks = _split_markdown(text)
    if len(chunks) <= 1:
        _add_doc(docs, kind=kind, title=path.stem, text=text[:4000])
        return
    for heading, body in chunks[:40]:
        _add_doc(docs, kind=kind, title=f"{path.stem} · {heading}", text=body[:3000])


def _split_markdown(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    chunks: list[tuple[str, str]] = []
    heading = "概述"
    buf: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if buf:
                chunks.append((heading, "\n".join(buf).strip()))
            heading = line[3:].strip() or "小节"
            buf = []
        else:
            buf.append(line)
    if buf:
        chunks.append((heading, "\n".join(buf).strip()))
    return [(h, b) for h, b in chunks if b]


def _load_docs(root: Path) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    seed = root / "seed_data"
    knowledge = root / "interview_knowledge"
    _load_projects(seed, docs)
    _load_tech_qa(knowledge, docs)
    _load_star_stories(knowledge, docs)
    _load_json_blob(knowledge / "self_intro.json", docs, kind="自我介绍", title="自我介绍模板")
    _load_json_blob(knowledge / "strategies.json", docs, kind="面试策略", title="面试策略")
    _load_json_blob(seed / "ai_profile.json", docs, kind="画像", title="AI 求职画像")
    _load_markdown(seed / "resume.md", docs, kind="简历")

    # portfolio 仓库根目录的准备材料（backend/../..）
    project_root = root.parent.parent
    for name in (
        "面试策略.md",
        "自我介绍.md",
        "项目展示方案.md",
        "面试准备-问题与回答.md",
        "简历.md",
    ):
        _load_markdown(project_root / name, docs, kind="面试材料")
    return docs


def _get_docs() -> list[dict[str, str]]:
    global _cache_docs, _cache_key, _cache_loaded_at
    root = _resolve_root()
    if root is None:
        raise FileNotFoundError(
            "找不到 interview 数据目录。请设置 INTERVIEW_DATA_ROOT 指向 "
            "portfolio/backend（内含 seed_data / interview_knowledge）。"
        )
    key = str(root)
    now = time.time()
    if (
        _cache_docs is not None
        and _cache_key == key
        and now - _cache_loaded_at < CACHE_TTL_SECONDS
    ):
        return _cache_docs
    docs = _load_docs(root)
    _cache_docs = docs
    _cache_key = key
    _cache_loaded_at = now
    logger.info("interview 检索索引加载完成：%s docs from %s", len(docs), root)
    return docs


def search_interview(keyword: str, limit: int = 8) -> list[dict[str, str]]:
    query = (keyword or "").strip()
    if not query:
        raise ValueError("关键词不能为空")
    tokens = [t.lower() for t in query.split() if t.strip()]
    if not tokens:
        raise ValueError("关键词不能为空")
    docs = _get_docs()
    hits: list[dict[str, str]] = []
    for doc in docs:
        hay = doc["haystack"]
        if not all(token in hay for token in tokens):
            continue
        hits.append(
            {
                "kind": doc["kind"],
                "title": doc["title"],
                "excerpt": doc["excerpt"],
                "url": doc["url"],
            }
        )
        if len(hits) >= max(1, min(int(limit or 8), 20)):
            break
    return hits


def format_search_result(keyword: str, limit: int = 8) -> str:
    hits = search_interview(keyword, limit=limit)
    if not hits:
        return f"interview 作品集/面试材料里没有找到「{keyword.strip()}」。"
    lines = [f"interview 命中 {len(hits)} 条："]
    for item in hits:
        snippet = item["excerpt"]
        tail = f"：{snippet}" if snippet else ""
        url = item.get("url") or ""
        lines.append(f"- [{item['kind']}] {item['title']} {url}{tail}")
    return "\n".join(lines)
