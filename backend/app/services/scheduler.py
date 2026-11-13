"""定时任务（hermes cron 裁剪版）：每日 21:00 自动生成日报草稿

wake gate：当天没有任务记录 → 不调 LLM 不建会话（无数据不烧钱）。
生成的日报放进一个独立会话，用户打开 AI 助手就能看到，可以直接接着聊。
"""
import asyncio
import logging
from datetime import date, datetime

import httpx

logger = logging.getLogger(__name__)

DAILY_REPORT_HOUR = 21  # 每天 21 点生成
SCHEDULER_ENABLED = False  # 总开关：用户暂不需要定时日报，改为 False 关闭（想开启改 True 重新部署）

_last_run: dict[str, date] = {}  # 防同一日重复触发


async def generate_scheduled_daily_report() -> bool:
    """生成今日日报草稿会话。返回是否真的生成了（wake gate 可能跳过）"""
    from app.core.database import async_session_maker
    from app.models.agent import AgentSession
    from app.services.agent_session import append_event
    from app.services.ai_service import get_active_ai_config, get_user_profile_text, _build_request
    from app.services.skill_service import get_pipeline_skill, render_content
    from app.services.task_context import get_task_context

    async with async_session_maker() as db:
        today = date.today()
        # wake gate：今天没记录就不生成
        ctx = await get_task_context(db, today, today)
        if not ctx.items:
            logger.info("定时日报 wake gate：今天无任务记录，跳过")
            return False
        # 今天已生成过（用户手动 /日报 过）就不重复
        from sqlalchemy import select
        existing = await db.execute(
            select(AgentSession).where(
                AgentSession.title.like(f"%日报 {today.isoformat()}%"),
            )
        )
        if existing.scalars().first():
            logger.info("定时日报：今天已有日报会话，跳过")
            return False

        skill = await get_pipeline_skill(db, "report_daily")
        config = await get_active_ai_config(db)
        if not skill or not config:
            logger.warning("定时日报：模板或模型未配置，跳过")
            return False

        profile_text = await get_user_profile_text(db)
        prompt = render_content(
            skill, user_profile=profile_text,
            date_range=today.isoformat(), task_context=ctx.text,
        )
        url, headers, payload = _build_request(config, [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"请生成 {today.isoformat()} 的日报。"},
        ])

        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"] or ""
        thinking = data["choices"][0]["message"].get("reasoning_content") or None

        session = AgentSession(title=f"日报 {today.isoformat()}（定时生成）")
        db.add(session)
        await db.flush()
        await append_event(db, session.id, "user_message", {"content": "/日报（定时生成）", "source": "scheduler"})
        await append_event(db, session.id, "assistant_message", {"content": content, "thinking": thinking})
        await db.commit()
        logger.info(f"定时日报已生成：会话 #{session.id}")
        return True


async def scheduler_loop() -> None:
    """每分钟检查一次的常驻调度循环（随服务启动）"""
    if not SCHEDULER_ENABLED:
        logger.info("定时任务调度已关闭（SCHEDULER_ENABLED=False）")
        return
    logger.info(f"定时任务调度启动：每日 {DAILY_REPORT_HOUR}:00 日报")
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.now()
            if now.hour == DAILY_REPORT_HOUR and _last_run.get("daily") != now.date():
                _last_run["daily"] = now.date()
                await generate_scheduled_daily_report()
        except Exception as e:
            logger.warning(f"定时任务异常（下分钟继续）: {e}")
