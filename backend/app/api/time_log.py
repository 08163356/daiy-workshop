"""时间记录 API"""

from datetime import datetime, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.time_log import TimeLog
from app.models.todo import TodoItem
from app.schemas.time_log import (
    TimeLogResponse,
    TimerStatusResponse,
    StatusPreset,
    TimeStatsCategory,
    TimeDailyStats,
    TimeAnalysisResponse,
)

router = APIRouter(prefix="/time", tags=["时间记录"])

# 预设状态列表
STATUS_PRESETS: list[StatusPreset] = [
    StatusPreset(label="通勤", emoji="🚌", color="#F59E0B"),
    StatusPreset(label="运动", emoji="🏃", color="#10B981"),
    StatusPreset(label="吃饭", emoji="🍚", color="#EF4444"),
    StatusPreset(label="睡觉", emoji="😴", color="#6366F1"),
    StatusPreset(label="放空", emoji="☁️", color="#94A3B8"),
    StatusPreset(label="娱乐", emoji="🎮", color="#8B5CF6"),
    StatusPreset(label="聚会", emoji="🍻", color="#EC4899"),
    StatusPreset(label="学习", emoji="📖", color="#3B82F6"),
    StatusPreset(label="工作", emoji="💻", color="#0EA5E9"),
    StatusPreset(label="家务", emoji="🧹", color="#78716C"),
]

# 分类合并映射：仅合并与任务分类有直接对应关系的状态
# 通勤、吃饭、睡觉、家务、放空等无对应任务分类的状态保持原样
CATEGORY_MERGE_MAP: dict[str, str] = {
    "status:工作": "work",
    "status:学习": "learning",
    "status:运动": "health",
    "status:聚会": "social",
    "status:娱乐": "creative",
}


def normalize_category(category: str | None) -> str:
    """将分类标准化：合并同类的 status 分类到任务分类"""
    if not category:
        return "uncategorized"
    return CATEGORY_MERGE_MAP.get(category, category)


# ==================== 内部工具函数 ====================

async def _stop_all_running(db: AsyncSession) -> Optional[TimeLog]:
    """停止所有正在进行的计时，返回被停止的记录（如有）"""
    running_logs = await db.execute(
        select(TimeLog).where(TimeLog.end_time.is_(None))
    )
    stopped = None
    now = datetime.now()
    for log in running_logs.scalars().all():
        log.end_time = now
        log.duration_seconds = int((now - log.start_time).total_seconds())
        stopped = log
    return stopped


# ==================== 任务计时操作 ====================

@router.post("/start/{todo_id}", response_model=TimerStatusResponse)
async def start_timer(todo_id: int, db: AsyncSession = Depends(get_db)):
    """开始任务计时（自动停止其他正在进行的计时，包括状态）"""
    # 检查任务是否存在
    todo = await db.get(TodoItem, todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 自动停止所有正在进行的计时（包括状态）
    await _stop_all_running(db)

    # 创建新的计时记录
    now = datetime.now()
    new_log = TimeLog(
        todo_id=todo_id,
        start_time=now,
        category=todo.category,
        activity_type="task",
    )
    db.add(new_log)
    await db.flush()

    return TimerStatusResponse(
        is_running=True,
        todo_id=todo_id,
        todo_title=todo.title,
        todo_category=todo.category,
        start_time=now,
        elapsed_seconds=0,
        time_log_id=new_log.id,
        activity_type="task",
    )


@router.post("/stop/{todo_id}", response_model=TimerStatusResponse)
async def stop_timer(todo_id: int, db: AsyncSession = Depends(get_db)):
    """停止任务计时"""
    result = await db.execute(
        select(TimeLog).where(
            TimeLog.todo_id == todo_id,
            TimeLog.end_time.is_(None),
        )
    )
    running_log = result.scalars().first()
    if not running_log:
        raise HTTPException(status_code=404, detail="该任务没有正在进行的计时")

    now = datetime.now()
    running_log.end_time = now
    running_log.duration_seconds = int((now - running_log.start_time).total_seconds())

    return TimerStatusResponse(
        is_running=False,
        todo_id=todo_id,
        elapsed_seconds=running_log.duration_seconds,
        time_log_id=running_log.id,
        activity_type="task",
    )


# ==================== 状态计时操作 ====================

@router.get("/status/presets", response_model=list[StatusPreset])
async def get_status_presets():
    """获取预设状态列表"""
    return STATUS_PRESETS


@router.post("/status/start", response_model=TimerStatusResponse)
async def start_status(
    label: str = Query(..., description="状态标签"),
    emoji: str = Query("⏱️", description="状态 emoji"),
    db: AsyncSession = Depends(get_db),
):
    """开始状态计时（自动停止其他正在进行的计时，包括任务）"""
    # 自动停止所有正在进行的计时
    await _stop_all_running(db)

    now = datetime.now()
    new_log = TimeLog(
        todo_id=None,
        start_time=now,
        category=f"status:{label}",
        activity_type="status",
        status_label=label,
        status_emoji=emoji,
    )
    db.add(new_log)
    await db.flush()

    # 习惯自动打卡：状态标签命中习惯关键词（如"洗澡""爬山"），失败不影响计时
    try:
        from app.services.todo_service import auto_checkin_habits
        await auto_checkin_habits(db, text=label)
    except Exception:
        pass

    return TimerStatusResponse(
        is_running=True,
        start_time=now,
        elapsed_seconds=0,
        time_log_id=new_log.id,
        activity_type="status",
        status_label=label,
        status_emoji=emoji,
    )


@router.post("/status/stop", response_model=TimerStatusResponse)
async def stop_status(db: AsyncSession = Depends(get_db)):
    """停止当前状态计时"""
    result = await db.execute(
        select(TimeLog).where(
            TimeLog.activity_type == "status",
            TimeLog.end_time.is_(None),
        )
    )
    running_log = result.scalars().first()
    if not running_log:
        raise HTTPException(status_code=404, detail="没有正在进行的状态计时")

    now = datetime.now()
    running_log.end_time = now
    running_log.duration_seconds = int((now - running_log.start_time).total_seconds())

    return TimerStatusResponse(
        is_running=False,
        elapsed_seconds=running_log.duration_seconds,
        time_log_id=running_log.id,
        activity_type="status",
        status_label=running_log.status_label,
        status_emoji=running_log.status_emoji,
    )


# ==================== 通用查询 ====================

@router.get("/current", response_model=TimerStatusResponse)
async def get_current_timer(db: AsyncSession = Depends(get_db)):
    """获取当前正在计时的任务或状态"""
    result = await db.execute(
        select(TimeLog).where(TimeLog.end_time.is_(None))
    )
    running_log = result.scalars().first()

    if not running_log:
        return TimerStatusResponse(is_running=False)

    elapsed = int((datetime.now() - running_log.start_time).total_seconds())

    if running_log.activity_type == "status":
        return TimerStatusResponse(
            is_running=True,
            start_time=running_log.start_time,
            elapsed_seconds=elapsed,
            time_log_id=running_log.id,
            activity_type="status",
            status_label=running_log.status_label,
            status_emoji=running_log.status_emoji,
        )

    # 任务计时
    todo = await db.get(TodoItem, running_log.todo_id) if running_log.todo_id else None

    return TimerStatusResponse(
        is_running=True,
        todo_id=running_log.todo_id,
        todo_title=todo.title if todo else None,
        todo_category=todo.category if todo else None,
        start_time=running_log.start_time,
        elapsed_seconds=elapsed,
        time_log_id=running_log.id,
        activity_type="task",
    )


@router.get("/total/{todo_id}")
async def get_todo_total_time(todo_id: int, db: AsyncSession = Depends(get_db)):
    """获取某个任务的累计时间（秒），包括正在计时的"""
    finished_result = await db.execute(
        select(func.sum(TimeLog.duration_seconds)).where(
            TimeLog.todo_id == todo_id,
            TimeLog.end_time.is_not(None),
        )
    )
    finished_seconds = finished_result.scalar() or 0

    running_result = await db.execute(
        select(TimeLog).where(
            TimeLog.todo_id == todo_id,
            TimeLog.end_time.is_(None),
        )
    )
    running_log = running_result.scalars().first()
    running_seconds = 0
    if running_log:
        running_seconds = int((datetime.now() - running_log.start_time).total_seconds())

    total_seconds = finished_seconds + running_seconds
    total_minutes = round(total_seconds / 60) if total_seconds > 0 else 0

    return {
        "todo_id": todo_id,
        "total_seconds": total_seconds,
        "total_minutes": total_minutes,
        "is_running": running_log is not None,
    }


@router.get("/today", response_model=list[TimeLogResponse])
async def get_today_logs(db: AsyncSession = Depends(get_db)):
    """获取今日所有时间记录（包括任务和状态）"""
    today_start = datetime.combine(date.today(), datetime.min.time())

    result = await db.execute(
        select(TimeLog)
        .where(TimeLog.start_time >= today_start)
        .order_by(TimeLog.start_time)
    )
    logs = result.scalars().all()

    response = []
    for log in logs:
        resp = TimeLogResponse.model_validate(log)
        if log.activity_type == "status":
            resp.todo_title = f"{log.status_emoji} {log.status_label}"
        elif log.todo_id:
            todo = await db.get(TodoItem, log.todo_id)
            resp.todo_title = todo.title if todo else f"任务#{log.todo_id}"
        else:
            resp.todo_title = "未知"
        response.append(resp)

    return response


@router.get("/analysis", response_model=TimeAnalysisResponse)
async def get_time_analysis(
    days: int = 7,
    start_date: str = None,
    end_date: str = None,
    target_date: str = None,
    db: AsyncSession = Depends(get_db),
):
    """获取时间分析数据（指定日期时间轴 + 分类统计 + N天趋势）
    
    target_date: 可选，指定时间轴要查询的日期（YYYY-MM-DD），默认为今天
    """

    # 确定分析时间范围
    if start_date and end_date:
        range_start = datetime.combine(date.fromisoformat(start_date), datetime.min.time())
        range_end = datetime.combine(date.fromisoformat(end_date), datetime.max.time())
    else:
        range_end = datetime.now()
        range_start = datetime.combine(date.today() - timedelta(days=days - 1), datetime.min.time())

    # 时间轴目标日期（支持按天查看）
    if target_date:
        timeline_date = date.fromisoformat(target_date)
    else:
        timeline_date = date.today()
    timeline_start = datetime.combine(timeline_date, datetime.min.time())
    timeline_end = datetime.combine(timeline_date, datetime.max.time())

    # 1. 指定日期时间轴
    today_result = await db.execute(
        select(TimeLog)
        .where(TimeLog.start_time >= timeline_start, TimeLog.start_time <= timeline_end)
        .order_by(TimeLog.start_time)
    )
    today_logs_raw = today_result.scalars().all()

    today_logs = []
    for log in today_logs_raw:
        resp = TimeLogResponse.model_validate(log)
        # 标准化分类（合并 status:工作 → work 等）
        resp.category = normalize_category(resp.category)
        if log.activity_type == "status":
            resp.todo_title = f"{log.status_emoji} {log.status_label}"
        elif log.todo_id:
            todo = await db.get(TodoItem, log.todo_id)
            resp.todo_title = todo.title if todo else f"任务#{log.todo_id}"
        else:
            resp.todo_title = "未知"
        today_logs.append(resp)

    # 2. 按分类聚合（在整个范围内）
    cat_result = await db.execute(
        select(
            TimeLog.category,
            func.sum(TimeLog.duration_seconds).label("total_seconds"),
            func.count(TimeLog.id).label("count"),
        )
        .where(
            TimeLog.start_time >= range_start,
            TimeLog.end_time.is_not(None),
        )
        .group_by(TimeLog.category)
    )
    category_stats = []
    # 合并后的分类统计（normalize 可能导致多个原始分类映射到同一个）
    merged_cats: dict[str, dict] = {}
    for row in cat_result.all():
        cat = normalize_category(row.category)
        if cat in merged_cats:
            merged_cats[cat]["total_seconds"] += (row.total_seconds or 0)
            merged_cats[cat]["count"] += (row.count or 0)
        else:
            merged_cats[cat] = {
                "total_seconds": row.total_seconds or 0,
                "count": row.count or 0,
            }
    for cat, data in merged_cats.items():
        category_stats.append(TimeStatsCategory(
            category=cat,
            total_seconds=data["total_seconds"],
            count=data["count"],
        ))

    # 3. 今日总计
    today_total = 0
    today_task_ids = set()
    for log in today_logs_raw:
        if log.duration_seconds:
            today_total += log.duration_seconds
        elif log.end_time is None:
            today_total += int((datetime.now() - log.start_time).total_seconds())
        if log.todo_id:
            today_task_ids.add(log.todo_id)

    # 4. 最近 N 天趋势
    daily_stats = []
    for i in range(days):
        day = date.today() - timedelta(days=days - 1 - i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = datetime.combine(day, datetime.max.time())

        day_result = await db.execute(
            select(
                TimeLog.category,
                func.sum(TimeLog.duration_seconds).label("total_seconds"),
            )
            .where(
                TimeLog.start_time >= day_start,
                TimeLog.start_time <= day_end,
                TimeLog.end_time.is_not(None),
            )
            .group_by(TimeLog.category)
        )

        day_categories: dict[str, int] = {}
        day_total = 0
        for row in day_result.all():
            cat = normalize_category(row.category)
            secs = row.total_seconds or 0
            # 累加（合并后可能有多个原始分类映射到同一个）
            day_categories[cat] = day_categories.get(cat, 0) + secs
            day_total += secs

        daily_stats.append(TimeDailyStats(
            date=day.isoformat(),
            total_seconds=day_total,
            categories=day_categories,
        ))

    return TimeAnalysisResponse(
        today_logs=today_logs,
        category_stats=category_stats,
        total_seconds=today_total,
        total_tasks=len(today_task_ids),
        daily_stats=daily_stats,
    )
