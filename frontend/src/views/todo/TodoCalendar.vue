<script setup lang="ts">
import { ref, computed, onMounted, watch, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { API_BASE, TODO_API_BASE, TIME_API_BASE } from '@/config'
import ChildProgressBadge from '@/components/todo/ChildProgressBadge.vue'
import TaskCreateExtras from '@/components/todo/TaskCreateExtras.vue'
import CoreTasksBar from '@/components/todo/CoreTasksBar.vue'
import { isCoreActive } from '@/utils/corePeriod'
import { marked } from 'marked'

marked.setOptions({ breaks: true, gfm: true })

const route = useRoute()
const router = useRouter()
const runningSessions = ref<{ id: number; title: string | null }[]>([])
let runningTimer = 0

async function loadRunningSessions() {
  try {
    const res = await fetch(`${API_BASE}/api/agent/sessions`)
    if (!res.ok) return
    const rows = await res.json()
    runningSessions.value = (rows || []).filter((row: { status?: string }) => row.status === 'running')
  } catch { /* 没网时不打断日程 */ }
}

interface TodoItem {
  id: number
  title: string
  description?: string
  quadrant: number
  status: string
  category: string | null
  tags: string[] | null
  ai_category: string | null
  ai_evaluation: string | null
  ai_answer: string | null
  original_text: string | null
  source: string
  parent_id: number | null
  due_date: string | null
  scheduled_date: string | null
  scheduled_end_date: string | null
  estimated_minutes: number | null
  actual_minutes: number | null
  deferred_until: string | null
  completed_at: string | null
  completion_note: string | null
  completion_notes: Array<{ content: string; timestamp: string }> | null
  urgency: number
  importance: number
  core_scope?: 'week' | 'month' | 'year' | null
  core_period_key?: string | null
  created_at: string
  updated_at: string
  // 子任务完成统计（后端聚合返回）
  child_total?: number
  child_done?: number
}

// 当前显示的年月
const currentYear = ref(new Date().getFullYear())
const currentMonth = ref(new Date().getMonth()) // 0-indexed

// 数据
const calendarItems = ref<TodoItem[]>([])
const unscheduledItems = ref<TodoItem[]>([])
const unscheduledTotal = ref(0)
const loading = ref(false)
const unscheduledLoading = ref(false)

// AI 排期结果弹层仍在，入口已改到助手对话
const aiResult = ref<any>(null)
const showAiResult = ref(false)
const applyingSchedule = ref(false)
const aiScheduleDays = ref(7)
const showDaysSelector = ref(false)

// 手机端侧边栏展开/折叠
const sidebarExpanded = ref(false)
// 手机端快捷排期（替代拖拽）
const quickScheduleId = ref<number | null>(null)

// AI 体检
const aiScanning = ref(false)
const aiScanResult = ref<any>(null)
const showScanResult = ref(false)
const scanCategoryConfig: Record<string, { label: string; icon: string; color: string }> = {
  can_analyze: { label: '可帮你分析', icon: 'Search', color: '#3B82F6' },
  can_plan: { label: '可帮你细化', icon: 'Document', color: '#8B5CF6' },
  unnecessary: { label: '建议关闭', icon: 'Delete', color: '#94A3B8' },
  wrong_priority: { label: '优先级偏差', icon: 'WarningFilled', color: '#F59E0B' },
  can_answer: { label: '可直接解答', icon: 'Opportunity', color: '#10B981' },
  healthy: { label: '状态良好', icon: 'Check', color: '#6B7280' },
}
const scanSteps = ref<string[]>([])

function applyScanSuggestion(item: any) {
  if (!item.todo_id) return
  const updates: any = {}
  if (item.category === 'unnecessary') updates.status = 'wont_fix'
  else if (item.category === 'can_answer') { updates.status = 'completed'; updates.completion_note = item.suggestion }
  else if (item.category === 'wrong_priority' && item.suggested_quadrant) { updates.quadrant = item.suggested_quadrant; if (item.suggested_category) updates.category = item.suggested_category }
  if (Object.keys(updates).length === 0) return
  fetch(`${TODO_API_BASE}/${item.todo_id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(updates) })
    .then(() => { item._applied = true; fetchCalendarData() }).catch(() => {})
}

// 提问功能
const showAskModal = ref(false)
const askQuestion = ref('')
const askLoading = ref(false)
const askAnswer = ref('')
const askMatchedTodos = ref<TodoItem[]>([])
const askSteps = ref<string[]>([])
const askScope = ref('')
const askMatchesExpanded = ref(false)
let askRequestId = 0

async function submitAsk() {
  if (!askQuestion.value.trim() || askLoading.value) return
  const requestId = ++askRequestId
  askLoading.value = true
  askAnswer.value = ''
  askScope.value = ''
  askMatchesExpanded.value = false
  askMatchedTodos.value = []
  askSteps.value = ['正在理解问题与时间范围...']
  const timers = [
    setTimeout(() => { if (requestId === askRequestId && askLoading.value) askSteps.value.push('正在读取任务、计划、想法和完成记录...') }, 1500),
    setTimeout(() => { if (requestId === askRequestId && askLoading.value) askSteps.value.push('正在生成回答...') }, 4000),
  ]
  try {
    const res = await fetch(`${TODO_API_BASE}/ask`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: askQuestion.value, reference_date: selectedDate.value }),
    })
    const data = await res.json()
    if (requestId !== askRequestId) return
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '提问失败，请稍后重试')
    askAnswer.value = data.answer || ''
    askMatchedTodos.value = data.matched_todos || []
    askScope.value = data.start_date ? `${data.intent === 'summary' ? '总结' : '查询'}范围：${data.start_date} 至 ${data.end_date}` : '查询范围：当前未完成任务（不限日期）'
    saveAskHistory(askQuestion.value, askAnswer.value, askScope.value, askMatchedTodos.value)
  } catch (e: unknown) {
    if (requestId === askRequestId) askAnswer.value = e instanceof Error ? e.message : '网络错误'
  } finally {
    timers.forEach(clearTimeout)
    if (requestId === askRequestId) askLoading.value = false
  }
}

function askPeriod(question: string) {
  if (askLoading.value) return
  askQuestion.value = question
  submitAsk()
}

function closeAsk() {
  askRequestId++
  showAskModal.value = false
  askLoading.value = false
  askQuestion.value = ''
  askAnswer.value = ''
  askScope.value = ''
  askMatchesExpanded.value = false
  askMatchedTodos.value = []
  askSteps.value = []
}

// ==================== 核心任务条 / 对齐检查 ====================
const coreBarRef = ref<InstanceType<typeof CoreTasksBar> | null>(null)
const showCoreReview = ref(false)
const coreReviewScope = ref<'week' | 'month'>('week')
const coreReviewLoading = ref(false)
const coreReviewResult = ref<{ analysis: string; core_titles: string[]; period_key: string } | null>(null)

function openCoreReview() {
  showCoreReview.value = true
  coreReviewResult.value = null
}

async function runCoreReview() {
  coreReviewLoading.value = true
  coreReviewResult.value = null
  try {
    const res = await fetch(`${TODO_API_BASE}/core-review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: coreReviewScope.value }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '对齐检查失败，请稍后重试')
    coreReviewResult.value = data
  } catch (e: any) {
    alert(e.message || '对齐检查失败')
  } finally {
    coreReviewLoading.value = false
  }
}

// ==================== 提问历史（本地保存近7天） ====================
interface AskHistoryItem {
  id: string
  question: string
  answer: string
  scope: string
  matchedTitles: string[]
  createdAt: number
}

const ASK_HISTORY_KEY = 'todo_ask_history'
const ASK_HISTORY_DAYS = 7
const askHistory = ref<AskHistoryItem[]>([])
const showAskHistory = ref(false)

function loadAskHistory() {
  try {
    const all: AskHistoryItem[] = JSON.parse(localStorage.getItem(ASK_HISTORY_KEY) || '[]')
    const cutoff = Date.now() - ASK_HISTORY_DAYS * 24 * 3600 * 1000
    askHistory.value = all.filter(h => h.createdAt >= cutoff)
    if (askHistory.value.length !== all.length) persistAskHistory()
  } catch {
    askHistory.value = []
  }
}

function persistAskHistory() {
  try {
    localStorage.setItem(ASK_HISTORY_KEY, JSON.stringify(askHistory.value.slice(0, 100)))
  } catch { /* 存储不可用时静默降级 */ }
}

function saveAskHistory(question: string, answer: string, scope: string, todos: TodoItem[]) {
  if (!question.trim() || !answer.trim()) return
  loadAskHistory()
  askHistory.value.unshift({
    id: `ask_${Date.now()}`,
    question,
    answer,
    scope,
    matchedTitles: todos.map(t => stripMarkdownTitle(t.title)).slice(0, 20),
    createdAt: Date.now(),
  })
  persistAskHistory()
}

function replayAskHistory(h: AskHistoryItem) {
  if (askLoading.value) return
  askQuestion.value = h.question
  askAnswer.value = h.answer
  askScope.value = h.scope
  askMatchesExpanded.value = false
  askMatchedTodos.value = []
  showAskHistory.value = false
}

function removeAskHistory(id: string) {
  askHistory.value = askHistory.value.filter(h => h.id !== id)
  persistAskHistory()
}

function formatAskTime(ts: number) {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function renderAskAnswer(md: string) {
  try { return marked.parse(md) as string }
  catch { return md.replace(/\n/g, '<br>') }
}

function stripMarkdownTitle(title: string) {
  return String(title).replace(/[#*`>_~]/g, '').trim()
}

// 未安排任务搜索筛选
const unscheduledKeyword = ref('')
const unscheduledCategory = ref('')
const unscheduledQuadrant = ref<number | null>(null)

// 选中日期详情
const selectedDate = ref<string | null>(null)

// 编辑预估时间
const editingEstimate = ref<number | null>(null)
const estimateValue = ref<number | null>(null)

// 任务详情弹窗
const showDetailModal = ref(false)
const detailItem = ref<TodoItem | null>(null)
const isEditing = ref(false)
const childItems = ref<TodoItem[]>([])

// 核心任务设置（本周/本月核心，与全部待办页同一接口）
const detailStack = ref<TodoItem[]>([])
const toggleCore = async (scope: 'week' | 'month' | 'year') => {
  if (!detailItem.value) return
  const isActive = isCoreActive(detailItem.value) && detailItem.value.core_scope === scope
  try {
    const res = await fetch(`${TODO_API_BASE}/${detailItem.value.id}/core`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: isActive ? null : scope }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '设置失败')
    detailItem.value = { ...detailItem.value, core_scope: data.core_scope, core_period_key: data.core_period_key }
    coreBarRef.value?.reload?.()
    await Promise.all([fetchCalendarData(), fetchUnscheduled()])
  } catch (e: any) {
    alert(e.message || '设置核心失败')
  }
}
const childItemsSnapshot = ref<Record<number, { title: string; status: string }>>({})
const detailExpanded = ref(false)
const descExpanded = ref(false)
const newChildTitle = ref('')

// 详情区块折叠（创建信息默认折叠；支持一键折叠/展开）
const metaExpanded = ref(false)
const childrenExpanded = ref(true)
const commentsExpanded = ref(true)
const lessonsExpanded = ref(true)
const detailAllExpanded = computed(() => metaExpanded.value && childrenExpanded.value && commentsExpanded.value && lessonsExpanded.value)
const toggleAllSections = () => {
  const v = !detailAllExpanded.value
  metaExpanded.value = v
  childrenExpanded.value = v
  commentsExpanded.value = v
  lessonsExpanded.value = v
}
// 想法二次编辑
const editingCommentId = ref<number | null>(null)
const editingCommentText = ref('')
const startEditComment = (c: TodoComment) => { editingCommentId.value = c.id; editingCommentText.value = c.content }
const saveComment = async (c: TodoComment) => {
  const content = editingCommentText.value.trim()
  if (!content) return
  try {
    const res = await fetch(`${TODO_API_BASE}/comments/${c.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    })
    if (res.ok) { c.content = content; editingCommentId.value = null }
  } catch { /* */ }
}

// 待办评论（随时记录想法，重新打开可查看）
interface TodoComment {
  id: number
  todo_id: number
  content: string
  kind?: string
  created_at: string
}
const comments = ref<TodoComment[]>([])
const ideaComments = computed(() => comments.value.filter(c => (c.kind || 'idea') === 'idea'))
const lessonComments = computed(() => comments.value.filter(c => c.kind === 'lesson'))
const newComment = ref('')
const newLesson = ref('')
const commentSaving = ref(false)
const lessonSaving = ref(false)

async function loadComments(todoId: number) {
  try {
    const res = await fetch(`${TODO_API_BASE}/${todoId}/comments`)
    if (res.ok) {
      comments.value = await res.json()
    } else {
      comments.value = []
    }
  } catch {
    comments.value = []
  }
}

async function addComment(kind: 'idea' | 'lesson' = 'idea') {
  const source = kind === 'lesson' ? newLesson : newComment
  const content = source.value.trim()
  if (!content || !detailItem.value) return
  if (kind === 'lesson') lessonSaving.value = true
  else commentSaving.value = true
  try {
    const res = await fetch(`${TODO_API_BASE}/${detailItem.value.id}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, kind }),
    })
    if (res.ok) {
      comments.value.push(await res.json())
      source.value = ''
    }
  } catch { /* */ }
  commentSaving.value = false
  lessonSaving.value = false
}

const patchChildUrgency = async (child: TodoItem, event: Event) => {
  const urgency = Number((event.target as HTMLSelectElement).value)
  try {
    const res = await fetch(`${TODO_API_BASE}/${child.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urgency }),
    })
    if (res.ok) {
      child.urgency = urgency
      childItems.value.sort((a, b) => (b.urgency || 0) - (a.urgency || 0))
    }
  } catch { /* */ }
}

async function deleteComment(commentId: number) {
  if (!confirm('确定删除这条想法？')) return
  try {
    const res = await fetch(`${TODO_API_BASE}/comments/${commentId}`, { method: 'DELETE' })
    if (res.ok) {
      comments.value = comments.value.filter(c => c.id !== commentId)
    }
  } catch { /* */ }
}

// 子任务数量/完成数变化后，把各处持有的同一条父任务统计同步（无需刷新页面即生效）
const bumpChildStat = (parentId: number, field: 'child_total' | 'child_done', delta: number) => {
  const targets: TodoItem[] = [
    ...calendarItems.value,
    ...unscheduledItems.value,
    ...askMatchedTodos.value,
  ]
  for (const t of targets) {
    if (t.id === parentId) t[field] = Math.max(0, (t[field] || 0) + delta)
  }
  if (detailItem.value && detailItem.value.id === parentId) {
    detailItem.value[field] = Math.max(0, (detailItem.value[field] || 0) + delta)
  }
}

const bumpChildTotal = (parentId: number) => bumpChildStat(parentId, 'child_total', 1)

const addChildTask = async () => {
  if (!newChildTitle.value.trim() || !detailItem.value) return
  const parentId = detailItem.value.id
  try {
    const res = await fetch(`${TODO_API_BASE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newChildTitle.value.trim(), status: detailItem.value.status, source: 'manual', parent_id: parentId }),
    })
    if (res.ok) {
      const child = await res.json()
      childItems.value.push(child)
      childItemsSnapshot.value[child.id] = { title: child.title, status: child.status }
      bumpChildTotal(parentId)
      newChildTitle.value = ''
    }
  } catch { /* */ }
}

// 快速新增待办
const showCreateModal = ref(false)
const creating = ref(false)
const newTitle = ref('')
const newDescription = ref('')
const newQuadrant = ref(4)
const newCategory = ref('')
const newDueDate = ref('')
const newScheduledDate = ref('')
const newSubtasks = ref<string[]>([])
const newIsWork = ref(false)
const newMarkDone = ref(false)
const newAiEval = ref(true)
const addNewSubtask = () => { newSubtasks.value.push(''); nextTick(() => { const els = document.querySelectorAll('.create-form__sub-input'); (els[els.length-1] as HTMLInputElement)?.focus() }) }
const removeNewSubtask = (i: number) => { newSubtasks.value.splice(i, 1) }

const quadrantConfig: Record<number, { name: string; icon: string; color: string; bg: string }> = {
  1: { name: '重要紧急', icon: 'Flag', color: '#EF4444', bg: 'rgba(239, 68, 68, 0.12)' },
  2: { name: '重要不紧急', icon: 'Flag', color: '#3B82F6', bg: 'rgba(59, 130, 246, 0.12)' },
  3: { name: '紧急不重要', icon: 'Flag', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.12)' },
  4: { name: '不重要不紧急', icon: 'Remove', color: '#94A3B8', bg: 'rgba(148, 163, 184, 0.12)' },
}

const categoryLabels: Record<string, string> = {
  work: '工作', learning: '学习', life: '生活',
  health: '健康', social: '社交', finance: '财务', creative: '创意',
}

const statusLabels: Record<string, { label: string; color: string }> = {
  inbox: { label: '收集箱', color: '#94A3B8' },
  evaluated: { label: '已评估', color: '#8B5CF6' },
  planned: { label: '已计划', color: '#3B82F6' },
  in_progress: { label: '进行中', color: '#F59E0B' },
  completed: { label: '已完成', color: '#10B981' },
  cancelled: { label: '已取消', color: '#EF4444' },
  deferred: { label: '已推迟', color: '#6B7280' },
  wont_fix: { label: '不解决', color: '#9CA3AF' },
}

const aiCategoryLabels: Record<string, { label: string; icon: string; color: string }> = {
  actionable: { label: '可执行', icon: 'Check', color: '#10B981' },
  answerable: { label: '直接解答', icon: 'Opportunity', color: '#3B82F6' },
  splittable: { label: '需拆分', icon: 'Sort', color: '#8B5CF6' },
  inspiration: { label: '灵感', icon: 'Star', color: '#F472B6' },
  questionable: { label: '需澄清', icon: 'QuestionFilled', color: '#F59E0B' },
  low_value: { label: '低价值', icon: 'Remove', color: '#94A3B8' },
}

const weekDays = ['一', '二', '三', '四', '五', '六', '日']

// 计算日历格子
const calendarDays = computed(() => {
  const y = currentYear.value
  const m = currentMonth.value
  const firstDay = new Date(y, m, 1)
  const lastDay = new Date(y, m + 1, 0)

  let startOffset = firstDay.getDay() - 1
  if (startOffset < 0) startOffset = 6

  const days: Array<{ date: string; day: number; isCurrentMonth: boolean; isToday: boolean; isWeekend: boolean }> = []

  for (let i = startOffset - 1; i >= 0; i--) {
    const d = new Date(y, m, -i)
    days.push({
      date: formatDate(d),
      day: d.getDate(),
      isCurrentMonth: false,
      isToday: false,
      isWeekend: d.getDay() === 0 || d.getDay() === 6,
    })
  }

  const todayStr = formatDate(new Date())
  for (let d = 1; d <= lastDay.getDate(); d++) {
    const dateObj = new Date(y, m, d)
    const dateStr = formatDate(dateObj)
    days.push({
      date: dateStr,
      day: d,
      isCurrentMonth: true,
      isToday: dateStr === todayStr,
      isWeekend: dateObj.getDay() === 0 || dateObj.getDay() === 6,
    })
  }

  const remaining = 7 - (days.length % 7)
  if (remaining < 7) {
    for (let i = 1; i <= remaining; i++) {
      const d = new Date(y, m + 1, i)
      days.push({
        date: formatDate(d),
        day: d.getDate(),
        isCurrentMonth: false,
        isToday: false,
        isWeekend: d.getDay() === 0 || d.getDay() === 6,
      })
    }
  }

  return days
})

// 周末（周六/周日）在日历中不显示工作任务（周末不上班）；其它页面不受影响
const isWeekendDate = (dateStr: string) => {
  const day = new Date(`${dateStr}T00:00:00`).getDay()
  return day === 0 || day === 6
}
const hideOnDate = (item: TodoItem, dateStr: string) =>
  item.category === 'work' && isWeekendDate(dateStr)

const tasksByDate = computed(() => {
  const map: Record<string, TodoItem[]> = {}
  for (const item of calendarItems.value) {
    const startDate = item.scheduled_date || item.due_date
    if (!startDate) continue

    const endDate = item.scheduled_end_date
    if (endDate && endDate > startDate) {
      // 跨天任务：在工作日照常显示，周末段落跳过工作任务
      const start = new Date(startDate)
      const end = new Date(endDate)
      for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const dateStr = formatDate(d)
        if (hideOnDate(item, dateStr)) continue
        if (!map[dateStr]) map[dateStr] = []
        map[dateStr].push(item)
      }
    } else {
      // 单天任务
      if (hideOnDate(item, startDate)) continue
      if (!map[startDate]) map[startDate] = []
      map[startDate].push(item)
    }
  }
  return map
})

const selectedDateTasks = computed(() => {
  if (!selectedDate.value) return []
  const tasks = tasksByDate.value[selectedDate.value] || []
  // 已完成的任务自动沉底
  return [...tasks].sort((a, b) => {
    const aDone = (a.status === 'completed' || a.status === 'wont_fix') ? 1 : 0
    const bDone = (b.status === 'completed' || b.status === 'wont_fix') ? 1 : 0
    return aDone - bDone
  })
})

const monthLabel = computed(() => `${currentYear.value}年${currentMonth.value + 1}月`)

function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function prevMonth() {
  if (currentMonth.value === 0) {
    currentMonth.value = 11
    currentYear.value--
  } else {
    currentMonth.value--
  }
}

function nextMonth() {
  if (currentMonth.value === 11) {
    currentMonth.value = 0
    currentYear.value++
  } else {
    currentMonth.value++
  }
}

function goToday() {
  const now = new Date()
  currentYear.value = now.getFullYear()
  currentMonth.value = now.getMonth()
  selectedDate.value = formatDate(now)
}

async function fetchCalendarData() {
  loading.value = true
  const y = currentYear.value
  const m = currentMonth.value
  // 前后各多取一个月：日历里补位的其它月份格子（如停在 11 月看 10 月末）也要能显示当天任务
  const startDate = formatDate(new Date(y, m - 1, 1))
  const endDate = formatDate(new Date(y, m + 2, 0))

  try {
    const res = await fetch(`${TODO_API_BASE}/calendar?start_date=${startDate}&end_date=${endDate}`)
    if (res.ok) {
      const data = await res.json()
      calendarItems.value = data.items || []
    }
  } catch { /* */ }
  loading.value = false
}

async function fetchUnscheduled() {
  unscheduledLoading.value = true
  try {
    const params = new URLSearchParams({ limit: '100' })
    if (unscheduledKeyword.value) params.set('keyword', unscheduledKeyword.value)
    if (unscheduledCategory.value) params.set('category', unscheduledCategory.value)
    if (unscheduledQuadrant.value) params.set('quadrant', String(unscheduledQuadrant.value))
    const res = await fetch(`${TODO_API_BASE}/unscheduled?${params}`)
    if (res.ok) {
      const data = await res.json()
      unscheduledItems.value = data.items || []
      unscheduledTotal.value = data.total || 0
    }
  } catch { /* */ }
  unscheduledLoading.value = false
}

async function scheduleToDate(todoId: number, dateStr: string) {
  // 乐观更新：先从未安排列表移除，避免重新渲染导致滚动条重置
  const removedItem = unscheduledItems.value.find(i => i.id === todoId)
  unscheduledItems.value = unscheduledItems.value.filter(i => i.id !== todoId)
  if (removedItem) {
    // 乐观地将任务加入日历数据
    calendarItems.value.push({ ...removedItem, scheduled_date: dateStr, status: removedItem.status === 'inbox' || removedItem.status === 'evaluated' ? 'planned' : removedItem.status })
  }
  try {
    const res = await fetch(`${TODO_API_BASE}/schedule?todo_id=${todoId}&scheduled_date=${dateStr}`, {
      method: 'PATCH',
    })
    if (res.ok) {
      // 静默刷新日历数据（不影响未安排列表的滚动位置）
      fetchCalendarData()
    } else {
      // 请求失败，回滚乐观更新
      if (removedItem) {
        unscheduledItems.value.push(removedItem)
        calendarItems.value = calendarItems.value.filter(i => !(i.id === todoId && i.scheduled_date === dateStr))
      }
    }
  } catch {
    // 网络错误，回滚
    if (removedItem) {
      unscheduledItems.value.push(removedItem)
      calendarItems.value = calendarItems.value.filter(i => !(i.id === todoId && i.scheduled_date === dateStr))
    }
  }
}

async function unscheduleTask(todoId: number) {
  try {
    const res = await fetch(`${TODO_API_BASE}/${todoId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scheduled_date: null }),
    })
    if (res.ok) {
      await Promise.all([fetchCalendarData(), fetchUnscheduled()])
    }
  } catch { /* */ }
}

async function saveEstimate(todoId: number) {
  if (!estimateValue.value || estimateValue.value <= 0) {
    editingEstimate.value = null
    return
  }
  try {
    const res = await fetch(`${TODO_API_BASE}/${todoId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ estimated_minutes: estimateValue.value }),
    })
    if (res.ok) {
      const item = calendarItems.value.find(i => i.id === todoId)
      if (item) item.estimated_minutes = estimateValue.value
      const uItem = unscheduledItems.value.find(i => i.id === todoId)
      if (uItem) uItem.estimated_minutes = estimateValue.value
    }
  } catch { /* */ }
  editingEstimate.value = null
}

async function applyAiSchedule() {
  if (!aiResult.value?.schedule?.length) return
  applyingSchedule.value = true
  try {
    const res = await fetch(`${TODO_API_BASE}/apply-schedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(aiResult.value.schedule),
    })
    if (res.ok) {
      const data = await res.json()
      showAiResult.value = false
      aiResult.value = null
      await Promise.all([fetchCalendarData(), fetchUnscheduled()])
      alert(`✅ 已应用 ${data.count} 条排期`)
    }
  } catch (e: any) {
    alert(e.message || '应用排期失败')
  } finally {
    applyingSchedule.value = false
  }
}

// 任务详情弹窗
function closeCalendarDetail() {
  showDetailModal.value = false
  detailStack.value = []
}

function backToParentDetail() {
  const parent = detailStack.value.pop()
  if (parent) openDetail(parent, true)
  else closeCalendarDetail()
}

async function openDetail(item: TodoItem, fromStack = false) {
  if (!fromStack && showDetailModal.value && detailItem.value && detailItem.value.id !== item.id) {
    detailStack.value.push({ ...detailItem.value })
  }
  // 从 API 获取完整详情
  try {
    const res = await fetch(`${TODO_API_BASE}/${item.id}`)
    if (res.ok) {
      detailItem.value = await res.json()
    } else {
      detailItem.value = { ...item }
    }
  } catch {
    detailItem.value = { ...item }
  }
  isEditing.value = false
  showDetailModal.value = true
  // 加载评论（历史想法）
  newComment.value = ''
  newLesson.value = ''
  loadComments(item.id)
  // 获取子任务（专用端点，不受列表分页影响）
  childItems.value = []
  childItemsSnapshot.value = {}
  try {
    const res = await fetch(`${TODO_API_BASE}/${item.id}/children`)
    if (res.ok) {
      childItems.value = await res.json()
      for (const c of childItems.value) {
        childItemsSnapshot.value[c.id] = { title: c.title, status: c.status }
      }
    }
  } catch { /* */ }
}

async function saveEdit() {
  if (!detailItem.value) return
  try {
    const res = await fetch(`${TODO_API_BASE}/${detailItem.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: detailItem.value.title,
        description: detailItem.value.description,
        quadrant: detailItem.value.quadrant,
        category: detailItem.value.category,
        status: detailItem.value.status,
        due_date: detailItem.value.due_date,
        scheduled_date: detailItem.value.scheduled_date,
        scheduled_end_date: detailItem.value.scheduled_end_date,
        estimated_minutes: detailItem.value.estimated_minutes,
      }),
    })
    if (!res.ok) return

    // 保存被修改的子任务
    for (const child of childItems.value) {
      const snap = childItemsSnapshot.value[child.id]
      if (!snap || snap.title !== child.title || snap.status !== child.status) {
        await fetch(`${TODO_API_BASE}/${child.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: child.title,
            status: child.status,
          }),
        })
      }
    }

    showDetailModal.value = false
    await Promise.all([fetchCalendarData(), fetchUnscheduled()])
  } catch { /* */ }
}

async function deleteChildItem(childId: number) {
  if (!confirm('确定删除该子任务？')) return
  try {
    const res = await fetch(`${TODO_API_BASE}/${childId}`, { method: 'DELETE' })
    if (res.ok) {
      childItems.value = childItems.value.filter(c => c.id !== childId)
      delete childItemsSnapshot.value[childId]
    }
  } catch { /* */ }
}

async function toggleComplete(item: TodoItem) {
  // 如果未完成 → 打开完成弹窗
  if (item.status !== 'completed') {
    openCompleteModal(item)
    return
  }
  // 如果已完成 → toggle 回未完成
  try {
    const res = await fetch(`${TODO_API_BASE}/${item.id}/toggle`, { method: 'PATCH' })
    if (res.ok) {
      const updated = await res.json()
      item.status = updated.status
      item.completed_at = updated.completed_at
    }
  } catch { /* */ }
}

// 子任务勾掉时同样弹出完成框，记录备注和耗时；已完成再点则直接改回未完成
async function toggleChildComplete(child: TodoItem) {
  if (child.status !== 'completed') {
    openCompleteModal(child)
    return
  }
  try {
    const res = await fetch(`${TODO_API_BASE}/${child.id}/toggle`, { method: 'PATCH' })
    if (res.ok) {
      const updated = await res.json()
      const wasCompleted = child.status === 'completed'
      child.status = updated.status
      child.completed_at = updated.completed_at
      const idx = childItems.value.findIndex(c => c.id === child.id)
      if (idx >= 0) {
        childItems.value[idx] = { ...childItems.value[idx], status: updated.status, completed_at: updated.completed_at }
      }
      // 父任务完成数同步，勾选后进度徽章立即变化
      const nowCompleted = updated.status === 'completed'
      if (child.parent_id && nowCompleted !== wasCompleted) {
        bumpChildStat(child.parent_id, 'child_done', nowCompleted ? 1 : -1)
      }
    }
  } catch { /* */ }
}

// 完成任务弹窗
const showCompleteModal2 = ref(false)
const completingItem2 = ref<TodoItem | null>(null)
const actualMinutes2 = ref<number | null>(null)
const completionNote2 = ref('')
const existingNotes2 = ref<Array<{ content: string; timestamp: string }>>([])

const timeLogMinutes2 = ref<number | null>(null) // TimeLog 累计时间

async function openCompleteModal(item: TodoItem) {
  completingItem2.value = item
  actualMinutes2.value = item.estimated_minutes || null
  completionNote2.value = ''
  existingNotes2.value = (item as any).completion_notes || []
  timeLogMinutes2.value = null

  // 自动查询 TimeLog 累计时间
  try {
    const res = await fetch(`${TIME_API_BASE}/total/${item.id}`)
    if (res.ok) {
      const data = await res.json()
      if (data.total_minutes > 0) {
        timeLogMinutes2.value = data.total_minutes
        actualMinutes2.value = data.total_minutes
      }
    }
  } catch { /* */ }

  // 如果正在计时，先停止
  if (timerTodoId.value === item.id) {
    await stopTimer(item.id)
  }

  showCompleteModal2.value = true
}

async function submitComplete2() {
  if (!completingItem2.value) return
  try {
    const params = new URLSearchParams()
    params.set('todo_id', String(completingItem2.value.id))
    if (actualMinutes2.value) {
      params.set('actual_minutes', String(actualMinutes2.value))
    }
    if (completionNote2.value.trim()) {
      params.set('completion_note', completionNote2.value.trim())
    }
    const res = await fetch(`${TODO_API_BASE}/complete-with-time?${params}`, { method: 'PATCH' })
    if (res.ok) {
      const updated = await res.json()
      const idx = childItems.value.findIndex(c => c.id === completingItem2.value!.id)
      if (idx >= 0) {
        childItems.value[idx] = {
          ...childItems.value[idx],
          status: updated.status,
          completed_at: updated.completed_at,
          completion_notes: updated.completion_notes,
          actual_minutes: updated.actual_minutes,
        }
      }
      await Promise.all([fetchCalendarData(), fetchUnscheduled()])
    }
  } catch { /* */ }
  showCompleteModal2.value = false
  completingItem2.value = null
  actualMinutes2.value = null
  completionNote2.value = ''
  existingNotes2.value = []
}

function cancelComplete2() {
  showCompleteModal2.value = false
  completingItem2.value = null
  actualMinutes2.value = null
  completionNote2.value = ''
  existingNotes2.value = []
}

async function markWontFix2() {
  if (!completingItem2.value) return
  try {
    const res = await fetch(`${TODO_API_BASE}/${completingItem2.value.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'wont_fix' }),
    })
    if (res.ok) {
      await Promise.all([fetchCalendarData(), fetchUnscheduled()])
    }
  } catch { /* */ }
  showCompleteModal2.value = false
  completingItem2.value = null
  actualMinutes2.value = null
  completionNote2.value = ''
  existingNotes2.value = []
}

async function deleteItem(id: number) {
  if (!confirm('确定删除？')) return
  try {
    await fetch(`${TODO_API_BASE}/${id}`, { method: 'DELETE' })
    showDetailModal.value = false
    await Promise.all([fetchCalendarData(), fetchUnscheduled()])
  } catch { /* */ }
}

async function createItem() {
  if (!newTitle.value.trim()) return
  creating.value = true
  try {
    const scheduledDate = newScheduledDate.value || selectedDate.value || null
    const subs = newSubtasks.value.map(s => s.trim()).filter(Boolean)
    const todoData = {
      title: newTitle.value,
      description: newDescription.value || undefined,
      quadrant: newQuadrant.value,
      category: newIsWork.value ? 'work' : (newCategory.value || null),
      due_date: newDueDate.value || null,
      scheduled_date: scheduledDate,
      status: newMarkDone.value ? 'completed' : 'planned',
      original_text: newTitle.value,
      skip_ai_eval: !newAiEval.value,
      ...(subs.length > 0 ? { sub_tasks: subs } : {}),
    }

    let created = false
    if (navigator.onLine) {
      try {
        const controller = new AbortController()
        const tid = setTimeout(() => controller.abort(), 8000)
        const res = await fetch(`${TODO_API_BASE}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(todoData),
          signal: controller.signal,
        })
        clearTimeout(tid)
        created = res.ok
      } catch { /* 网络失败 */ }
    }

    if (!created) {
      const pending = JSON.parse(localStorage.getItem('pending_todos') || '[]')
      pending.push({ ...todoData, _created_at: new Date().toISOString() })
      localStorage.setItem('pending_todos', JSON.stringify(pending))
    }

    showCreateModal.value = false
    newTitle.value = ''
    newDescription.value = ''
    newQuadrant.value = 4
    newCategory.value = ''
    newDueDate.value = ''
    newScheduledDate.value = ''
    newSubtasks.value = []
    newIsWork.value = false
    newMarkDone.value = false
    newAiEval.value = true
    await Promise.all([fetchCalendarData(), fetchUnscheduled()])
    // 5秒后再刷新一次，此时后端AI分类应已完成
    setTimeout(() => { fetchCalendarData(); fetchUnscheduled() }, 5000)
  } catch (e) { /* 静默 */ }
  finally { creating.value = false }
}

// 同步本地缓存的待办到服务器（后端会自动触发AI分类）
async function syncPendingTodos() {
  if (!navigator.onLine) return
  const pending: any[] = JSON.parse(localStorage.getItem('pending_todos') || '[]')
  if (!pending.length) return
  const synced: number[] = []
  for (let i = 0; i < pending.length; i++) {
    const item = { ...pending[i] }
    delete item._created_at
    try {
      const r = await fetch(`${TODO_API_BASE}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(item),
      })
      if (r.ok) synced.push(i)
    } catch { break }
  }
  if (synced.length) {
    localStorage.setItem('pending_todos', JSON.stringify(pending.filter((_: any, i: number) => !synced.includes(i))))
    await Promise.all([fetchCalendarData(), fetchUnscheduled()])
  }
}
window.addEventListener('online', syncPendingTodos)

function daysSince(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime()
  return Math.floor(diff / (1000 * 60 * 60 * 24))
}

// 拖拽相关
const draggingId = ref<number | null>(null)
const dragOverId = ref<number | null>(null) // 用于排序占位
const isReordering = ref(false) // 是否在排序模式

// ==================== 计时器功能 ====================
const timerTodoId = ref<number | null>(null)
const timerStartTime = ref<Date | null>(null)
const timerElapsed = ref(0) // 秒
let timerInterval: ReturnType<typeof setInterval> | null = null

const formatTimer = (seconds: number): string => {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const startTimerTick = () => {
  if (timerInterval) clearInterval(timerInterval)
  timerInterval = setInterval(() => {
    if (timerStartTime.value) {
      timerElapsed.value = Math.floor((Date.now() - timerStartTime.value.getTime()) / 1000)
    }
  }, 1000)
}

const stopTimerTick = () => {
  if (timerInterval) {
    clearInterval(timerInterval)
    timerInterval = null
  }
}

const fetchCurrentTimer = async () => {
  try {
    const res = await fetch(`${TIME_API_BASE}/current`)
    if (!res.ok) return
    const data = await res.json()
    if (data.is_running && data.todo_id) {
      timerTodoId.value = data.todo_id
      timerStartTime.value = new Date(data.start_time)
      timerElapsed.value = data.elapsed_seconds || 0
      startTimerTick()
    } else {
      timerTodoId.value = null
      timerStartTime.value = null
      timerElapsed.value = 0
      stopTimerTick()
    }
  } catch { /* */ }
}

const startTimer = async (todoId: number) => {
  try {
    const res = await fetch(`${TIME_API_BASE}/start/${todoId}`, { method: 'POST' })
    if (!res.ok) return
    const data = await res.json()
    timerTodoId.value = data.todo_id
    timerStartTime.value = new Date(data.start_time)
    timerElapsed.value = 0
    startTimerTick()
  } catch { /* */ }
}

const stopTimer = async (todoId: number) => {
  try {
    const res = await fetch(`${TIME_API_BASE}/stop/${todoId}`, { method: 'POST' })
    if (!res.ok) return
    timerTodoId.value = null
    timerStartTime.value = null
    timerElapsed.value = 0
    stopTimerTick()
  } catch { /* */ }
}

function onDragStart(e: DragEvent, todoId: number) {
  draggingId.value = todoId
  e.dataTransfer?.setData('text/plain', String(todoId))
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}

function onDrop(e: DragEvent, dateStr: string) {
  e.preventDefault()
  const todoId = Number(e.dataTransfer?.getData('text/plain'))
  if (todoId) {
    scheduleToDate(todoId, dateStr)
  }
  draggingId.value = null
}

// ==================== 拖拽排序功能 ====================

// 侧边栏任务拖拽开始（排序模式）
function onSidebarDragStart(e: DragEvent, todoId: number) {
  draggingId.value = todoId
  isReordering.value = true
  e.dataTransfer?.setData('text/plain', String(todoId))
  e.dataTransfer!.effectAllowed = 'move'
}

// 侧边栏任务拖拽悬停
function onSidebarDragOver(e: DragEvent, targetId: number) {
  e.preventDefault()
  if (isReordering.value && draggingId.value !== targetId) {
    dragOverId.value = targetId
    e.dataTransfer!.dropEffect = 'move'
  }
}

// 侧边栏任务拖拽离开
function onSidebarDragLeave() {
  dragOverId.value = null
}

// 侧边栏任务放下（排序）
async function onSidebarDrop(e: DragEvent, targetId: number) {
  e.preventDefault()
  const draggedId = Number(e.dataTransfer?.getData('text/plain'))
  
  if (!draggedId || draggedId === targetId) {
    resetDragState()
    return
  }
  
  // 执行本地排序
  const tasks = [...selectedDateTasks.value]
  const draggedIndex = tasks.findIndex(t => t.id === draggedId)
  const targetIndex = tasks.findIndex(t => t.id === targetId)
  
  if (draggedIndex === -1 || targetIndex === -1) {
    resetDragState()
    return
  }
  
  // 移动元素
  const [draggedItem] = tasks.splice(draggedIndex, 1)
  tasks.splice(targetIndex, 0, draggedItem)
  
  // 调用后端更新排序
  const todoIds = tasks.map(t => t.id)
  try {
    await fetch(`${TODO_API_BASE}/reorder?todo_ids=${todoIds.join(',')}`, { method: 'POST' })
    // 重新获取数据以更新排序
    await fetchCalendarData()
  } catch (err) {
    console.error('排序更新失败:', err)
  }
  
  resetDragState()
}

function resetDragState() {
  draggingId.value = null
  dragOverId.value = null
  isReordering.value = false
}

function dayTotalMinutes(dateStr: string): number {
  const tasks = tasksByDate.value[dateStr] || []
  return tasks.reduce((sum, t) => sum + (t.estimated_minutes || 0), 0)
}

function dayLoadLevel(dateStr: string): string {
  const total = dayTotalMinutes(dateStr)
  if (total === 0) return ''
  if (total <= 180) return 'light'
  if (total <= 360) return 'moderate'
  return 'heavy'
}

// 手机端：快捷排期到选中日期
function quickScheduleToSelected(todoId: number) {
  if (selectedDate.value) {
    scheduleToDate(todoId, selectedDate.value)
    quickScheduleId.value = null
  }
}

watch([currentYear, currentMonth], () => {
  fetchCalendarData()
})

watch([unscheduledCategory, unscheduledQuadrant], () => {
  fetchUnscheduled()
})

watch(() => route.query.open, (value) => {
  const id = Number(value)
  if (id) openDetail({ id } as TodoItem)
}, { immediate: true })

onMounted(() => {
  fetchCalendarData()
  fetchUnscheduled()
  selectedDate.value = formatDate(new Date())
  fetchCurrentTimer()
  loadRunningSessions()
  runningTimer = window.setInterval(loadRunningSessions, 15000)
})

onUnmounted(() => {
  stopTimerTick()
  if (runningTimer) window.clearInterval(runningTimer)
})
</script>

<template>
  <div class="todo-calendar">
    <!-- Header -->
    <div class="todo-calendar__header">
      <div class="todo-calendar__header-left">
        <h1><Calendar class="ep-icon" /> 日历规划</h1>
      </div>
      <div class="todo-calendar__header-actions">
        <button class="btn btn--ghost btn--back" @click="router.push('/todo')">← 返回</button>
      </div>
    </div>

    <div v-if="runningSessions.length" class="running-lane">
      <span class="running-lane__label">AI 正在跑</span>
      <button
        v-for="session in runningSessions"
        :key="session.id"
        type="button"
        class="running-lane__item"
        @click="router.push({ path: '/assistant', query: { session: String(session.id) } })"
      >
        <span class="running-lane__dot"></span>
        {{ session.title || '未命名对话' }}
      </button>
    </div>

    <!-- 核心任务条：按选中日期所在周/月展示（切到历史日期回看当时的核心） -->
    <CoreTasksBar ref="coreBarRef" :selected-date="selectedDate" @open-task="(t) => openDetail(t as any)" @review="openCoreReview" />

    <div class="todo-calendar__layout">
      <!-- 左：日历 -->
      <div class="calendar-panel">
        <div class="calendar-nav">
          <button class="btn btn--sm btn--ghost" @click="prevMonth">◀</button>
          <h2 class="calendar-nav__title">{{ monthLabel }}</h2>
          <button class="btn btn--sm btn--ghost" @click="nextMonth">▶</button>
          <button class="btn btn--sm btn--ghost calendar-nav__today" @click="goToday">今天</button>
        </div>

        <div class="calendar-weekdays">
          <div v-for="d in weekDays" :key="d" class="calendar-weekday" :class="{ 'calendar-weekday--weekend': d === '六' || d === '日' }">{{ d }}</div>
        </div>

        <div class="calendar-grid">
          <div
            v-for="day in calendarDays"
            :key="day.date"
            class="calendar-cell"
            :class="{
              'calendar-cell--other': !day.isCurrentMonth,
              'calendar-cell--today': day.isToday,
              'calendar-cell--selected': selectedDate === day.date,
              'calendar-cell--weekend': day.isWeekend,
              [`calendar-cell--${dayLoadLevel(day.date)}`]: dayLoadLevel(day.date),
            }"
            @click="selectedDate = day.date"
            @dragover="onDragOver"
            @drop="onDrop($event, day.date)"
          >
            <div class="calendar-cell__header">
              <span class="calendar-cell__day">{{ day.day }}</span>
              <span v-if="dayTotalMinutes(day.date) > 0" class="calendar-cell__time">
                {{ Math.round(dayTotalMinutes(day.date) / 60 * 10) / 10 }}h
              </span>
            </div>
            <!-- 桌面端：显示任务卡片 -->
            <div class="calendar-cell__tasks calendar-cell__tasks--desktop">
              <div
                v-for="item in (tasksByDate[day.date] || []).slice(0, 3)"
                :key="item.id"
                class="calendar-task"
                :class="{ 'calendar-task--multi-day': item.scheduled_end_date && item.scheduled_end_date > (item.scheduled_date || '') }"
                :style="{ background: quadrantConfig[item.quadrant]?.bg, borderLeftColor: quadrantConfig[item.quadrant]?.color }"
                :title="item.scheduled_end_date ? `${item.title} (${item.scheduled_date} ~ ${item.scheduled_end_date})` : item.title"
                draggable="true"
                @dragstart="onDragStart($event, item.id)"
                @click.stop="openDetail(item)"
              >
                <span v-if="item.scheduled_end_date && item.scheduled_end_date > (item.scheduled_date || '')" class="calendar-task__multi-icon"><Calendar class="ep-icon" /></span>
                <span class="calendar-task__title" :style="{ color: quadrantConfig[item.quadrant]?.color }">{{ item.title }}</span>
                <ChildProgressBadge v-if="item.child_total" compact :total="item.child_total" :done="item.child_done || 0" />
              </div>
              <div v-if="(tasksByDate[day.date] || []).length > 3" class="calendar-cell__more">
                +{{ (tasksByDate[day.date] || []).length - 3 }}
              </div>
            </div>
            <!-- 手机端：只显示任务数量圆点 -->
            <div class="calendar-cell__tasks calendar-cell__tasks--mobile">
              <div v-if="(tasksByDate[day.date] || []).length > 0" class="calendar-cell__dots">
                <span
                  v-for="item in (tasksByDate[day.date] || []).slice(0, 4)"
                  :key="item.id"
                  class="calendar-cell__dot"
                  :style="{ background: quadrantConfig[item.quadrant]?.color }"
                ></span>
                <span v-if="(tasksByDate[day.date] || []).length > 4" class="calendar-cell__dot-more">
                  +{{ (tasksByDate[day.date] || []).length - 4 }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 手机端：侧边栏折叠按钮 -->
      <button class="sidebar-toggle" @click="sidebarExpanded = !sidebarExpanded">
        {{ sidebarExpanded ? '收起详情 ▲' : `展开详情 ▼ · ${selectedDate || ''} · ${selectedDateTasks.length}项 / 未排${unscheduledTotal}项` }}
      </button>

      <!-- 右：侧边栏 -->
      <div class="sidebar-panel" :class="{ 'sidebar-panel--expanded': sidebarExpanded }">
        <!-- 选中日期详情 -->
        <div v-if="selectedDate" class="sidebar-section">
          <h3 class="sidebar-section__title">
            <Document class="ep-icon" /> {{ selectedDate }}
            <span class="sidebar-section__count">{{ selectedDateTasks.length }} 项</span>
            <span v-if="dayTotalMinutes(selectedDate) > 0" class="sidebar-section__time">
              预计 {{ Math.round(dayTotalMinutes(selectedDate) / 60 * 10) / 10 }}h
            </span>
          </h3>
          <div v-if="selectedDateTasks.length === 0" class="sidebar-empty">
            <p>当天无任务</p>
            <p class="sidebar-empty__hint">拖拽下方未安排的任务到日历格子</p>
          </div>
          <div v-else class="sidebar-tasks">
            <div
              v-for="item in selectedDateTasks"
              :key="item.id"
              class="sidebar-task"
              :class="{
                'sidebar-task--done': item.status === 'completed' || item.status === 'wont_fix',
                'sidebar-task--dragging': draggingId === item.id,
                'sidebar-task--drag-over': dragOverId === item.id
              }"
              draggable="true"
              @dragstart="onSidebarDragStart($event, item.id)"
              @dragover="onSidebarDragOver($event, item.id)"
              @dragleave="onSidebarDragLeave"
              @drop="onSidebarDrop($event, item.id)"
              @dragend="resetDragState"
            >
              <div class="sidebar-task__header" @click="openDetail(item)">
                <label class="checkbox" @click.stop="toggleComplete(item)">
                  <input type="checkbox" :checked="item.status === 'completed'" @change.prevent />
                  <span class="checkbox__mark"></span>
                </label>
                <span class="sidebar-task__quadrant" :style="{ color: quadrantConfig[item.quadrant]?.color, background: quadrantConfig[item.quadrant]?.bg }">
                  <component :is="quadrantConfig[item.quadrant]?.icon" class="ep-icon" />
                </span>
                <span class="sidebar-task__title" :style="{ color: quadrantConfig[item.quadrant]?.color }">{{ item.title }}</span>
                <ChildProgressBadge v-if="item.child_total" :total="item.child_total" :done="item.child_done || 0" />
              </div>
              <div class="sidebar-task__meta">
                <span v-if="item.category" class="sidebar-task__cat">{{ categoryLabels[item.category] || item.category }}</span>
                <span class="sidebar-task__status" :style="{ color: statusLabels[item.status]?.color }">
                  {{ statusLabels[item.status]?.label }}
                </span>
                <!-- 计时按钮 -->
                <button
                  v-if="item.status !== 'completed' && item.status !== 'cancelled' && item.status !== 'wont_fix' && timerTodoId === item.id"
                  class="timer-btn timer-btn--active"
                  @click.stop="stopTimer(item.id)"
                  title="停止计时"
                >
                  <span class="timer-btn__icon">⏹️</span>
                  <span class="timer-btn__time">{{ formatTimer(timerElapsed) }}</span>
                </button>
                <button
                  v-else-if="item.status !== 'completed' && item.status !== 'cancelled' && item.status !== 'wont_fix'"
                  class="timer-btn"
                  @click.stop="startTimer(item.id)"
                  title="开始计时"
                >
                  <span class="timer-btn__icon">▶️</span>
                </button>
                <span v-if="item.estimated_minutes" class="sidebar-task__est" @click="editingEstimate = item.id; estimateValue = item.estimated_minutes">
                  <Timer class="ep-icon" />️ {{ item.estimated_minutes }}min
                </span>
                <span v-else class="sidebar-task__est sidebar-task__est--empty" @click="editingEstimate = item.id; estimateValue = 30">
                  + 预估时间
                </span>
                <span v-if="item.actual_minutes" class="sidebar-task__actual"><Check class="ep-icon" /> {{ item.actual_minutes }}min</span>
                <button class="btn-unschedule" @click="unscheduleTask(item.id)" title="取消安排，移回未排期池">
                  <span><Close class="ep-icon" /></span><span class="btn-unschedule__text"> 取消安排</span>
                </button>
              </div>
              <!-- 编辑预估时间 -->
              <div v-if="editingEstimate === item.id" class="sidebar-task__edit-est">
                <div class="quick-times">
                  <button v-for="t in [15, 30, 45, 60, 90, 120]" :key="t" class="btn btn--xs" :class="{ 'btn--primary': estimateValue === t }" @click="estimateValue = t">{{ t }}m</button>
                </div>
                <div class="edit-est-row">
                  <input type="number" v-model.number="estimateValue" min="1" class="edit-est-input" />
                  <button class="btn btn--xs btn--primary" @click="saveEstimate(item.id)">保存</button>
                  <button class="btn btn--xs btn--ghost" @click="editingEstimate = null">取消</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 未安排的任务池 -->
        <div class="sidebar-section">
          <h3 class="sidebar-section__title">
            <Box class="ep-icon" /> 未安排任务
            <span class="sidebar-section__count">{{ unscheduledTotal }}</span>
          </h3>

          <!-- 搜索和筛选 -->
          <div class="unscheduled-filters">
            <input
              v-model="unscheduledKeyword"
              class="unscheduled-filters__search"
              placeholder="🔍 搜索任务..."
              @keyup.enter="fetchUnscheduled"
            />
            <div class="unscheduled-filters__row">
              <select v-model="unscheduledCategory" class="unscheduled-filters__select">
                <option value="">全部分类</option>
                <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
              </select>
              <div class="unscheduled-filters__quadrants">
                <button
                  v-for="q in [1,2,3,4]"
                  :key="q"
                  class="quadrant-filter-btn"
                  :class="{ 'quadrant-filter-btn--active': unscheduledQuadrant === q }"
                  :style="{ borderColor: unscheduledQuadrant === q ? quadrantConfig[q].color : 'transparent' }"
                  @click="unscheduledQuadrant = unscheduledQuadrant === q ? null : q"
                  :title="quadrantConfig[q].name"
                ><component :is="quadrantConfig[q].icon" class="ep-icon" /></button>
              </div>
            </div>
          </div>

          <div v-if="unscheduledLoading" class="sidebar-loading">
            <div class="loading-spinner"></div>
          </div>
          <div v-else-if="unscheduledItems.length === 0" class="sidebar-empty">
            <p>👏 所有任务都已安排</p>
          </div>
          <div v-else class="unscheduled-list">
            <div
              v-for="item in unscheduledItems"
              :key="item.id"
              class="unscheduled-item"
              draggable="true"
              @dragstart="onDragStart($event, item.id)"
              :class="{ 'unscheduled-item--dragging': draggingId === item.id }"
            >
              <span class="unscheduled-item__icon" :style="{ color: quadrantConfig[item.quadrant]?.color }">
                <component :is="quadrantConfig[item.quadrant]?.icon" class="ep-icon" />
              </span>
              <div class="unscheduled-item__content" @click="openDetail(item)">
                <span class="unscheduled-item__title" :style="{ color: quadrantConfig[item.quadrant]?.color }">{{ item.title }}</span>
                <ChildProgressBadge v-if="item.child_total" :total="item.child_total" :done="item.child_done || 0" />
                <div class="unscheduled-item__meta">
                  <span v-if="item.category" class="unscheduled-item__cat">{{ categoryLabels[item.category] || item.category }}</span>
                  <span class="unscheduled-item__status" :style="{ color: statusLabels[item.status]?.color }">
                    {{ statusLabels[item.status]?.label }}
                  </span>
                  <span v-if="item.due_date" class="unscheduled-item__due">截止 {{ item.due_date }}</span>
                  <span v-if="item.estimated_minutes" class="unscheduled-item__est"><Timer class="ep-icon" />️ {{ item.estimated_minutes }}min</span>
                </div>
              </div>
              <div class="unscheduled-item__quick">
                <!-- 计时按钮 -->
                <button
                  v-if="timerTodoId === item.id"
                  class="timer-btn timer-btn--active"
                  @click.stop="stopTimer(item.id)"
                  title="停止计时"
                >
                  <span class="timer-btn__icon">⏹️</span>
                  <span class="timer-btn__time">{{ formatTimer(timerElapsed) }}</span>
                </button>
                <button
                  v-else
                  class="timer-btn"
                  @click.stop="startTimer(item.id)"
                  title="开始计时"
                >
                  <span class="timer-btn__icon">▶️</span>
                </button>
                <!-- 桌面端：今/明 快捷按钮 -->
                <button class="btn btn--xs btn--ghost unscheduled-item__quick-desktop" @click="scheduleToDate(item.id, formatDate(new Date()))" title="安排到今天">今</button>
                <button class="btn btn--xs btn--ghost unscheduled-item__quick-desktop" @click="scheduleToDate(item.id, formatDate(new Date(Date.now() + 86400000)))" title="安排到明天">明</button>
                <!-- 手机端：排到选中日期 -->
                <button
                  v-if="selectedDate"
                  class="btn btn--xs btn--primary unscheduled-item__quick-mobile"
                  @click="quickScheduleToSelected(item.id)"
                  :title="`排到 ${selectedDate}`"
                >
                  → {{ selectedDate.slice(5) }}
                </button>
                <button
                  class="btn btn--xs btn--ghost unscheduled-item__quick-mobile"
                  @click="scheduleToDate(item.id, formatDate(new Date()))"
                  title="安排到今天"
                >今</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 任务详情弹窗 (与全部待办保持一致) -->
    <div v-if="showDetailModal && detailItem" class="modal-overlay" @click.self="closeCalendarDetail">
      <div class="modal modal--detail">
        <div class="modal__header">
          <h3>{{ isEditing ? '编辑待办' : '待办详情' }}</h3>
          <div class="modal__header-actions">
            <button v-if="detailStack.length" class="btn btn--sm btn--ghost" @click="backToParentDetail">返回父任务</button>
            <button v-if="!isEditing" class="btn btn--sm btn--ghost" @click="toggleAllSections">{{ detailAllExpanded ? '一键折叠' : '一键展开' }}</button>
            <button v-if="!isEditing" class="btn btn--sm btn--ghost" @click="isEditing = true"><Edit class="ep-icon" /> 编辑</button>
            <button class="btn btn--sm btn--ghost" @click="closeCalendarDetail"><Close class="ep-icon" /></button>
          </div>
        </div>

        <!-- 详情视图 -->
        <template v-if="!isEditing">
          <div class="detail-section">
            <h4 class="detail-title">{{ detailItem.title }}</h4>
            <div class="detail-tags">
              <span class="detail-tag" :style="{ color: quadrantConfig[detailItem.quadrant]?.color, background: quadrantConfig[detailItem.quadrant]?.bg }">
                <component :is="quadrantConfig[detailItem.quadrant]?.icon" class="ep-icon" /> {{ quadrantConfig[detailItem.quadrant]?.name }}
              </span>
              <span v-if="detailItem.category" class="detail-tag detail-tag--category">
                {{ categoryLabels[detailItem.category] || detailItem.category }}
              </span>
              <span class="detail-tag" :style="{ color: statusLabels[detailItem.status]?.color }">
                {{ statusLabels[detailItem.status]?.label }}
              </span>
              <span v-if="detailItem.ai_category" class="detail-tag" :style="{ color: aiCategoryLabels[detailItem.ai_category]?.color }">
                <component :is="aiCategoryLabels[detailItem.ai_category]?.icon" class="ep-icon" /> {{ aiCategoryLabels[detailItem.ai_category]?.label }}
              </span>
            </div>
          </div>

          <!-- 原始输入 & AI 评估 (折叠) -->
          <div v-if="detailItem.original_text || detailItem.ai_evaluation" class="detail-collapse">
            <button class="detail-collapse__toggle" @click="detailExpanded = !detailExpanded">
              {{ detailExpanded ? '▼ 收起' : '▶ 原始输入 / AI 评估' }}
            </button>
            <template v-if="detailExpanded">
              <div v-if="detailItem.original_text" class="detail-section detail-section--highlight">
                <div class="detail-label"><Document class="ep-icon" /> 原始输入</div>
                <div class="detail-value">{{ detailItem.original_text }}</div>
              </div>
              <div v-if="detailItem.ai_evaluation" class="detail-section detail-section--ai">
                <div class="detail-label"><MagicStick class="ep-icon" /> AI 评估</div>
                <div class="detail-value">{{ detailItem.ai_evaluation }}</div>
              </div>
            </template>
          </div>

          <!-- AI 解答 -->
          <div v-if="detailItem.ai_answer && detailItem.ai_category !== 'inspiration'" class="detail-section detail-section--answer">
            <div class="detail-label"><Opportunity class="ep-icon" /> AI 解答</div>
            <div class="detail-value detail-value--answer">{{ detailItem.ai_answer }}</div>
          </div>

          <!-- 灵感点评 -->
          <div v-if="detailItem.ai_answer && detailItem.ai_category === 'inspiration'" class="detail-section detail-section--inspiration">
            <div class="detail-label"><Star class="ep-icon" /> 灵感点评</div>
            <div class="detail-value detail-value--inspiration">{{ detailItem.ai_answer }}</div>
          </div>

          <!-- 核心任务标记 -->
          <div class="detail-core">
            <span class="detail-core__label"><Star class="ep-icon" /> 核心任务：</span>
            <button
              class="detail-core__btn detail-core__btn--week"
              :class="{ 'detail-core__btn--on': isCoreActive(detailItem) && detailItem.core_scope === 'week' }"
              @click="toggleCore('week')"
            >{{ isCoreActive(detailItem) && detailItem.core_scope === 'week' ? '★ 本周核心（点击取消）' : '设为本周核心' }}</button>
            <button
              class="detail-core__btn detail-core__btn--month"
              :class="{ 'detail-core__btn--on': isCoreActive(detailItem) && detailItem.core_scope === 'month' }"
              @click="toggleCore('month')"
            >{{ isCoreActive(detailItem) && detailItem.core_scope === 'month' ? '★ 本月核心（点击取消）' : '设为本月核心' }}</button>
            <button
              class="detail-core__btn detail-core__btn--year"
              :class="{ 'detail-core__btn--on': isCoreActive(detailItem) && detailItem.core_scope === 'year' }"
              @click="toggleCore('year')"
            >{{ isCoreActive(detailItem) && detailItem.core_scope === 'year' ? '★ 年度目标（点击取消）' : '设为年度目标' }}</button>
          </div>

          <!-- 描述（默认折叠） -->
          <div v-if="detailItem.description" class="detail-collapse">
            <button class="detail-collapse__toggle" @click="descExpanded = !descExpanded">
              {{ descExpanded ? '▼ 收起描述' : '▶ 描述' }}
            </button>
            <div v-if="descExpanded" class="detail-section">
              <div class="detail-value">{{ detailItem.description }}</div>
            </div>
          </div>

          <!-- 子任务 -->
          <div class="detail-section">
            <button class="detail-label detail-label--toggle" @click="childrenExpanded = !childrenExpanded">
              <Collection class="ep-icon" /> 子任务 ({{ childItems.length }}) <span>{{ childrenExpanded ? '▾' : '▸' }}</span>
            </button>
            <template v-if="childrenExpanded">
            <div v-if="childItems.length > 0" class="detail-children">
              <div v-for="child in childItems" :key="child.id" class="detail-child-item"
                :class="{ 'detail-child-item--done': child.status === 'completed' }">
                <label class="checkbox" @click.stop="toggleChildComplete(child)">
                  <input type="checkbox" :checked="child.status === 'completed'" @change.prevent />
                  <span class="checkbox__mark"></span>
                </label>
                <span class="detail-child-item__flag" :style="{ color: quadrantConfig[child.quadrant]?.color }" :title="quadrantConfig[child.quadrant]?.name">
                  <component :is="quadrantConfig[child.quadrant]?.icon" class="ep-icon" />
                </span>
                <span class="detail-child-item__title" @click.stop="openDetail(child)">{{ child.title }}</span>
                <select class="detail-child-item__urg" :value="child.urgency" @click.stop @change="patchChildUrgency(child, $event)">
                  <option v-for="n in [5,4,3,2,1]" :key="n" :value="n">紧急{{ n }}</option>
                </select>
                <span class="detail-child-item__status" :style="{ color: statusLabels[child.status]?.color }">
                  {{ statusLabels[child.status]?.label }}
                </span>
              </div>
            </div>
            <div class="detail-add-child">
              <input v-model="newChildTitle" class="detail-add-child__input" placeholder="＋ 添加子任务" @keydown.enter.prevent="addChildTask" />
              <button v-if="newChildTitle.trim()" class="btn btn--sm btn--primary" @click="addChildTask">添加</button>
            </div>
            </template>
          </div>

          <!-- 完成备注 -->
          <div v-if="detailItem.completion_notes && detailItem.completion_notes.length > 0" class="detail-section detail-section--notes">
            <div class="detail-label"><ChatLineSquare class="ep-icon" /> 完成备注</div>
            <div class="detail-notes-list">
              <div v-for="(note, idx) in detailItem.completion_notes" :key="idx" class="detail-note-item">
                <span class="detail-note-content">{{ note.content }}</span>
                <span class="detail-note-time">{{ note.timestamp?.split('T')[0] || '' }}</span>
              </div>
            </div>
          </div>

          <!-- 评论：随时记录想法，支持二次编辑 -->
          <div class="detail-section detail-section--comments">
            <button class="detail-label detail-label--toggle" @click="commentsExpanded = !commentsExpanded">
              <ChatLineSquare class="ep-icon" /> 想法记录 ({{ ideaComments.length }}) <span>{{ commentsExpanded ? '▾' : '▸' }}</span>
            </button>
            <template v-if="commentsExpanded">
            <div v-if="ideaComments.length > 0" class="detail-notes-list">
              <div v-for="c in ideaComments" :key="c.id" class="detail-note-item">
                <template v-if="editingCommentId === c.id">
                  <input v-model="editingCommentText" class="detail-comment-edit" @keydown.enter.exact.prevent="saveComment(c)" />
                  <button class="detail-note-edit" @click.stop="saveComment(c)">保存</button>
                  <button class="detail-note-edit" @click.stop="editingCommentId = null">取消</button>
                </template>
                <template v-else>
                  <span class="detail-note-content">{{ c.content }}</span>
                  <span class="detail-note-time">{{ c.created_at?.replace('T', ' ').slice(0, 16) || '' }}</span>
                  <button class="detail-note-edit" @click.stop="startEditComment(c)" title="编辑">✎</button>
                  <button class="detail-note-del" @click.stop="deleteComment(c.id)" title="删除"><Close class="ep-icon" /></button>
                </template>
              </div>
            </div>
            <div class="detail-comment-input">
              <textarea
                v-model="newComment"
                class="detail-comment-textarea"
                rows="2"
                placeholder="随时记下你的想法..."
                @keydown.enter.exact.prevent="addComment('idea')"
              ></textarea>
              <button class="btn btn--sm btn--primary" :disabled="!newComment.trim() || commentSaving" @click="addComment('idea')">
                {{ commentSaving ? '保存中...' : '添加' }}
              </button>
            </div>
            </template>
          </div>

          <div class="detail-section detail-section--comments">
            <button class="detail-label detail-label--toggle" @click="lessonsExpanded = !lessonsExpanded">
              <Notebook class="ep-icon" /> 经验沉淀 ({{ lessonComments.length }}) <span>{{ lessonsExpanded ? '▾' : '▸' }}</span>
            </button>
            <template v-if="lessonsExpanded">
            <div v-if="lessonComments.length > 0" class="detail-notes-list">
              <div v-for="c in lessonComments" :key="c.id" class="detail-note-item">
                <template v-if="editingCommentId === c.id">
                  <input v-model="editingCommentText" class="detail-comment-edit" @keydown.enter.exact.prevent="saveComment(c)" />
                  <button class="detail-note-edit" @click.stop="saveComment(c)">保存</button>
                  <button class="detail-note-edit" @click.stop="editingCommentId = null">取消</button>
                </template>
                <template v-else>
                  <span class="detail-note-content">{{ c.content }}</span>
                  <span class="detail-note-time">{{ c.created_at?.replace('T', ' ').slice(0, 16) || '' }}</span>
                  <button class="detail-note-edit" @click.stop="startEditComment(c)" title="编辑">✎</button>
                  <button class="detail-note-del" @click.stop="deleteComment(c.id)" title="删除"><Close class="ep-icon" /></button>
                </template>
              </div>
            </div>
            <div class="detail-comment-input">
              <textarea
                v-model="newLesson"
                class="detail-comment-textarea"
                rows="2"
                placeholder="记下心得、教训、下次怎么做…"
                @keydown.enter.exact.prevent="addComment('lesson')"
              ></textarea>
              <button class="btn btn--sm btn--primary" :disabled="!newLesson.trim() || lessonSaving" @click="addComment('lesson')">
                {{ lessonSaving ? '保存中...' : '添加' }}
              </button>
            </div>
            </template>
          </div>

          <!-- 创建信息（默认折叠） -->
          <div class="detail-section detail-section--meta">
            <button class="detail-label detail-label--toggle" @click="metaExpanded = !metaExpanded">
              创建信息 <span>{{ metaExpanded ? '▾' : '▸' }}</span>
            </button>
            <div v-show="metaExpanded" class="detail-meta-grid">
              <div><span class="detail-meta-label">紧急度</span> <span class="detail-meta-value">{{ detailItem.urgency }}/5</span></div>
              <div><span class="detail-meta-label">重要度</span> <span class="detail-meta-value">{{ detailItem.importance }}/5</span></div>
              <div v-if="detailItem.due_date"><span class="detail-meta-label">截止日期</span> <span class="detail-meta-value">{{ detailItem.due_date }}</span></div>
              <div v-if="detailItem.scheduled_date"><span class="detail-meta-label">计划日期</span> <span class="detail-meta-value">{{ detailItem.scheduled_date }}{{ detailItem.scheduled_end_date ? ' ~ ' + detailItem.scheduled_end_date : '' }}</span></div>
              <div v-if="detailItem.estimated_minutes"><span class="detail-meta-label">预估耗时</span> <span class="detail-meta-value">{{ detailItem.estimated_minutes }}min</span></div>
              <div v-if="detailItem.actual_minutes"><span class="detail-meta-label">实际耗时</span> <span class="detail-meta-value">{{ detailItem.actual_minutes }}min</span></div>
              <div><span class="detail-meta-label">来源</span> <span class="detail-meta-value">{{ detailItem.source }}</span></div>
              <div><span class="detail-meta-label">创建于</span> <span class="detail-meta-value">{{ detailItem.created_at?.split('T')[0] }}</span></div>
              <div v-if="detailItem.completed_at"><span class="detail-meta-label">完成于</span> <span class="detail-meta-value">{{ detailItem.completed_at?.split('T')[0] }}</span></div>
              <div v-if="detailItem.status !== 'completed'"><span class="detail-meta-label">等待</span> <span class="detail-meta-value">{{ daysSince(detailItem.created_at) }} 天</span></div>
            </div>
          </div>

          <!-- 底部操作 -->
          <div class="detail-actions">
            <button v-if="detailItem.scheduled_date" class="btn btn--sm btn--ghost" @click="unscheduleTask(detailItem.id); showDetailModal = false">
              <Close class="ep-icon" /> 取消排期
            </button>
            <button class="btn btn--sm btn--ghost detail-actions__delete" @click="deleteItem(detailItem.id)"><Delete class="ep-icon" />️ 删除</button>
          </div>
        </template>

        <!-- 编辑视图 -->
        <template v-else>
          <div class="form-group">
            <label>标题</label>
            <input v-model="detailItem.title" class="form-input" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="detailItem.description" class="form-textarea" rows="3"></textarea>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>四象限</label>
              <select v-model="detailItem.quadrant" class="form-input">
                <option v-for="q in [1,2,3,4]" :key="q" :value="q">{{ quadrantConfig[q].name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>分类</label>
              <select v-model="detailItem.category" class="form-input">
                <option value="">无</option>
                <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>状态</label>
              <select v-model="detailItem.status" class="form-input">
                <option v-for="(cfg, key) in statusLabels" :key="key" :value="key">{{ cfg.label }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>截止日期</label>
              <input v-model="detailItem.due_date" type="date" class="form-input" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>计划日期</label>
              <input v-model="detailItem.scheduled_date" type="date" class="form-input" />
            </div>
            <div class="form-group">
              <label>结束日期 (跨天)</label>
              <input v-model="detailItem.scheduled_end_date" type="date" class="form-input" :min="detailItem.scheduled_date || ''" placeholder="留空为单天任务" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>预估耗时 (分钟)</label>
              <input v-model.number="detailItem.estimated_minutes" type="number" min="1" class="form-input" />
            </div>
          </div>

          <!-- 子任务编辑 -->
          <div v-if="childItems.length > 0" class="form-group">
            <label><FolderOpened class="ep-icon" /> 子任务 ({{ childItems.length }})</label>
            <div class="edit-children">
              <div v-for="child in childItems" :key="child.id" class="edit-child-item">
                <input v-model="child.title" class="form-input form-input--sm" placeholder="子任务标题" />
                <select v-model="child.status" class="form-input form-input--xs">
                  <option v-for="(cfg, key) in statusLabels" :key="key" :value="key">{{ cfg.label }}</option>
                </select>
                <button class="btn-child-delete" title="删除子任务" @click="deleteChildItem(child.id)"><Delete class="ep-icon" />️</button>
              </div>
            </div>
          </div>

          <div class="modal__actions">
            <button class="btn btn--ghost" @click="isEditing = false">取消编辑</button>
            <button class="btn btn--primary" @click="saveEdit">保存</button>
          </div>
        </template>
      </div>
    </div>

    <!-- AI 排期结果弹窗 -->
    <div v-if="showAiResult && aiResult" class="ai-overlay" @click.self="showAiResult = false">
      <div class="ai-modal">
        <div class="ai-modal__header">
          <h3><MagicStick class="ep-icon" /> AI 排期建议（{{ aiScheduleDays }}天）</h3>
          <button class="btn btn--sm btn--ghost" @click="showAiResult = false"><Close class="ep-icon" /></button>
        </div>
        <div class="ai-modal__body">
          <div v-if="aiResult.summary" class="ai-summary">
            <p>{{ aiResult.summary }}</p>
          </div>

          <div v-if="aiResult.tips?.length" class="ai-tips">
            <span v-for="(tip, i) in aiResult.tips" :key="i" class="ai-tip"><Opportunity class="ep-icon" /> {{ tip }}</span>
          </div>

          <div v-if="aiResult.schedule?.length" class="ai-schedule-list">
            <div v-for="s in aiResult.schedule" :key="s.todo_id" class="ai-schedule-item">
              <div class="ai-schedule-item__date">{{ s.scheduled_date }}</div>
              <div class="ai-schedule-item__content">
                <span class="ai-schedule-item__title">
                  {{ unscheduledItems.find(t => t.id === s.todo_id)?.title || `#${s.todo_id}` }}
                </span>
                <span v-if="s.estimated_minutes" class="ai-schedule-item__est"><Timer class="ep-icon" />️ {{ s.estimated_minutes }}min</span>
              </div>
              <div v-if="s.reason" class="ai-schedule-item__reason">{{ s.reason }}</div>
            </div>
          </div>
          <div v-else class="sidebar-empty">
            <p>AI 未生成排期建议</p>
          </div>
        </div>
        <div class="ai-modal__footer">
          <button class="btn btn--ghost" @click="showAiResult = false">取消</button>
          <button
            class="btn btn--primary"
            :disabled="!aiResult.schedule?.length || applyingSchedule"
            @click="applyAiSchedule"
          >
            {{ applyingSchedule ? '应用中...' : `✅ 全部应用 (${aiResult.schedule?.length || 0} 条)` }}
          </button>
        </div>
      </div>
    </div>

    <!-- 点击外部关闭天数选择器 -->
    <div v-if="showDaysSelector" class="days-selector-backdrop" @click="showDaysSelector = false"></div>

    <!-- 完成记录耗时弹窗 -->
    <div v-if="showCompleteModal2 && completingItem2" class="modal-overlay" @click.self="cancelComplete2">
      <div class="modal modal--complete">
        <div class="modal__header">
          <h3><Check class="ep-icon" /> 完成任务</h3>
          <button class="btn btn--sm btn--ghost" @click="cancelComplete2"><Close class="ep-icon" /></button>
        </div>
        <div class="complete-modal__body">
          <p class="complete-modal__title">{{ completingItem2.title }}</p>
          <div class="complete-modal__field">
            <label>实际耗时（分钟，可不填）</label>
            <p v-if="timeLogMinutes2" class="complete-modal__timelog-hint">
              <Timer class="ep-icon" />️ 计时记录累计 <strong>{{ timeLogMinutes2 >= 60 ? Math.floor(timeLogMinutes2 / 60) + ' 小时 ' + (timeLogMinutes2 % 60 > 0 ? timeLogMinutes2 % 60 + ' 分钟' : '') : timeLogMinutes2 + ' 分钟' }}</strong>，已自动填入
            </p>
            <div class="complete-modal__input-row">
              <button v-if="timeLogMinutes2" class="btn btn--sm" :class="{ 'btn--primary': actualMinutes2 === timeLogMinutes2 }" @click="actualMinutes2 = timeLogMinutes2">{{ timeLogMinutes2 }}min (计时)</button>
              <button v-for="t in [5, 15, 30, 60, 120]" :key="t" class="btn btn--sm" :class="{ 'btn--primary': actualMinutes2 === t }" @click="actualMinutes2 = t">{{ t }}min</button>
              <button class="btn btn--sm" :class="{ 'btn--primary': actualMinutes2 === null }" @click="actualMinutes2 = null">不记录</button>
            </div>
            <input type="number" v-model.number="actualMinutes2" min="1" placeholder="自定义分钟数" class="complete-modal__input" />
          </div>
          <!-- 已有备注 -->
          <div v-if="existingNotes2.length > 0" class="complete-modal__field">
            <label><EditPen class="ep-icon" /> 已有备注</label>
            <div class="complete-modal__notes-list">
              <div v-for="(note, idx) in existingNotes2" :key="idx" class="complete-modal__note-item">
                <span class="complete-modal__note-content">{{ note.content }}</span>
                <span class="complete-modal__note-time">{{ note.timestamp?.split('T')[0] || '' }}</span>
              </div>
            </div>
          </div>
          <div class="complete-modal__field">
            <label>{{ existingNotes2.length > 0 ? '追加备注（可选）' : '备注（可选）' }}</label>
            <textarea v-model="completionNote2" class="complete-modal__textarea" rows="2" placeholder="记录些什么..."></textarea>
          </div>
          <p v-if="completingItem2.estimated_minutes" class="complete-modal__hint">
            预估耗时：{{ completingItem2.estimated_minutes }} 分钟
            <template v-if="actualMinutes2">
              <span v-if="actualMinutes2 <= completingItem2.estimated_minutes" style="color: #10B981"> → 比预期快 👏</span>
              <span v-else style="color: #F59E0B"> → 比预期多 {{ actualMinutes2 - completingItem2.estimated_minutes }} 分钟</span>
            </template>
          </p>
        </div>
        <div class="modal__actions">
          <button class="btn btn--ghost" @click="cancelComplete2">取消</button>
          <button class="btn btn--ghost" @click="markWontFix2" title="标记为不解决，不记录耗时"><Close class="ep-icon" /> 不解决</button>
          <button class="btn btn--primary" @click="submitComplete2"><Check class="ep-icon" /> 确认完成</button>
        </div>
      </div>
    </div>

    <!-- 浮动新增按钮 -->
    <button class="fab" @click="showCreateModal = true" title="新增待办">+</button>

    <!-- 新建待办 Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal modal--create">
        <div class="modal__header">
          <h3><Document class="ep-icon" /> 快速新增待办</h3>
          <div class="modal__header-actions">
            <button class="btn btn--sm btn--ghost" @click="showCreateModal = false"><Close class="ep-icon" /></button>
          </div>
        </div>
        <div class="create-form__body">
          <div class="create-form__group">
            <label>标题 <span class="create-form__required">*</span></label>
            <input
              v-model="newTitle"
              class="create-form__input"
              placeholder="输入待办标题..."
              @keydown.enter="createItem"
              autofocus
            />
          </div>
          <div class="create-form__group">
            <label>描述（可选）</label>
            <textarea v-model="newDescription" class="create-form__textarea" rows="2" placeholder="补充描述..."></textarea>
          </div>
          <div class="create-form__row">
            <div class="create-form__group">
              <label>四象限</label>
              <select v-model="newQuadrant" class="create-form__input">
                <option :value="1">🔴 重要紧急</option>
                <option :value="2">🔵 重要不紧急</option>
                <option :value="3">🟠 紧急不重要</option>
                <option :value="4">⚪ 不重要不紧急</option>
              </select>
            </div>
            <div class="create-form__group">
              <label>分类</label>
              <select v-model="newCategory" class="create-form__input">
                <option value="">无</option>
                <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
              </select>
            </div>
          </div>
          <div class="create-form__row">
            <div class="create-form__group">
              <label>截止日期</label>
              <input v-model="newDueDate" type="date" class="create-form__input" />
            </div>
            <div class="create-form__group">
              <label>计划日期 <span v-if="selectedDate && !newScheduledDate" class="create-form__hint">默认用选中的 {{ selectedDate }}</span></label>
              <input v-model="newScheduledDate" type="date" class="create-form__input" />
            </div>
          </div>
          <!-- 子任务 -->
          <div class="create-form__group">
            <label>子任务（可选）</label>
            <div v-if="newSubtasks.length" class="create-form__sub-list">
              <div v-for="(_, i) in newSubtasks" :key="i" class="create-form__sub-row">
                <span class="create-form__sub-bullet">○</span>
                <input v-model="newSubtasks[i]" class="create-form__sub-input" :placeholder="`子任务 ${i+1}`" @keydown.enter.prevent="addNewSubtask" @keydown.backspace="!newSubtasks[i] && removeNewSubtask(i)" />
                <button class="create-form__sub-del" @click="removeNewSubtask(i)"><Close class="ep-icon" /></button>
              </div>
            </div>
            <button class="create-form__add-sub" @click="addNewSubtask" type="button">＋ 添加子任务</button>
          </div>
          <div class="create-form__group">
            <TaskCreateExtras v-model:work="newIsWork" v-model:markDone="newMarkDone" v-model:aiEval="newAiEval" />
          </div>
        </div>
        <div class="modal__actions">
          <button class="btn btn--ghost" @click="showCreateModal = false" :disabled="creating">取消</button>
          <button class="btn btn--primary" @click="createItem" :disabled="!newTitle.trim() || creating">
            <MagicStick v-if="creating" class="ep-icon" /> {{ creating ? 'AI 分类中...' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- AI 体检面板 -->
  <div v-if="showScanResult" class="ai-overlay" @click.self="showScanResult = false">
    <div class="ai-modal ai-modal--scan">
      <div class="ai-modal__header">
        <h3><Aim class="ep-icon" /> AI 任务体检</h3>
        <button class="btn btn--sm btn--ghost" @click="showScanResult = false"><Close class="ep-icon" /></button>
      </div>
      <div class="ai-modal__body">
        <div v-if="aiScanning" class="scan-progress">
          <div class="loading-spinner" style="width:24px;height:24px;margin:0 auto 12px"></div>
          <div v-for="(step, i) in scanSteps" :key="i" class="scan-step" :class="{ 'scan-step--latest': i === scanSteps.length - 1 }">
            <span class="scan-step__dot"><Clock v-if="i === scanSteps.length - 1" class="ep-icon" /><Check v-else class="ep-icon" /></span> {{ step }}
          </div>
        </div>
        <div v-else-if="aiScanResult?.error" style="color:#EF4444;padding:20px">{{ aiScanResult.error }}</div>
        <template v-else-if="aiScanResult">
          <div class="scan-summary-box">
            <p>{{ aiScanResult.scan_summary }}</p>
            <div class="scan-stats-row">
              <span>扫描 {{ aiScanResult.total_scanned || 0 }} 条</span>
              <span>健康 {{ aiScanResult.healthy_count || 0 }} 条</span>
              <span>有建议 {{ (aiScanResult.items || []).length }} 条</span>
            </div>
          </div>
          <div v-for="(item, idx) in (aiScanResult.items || []).filter((i: any) => i.category !== 'healthy')" :key="idx" class="scan-card" :class="{ 'scan-card--applied': item._applied }">
            <div class="scan-card__header">
              <span :style="{ color: scanCategoryConfig[item.category]?.color }"><component :is="scanCategoryConfig[item.category]?.icon" class="ep-icon" /> {{ scanCategoryConfig[item.category]?.label }}</span>
              <span class="scan-card__title">{{ item.todo_title }}</span>
            </div>
            <div class="scan-card__reason">{{ item.reason }}</div>
            <div v-if="item.suggestion" class="scan-card__suggestion"><Opportunity class="ep-icon" /> {{ item.suggestion }}</div>
            <div class="scan-card__actions" v-if="!item._applied">
              <button v-if="item.category === 'unnecessary'" class="btn btn--xs btn--ghost" @click="applyScanSuggestion(item)">标记不解决</button>
              <button v-if="item.category === 'can_answer'" class="btn btn--xs btn--primary" @click="applyScanSuggestion(item)">采纳并完成</button>
              <button v-if="item.category === 'wrong_priority'" class="btn btn--xs btn--ghost" @click="applyScanSuggestion(item)">修正优先级</button>
            </div>
            <div v-else style="font-size:13px;color:#10B981"><Check class="ep-icon" /> 已采纳</div>
          </div>
        </template>
      </div>
    </div>
  </div>

  <!-- 提问弹窗 -->
  <div v-if="showAskModal" class="ai-overlay" @click.self="closeAsk">
    <div class="ai-modal ai-modal--ask">
      <div class="ai-modal__header">
        <h3><Search class="ep-icon" /> 向待办提问</h3>
        <button class="btn btn--sm btn--ghost" @click="closeAsk"><Close class="ep-icon" /></button>
      </div>
      <div class="ai-modal__body">
        <div class="ask-context">
          <p>参考日期：{{ selectedDate || '今天' }}；本周、本月以此日期为参考，“今天”指实际今天。</p>
          <div class="ask-context__actions">
            <button class="btn btn--sm btn--ghost" :disabled="askLoading" @click="askPeriod('生成今天的日报')">日报</button>
            <button class="btn btn--sm btn--ghost" :disabled="askLoading" @click="askPeriod('生成本周周报')">周报</button>
            <button class="btn btn--sm btn--ghost" :disabled="askLoading" @click="askPeriod('总结近一周做了什么')">近一周</button>
            <button class="btn btn--sm btn--ghost" :disabled="askLoading" @click="askPeriod('总结近一个月做了什么')">近一个月</button>
            <button class="btn btn--sm btn--ghost" @click="showAskHistory = !showAskHistory">
              <Clock class="ep-icon" /> 历史<template v-if="askHistory.length"> ({{ askHistory.length }})</template>
            </button>
          </div>
          <div v-if="showAskHistory" class="ask-history">
            <div v-if="askHistory.length === 0" class="ask-history__empty">近7天没有提问记录</div>
            <div v-for="h in askHistory" :key="h.id" class="ask-history__item">
              <div class="ask-history__main" title="点击回看这次问答" @click="replayAskHistory(h)">
                <div class="ask-history__q">{{ h.question }}</div>
                <div class="ask-history__meta">{{ formatAskTime(h.createdAt) }}<template v-if="h.scope"> · {{ h.scope }}</template></div>
              </div>
              <button class="ask-history__del" title="删除这条记录" @click.stop="removeAskHistory(h.id)"><Delete class="ep-icon" /></button>
            </div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-bottom:16px">
          <textarea v-model="askQuestion" placeholder="例如：总结本周做了什么；搜索协议相关任务；这天有哪些计划还没完成？" rows="2" style="flex:1;padding:10px;border:1px solid #d0d7de;border-radius:8px;font-size:14px;resize:none;outline:none" :disabled="askLoading" @keydown.ctrl.enter="submitAsk"></textarea>
          <button class="btn btn--primary" @click="submitAsk" :disabled="!askQuestion.trim() || askLoading" style="white-space:nowrap"><Refresh v-if="askLoading" class="ep-icon" /><MagicStick v-else class="ep-icon" /> {{ askLoading ? '' : '提问' }}</button>
        </div>
        <div v-if="askLoading" class="scan-progress">
          <div class="loading-spinner" style="width:24px;height:24px;margin:0 auto 12px"></div>
          <div v-for="(step, i) in askSteps" :key="i" class="scan-step" :class="{ 'scan-step--latest': i === askSteps.length - 1 }">
            <span class="scan-step__dot"><Clock v-if="i === askSteps.length - 1" class="ep-icon" /><Check v-else class="ep-icon" /></span> {{ step }}
          </div>
        </div>
        <div v-if="askAnswer" style="margin-top:12px">
          <div style="font-size:13px;color:#64748B;margin-bottom:4px"><Opportunity class="ep-icon" /> AI 回答</div>
          <p v-if="askScope" class="ask-context__scope">{{ askScope }}</p>
          <div class="ask-answer" v-html="renderAskAnswer(askAnswer)"></div>
        </div>
        <div v-if="askMatchedTodos.length > 0" style="margin-top:12px">
          <button class="ask-matches__toggle" @click="askMatchesExpanded = !askMatchesExpanded">
            <Document class="ep-icon" /> 匹配到 {{ askMatchedTodos.length }} 条待办
            <span class="ask-matches__arrow">{{ askMatchesExpanded ? '▼' : '▶' }}</span>
          </button>
          <template v-if="askMatchesExpanded">
            <div v-for="item in askMatchedTodos" :key="item.id" style="padding:8px 12px;background:rgba(0,0,0,0.02);border-radius:6px;margin-bottom:6px;font-size:14px;cursor:pointer" @click="openDetail(item); closeAsk()">
              <span class="ask-todo-card__quadrant" :style="{ color: quadrantConfig[item.quadrant]?.color, background: quadrantConfig[item.quadrant]?.bg }"><component :is="quadrantConfig[item.quadrant]?.icon" class="ep-icon" /></span>
              {{ item.title }}
              <ChildProgressBadge v-if="item.child_total" :total="item.child_total" :done="item.child_done || 0" />
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>

  <!-- 核心对齐检查弹窗 -->
  <div v-if="showCoreReview" class="ai-overlay" @click.self="showCoreReview = false">
    <div class="ai-modal ai-modal--ask">
      <div class="ai-modal__header">
        <h3><Aim class="ep-icon" /> 核心对齐检查</h3>
        <button class="btn btn--sm btn--ghost" @click="showCoreReview = false"><Close class="ep-icon" /></button>
      </div>
      <div class="ai-modal__body">
        <div class="ask-context">
          <p>AI 对照本期实际记录（任务执行/完成/计时/备注），分析核心任务的推进对齐情况。</p>
          <div class="ask-context__actions">
            <button class="btn btn--sm" :class="coreReviewScope === 'week' ? 'btn--primary' : 'btn--ghost'" @click="coreReviewScope = 'week'">本周核心</button>
            <button class="btn btn--sm" :class="coreReviewScope === 'month' ? 'btn--primary' : 'btn--ghost'" @click="coreReviewScope = 'month'">本月核心</button>
            <button class="btn btn--sm btn--primary" :disabled="coreReviewLoading" @click="runCoreReview">
              <Refresh v-if="coreReviewLoading" class="ep-icon" /><MagicStick v-else class="ep-icon" />{{ coreReviewLoading ? ' 分析中...' : ' 开始检查' }}
            </button>
          </div>
        </div>
        <div v-if="coreReviewLoading" class="scan-progress">
          <div class="loading-spinner" style="width:24px;height:24px;margin:0 auto 12px"></div>
          <div class="scan-step scan-step--latest"><span class="scan-step__dot"><Clock class="ep-icon" /></span> 正在汇总本期记录并分析...</div>
        </div>
        <div v-if="coreReviewResult" style="margin-top:12px">
          <div style="font-size:13px;color:#64748B;margin-bottom:4px">
            <Opportunity class="ep-icon" /> {{ coreReviewScope === 'week' ? '本周' : '本月' }}核心（{{ coreReviewResult.period_key }}）：{{ coreReviewResult.core_titles.join('、') }}
          </div>
          <div class="ask-answer" v-html="renderAskAnswer(coreReviewResult.analysis)"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.ask-context {
  margin-bottom: $spacing-md;
  color: $text-secondary;
  font-size: $font-size-xs;
  line-height: 1.6;

  &__actions {
    display: flex;
    flex-wrap: wrap;
    gap: $spacing-sm;
    margin-top: $spacing-sm;
  }

  &__scope { color: $text-muted; margin-bottom: $spacing-sm; }
}

// 提问历史（近7天，本地保存）
.ask-matches__toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 4px 0;
  background: none;
  border: none;
  font-size: 13px;
  color: #64748B;
  cursor: pointer;
  text-align: left;

  &:hover { color: $primary-color; }
}

.ask-matches__arrow {
  margin-left: auto;
  font-size: 11px;
  color: $text-muted;
}

.ask-history {
  margin-top: $spacing-sm;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  max-height: 220px;
  overflow-y: auto;

  &__empty {
    padding: $spacing-md;
    font-size: $font-size-xs;
    color: $text-muted;
  }

  &__item {
    display: flex;
    align-items: flex-start;
    gap: $spacing-sm;
    padding: $spacing-sm $spacing-md;
    border-bottom: 1px solid $border-color;
    &:last-child { border-bottom: none; }
    &:hover { background: rgba($primary-color, 0.04); }
  }

  &__main { flex: 1; min-width: 0; cursor: pointer; }
  &__q {
    font-size: $font-size-xs;
    font-weight: 500;
    color: $text-primary;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  &__meta { font-size: 11px; color: $text-muted; margin-top: 2px; }
  &__del {
    background: none; border: none; color: $text-muted; cursor: pointer;
    padding: 2px 4px; border-radius: 4px; flex-shrink: 0;
    &:hover { color: $danger-color; background: rgba($danger-color, 0.08); }
  }
}

// AI 回答 Markdown 渲染
.ask-answer {
  background: #f8f9fa;
  padding: 12px 16px;
  border-radius: 8px;
  line-height: 1.7;
  font-size: 14px;
  overflow-wrap: anywhere;

  :deep(h1), :deep(h2), :deep(h3), :deep(h4) {
    margin: 12px 0 6px;
    font-weight: 600;
    color: $text-primary;
    &:first-child { margin-top: 0; }
  }
  :deep(h2) { font-size: 16px; }
  :deep(h3) { font-size: 15px; }
  :deep(h4) { font-size: 14px; }
  :deep(p) { margin: 6px 0; }
  :deep(ul), :deep(ol) { margin: 6px 0; padding-left: 20px; }
  :deep(li) { margin: 3px 0; }
  :deep(strong) { color: $text-primary; }
  :deep(code) {
    background: rgba(0, 0, 0, 0.05);
    padding: 1px 5px;
    border-radius: 4px;
    font-size: 13px;
  }
  :deep(blockquote) {
    border-left: 3px solid $primary-color;
    padding: 4px 12px;
    margin: 6px 0;
    background: rgba($primary-color, 0.03);
    border-radius: 0 6px 6px 0;
    color: $text-secondary;
  }
  :deep(hr) { border: none; border-top: 1px solid $border-color; margin: 10px 0; }
  :deep(a) { color: $primary-color; }
  :deep(table) { border-collapse: collapse; margin: 8px 0; }
  :deep(th), :deep(td) { border: 1px solid $border-color; padding: 4px 10px; font-size: 13px; }
}

.todo-calendar {
  min-width: 0;
  overflow-x: hidden;
  &__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: $spacing-lg;

    h1 {
      font-size: $font-size-xl;
    }

    @media (max-width: $breakpoint-sm) {
      flex-direction: column;
      gap: $spacing-sm;
      margin-bottom: $spacing-md;

      h1 { font-size: $font-size-lg; }
    }
  }

  &__header-left {
    min-width: 0;
  }

  &__subtitle {
    color: $text-secondary;
    font-size: $font-size-sm;
    margin-top: $spacing-xs;

    @media (max-width: $breakpoint-sm) {
      display: none;
    }
  }

  &__header-actions {
    display: flex;
    gap: $spacing-sm;
    align-items: center;
    flex-shrink: 0;
    flex-wrap: wrap;

    @media (max-width: $breakpoint-sm) {
      width: 100%;
      gap: $spacing-xs;
    }
  }

  &__layout {
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: $spacing-lg;
    align-items: stretch;
    min-width: 0;

    @media (max-width: $breakpoint-md) {
      grid-template-columns: 1fr;
      gap: $spacing-md;
    }
  }
}

// 侧边栏折叠按钮（仅手机端显示）
.sidebar-toggle {
  display: none;

  @media (max-width: $breakpoint-md) {
    display: block;
    width: 100%;
    padding: $spacing-sm $spacing-md;
    background: rgba(139, 92, 246, 0.06);
    border: 1px solid rgba(139, 92, 246, 0.15);
    border-radius: $border-radius-sm;
    color: #8B5CF6;
    font-size: $font-size-xs;
    font-weight: 500;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;

    &:hover, &:active {
      background: rgba(139, 92, 246, 0.12);
    }
  }
}

// AI 按钮组 & 天数选择器
.ai-btn-group {
  position: relative;
}

.days-selector {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: $spacing-xs;
  background: white;
  border-radius: $border-radius-md;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
  padding: $spacing-md;
  min-width: 220px;
  z-index: 100;

  @media (max-width: $breakpoint-sm) {
    position: fixed;
    top: auto;
    bottom: 0;
    left: 0;
    right: 0;
    margin-top: 0;
    border-radius: $border-radius-lg $border-radius-lg 0 0;
    padding: $spacing-lg $spacing-md;
    min-width: auto;
    z-index: 101;
    box-shadow: 0 -4px 30px rgba(0, 0, 0, 0.2);
  }

  &__title {
    font-size: $font-size-xs;
    font-weight: 600;
    color: $text-secondary;
    margin-bottom: $spacing-sm;

    @media (max-width: $breakpoint-sm) {
      font-size: $font-size-sm;
      text-align: center;
      margin-bottom: $spacing-md;
    }
  }

  &__options {
    display: flex;
    gap: $spacing-xs;
    margin-bottom: $spacing-sm;

    @media (max-width: $breakpoint-sm) {
      gap: $spacing-sm;
      margin-bottom: $spacing-md;
    }
  }

  &__custom {
    display: flex;
    gap: $spacing-xs;
    align-items: center;
    padding-top: $spacing-sm;
    border-top: 1px solid rgba(0, 0, 0, 0.06);

    @media (max-width: $breakpoint-sm) {
      gap: $spacing-sm;
      padding-top: $spacing-md;
      padding-bottom: env(safe-area-inset-bottom, 8px);
    }
  }
}

.days-option {
  flex: 1;
  padding: $spacing-xs $spacing-sm;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  background: white;
  font-size: $font-size-xs;
  font-weight: 500;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-sm $spacing-md;
    font-size: $font-size-sm;
  }

  &:hover { border-color: #8B5CF6; color: #8B5CF6; }
  &--active { border-color: #8B5CF6; background: rgba(139, 92, 246, 0.1); color: #8B5CF6; }
}

.days-input {
  width: 70px;
  padding: 4px 8px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  font-size: $font-size-xs;
  text-align: center;

  @media (max-width: $breakpoint-sm) {
    flex: 1;
    width: auto;
    padding: $spacing-sm $spacing-md;
    font-size: $font-size-sm;
  }

  &:focus { outline: none; border-color: #8B5CF6; }
}

.days-selector-backdrop {
  position: fixed;
  inset: 0;
  z-index: 99;

  @media (max-width: $breakpoint-sm) {
    background: rgba(0, 0, 0, 0.3);
    z-index: 100;
  }
}

.dropdown-enter-active, .dropdown-leave-active {
  transition: all 0.2s ease;
}
.dropdown-enter-from, .dropdown-leave-to {
  opacity: 0;
  transform: translateY(-8px);

  @media (max-width: $breakpoint-sm) {
    transform: translateY(100%);
  }
}

// 按钮
.btn {
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
  white-space: nowrap;

  &--primary {
    background: linear-gradient(135deg, #EC4899, #8B5CF6);
    color: white;
    &:hover { opacity: 0.9; }
  }

  &--ai {
    background: linear-gradient(135deg, #6366F1, #8B5CF6);
    color: white;
    white-space: nowrap;
    &:hover { opacity: 0.9; transform: translateY(-1px); }

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-xs $spacing-sm;
      font-size: $font-size-xs;
    }
  }

  &--ghost {
    background: transparent;
    color: $text-secondary;
    &:hover { color: #EC4899; }
  }

  &--back {
    @media (max-width: $breakpoint-sm) {
      padding: $spacing-xs $spacing-sm;
      font-size: $font-size-xs;
    }
  }

  &--sm { padding: 4px 12px; font-size: $font-size-xs; }
  &--xs { padding: 2px 8px; font-size: 10px; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

// 取消安排按钮
.btn-unschedule {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 1px 6px;
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 4px;
  background: rgba(239, 68, 68, 0.05);
  color: #EF4444;
  font-size: 10px;
  cursor: pointer;

  &__text {
    @media (max-width: $breakpoint-sm) { display: none; }
  }
  transition: all 0.15s;
  white-space: nowrap;

  &:hover {
    background: rgba(239, 68, 68, 0.12);
    border-color: rgba(239, 68, 68, 0.4);
  }

  span { font-weight: 600; }
}

// 计时按钮
.timer-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.04);
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 10px;
  color: $text-secondary;
  transition: all 0.15s;
  white-space: nowrap;

  &:hover { background: rgba(0, 0, 0, 0.08); }

  &__icon { font-size: 10px; line-height: 1; }
  &__time {
    font-family: 'Courier New', monospace;
    font-weight: 600;
    font-size: 10px;
    min-width: 32px;
  }

  &--active {
    background: rgba(236, 72, 153, 0.1);
    border-color: rgba(236, 72, 153, 0.3);
    color: #EC4899;
    animation: timer-glow 1.5s ease-in-out infinite;

    &:hover { background: rgba(236, 72, 153, 0.18); }
  }
}

@keyframes timer-glow {
  0%, 100% { box-shadow: 0 0 0 0 rgba(236, 72, 153, 0); }
  50% { box-shadow: 0 0 4px 2px rgba(236, 72, 153, 0.2); }
}

// 日历面板
.calendar-panel {
  @include glass-card;
  padding: $spacing-md;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-sm;
    border-radius: $border-radius-md;
  }
}

.calendar-nav {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  margin-bottom: $spacing-md;

  @media (max-width: $breakpoint-sm) {
    margin-bottom: $spacing-sm;
    gap: $spacing-xs;
  }

  &__title {
    font-size: $font-size-lg;
    font-weight: 600;
    flex: 1;
    text-align: center;
    margin: 0;

    @media (max-width: $breakpoint-sm) {
      font-size: $font-size-md;
    }
  }

  &__today {
    margin-left: $spacing-sm;
    font-weight: 500 !important;
    color: #EC4899 !important;

    @media (max-width: $breakpoint-sm) {
      margin-left: $spacing-xs;
    }
  }
}

.calendar-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  margin-bottom: 2px;
}

.calendar-weekday {
  text-align: center;
  font-size: $font-size-xs;
  font-weight: 600;
  color: $text-secondary;
  padding: $spacing-xs 0;

  @media (max-width: $breakpoint-sm) {
    font-size: 10px;
    padding: 2px 0;
  }

  &--weekend { color: #F59E0B; }
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;

  @media (max-width: $breakpoint-sm) {
    gap: 1px;
  }
}

.calendar-cell {
  min-height: 90px;
  padding: 4px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.6);
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
  overflow: hidden;

  @media (max-width: $breakpoint-sm) {
    min-height: 48px;
    padding: 2px;
    border-radius: 4px;
    border-width: 1.5px;
  }

  &:hover { background: rgba(255, 255, 255, 0.9); }

  &--other {
    opacity: 0.35;
    background: rgba(0, 0, 0, 0.02);
  }

  &--today {
    border-color: #EC4899;
    background: rgba(236, 72, 153, 0.04);
  }

  &--selected {
    border-color: #8B5CF6;
    background: rgba(139, 92, 246, 0.06);
    box-shadow: 0 0 0 1px rgba(139, 92, 246, 0.2);

    @media (max-width: $breakpoint-sm) {
      box-shadow: none;
      background: rgba(139, 92, 246, 0.1);
    }
  }

  &--weekend { background: rgba(245, 158, 11, 0.03); }

  &--light { background: rgba(16, 185, 129, 0.04); }
  &--moderate { background: rgba(59, 130, 246, 0.06); }
  &--heavy { background: rgba(239, 68, 68, 0.06); border-color: rgba(239, 68, 68, 0.3); }

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2px;

    @media (max-width: $breakpoint-sm) {
      margin-bottom: 1px;
      justify-content: center;
    }
  }

  &__day {
    font-size: $font-size-xs;
    font-weight: 600;
    color: $text-primary;

    @media (max-width: $breakpoint-sm) {
      font-size: 11px;
    }
  }

  &__time {
    font-size: 9px;
    color: $text-muted;
    background: rgba(0, 0, 0, 0.04);
    padding: 0 4px;
    border-radius: 4px;

    @media (max-width: $breakpoint-sm) {
      display: none;
    }
  }

  // 桌面端任务卡片
  &__tasks--desktop {
    display: flex;
    flex-direction: column;
    gap: 1px;

    @media (max-width: $breakpoint-sm) {
      display: none;
    }
  }

  // 手机端任务圆点
  &__tasks--mobile {
    display: none;

    @media (max-width: $breakpoint-sm) {
      display: flex;
      justify-content: center;
    }
  }

  &__dots {
    display: flex;
    gap: 2px;
    justify-content: center;
    flex-wrap: wrap;
    padding-top: 1px;
  }

  &__dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  &__dot-more {
    font-size: 8px;
    color: $text-muted;
    line-height: 1;
  }

  &__more {
    font-size: 9px;
    color: $text-muted;
    text-align: center;
    padding: 1px;
  }
}

.calendar-task {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 1px 4px;
  border-radius: 3px;
  border-left: 2px solid;
  cursor: grab;
  transition: all 0.15s;

  &:hover { transform: scale(1.02); box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1); }
  &:active { cursor: grabbing; }

  &--multi-day {
    border-left-width: 3px;
    border-left-style: dashed;
    opacity: 0.85;
  }

  &__multi-icon {
    font-size: 8px;
    flex-shrink: 0;
  }

  &__title {
    font-size: 10px;
    line-height: 1.3;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.running-lane {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: $spacing-md;
  padding: 8px 12px;
  border-radius: $border-radius-md;
  background: rgba($primary-color, 0.08);

  &__label { font-size: $font-size-sm; color: $text-secondary; }
  &__item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 36px;
    padding: 0 10px;
    border: none;
    border-radius: 999px;
    background: #fff;
    color: $text-primary;
    cursor: pointer;
    font-size: $font-size-sm;
  }
  &__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: $danger-color;
    box-shadow: 0 0 0 4px rgba($danger-color, 0.15);
  }
}

// 侧边栏
.sidebar-panel {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
  min-width: 0;
  overflow-x: hidden;

  @media (min-width: 769px) {
    height: 100%;
    min-height: 0;
    overflow: hidden;
  }

  @media (max-width: $breakpoint-md) {
    display: none;
    height: auto;
    overflow: visible;

    &--expanded {
      display: flex;
    }
  }
}

.sidebar-section {
  @include glass-card;
  padding: $spacing-md;
  min-width: 0;
  overflow: hidden;

  @media (min-width: 769px) {
    &:first-child {
      flex: 0 1 auto;
      max-height: 42%;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }

    &:last-child {
      flex: 1 1 auto;
      min-height: 0;
      display: flex;
      flex-direction: column;
    }
  }

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-sm;
    border-radius: $border-radius-md;
  }

  &__title {
    font-size: $font-size-sm;
    font-weight: 600;
    margin: 0 0 $spacing-sm;
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    flex-wrap: wrap;
    flex-shrink: 0;
  }

  &__count {
    font-size: $font-size-xs;
    background: rgba(139, 92, 246, 0.1);
    color: #8B5CF6;
    padding: 0 8px;
    border-radius: 10px;
  }

  &__time {
    font-size: $font-size-xs;
    color: $text-muted;
    margin-left: auto;
  }
}

.sidebar-empty {
  text-align: center;
  padding: $spacing-md;
  color: $text-muted;
  font-size: $font-size-sm;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-sm;
    font-size: $font-size-xs;
  }

  &__hint { font-size: $font-size-xs; margin-top: $spacing-xs; }
}

.sidebar-loading {
  text-align: center;
  padding: $spacing-md;
}

.loading-spinner {
  width: 24px; height: 24px;
  border: 2px solid $border-color;
  border-top-color: #EC4899;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto;
}

@keyframes spin { to { transform: rotate(360deg); } }

.sidebar-tasks {
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
  overflow-x: hidden;

  @media (min-width: 769px) {
    min-height: 0;
    overflow-y: auto;
  }
}

.sidebar-task {
  padding: $spacing-sm;
  border-radius: $border-radius-sm;
  background: rgba(255, 255, 255, 0.6);
  transition: all 0.15s;

  &:hover { background: rgba(255, 255, 255, 0.9); }

  &--done {
    opacity: 0.5;
    .sidebar-task__title { text-decoration: line-through; }
  }

  &--dragging {
    opacity: 0.4;
    border: 2px dashed #8B5CF6;
    background: rgba(139, 92, 246, 0.1);
  }

  &--drag-over {
    border-top: 3px solid #8B5CF6;
    margin-top: -3px;
  }

  &__header {
    display: flex;
    align-items: flex-start;
    gap: $spacing-xs;
    margin-bottom: 2px;
    cursor: pointer;

    &:hover .sidebar-task__title { color: #8B5CF6; }
  }

  &__quadrant { flex-shrink: 0; }

  &__title {
    font-size: $font-size-sm;
    font-weight: 500;
    line-height: 1.4;
    word-break: break-word;
    transition: color 0.15s;
  }

  &__meta {
    display: flex;
    gap: $spacing-xs;
    flex-wrap: wrap;
    align-items: center;
    margin-left: 20px;

    @media (max-width: $breakpoint-sm) {
      margin-left: 0;
      margin-top: $spacing-xs;
    }
  }

  &__cat {
    font-size: 10px;
    padding: 0 4px;
    border-radius: 4px;
    background: rgba(139, 92, 246, 0.1);
    color: #8B5CF6;
  }

  &__status {
    font-size: 10px;
    padding: 0 4px;
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.04);
  }

  &__est {
    font-size: 10px;
    color: #3B82F6;
    cursor: pointer;
    padding: 0 4px;
    border-radius: 4px;
    background: rgba(59, 130, 246, 0.08);

    &:hover { background: rgba(59, 130, 246, 0.15); }
    &--empty { color: $text-muted; background: rgba(0, 0, 0, 0.04); border: 1px dashed $border-color; }
  }

  &__actual {
    font-size: 10px;
    color: #10B981;
    padding: 0 4px;
    border-radius: 4px;
    background: rgba(16, 185, 129, 0.08);
  }

  &__edit-est {
    margin-top: $spacing-xs;
    margin-left: 20px;
    padding: $spacing-xs;
    background: rgba(59, 130, 246, 0.04);
    border-radius: $border-radius-sm;

    @media (max-width: $breakpoint-sm) {
      margin-left: 0;
    }
  }
}

.quick-times {
  display: flex;
  gap: 2px;
  flex-wrap: wrap;
  margin-bottom: $spacing-xs;
}

.edit-est-row {
  display: flex;
  gap: $spacing-xs;
  align-items: center;
}

.edit-est-input {
  width: 60px;
  padding: 2px 6px;
  border: 1px solid $border-color;
  border-radius: 4px;
  font-size: $font-size-xs;
  text-align: center;

  &:focus { outline: none; border-color: #3B82F6; }
}

// 未排期搜索筛选
.unscheduled-filters {
  margin-bottom: $spacing-sm;
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
  flex-shrink: 0;

  &__search {
    width: 100%;
    padding: $spacing-xs $spacing-sm;
    border: 1px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-xs;
    background: rgba(255, 255, 255, 0.8);
    &:focus { outline: none; border-color: #EC4899; }
  }

  &__row {
    display: flex;
    gap: $spacing-xs;
    align-items: center;
  }

  &__select {
    flex: 1;
    padding: $spacing-xs $spacing-sm;
    border: 1px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-xs;
    background: white;
    &:focus { outline: none; border-color: #EC4899; }
  }

  &__quadrants {
    display: flex;
    gap: 2px;
  }
}

.quadrant-filter-btn {
  width: 26px;
  height: 26px;
  border-radius: $border-radius-sm;
  border: 2px solid transparent;
  background: rgba(0, 0, 0, 0.04);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover { background: rgba(0, 0, 0, 0.08); }
  &--active { background: rgba(236, 72, 153, 0.1); }
}

// 未排期列表
.unscheduled-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
  max-height: 400px;
  overflow-y: auto;
  overflow-x: hidden;

  @media (min-width: 769px) {
    flex: 1;
    min-height: 0;
    max-height: 420px;
  }

  @media (max-width: $breakpoint-sm) {
    max-height: 300px;
  }
}

.unscheduled-item {
  display: flex;
  align-items: flex-start;
  gap: $spacing-xs;
  padding: $spacing-sm;
  border-radius: $border-radius-sm;
  background: rgba(255, 255, 255, 0.6);
  cursor: grab;
  transition: all 0.15s;
  border: 1px solid transparent;
  min-width: 0;

  @media (max-width: $breakpoint-sm) {
    cursor: default; // 手机端不支持拖拽
  }

  &:hover {
    background: rgba(255, 255, 255, 0.9);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  }
  &:active { cursor: grabbing; }
  &--dragging { opacity: 0.4; border: 1px dashed #8B5CF6; }

  &__icon { flex-shrink: 0; margin-top: 2px; }

  &__content {
    flex: 1;
    min-width: 0;
    cursor: pointer;

    &:hover .unscheduled-item__title { color: #8B5CF6; }
  }

  &__title {
    font-size: $font-size-sm;
    font-weight: 500;
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    transition: color 0.15s;
  }

  &__meta {
    display: flex;
    gap: $spacing-xs;
    margin-top: 2px;
    flex-wrap: wrap;
  }

  &__cat {
    font-size: 10px;
    padding: 0 4px;
    border-radius: 4px;
    background: rgba(139, 92, 246, 0.1);
    color: #8B5CF6;
  }

  &__status {
    font-size: 10px;
    padding: 0 4px;
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.04);
  }

  &__due {
    font-size: 10px;
    color: #EF4444;
  }

  &__est {
    font-size: 10px;
    color: #3B82F6;
  }

  &__quick {
    display: flex;
    gap: 2px;
    flex-shrink: 0;
    flex-wrap: wrap;
    align-items: center;
  }

  // 桌面端显示「今」「明」，手机端隐藏
  &__quick-desktop {
    @media (max-width: $breakpoint-sm) {
      display: none;
    }
  }

  // 手机端显示「→日期」「今」，桌面端隐藏
  &__quick-mobile {
    display: none;

    @media (max-width: $breakpoint-sm) {
      display: inline-flex;
    }
  }
}

// Modal 公共样式
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: $spacing-md;

  @media (max-width: $breakpoint-sm) {
    padding: 0;
    align-items: flex-end;
  }
}

.modal {
  @include glass-card;
  padding: $spacing-xl;
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
  animation: modal-pop 0.3s ease;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    max-width: 100%;
    max-height: 92vh;
    border-radius: $border-radius-lg $border-radius-lg 0 0;
    animation: modal-slide-up 0.3s ease;
    padding-bottom: calc($spacing-md + env(safe-area-inset-bottom, 8px));
  }

  h3 { font-size: $font-size-lg; margin-bottom: 0; }

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $spacing-lg;

    @media (max-width: $breakpoint-sm) {
      margin-bottom: $spacing-md;
    }
  }

  &__header-actions {
    display: flex;
    gap: $spacing-xs;
  }

  &__actions {
    display: flex;
    gap: $spacing-md;
    justify-content: flex-end;
    margin-top: $spacing-lg;

    @media (max-width: $breakpoint-sm) {
      margin-top: $spacing-md;
    }
  }
}

// 详情样式 (与 TodoList.vue 保持一致)
.detail-section {
  margin-bottom: $spacing-md;
  padding-bottom: $spacing-md;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);

  @media (max-width: $breakpoint-sm) {
    margin-bottom: $spacing-sm;
    padding-bottom: $spacing-sm;
  }

  &:last-child { border-bottom: none; }

  &--highlight {
    background: rgba(236, 72, 153, 0.04);
    padding: $spacing-md;
    border-radius: $border-radius-sm;
    border-bottom: none;
    margin-bottom: $spacing-sm;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-sm;
    }
  }

  &--ai {
    background: rgba(139, 92, 246, 0.04);
    padding: $spacing-md;
    border-radius: $border-radius-sm;
    border-bottom: none;
    margin-bottom: $spacing-sm;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-sm;
    }
  }

  &--answer {
    background: rgba(59, 130, 246, 0.04);
    padding: $spacing-md;
    border-radius: $border-radius-sm;
    border-bottom: none;
    margin-bottom: $spacing-sm;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-sm;
    }
  }

  &--inspiration {
    background: linear-gradient(135deg, rgba(244, 114, 182, 0.06), rgba(139, 92, 246, 0.04));
    padding: $spacing-md;
    border-radius: $border-radius-sm;
    border: 1px dashed rgba(244, 114, 182, 0.3);
    border-bottom: none;
    margin-bottom: $spacing-sm;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-sm;
    }
  }

  &--meta { border-bottom: none; }
}

.detail-title {
  font-size: $font-size-lg;
  font-weight: 600;
  margin-bottom: $spacing-sm;

  @media (max-width: $breakpoint-sm) {
    font-size: $font-size-md;
  }
}

.detail-tags {
  display: flex;
  gap: $spacing-xs;
  flex-wrap: wrap;
}

.detail-tag {
  font-size: $font-size-xs;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.04);
  white-space: nowrap;

  @media (max-width: $breakpoint-sm) {
    font-size: 10px;
    padding: 1px 6px;
  }

  &--category {
    background: rgba(139, 92, 246, 0.1);
    color: #8B5CF6;
  }
}

.detail-label {
  font-size: $font-size-sm;
  font-weight: 700;
  color: #1F2937;
  margin-bottom: $spacing-xs;

  &--toggle {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: none;
    background: transparent;
    cursor: pointer;
    padding: 4px 0;
    span { color: $text-muted; font-size: 11px; }
    &:hover { color: $primary-color; }
  }
}

.detail-value {
  font-size: $font-size-sm;
  line-height: 1.6;
  color: $text-primary;
  white-space: pre-wrap;

  @media (max-width: $breakpoint-sm) {
    font-size: $font-size-xs;
    line-height: 1.5;
  }

  &--answer { color: #1e40af; }
  &--inspiration { color: #be185d; }
}

.detail-meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-sm $spacing-lg;

  @media (max-width: $breakpoint-sm) {
    gap: $spacing-xs $spacing-md;
  }
}

.detail-meta-label {
  font-size: $font-size-xs;
  color: #1F2937;
  font-weight: 700;

  @media (max-width: $breakpoint-sm) {
    font-size: 10px;
  }
}

.detail-meta-value {
  font-size: $font-size-xs;
  font-weight: 500;
  margin-left: $spacing-xs;

  @media (max-width: $breakpoint-sm) {
    font-size: 10px;
  }
}

.detail-notes-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
}

.detail-note-item {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: $spacing-sm;
  padding: $spacing-xs $spacing-sm;
  border-radius: $border-radius-sm;
  background: rgba(16, 185, 129, 0.06);
  border-left: 2px solid rgba(16, 185, 129, 0.3);
}

.detail-note-del {
  background: none;
  border: none;
  color: $text-muted;
  cursor: pointer;
  padding: 0 2px;
  flex-shrink: 0;
  font-size: 12px;
  &:hover { color: $danger-color; }
}

.detail-comment-input {
  display: flex;
  gap: $spacing-sm;
  align-items: flex-end;
  margin-top: $spacing-xs;
}

.detail-comment-textarea {
  flex: 1;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  padding: $spacing-xs $spacing-sm;
  font-family: inherit;
  font-size: $font-size-sm;
  resize: vertical;
  &:focus {
    outline: none;
    border-color: $primary-color;
  }
}

.detail-note-content {
  font-size: $font-size-sm;
  color: $text-primary;
  font-weight: 600;
  flex: 1;
  word-break: break-word;
  white-space: pre-wrap;  // 保留换行符
}

.detail-note-edit {
  background: none; border: none; color: $text-muted;
  cursor: pointer; padding: 0 4px; font-size: 12px; flex-shrink: 0;
  &:hover { color: $primary-color; }
}
.detail-comment-edit {
  flex: 1; min-width: 0; padding: 4px 8px;
  border: 1px solid $primary-color; border-radius: 6px;
  font-size: 12px; font-family: inherit;
}

.detail-note-time {
  font-size: 10px;
  color: $text-muted;
  white-space: nowrap;
  flex-shrink: 0;
}

.detail-children {
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
}

.detail-child-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-xs $spacing-sm;
  border-radius: $border-radius-sm;
  background: rgba(255, 255, 255, 0.6);

  &--done {
    opacity: 0.5;
    .detail-child-item__title { text-decoration: line-through; }
  }

  &__title { flex: 1; font-size: $font-size-sm; cursor: pointer; }
  &__flag { display: inline-flex; flex-shrink: 0; }
  &__urg {
    font-size: 11px;
    border: 1px solid $border-color;
    border-radius: 6px;
    background: #fff;
    color: $text-secondary;
    padding: 1px 4px;
  }
  &__status { font-size: 10px; white-space: nowrap; }
}

.detail-actions {
  display: flex;
  gap: $spacing-sm;
  justify-content: flex-end;
  margin-top: $spacing-md;
  padding-top: $spacing-md;
  border-top: 1px solid rgba(0, 0, 0, 0.06);

  @media (max-width: $breakpoint-sm) {
    margin-top: $spacing-sm;
    padding-top: $spacing-sm;
  }

  &__delete { color: #EF4444 !important; &:hover { background: rgba(239, 68, 68, 0.08); } }
}

// Checkbox
.checkbox {
  position: relative;
  display: flex;
  align-items: center;
  cursor: pointer;
  flex-shrink: 0;
  margin-top: 2px;

  input { position: absolute; opacity: 0; width: 0; height: 0; }

  &__mark {
    width: 20px;
    height: 20px;
    border: 2px solid $border-color;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;

    &::after {
      content: '';
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: transparent;
      transition: all 0.15s;
    }
  }

  input:checked + .checkbox__mark {
    border-color: #10B981;
    background: #10B981;
    &::after { background: white; }
  }
}

// 表单
.form-group {
  margin-bottom: $spacing-md;
  label { display: block; font-size: $font-size-xs; font-weight: 600; color: $text-secondary; margin-bottom: $spacing-xs; }

  @media (max-width: $breakpoint-sm) {
    margin-bottom: $spacing-sm;
  }
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-md;

  @media (max-width: $breakpoint-sm) {
    grid-template-columns: 1fr;
    gap: $spacing-sm;
  }
}

.form-input, .form-textarea {
  width: 100%;
  padding: $spacing-sm $spacing-md;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  font-family: inherit;
  background: rgba(255, 255, 255, 0.8);
  &:focus { outline: none; border-color: #EC4899; }
}

.form-textarea { resize: vertical; }

// 子任务编辑
.edit-children {
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
  margin-top: $spacing-xs;
}

.edit-child-item {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  padding: $spacing-xs;
  border-radius: $border-radius-sm;
  background: rgba(139, 92, 246, 0.04);
  border: 1px solid rgba(139, 92, 246, 0.1);
}

.form-input--sm {
  flex: 1;
  min-width: 0;
  padding: $spacing-xs $spacing-sm;
  font-size: $font-size-xs;
}

.form-input--xs {
  width: 90px;
  padding: $spacing-xs $spacing-sm;
  font-size: $font-size-xs;
  flex-shrink: 0;
}

.btn-child-delete {
  width: 28px;
  height: 28px;
  border-radius: $border-radius-sm;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s;

  &:hover { background: rgba(239, 68, 68, 0.1); }
}

// AI 排期弹窗
.ai-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: $spacing-md;

  @media (max-width: $breakpoint-sm) {
    padding: 0;
    align-items: flex-end;
  }
}

.ai-modal {
  @include glass-card;
  width: 100%;
  max-width: 640px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  animation: modal-pop 0.3s ease;

  @media (max-width: $breakpoint-sm) {
    max-width: 100%;
    max-height: 90vh;
    border-radius: $border-radius-lg $border-radius-lg 0 0;
    animation: modal-slide-up 0.3s ease;
  }

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: $spacing-md $spacing-lg;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
    flex-shrink: 0;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-sm $spacing-md;
    }

    h3 {
      font-size: $font-size-md;
      font-weight: 600;
      margin: 0;

      @media (max-width: $breakpoint-sm) {
        font-size: $font-size-sm;
      }
    }
  }

  &__body {
    flex: 1;
    overflow-y: auto;
    padding: $spacing-lg;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-md;
    }
  }

  &__footer {
    display: flex;
    gap: $spacing-md;
    justify-content: flex-end;
    padding: $spacing-md $spacing-lg;
    border-top: 1px solid rgba(0, 0, 0, 0.06);
    flex-shrink: 0;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-sm $spacing-md;
      padding-bottom: calc($spacing-sm + env(safe-area-inset-bottom, 8px));
      gap: $spacing-sm;
    }
  }
}

.ai-summary {
  padding: $spacing-md;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.06), rgba(139, 92, 246, 0.06));
  border-radius: $border-radius-sm;
  margin-bottom: $spacing-md;
  border-left: 3px solid #6366F1;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-sm;
  }

  p { font-size: $font-size-sm; line-height: 1.7; color: $text-primary; margin: 0; }
}

.ai-tips {
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
  margin-bottom: $spacing-md;
}

.ai-tip {
  font-size: $font-size-xs;
  color: #6366F1;
  padding: $spacing-xs $spacing-sm;
  background: rgba(99, 102, 241, 0.05);
  border-radius: $border-radius-sm;
}

.ai-schedule-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;
}

.ai-schedule-item {
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-sm;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(0, 0, 0, 0.06);

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-sm;
  }

  &__date {
    font-size: $font-size-xs;
    font-weight: 600;
    color: #6366F1;
    margin-bottom: 2px;
  }

  &__content {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    margin-bottom: 2px;
  }

  &__title {
    font-size: $font-size-sm;
    font-weight: 500;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    @media (max-width: $breakpoint-sm) {
      font-size: $font-size-xs;
    }
  }

  &__est {
    font-size: 10px;
    color: #3B82F6;
    white-space: nowrap;
    padding: 0 4px;
    background: rgba(59, 130, 246, 0.08);
    border-radius: 4px;
  }

  &__reason {
    font-size: $font-size-xs;
    color: $text-muted;
    line-height: 1.4;

    @media (max-width: $breakpoint-sm) {
      font-size: 10px;
    }
  }
}

@keyframes modal-pop {
  0% { transform: scale(0.95); opacity: 0; }
  100% { transform: scale(1); opacity: 1; }
}

@keyframes modal-slide-up {
  0% { transform: translateY(100%); opacity: 0; }
  100% { transform: translateY(0); opacity: 1; }
}

// 完成记录耗时弹窗
.modal--complete {
  max-width: 420px;
}

.complete-modal {
  &__body {
    padding: $spacing-lg;
    @media (max-width: $breakpoint-sm) { padding: $spacing-md; }
  }

  &__title {
    font-size: $font-size-md;
    font-weight: 600;
    margin-bottom: $spacing-md;
    line-height: 1.6;
  }

  &__field {
    margin-bottom: $spacing-md;

    label {
      display: block;
      font-size: $font-size-sm;
      font-weight: 500;
      margin-bottom: $spacing-sm;
      color: $text-secondary;
    }
  }

  &__input-row {
    display: flex;
    gap: $spacing-xs;
    flex-wrap: wrap;
    margin-bottom: $spacing-sm;
  }

  &__input {
    width: 100%;
    padding: $spacing-sm $spacing-md;
    border: 2px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-sm;
    text-align: center;
    font-weight: 600;
    &:focus { outline: none; border-color: #EC4899; box-shadow: 0 0 0 3px rgba(236, 72, 153, 0.1); }
  }

  &__textarea {
    width: 100%;
    padding: $spacing-sm $spacing-md;
    border: 2px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-sm;
    font-family: inherit;
    resize: vertical;
    min-height: 50px;
    background: rgba(255, 255, 255, 0.6);
    &:focus { outline: none; border-color: #EC4899; box-shadow: 0 0 0 3px rgba(236, 72, 153, 0.1); }
    &::placeholder { color: $text-muted; }
  }

  &__hint {
    font-size: $font-size-xs;
    color: $text-muted;
    margin-top: $spacing-sm;
  }

  &__timelog-hint {
    font-size: $font-size-xs;
    color: #8B5CF6;
    background: rgba(139, 92, 246, 0.08);
    padding: 4px 8px;
    border-radius: 4px;
    margin-bottom: $spacing-sm;

    strong {
      font-weight: 700;
      color: #7C3AED;
    }
  }

  &__notes-list {
    display: flex;
    flex-direction: column;
    gap: $spacing-xs;
    max-height: 120px;
    overflow-y: auto;
  }

  &__note-item {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: $spacing-sm;
    padding: $spacing-xs $spacing-sm;
    border-radius: $border-radius-sm;
    background: rgba(139, 92, 246, 0.06);
    border: 1px solid rgba(139, 92, 246, 0.12);
  }

  &__note-content {
    flex: 1;
    font-size: $font-size-xs;
    line-height: 1.5;
    color: $text-primary;
    word-break: break-word;
  }

  &__note-time {
    font-size: 10px;
    color: $text-muted;
    white-space: nowrap;
    flex-shrink: 0;
  }
}

// 浮动新增按钮
.fab {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #EC4899, #8B5CF6);
  color: white;
  font-size: 28px;
  font-weight: 300;
  border: none;
  cursor: pointer;
  box-shadow: 0 4px 20px rgba(236, 72, 153, 0.4);
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;

  &:hover { transform: scale(1.1); box-shadow: 0 6px 24px rgba(236, 72, 153, 0.5); }

  @media (max-width: $breakpoint-md) {
    bottom: calc(72px + env(safe-area-inset-bottom, 0px));
    right: 16px;
    width: 48px;
    height: 48px;
    font-size: 24px;
  }
}

// 新建待办弹窗
.modal--create {
  max-width: 480px;
}

.create-form {
  &__body {
    padding: $spacing-lg;
    @media (max-width: $breakpoint-sm) { padding: $spacing-md; }
  }

  &__group {
    margin-bottom: $spacing-md;

    label {
      display: block;
      font-size: $font-size-xs;
      font-weight: 600;
      color: $text-secondary;
      margin-bottom: $spacing-xs;
    }
  }

  &__required {
    color: #EF4444;
  }

  &__hint {
    font-weight: 400;
    color: $text-muted;
    font-size: 10px;
  }

  &__input {
    width: 100%;
    padding: $spacing-sm $spacing-md;
    border: 2px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-sm;
    font-family: inherit;
    background: rgba(255, 255, 255, 0.6);
    transition: border-color 0.2s;

    &:focus {
      outline: none;
      border-color: #EC4899;
      box-shadow: 0 0 0 3px rgba(236, 72, 153, 0.1);
    }

    &::placeholder { color: $text-muted; }
  }

  &__textarea {
    width: 100%;
    padding: $spacing-sm $spacing-md;
    border: 2px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-sm;
    font-family: inherit;
    resize: vertical;
    min-height: 50px;
    background: rgba(255, 255, 255, 0.6);

    &:focus {
      outline: none;
      border-color: #EC4899;
      box-shadow: 0 0 0 3px rgba(236, 72, 153, 0.1);
    }

    &::placeholder { color: $text-muted; }
  }

  &__row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: $spacing-md;

    @media (max-width: $breakpoint-sm) {
      grid-template-columns: 1fr;
      gap: $spacing-sm;
    }
  }

  &__sub-list { display: flex; flex-direction: column; gap: 4px; padding-left: 8px; border-left: 2px solid rgba(#EC4899, 0.15); margin-bottom: 6px; }
  &__sub-row { display: flex; align-items: center; gap: 6px; }
  &__sub-bullet { color: $text-muted; font-size: 12px; flex-shrink: 0; }
  &__sub-input { flex: 1; border: 1px solid $border-color; border-radius: 8px; padding: 6px 10px; font-size: 13px; font-family: inherit; box-sizing: border-box; &:focus { outline: none; border-color: #EC4899; } }
  &__sub-del { background: none; border: none; color: $text-muted; cursor: pointer; font-size: 12px; padding: 2px 4px; border-radius: 4px; flex-shrink: 0; &:hover { color: $danger-color; background: rgba($danger-color, 0.08); } }
  &__add-sub { align-self: flex-start; background: none; border: none; color: $text-secondary; font-size: 13px; cursor: pointer; padding: 4px 8px; border-radius: 6px; &:hover { color: #EC4899; background: rgba(#EC4899, 0.06); } }
}

// header 新增按钮样式
.btn--scan {
  background: linear-gradient(135deg, #8B5CF6, #EC4899); color: white; white-space: nowrap;
  &:hover { opacity: 0.9; } &:disabled { opacity: 0.6; cursor: not-allowed; }
}
.btn--ask {
  background: linear-gradient(135deg, #3B82F6, #06B6D4); color: white; white-space: nowrap;
  &:hover { opacity: 0.9; }
}
.btn--inbox {
  background: linear-gradient(135deg, #10B981, #06B6D4); color: white; white-space: nowrap;
  &:hover { opacity: 0.9; }
}

// AI 体检步骤进度
.scan-progress {
  text-align: center; padding: $spacing-md;
}
.scan-step {
  text-align: left; font-size: 13px; color: $text-secondary; padding: 4px 0;
  transition: all 0.3s;
  &--latest { color: $text-primary; font-weight: 500; }
  &__dot { margin-right: 6px; }
}
.scan-summary-box {
  padding: $spacing-md; background: rgba(139,92,246,0.05); border-radius: $border-radius-sm; margin-bottom: $spacing-md;
  p { margin: 0 0 8px; line-height: 1.6; }
}
.scan-stats-row {
  display: flex; gap: $spacing-md; font-size: 13px; color: $text-secondary;
  span { background: rgba(0,0,0,0.04); padding: 2px 8px; border-radius: 4px; }
}
.scan-card {
  padding: $spacing-md; background: rgba(0,0,0,0.02); border-radius: $border-radius-sm; border-left: 3px solid #ddd; margin-bottom: 8px;
  &--applied { opacity: 0.5; }
  &__header { display: flex; align-items: center; gap: $spacing-sm; margin-bottom: 4px; font-size: 13px; }
  &__title { font-weight: 500; color: $text-primary; font-size: 14px; }
  &__reason { font-size: 13px; color: $text-secondary; margin-bottom: 4px; }
  &__suggestion { font-size: 13px; background: rgba(59,130,246,0.05); padding: 6px 10px; border-radius: 4px; margin-bottom: 6px; line-height: 1.5; }
  &__actions { display: flex; gap: $spacing-xs; }
}

.loading-spinner {
  border: 3px solid rgba(99,102,241,0.2); border-top-color: #6366F1; border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.detail-collapse {
  margin-bottom: $spacing-sm;
}
.detail-collapse__toggle {
  display: inline-block; padding: 3px 10px; border: none; background: rgba(0,0,0,0.03); border-radius: 6px;
  font-size: 12px; color: $text-muted; cursor: pointer; transition: all 0.15s;
  &:hover { background: rgba($primary-color, 0.08); color: $primary-color; }
}
.detail-core {
  display: flex; align-items: center; gap: $spacing-sm; margin-bottom: $spacing-md; flex-wrap: wrap;
  &__label { display: inline-flex; align-items: center; gap: 4px; font-size: $font-size-xs; color: $text-secondary; font-weight: 600; }
  &__btn {
    padding: 3px 12px; border-radius: 99px; border: 1px solid $border-color; background: transparent;
    font-size: $font-size-xs; color: $text-secondary; cursor: pointer; transition: all 0.15s;
    &:hover { border-color: #F97316; color: #C2410C; }
    &.detail-core__btn--week:hover { border-color: #F97316; color: #F97316; }
    &.detail-core__btn--month:hover { border-color: #3B82F6; color: #3B82F6; }
    &.detail-core__btn--year:hover { border-color: #8B5CF6; color: #8B5CF6; }
    &.detail-core__btn--on {
      font-weight: 600;
      &.detail-core__btn--week { background: rgba(#F97316, 0.12); border-color: #F97316; color: #C2410C; }
      &.detail-core__btn--month { background: rgba(#3B82F6, 0.12); border-color: #3B82F6; color: #1D4ED8; }
      &.detail-core__btn--year { background: rgba(#8B5CF6, 0.12); border-color: #8B5CF6; color: #6D28D9; }
    }
  }
}
.detail-add-child {
  display: flex; align-items: center; gap: 8px; margin-top: 8px;
}
.detail-add-child__input {
  flex: 1; border: 1px dashed $border-color; border-radius: 8px; padding: 6px 12px;
  font-size: 13px; font-family: inherit; background: transparent; box-sizing: border-box;
  &:focus { outline: none; border-color: $primary-color; border-style: solid; }
}
</style>
