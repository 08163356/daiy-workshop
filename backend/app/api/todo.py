"""待办模块 API"""

import logging
from typing import Optional
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, desc, case, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.todo import TodoItem, RecurringTask, InboxHistory, TodoComment
from app.schemas.todo import (
    TodoCreate, TodoUpdate, TodoResponse, TodoListItem, TodoOverview,
    BatchInputRequest, AIEvaluationResult, BatchSaveRequest,
    RecurringTaskCreate, RecurringTaskUpdate, RecurringTaskResponse,
    ReviewStats, SummaryRequest, SummaryResponse,
    DiaryActionItem, ImportActionsRequest,
    TodoAskRequest, TodoAskResult,
    InboxHistoryResponse, InboxHistorySaveRequest,
    TodoCommentCreate, TodoCommentResponse,
    CoreSetRequest, CoreReviewRequest, CoreReviewResult,
)
from app.schemas.investment import ListResponse
from app.services.todo_service import (
    evaluate_batch_input, evaluate_batch_input_stream,
    get_ai_suggestions, generate_summary_report,
    get_overview_data, get_today_plan, get_review_stats,
    get_diary_action_items, check_in_habit, undo_check_in, auto_checkin_habits,
    ask_todos, ai_schedule_todos,
    set_core, get_current_core, core_review,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/todo", tags=["待办模块"])


async def _attach_child_progress(db: AsyncSession, items: list[TodoItem]) -> list[TodoItem]:
    """批量附加子任务完成统计（单次聚合查询，避免 N+1）

    给每个待办挂上 child_total / child_done，前端在任意能看到任务的地方
    （全部待办 / 总览 / 日历 / 今日计划 ...）都能直接展示进度，
    不必每个页面单独去加载子任务列表。
    """
    if not items:
        return items
    parent_ids = [i.id for i in items]
    rows = (
        await db.execute(
            select(
                TodoItem.parent_id,
                func.count(TodoItem.id),
                func.sum(case((TodoItem.status == "completed", 1), else_=0)),
            )
            .where(TodoItem.parent_id.in_(parent_ids))
            .group_by(TodoItem.parent_id)
        )
    ).all()
    stat = {r[0]: (r[1] or 0, r[2] or 0) for r in rows}
    for i in items:
        total, done = stat.get(i.id, (0, 0))
        i.child_total = total
        i.child_done = done
    return items


# ==================== 总览 ====================

@router.get("/overview", response_model=TodoOverview)
async def get_overview(db: AsyncSession = Depends(get_db)):
    """获取待办系统总览"""
    data = await get_overview_data(db)
    return TodoOverview(**data)


# ==================== 今日计划 ====================

@router.get("/today")
async def get_today(db: AsyncSession = Depends(get_db)):
    """获取今日计划"""
    items = await get_today_plan(db)
    await _attach_child_progress(db, items)
    return {"items": [TodoListItem.model_validate(i) for i in items]}


# ==================== CRUD ====================

@router.get("", response_model=ListResponse)
async def list_todos(
    status: Optional[str] = None,
    quadrant: Optional[int] = None,
    category: Optional[str] = None,
    ai_category: Optional[str] = None,
    keyword: Optional[str] = None,
    completion: Optional[str] = Query(None, description="完成情况筛选: done/undone"),
    sort_by: str = Query("created_at", description="排序: created_at/urgency/importance/smart"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    include_children: bool = Query(False, description="是否包含子任务（全部待办页面需要）"),
    db: AsyncSession = Depends(get_db),
):
    """获取待办列表（支持筛选）"""
    query = select(TodoItem).where(TodoItem.parent_id.is_(None))
    count_query = select(func.count(TodoItem.id)).where(TodoItem.parent_id.is_(None))

    if status:
        query = query.where(TodoItem.status == status)
        count_query = count_query.where(TodoItem.status == status)
    if quadrant:
        query = query.where(TodoItem.quadrant == quadrant)
        count_query = count_query.where(TodoItem.quadrant == quadrant)
    if category:
        query = query.where(TodoItem.category == category)
        count_query = count_query.where(TodoItem.category == category)
    if ai_category:
        query = query.where(TodoItem.ai_category == ai_category)
        count_query = count_query.where(TodoItem.ai_category == ai_category)
    if keyword:
        query = query.where(TodoItem.title.contains(keyword))
        count_query = count_query.where(TodoItem.title.contains(keyword))

    # 完成情况筛选
    if completion == "done":
        query = query.where(TodoItem.status.in_(["completed", "cancelled", "wont_fix"]))
        count_query = count_query.where(TodoItem.status.in_(["completed", "cancelled", "wont_fix"]))
    elif completion == "undone":
        query = query.where(TodoItem.status.notin_(["completed", "cancelled", "wont_fix"]))
        count_query = count_query.where(TodoItem.status.notin_(["completed", "cancelled", "wont_fix"]))

    # 排序
    # smart 排序：进行中 > 已计划 > 已评估 > 收集箱 > 已推迟 > 不解决 > 已取消 > 已完成
    status_priority = case(
        (TodoItem.status == "in_progress", 1),
        (TodoItem.status == "planned", 2),
        (TodoItem.status == "evaluated", 3),
        (TodoItem.status == "inbox", 4),
        (TodoItem.status == "deferred", 5),
        (TodoItem.status == "wont_fix", 6),
        (TodoItem.status == "cancelled", 7),
        (TodoItem.status == "completed", 8),
        else_=9,
    )

    if sort_by == "smart":
        query = query.order_by(asc(status_priority), desc(TodoItem.urgency), desc(TodoItem.importance), desc(TodoItem.created_at))
    elif sort_by == "urgency":
        query = query.order_by(desc(TodoItem.urgency), desc(TodoItem.importance))
    elif sort_by == "importance":
        query = query.order_by(desc(TodoItem.importance), desc(TodoItem.urgency))
    else:
        query = query.order_by(desc(TodoItem.created_at))

    total = await db.scalar(count_query)
    result = await db.execute(query.offset(skip).limit(limit))
    parent_items = list(result.scalars())
    await _attach_child_progress(db, parent_items)

    # include_children=true 时，额外查询子任务附加到结果中
    if include_children and parent_items:
        parent_ids = [p.id for p in parent_items]
        children_result = await db.execute(
            select(TodoItem).where(TodoItem.parent_id.in_(parent_ids))
            .order_by(desc(TodoItem.urgency), TodoItem.created_at, TodoItem.id)
        )
        children = list(children_result.scalars())
        all_items = parent_items + children
    else:
        all_items = parent_items

    items = [TodoListItem.model_validate(e) for e in all_items]
    return ListResponse(total=total or 0, items=items)


@router.post("", response_model=TodoResponse)
async def create_todo(data: TodoCreate, db: AsyncSession = Depends(get_db)):
    """创建待办，支持同时创建子任务，创建后异步触发AI分类（不阻塞）"""
    import asyncio
    from app.services.todo_async_eval import async_evaluate_todo

    sub_tasks = data.sub_tasks or []
    # skip_ai_eval 是接口控制字段，不是模型列，必须从 model_dump 排除
    item = TodoItem(**data.model_dump(exclude={"sub_tasks", "skip_ai_eval"}))
    # 子任务未显式指定象限时继承父任务象限，子任务的优先级展示才有意义
    if item.parent_id and data.quadrant == 4:
        parent = await db.get(TodoItem, item.parent_id)
        if parent:
            item.quadrant = parent.quadrant
    db.add(item)
    await db.flush()
    await db.refresh(item)

    # 创建子任务
    for sub_title in sub_tasks:
        if sub_title.strip():
            child = TodoItem(
                title=sub_title.strip(),
                status=item.status,
                source="manual",
                parent_id=item.id,
                category=item.category,
                quadrant=item.quadrant,
            )
            db.add(child)
    if sub_tasks:
        await db.flush()

    # 没有AI评估且是默认四象限(4)时，后台异步AI分类
    # 只对父任务评估：子任务的语义依附于父任务，逐个评估既浪费又容易跑偏
    # skip_ai_eval：新建表单默认不做 AI 评估，用户显式开启才评估
    if (
        not data.skip_ai_eval
        and not item.ai_evaluation
        and item.quadrant == 4
        and item.parent_id is None
        and item.status in ("planned", "inbox")
    ):
        asyncio.create_task(async_evaluate_todo(item.id, item.title, item.description))

    await _attach_child_progress(db, [item])
    return TodoResponse.model_validate(item)


# ==================== 批量输入 & AI 评估 ====================

@router.post("/batch-input")
async def batch_input(data: BatchInputRequest, db: AsyncSession = Depends(get_db)):
    """批量输入（简单保存为 inbox 状态）"""
    lines = [l.strip() for l in data.content.strip().split("\n") if l.strip()]
    items = []
    for line in lines:
        # 去掉序号前缀
        clean = line.lstrip("0123456789.-、）) ·•")
        if clean:
            item = TodoItem(title=clean, status="inbox", source="manual")
            db.add(item)
            items.append(clean)
    await db.flush()
    return {"message": f"已保存 {len(items)} 条待办到收集箱", "count": len(items)}


@router.post("/evaluate")
async def evaluate_todos(data: BatchInputRequest, db: AsyncSession = Depends(get_db)):
    """AI 评估批量输入"""
    try:
        result = await evaluate_batch_input(db, data.content)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 评估失败: {str(e)}")


@router.post("/evaluate/stream")
async def evaluate_todos_stream(data: BatchInputRequest, db: AsyncSession = Depends(get_db)):
    """流式 AI 评估批量输入（SSE）

    返回 Server-Sent Events 流：
    - type=chunk: AI 输出的 Markdown 文本片段
    - type=status: 状态消息
    - type=done: 评估完成，附结构化结果
    - type=error: 错误信息
    """
    import json
    import logging

    logger = logging.getLogger(__name__)

    async def event_generator():
        try:
            async for chunk in evaluate_batch_input_stream(db, data.content):
                yield chunk
        except Exception as e:
            logger.error(f"流式待办评估失败: {e}")
            error_data = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/batch-save")
async def batch_save(data: BatchSaveRequest, db: AsyncSession = Depends(get_db)):
    """批量保存确认的待办（支持父子关系）"""
    saved = []
    # 第一轮：保存非 ai_split 的项目（父任务）
    parent_map: dict[str, int] = {}  # title -> id，用于子任务关联父ID
    for item_data in data.items:
        if item_data.source != 'ai_split':
            item = TodoItem(**item_data.model_dump())
            item.status = "evaluated"
            db.add(item)
            await db.flush()
            parent_map[item_data.title] = item.id
            saved.append(item_data.title)

    # 第二轮：保存 ai_split 的子任务，关联 parent_id
    for item_data in data.items:
        if item_data.source == 'ai_split':
            item = TodoItem(**item_data.model_dump())
            item.status = "evaluated"
            # 从 description 中提取父任务标题来关联
            if item_data.description and item_data.description.startswith("拆分自: "):
                parent_title = item_data.description[4:]  # "拆分自: xxx" -> "xxx"
                for ptitle, pid in parent_map.items():
                    if ptitle in parent_title or parent_title in ptitle:
                        item.parent_id = pid
                        break
            db.add(item)
            saved.append(item_data.title)

    await db.flush()
    return {"message": f"已保存 {len(saved)} 条待办", "count": len(saved)}


# ==================== 分类 ====================

@router.get("/categories")
async def get_categories(db: AsyncSession = Depends(get_db)):
    """获取所有分类及统计"""
    result = await db.execute(
        select(TodoItem.category, func.count(TodoItem.id))
        .where(TodoItem.category.isnot(None))
        .group_by(TodoItem.category)
        .order_by(desc(func.count(TodoItem.id)))
    )
    categories = {row[0]: row[1] for row in result}

    # 预设分类
    preset = {
        "work": "工作/项目",
        "learning": "学习/成长",
        "life": "生活/事务",
        "health": "健康/运动",
        "social": "社交/关系",
        "finance": "财务/投资",
        "creative": "创意/探索",
    }

    return {"categories": categories, "preset": preset}


# ==================== 日记联动 ====================

@router.get("/diary-actions")
async def get_diary_actions(db: AsyncSession = Depends(get_db)):
    """获取日记中待认领的 action_items"""
    items = await get_diary_action_items(db)
    return {"items": items}


@router.post("/import-actions")
async def import_actions(data: ImportActionsRequest, db: AsyncSession = Depends(get_db)):
    """用户确认导入日记 action_items"""
    imported = 0
    for item in data.items:
        diary_id = item.get("diary_id")
        action = item.get("action_item", "")
        if action:
            todo = TodoItem(
                title=action,
                status="evaluated",
                source="diary",
                source_id=diary_id,
            )
            db.add(todo)
            imported += 1
    await db.flush()
    return {"message": f"已导入 {imported} 条待办", "count": imported}


# ==================== 回顾统计 ====================

@router.get("/review")
async def get_review(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """获取回顾统计数据"""
    stats = await get_review_stats(db, start_date, end_date)
    return stats


@router.post("/review/summary", response_model=SummaryResponse)
async def get_review_summary(data: SummaryRequest, db: AsyncSession = Depends(get_db)):
    """AI 生成总结报告（纯展示不存储）"""
    try:
        days = (data.end_date - data.start_date).days
        if days <= 1:
            period = "日"
        elif days <= 7:
            period = "周"
        else:
            period = "月"
        result = await generate_summary_report(db, data.start_date, data.end_date, period)
        return SummaryResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成总结失败: {str(e)}")


# ==================== 重复任务/习惯 ====================

@router.get("/recurring")
async def list_recurring(db: AsyncSession = Depends(get_db)):
    """获取重复任务列表"""
    result = await db.execute(
        select(RecurringTask).order_by(desc(RecurringTask.streak))
    )
    items = [RecurringTaskResponse.model_validate(t) for t in result.scalars()]
    return {"items": items}


@router.post("/recurring", response_model=RecurringTaskResponse)
async def create_recurring(data: RecurringTaskCreate, db: AsyncSession = Depends(get_db)):
    """创建重复任务"""
    task = RecurringTask(
        **data.model_dump(),
        next_due=date.today() + timedelta(days=1) if data.frequency == "daily" else date.today() + timedelta(weeks=1),
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return RecurringTaskResponse.model_validate(task)


@router.put("/recurring/{task_id}", response_model=RecurringTaskResponse)
async def update_recurring(
    task_id: int, data: RecurringTaskUpdate, db: AsyncSession = Depends(get_db)
):
    """更新重复任务"""
    result = await db.execute(
        select(RecurringTask).where(RecurringTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="习惯不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    await db.flush()
    await db.refresh(task)
    return RecurringTaskResponse.model_validate(task)


@router.post("/recurring/{task_id}/check-in", response_model=RecurringTaskResponse)
async def checkin_recurring(task_id: int, db: AsyncSession = Depends(get_db)):
    """习惯打卡"""
    try:
        task = await check_in_habit(db, task_id)
        return RecurringTaskResponse.model_validate(task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/recurring/{task_id}/undo-check-in", response_model=RecurringTaskResponse)
async def undo_checkin_recurring(task_id: int, db: AsyncSession = Depends(get_db)):
    """撤销今日打卡（手动/自动均可，仅限当天）"""
    try:
        task = await undo_check_in(db, task_id)
        return RecurringTaskResponse.model_validate(task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _auto_checkin_from_text(db: AsyncSession, text: str) -> None:
    """待办完成时按任务名尝试习惯自动打卡（静默失败，不影响主流程）"""
    try:
        await auto_checkin_habits(db, text=text)
    except Exception:
        pass


# ==================== AI 主动建议 ====================

@router.get("/suggestions")
async def get_suggestions(db: AsyncSession = Depends(get_db)):
    """获取 AI 主动建议"""
    try:
        result = await get_ai_suggestions(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取建议失败: {str(e)}")


# ==================== 提问功能 ====================

@router.post("/ask", response_model=TodoAskResult)
async def ask_todo_question(data: TodoAskRequest, db: AsyncSession = Depends(get_db)):
    """理解搜索或时间总结意图，返回原始记录的分析与引用任务。"""
    try:
        result = await ask_todos(db, data.question, reference_date=data.reference_date)
        todos = result.get("matched_todos", [])
        await _attach_child_progress(db, todos)
        matched = [TodoListItem.model_validate(t) for t in todos]
        return TodoAskResult(
            answer=result.get("answer", ""),
            matched_todos=matched,
            tokens_used=result.get("tokens_used", 0),
            intent=result.get("intent", "search"),
            start_date=result.get("start_date"),
            end_date=result.get("end_date"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("待办提问失败")
        raise HTTPException(status_code=502, detail="AI服务暂时不可用，请稍后重试")


# ==================== 日历规划 ====================

@router.get("/calendar")
async def get_calendar_data(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """获取日历视图数据：指定日期范围内的任务（支持跨天任务）"""
    from sqlalchemy import or_, and_

    result = await db.execute(
        select(TodoItem)
        .where(
            TodoItem.parent_id.is_(None),
            TodoItem.status.notin_(["cancelled"]),
            or_(
                # 单天任务：scheduled_date 在范围内
                and_(
                    TodoItem.scheduled_date.isnot(None),
                    TodoItem.scheduled_end_date.is_(None),
                    TodoItem.scheduled_date >= start_date,
                    TodoItem.scheduled_date <= end_date,
                ),
                # 跨天任务：日期范围与查询范围有重叠
                and_(
                    TodoItem.scheduled_date.isnot(None),
                    TodoItem.scheduled_end_date.isnot(None),
                    TodoItem.scheduled_date <= end_date,
                    TodoItem.scheduled_end_date >= start_date,
                ),
                # due_date 在范围内
                and_(
                    TodoItem.due_date.isnot(None),
                    TodoItem.due_date >= start_date,
                    TodoItem.due_date <= end_date,
                ),
            )
        )
        .order_by(TodoItem.scheduled_date, TodoItem.sort_order, TodoItem.quadrant, desc(TodoItem.urgency))
    )
    orm_items = list(result.scalars())
    await _attach_child_progress(db, orm_items)
    items = [TodoListItem.model_validate(e) for e in orm_items]
    return {"items": items}


@router.get("/unscheduled")
async def get_unscheduled_todos(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类筛选"),
    quadrant: Optional[int] = Query(None, description="四象限筛选"),
    db: AsyncSession = Depends(get_db),
):
    """获取未安排日期的待办（供日历页面拖拽安排），支持搜索和筛选"""
    base_filter = [
        TodoItem.parent_id.is_(None),
        TodoItem.scheduled_date.is_(None),
        TodoItem.status.notin_(["completed", "cancelled"]),
    ]
    if keyword:
        base_filter.append(TodoItem.title.contains(keyword))
    if category:
        base_filter.append(TodoItem.category == category)
    if quadrant:
        base_filter.append(TodoItem.quadrant == quadrant)

    count_query = select(func.count(TodoItem.id)).where(*base_filter)
    total = await db.scalar(count_query) or 0

    result = await db.execute(
        select(TodoItem)
        .where(*base_filter)
        .order_by(TodoItem.quadrant, desc(TodoItem.urgency))
        .offset(skip)
        .limit(limit)
    )
    orm_items = list(result.scalars())
    await _attach_child_progress(db, orm_items)
    items = [TodoListItem.model_validate(e) for e in orm_items]
    return {"total": total, "items": items}


@router.patch("/schedule")
async def schedule_todo(
    todo_id: int = Query(...),
    scheduled_date: date = Query(...),
    scheduled_end_date: Optional[date] = Query(None, description="计划结束日期（跨天任务）"),
    db: AsyncSession = Depends(get_db),
):
    """快速安排任务到某一天或某个日期范围（跨天任务）"""
    result = await db.execute(
        select(TodoItem).where(TodoItem.id == todo_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="待办不存在")

    item.scheduled_date = scheduled_date
    item.scheduled_end_date = scheduled_end_date
    # 自动将状态从 inbox/evaluated 改为 planned
    if item.status in ("inbox", "evaluated"):
        item.status = "planned"

    await db.flush()
    await db.refresh(item)
    return TodoResponse.model_validate(item)


@router.patch("/complete-with-time")
async def complete_with_time(
    todo_id: int = Query(...),
    actual_minutes: Optional[int] = Query(None, ge=1),
    completion_note: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """完成任务（可选记录实际耗时和备注）
    如果未传 actual_minutes 但有 TimeLog 记录，自动汇总填入
    """
    from app.models.time_log import TimeLog

    result = await db.execute(
        select(TodoItem).where(TodoItem.id == todo_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="待办不存在")

    # 自动停止该任务正在进行的计时
    running_result = await db.execute(
        select(TimeLog).where(
            TimeLog.todo_id == todo_id,
            TimeLog.end_time.is_(None),
        )
    )
    for running_log in running_result.scalars():
        now = datetime.now()
        running_log.end_time = now
        running_log.duration_seconds = int((now - running_log.start_time).total_seconds())

    # 如果未传 actual_minutes，自动从 TimeLog 汇总
    if not actual_minutes:
        total_result = await db.execute(
            select(func.sum(TimeLog.duration_seconds)).where(
                TimeLog.todo_id == todo_id,
                TimeLog.end_time.is_not(None),
            )
        )
        total_seconds = total_result.scalar() or 0
        if total_seconds > 0:
            actual_minutes = max(1, round(total_seconds / 60))

    item.status = "completed"
    item.completed_at = datetime.now()

    # 习惯自动打卡：任务名命中习惯关键词
    await _auto_checkin_from_text(db, item.title)
    # 教练跟进闭环：source=coach 待办完成 → 会话上对应跟进项标 done
    try:
        from app.services.coach_service import close_followup_by_todo
        await close_followup_by_todo(db, item.id)
    except Exception:
        pass

    # 心愿联动：完成待办后，为关联该分类的活跃心愿自动推进进度（保底机制，不依赖AI）
    if item.category:
        try:
            from app.models.wishlist import Wish
            wish_result = await db.execute(
                select(Wish).where(
                    Wish.linked_todo_category == item.category,
                    Wish.status == "active",
                )
            )
            for wish in wish_result.scalars():
                if not wish.milestones:  # 有里程碑的心愿以里程碑完成比例为准，不被待办联动覆盖
                    wish.progress = min(100, wish.progress + (wish.progress_step or 10))
        except Exception as _e:
            logging.getLogger(__name__).warning(f"心愿待办联动失败: {_e}")

    if actual_minutes:
        item.actual_minutes = actual_minutes
    if completion_note:
        # 追加到 completion_notes JSON 数组
        import json as _json
        notes = item.completion_notes or []
        if isinstance(notes, str):
            try:
                notes = _json.loads(notes)
            except Exception:
                notes = []
        notes.append({
            "content": completion_note,
            "timestamp": datetime.now().isoformat(),
        })
        item.completion_notes = notes
        # 兼容旧字段
        item.completion_note = completion_note

    # 父任务完成时自动完成子任务
    children_result = await db.execute(
        select(TodoItem).where(
            TodoItem.parent_id == todo_id,
            TodoItem.status != "completed",
        )
    )
    for child in children_result.scalars():
        child.status = "completed"
        child.completed_at = datetime.now()

    await db.flush()
    await db.refresh(item)
    return TodoResponse.model_validate(item)


@router.post("/ai-schedule")
async def ai_schedule(
    days: int = Query(7, ge=1, le=30, description="排期天数范围"),
    db: AsyncSession = Depends(get_db),
):
    """AI 智能排期：分析所有未排期任务，给出排期建议"""
    try:
        result = await ai_schedule_todos(db, days=days)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 排期失败: {str(e)}")


@router.post("/apply-schedule")
async def apply_schedule(
    schedules: list[dict],
    db: AsyncSession = Depends(get_db),
):
    """批量应用 AI 排期建议"""
    applied = 0
    for s in schedules:
        todo_id = s.get("todo_id")
        scheduled_date_str = s.get("scheduled_date")
        estimated_minutes = s.get("estimated_minutes")

        if not todo_id or not scheduled_date_str:
            continue

        result = await db.execute(
            select(TodoItem).where(TodoItem.id == todo_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            continue

        item.scheduled_date = date.fromisoformat(scheduled_date_str)
        if estimated_minutes and estimated_minutes > 0:
            item.estimated_minutes = estimated_minutes
        if item.status in ("inbox", "evaluated"):
            item.status = "planned"
        applied += 1

    await db.flush()
    return {"message": f"已应用 {applied} 条排期", "count": applied}


# ==================== 重复任务检测 ====================

@router.post("/check-duplicates")
async def check_duplicates(
    titles: list[str],
    db: AsyncSession = Depends(get_db),
):
    """检查新待办标题与已有待办的相似度，返回可能的重复项

    误报防护（此前「录入第一条就提示已存在」的两个原因）：
    1. 只与「未完成」的待办比对 —— 原来把已完成的 787 条历史任务也纳入，
       新任务很容易和历史任务撞上。
    2. 包含关系不再无条件判 0.85 —— 原来「日报」会被「写日报」判成重复。
       现在要求被包含的一方至少 5 字且占长边 60% 以上才算。
    """
    from difflib import SequenceMatcher

    def _similarity(a: str, b: str) -> float:
        if a == b:
            return 1.0
        if a in b or b in a:
            short, long_ = (a, b) if len(a) <= len(b) else (b, a)
            if len(short) < 5 or len(short) / len(long_) < 0.6:
                return 0.0
            return 0.85
        return SequenceMatcher(None, a, b).ratio()

    # 只比对仍未完成的待办
    result = await db.execute(
        select(TodoItem.id, TodoItem.title, TodoItem.status, TodoItem.quadrant, TodoItem.category)
        .where(TodoItem.status.notin_(["cancelled", "completed", "archived"]))
        .order_by(desc(TodoItem.created_at))
        .limit(200)
    )
    existing = result.all()

    duplicates: dict[str, list] = {}
    THRESHOLD = 0.78

    for new_title in titles:
        new_lower = new_title.strip().lower()
        if not new_lower:
            continue
        matches = []
        for eid, etitle, estatus, equadrant, ecategory in existing:
            existing_lower = etitle.strip().lower()
            similarity = _similarity(new_lower, existing_lower)

            if similarity >= THRESHOLD:
                matches.append({
                    "id": eid,
                    "title": etitle,
                    "status": estatus,
                    "quadrant": equadrant,
                    "category": ecategory,
                    "similarity": round(similarity, 2),
                })

        # 按相似度排序，取前3
        matches.sort(key=lambda x: x["similarity"], reverse=True)
        if matches:
            duplicates[new_title] = matches[:3]

    return {"duplicates": duplicates}


# ==================== 收集箱历史 ====================

@router.get("/inbox-history")
async def list_inbox_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取近7天的收集箱历史对话列表"""
    from datetime import timedelta, datetime as dt
    cutoff = dt.now() - timedelta(days=7)
    count_query = select(func.count(InboxHistory.id)).where(InboxHistory.created_at >= cutoff)
    total = await db.scalar(count_query) or 0

    result = await db.execute(
        select(InboxHistory)
        .where(InboxHistory.created_at >= cutoff)
        .order_by(desc(InboxHistory.created_at))
        .offset(skip)
        .limit(limit)
    )
    items = [InboxHistoryResponse.model_validate(h) for h in result.scalars()]
    return {"total": total, "items": items}


@router.get("/inbox-history/{history_id}")
async def get_inbox_history_detail(history_id: int, db: AsyncSession = Depends(get_db)):
    """获取单条收集箱历史详情"""
    result = await db.execute(
        select(InboxHistory).where(InboxHistory.id == history_id)
    )
    history = result.scalar_one_or_none()
    if not history:
        raise HTTPException(status_code=404, detail="历史记录不存在")
    return InboxHistoryResponse.model_validate(history)


@router.post("/inbox-history")
async def save_inbox_history(data: InboxHistorySaveRequest, db: AsyncSession = Depends(get_db)):
    """保存收集箱对话历史"""
    history = InboxHistory(
        user_input=data.user_input,
        ai_markdown=data.ai_markdown,
        structured_items=data.structured_items,
        summary=data.summary,
        saved_count=data.saved_count,
        elapsed_seconds=data.elapsed_seconds,
    )
    db.add(history)
    await db.flush()
    await db.refresh(history)
    return {"id": history.id, "message": "保存成功"}


# ==================== AI 扫描存量任务 ====================

@router.post("/ai-scan")
async def ai_scan(db: AsyncSession = Depends(get_db)):
    """AI 全面扫描存量任务：分析优先级、分类准确性、可直接解答的任务等"""
    from app.services.todo_service import ai_scan_todos
    try:
        result = await ai_scan_todos(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 扫描失败: {str(e)}")


# ==================== 核心任务（本周/本月核心） ====================

@router.get("/core")
async def list_core_tasks(date: str | None = Query(None, description="按该日期所在周/月取核心任务（YYYY-MM-DD），空=服务器今天"),
                          db: AsyncSession = Depends(get_db)):
    """指定日期所在周期的核心任务（week/month 分组；日历点历史日期时回看当时设的核心）"""
    from datetime import date as _date
    target = None
    if date:
        try:
            target = _date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD")
    core = await get_current_core(db, target)
    return {
        "week": [TodoListItem.model_validate(t) for t in core["week"]],
        "month": [TodoListItem.model_validate(t) for t in core["month"]],
        "year": [TodoListItem.model_validate(t) for t in core.get("year", [])],
    }


@router.post("/core-review", response_model=CoreReviewResult)
async def core_alignment_review(data: CoreReviewRequest, db: AsyncSession = Depends(get_db)):
    """核心对齐检查：AI 对照本期实际记录分析核心任务推进情况"""
    try:
        return await core_review(db, data.scope)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"核心对齐检查失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"对齐检查失败: {str(e)}")


# ==================== 单条 CRUD（路径参数路由必须放最后，避免拦截固定路径） ====================

@router.patch("/{todo_id}/core", response_model=TodoResponse)
async def set_todo_core(todo_id: int, data: CoreSetRequest, db: AsyncSession = Depends(get_db)):
    """标记/取消核心任务（scope=week/month/year/null），各周期最多 3 条"""
    try:
        item = await set_core(db, todo_id, data.scope)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TodoResponse.model_validate(item)


@router.get("/{todo_id}/children", response_model=list[TodoListItem])
async def get_todo_children(todo_id: int, db: AsyncSession = Depends(get_db)):
    """获取指定父任务的全部子任务

    供详情弹窗使用，直接按 parent_id 查询，
    不依赖待办列表的分页（老任务排在列表 50 条之外时子任务也能取到）。
    """
    result = await db.execute(
        select(TodoItem)
        .where(TodoItem.parent_id == todo_id)
        .order_by(desc(TodoItem.urgency), TodoItem.created_at, TodoItem.id)
    )
    return [TodoListItem.model_validate(t) for t in result.scalars()]


@router.get("/{todo_id}", response_model=TodoResponse)
async def get_todo(todo_id: int, db: AsyncSession = Depends(get_db)):
    """获取单条待办详情"""
    result = await db.execute(
        select(TodoItem).where(TodoItem.id == todo_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="待办不存在")
    await _attach_child_progress(db, [item])
    return TodoResponse.model_validate(item)


@router.put("/{todo_id}", response_model=TodoResponse)
async def update_todo(todo_id: int, data: TodoUpdate, db: AsyncSession = Depends(get_db)):
    """更新待办（父任务标题/描述变化时异步触发 AI 重新分析）"""
    result = await db.execute(
        select(TodoItem).where(TodoItem.id == todo_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="待办不存在")

    update_data = data.model_dump(exclude_unset=True)

    # 检测标题/描述是否变化（用于触发 AI 重新分析）
    title_changed = "title" in update_data and update_data["title"] != item.title
    desc_changed = "description" in update_data and (update_data.get("description") or None) != (item.description or None)

    for field, value in update_data.items():
        setattr(item, field, value)

    # 如果状态变为 completed，记录完成时间
    if data.status == "completed" and not item.completed_at:
        item.completed_at = datetime.now()
        # 习惯自动打卡：任务名命中习惯关键词
        await _auto_checkin_from_text(db, item.title)
        # 教练跟进闭环
        try:
            from app.services.coach_service import close_followup_by_todo
            await close_followup_by_todo(db, item.id)
        except Exception:
            pass

    await db.flush()
    await db.refresh(item)

    # 父任务标题/描述变化时，异步触发 AI 重新评估（不阻塞）
    if (title_changed or desc_changed) and item.parent_id is None:
        import asyncio
        from app.services.todo_async_eval import async_evaluate_todo
        asyncio.create_task(async_evaluate_todo(item.id, item.title, item.description))

    await _attach_child_progress(db, [item])
    return TodoResponse.model_validate(item)


@router.post("/reorder")
async def reorder_todos(
    todo_ids: list[int] = Query(..., description="按新顺序排列的任务ID列表"),
    db: AsyncSession = Depends(get_db),
):
    """批量更新任务排序顺序（同一天内拖拽排序）"""
    for idx, todo_id in enumerate(todo_ids):
        result = await db.execute(
            select(TodoItem).where(TodoItem.id == todo_id)
        )
        item = result.scalar_one_or_none()
        if item:
            item.sort_order = idx
    await db.flush()
    return {"message": f"已更新 {len(todo_ids)} 条任务排序", "count": len(todo_ids)}


@router.delete("/{todo_id}")
async def delete_todo(todo_id: int, db: AsyncSession = Depends(get_db)):
    """删除待办（级联删除子任务）"""
    result = await db.execute(
        select(TodoItem).where(TodoItem.id == todo_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="待办不存在")

    # 级联删除子任务
    children_result = await db.execute(
        select(TodoItem).where(TodoItem.parent_id == todo_id)
    )
    children = list(children_result.scalars().all())
    for child in children:
        await db.delete(child)

    await db.delete(item)
    await db.flush()
    return {"message": f"删除成功（含 {len(children)} 条子任务）"}


@router.patch("/{todo_id}/toggle", response_model=TodoResponse)
async def toggle_todo(todo_id: int, db: AsyncSession = Depends(get_db)):
    """切换待办完成状态（checkbox）— 父任务完成时子任务自动完成"""
    result = await db.execute(
        select(TodoItem).where(TodoItem.id == todo_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="待办不存在")

    if item.status == "completed":
        item.status = "planned"
        item.completed_at = None
    else:
        item.status = "completed"
        item.completed_at = datetime.now()
        # 习惯自动打卡：任务名命中习惯关键词
        await _auto_checkin_from_text(db, item.title)
        # 教练跟进闭环
        try:
            from app.services.coach_service import close_followup_by_todo
            await close_followup_by_todo(db, item.id)
        except Exception:
            pass

    # 如果是父任务被完成，自动完成所有子任务
    if item.status == "completed":
        # 心愿联动：完成待办后，为关联该分类的活跃心愿自动推进进度（保底机制，不依赖AI）
        if item.category:
            try:
                from app.models.wishlist import Wish
                wish_result = await db.execute(
                    select(Wish).where(
                        Wish.linked_todo_category == item.category,
                        Wish.status == "active",
                    )
                )
                for wish in wish_result.scalars():
                    if not wish.milestones:
                        wish.progress = min(100, wish.progress + (wish.progress_step or 10))
            except Exception as _e:
                logging.getLogger(__name__).warning(f"心愿待办联动失败: {_e}")

        children_result = await db.execute(
            select(TodoItem).where(
                TodoItem.parent_id == todo_id,
                TodoItem.status != "completed",
            )
        )
        for child in children_result.scalars():
            child.status = "completed"
            child.completed_at = datetime.now()

    await db.flush()
    await db.refresh(item)
    return TodoResponse.model_validate(item)


# ==================== 待办评论 ====================

@router.get("/{todo_id}/comments", response_model=list[TodoCommentResponse])
async def list_todo_comments(todo_id: int, db: AsyncSession = Depends(get_db)):
    """获取待办的评论列表（按时间正序），重新打开详情可查看历史想法"""
    result = await db.execute(
        select(TodoComment)
        .where(TodoComment.todo_id == todo_id)
        .order_by(TodoComment.created_at)
    )
    return [TodoCommentResponse.model_validate(c) for c in result.scalars()]


@router.post("/{todo_id}/comments", response_model=TodoCommentResponse)
async def create_todo_comment(
    todo_id: int, data: TodoCommentCreate, db: AsyncSession = Depends(get_db)
):
    """给待办添加一条评论（用于随时记录想法）"""
    todo_result = await db.execute(
        select(TodoItem).where(TodoItem.id == todo_id)
    )
    if not todo_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="待办不存在")

    kind = data.kind if data.kind in ("idea", "lesson") else "idea"
    comment = TodoComment(
        todo_id=todo_id,
        content=data.content.strip(),
        kind=kind,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment)
    return TodoCommentResponse.model_validate(comment)


@router.put("/comments/{comment_id}", response_model=TodoCommentResponse)
async def update_todo_comment(comment_id: int, data: TodoCommentCreate, db: AsyncSession = Depends(get_db)):
    """二次编辑一条想法记录"""
    comment = await db.get(TodoComment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="想法不存在")
    comment.content = data.content.strip()
    await db.flush()
    await db.refresh(comment)
    return TodoCommentResponse.model_validate(comment)


@router.delete("/comments/{comment_id}")
async def delete_todo_comment(comment_id: int, db: AsyncSession = Depends(get_db)):
    """删除一条评论"""
    result = await db.execute(
        select(TodoComment).where(TodoComment.id == comment_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    await db.delete(comment)
    await db.flush()
    return {"message": "评论已删除"}
