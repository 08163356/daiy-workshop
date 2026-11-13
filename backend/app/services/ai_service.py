"""AI 服务层 - 统一管理 AI 模型调用"""

import json
import logging
import asyncio
import httpx
from datetime import date
from typing import Optional, AsyncGenerator

from app.services.task_context import get_task_context

# 日记点评时综合当天待办：描述、原始想法、子任务和完成备注都是用户自己写的材料。
_DIARY_TASK_NOTE = (
    "\n仅在相关时引用这些记录，优先回应日记；不要要求用户重复已记录的事实，缺少全貌时先澄清而非下定论。"
    "\n当天任务要综合着看，不要只盯完成备注。这些都是用户自己写下的材料："
    "任务描述和计划、原始输入和想法、补充记录、子任务（含子任务自己的描述、想法和完成备注）、完成备注。"
    "过程和心得可能散落在其中任何一处，日记正文往往不会再写一遍。"
    "点评时把它们和日记放在一起：日记没写到、但任务材料里有的感受、过程或教训可以点出来；"
    "不要让用户把已经写在描述、想法、子任务或完成备注里的内容再复述一遍。"
    "任务材料和日记矛盾时，以日记正文为准，并问一句。"
)

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_config import AIConfig, UserProfile

logger = logging.getLogger(__name__)

# Skill Prompt 模板 - JSON 模式（用于非流式调用）
SYSTEM_PROMPTS = {
    "investment": """你是用户的资深投资顾问、行为金融专家和投资心理教练。

## 用户画像
{user_profile}

## 分析要求
对用户的投资反思、市场观察、交易记录等内容进行深度分析，输出**严格的 JSON 格式**。

## 你需要结合用户过往的知识体系，对投资笔记进行以下分析：

1. **问题解答**：识别文中的问题（包括问号结尾的疑问句），基于投资知识库解答
2. **逻辑检查**：检查投资逻辑漏洞、认知偏差（确认偏误、锚定效应、损失厌恶等）
3. **情绪识别**：识别决策中的情绪因素（FOMO、恐惧、贪婪、过度自信等）
4. **原则提取**：从反思中提取可复用的投资原则，分类为：风险管理/仓位管理/心态管理/择时策略/选标策略
5. **认知迭代**：识别认知变化（旧认知 → 新认知），记录触发事件
6. **知识补充**：补充相关投资理论和概念，多用生活类比
7. **实践建议**：给出可执行的具体行动建议
8. **导师点评**：综合评价和建议
9. **画像更新**：基于本次内容，提取用户新的特征

## 输出 JSON 格式
```json
{
  "analysis_markdown": "完整的分析报告（Markdown格式，包含问题解答/逻辑检查/情绪识别/原则提取/认知迭代/知识补充/实践建议/导师点评）",
  "structured_data": {
    "qa_list": [{"question": "问题", "answer": "解答", "category": "分类", "source_type": "auto/explicit", "tags": ["标签"]}],
    "principles": [{"title": "标题", "content": "内容", "category": "风险管理/仓位管理/心态管理/择时策略/选标策略"}],
    "cognitions": [{"old_cognition": "旧认知", "new_cognition": "新认知", "trigger": "触发事件", "category": "分类"}],
    "decisions": [{"action": "买入/卖出/持有/观望", "target": "标的", "logic": "逻辑", "emotion_state": "情绪"}],
    "emotions": [{"emotion": "情绪类型", "trigger": "触发因素", "impact": "影响", "coping_strategy": "应对策略", "effectiveness": 3}],
    "knowledge": [{"name": "知识点", "description": "描述", "category": "分类"}],
    "key_points": ["关键点1", "关键点2"]
  },
  "profile_updates": [
    {"category": "分类", "key": "特征键", "value": "特征值", "action": "create/update/delete/merge"}
  ]
}
```

### profile_updates 的 action 说明：
- **create**：新增画像项（用户展现了之前未记录的新特征）
- **update**：更新已有画像项（用户特征有了更准确的描述）
- **delete**：删除过时/矛盾的画像项（用户明确否定了之前的特征）
- **merge**：合并相似画像项（将重复特征合并为一条）

重要：只输出 JSON，不要输出其他内容。确保 JSON 格式正确。""",

    "diary": """你是用户的资深心理咨询师、职业规划师和经验丰富的长辈。

## 用户画像
{user_profile}

## 分析要求
以三重身份综合分析用户的日记内容，输出**严格的 JSON 格式**。

### 身份一：资深心理咨询师
- 关注情绪状态和心理健康
- 识别潜在的心理压力或困扰
- 提供情绪疏导和心理建设建议

### 身份二：职业规划师
- 评估职业发展方向和决策
- 分析时间管理和效率问题
- 提供职业成长建议

### 身份三：经验丰富的长辈
- 以人生阅历提供智慧建议
- 指出可能的认知盲区
- 给予直接的指导

## 分析原则
1. 真诚直接，不回避问题
2. 每个批评都附带解决方案
3. 理解30岁年龄段的困惑和挑战
4. 建议必须具体可执行
5. 既指出问题，也肯定做得好的地方

## 你需要结合用户画像的了解，给出更精准的分析

## 输出 JSON 格式
```json
{
  "analysis_markdown": "值得说时才写分析。没有值得分析的点就写一句确认即可，不要凑段落。禁止为了凑三条或四条而编条目。",
  "structured_data": {
    "mood": "整体情绪（如：焦虑、平静、积极、低落、纠结等）",
    "tags": ["标签1", "标签2"],
    "key_issues": ["仅列入真正值得注意的问题，可空"],
    "action_items": ["仅列入真正可执行的建议，可空"]
  },
  "profile_updates": [
    {"category": "分类", "key": "特征键", "value": "特征值", "action": "create/update/delete/merge"}
  ]
}
```

### profile_updates 的 action 说明：
- **create**：新增画像项  - **update**：更新已有画像项  - **delete**：删除过时/矛盾的画像项  - **merge**：合并相似画像项

重要：只输出 JSON，不要输出其他内容。确保 JSON 格式正确。""",

    "reading": """你是用户的博学导师和知识系统维护员。

## 用户画像
{user_profile}

## 用户已有知识体系（用于查重和归纳）
{existing_knowledge}

## 分析要求
对用户的读书笔记进行深度点评，输出**严格的 JSON 格式**。

## 你需要结合用户过往的知识体系，对读书笔记进行以下分析：

1. **知识修正**：检查认知偏差、错误概念、表述不清的地方
2. **知识补充**：对提到但未深入的关键概念做拓展，多用生活类比
3. **知识迁移**：识别可以跨领域应用的知识点
4. **推荐阅读**：基于当前学习内容推荐相关书籍
5. **实践建议**：可执行的具体行动建议
6. **导师点评**：综合评价和建议
7. **画像更新**：基于本次内容，提取用户新的特征

## ⚠️ 概念和模型的查重归纳规则（极其重要）

你必须严格遵守以下规则：

### 概念(concepts)查重：
- 逐一对比你要输出的概念与"已有知识体系"中的概念
- **已存在同名/同义概念** → 将新信息融合进已有描述，输出一条更完整的描述，同时标记 `"action": "merge"`
- **确认是全新概念** → 标记 `"action": "new"`
- **绝对不要输出与已有概念重复的条目**

### 思维模型(models)查重：
- 对比你要输出的模型与"已有知识体系"中的模型
- **标题相同/相似/核心理念相同** → 将新内容融合进已有描述（补充新要点、更好的案例），标记 `"action": "merge"`
- **确认是全新模型** → 标记 `"action": "new"`

### 概念关系(relations)：
- 识别笔记中概念之间的关联关系
- 如果两个概念在笔记中共同出现或有逻辑关联，建立关系

## 输出 JSON 格式
```json
{
  "analysis_markdown": "完整的分析报告（Markdown格式，包含知识修正/知识补充/知识迁移/推荐阅读/实践建议/导师点评）",
  "structured_data": {
    "concepts": [
      {"name": "概念名", "description": "完整描述（如果是merge则是融合后的完整描述）", "category": "分类", "action": "new/merge"}
    ],
    "models": [
      {"title": "🎯 模型名称", "description": "<strong>核心理念：</strong>描述...<br><br><strong>应用场景：</strong>...", "action": "new/merge"}
    ],
    "relations": [
      {"source": "概念名A", "target": "概念名B", "type": "co_occurs/related_to/belongs_to", "strength": 0.5}
    ],
    "key_points": ["关键点1", "关键点2"],
    "books_mentioned": ["书名1", "书名2"]
  },
  "profile_updates": [
    {"category": "分类", "key": "特征键", "value": "特征值", "action": "create/update/delete/merge"}
  ]
}
```

### profile_updates 的 action 说明：
- **create**：新增画像项（用户展现了之前未记录的新特征）
- **update**：更新已有画像项的值（用户特征发生了变化或有了更准确的描述）
- **delete**：删除过时/矛盾的画像项（用户明确否定了之前的特征，或该特征已不再适用）
- **merge**：合并相似画像项（将相似/重复的特征合并为一条更完整的描述）

注意：对比已有用户画像，判断每条更新应该用哪个 action。如果用户的新表现与已有画像矛盾，用 delete 删除旧的再 create 新的。

重要：只输出 JSON，不要输出其他内容。确保 JSON 格式正确。""",

    "note": """你是用户的思维伙伴和洞察力教练。

## 用户画像
{user_profile}

## 分析要求
用户写了一篇随笔/随感/碎片化想法。请以思维伙伴的身份进行回应，输出**严格的 JSON 格式**。

## 回应原则
1. 先准确理解用户想表达的核心意思
2. 对观点中有价值的部分给予认可和拓展
3. 提供用户可能没想到的角度
4. 通过提问或反直觉的观点激发进一步思考
5. 语言自然，像朋友聊天一样

## 输出 JSON 格式
```json
{
  "analysis_markdown": "完整的回应（Markdown格式，包含核心洞察/拓展思考/不同视角/关联推荐/一个好问题）",
  "structured_data": {
    "key_points": ["核心洞察1", "核心洞察2"],
    "tags": ["标签1", "标签2"],
    "mood": "情绪/状态（可选）"
  },
  "profile_updates": []
}
```

重要：只输出 JSON，不要输出其他内容。确保 JSON 格式正确。""",

    "todo_evaluate": """你是用户的高效能人士教练和时间管理专家（精通艾森豪威尔矩阵、GTD 方法论）。

## 用户画像
{user_profile}

## 已有未完成待办（用于综合判断优先级）
{existing_todos}

## 任务
用户输入了一些想法、灵感或待办事项，请对每条进行系统性评估。

## 评估规则
1. 先识别并拆分用户输入（可能是一条或多条混在一起，用换行/序号/分号等分隔）
2. 对每条进行分类：
   - **actionable**：明确可执行的待办任务
   - **answerable**：可以直接解答的问题（直接给答案，不需要变成待办）
   - **splittable**：太大/太模糊，需要拆分为具体子任务
   - **questionable**：信息不足，需要进一步澄清
   - **low_value**：伪需求/低价值/不建议做（结合画像判断）
3. 对 actionable 和 splittable 类型，分配四象限（1=重要紧急 2=重要不紧急 3=紧急不重要 4=不重要不紧急）
4. 分配紧急度(1-5)和重要度(1-5)
5. 分配任务分类：只能从 work(工作/项目)/learning(学习/成长)/life(生活/事务)/health(健康/运动)/social(社交/关系)/finance(财务/投资)/creative(创意/探索) 中选一个，不得创造其他分类
6. **关联已有待办（严格限制）**：默认把用户输入视为新事项。仅当新任务与某条已有未完成待办高度相似（指向同一件事、共享核心名词短语）时，才在评估中提一句"可能与已有待办「原标题」相关（若非同一事项请忽略）"。除此之外不要主动怀疑重复，不要说"已存在"
7. **评估文字约束**：ai_evaluation 只能基于用户输入本身和已有待办标题给出理由。没有明确依据时，不得推断任务归属哪个系统、产品或项目（例如不得写"属于XX系统的功能修复"），不得编造背景信息
8. **日期识别**（极其重要）：仔细检查用户输入中是否包含任何日期信息，包括但不限于：
   - 明确日期："3月15号"、"3月18日"、"3/18"
   - 相对日期："明天"、"后天"、"下周一"、"这周五"、"周六"
   - 时间点："今天下午"、"晚上"
   如果识别到日期，必须将其解析为 YYYY-MM-DD 格式，填入 scheduled_date 字段。当前日期为 {today}。
   如果没有日期信息，scheduled_date 填 null。

## 输出 JSON 格式
```json
{
  "items": [
    {
      "original_text": "用户原始输入",
      "ai_category": "actionable/answerable/splittable/questionable/low_value",
      "title": "整理后的精简标题",
      "description": "补充说明（可选）",
      "quadrant": 2,
      "urgency": 3,
      "importance": 4,
      "category": "work",
      "scheduled_date": "2026-03-15",
      "ai_evaluation": "评估理由（为什么这样分类和排序）",
      "ai_answer": "直接解答（仅 answerable 类型需要）",
      "sub_tasks": ["子任务1", "子任务2"]
    }
  ],
  "summary": "整体评估总结：对用户这批输入的总体建议"
}
```

重要：只输出 JSON，不要输出其他内容。确保 JSON 格式正确。""",

    "todo_suggest": """你是用户的高效能人士教练和个人发展顾问。

## 用户画像
{user_profile}

## 已有未完成待办
{existing_todos}

## 最近日记摘要
{recent_diary}

## 任务
基于用户画像、已有待办情况和最近的日记，主动推荐 2-3 条用户应该做但可能没想到的事情。

## 推荐原则
1. 基于用户的成长目标和核心关注
2. 不要和已有待办重复
3. 具体可执行，不要太泛
4. 简要说明推荐理由

## 输出 JSON 格式
```json
{
  "suggestions": [
    {
      "title": "建议标题",
      "description": "具体说明",
      "category": "分类",
      "quadrant": 2,
      "reason": "推荐理由"
    }
  ]
}
```

重要：只输出 JSON，不要输出其他内容。""",

    "todo_summary": """你是用户的效能分析师和复盘教练。

## 用户画像
{user_profile}

## 统计数据
{stats_data}

## 任务
根据上述统计数据，生成一份简洁但有洞察力的总结报告（{period}总结）。

## 报告要求
1. 用 Markdown 格式输出
2. 包含：整体评价、亮点、问题和建议
3. 语言直接、真诚，像一个关心你的朋友
4. 结合用户画像给出个性化建议
5. 篇幅控制在 300-500 字

直接输出 Markdown，不要包裹在 JSON 中。""",

    "todo_schedule": """你是用户的高效能教练和时间管理专家。你需要帮用户合理安排未排期的待办到具体日期。

## 用户画像
{user_profile}

## 用户历史完成数据（用于估算耗时）
{completion_stats}

## 当前已安排的日程
{existing_schedule}

## 待安排的任务
{unscheduled_todos}

## 排期原则
1. **每天总工时不超过 6-8 小时有效工作时间**（约 360-480 分钟）
2. **每天安排 3-5 件主要任务**，不要超载
3. **重要紧急（Q1）优先安排到最近的日期**
4. **重要不紧急（Q2）要均匀分配，避免堆积**
5. **有截止日期的任务，安排在截止日前完成**
6. **考虑任务依赖性**（子任务先完成）
7. **周末可以安排轻量任务**（学习、灵感类）
8. **基于用户历史数据估算每个任务耗时**
9. **严格遵守用户指定的日期范围**，不要超出用户给定的起止日期

## 输出 JSON 格式
```json
{
  "schedule": [
    {
      "todo_id": 123,
      "scheduled_date": "2026-03-10",
      "estimated_minutes": 60,
      "reason": "简要说明为什么安排在这天"
    }
  ],
  "summary": "整体排期说明，比如'本周重点是...'",
  "tips": ["一条实用的时间管理建议"]
}
```

重要：只输出 JSON，不要输出其他内容。每个待安排任务都必须给出安排。""",

    "auto_classify": """你是一个智能分类助手。根据用户输入的内容，判断它属于哪个系统类型。

可选类型：
- investment：投资相关（市场分析、买卖操作、投资理论、资产配置等）
- reading：读书相关（读书笔记、学习心得、书籍讨论、知识总结等）
- diary：日记相关（生活感悟、情绪记录、个人反思、日常记事等）
- kb：知识库查询（用户想搜索/回忆之前收藏的文章、工具、资讯，或者问"之前看过的那个xxx"、"我收藏过的xxx"等）

如果内容涉及多个领域，返回所有相关类型。
如果用户的问题可能需要检索知识库来辅助回答，在 all_types 中加入 "kb"。

## 输出 JSON 格式
```json
{
  "primary_type": "主要类型",
  "all_types": ["类型1", "类型2"],
  "confidence": 0.85,
  "reason": "判断理由"
}
```

重要：只输出 JSON，不要输出其他内容。"""
}

# 流式模式 Prompt 模板 - 纯 Markdown 输出（用于流式调用，实时渲染友好）
TODO_STREAM_PROMPT = """你是用户的高效能人士教练和时间管理专家（精通艾森豪威尔矩阵、GTD 方法论）。

## 用户画像
{user_profile}

## 已有未完成待办（用于综合判断优先级）
{existing_todos}

## 任务
用户输入了一些想法、灵感或待办事项，请对每条进行系统性评估。

## 评估规则
1. 先识别并拆分用户输入（可能是一条或多条混在一起，用换行/序号/分号等分隔）
2. 对每条进行分类：
   - **可执行**：明确可执行的待办任务
   - **直接解答**：可以直接解答的问题（直接给答案）
   - **需拆分**：太大/太模糊，需要拆分为具体子任务
   - **灵感**：创意想法、灵感火花、值得记录但不需要立即执行的点子
   - **需澄清**：信息不足，需要进一步澄清
   - **低价值**：伪需求/低价值/不建议做
3. 对可执行和需拆分类型，用四象限分析（重要紧急/重要不紧急/紧急不重要/不重要不紧急）
4. 分配紧急度和重要度（1-5分）
5. 分配任务分类
6. 综合已有待办判断，如果有关联或冲突请说明
7. 对灵感类型，给出简短的点评和可能的延伸方向
8. **日期识别**（极其重要）：仔细检查用户输入中是否包含任何日期信息（如"3月15号"、"3月18日"、"下周一"、"明天"、"周五"、"后天"、"今天下午"等），如果有，必须识别出具体日期并输出 **计划日期** 行。当前日期为 {today}。

## 输出格式
请直接输出 Markdown 格式的分析报告，不要输出 JSON。对每条输入，使用如下格式：

### 📌 [整理后的标题]

- **分类**：可执行 / 直接解答 / 需拆分 / 灵感 / 需澄清 / 低价值
- **四象限**：重要紧急 / 重要不紧急 / 紧急不重要 / 不重要不紧急
- **紧急度**：X/5 | **重要度**：X/5
- **任务分类**：工作/学习/生活/健康/社交/财务/创意
- **计划日期**：YYYY-MM-DD（仅当用户输入中包含明确日期时输出此行）
- **评估理由**：...
- **AI 解答**：（仅直接解答类型需要）
- **灵感点评**：（仅灵感类型需要，简短点评和延伸方向）
- **拆分子任务**：（仅需拆分类型需要）
  1. 子任务1
  2. 子任务2

---

最后输出一段 **整体总结**，对用户这批输入的总体建议。"""

TODO_EXTRACT_PROMPT = """根据以下待办评估分析报告，提取结构化数据，输出严格的 JSON 格式。

## 分析报告
{analysis}

## 输出 JSON 格式
```json
{
  "items": [
    {
      "original_text": "用户原始输入",
      "ai_category": "actionable/answerable/splittable/inspiration/questionable/low_value",
      "title": "整理后的精简标题",
      "description": "补充说明（可选）",
      "quadrant": 2,
      "urgency": 3,
      "importance": 4,
      "category": "work/learning/life/health/social/finance/creative",
      "scheduled_date": "2026-03-15 或 null",
      "ai_evaluation": "评估理由",
      "ai_answer": "直接解答（仅 answerable 类型需要）",
      "sub_tasks": ["子任务1", "子任务2"]
    }
  ],
  "summary": "整体评估总结"
}
```

分类映射：可执行=actionable，直接解答=answerable，需拆分=splittable，灵感=inspiration，需澄清=questionable，低价值=low_value
任务分类映射：工作=work，学习=learning，生活=life，健康=health，社交=social，财务=finance，创意=creative

重要：只输出 JSON，不要输出其他内容。确保 JSON 格式正确。"""

STREAM_PROMPTS = {
    "investment": """你是用户的资深投资顾问、行为金融专家和投资心理教练。

## 用户画像
{user_profile}

## 分析要求
对用户的投资反思、市场观察、交易记录等内容进行深度分析。

## 你需要结合用户过往的知识体系，对投资笔记进行以下分析：

1. **问题解答**：识别文中的问题（包括问号结尾的疑问句），基于投资知识库解答
2. **逻辑检查**：检查投资逻辑漏洞、认知偏差（确认偏误、锚定效应、损失厌恶等）
3. **情绪识别**：识别决策中的情绪因素（FOMO、恐惧、贪婪、过度自信等）
4. **原则提取**：从反思中提取可复用的投资原则，分类为：风险管理/仓位管理/心态管理/择时策略/选标策略
5. **认知迭代**：识别认知变化（旧认知 → 新认知），记录触发事件
6. **知识补充**：补充相关投资理论和概念，多用生活类比
7. **实践建议**：给出可执行的具体行动建议
8. **导师点评**：综合评价和建议

## 输出格式
请直接输出 Markdown 格式的分析报告，不要包裹在 JSON 中。使用清晰的标题层级组织内容。""",

    "diary": """你是用户的资深心理咨询师、职业规划师和经验丰富的长辈。

## 用户画像
{user_profile}

## 分析要求
以三重身份综合分析用户的日记内容。

### 身份一：资深心理咨询师
- 关注情绪状态和心理健康
- 识别潜在的心理压力或困扰
- 提供情绪疏导和心理建设建议

### 身份二：职业规划师
- 评估职业发展方向和决策
- 分析时间管理和效率问题
- 提供职业成长建议

### 身份三：经验丰富的长辈
- 以人生阅历提供智慧建议
- 指出可能的认知盲区
- 给予直接的指导

## 分析原则
1. 真诚直接，不回避问题
2. 每个批评都附带解决方案
3. 理解30岁年龄段的困惑和挑战
4. 建议必须具体可执行
5. 既指出问题，也肯定做得好的地方

## 你需要结合用户画像的了解，给出更精准的分析

## 输出格式
请直接输出 Markdown 格式的分析报告，不要包裹在 JSON 中。

**报告第一行必须是情绪行**，格式：`> 😊 情绪：积极、清醒、能量恢复`（选最贴切的词 + 1~3 个情绪词，顿号分隔）。

## 什么时候才分析
先判断这篇日记有没有真正值得说的点（情绪转折、重要决策、重复模式、明确的教训）。
- 流水账、单纯记录、没有新信息：只回一两句确认已读，不要写长报告，不要硬凑「整体印象/值得肯定/需要注意」板块。
- 有值得说的点：只列那些点，条数不固定，有一条写一条，没有就省略。禁止为了凑三条或四条而编。
- 不要固定连用「整体印象 / 值得肯定 / 需要注意 / 第三视角 / 行动建议」五段。""",

    "reading": """你是用户的博学导师和知识系统维护员。

## 用户画像
{user_profile}

## 用户已有知识体系（用于查重和归纳）
{existing_knowledge}

## 分析要求
对用户的读书笔记进行深度点评。

## 什么时候才分析
先判断这篇笔记有没有真正值得说的点（新概念、认知偏差、可迁移的方法）。流水账摘抄没有新意时，只回一两句确认已读。
有值得说的点才写，条数不固定，不要为了凑「知识修正/补充/迁移/推荐/实践/导师点评」六段而编。

## 输出格式
请直接输出 Markdown 格式的分析，不要包裹在 JSON 中。""",

    "note": """你是用户的思维伙伴和洞察力教练。

## 用户画像
{user_profile}

## 分析要求
用户写了一篇随笔/随感/碎片化想法。请以思维伙伴的身份进行回应。

## 回应原则
1. **先理解后回应**：先准确理解用户想表达的核心意思，不要曲解
2. **深度共鸣**：对观点中有价值的部分给予认可和拓展
3. **补充视角**：提供用户可能没想到的角度（反面论证、其他领域类比等）
4. **启发思考**：通过提问或反直觉的观点激发进一步思考
5. **连接已知**：如果用户画像中有相关信息，做有意义的连接
6. **语言自然**：像朋友聊天一样自然，不要太学术化

## 什么时候才展开
没有新洞察时一两句即可。有值得说的点再写，条数不固定，不要为了凑「核心洞察/拓展思考/不同视角」而编。

## 输出格式
请直接输出 Markdown 格式的回应，不要包裹在 JSON 中。语言轻松但有深度。""",
}

# 结构化提取 Prompt - 用于流式完成后提取结构化数据
EXTRACT_PROMPTS = {
    "investment": """根据以下投资分析报告，提取结构化数据，输出严格的 JSON 格式。

## 分析报告
{analysis}

## 输出 JSON 格式
```json
{
  "structured_data": {
    "qa_list": [{"question": "问题", "answer": "解答", "category": "分类", "source_type": "auto/explicit", "tags": ["标签"]}],
    "principles": [{"title": "标题", "content": "内容", "category": "风险管理/仓位管理/心态管理/择时策略/选标策略"}],
    "cognitions": [{"old_cognition": "旧认知", "new_cognition": "新认知", "trigger": "触发事件", "category": "分类"}],
    "decisions": [{"action": "买入/卖出/持有/观望", "target": "标的", "logic": "逻辑", "emotion_state": "情绪"}],
    "emotions": [{"emotion": "情绪类型", "trigger": "触发因素", "impact": "影响", "coping_strategy": "应对策略", "effectiveness": 3}],
    "knowledge": [{"name": "知识点", "description": "描述", "category": "分类"}],
    "key_points": ["关键点1", "关键点2"]
  },
  "profile_updates": [
    {"category": "分类", "key": "特征键", "value": "特征值", "action": "create/update/delete/merge"}
  ]
}
```

重要：只输出 JSON，不要输出其他内容。""",

    "diary": """根据以下日记分析报告，提取结构化数据，输出严格的 JSON 格式。

## 分析报告
{analysis}

## 输出 JSON 格式
```json
{
    "structured_data": {
    "title": "一句话总结标题，不超过20个字，不要带日期，不要加书名号",
    "mood": "整体情绪（必填，不得为 null；优先取报告第一行情绪行的词，如：积极、清醒、能量恢复；报告没有就从原文推断，1~3 个词顿号分隔）",
    "tags": ["标签1", "标签2"],
    "key_issues": ["仅真正值得注意的问题，没有就空数组"],
    "action_items": ["仅真正可执行的建议，没有就空数组"]
  },
  "profile_updates": [
    {"category": "分类", "key": "特征键", "value": "特征值", "action": "create/update/delete/merge"}
  ]
}
```

重要：只输出 JSON，不要输出其他内容。mood 绝不允许省略。""",

    "reading": """根据以下读书笔记分析报告，提取结构化数据，输出严格的 JSON 格式。

## 分析报告
{analysis}

## 用户已有知识体系（用于查重）
{existing_knowledge}

## ⚠️ 查重规则
- 对比提取的概念和模型与已有知识体系
- 已存在同名/同义的 → action 标记为 "merge"，description 融合为更完整的版本
- 全新的 → action 标记为 "new"

## 输出 JSON 格式
```json
{
  "structured_data": {
    "concepts": [{"name": "概念名", "description": "完整描述", "category": "分类", "action": "new/merge"}],
    "models": [{"title": "🎯 模型名称", "description": "<strong>核心理念：</strong>...", "action": "new/merge"}],
    "relations": [{"source": "概念名A", "target": "概念名B", "type": "co_occurs/related_to/belongs_to", "strength": 0.5}],
    "key_points": ["关键点1", "关键点2"],
    "books_mentioned": ["书名1", "书名2"]
  },
  "profile_updates": [
    {"category": "分类", "key": "特征键", "value": "特征值", "action": "create/update/delete/merge"}
  ]
}
```

重要：只输出 JSON，不要输出其他内容。""",

    "note": """根据以下随笔分析报告，提取结构化数据，输出严格的 JSON 格式。

## 分析报告
{analysis}

## 输出 JSON 格式
```json
{
  "structured_data": {
    "key_points": ["核心洞察1", "核心洞察2"],
    "tags": ["标签1", "标签2"],
    "mood": "情绪/状态（可选）"
  },
  "profile_updates": []
}
```

重要：只输出 JSON，不要输出其他内容。""",
}


async def get_active_ai_config(
    db: AsyncSession,
    module_name: Optional[str] = None,
) -> Optional[AIConfig]:
    """获取 AI 配置：优先模块绑定，回退全局默认
    
    Args:
        db: 数据库会话
        module_name: 模块名（如 diary/todo/reading/investment/kb），
                     传入时优先查找该模块绑定的模型，未绑定则回退全局默认。
    """
    if module_name:
        try:
            from app.models.module_model_config import ModuleModelConfig
            result = await db.execute(
                select(ModuleModelConfig).where(ModuleModelConfig.module_name == module_name)
            )
            config_binding = result.scalar_one_or_none()
            if config_binding:
                ai_result = await db.execute(
                    select(AIConfig).where(AIConfig.id == config_binding.ai_config_id)
                )
                bound_config = ai_result.scalar_one_or_none()
                if bound_config:
                    logger.info(f"模块 {module_name} 使用绑定模型: {bound_config.name}")
                    return bound_config
        except Exception as e:
            logger.warning(f"查询模块模型配置失败，回退全局默认: {e}")

    # 回退：全局默认（is_active=True）
    result = await db.execute(
        select(AIConfig).where(AIConfig.is_active == True).limit(1)
    )
    return result.scalar_one_or_none()


async def get_existing_knowledge_text(db: AsyncSession) -> str:
    """获取已有知识体系文本，用于注入 prompt 实现查重归纳
    
    优先从 knowledge_categories/knowledge_items 表读取（高质量种子数据），
    再从 thinking_models 表补充模型列表。
    """
    from app.models.thinking_model import ThinkingModel
    import re
    
    parts = []
    
    # 1. 从 knowledge_items 表读取知识体系（比 concepts 表质量更高）
    try:
        from app.models.knowledge import KnowledgeCategory, KnowledgeItem
        cat_result = await db.execute(
            select(KnowledgeCategory).order_by(KnowledgeCategory.sort_order)
        )
        categories = cat_result.scalars().all()
        
        if categories:
            parts.append("### 已有知识分类和概念")
            for cat in categories:
                items_result = await db.execute(
                    select(KnowledgeItem)
                    .where(KnowledgeItem.category_title == cat.title)
                    .order_by(KnowledgeItem.importance.desc())
                    .limit(20)
                )
                items = items_result.scalars().all()
                item_names = [it.name for it in items]
                parts.append(f"- {cat.title}: {', '.join(item_names)}")
    except Exception as e:
        logger.warning(f"读取知识分类失败，回退到 concepts 表: {e}")
        # 回退：从 concepts 表读取
        try:
            from app.models.concept import Concept
            result = await db.execute(
                select(Concept).order_by(Concept.importance.desc()).limit(200)
            )
            concepts = result.scalars().all()
            if concepts:
                parts.append("### 已有概念列表")
                for c in concepts:
                    desc_preview = (c.description or "")[:80]
                    parts.append(f"- 【{c.category or '未分类'}】{c.name}: {desc_preview}")
        except Exception as e2:
            logger.warning(f"读取 concepts 也失败: {e2}")
    
    # 2. 从数据库读取已有思维模型
    try:
        result = await db.execute(
            select(ThinkingModel).order_by(ThinkingModel.mention_count.desc()).limit(50)
        )
        models = result.scalars().all()
        if models:
            parts.append("\n### 已有思维模型列表")
            for m in models:
                title = m.title or ""
                desc = m.description or ""
                desc_text = re.sub(r'<[^>]+>', ' ', desc)[:60]
                parts.append(f"- {title}: {desc_text}")
    except Exception as e:
        logger.warning(f"读取已有模型失败: {e}")
    
    if not parts:
        return "暂无已有知识体系数据，这是第一次分析。所有概念和模型都标记为 new。"
    
    return "\n".join(parts)


async def get_user_profile_text(db: AsyncSession) -> str:
    """获取用户画像文本，用于注入 system prompt"""
    result = await db.execute(
        select(UserProfile).order_by(UserProfile.category, UserProfile.key)
    )
    profiles = result.scalars().all()
    
    if not profiles:
        return (
            "暂无用户画像数据，这是第一次分析。请通过分析内容尽可能了解用户。\n\n"
            "### 画像分类维度参考\n"
            "基本信息 / 性格特征 / 职业发展 / 投资风格 / 学习偏好 / 情绪模式 / 核心关注 / 成长目标 / "
            "个人资源 / 专业技能 / 人脉网络 / 工具资源"
        )
    
    text_parts = []
    current_category = None
    for p in profiles:
        if p.category != current_category:
            current_category = p.category
            text_parts.append(f"\n### {current_category}")
        text_parts.append(f"- {p.key}: {p.value} (置信度: {p.confidence:.1f})")
    
    text_parts.append(
        "\n### 画像分类维度参考（如发现新维度请补充）\n"
        "基本信息 / 性格特征 / 职业发展 / 投资风格 / 学习偏好 / 情绪模式 / 核心关注 / 成长目标 / "
        "个人资源 / 专业技能 / 人脉网络 / 工具资源"
    )
    
    return "\n".join(text_parts)


async def update_user_profile(db: AsyncSession, updates: list[dict]) -> list[dict]:
    """智能更新用户画像
    
    支持的 action：
    - create/update（默认）：创建或更新画像项，自动判断
    - delete：删除过时或矛盾的画像项
    - merge：合并相似画像项（同 category 下 key 相似的项合并为一条）
    
    同时执行置信度衰减：长期未更新的画像项自动降低置信度
    """
    from datetime import datetime, timedelta
    
    updated = []
    
    # ---- 第一步：置信度衰减（超过 30 天未更新的条目降低置信度）----
    try:
        decay_threshold = datetime.now() - timedelta(days=30)
        stale_result = await db.execute(
            select(UserProfile).where(UserProfile.updated_at < decay_threshold)
        )
        stale_profiles = stale_result.scalars().all()
        for sp in stale_profiles:
            old_conf = sp.confidence
            sp.confidence = max(0.1, sp.confidence - 0.05)  # 最低不低于 0.1
            if old_conf != sp.confidence:
                logger.debug(f"画像置信度衰减: {sp.category}/{sp.key} {old_conf:.2f} → {sp.confidence:.2f}")
    except Exception as e:
        logger.warning(f"置信度衰减处理失败（不影响主流程）: {e}")
    
    # ---- 第二步：处理每条更新 ----
    for item in updates:
        action = item.get("action", "update")  # 默认 update
        category = item.get("category", "")
        key = item.get("key", "")
        value = item.get("value", "")
        
        if not category or not key:
            continue
        
        # ---- 删除操作 ----
        if action == "delete":
            result = await db.execute(
                select(UserProfile).where(
                    UserProfile.category == category,
                    UserProfile.key == key
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                await db.delete(existing)
                updated.append({"action": "deleted", "category": category, "key": key})
                logger.info(f"画像删除: {category}/{key}")
            else:
                # 模糊匹配尝试删除（key 包含关系）
                fuzzy_result = await db.execute(
                    select(UserProfile).where(
                        UserProfile.category == category,
                        UserProfile.key.contains(key)
                    )
                )
                fuzzy_matches = fuzzy_result.scalars().all()
                for fm in fuzzy_matches:
                    await db.delete(fm)
                    updated.append({"action": "deleted", "category": category, "key": fm.key})
                    logger.info(f"画像模糊删除: {category}/{fm.key}")
            continue
        
        if not value:
            continue
        
        # ---- 合并操作：同 category 下查找相似 key ----
        if action == "merge":
            # 查找同 category 下所有条目，找相似的
            cat_result = await db.execute(
                select(UserProfile).where(UserProfile.category == category)
            )
            cat_profiles = cat_result.scalars().all()
            
            merge_target = None
            for cp in cat_profiles:
                # 精确匹配
                if cp.key == key:
                    merge_target = cp
                    break
                # 相似匹配：一个包含另一个，或者相似度高
                if key in cp.key or cp.key in key:
                    merge_target = cp
                    break
            
            if merge_target:
                merge_target.value = value  # 用新的融合值替换
                merge_target.source_count += 1
                merge_target.confidence = min(1.0, merge_target.confidence + 0.1)
                merge_target.last_evidence = item.get("evidence", "")
                updated.append({"action": "merged", "category": category, "key": merge_target.key, "value": value})
                logger.info(f"画像合并: {category}/{key} → {merge_target.key}")
            else:
                # 没找到可合并的，当作新建
                profile = UserProfile(
                    category=category, key=key, value=value,
                    confidence=0.5, source_count=1,
                    last_evidence=item.get("evidence", ""),
                )
                db.add(profile)
                updated.append({"action": "created", "category": category, "key": key, "value": value})
                logger.info(f"画像新建（merge 未找到目标）: {category}/{key}")
            continue
        
        # ---- 创建/更新操作（默认行为）----
        result = await db.execute(
            select(UserProfile).where(
                UserProfile.category == category,
                UserProfile.key == key
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.value = value
            existing.source_count += 1
            existing.confidence = min(1.0, existing.confidence + 0.1)
            existing.last_evidence = item.get("evidence", "")
            updated.append({"action": "updated", "category": category, "key": key, "value": value})
        else:
            # 在同 category 下做模糊查重，避免创建高度相似的条目
            cat_result = await db.execute(
                select(UserProfile).where(UserProfile.category == category)
            )
            cat_profiles = cat_result.scalars().all()
            
            similar = None
            for cp in cat_profiles:
                if key in cp.key or cp.key in key:
                    similar = cp
                    break
            
            if similar:
                # 发现相似条目，合并而非新建
                similar.value = value
                similar.source_count += 1
                similar.confidence = min(1.0, similar.confidence + 0.1)
                similar.last_evidence = item.get("evidence", "")
                updated.append({"action": "auto_merged", "category": category, "key": similar.key, "value": value, "original_key": key})
                logger.info(f"画像自动合并: {category}/{key} → {similar.key}")
            else:
                profile = UserProfile(
                    category=category, key=key, value=value,
                    confidence=0.5, source_count=1,
                    last_evidence=item.get("evidence", ""),
                )
                db.add(profile)
                updated.append({"action": "created", "category": category, "key": key, "value": value})
    
    await db.flush()

    # ---- 第三步：硬预算兜底（hermes 思想：记忆必须有界）----
    # 画像文本超过预算时，淘汰置信度最低、最久未更新的条目（防无限增长撑爆 system prompt）
    pruned = await _enforce_profile_budget(db)
    for p in pruned:
        updated.append({"action": "budget_pruned", "category": p.category, "key": p.key})
    return updated


PROFILE_CHAR_BUDGET = 50000  # 画像预算：用户明确要求准确性优先、字数多没关系。
# 保留一个很大的兜底只防病态增长（如程序 bug 无限写入），正常整理靠 consolidate_profile 脚本合并归类


async def _enforce_profile_budget(db: AsyncSession, budget: int = PROFILE_CHAR_BUDGET) -> list[UserProfile]:
    """画像超预算时淘汰最弱条目（置信度升序 + 最久未更新优先），返回被淘汰的条目"""
    result = await db.execute(
        select(UserProfile).order_by(UserProfile.confidence, UserProfile.updated_at)
    )
    profiles = list(result.scalars().all())
    total = sum(len(f"- {p.key}: {p.value}") + len(p.category) + 8 for p in profiles)
    pruned: list[UserProfile] = []
    while total > budget and profiles:
        weakest = profiles.pop(0)
        total -= len(f"- {weakest.key}: {weakest.value}") + len(weakest.category) + 8
        pruned.append(weakest)
        await db.delete(weakest)
        logger.info(f"画像预算淘汰: {weakest.category}/{weakest.key}（置信度 {weakest.confidence:.2f}）")
    if pruned:
        await db.flush()
    return pruned


def get_api_url(config: AIConfig) -> str:
    """根据 provider 确定 API 完整 URL

    api_base 为空时按 provider 回退到官方默认地址，
    因此调用方无需关心配置里是否填了自定义地址。
    """
    api_base = config.api_base
    if not api_base:
        provider_bases = {
            "openai": "https://api.openai.com/v1",
            "deepseek": "https://api.deepseek.com",
            "moonshot": "https://api.moonshot.cn/v1",
            "zhipu": "https://open.bigmodel.cn/api/paas/v4",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        }
        api_base = provider_bases.get(config.provider, "https://api.openai.com/v1")
    return f"{api_base.rstrip('/')}/chat/completions"


# 向后兼容旧命名
_get_api_url = get_api_url


def _build_request(config: AIConfig, messages: list[dict]) -> tuple:
    """构建 AI 请求的 URL, headers, payload"""
    url = get_api_url(config)
    api_key = (config.api_key or "").strip()
    if not api_key:
        raise ValueError("API Key 为空，请在设置页面配置 AI 模型的 API Key")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    return url, headers, payload


async def _get_kb_context_if_needed(db: AsyncSession, system_type: str, user_content: str) -> str:
    """当需要时获取知识库上下文注入到 AI prompt
    
    当 system_type 为 "kb" 或 auto_classify 检测到 kb 类型时，
    搜索知识库并返回格式化的上下文文本。
    """
    if system_type in ("kb", "auto"):
        try:
            from app.services.kb_service import search_for_ai_context
            kb_text = await search_for_ai_context(db, user_content, limit=5)
            if kb_text:
                return kb_text
        except Exception as e:
            logger.warning(f"知识库上下文检索失败: {e}")
    return ""


def _parse_ai_json(content: str) -> dict:
    """解析 AI 返回的 JSON（带容错处理）"""
    import re
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        start = 1 if lines[0].startswith("```") else 0
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        content = "\n".join(lines[start:end])
    
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning(f"AI 响应不是有效 JSON，尝试提取: {content[:200]}...")
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return {
            "analysis_markdown": content,
            "structured_data": {},
            "profile_updates": [],
        }


async def call_ai(
    db: AsyncSession,
    system_type: str,
    user_content: str,
    config: Optional[AIConfig] = None,
    module_name: Optional[str] = None,
    diary_date: Optional[date] = None,
) -> dict:
    """调用 AI 模型进行分析
    
    Args:
        db: 数据库会话
        system_type: 系统类型
        user_content: 用户输入内容
        config: AI 配置（可选，传入则直接使用）
        module_name: 模块名（可选，用于模块级模型选择）
    
    Returns:
        dict: 包含 analysis_markdown, structured_data, profile_updates 的字典
    """
    if config is None:
        config = await get_active_ai_config(db, module_name=module_name or system_type)
    
    if not config:
        raise ValueError("未配置 AI 模型，请先在设置页面配置 AI 模型信息")
    
    # 获取用户画像
    profile_text = await get_user_profile_text(db)
    
    # 获取 system prompt
    prompt_template = SYSTEM_PROMPTS.get(system_type)
    if not prompt_template:
        raise ValueError(f"未知的系统类型: {system_type}")
    
    system_prompt = prompt_template.replace("{user_profile}", profile_text)
    if system_type == "diary":
        target_date = diary_date or date.today()
        task_context = await get_task_context(db, target_date, target_date)
        system_prompt += "\n\n## 日记当天的任务参考记录\n" + task_context.text
        system_prompt += _DIARY_TASK_NOTE
    
    # 对 reading 类型注入已有知识体系
    if system_type == "reading" and "{existing_knowledge}" in system_prompt:
        knowledge_text = await get_existing_knowledge_text(db)
        system_prompt = system_prompt.replace("{existing_knowledge}", knowledge_text)
    
    # 知识库上下文注入（当 system_type 涉及 kb 时）
    kb_context = await _get_kb_context_if_needed(db, system_type, user_content)
    if kb_context:
        system_prompt = kb_context + "\n\n" + system_prompt
    
    # 构建请求
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    
    url, headers, payload = _build_request(config, messages)
    
    logger.info(f"调用 AI: provider={config.provider}, model={config.model}")
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        tokens_used = data.get("usage", {}).get("total_tokens", 0)
    
    result = _parse_ai_json(content)
    result["tokens_used"] = tokens_used
    return result


async def classify_content(db: AsyncSession, content: str) -> dict:
    """自动分类用户输入的内容类型"""
    config = await get_active_ai_config(db, module_name="auto_classify")
    if not config:
        raise ValueError("未配置 AI 模型")
    
    return await call_ai(db, "auto_classify", content, config, module_name="auto_classify")


async def call_ai_stream(
    db: AsyncSession,
    system_type: str,
    user_content: str,
    config: Optional[AIConfig] = None,
    module_name: Optional[str] = None,
    diary_date: Optional[date] = None,
) -> AsyncGenerator[str, None]:
    """流式调用 AI 模型，yield SSE 格式的数据块
    
    两阶段策略：
    1. 流式阶段：使用纯 Markdown prompt，AI 直接输出可渲染的 markdown
    2. 提取阶段：流结束后，用非流式调用从 markdown 中提取结构化数据
    
    Args:
        db: 数据库会话
        system_type: 系统类型
        user_content: 用户输入内容
        config: AI 配置（可选）
        module_name: 模块名（可选，用于模块级模型选择）
    
    Yields:
        SSE data lines: 'data: {...}\n\n'
    """
    if config is None:
        config = await get_active_ai_config(db, module_name=module_name or system_type)
    
    if not config:
        raise ValueError("未配置 AI 模型，请先在设置页面配置 AI 模型信息")
    
    profile_text = await get_user_profile_text(db)
    
    # 阶段一：使用流式 Prompt（纯 Markdown 输出）
    stream_template = STREAM_PROMPTS.get(system_type)
    if not stream_template:
        # 如果没有流式模板，回退到 JSON 模板
        stream_template = SYSTEM_PROMPTS.get(system_type)
    if not stream_template:
        raise ValueError(f"未知的系统类型: {system_type}")
    
    system_prompt = stream_template.replace("{user_profile}", profile_text)
    diary_context = ""
    if system_type == "diary":
        target_date = diary_date or date.today()
        task_context = await get_task_context(db, target_date, target_date)
        diary_context = task_context.text
        system_prompt += "\n\n## 日记当天的任务参考记录\n" + diary_context
        system_prompt += _DIARY_TASK_NOTE
    
    # 对 reading 类型注入已有知识体系
    _existing_knowledge_text = ""
    if system_type == "reading":
        _existing_knowledge_text = await get_existing_knowledge_text(db)
        if "{existing_knowledge}" in system_prompt:
            system_prompt = system_prompt.replace("{existing_knowledge}", _existing_knowledge_text)
    
    # 知识库上下文注入
    kb_context = await _get_kb_context_if_needed(db, system_type, user_content)
    if kb_context:
        system_prompt = kb_context + "\n\n" + system_prompt

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    
    url, headers, payload = _build_request(config, messages)
    payload["stream"] = True
    
    logger.info(f"流式调用 AI: provider={config.provider}, model={config.model}")
    
    full_content = ""
    last_yield_time = asyncio.get_event_loop().time()
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    # 每 15 秒发一次心跳，防止 Nginx/CDN 超时断连
                    now = asyncio.get_event_loop().time()
                    if now - last_yield_time > 15:
                        yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
                        last_yield_time = now
                    continue
                
                data_str = line[6:]  # 去掉 "data: " 前缀
                
                if data_str.strip() == "[DONE]":
                    break
                
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    # 思维链增量（thinking 模型返回）：以独立事件透出，旧前端忽略未知类型
                    reasoning_piece = delta.get("reasoning_content", "")
                    if reasoning_piece:
                        last_yield_time = asyncio.get_event_loop().time()
                        yield f"data: {json.dumps({'type': 'reasoning', 'content': reasoning_piece}, ensure_ascii=False)}\n\n"
                    content_piece = delta.get("content", "")

                    if content_piece:
                        full_content += content_piece
                        last_yield_time = asyncio.get_event_loop().time()
                        yield f"data: {json.dumps({'type': 'chunk', 'content': content_piece}, ensure_ascii=False)}\n\n"
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue
    
    # 阶段一完成，先发送 partial 事件（携带完整 markdown，供前端在提取失败时保存）
    yield f"data: {json.dumps({'type': 'partial', 'analysis_markdown': full_content}, ensure_ascii=False)}\n\n"
    
    # 阶段二：从 markdown 分析报告中提取结构化数据
    structured_result = {"structured_data": {}, "profile_updates": []}
    extract_template = EXTRACT_PROMPTS.get(system_type)
    if extract_template:
        try:
            logger.info("开始提取结构化数据...")
            yield f"data: {json.dumps({'type': 'status', 'message': '正在提取结构化数据...'}, ensure_ascii=False)}\n\n"
            
            extract_prompt = extract_template.replace("{analysis}", full_content)
            if system_type == "diary":
                extract_prompt += "\n\n## 原始日记\n" + user_content + "\n\n## 当天任务参考\n" + diary_context
                extract_prompt += "\n画像更新必须有原文证据，任务计划不能作为已经实现的证据；未确认的推测不写入确定性画像。"
            # 对 reading 类型注入已有知识体系到提取 prompt
            if system_type == "reading" and "{existing_knowledge}" in extract_prompt:
                extract_prompt = extract_prompt.replace("{existing_knowledge}", _existing_knowledge_text)
            extract_messages = [
                {"role": "system", "content": "你是一个数据提取助手，从分析报告中提取结构化数据。只输出 JSON。"},
                {"role": "user", "content": extract_prompt},
            ]
            
            extract_url, extract_headers, extract_payload = _build_request(config, extract_messages)
            # 提取用较低 token 限制，加快速度
            extract_payload["max_tokens"] = min(config.max_tokens, 2048)
            extract_payload["temperature"] = 0.1  # 低温度保证结构一致性
            # 提取是机械任务：关掉思维链，避免思考吃掉 token 上限导致 JSON 截断丢字段
            if config.provider == "deepseek":
                extract_payload["thinking"] = {"type": "disabled"}
            
            # 提取阶段加心跳协程，防止长时间无输出导致连接断开
            async def do_extract():
                async with httpx.AsyncClient(timeout=90.0) as client:
                    r = await client.post(extract_url, json=extract_payload, headers=extract_headers)
                    r.raise_for_status()
                    return r.json()
            
            async def heartbeat_loop():
                while True:
                    await asyncio.sleep(10)
                    yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
            
            # 并发：提取 + 心跳
            extract_task = asyncio.create_task(do_extract())
            heartbeat_sent = 0
            while not extract_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(extract_task), timeout=10.0)
                except asyncio.TimeoutError:
                    heartbeat_sent += 1
                    yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
            
            extract_data = extract_task.result()
            extract_content = extract_data["choices"][0]["message"]["content"]
            structured_result = _parse_ai_json(extract_content)
            
        except Exception as e:
            logger.warning(f"结构化数据提取失败: {e}")
            # 提取失败不影响主流程，直接用空结构化数据发 done
    
    # 发送最终结果
    result = {
        "analysis_markdown": full_content,
        "structured_data": structured_result.get("structured_data", {}),
        "profile_updates": structured_result.get("profile_updates", []),
    }
    yield f"data: {json.dumps({'type': 'done', 'result': result}, ensure_ascii=False)}\n\n"


# ==================== 用户画像周期性蒸馏（最小实现）====================

PROFILE_DISTILL_PROMPT = """你是用户的成长见证者和画像维护专家，正在做一次周期性的综合复盘（而非单篇内容分析）。

## 当前用户画像
{user_profile}

## 近14天的日记摘要
{diary_summary}

## 近14天的待办完成情况（按分类统计）
{todo_summary}

## 近14天的心力记录（成就/感恩）摘要
{wellbeing_summary}

## 近14天的心愿进展日志摘要
{wish_log_summary}

## 任务
这是一次**跨数据源的综合蒸馏**，不同于单篇内容分析，请重点关注：
1. 单次分析容易忽略的**跨领域模式**（比如某类待办完成率低、某个主题反复出现在日记和心力记录中）
2. **长期趋势**（比如情绪状态的变化方向、某项能力的持续精进）
3. **被反复提及但从未被记录的特征**
4. 与现有画像**矛盾或过时**的内容，应该用 delete 处理

## 输出 JSON 格式
```json
{{
  "profile_updates": [
    {{"category": "分类", "key": "特征键", "value": "特征值", "action": "create/update/delete/merge", "evidence": "支撑证据摘要"}}
  ],
  "summary": "一句话总结本次蒸馏最重要的发现"
}}
```

重要：只输出 JSON，不要输出其他内容。如果数据不足以支撑任何更新，profile_updates 返回空数组，summary 说明原因。
"""


async def distill_user_profile(db: AsyncSession) -> dict:
    """用户画像周期性蒸馏（最小实现）：
    整合近14天日记/待办完成/心力记录/心愿日志，一次性喂给 AI，产出结构化画像更新，
    直接复用 update_user_profile 完成落库，并记录本次蒸馏结果供追溯。
    """
    from datetime import datetime, timedelta

    period_end = datetime.now()
    period_start = period_end - timedelta(days=14)

    # ---- 收集数据：任一类失败都静默降级为空，不影响其他类 ----
    diary_lines: list[str] = []
    diary_count = 0
    try:
        from app.models.diary import DiaryEntry
        result = await db.execute(
            select(DiaryEntry)
            .where(DiaryEntry.date >= period_start.date())
            .order_by(DiaryEntry.date.desc())
            .limit(20)
        )
        diaries = list(result.scalars())
        diary_count = len(diaries)
        for d in diaries:
            preview = (d.content or "")[:100].replace("\n", " ")
            diary_lines.append(f"- {d.date}: {preview}")
    except Exception as e:
        logger.warning(f"画像蒸馏读取日记失败: {e}")

    todo_lines: list[str] = []
    todo_completed = 0
    try:
        from app.models.todo import TodoItem
        result = await db.execute(
            select(TodoItem.category, func.count(TodoItem.id))
            .where(
                TodoItem.status == "completed",
                TodoItem.completed_at >= period_start,
            )
            .group_by(TodoItem.category)
        )
        rows = list(result)
        todo_completed = sum(n for _, n in rows)
        for cat, n in rows:
            todo_lines.append(f"- {cat or '未分类'}: 完成 {n} 项")
    except Exception as e:
        logger.warning(f"画像蒸馏读取待办统计失败: {e}")

    wellbeing_lines: list[str] = []
    wellbeing_count = 0
    try:
        from app.models.wellbeing import WellbeingEntry
        result = await db.execute(
            select(WellbeingEntry)
            .where(WellbeingEntry.occurred_at >= period_start.date())
            .order_by(WellbeingEntry.occurred_at.desc())
            .limit(15)
        )
        entries = list(result.scalars())
        wellbeing_count = len(entries)
        for e in entries:
            wellbeing_lines.append(f"- [{e.type}] {e.content[:80]}")
    except Exception as e:
        logger.warning(f"画像蒸馏读取心力记录失败: {e}")

    wish_log_lines: list[str] = []
    wish_log_count = 0
    try:
        from app.models.wishlist import WishLogEntry
        result = await db.execute(
            select(WishLogEntry)
            .where(WishLogEntry.created_at >= period_start)
            .order_by(WishLogEntry.created_at.desc())
            .limit(15)
        )
        logs = list(result.scalars())
        wish_log_count = len(logs)
        for lg in logs:
            wish_log_lines.append(f"- (心愿#{lg.wish_id}) {lg.content[:80]}")
    except Exception as e:
        logger.warning(f"画像蒸馏读取心愿日志失败: {e}")

    sources_summary = {
        "diary_count": diary_count,
        "todo_completed": todo_completed,
        "wellbeing_count": wellbeing_count,
        "wish_log_count": wish_log_count,
    }

    profile_text = await get_user_profile_text(db)
    prompt = (
        PROFILE_DISTILL_PROMPT
        .replace("{user_profile}", profile_text)
        .replace("{diary_summary}", "\n".join(diary_lines) or "（近14天暂无日记）")
        .replace("{todo_summary}", "\n".join(todo_lines) or "（近14天暂无已完成待办）")
        .replace("{wellbeing_summary}", "\n".join(wellbeing_lines) or "（近14天暂无心力记录）")
        .replace("{wish_log_summary}", "\n".join(wish_log_lines) or "（近14天暂无心愿进展日志）")
    )

    # ---- 调用 AI（失败应向上抛出，因为这是用户主动触发的操作，不宜静默降级）----
    config = await get_active_ai_config(db, module_name="profile_distill")
    if not config:
        raise ValueError("未配置 AI 模型，请先在设置页面配置 AI 模型信息")

    messages = [
        {"role": "system", "content": "你是一个严谨的 JSON 输出助手，只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]
    url, headers, payload = _build_request(config, messages)
    payload["max_tokens"] = min(config.max_tokens, 2000)
    payload["temperature"] = 0.4

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    content = data["choices"][0]["message"]["content"]
    model_name = f"{config.provider}/{config.model}"
    parsed = _parse_ai_json(content)

    updated = await update_user_profile(db, parsed.get("profile_updates") or [])

    from app.models.ai_config import ProfileDistillRun
    run = ProfileDistillRun(
        period_start=period_start,
        period_end=period_end,
        sources_summary=sources_summary,
        profile_updates=updated,
        summary=parsed.get("summary") or "",
        model_used=model_name,
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)

    return {
        "summary": parsed.get("summary", ""),
        "updated": updated,
        "sources_summary": sources_summary,
        "run_id": run.id,
        "created_at": run.created_at.isoformat(),
    }

