"""测试 start_status API"""
import asyncio
import sys
sys.path.insert(0, '.')

async def test():
    from app.core.database import init_db, async_session_maker, engine
    from app.models.time_log import TimeLog
    from sqlalchemy import select, text

    # 初始化数据库
    await init_db()
    print("init_db done")

    # 检查 time_logs 表结构
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(time_logs)"))
        cols = result.fetchall()
        print(f"time_logs columns: {[c[1] for c in cols]}")

    # 模拟 start_status
    from datetime import datetime
    async with async_session_maker() as db:
        try:
            # 先检查有没有正在运行的
            result = await db.execute(
                select(TimeLog).where(TimeLog.end_time.is_(None))
            )
            running = result.scalars().all()
            print(f"Running logs: {len(running)}")

            # 创建新记录
            now = datetime.now()
            new_log = TimeLog(
                todo_id=None,
                start_time=now,
                category="status:通勤",
                activity_type="status",
                status_label="通勤",
                status_emoji="🚌",
            )
            db.add(new_log)
            print("db.add done")
            await db.flush()
            print(f"db.flush done, id={new_log.id}")
            await db.commit()
            print("db.commit done - SUCCESS!")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            await db.rollback()

    await engine.dispose()

asyncio.run(test())
