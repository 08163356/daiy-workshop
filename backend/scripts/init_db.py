"""初始化或检查数据库表结构。

用法：
  python scripts/init_db.py
  python scripts/init_db.py --check
  python scripts/seed_demo.py  # 可选：写入虚构演示数据
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app.core.database import engine, init_db


async def check_database() -> None:
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        )
        tables = [row[0] for row in result.fetchall()]
    print(f"数据库表（{len(tables)}）：")
    for table in tables:
        print(f"  - {table}")


async def main() -> None:
    if "--check" not in sys.argv:
        await init_db()
        print("数据库表结构已就绪")
    await check_database()


if __name__ == "__main__":
    asyncio.run(main())
