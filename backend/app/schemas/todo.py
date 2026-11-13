"""待办模块的 Pydantic 模式"""

from datetime import datetime, date as DateType
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ==================== TodoItem Schemas ====================

class TodoBase(BaseModel):
    """待办基础模式"""
    title: str = Field(..., min_length=1, max_length=500, description="标题")
    description: Optional[str] = Field(None, description="详细描述")
    quadrant: int = Field(4, ge=1, le=4, description="四象限: 1=重要紧急 2=重要不紧急 3=紧急不重要 4=不重要不紧急")
    urgency: int = Field(3, ge=1, le=5, description="紧急度 1-5")
    importance: int = Field(3, ge=1, le=5, description="重要度 1-5")
    category: Optional[str] = Field(None, description="任务分类")
    tags: Optional[list[str]] = Field(None, description="标签")
    due_date: Optional[DateType] = Field(None, description="截止日期")
    scheduled_date: Optional[DateType] = Field(None, description="计划执行日期")
    scheduled_end_date: Optional[DateType] = Field(None, description="计划结束日期（跨天任务）")
    estimated_minutes: Optional[int] = Field(None, ge=1, description="预估耗时（分钟）")


class TodoCreate(TodoBase):
    """创建待办"""
    status: str = Field("inbox", description="状态")
    source: str = Field("manual", description="来源")
    source_id: Optional[int] = Field(None, description="来源 ID")
    parent_id: Optional[int] = Field(None, description="父任务 ID")
    ai_evaluation: Optional[str] = Field(None, description="AI 评估说明")
    ai_category: Optional[str] = Field(None, description="AI 分类")
    ai_answer: Optional[str] = Field(None, description="AI 直接解答")
    original_text: Optional[str] = Field(None, description="用户原始输入文本")
    sub_tasks: Optional[list[str]] = Field(None, description="子任务标题列表（创建时一并创建）")
    skip_ai_eval: bool = Field(False, description="跳过创建后的自动 AI 评估（新建待办表单默认不评估）")


class TodoUpdate(BaseModel):
    """更新待办"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    quadrant: Optional[int] = Field(None, ge=1, le=4)
    status: Optional[str] = None
    urgency: Optional[int] = Field(None, ge=1, le=5)
    importance: Optional[int] = Field(None, ge=1, le=5)
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    due_date: Optional[DateType] = None
    scheduled_date: Optional[DateType] = None
    scheduled_end_date: Optional[DateType] = None
    estimated_minutes: Optional[int] = Field(None, ge=1)
    actual_minutes: Optional[int] = Field(None, ge=1)
    deferred_until: Optional[DateType] = None
    completion_note: Optional[str] = Field(None, description="完成备注")
    completion_notes: Optional[list] = Field(None, description="完成备注列表（JSON数组）")


class TodoResponse(TodoBase):
    """待办响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str = "inbox"
    ai_evaluation: Optional[str] = None
    ai_category: Optional[str] = None
    ai_answer: Optional[str] = None
    original_text: Optional[str] = None
    source: str = "manual"
    source_id: Optional[int] = None
    parent_id: Optional[int] = None
    deferred_until: Optional[DateType] = None
    completion_note: Optional[str] = None
    completion_notes: Optional[list] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # 核心任务标记（week/month + 周期 key，过期自动失效）
    core_scope: Optional[str] = None
    core_period_key: Optional[str] = None
    # 子任务完成统计（供列表/日历/总览等各处展示进度）
    child_total: int = 0
    child_done: int = 0


class TodoListItem(BaseModel):
    """待办列表项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    quadrant: int = 4
    status: str = "inbox"
    urgency: int = 3
    importance: int = 3
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    ai_category: Optional[str] = None
    ai_evaluation: Optional[str] = None
    ai_answer: Optional[str] = None
    original_text: Optional[str] = None
    source: str = "manual"
    parent_id: Optional[int] = None
    due_date: Optional[DateType] = None
    scheduled_date: Optional[DateType] = None
    scheduled_end_date: Optional[DateType] = None
    estimated_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    deferred_until: Optional[DateType] = None
    completion_note: Optional[str] = None
    completion_notes: Optional[list] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # 核心任务标记（week/month + 周期 key，过期自动失效）
    core_scope: Optional[str] = None
    core_period_key: Optional[str] = None
    # 子任务完成统计（供列表/日历/总览等各处展示进度）
    child_total: int = 0
    child_done: int = 0


class CoreSetRequest(BaseModel):
    """设置/取消核心任务"""
    scope: Optional[str] = Field(None, description="week=本周核心 month=本月核心 year=年度目标 null=取消")


class CoreReviewRequest(BaseModel):
    """核心对齐检查请求"""
    scope: str = Field("week", description="week=本周 month=本月")


class CoreReviewResult(BaseModel):
    """核心对齐检查结果"""
    scope: str
    period_key: str
    core_titles: list[str]
    analysis: str
    elapsed_seconds: float = 0
    tokens_used: int = 0


class TodoOverview(BaseModel):
    """待办系统总览"""
    total_count: int = Field(0, description="总待办数")
    today_count: int = Field(0, description="今日计划数")
    week_completed: int = Field(0, description="本周完成数")
    max_streak: int = Field(0, description="最长习惯连续天数")
    quadrant_distribution: dict[int, int] = Field(default_factory=dict, description="四象限分布")
    category_distribution: dict[str, int] = Field(default_factory=dict, description="分类分布")
    status_distribution: dict[str, int] = Field(default_factory=dict, description="状态分布")


# ==================== BatchInput & AI Evaluation ====================

class BatchInputRequest(BaseModel):
    """批量输入请求"""
    content: str = Field(..., min_length=1, description="用户输入的想法/灵感/待办（自由格式）")


class AIEvaluationItem(BaseModel):
    """AI 评估结果项"""
    original_text: str = Field(..., description="原始输入文本")
    ai_category: str = Field(..., description="AI 分类: actionable/answerable/splittable/questionable/low_value")
    title: str = Field(..., description="整理后的标题")
    description: Optional[str] = Field(None, description="补充说明")
    quadrant: int = Field(4, ge=1, le=4, description="建议四象限")
    urgency: int = Field(3, ge=1, le=5, description="建议紧急度")
    importance: int = Field(3, ge=1, le=5, description="建议重要度")
    category: Optional[str] = Field(None, description="建议分类")
    ai_evaluation: str = Field("", description="AI 评估说明")
    ai_answer: Optional[str] = Field(None, description="直接解答内容（answerable 类型）")
    sub_tasks: Optional[list[str]] = Field(None, description="拆分的子任务（splittable 类型）")


class AIEvaluationResult(BaseModel):
    """AI 评估结果"""
    items: list[AIEvaluationItem] = Field(default_factory=list, description="评估项列表")
    summary: str = Field("", description="AI 总结说明")
    tokens_used: int = Field(0, description="消耗 token 数")


class BatchSaveRequest(BaseModel):
    """批量保存确认项"""
    items: list[TodoCreate] = Field(..., description="确认要保存的待办列表")


# ==================== RecurringTask Schemas ====================

class RecurringTaskCreate(BaseModel):
    """创建重复任务"""
    title: str = Field(..., min_length=1, max_length=500, description="习惯名称")
    description: Optional[str] = Field(None, description="描述")
    frequency: str = Field("daily", description="频率: daily/weekly/custom")
    frequency_detail: Optional[str] = Field(None, description="自定义周期详情")
    category: Optional[str] = Field(None, description="分类")
    auto_event: Optional[str] = Field(None, description="自动打卡事件: diary(写日记时)/basketball(保存篮球复盘后)")
    auto_keywords: Optional[str] = Field(None, description="自动打卡关键词，逗号分隔，如: 洗澡,冲凉")


class RecurringTaskUpdate(BaseModel):
    """更新重复任务"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    frequency: Optional[str] = None
    frequency_detail: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
    auto_event: Optional[str] = None
    auto_keywords: Optional[str] = None


class RecurringTaskResponse(BaseModel):
    """重复任务响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    frequency: str = "daily"
    frequency_detail: Optional[str] = None
    category: Optional[str] = None
    next_due: DateType
    streak: int = 0
    total_completed: int = 0
    last_checked_at: Optional[datetime] = None
    is_active: bool = True
    auto_event: Optional[str] = None
    auto_keywords: Optional[str] = None
    last_checkin_auto: bool = False
    created_at: datetime


# ==================== Review & Summary ====================

class ReviewStatsRequest(BaseModel):
    """回顾统计请求"""
    start_date: DateType = Field(..., description="开始日期")
    end_date: DateType = Field(..., description="结束日期")


class ReviewStats(BaseModel):
    """回顾统计数据"""
    total_created: int = 0
    total_completed: int = 0
    total_deferred: int = 0
    total_cancelled: int = 0
    completion_rate: float = 0.0
    quadrant_stats: dict[int, dict[str, int]] = Field(default_factory=dict, description="各象限新增/完成/推迟数")
    category_stats: dict[str, int] = Field(default_factory=dict, description="分类分布")
    daily_completion: dict[str, int] = Field(default_factory=dict, description="每日完成数")
    top_delayed: list[dict] = Field(default_factory=list, description="拖延最久的 Top 5")


class DiaryActionItem(BaseModel):
    """日记待认领 action item"""
    diary_id: int
    diary_date: DateType
    diary_title: str
    action_item: str


class ImportActionsRequest(BaseModel):
    """导入 action items 请求"""
    items: list[dict] = Field(..., description="要导入的 items，每项含 diary_id 和 action_item")


class SummaryRequest(BaseModel):
    """AI 总结请求"""
    start_date: DateType = Field(..., description="开始日期")
    end_date: DateType = Field(..., description="结束日期")


class SummaryResponse(BaseModel):
    """AI 总结响应"""
    markdown: str = Field("", description="Markdown 格式总结报告")
    tokens_used: int = Field(0, description="消耗 token 数")


# ==================== 提问功能 ====================

class TodoAskRequest(BaseModel):
    """待办提问请求"""
    question: str = Field(..., min_length=1, description="用户提问内容")
    reference_date: Optional[DateType] = Field(None, description="日历选中日期，作为这天/本周/本月的参考")


class TodoAskResult(BaseModel):
    """待办提问结果"""
    answer: str = Field("", description="AI 回答")
    matched_todos: list[TodoListItem] = Field(default_factory=list, description="匹配到的待办")
    tokens_used: int = Field(0, description="消耗 token 数")
    intent: str = Field("search", description="search搜索或summary总结")
    start_date: Optional[DateType] = None
    end_date: Optional[DateType] = None


# ==================== 收集箱历史 ====================

class InboxHistoryResponse(BaseModel):
    """收集箱历史记录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_input: str
    ai_markdown: Optional[str] = None
    structured_items: Optional[list] = None
    summary: Optional[str] = None
    saved_count: int = 0
    elapsed_seconds: Optional[float] = None
    created_at: datetime


class InboxHistorySaveRequest(BaseModel):
    """保存收集箱历史请求"""
    user_input: str = Field(..., description="用户原始输入")
    ai_markdown: Optional[str] = Field(None, description="AI原始Markdown回复")
    structured_items: Optional[list] = Field(None, description="结构化items")
    summary: Optional[str] = Field(None, description="总结")
    saved_count: int = Field(0, description="保存了几条")
    elapsed_seconds: Optional[float] = Field(None, description="耗时")


# ==================== 待办评论 ====================

class TodoCommentCreate(BaseModel):
    """新增待办评论"""
    content: str = Field(..., min_length=1, description="评论内容")
    kind: str = Field("idea", description="idea=想法记录 lesson=经验沉淀")
    author: Optional[str] = Field(None, description="作者（预留）")


class TodoCommentResponse(BaseModel):
    """待办评论响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    todo_id: int
    content: str
    kind: str = "idea"
    created_at: datetime
