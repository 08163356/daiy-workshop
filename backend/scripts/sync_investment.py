"""同步投资笔记脚本"""

import asyncio
import sys
import re
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings
from app.core.database import async_session_maker, init_db
from sqlalchemy import select
from app.models.investment import InvestmentReflection


async def parse_investment_note(file_path: Path) -> dict:
    """解析投资笔记文件"""
    content = file_path.read_text(encoding="utf-8")
    filename = file_path.stem  # 如 "20260201关于黄金上涨"
    
    # 尝试从文件名提取日期 (格式: YYYYMMDD...)
    date_match = re.match(r"(\d{4})(\d{2})(\d{2})", filename)
    if date_match:
        year, month, day = date_match.groups()
        note_date = f"{year}-{month}-{day}"
        # 标题是日期后面的部分
        title = filename[8:] if len(filename) > 8 else filename
    else:
        # 没有日期前缀，使用文件修改时间
        mtime = file_path.stat().st_mtime
        note_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        title = filename
    
    # 如果标题为空，使用文件名
    if not title.strip():
        title = filename
    
    # 提取原始内容（去掉 AI 分析部分）
    original_content = content
    ai_analysis = None
    
    # 查找 AI 分析分隔符
    ai_marker = "## 🤖 投资导师的深度分析"
    if ai_marker in content:
        parts = content.split("---\n\n" + ai_marker)
        if len(parts) >= 2:
            original_content = parts[0].strip()
            ai_analysis = ai_marker + parts[1]
    
    # 提取关键点（从内容中识别要点）
    key_points = []
    lines = original_content.split("\n")
    for line in lines:
        line = line.strip()
        # 识别要点行
        if line.startswith("- ") or line.startswith("* ") or re.match(r"^\d+\.", line):
            point = re.sub(r"^[-*\d.]+\s*", "", line).strip()
            if point and len(point) > 5:
                key_points.append(point[:100])  # 限制长度
    
    # 如果没有提取到关键点，取前几句作为摘要
    if not key_points and original_content:
        sentences = re.split(r"[。！？\n]", original_content)
        key_points = [s.strip()[:100] for s in sentences[:3] if s.strip()]
    
    return {
        "date": note_date,
        "title": title,
        "content": original_content,
        "ai_analysis": ai_analysis,
        "key_points": key_points[:5],  # 最多5个关键点
        "file_path": str(file_path.relative_to(settings.investment_dir.parent)),
    }


async def sync_investment():
    """同步所有投资笔记"""
    print("=" * 50)
    print("投资管理系统 - 笔记同步")
    print("=" * 50)

    # 确保数据库表存在
    await init_db()

    investment_dir = settings.investment_dir
    print(f"\n投资笔记目录: {investment_dir}")

    if not investment_dir.exists():
        print(f"\n❌ 错误: 投资目录不存在！")
        print(f"   请检查路径: {investment_dir}")
        return

    # 扫描投资笔记文件
    md_files = list(investment_dir.glob("*.md"))
    # 排除一些特殊文件
    exclude_files = {"方案规划.md", "缘起.md", "投资学习计划.md", "投资记录模板.md"}
    md_files = [f for f in md_files if f.name not in exclude_files]
    
    print(f"发现 {len(md_files)} 个投资笔记文件")

    stats = {
        "total_files": len(md_files),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
    }

    async with async_session_maker() as db:
        for file_path in md_files:
            try:
                print(f"\n处理: {file_path.name}")
                
                # 解析笔记
                note_data = await parse_investment_note(file_path)
                
                # 检查是否已存在（通过文件路径）
                result = await db.execute(
                    select(InvestmentReflection).where(
                        InvestmentReflection.file_path == note_data["file_path"]
                    )
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # 检查内容是否有变化
                    if existing.content == note_data["content"] and existing.ai_analysis == note_data["ai_analysis"]:
                        print(f"  ⏭️  跳过（无变化）")
                        stats["skipped"] += 1
                    else:
                        # 更新
                        existing.title = note_data["title"]
                        existing.content = note_data["content"]
                        existing.ai_analysis = note_data["ai_analysis"]
                        existing.key_points = note_data["key_points"]
                        print(f"  🔄 更新: {note_data['title']}")
                        stats["updated"] += 1
                else:
                    # 新建
                    from datetime import date as date_type
                    reflection = InvestmentReflection(
                        date=date_type.fromisoformat(note_data["date"]),
                        title=note_data["title"],
                        content=note_data["content"],
                        ai_analysis=note_data["ai_analysis"],
                        key_points=note_data["key_points"],
                        file_path=note_data["file_path"],
                    )
                    db.add(reflection)
                    print(f"  ✨ 新建: {note_data['title']}")
                    stats["created"] += 1
                    
            except Exception as e:
                print(f"  ❌ 错误: {e}")
                stats["errors"] += 1

        await db.commit()

    print("\n" + "-" * 50)
    print("同步统计:")
    print(f"  📄 文件总数: {stats['total_files']}")
    print(f"  ✨ 新建笔记: {stats['created']}")
    print(f"  🔄 更新笔记: {stats['updated']}")
    print(f"  ⏭️  跳过未变: {stats['skipped']}")
    print(f"  ❌ 处理失败: {stats['errors']}")
    print("=" * 50)
    print("\n✅ 投资笔记同步完成！")


if __name__ == "__main__":
    asyncio.run(sync_investment())
