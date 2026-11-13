"""心力模块 AI 服务

封装 5 个 AI 任务：
1. extract_candidates_from_diary - 从日记内容提取候选成就/感恩
2. extract_candidates_from_note - 从读书笔记提取候选
3. generate_comfort_card - 焦虑模式安抚语生成
4. generate_period_report - 周报/月报生成
5. analyze_correlations - 成就-感恩-情绪关联分析

复用 app.services.ai_service 的模型调用与画像注入能力，所有失败都降级为本地预置文案。
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, date, timedelta
from typing import Optional, Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.wellbeing import (
    WellbeingEntry,
    WellbeingCandidate,
    WellbeingReport,
)
from app.services.ai_service import (
    get_active_ai_config,
    get_user_profile_text,
    _build_request,
    _parse_ai_json,
)

logger = logging.getLogger(__name__)

MODULE_NAME = "wellbeing"

# ---------- Prompt 模板 ----------

EXTRACT_PROMPT = """你是一个善于发现「积极瞬间」的心理疗愈助手。用户的日常文本中往往隐藏着值得肯定的成就、值得感恩的瞬间，但他/她自己常常忽略。

## 用户画像
{user_profile}

## 任务
从下面的{source_label}中识别出 0-5 条值得记入「成就」或「感恩」账户的事件。

## 识别规则
1. **成就（achievement）**：用户做到的事——大到升职加薪买房，小到 6 点早起、坚持运动、克服一次拖延、说出一句不容易的话。注意识别"虽然没说但确实做到"的小事。
2. **感恩（gratitude）**：用户被善待/被支持/被给予的瞬间——别人的帮助、家人的关心、好天气、一顿好饭、身体健康。
3. **强度（intensity 1-5）**：1=微小日常 / 3=值得被记住 / 5=人生级别
4. **分类（category）**：工作 / 家庭 / 健康 / 关系 / 学习 / 其他
5. **置信度（ai_confidence 0-1）**：你对"这件事确实是积极瞬间"的信心
6. 如果文本通篇都是负面情绪没有任何积极点，返回空数组，不要硬挖
7. **不要复述**：用户已经在文中明确说"今天的成就是XX"，可以不重复识别（除非他/她在埋怨自己时其实做到了某事）

## 输入文本
{content}

## 输出 JSON 格式
```json
{
  "items": [
    {
      "type": "achievement",
      "content": "用一句话精炼概括这件事（用第二人称视角写，例如：你今天 6 点起床完成了晨跑）",
      "category": "健康",
      "intensity": 3,
      "ai_confidence": 0.85,
      "ai_reason": "为什么识别为积极瞬间（一句话）",
      "excerpt": "原文中对应的关键句子（30字以内）"
    }
  ]
}
```

重要：只输出 JSON，不要输出其他内容。最多 5 条。如果没有识别到，items 为 []。
"""

COMFORT_PROMPT = """你是用户最信任的、温暖而清醒的朋友。用户此刻正陷入焦虑和自我否定中。

## 用户画像
{user_profile}

## 用户最近的成就片段
{recent_achievements}

## 用户最近的感恩片段
{recent_gratitudes}

## 任务
请用一段 80-150 字的中文，对用户说一段安抚的话。要求：
1. **不要敷衍说"加油"、"会好起来的"** 这类空话
2. 真诚承认他/她此刻的感受是合理的
3. 引用上面 1-2 条具体的成就或感恩事件，提醒他/她"你不是什么都没做好"
4. 不要给行动建议，此刻只需要被看见
5. 像一个真懂他/她的朋友在身边轻声说话，不要排比、不要鸡汤

直接输出这段话，不要任何前缀、Markdown 标记、引号。
"""

REPORT_PROMPT = """你是用户的成长见证者，正在为他/她写一份{period_label}心力账户报告。

## 用户画像
{user_profile}

## 本期数据
- 成就累积：{achievement_count} 条
- 感恩累积：{gratitude_count} 条
- 时间范围：{period_start} 至 {period_end}

## 本期成就清单
{achievements_text}

## 本期感恩清单
{gratitudes_text}

## 任务
请写一份杂志式的{period_label}报告，用 Markdown 输出。结构如下：

### ✨ 本期亮点
（用 2-3 句温暖的话，挑出最值得被记住的 2-3 个瞬间。要具体引用，不要泛泛而谈。）

### 📈 成长曲线
（观察成就/感恩的频率、分类分布、强度变化，给出一句真诚的观察。可以是"你这周特别多在工作上突破"这类。）

### 🔗 关联洞察
（如果发现某些规律：比如运动类成就和好心情同现、家庭感恩频繁、某类事件常被忽略却很重要——指出来。如果数据太少不强行造洞察。）

### 💚 给你的话
（80-120 字，结合用户画像，给一段不鸡汤、不说教、像知己长辈一样的话。强调"你已经在路上了"，对抗"我什么都没做好"的认知扭曲。）

要求：
- 总长 400-600 字
- 真诚、克制、温暖，避免感叹号轰炸
- 直接输出 Markdown，不要任何前后缀说明

"""

# ---------- 降级文案池 ----------

FALLBACK_COMFORT = [
    "焦虑不是你的错，是你太想做好。先停一下，深呼吸。你过去一段时间累积的那些好，不会因为今天的难受就消失。",
    "此刻的难受是真的，但你比你自己以为的要强。看看你之前记下的那些瞬间——它们都是证据。",
    "感觉一切都不够好的时候，请记得：你已经走得比昨天的自己更远了。慢一点也是可以的。",
    "你不需要现在就找到答案。允许自己只是难过一会儿。你做过的好事，会一直在那里等你回头看。",
    "如果今天什么都做不了，那就好好歇着。你已经为很多人和很多事努力过了，包括你自己。",
]


# ---------- 工具：提取 AI Markdown 内容 ----------

async def _ai_call_json(db: AsyncSession, prompt: str, *, max_tokens: int = 1024) -> tuple[dict, str, int]:
    """简单封装：调 AI，期望返回 JSON。返回 (parsed, model_name, tokens)"""
    config = await get_active_ai_config(db, module_name=MODULE_NAME)
    if not config:
        raise RuntimeError("未配置 AI 模型")

    messages = [
        {"role": "system", "content": "你是一个严谨的 JSON 输出助手，只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]
    url, headers, payload = _build_request(config, messages)
    payload["max_tokens"] = min(config.max_tokens, max_tokens)
    payload["temperature"] = 0.3

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    content = data["choices"][0]["message"]["content"]
    tokens = int(data.get("usage", {}).get("total_tokens", 0) or 0)
    parsed = _parse_ai_json(content)
    return parsed, f"{config.provider}/{config.model}", tokens


async def _ai_call_text(db: AsyncSession, prompt: str, *, max_tokens: int = 800, temperature: float = 0.7) -> tuple[str, str, int]:
    """简单封装：调 AI，期望返回纯文本/Markdown。返回 (text, model_name, tokens)"""
    config = await get_active_ai_config(db, module_name=MODULE_NAME)
    if not config:
        raise RuntimeError("未配置 AI 模型")

    messages = [
        {"role": "user", "content": prompt},
    ]
    url, headers, payload = _build_request(config, messages)
    payload["max_tokens"] = min(config.max_tokens, max_tokens)
    payload["temperature"] = temperature

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    content = data["choices"][0]["message"]["content"].strip()
    tokens = int(data.get("usage", {}).get("total_tokens", 0) or 0)
    return content, f"{config.provider}/{config.model}", tokens


# ---------- 任务一：从日记/笔记提取候选项 ----------

async def _extract_candidates(
    db: AsyncSession,
    *,
    source_type: str,
    source_id: int,
    content: str,
    source_label: str,
) -> list[WellbeingCandidate]:
    """通用候选提取，已落库返回 candidate 列表。"""
    if not content or len(content.strip()) < 10:
        return []

    profile_text = await get_user_profile_text(db)
    prompt = (
        EXTRACT_PROMPT
        .replace("{user_profile}", profile_text)
        .replace("{source_label}", source_label)
        .replace("{content}", content[:6000])  # 控制 token
    )

    candidates: list[WellbeingCandidate] = []
    try:
        parsed, model_name, _tokens = await _ai_call_json(db, prompt, max_tokens=1500)
        items = parsed.get("items") or []
        if not isinstance(items, list):
            items = []
        for raw in items[:5]:
            if not isinstance(raw, dict):
                continue
            stype = (raw.get("type") or "").strip()
            if stype not in ("achievement", "gratitude"):
                continue
            content_text = (raw.get("content") or "").strip()
            if not content_text:
                continue
            cand = WellbeingCandidate(
                source_type=source_type,
                source_id=source_id,
                source_excerpt=(raw.get("excerpt") or "")[:500] or None,
                suggested_type=stype,
                suggested_content=content_text[:500],
                suggested_category=(raw.get("category") or None),
                suggested_intensity=int(raw.get("intensity") or 3),
                suggested_tags=raw.get("tags") if isinstance(raw.get("tags"), list) else None,
                ai_confidence=float(raw.get("ai_confidence") or 0.5),
                ai_reason=(raw.get("ai_reason") or None),
                status="pending",
                extract_status="success",
                model_used=model_name,
            )
            db.add(cand)
            candidates.append(cand)
        await db.flush()
        logger.info(f"心力候选提取成功: source={source_type}/{source_id} 提取 {len(candidates)} 条")
    except Exception as e:
        logger.warning(f"心力候选提取失败: source={source_type}/{source_id} err={e}")
        # 落一条 failed 记录便于追踪
        try:
            cand = WellbeingCandidate(
                source_type=source_type,
                source_id=source_id,
                suggested_type="achievement",
                suggested_content="(提取失败)",
                status="rejected",
                extract_status="failed",
                error_msg=str(e)[:500],
            )
            db.add(cand)
            await db.flush()
        except Exception:
            pass
    return candidates


async def extract_candidates_from_diary(diary_id: int, content: str) -> None:
    """BackgroundTask 入口：从日记提取候选。
    使用独立 session，避免与原请求 session 冲突。
    """
    try:
        async with async_session_maker() as db:
            await _extract_candidates(
                db,
                source_type="diary",
                source_id=diary_id,
                content=content,
                source_label="日记",
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"extract_candidates_from_diary 顶层失败: {e}")


async def extract_candidates_from_note(note_id: int, content: str) -> None:
    """BackgroundTask 入口：从读书笔记提取候选"""
    try:
        async with async_session_maker() as db:
            await _extract_candidates(
                db,
                source_type="note",
                source_id=note_id,
                content=content,
                source_label="读书笔记",
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"extract_candidates_from_note 顶层失败: {e}")


# ---------- 任务二：安抚卡 ----------

async def generate_comfort_message(
    db: AsyncSession,
    *,
    achievements: list[WellbeingEntry],
    gratitudes: list[WellbeingEntry],
) -> tuple[str, bool]:
    """生成焦虑模式的安抚语，返回 (text, fallback)"""
    if not achievements and not gratitudes:
        return random.choice(FALLBACK_COMFORT), True

    profile_text = await get_user_profile_text(db)
    ach_text = "\n".join(f"- {e.content}" for e in achievements[:5]) or "（暂无）"
    grat_text = "\n".join(f"- {e.content}" for e in gratitudes[:5]) or "（暂无）"
    prompt = (
        COMFORT_PROMPT
        .replace("{user_profile}", profile_text)
        .replace("{recent_achievements}", ach_text)
        .replace("{recent_gratitudes}", grat_text)
    )

    try:
        text, _model, _tokens = await _ai_call_text(db, prompt, max_tokens=400, temperature=0.85)
        text = text.strip().strip('"').strip("「").strip("」")
        if not text:
            return random.choice(FALLBACK_COMFORT), True
        return text, False
    except Exception as e:
        logger.warning(f"安抚语生成失败，降级为预置文案: {e}")
        return random.choice(FALLBACK_COMFORT), True


# ---------- 任务三：周/月报 ----------

def _format_entries_for_report(entries: list[WellbeingEntry], limit: int = 30) -> str:
    if not entries:
        return "（本期暂无记录）"
    lines = []
    for e in entries[:limit]:
        cat = f"[{e.category}]" if e.category else ""
        stars = "★" * e.intensity
        lines.append(f"- {e.occurred_at} {cat} {stars} {e.content}")
    return "\n".join(lines)


async def generate_period_report(
    db: AsyncSession,
    *,
    period_type: str,
    period_start: date,
    period_end: date,
    achievements: list[WellbeingEntry],
    gratitudes: list[WellbeingEntry],
) -> tuple[str, str, int]:
    """生成周报/月报 Markdown，返回 (markdown, model_name, tokens)"""
    profile_text = await get_user_profile_text(db)
    period_label = "本周" if period_type == "week" else "本月"
    prompt = (
        REPORT_PROMPT
        .replace("{user_profile}", profile_text)
        .replace("{period_label}", period_label)
        .replace("{achievement_count}", str(len(achievements)))
        .replace("{gratitude_count}", str(len(gratitudes)))
        .replace("{period_start}", period_start.isoformat())
        .replace("{period_end}", period_end.isoformat())
        .replace("{achievements_text}", _format_entries_for_report(achievements))
        .replace("{gratitudes_text}", _format_entries_for_report(gratitudes))
    )

    try:
        text, model, tokens = await _ai_call_text(db, prompt, max_tokens=1200, temperature=0.6)
        if not text.strip():
            text = _fallback_report(period_label, achievements, gratitudes)
            model = "fallback"
        return text, model, tokens
    except Exception as e:
        logger.warning(f"周月报生成失败，降级为本地汇总: {e}")
        return _fallback_report(period_label, achievements, gratitudes), "fallback", 0


def _fallback_report(period_label: str, achievements: list[WellbeingEntry], gratitudes: list[WellbeingEntry]) -> str:
    return (
        f"### {period_label}心力账户简报\n\n"
        f"- 成就累积：**{len(achievements)}** 条\n"
        f"- 感恩累积：**{len(gratitudes)}** 条\n\n"
        f"### 成就清单\n{_format_entries_for_report(achievements, limit=20)}\n\n"
        f"### 感恩清单\n{_format_entries_for_report(gratitudes, limit=20)}\n\n"
        f"> AI 暂时不可用，以上为本地汇总。点击右上角「重新生成」可再次尝试 AI 报告。"
    )


# ---------- 任务四：关联分析 ----------

def analyze_correlations(entries: list[WellbeingEntry]) -> dict:
    """纯 Python 关联分析，输出可消费的洞察 dict"""
    if not entries:
        return {
            "summary": "还没有足够的数据形成洞察，先记录一些瞬间吧。",
            "correlations": [],
            "suggestions": [],
        }

    from collections import Counter, defaultdict

    cat_counter: Counter[str] = Counter()
    cat_intensity: dict[str, list[int]] = defaultdict(list)
    type_counter: Counter[str] = Counter()
    # 同日成就 + 感恩共现
    by_date: dict[date, dict[str, list[str]]] = defaultdict(lambda: {"achievement": [], "gratitude": []})

    for e in entries:
        if e.category:
            cat_counter[e.category] += 1
            cat_intensity[e.category].append(e.intensity)
        type_counter[e.type] += 1
        by_date[e.occurred_at][e.type].append(e.category or "其他")

    # 共现矩阵：成就分类 ↔ 感恩分类
    co_counter: Counter[tuple[str, str]] = Counter()
    for d, group in by_date.items():
        for ac in group["achievement"]:
            for gr in group["gratitude"]:
                co_counter[(ac, gr)] += 1

    correlations = []
    for (ac, gr), n in co_counter.most_common(5):
        if n < 2:
            continue
        correlations.append({
            "label": f"{ac} 类成就 × {gr} 类感恩",
            "score": round(min(1.0, n / 10), 2),
            "note": f"近期同日共现 {n} 次",
        })

    # summary：找最高频分类
    top_cat = cat_counter.most_common(1)
    summary_parts = [f"已累积 {sum(type_counter.values())} 条心力记录"]
    if top_cat:
        cat, n = top_cat[0]
        summary_parts.append(f"，其中 **{cat}** 类最多（{n} 条）")
    if correlations:
        summary_parts.append("。下面是发现的关联模式：")
    else:
        summary_parts.append("。继续记录，更多模式会浮现。")
    summary = "".join(summary_parts)

    # 建议
    suggestions = []
    if len(entries) < 10:
        suggestions.append("条目还较少，每天试着记 1 条感恩 + 1 条成就，连续 7 天会看到明显变化。")
    if cat_counter and cat_counter.most_common(1)[0][1] > sum(cat_counter.values()) * 0.6:
        suggestions.append(f"分类比较集中在「{cat_counter.most_common(1)[0][0]}」，可以留意其他维度的积极瞬间。")
    if type_counter.get("gratitude", 0) < type_counter.get("achievement", 0) / 3:
        suggestions.append("感恩类条目偏少，建议每天结束时回想一件被善待的小事。")
    if type_counter.get("achievement", 0) < type_counter.get("gratitude", 0) / 3:
        suggestions.append("成就类条目偏少，记得自己做到的小事也值得记一笔。")

    return {
        "summary": summary,
        "correlations": correlations,
        "suggestions": suggestions,
    }
