"""写入一组完全虚构的演示数据。

用法：在 backend 目录执行 `python scripts/seed_demo.py`。
脚本仅在待办、日记和笔记都为空时写入，重复执行不会叠加数据。
"""

import asyncio
import hashlib
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.core.database import async_session_maker, init_db
from app.models.diary import DiaryEntry
from app.models.note import Note
from app.models.todo import TodoComment, TodoItem
from app.models.time_log import TimeLog
from app.models.wellbeing import WellbeingEntry


async def seed() -> None:
    await init_db()
    today = date.today()
    week = today.isocalendar()
    week_key = f"{week.year}-W{week.week:02d}"
    month_key = today.strftime("%Y-%m")
    year_key = str(today.year)

    async with async_session_maker() as db:
        existing = await db.scalar(select(func.count()).select_from(TodoItem))
        if existing:
            print("数据库已有数据，跳过演示数据写入")
            return

        launch = TodoItem(
            title="发布个人知识系统的第一个公开版本",
            description="整理功能边界、演示数据和发布文章。",
            quadrant=2,
            urgency=4,
            importance=5,
            category="creative",
            status="in_progress",
            scheduled_date=today,
            due_date=today + timedelta(days=5),
            estimated_minutes=240,
            source="demo",
            core_scope="week",
            core_period_key=week_key,
        )
        health = TodoItem(
            title="完成本周三次运动",
            quadrant=2,
            urgency=3,
            importance=4,
            category="health",
            status="planned",
            scheduled_date=today + timedelta(days=1),
            source="demo",
            core_scope="month",
            core_period_key=month_key,
        )
        writing = TodoItem(
            title="持续输出 12 篇产品设计文章",
            quadrant=2,
            urgency=2,
            importance=5,
            category="creative",
            status="planned",
            source="demo",
            core_scope="year",
            core_period_key=year_key,
        )
        db.add_all([launch, health, writing])
        await db.flush()

        children = [
            TodoItem(
                title="整理开源仓库 README",
                parent_id=launch.id,
                quadrant=2,
                urgency=5,
                importance=5,
                category="creative",
                status="completed",
                completed_at=datetime.now() - timedelta(days=1),
                scheduled_date=today - timedelta(days=1),
                actual_minutes=70,
                source="demo",
            ),
            TodoItem(
                title="重拍关键产品截图",
                parent_id=launch.id,
                quadrant=2,
                urgency=4,
                importance=4,
                category="creative",
                status="in_progress",
                scheduled_date=today,
                source="demo",
            ),
            TodoItem(
                title="完成发布文章初稿",
                parent_id=launch.id,
                quadrant=2,
                urgency=3,
                importance=4,
                category="creative",
                status="planned",
                scheduled_date=today + timedelta(days=2),
                source="demo",
            ),
        ]
        db.add_all(children)
        await db.flush()

        db.add_all(
            [
                TodoComment(
                    todo_id=launch.id,
                    kind="idea",
                    content="文章不要罗列所有模块，重点讲记录如何变成行动。",
                ),
                TodoComment(
                    todo_id=launch.id,
                    kind="lesson",
                    content="先准备合成演示数据再截图，避免发布前反复遮挡隐私。",
                ),
                DiaryEntry(
                    date=today - timedelta(days=2),
                    title="开始准备公开发布",
                    content=(
                        "今天把过去几个月做的功能重新看了一遍。真正有价值的不是页面数量，"
                        "而是待办、日记和复盘开始互相连接。接下来先把隐私边界处理好，再写文章。"
                    ),
                    ai_analysis=(
                        "值得保留的判断：产品差异不在“功能多”，而在“真实记录能回到下一次行动”。"
                    ),
                    mood="平静、期待",
                    tags=["开源", "产品复盘"],
                    action_items=["列出公开仓库白名单", "准备统一截图故事线"],
                    source="demo",
                ),
                DiaryEntry(
                    date=today - timedelta(days=1),
                    title="第一次完整走通发布故事",
                    content=(
                        "用虚构数据走了一遍：先让助手总结上周，再把零散想法拆成任务单，"
                        "最后检查年度目标是否真的获得了时间投入。叙事已经比单独展示页面清楚很多。"
                    ),
                    ai_analysis="这次验证说明，最好的产品介绍应该围绕一条真实工作流展开。",
                    mood="专注",
                    tags=["演示", "写作"],
                    source="demo",
                ),
                Note(
                    filename="demo-trusted-ai.md",
                    title="可信 AI 助手的三个原则",
                    content=(
                        "一、先读真实数据再回答。二、写入系统前让用户确认。"
                        "三、没有值得说的内容时保持克制。"
                    ),
                    summary="真实数据、确认门和克制，是个人 AI 产品获得信任的基础。",
                    reading_date=today - timedelta(days=3),
                    word_count=52,
                    file_hash=hashlib.sha256(b"demo-trusted-ai").hexdigest(),
                    source_type="self",
                ),
                WellbeingEntry(
                    type="achievement",
                    content="完成了公开版本的隐私审计清单",
                    category="学习",
                    intensity=4,
                    occurred_at=today - timedelta(days=1),
                    source_type="demo",
                ),
                WellbeingEntry(
                    type="gratitude",
                    content="感谢朋友帮忙从第一次使用者视角检查安装步骤",
                    category="关系",
                    intensity=3,
                    occurred_at=today,
                    source_type="demo",
                ),
                TimeLog(
                    todo_id=launch.id,
                    start_time=datetime.now() - timedelta(days=1, hours=2),
                    end_time=datetime.now() - timedelta(days=1),
                    duration_seconds=7200,
                    category="creative",
                    activity_type="task",
                ),
            ]
        )
        await db.commit()
        print("已写入虚构演示数据")


if __name__ == "__main__":
    asyncio.run(seed())
