"""
存量数据迁移脚本：将读书目录下的 MD 文件的原文和 AI 分析回填到 timeline.json

逻辑：
1. 读取当前 timeline.json
2. 遍历每个 timeline 条目，通过标题/日期模糊匹配对应的 md 文件
3. 从 md 文件中提取原文（--- 之前）和 AI 分析（--- 之后）
4. 回填到 timeline.json 的 original_content 和 ai_analysis 字段
5. 同时写入 data/ 和 frontend/public/data/ 两个目录
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DATA_DIR = BASE_DIR / "frontend" / "public" / "data"

# 读书目录（在项目的上级目录）
READING_DIR = BASE_DIR.parent / "读书"

def load_timeline():
    """加载 timeline.json"""
    path = DATA_DIR / "timeline.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_timeline(data):
    """保存 timeline.json 到两个目录"""
    for d in [DATA_DIR, FRONTEND_DATA_DIR]:
        d.mkdir(parents=True, exist_ok=True)
        path = d / "timeline.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已保存 timeline.json (共 {len(data)} 条)")

def parse_md_file(filepath: Path):
    """解析 MD 文件，提取原文和 AI 分析
    
    格式约定：
    - 原文在第一个 --- 之前
    - AI 分析在第一个 --- 之后（如果有的话）
    """
    content = filepath.read_text(encoding="utf-8")
    
    # 用 --- 分割（独立成行的分隔符）
    parts = re.split(r'\n---\n', content, maxsplit=1)
    
    original = parts[0].strip()
    ai_analysis = parts[1].strip() if len(parts) > 1 else ""
    
    return original, ai_analysis

def extract_date_from_filename(filename: str):
    """从文件名提取日期
    
    支持格式：
    - 20260304xxx.md → 2026.03.04
    - 1230xxx.md → 2024.12.30（默认2024年）
    - 1120xxx.md → 2024.11.20
    """
    name = Path(filename).stem
    
    # 8位日期: 20260304
    m = re.match(r'^(\d{4})(\d{2})(\d{2})', name)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    
    # 4位日期: 1230
    m = re.match(r'^(\d{2})(\d{2})', name)
    if m:
        month = m.group(1)
        day = m.group(2)
        # 默认 2024 年
        return f"2024.{month}.{day}"
    
    return None

def normalize_date(date_str: str) -> str:
    """标准化日期字符串为 YYYY.MM.DD 格式"""
    return date_str.replace("-", ".").strip()

def match_timeline_to_files(timeline, md_files):
    """将 timeline 条目匹配到 md 文件
    
    匹配策略：
    1. 优先按日期精确匹配
    2. 然后按标题关键词模糊匹配
    """
    # 构建文件索引
    file_index = {}  # date -> [(filepath, original, ai_analysis)]
    
    for fp in md_files:
        date = extract_date_from_filename(fp.name)
        if date:
            original, ai_analysis = parse_md_file(fp)
            if date not in file_index:
                file_index[date] = []
            file_index[date].append({
                "filepath": fp,
                "original": original,
                "ai_analysis": ai_analysis,
                "filename": fp.name,
            })
    
    print(f"\n📂 读书目录共 {len(md_files)} 个 md 文件，解析出 {len(file_index)} 个日期")
    for date, files in sorted(file_index.items()):
        for f in files:
            has_ai = "✅" if f["ai_analysis"] else "❌"
            print(f"  {date} → {f['filename']} (AI分析: {has_ai})")
    
    # 匹配
    matched = 0
    skipped = 0
    already_has = 0
    
    for item in timeline:
        item_date = normalize_date(item.get("date", ""))
        
        # 已经有原文的跳过
        if item.get("original_content") and item.get("ai_analysis"):
            already_has += 1
            continue
        
        # 按日期匹配
        if item_date in file_index:
            candidates = file_index[item_date]
            
            # 如果只有一个候选，直接匹配
            if len(candidates) == 1:
                best = candidates[0]
            else:
                # 多个候选时，按标题相似度匹配
                title = item.get("title", "")
                best = None
                best_score = 0
                for c in candidates:
                    # 简单的关键词匹配
                    score = sum(1 for word in title if word in c["filename"])
                    if score > best_score:
                        best_score = score
                        best = c
                if not best:
                    best = candidates[0]
            
            if best["original"]:
                item["original_content"] = best["original"]
            if best["ai_analysis"]:
                item["ai_analysis"] = best["ai_analysis"]
            
            matched += 1
            print(f"  ✅ 匹配: [{item_date}] {item.get('title', '')[:30]} ← {best['filename']}")
        else:
            skipped += 1
            print(f"  ❓ 未匹配: [{item_date}] {item.get('title', '')[:40]}")
    
    print(f"\n📊 匹配结果：匹配 {matched} | 已有数据 {already_has} | 未匹配 {skipped}")
    return timeline

def main():
    print("=" * 60)
    print("📚 存量数据迁移：回填原文和 AI 分析到 timeline.json")
    print("=" * 60)
    
    # 检查目录
    if not READING_DIR.exists():
        print(f"❌ 读书目录不存在: {READING_DIR}")
        sys.exit(1)
    
    # 加载 timeline
    timeline = load_timeline()
    print(f"\n📋 当前 timeline.json 共 {len(timeline)} 条记录")
    
    # 获取 md 文件列表（排除非读书笔记的文件）
    exclude_files = {"读书管理系统.html", "读书管理系统_更新版.html", "update_system.py", "一键更新.bat"}
    md_files = [
        f for f in READING_DIR.glob("*.md")
        if f.name not in exclude_files
    ]
    print(f"📂 读书目录共 {len(md_files)} 个 md 文件")
    
    # 匹配并回填
    timeline = match_timeline_to_files(timeline, md_files)
    
    # 保存
    save_timeline(timeline)
    print("\n✨ 迁移完成！")

if __name__ == "__main__":
    main()
