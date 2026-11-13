"""Agent 对话循环（function calling + SSE 事件流）

借鉴 harness：消息历史从事件日志投影；思维链/工具调用/正文分流；
一轮 = 一次模型请求 + 其工具调用；上限 8 轮防失控。
"""

import json
import logging
import re
from datetime import date
from typing import Any, AsyncGenerator, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentEvent, AgentSession
from app.services.agent_session import append_event, derive_messages, auto_title, get_voided_seqs
from app.services.agent_tools import get_tool_schemas, execute_tool, TOOLS
from app.services.ai_service import get_active_ai_config, get_user_profile_text

logger = logging.getLogger(__name__)

MAX_ROUNDS = 8

SYSTEM_PROMPT_SECTIONS = [
    "你是用户个人系统「Daily」的内置 AI 助手，能直接查询用户的真实数据（待办、日记、笔记、心力、投资、画像、知识库、个人博客、interview 面试材料）。",
    "## 工具使用规则\n- 用户的问题涉及他自己的数据/记录时，先调工具查真实数据再回答，绝不编造\n- 不确定日期范围时用今天的日期推算\n- **问「某天到某天/本月/本周/上周/近三个月我做了什么、总结」必须调用 get_period_summary 拿到完整原始记录再答；只查 query_todos 不够（会漏掉已完成、计时、备注）**\n- 用户说「不要评价/只总结」时，只陈述记录里的事实，不加评价、建议、打分、鼓励\n- 系统若给出「本轮日期范围解析」，必须用该范围调用 get_period_summary，不要自己改\n- 问博客里有没有、自己写过某篇，用 search_blog（个人博客公开稿，不是知识库）\n- 问收藏过的文章、工具、知识，用 search_knowledge；要记进知识库用 save_knowledge\n- 问面试怎么答、作品集项目、STAR、自我介绍、简历要点，用 search_interview（interview 项目材料，不是博客/知识库）\n- 用户要体检待办时调用 scan_todos，只转述建议\n- 用户要排期时先 propose_schedule，把安排说清楚，同意后再 apply_schedule\n- 工具结果已截断时，告诉用户是部分结果\n- 回答用简体中文，自然口语化，像了解用户的老朋友\n- 提到某条待办时写成 markdown 链接 [标题](todo:数字ID)，用户可以点开",
    "- 用户发来一段零散事情、或说「提取本周要做的事」「生成任务单」「把这些整理成待办」时，调用 draft_tasklist 把内容拆成父子任务草稿；不要直接一条条 create_todo（草稿要让用户先编辑确认）\n"
    "- 系统若给出「本轮真实记录」，必须只基于这些记录回答，不要再改日期、不要编造\n"
    "## 斜杠命令（用户消息以这些前缀开头时的固定动作）\n"
    "- /心力 <内容> → 调用 add_wellbeing，按内容判断 achievement（成就）或 gratitude（感恩）\n"
    "- /待办 <内容> → 调用 create_todo\n"
    "- /知识 <内容> → 调用 save_knowledge，把内容收进知识库\n"
    "这些是写操作，调用后等用户确认即可。/日记 /笔记 /课程 /随笔 /投资 走分析管线；/日报 /周报 /复盘 /月报 走报告管线（你都不需要处理）。其它以 / 开头的词只是普通提问，正常用工具查询后回答。",
]


def _parse_explicit_date_range(text: str) -> tuple[str, str] | None:
    """确定性兜底：解析中文明确日期范围（模型常常算错/根本不调工具）。
    支持「10月26到10月31」「10月26-31」「2026-10-26~2026-10-31」「11/1到11/5」。
    """
    import re as _re
    today = date.today()
    year = today.year
    # 2026-10-26 ~ 2026-10-31
    m = _re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*(?:到|至|~|-|—)\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        return (f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
                f"{m.group(4)}-{int(m.group(5)):02d}-{int(m.group(6)):02d}")
    # 10月26日到10月31日 / 10月26到10月31
    m = _re.search(r"(\d{1,2})月(\d{1,2})日?\s*(?:到|至|~|-|—)\s*(\d{1,2})月(\d{1,2})日?", text)
    if m:
        return (f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}",
                f"{year}-{int(m.group(3)):02d}-{int(m.group(4)):02d}")
    # 10月26到31（同月）
    m = _re.search(r"(\d{1,2})月(\d{1,2})日?\s*(?:到|至|~|-|—)\s*(\d{1,2})日?", text)
    if m:
        return (f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}",
                f"{year}-{int(m.group(1)):02d}-{int(m.group(3)):02d}")
    return None


_SUMMARY_RE = re.compile(r"总结|做了什么|回顾|记录|干了什么|做过|盘点|日程")
_TASKLIST_RE = re.compile(r"生成任务单|提取本周要做|提取要做的|整理成待办|拆成任务|把这些整理")


def resolve_turn_date_range(text: str, today: date | None = None) -> tuple[str, str] | None:
    """明确日期或命名周期 → ISO 区间。不含时间词的「总结」不默认今天。"""
    explicit = _parse_explicit_date_range(text)
    if explicit:
        return explicit
    from app.services.task_context import resolve_named_period_range
    named = resolve_named_period_range(text, today=today)
    if named:
        return named[0].isoformat(), named[1].isoformat()
    return None


def should_inject_period(text: str) -> bool:
    return bool(_SUMMARY_RE.search(text or "") and resolve_turn_date_range(text))


def should_force_tasklist(text: str) -> bool:
    t = (text or "").strip()
    if t.startswith("/任务单"):
        return False
    return bool(_TASKLIST_RE.search(t))


def build_system_prompt(profile_text: str) -> str:
    """分节组装系统提示词：稳定段在前，动态段在后（KV cache 友好）"""
    sections = list(SYSTEM_PROMPT_SECTIONS)
    sections.append(f"## 今天日期\n{date.today().isoformat()}")
    sections.append(f"## 用户画像\n{profile_text or '暂无画像'}")
    return "\n\n".join(sections)


async def llm_stream_round(config: Any, messages: list[dict], tools: list[dict],
                           out: dict, thinking_enabled: bool = True) -> AsyncGenerator[dict, None]:
    """一轮流式 LLM 调用。yield thinking/content 增量事件；out 累积本轮结果（含 tool_calls）"""
    import httpx
    from app.services.ai_service import get_api_url

    url = get_api_url(config)
    payload: dict = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
    if not thinking_enabled:
        # 历史里有缺 reasoning_content 的 assistant 消息时，思维链模式会被 API 拒绝（400）；
        # 该轮降级为非思维链（本轮不显示思维链），保证对话可用
        payload["thinking"] = {"type": "disabled"}
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    tool_calls_map: dict[int, dict] = {}
    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                # 思维链（仅支持思考的模型返回）
                reasoning = delta.get("reasoning_content")
                if reasoning:
                    out["thinking"] += reasoning
                    yield {"type": "thinking", "delta": reasoning}
                content = delta.get("content")
                if content:
                    out["content"] += content
                    yield {"type": "content", "delta": content}
                # 工具调用增量按 index 累积
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = tool_calls_map.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] += fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]

    out["tool_calls"] = [
        {
            "id": slot["id"] or f"call_{i}",
            "type": "function",
            "function": {"name": slot["name"], "arguments": slot["arguments"]},
        }
        for i, (_, slot) in enumerate(sorted(tool_calls_map.items()))
        if slot["name"]
    ]


async def _prepare_context(db: AsyncSession, session: AgentSession):
    """准备一轮对话所需的 config/messages/tools（教练模式注入 coach skill + 跨会话记忆）"""
    from app.models.ai_config import AIConfig

    # 会话绑定模型优先，否则跟随全局
    config = await db.get(AIConfig, session.ai_config_id) if session.ai_config_id else None
    if not config:
        config = await get_active_ai_config(db, module_name="coaching" if session.mode == "coach" else None)

    profile_text = await get_user_profile_text(db)
    system_prompt = build_system_prompt(profile_text)
    try:
        from app.services.skill_service import list_enabled_skills, render_catalog
        catalog = render_catalog(await list_enabled_skills(db))
        if catalog:
            system_prompt += "\n\n" + catalog
    except Exception as e:
        logger.debug(f"skill 目录注入失败: {e}")
    try:
        from app.models.todo import TodoItem
        year_key = str(date.today().year)
        year_cores = list((await db.execute(
            select(TodoItem).where(
                TodoItem.core_scope == "year",
                TodoItem.core_period_key == year_key,
            )
        )).scalars())
        if year_cores:
            system_prompt += "\n\n## 当前年度目标\n" + "\n".join(f"- {t.title}" for t in year_cores)
    except Exception as e:
        logger.debug(f"年度目标注入失败: {e}")
    if session.mode == "coach":
        from app.services.skill_service import get_skill, render_content
        from app.services.coach_service import get_recent_coach_summaries, get_open_followups, get_origin_excerpt
        coach_skill = await get_skill(db, "coach")
        if coach_skill and coach_skill.enabled:
            recent = await get_recent_coach_summaries(db, session.id)
            followups = await get_open_followups(db, session.id)
            coach_block = render_content(
                coach_skill, user_profile=profile_text,
                recent_coach_sessions=recent or "（这是第一次教练对话）",
                open_followups=followups or "（没有未关闭的跟进项）",
            )
            coach_skill.use_count += 1
            coach_skill.last_used_revision = coach_skill.revision
            await db.flush()
            system_prompt = system_prompt + "\n\n" + coach_block
        # 深挖来源摘录（日记/笔记/提问）：服务端注入，不塞用户气泡
        excerpt = await get_origin_excerpt(db, session)
        if excerpt:
            system_prompt += "\n\n" + excerpt
        from app.services.explore_service import get_latest_explore_brief
        explore_brief = await get_latest_explore_brief(db, session.id)
        if explore_brief:
            system_prompt += (
                "\n\n## 最近一次发展评估（只作背景，不要改成四象限问卷）\n"
                + explore_brief
            )
    elif session.mode == "explore":
        from app.services.skill_service import get_skill, render_content
        from app.services.explore_service import get_latest_explore_brief
        explore_skill = await get_skill(db, "human3")
        if explore_skill and explore_skill.enabled:
            explore_brief = await get_latest_explore_brief(db, session.id)
            explore_block = render_content(
                explore_skill, user_profile=profile_text,
                recent_explore=explore_brief or "（这是第一次发展评估）",
            )
            explore_skill.use_count += 1
            explore_skill.last_used_revision = explore_skill.revision
            await db.flush()
            system_prompt = system_prompt + "\n\n" + explore_block
    history = await derive_messages(db, session.id)
    messages = [{"role": "system", "content": system_prompt}] + history
    # 上下文压缩：超阈值先 prune，必要时 LLM checkpoint（surface_op replace）
    try:
        from app.services.compaction import maybe_compact
        messages = await maybe_compact(db, session, messages)
    except Exception as e:
        logger.debug(f"压缩检查失败（不影响对话）: {e}")
    return config, messages, get_tool_schemas()


def _history_thinking_complete(messages: list[dict]) -> bool:
    """历史里每条 assistant 消息都有 reasoning_content 才允许开思维链（否则 API 400）"""
    return all(
        m.get("role") != "assistant" or bool(m.get("reasoning_content"))
        for m in messages
    )


async def _set_status(db: AsyncSession, session: AgentSession, status: str) -> None:
    session.status = status
    await db.flush()
    await db.commit()


async def _claim_pending_steering(db: AsyncSession, session_id: int) -> list[str]:
    """领取未消费的 steering 插话：标记 claimed + 升格为 user_message 事件（harness 语义裁剪版）。

    被撤回的 steering（message_void 标记）不升格。返回升格后的文本列表。
    """
    result = await db.execute(
        select(AgentEvent).where(
            AgentEvent.session_id == session_id, AgentEvent.event_type == "steering"
        ).order_by(AgentEvent.seq)
    )
    events = list(result.scalars())
    if not events:
        return []
    all_events = await db.execute(
        select(AgentEvent).where(AgentEvent.session_id == session_id)
    )
    voided = await get_voided_seqs(list(all_events.scalars()))
    texts: list[str] = []
    for ev in events:
        if (ev.payload or {}).get("claimed") or ev.seq in voided:
            continue
        content = (ev.payload or {}).get("content", "")
        ev.payload = {**ev.payload, "claimed": True}
        if content:
            await append_event(db, session_id, "user_message", {"content": content, "source": "steering"})
            texts.append(content)
    await db.flush()
    return texts


async def _run_rounds(
    db: AsyncSession, session: AgentSession, messages: list[dict], config, tools: list[dict]
) -> AsyncGenerator[dict, None]:
    """轮次循环：模型请求 → 工具调用 → 结果回填，直至无工具调用或需确认或超限"""
    thinking_ok = _history_thinking_complete(messages)
    for round_i in range(MAX_ROUNDS):
        # 轮次边界领取插话（harness：不打断当前流，在边界消费）
        steered = await _claim_pending_steering(db, session.id)
        for text in steered:
            messages.append({"role": "user", "content": text})
        if steered:
            yield {"type": "steering_claimed", "count": len(steered)}

        out = {"content": "", "thinking": "", "tool_calls": []}
        async for ev in llm_stream_round(config, messages, tools, out, thinking_ok):
            yield ev

        if not out["tool_calls"]:
            await append_event(db, session.id, "assistant_message", {
                "content": out["content"],
                "thinking": out["thinking"] or None,
            })
            # 轮次要关闭了：最后机会领取插话，有则继续一轮回应插话（harness turn-stopping 语义）
            steered = await _claim_pending_steering(db, session.id)
            if not steered:
                return
            for text in steered:
                messages.append({"role": "user", "content": text})
            yield {"type": "steering_claimed", "count": len(steered)}
            continue

        # 有工具调用：assistant 消息（带 tool_calls）入日志
        await append_event(db, session.id, "assistant_message", {
            "content": out["content"],
            "tool_calls": out["tool_calls"],
            "thinking": out["thinking"] or None,
        })
        assistant_msg: dict = {
            "role": "assistant",
            "content": out["content"] or None,
            "tool_calls": out["tool_calls"],
        }
        # 思维链模式：带 tool_calls 的消息后续轮次必须回传 reasoning_content（否则 400）
        if out["thinking"]:
            assistant_msg["reasoning_content"] = out["thinking"]
        messages.append(assistant_msg)

        calls = out["tool_calls"]
        for i, call in enumerate(calls):
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_call", "name": name, "args": args}

            tool = TOOLS.get(name)
            if tool and tool.requires_confirm:
                # 写操作：落 confirm_pending 日志并中断本轮，等用户确认（fail-closed）
                await append_event(db, session.id, "confirm_pending", {
                    "tool_call_id": call["id"], "name": name, "args": args,
                })
                # 同一消息里排在该确认之后的调用不再执行，但必须补 tool_result，
                # 否则历史投影里 assistant 的 tool_calls 缺 tool 响应，后续请求会被模型 API 拒绝（400）
                for skipped in calls[i + 1:]:
                    await append_event(db, session.id, "tool_result", {
                        "tool_call_id": skipped["id"],
                        "name": skipped["function"]["name"],
                        "content": "（前一个写操作等待用户确认，本次未执行；确认后可重新发起）",
                    })
                yield {"type": "confirm_required", "tool_call_id": call["id"], "name": name, "args": args}
                return

            # 教练会话内建任务自动带来源（追溯链：待办 → 本次教练会话）
            if name == "create_todo" and session.mode == "coach":
                args = {**args, "source": "coach", "source_id": session.id}
            result = await execute_tool(db, name, args)
            result_text = result.get("content") or result.get("error") or ""
            await append_event(db, session.id, "tool_result", {
                "tool_call_id": call["id"], "name": name, "content": result_text,
            })
            yield {
                "type": "tool_result", "name": name,
                "summary": result_text[:200], "error": "error" in result,
            }
            # 任务单草稿：把结构化 groups 发给前端，渲染可编辑卡片（不写库）
            if result.get("draft"):
                groups = result["draft"].get("groups") or []
                await append_event(db, session.id, "tasklist_draft", {"groups": groups})
                yield {"type": "tasklist_draft", "groups": groups}
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result_text})
    else:
        fallback = "（已达到最大工具调用轮数，请换个问法或拆分问题）"
        await append_event(db, session.id, "assistant_message", {"content": fallback})
        yield {"type": "content", "delta": fallback}


# ==================== 报告管线（/日报 /周报 /复盘 /月报） ====================
# 报告不走工具回填（工具结果 2000 字截断是报告质量差的根因）：
# get_task_context 全文一次性直注 prompt，不进对话历史，不进工具协议。
# 模板存 prompt_skills（bind_pipeline 绑定），页面可编辑，下次直接生效。

REPORT_PIPELINES = {"/日报": "report_daily", "/周报": "report_weekly", "/复盘": "report_review", "/月报": "report_month"}
REPORT_LABELS = {"report_daily": "日报", "report_weekly": "周报", "report_review": "复盘", "report_month": "月报"}


def _match_report_pipeline(content: str) -> Optional[str]:
    for prefix, key in REPORT_PIPELINES.items():
        if content.strip() == prefix or content.startswith(prefix + " "):
            return key
    return None


def _report_date_range(pipeline_key: str) -> tuple[date, date]:
    from datetime import timedelta
    today = date.today()
    if pipeline_key == "report_daily":
        return today, today
    if pipeline_key in ("report_weekly", "report_review"):
        return today - timedelta(days=today.weekday()), today
    return today.replace(day=1), today


async def _run_report_pipeline(
    db: AsyncSession, session: AgentSession, pipeline_key: str
) -> AsyncGenerator[dict, None]:
    """报告管线：skill 模板 + 任务全文 → 流式生成（wake gate：无记录不调 LLM）"""
    from app.services.skill_service import get_pipeline_skill, render_content
    from app.services.task_context import get_task_context

    await _set_status(db, session, "running")
    label = REPORT_LABELS[pipeline_key]
    start, end = _report_date_range(pipeline_key)
    date_range = f"{start.isoformat()} 至 {end.isoformat()}" if start != end else start.isoformat()

    skill = await get_pipeline_skill(db, pipeline_key)
    if not skill:
        msg = f"「{label}」模板未配置或已禁用。到 设置 → Skill 管理 里启用或新建一个绑定 {pipeline_key} 的模板。"
        await append_event(db, session.id, "assistant_message", {"content": msg})
        yield {"type": "content", "delta": msg}
        await _set_status(db, session, "idle")
        yield {"type": "done", "session_id": session.id}
        return

    ctx = await get_task_context(db, start, end)
    # wake gate（hermes cron 思想）：本期没有任务记录就不烧 LLM
    if not ctx.items:
        msg = f"{date_range} 没有任务记录，没什么可总结的。先去干点活儿，或者换个周期试试？"
        await append_event(db, session.id, "assistant_message", {"content": msg})
        yield {"type": "content", "delta": msg}
        await _set_status(db, session, "idle")
        yield {"type": "done", "session_id": session.id}
        return

    config = await get_active_ai_config(db)
    if not config:
        yield {"type": "error", "message": "未配置 AI 模型，请先在设置页配置"}
        await _set_status(db, session, "idle")
        return

    profile_text = await get_user_profile_text(db)
    prompt = render_content(skill, user_profile=profile_text, date_range=date_range, task_context=ctx.text)
    # 使用计数+改进有效性度量（hermes patch_generation 思想）
    skill.use_count += 1
    skill.last_used_revision = skill.revision
    await db.flush()

    out = {"content": "", "thinking": "", "tool_calls": []}
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"请生成 {date_range} 的{label}。"},
    ]
    try:
        async for ev in llm_stream_round(config, messages, None, out):
            yield ev
    except Exception as e:
        logger.error(f"报告管线生成失败: {e}", exc_info=True)
        await _set_status(db, session, "idle")
        yield {"type": "error", "message": f"生成失败: {e}"}
        return

    await append_event(db, session.id, "assistant_message", {
        "content": out["content"], "thinking": out["thinking"] or None,
    })
    await auto_title(db, session.id, f"{label} {date_range}")
    await db.refresh(session)
    await _set_status(db, session, "idle")
    yield {"type": "done", "session_id": session.id, "title": session.title}


# ==================== 记录类斜杠命令管线（/日记 /笔记 /投资） ====================
# 复用老 ChatView 的分析链路：流式分析（含当天任务上下文注入）→ 结构化提取 → 确认卡 → 保存
# AI 不可用时降级为直接保存原文。

async def _run_tasklist_pipeline(db: AsyncSession, session: AgentSession, content: str) -> AsyncGenerator[dict, None]:
    """/任务单：确定性拆分成父子任务草稿 → 前端可编辑卡片 → 用户点创建才落库"""
    from app.services.tasklist_service import split_tasklist
    await _set_status(db, session, "running")
    try:
        groups = await split_tasklist(db, content)
    except Exception as e:
        logger.warning(f"任务单拆分失败: {e}")
        msg = f"⚠️ 拆分失败：{e}。可以换种说法，或直接在对话里让我拆。"
        await append_event(db, session.id, "assistant_message", {"content": msg})
        yield {"type": "content", "delta": msg}
        await _set_status(db, session, "idle")
        yield {"type": "done", "session_id": session.id}
        return
    intro = f"我把这段拆成了 {len(groups)} 组任务（{sum(len(g['children']) for g in groups)} 个子任务）。你可以直接改标题、增删条目，确认没问题再创建："
    await append_event(db, session.id, "assistant_message", {"content": intro})
    yield {"type": "content", "delta": intro}
    await append_event(db, session.id, "tasklist_draft", {"groups": groups})
    yield {"type": "tasklist_draft", "groups": groups}
    await _set_status(db, session, "idle")
    yield {"type": "done", "session_id": session.id}


RECORD_PIPELINES = {"/日记": "diary", "/笔记": "reading", "/课程": "course", "/随笔": "selfnote", "/投资": "investment"}
RECORD_TYPE_LABELS = {"diary": "日记", "reading": "笔记", "course": "课程笔记", "selfnote": "随笔", "investment": "投资反思"}
# 课程/随笔复用读书笔记的 AI 分析链（概念抽取/知识关联），仅落库来源类型不同
ANALYSIS_TYPE_ALIAS = {"course": "reading", "selfnote": "reading"}


def _match_record_pipeline(content: str) -> tuple[str, str] | None:
    for prefix, sys_type in RECORD_PIPELINES.items():
        if content.startswith(prefix):
            body = content[len(prefix):].strip()
            if body:
                return sys_type, body
    return None


async def _run_record_pipeline(
    db: AsyncSession, session: AgentSession, system_type: str, content: str,
    images: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    """记录管线：流式分析 → 分析入日志 → 保存确认卡（分析随保存一起落库）"""
    import uuid
    from app.services.ai_service import call_ai_stream

    await _set_status(db, session, "running")
    call_id = f"save_{uuid.uuid4().hex[:12]}"
    label = RECORD_TYPE_LABELS[system_type]
    today = date.today().isoformat()
    title = f"{today} {label}"

    analysis = ""
    thinking = ""
    structured: dict = {}
    failed: str | None = None
    try:
        async for sse_line in call_ai_stream(db, ANALYSIS_TYPE_ALIAS.get(system_type, system_type), content):
            for line in sse_line.strip().split("\n"):
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                try:
                    ev = json.loads(data)
                except json.JSONDecodeError:
                    continue
                ev_type = ev.get("type")
                if ev_type == "chunk":
                    analysis += ev.get("content", "")
                    yield {"type": "content", "delta": ev["content"]}
                elif ev_type == "reasoning":
                    # 思维链增量：透出给前端实时展示，并存入事件供投影回传（思维链模式硬性要求）
                    thinking += ev.get("content", "")
                    yield {"type": "thinking", "delta": ev["content"]}
                elif ev_type == "done":
                    result = ev.get("result") or {}
                    analysis = result.get("analysis_markdown") or analysis
                    structured = result.get("structured_data") or {}
                elif ev_type == "error":
                    failed = ev.get("message") or "AI 分析失败"
    except Exception as e:
        logger.warning(f"记录管线分析失败（{system_type}）: {e}")
        failed = str(e)

    if failed:
        msg_content = f"⚠️ AI 分析暂时不可用（{failed}）。\n可以点下方按钮先把原文存下来，分析以后在详情页再补。"
    else:
        msg_content = analysis + "\n\n---\n以上是分析。想深挖哪一点可以继续聊；确认无误后点下方按钮保存（分析会一起存进去）。"

    # 对话内澄清提问（分析真正触发需要了解用户的地方才问；宁缺毋滥）
    clarify: dict | None = None
    if not failed:
        try:
            from app.services.clarify_service import generate_clarify_questions
            clarify = await generate_clarify_questions(db, label, content, analysis)
        except Exception as e:
            logger.debug(f"澄清提问生成失败（不影响流程）: {e}")
    if clarify:
        await append_event(db, session.id, "clarify_questions", {
            "batch_id": clarify["batch_id"], "questions": clarify["questions"],
            "source_content": content[:2000],
        })
        yield {"type": "questions", "batch_id": clarify["batch_id"], "questions": clarify["questions"]}

    # 合成一轮工具调用：assistant 消息带 tool_calls，确认后 tool_result 补上，投影始终合法
    if system_type == "diary" and not failed:
        summary_title = str((structured or {}).get("title") or "").strip().strip("\"'").replace("\n", " ")
        if summary_title and summary_title.lower() != "null":
            title = summary_title[:40]
    save_args = {
        "record_type": system_type,
        "title": title,
        "content": content,
        "record_date": today,
        "analysis": "" if failed else analysis,
        "structured": structured,
    }
    if images:
        save_args["images"] = images
    await append_event(db, session.id, "assistant_message", {
        "content": msg_content,
        "thinking": thinking or None,
        "tool_calls": [{
            "id": call_id, "type": "function",
            "function": {"name": "__save_record", "arguments": json.dumps(save_args, ensure_ascii=False)},
        }],
    })
    await append_event(db, session.id, "confirm_pending", {
        "tool_call_id": call_id, "name": "__save_record", "args": save_args,
    })
    # 确认卡只展示摘要，完整数据在服务端事件里；带上情绪/标签恢复旧版分析的展示体验
    yield {"type": "confirm_required", "tool_call_id": call_id, "name": "__save_record",
           "args": {"title": f"保存{label}", "content": title,
                    "mood": structured.get("mood"), "tags": structured.get("tags"),
                    "key_issues": (structured.get("key_issues") or [])[:5],
                    "action_items": (structured.get("action_items") or [])[:5]}}

    await auto_title(db, session.id, content[:100])
    await db.refresh(session)
    await _set_status(db, session, "idle")
    yield {"type": "done", "session_id": session.id, "title": session.title}


async def run_agent_turn(
    db: AsyncSession, session: AgentSession, user_content: str,
    images: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    """一轮完整对话：用户消息入日志 → 投影历史 → 多轮工具调用 → 正文入日志

    yield 的 SSE 事件：thinking/content（增量）、tool_call、tool_result、confirm_required、done、error
    """
    # 教练模式入口：/教练 <话题>（会话转为教练模式，前缀不入日志）
    if user_content.strip().startswith("/教练"):
        topic = user_content.strip()[len("/教练"):].strip()
        if session.mode != "coach":
            session.mode = "coach"
            await db.flush()
            await db.commit()
        user_content = topic or "我想开始一次教练对话。请先向我提一个你最想了解的问题。"

    # 探索模式入口：/探索 <话题>（整段会话注入 human3，前缀不入日志）
    if user_content.strip().startswith("/探索"):
        topic = user_content.strip()[len("/探索"):].strip()
        if session.mode != "explore":
            session.mode = "explore"
            await db.flush()
            await db.commit()
        user_content = topic or "我想开始一次发展评估。请用两三句话说明这次会怎么进行，然后只问心智的第一个问题。"

    image_urls = [u for u in (images or []) if isinstance(u, str) and u.startswith("/api/uploads/images/") and ".." not in u][:9]
    await append_event(db, session.id, "user_message", {
        "content": user_content,
        **({"images": image_urls} if image_urls else {}),
    })

    # 只有图片、没有文字：只落库，不送给模型
    if not user_content.strip():
        note = "图片已保存，这次不做分析。"
        await append_event(db, session.id, "assistant_message", {"content": note})
        await auto_title(db, session.id, "图片")
        await _set_status(db, session, "idle")
        yield {"type": "content", "delta": note}
        yield {"type": "done", "session_id": session.id}
        return

    # /任务单 或自然语言「生成任务单/提取本周要做的」：拆成父子任务草稿
    tasklist_body = None
    if user_content.strip().startswith("/任务单"):
        tasklist_body = user_content.strip()[len("/任务单"):].strip()
    elif should_force_tasklist(user_content):
        tasklist_body = user_content.strip()
    if tasklist_body:
        try:
            async for ev in _run_tasklist_pipeline(db, session, tasklist_body):
                yield ev
        except Exception as e:
            logger.error(f"任务单管线失败: {e}", exc_info=True)
            await _set_status(db, session, "idle")
            yield {"type": "error", "message": f"执行失败: {e}"}
        return
    if user_content.strip().startswith("/任务单"):
        yield {"type": "content", "delta": "先写要拆的事情，再发 /任务单。"}
        await append_event(db, session.id, "assistant_message", {"content": "先写要拆的事情，再发 /任务单。"})
        await _set_status(db, session, "idle")
        yield {"type": "done", "session_id": session.id}
        return

    # 报告类斜杠命令走报告管线（skill 模板 + 全文直注，不进工具循环）
    report_key = _match_report_pipeline(user_content)
    if report_key:
        try:
            async for ev in _run_report_pipeline(db, session, report_key):
                yield ev
        except Exception as e:
            logger.error(f"Agent 会话 #{session.id} 报告管线失败: {e}", exc_info=True)
            try:
                await _set_status(db, session, "idle")
            except Exception:
                pass
            yield {"type": "error", "message": f"执行失败: {e}"}
        return

    # 记录类斜杠命令走确定性分析管线（不进 LLM 工具循环）
    matched = _match_record_pipeline(user_content)
    if matched:
        sys_type, body = matched
        try:
            async for ev in _run_record_pipeline(db, session, sys_type, body, image_urls):
                yield ev
        except Exception as e:
            logger.error(f"Agent 会话 #{session.id} 记录管线失败: {e}", exc_info=True)
            try:
                await _set_status(db, session, "idle")
            except Exception:
                pass
            yield {"type": "error", "message": f"执行失败: {e}"}
        return

    # 显式技能调用：/skill:<name> <内容> → 技能正文注入本轮系统提示词（前缀不入日志语义，仅作路由）
    explicit_skill = None
    if user_content.strip().startswith("/skill:"):
        head, _, rest = user_content.strip().partition(" ")
        skill_name = head[len("/skill:"):].strip()
        from app.services.skill_service import get_skill, render_content
        from app.services.ai_service import get_user_profile_text
        skill = await get_skill(db, skill_name)
        if skill and skill.enabled:
            skill.use_count = (skill.use_count or 0) + 1
            await db.flush()
            explicit_skill = render_content(skill, user_profile=await get_user_profile_text(db))
            user_content = rest.strip() or f"请用「{skill.title}」技能和我开始。"
        else:
            yield {"type": "content", "delta": f"技能「{skill_name}」不存在或已停用，到 🧩 Skill 面板检查一下。"}
            await append_event(db, session.id, "assistant_message", {"content": f"技能「{skill_name}」不存在或已停用"})
            await _set_status(db, session, "idle")
            yield {"type": "done", "session_id": session.id}
            return

    try:
        config, messages, tools = await _prepare_context(db, session)
        if explicit_skill:
            # 显式技能：正文追加进 system 段（动态段尾部，本轮生效）
            messages[0]["content"] += f"\n\n## 用户本轮指定技能（必须遵循）\n{explicit_skill}"

        # 总结类 + 明确日期/命名周期：服务端直注待办+日记+笔记+心力，不赌模型调工具
        if should_inject_period(user_content):
            date_range = resolve_turn_date_range(user_content)
            if date_range:
                try:
                    from app.services.task_context import get_period_bundle
                    bundle = await get_period_bundle(
                        db, date.fromisoformat(date_range[0]), date.fromisoformat(date_range[1]),
                    )
                    fact_only = "用户说「不要评价/只总结」时只陈述事实，不加评价、建议或鼓励。" if "不要评价" in user_content or "只总结" in user_content else ""
                    messages[0]["content"] += (
                        f"\n\n## 用户本轮询问的日期范围：{date_range[0]} ~ {date_range[1]}（服务端直注的真实记录）\n"
                        f"{bundle}\n\n必须只基于以上记录回答，不要编造。{fact_only}"
                    )
                except Exception as e:
                    logger.warning(f"日期范围直注失败（退回工具调用）: {e}")

        if not config:
            yield {"type": "error", "message": "未配置 AI 模型，请先在设置页配置"}
            return

        await _set_status(db, session, "running")
        async for ev in _run_rounds(db, session, messages, config, tools):
            yield ev

        # 首条消息后自动生成标题（钉住/已有则跳过）
        await auto_title(db, session.id, user_content)
        await db.refresh(session)
        await _set_status(db, session, "idle")

        # 复盘 nudge（hermes background_review 裁剪）：普通对话累计够量后后台蒸馏经验为候选 skill
        # 教练/探索/管线会话不触发（它们有专门沉淀；管线是任务执行不是经验）
        if session.mode not in ("coach", "explore"):
            try:
                from app.services.review_service import maybe_review_session
                await maybe_review_session(db, session)
            except Exception as e:
                logger.debug(f"复盘触发检查失败（不影响对话）: {e}")

        yield {"type": "done", "session_id": session.id, "title": session.title}

    except Exception as e:
        logger.error(f"Agent 会话 #{session.id} 执行失败: {e}", exc_info=True)
        try:
            await _set_status(db, session, "idle")
        except Exception:
            pass
        yield {"type": "error", "message": f"执行失败: {e}"}


async def resume_after_confirm(
    db: AsyncSession, session: AgentSession, approved: bool
) -> AsyncGenerator[dict, None]:
    """确认后恢复：执行（或跳过）待确认工具，然后继续轮次循环

    从事件日志找最近一条未被 tool_result 处理的 confirm_pending。
    """
    from app.services.agent_session import get_session_events

    events = await get_session_events(db, session.id)
    pending = None
    for ev in reversed(events):
        if ev.event_type == "tool_result":
            break  # 最近的工具调用已处理完，没有待确认
        if ev.event_type == "confirm_pending":
            pending = ev
            break
    if not pending:
        raise ValueError("没有待确认的操作")

    name = pending.payload["name"]
    args = pending.payload.get("args") or {}
    call_id = pending.payload.get("tool_call_id", "")

    try:
        await _set_status(db, session, "running")
        if approved:
            # 教练会话内建任务自动带来源
            if name == "create_todo" and session.mode == "coach":
                args = {**args, "source": "coach", "source_id": session.id}
            result = await execute_tool(db, name, args)
            rejected = False
        else:
            result = {"content": "用户拒绝了这次操作，未执行。"}
            rejected = True

        result_text = result.get("content") or result.get("error") or ""
        await append_event(db, session.id, "tool_result", {
            "tool_call_id": call_id, "name": name, "content": result_text,
        })
        yield {
            "type": "tool_result", "name": name,
            "summary": result_text[:200], "rejected": rejected,
        }

        # 继续循环：日志里已有 assistant(tool_calls) + tool_result，投影即可衔接
        config, messages, tools = await _prepare_context(db, session)
        if not config:
            yield {"type": "error", "message": "未配置 AI 模型"}
            return
        async for ev in _run_rounds(db, session, messages, config, tools):
            yield ev

        await _set_status(db, session, "idle")
        yield {"type": "done", "session_id": session.id}

    except Exception as e:
        logger.error(f"Agent 会话 #{session.id} 确认恢复失败: {e}", exc_info=True)
        try:
            await _set_status(db, session, "idle")
        except Exception:
            pass
        yield {"type": "error", "message": f"执行失败: {e}"}
