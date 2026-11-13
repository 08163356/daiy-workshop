"""同步 Markdown 文件脚本"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings
from app.core.database import async_session_maker, init_db
from app.services.sync_service import SyncService


async def sync_markdown():
    """同步所有 Markdown 文件"""
    print("=" * 50)
    print("读书管理系统 - Markdown 同步")
    print("=" * 50)

    # 确保数据库表存在
    await init_db()

    print(f"\nMarkdown 目录: {settings.markdown_dir}")

    if not settings.markdown_dir.exists():
        print(f"\n❌ 错误: Markdown 目录不存在！")
        print(f"   请检查路径: {settings.markdown_dir}")
        return

    md_files = list(settings.markdown_dir.glob("*.md"))
    print(f"发现 {len(md_files)} 个 MD 文件")

    async with async_session_maker() as db:
        service = SyncService(db)

        print("\n开始同步...")
        stats = await service.sync_all()

        await db.commit()

    print("\n" + "-" * 50)
    print("同步统计:")
    print(f"  📄 文件总数: {stats.get('total_files', 0)}")
    print(f"  ✨ 新建笔记: {stats.get('created', 0)}")
    print(f"  🔄 更新笔记: {stats.get('updated', 0)}")
    print(f"  ⏭️  跳过未变: {stats.get('skipped', 0)}")
    print(f"  ❌ 处理失败: {stats.get('errors', 0)}")
    print("-" * 50)
    print(f"  💡 概念总数: {stats.get('total_concepts', 0)}")
    print(f"  🔗 关系总数: {stats.get('total_relations', 0)}")
    print("=" * 50)
    print("\n✅ 同步完成！")


if __name__ == "__main__":
    asyncio.run(sync_markdown())
