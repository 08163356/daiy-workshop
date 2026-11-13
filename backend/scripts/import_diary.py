"""
导入「说点儿啥」目录的 MD 文件到日记数据库
用法: python scripts/import_diary.py [--db DB_PATH] [--dir DIARY_DIR] [--clean]

--clean: 清空已有日记数据后重新导入（首次可用，后续增量别加）
"""

import os
import re
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# 不导入这些文件（纯 prompt / 工具型文件）
SKIP_FILES = {
    "prompt.md",
    "AI使用测试之多任务并行.md",
    "面试本质是一场销售.md",
}

# AI 回复的常见分隔标记
AI_SEPARATORS = [
    r"^---\s*$",
    r"^#+\s*(AI\s*回复|日记分析|心理咨询师|专业心理|分析与建议|🧠)",
    r"^###\s*(心理咨询师视角|职业规划师视角|从.*视角|📊)",
]

# 日记前的提示语模式
PROMPT_PATTERNS = [
    r"^请你(作为|以).*?日记.*?[：:]\s*$",
    r"^请你(作为|以).*?(身份|视角).*?[，,].*?日记.*$",
]


def detect_date(filepath: Path) -> datetime:
    """从文件名或修改时间推断日期"""
    name = filepath.stem
    m = re.match(r"^(\d{8})", name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d")
        except ValueError:
            pass
    m = re.match(r"^(\d{4})", name)
    if m:
        digits = m.group(1)
        month, day = int(digits[:2]), int(digits[2:])
        if 1 <= month <= 12 and 1 <= day <= 31:
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
            year = mtime.year
            if mtime.month < month:
                year -= 1
            try:
                return datetime(year, month, day)
            except ValueError:
                pass
    return datetime.fromtimestamp(filepath.stat().st_mtime)


def clean_title(filename: str) -> str:
    name = Path(filename).stem
    name = re.sub(r"^\d{4,8}", "", name)
    return name.strip() or Path(filename).stem


def split_content_and_ai(raw: str) -> tuple[str, str | None]:
    lines = raw.split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        is_prompt = False
        for pat in PROMPT_PATTERNS:
            if re.match(pat, stripped):
                is_prompt = True
                break
        if is_prompt:
            start_idx = i + 1
            while start_idx < len(lines) and not lines[start_idx].strip():
                start_idx += 1
            break
        else:
            break
    while start_idx < len(lines):
        stripped = lines[start_idx].strip().lower()
        if stripped in ("[toc]", "## 日记内容", "## 日记"):
            start_idx += 1
            while start_idx < len(lines) and not lines[start_idx].strip():
                start_idx += 1
        else:
            break
    ai_start = None
    for i in range(start_idx, len(lines)):
        line = lines[i].strip()
        for pat in AI_SEPARATORS:
            if re.match(pat, line):
                if line == "---":
                    for j in range(i + 1, min(i + 5, len(lines))):
                        next_line = lines[j].strip()
                        if re.match(r"^#+\s*(日记分析|AI|心理|专业|分析|🧠|📊)", next_line):
                            ai_start = i
                            break
                else:
                    ai_start = i
                    break
        if ai_start is not None:
            break
    if ai_start is not None:
        diary_content = "\n".join(lines[start_idx:ai_start]).strip()
        ai_content = "\n".join(lines[ai_start:]).strip()
        ai_content = re.sub(r"^---\s*\n*", "", ai_content).strip()
    else:
        full_text = "\n".join(lines[start_idx:])
        ai_match = re.search(r"\n\s*(AI\s*回复[：:])\s*\n", full_text)
        if ai_match:
            diary_content = full_text[:ai_match.start()].strip()
            ai_content = full_text[ai_match.start():].strip()
        else:
            diary_content = full_text.strip()
            ai_content = None
    return diary_content, ai_content


def extract_mood(content: str, ai_analysis: str | None) -> str | None:
    text = (content + "\n" + (ai_analysis or "")).lower()
    mood_keywords = {
        "焦虑": ["焦虑", "焦虑感", "不安", "紧张"],
        "自卑": ["自卑", "自卑感", "不如别人", "羡慕"],
        "迷茫": ["迷茫", "不知道", "没有方向", "没方向"],
        "反思": ["反思", "复盘", "思考", "回顾"],
        "积极": ["积极", "开心", "快乐", "成就感", "进步"],
        "低落": ["颓废", "失落", "难受", "不开心", "郁闷"],
        "烦躁": ["烦躁", "烦", "怒气", "不耐烦", "暴躁"],
        "平静": ["平静", "淡定", "释然"],
    }
    scores = {}
    for mood, keywords in mood_keywords.items():
        score = sum(text.count(kw) for kw in keywords)
        if score > 0:
            scores[mood] = score
    if scores:
        return max(scores, key=scores.get)
    return "反思"


def extract_tags(title: str, content: str, subdir: str | None) -> list[str]:
    tags = ["随笔"]
    if subdir:
        tags.append(subdir)
    tag_keywords = {
        "职场": ["工作", "绩效", "领导", "同事", "公司", "摆烂", "职场", "面试"],
        "家庭": ["父母", "家里", "过年", "家庭", "哥哥", "侄子", "侄女"],
        "情绪": ["焦虑", "自卑", "颓废", "失落", "烦", "不开心"],
        "成长": ["读书", "学习", "反思", "进步", "习惯"],
        "运动": ["篮球", "打球", "跑步", "训练", "爬山", "徒步"],
        "社交": ["朋友", "活动", "交友", "聊天", "联谊"],
    }
    text = title + " " + content[:500]
    for tag, keywords in tag_keywords.items():
        if any(kw in text for kw in keywords):
            tags.append(tag)
    return list(dict.fromkeys(tags))


def import_diaries(db_path: str, diary_dir: str, clean: bool = False):
    diary_path = Path(diary_dir)
    if not diary_path.exists():
        print(f"错误: 目录不存在 - {diary_dir}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS diary_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE NOT NULL,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            ai_analysis TEXT,
            mood VARCHAR(50),
            tags JSON,
            key_issues JSON,
            action_items JSON,
            file_path VARCHAR(500),
            source VARCHAR(50) DEFAULT 'sync',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    if clean:
        cursor.execute("DELETE FROM diary_entries WHERE source = 'sync'")
        print(f"已清空 sync 来源的日记数据")

    md_files = []
    for root, dirs, files in os.walk(diary_path):
        for f in files:
            if f.endswith(".md") and f not in SKIP_FILES:
                md_files.append(Path(root) / f)
    md_files.sort(key=lambda p: p.stat().st_mtime)

    imported = 0
    skipped = 0

    for filepath in md_files:
        rel_path = filepath.relative_to(diary_path)
        subdir = str(rel_path.parent) if str(rel_path.parent) != "." else None
        file_path_str = str(rel_path).replace("\\", "/")
        cursor.execute("SELECT id FROM diary_entries WHERE file_path = ?", (file_path_str,))
        if cursor.fetchone():
            skipped += 1
            continue
        try:
            raw = filepath.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  跳过 {rel_path}: 读取失败 - {e}")
            skipped += 1
            continue
        if not raw.strip():
            skipped += 1
            continue
        title = clean_title(filepath.name)
        entry_date = detect_date(filepath)
        diary_content, ai_analysis = split_content_and_ai(raw)
        if not diary_content or len(diary_content) < 10:
            skipped += 1
            continue
        mood = extract_mood(diary_content, ai_analysis)
        tags = extract_tags(title, diary_content, subdir)

        cursor.execute("""
            INSERT INTO diary_entries (date, title, content, ai_analysis, mood, tags, file_path, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'sync', ?, ?)
        """, (
            entry_date.strftime("%Y-%m-%d"),
            title,
            diary_content,
            ai_analysis,
            mood,
            json.dumps(tags, ensure_ascii=False),
            file_path_str,
            entry_date.strftime("%Y-%m-%d %H:%M:%S"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        imported += 1
        print(f"  + {rel_path} -> {entry_date.strftime('%Y-%m-%d')} | {title} | {mood} | {tags}")

    conn.commit()
    conn.close()
    print(f"\n导入完成: {imported} 条新增, {skipped} 条跳过")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导入日记 MD 文件到数据库")
    parser.add_argument("--db", default=None, help="数据库路径")
    parser.add_argument("--dir", default=None, help="日记目录路径")
    parser.add_argument("--clean", action="store_true", help="清空已有 sync 数据后重新导入")
    args = parser.parse_args()

    if args.db is None:
        args.db = str(Path(__file__).parent.parent / "reading_system.db")
    if args.dir is None:
        args.dir = str(Path("./user-data/diary"))

    print(f"数据库: {args.db}")
    print(f"日记目录: {args.dir}")
    print(f"清空模式: {args.clean}\n")
    import_diaries(args.db, args.dir, args.clean)
