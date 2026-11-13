"""Fail when files unsafe for the public repository are present."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist"}
TEXT_SUFFIXES = {
    ".py", ".ts", ".vue", ".js", ".mjs", ".md", ".sh", ".bat",
    ".json", ".yml", ".yaml", ".toml", ".env", ".txt",
}
FORBIDDEN_FILES = {".env", "diary_seed.sql"}
FORBIDDEN_SUFFIXES = {
    ".db", ".db-journal", ".db-wal", ".db-shm",
    ".sqlite", ".sqlite-journal", ".sqlite-wal", ".sqlite-shm",
    ".sqlite3", ".sqlite3-journal", ".sqlite3-wal", ".sqlite3-shm",
    ".dump", ".bak", ".pyc",
}
FORBIDDEN_PATTERNS = {
    "production_ip": re.compile(r"\b8\.135\.9\.12\b"),
    "old_password": re.compile(r"Lx1010", re.I),
    "private_path": re.compile(r"axingSpace", re.I),
    "personal_domain": re.compile(r"ablog\.axingit\.top", re.I),
    "private_key": re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    "github_token": re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
}


def main() -> int:
    failures: list[str] = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if not path.is_file():
            continue
        if rel.as_posix() == "scripts/check_public_repo.py":
            continue
        if path.name in FORBIDDEN_FILES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"forbidden file: {rel}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".env.example":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in FORBIDDEN_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{name}: {rel}")

    if failures:
        print("Public repository check failed:")
        for failure in sorted(set(failures)):
            print(f"  - {failure}")
        return 1
    print("Public repository check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
