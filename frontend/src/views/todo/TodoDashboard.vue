<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { TODO_API_BASE } from '@/config'
import { isCoreActive } from '@/utils/corePeriod'
import WellbeingQuickBar from '@/components/wellbeing/WellbeingQuickBar.vue'
import ChildProgressBadge from '@/components/todo/ChildProgressBadge.vue'
import TaskCreateExtras from '@/components/todo/TaskCreateExtras.vue'

// 简单的 Markdown 渲染函数
const renderMarkdown = (text: string): string => {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>')
    .replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`)
    .replace(/^---$/gm, '<hr/>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br/>')
    .replace(/^(.+)/, '<p>$1')
    .replace(/(.+)$/, '$1</p>')
}

const router = useRouter()

// 每日欢迎弹窗
const showWelcome = ref(false)
const checkDailyWelcome = () => {
  const todayStr = new Date().toISOString().split('T')[0]
  const lastVisit = localStorage.getItem('todo_last_visit_date')
  if (lastVisit !== todayStr) {
    showWelcome.value = true
    localStorage.setItem('todo_last_visit_date', todayStr)
    setTimeout(() => { showWelcome.value = false }, 3500)
  }
}

interface Overview {
  total_count: number
  today_count: number
  week_completed: number
  max_streak: number
  quadrant_distribution: Record<number, number>
  category_distribution: Record<string, number>
  status_distribution: Record<string, number>
}

interface TodoItem {
  id: number
  title: string
  description?: string
  quadrant: number
  status: string
  urgency: number
  importance: number
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
  estimated_minutes: number | null
  actual_minutes: number | null
  completed_at: string | null
  completion_note: string | null
  completion_notes: Array<{ content: string; timestamp: string }> | null
  core_scope?: 'week' | 'month' | 'year' | null
  core_period_key?: string | null
  created_at: string
  updated_at: string
  // 子任务完成统计（后端聚合返回）
  child_total?: number
  child_done?: number
}

const overview = ref<Overview | null>(null)
const todayItems = ref<TodoItem[]>([])
const suggestions = ref<any[]>([])
const inspirations = ref<TodoItem[]>([])
const loading = ref(true)
const suggestionsLoading = ref(false)
const error = ref('')

// 四象限配置
const quadrantConfig = [
  { id: 1, name: '重要且紧急', icon: 'Flag', color: '#EF4444', bgColor: 'rgba(239, 68, 68, 0.08)', borderColor: 'rgba(239, 68, 68, 0.2)' },
  { id: 2, name: '重要不紧急', icon: 'Flag', color: '#3B82F6', bgColor: 'rgba(59, 130, 246, 0.08)', borderColor: 'rgba(59, 130, 246, 0.2)' },
  { id: 3, name: '紧急不重要', icon: 'Flag', color: '#F59E0B', bgColor: 'rgba(245, 158, 11, 0.08)', borderColor: 'rgba(245, 158, 11, 0.2)' },
  { id: 4, name: '不重要不紧急', icon: 'Remove', color: '#94A3B8', bgColor: 'rgba(148, 163, 184, 0.08)', borderColor: 'rgba(148, 163, 184, 0.2)' },
]

const categoryLabels: Record<string, string> = {
  work: '工作/项目', learning: '学习/成长', life: '生活/事务',
  health: '健康/运动', social: '社交/关系', finance: '财务/投资', creative: '创意/探索',
}

// 快速新增待办
const showCreateModal = ref(false)
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

// 四象限待办
const quadrantItems = ref<Record<number, TodoItem[]>>({ 1: [], 2: [], 3: [], 4: [] })

const fetchData = async () => {
  loading.value = true
  try {
    const [overviewRes, todayRes] = await Promise.all([
      fetch(`${TODO_API_BASE}/overview`),
      fetch(`${TODO_API_BASE}/today`),
    ])
    if (!overviewRes.ok || !todayRes.ok) throw new Error('加载失败')
    overview.value = await overviewRes.json()
    const todayData = await todayRes.json()
    todayItems.value = todayData.items || []

    // 获取四象限待办
    for (const q of [1, 2, 3, 4]) {
      const res = await fetch(`${TODO_API_BASE}?quadrant=${q}&limit=8`)
      if (res.ok) {
        const data = await res.json()
        const allItems = data.items || []
        // 排序：未完成的在前，已完成/不解决的在后；同组内按 urgency 降序
        allItems.sort((a: TodoItem, b: TodoItem) => {
          const aDone = (a.status === 'completed' || a.status === 'wont_fix') ? 1 : 0
          const bDone = (b.status === 'completed' || b.status === 'wont_fix') ? 1 : 0
          if (aDone !== bDone) return aDone - bDone
          return (b.urgency || 0) - (a.urgency || 0)
        })
        quadrantItems.value[q] = allItems.slice(0, 5)
      }
    }

    // 获取灵感列表
    try {
      const inspRes = await fetch(`${TODO_API_BASE}?ai_category=inspiration&limit=6&sort_by=created_at`)
      if (inspRes.ok) {
        const inspData = await inspRes.json()
        inspirations.value = inspData.items || []
      }
    } catch { /* 静默 */ }
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const fetchSuggestions = async () => {
  suggestionsLoading.value = true
  try {
    const res = await fetch(`${TODO_API_BASE}/suggestions`)
    if (res.ok) {
      const data = await res.json()
      suggestions.value = data.suggestions || []
    }
  } catch (e) {
    // 静默失败
  } finally {
    suggestionsLoading.value = false
  }
}

const toggleComplete = async (item: TodoItem) => {
  try {
    const res = await fetch(`${TODO_API_BASE}/${item.id}/toggle`, { method: 'PATCH' })
    if (res.ok) {
      const updated = await res.json()
      item.status = updated.status
      item.completed_at = updated.completed_at
      // 局部更新：同步更新四象限中对应的 item
      for (const q of [1, 2, 3, 4]) {
        const found = quadrantItems.value[q]?.find((i: TodoItem) => i.id === item.id)
        if (found) {
          found.status = updated.status
          found.completed_at = updated.completed_at
        }
      }
      // 局部更新今日列表
      const todayFound = todayItems.value.find(i => i.id === item.id)
      if (todayFound) {
        todayFound.status = updated.status
        todayFound.completed_at = updated.completed_at
      }
      // 父任务完成时，同步更新详情弹窗中的子任务状态
      if (updated.status === 'completed' && detailChildren.value.length > 0) {
        detailChildren.value.forEach(child => {
          if (child.status !== 'completed') {
            child.status = 'completed'
            child.completed_at = updated.completed_at
          }
        })
      }
      // 静默刷新总览数据（不影响列表状态，不 loading）
      try {
        const overviewRes = await fetch(`${TODO_API_BASE}/overview`)
        if (overviewRes.ok) overview.value = await overviewRes.json()
      } catch { /* 静默 */ }
    }
  } catch (e) {
    // 静默
  }
}

const creating = ref(false)

const createItem = async () => {
  if (!newTitle.value.trim()) return
  creating.value = true
  try {
    const subs = newSubtasks.value.map(s => s.trim()).filter(Boolean)
    const todoData: any = {
      title: newTitle.value,
  description: newDescription.value || undefined,
      quadrant: newQuadrant.value,
      category: newIsWork.value ? 'work' : (newCategory.value || null),
      due_date: newDueDate.value || null,
      scheduled_date: newScheduledDate.value || null,
      status: newMarkDone.value ? 'completed' : 'planned',
      original_text: newTitle.value,
      skip_ai_eval: !newAiEval.value,
      ...(subs.length > 0 ? { sub_tasks: subs } : {}),
    }

    let created = false
    if (navigator.onLine) {
      try {
        const controller = new AbortController()
        const tid = setTimeout(() => controller.abort(), 5000)
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
    fetchData()
    // 5秒后再刷新，获取AI分类结果
    setTimeout(() => fetchData(), 5000)
  } catch (e) { /* 静默 */ }
  finally { creating.value = false }
}

// 同步本地缓存的待办（后端会自动触发AI分类）
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
    fetchData()
  }
}
window.addEventListener('online', syncPendingTodos)

const adoptSuggestion = async (suggestion: any) => {
  try {
    const res = await fetch(`${TODO_API_BASE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: suggestion.title,
        description: suggestion.description,
        category: suggestion.category,
        quadrant: suggestion.quadrant || 2,
        source: 'ai_suggest',
        status: 'evaluated',
      }),
    })
    if (res.ok) {
      suggestions.value = suggestions.value.filter(s => s.title !== suggestion.title)
      fetchData()
    }
  } catch (e) {
    // 静默
  }
}

const todayProgress = computed(() => {
  if (todayItems.value.length === 0) return 0
  const completed = todayItems.value.filter(i => i.status === 'completed').length
  return Math.round((completed / todayItems.value.length) * 100)
})

const navigateTo = (path: string) => router.push(path)

// 去除 markdown 格式
const stripMarkdown = (text: string) => {
  if (!text) return ''
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/_(.*?)_/g, '$1')
    .replace(/~~(.*?)~~/g, '$1')
    .replace(/`(.*?)`/g, '$1')
}

// 详情弹窗相关
const showDetailModal = ref(false)
const selectedItem = ref<TodoItem | null>(null)
const detailChildren = ref<TodoItem[]>([])
const detailLoading = ref(false)

// 核心任务设置（本周/本月核心，与全部待办页同一接口）
const detailStack = ref<TodoItem[]>([])
const toggleCore = async (scope: 'week' | 'month' | 'year') => {
  if (!selectedItem.value) return
  const isActive = isCoreActive(selectedItem.value) && selectedItem.value.core_scope === scope
  try {
    const res = await fetch(`${TODO_API_BASE}/${selectedItem.value.id}/core`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: isActive ? null : scope }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '设置失败')
    selectedItem.value = { ...selectedItem.value, core_scope: data.core_scope, core_period_key: data.core_period_key }
    fetchData()
  } catch (e: any) {
    alert(e.message || '设置核心失败')
  }
}
const detailExpanded = ref(false)
const descExpanded = ref(false)
const newChildTitle = ref('')

// 详情区块折叠（创建信息默认折叠；一键折叠/展开）
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
    comments.value = res.ok ? await res.json() : []
  } catch {
    comments.value = []
  }
}

async function addComment(kind: 'idea' | 'lesson' = 'idea') {
  const source = kind === 'lesson' ? newLesson : newComment
  const content = source.value.trim()
  if (!content || !selectedItem.value) return
  if (kind === 'lesson') lessonSaving.value = true
  else commentSaving.value = true
  try {
    const res = await fetch(`${TODO_API_BASE}/${selectedItem.value.id}/comments`, {
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
      detailChildren.value.sort((a, b) => (b.urgency || 0) - (a.urgency || 0))
    }
  } catch { /* */ }
}

async function deleteComment(commentId: number) {
  if (!confirm('确定删除这条想法？')) return
  try {
    const res = await fetch(`${TODO_API_BASE}/comments/${commentId}`, { method: 'DELETE' })
    if (res.ok) comments.value = comments.value.filter(c => c.id !== commentId)
  } catch { /* */ }
}

// 子任务数量/完成数变化后，把各处持有的同一条父任务统计同步（无需刷新页面即生效）
const bumpChildStat = (parentId: number, field: 'child_total' | 'child_done', delta: number) => {
  const lists: TodoItem[][] = [
    todayItems.value,
    inspirations.value,
    ...Object.values(quadrantItems.value),
  ]
  for (const list of lists) {
    const t = list.find(x => x.id === parentId)
    if (t) t[field] = Math.max(0, (t[field] || 0) + delta)
  }
  if (selectedItem.value && selectedItem.value.id === parentId) {
    selectedItem.value[field] = Math.max(0, (selectedItem.value[field] || 0) + delta)
  }
}

const bumpChildTotal = (parentId: number) => bumpChildStat(parentId, 'child_total', 1)

const addChildTask = async () => {
  if (!newChildTitle.value.trim() || !selectedItem.value) return
  const parentId = selectedItem.value.id
  try {
    const res = await fetch(`${TODO_API_BASE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newChildTitle.value.trim(), status: selectedItem.value.status, source: 'manual', parent_id: parentId }),
    })
    if (res.ok) {
      const child = await res.json()
      detailChildren.value.push(child)
      bumpChildTotal(parentId)
      newChildTitle.value = ''
    }
  } catch { /* */ }
}

const aiCategoryLabels: Record<string, { label: string; icon: string; color: string }> = {
  actionable: { label: '可执行', icon: 'Check', color: '#10B981' },
  answerable: { label: '直接解答', icon: 'Opportunity', color: '#3B82F6' },
  splittable: { label: '需拆分', icon: 'Sort', color: '#8B5CF6' },
  inspiration: { label: '灵感', icon: 'Star', color: '#F472B6' },
  questionable: { label: '需澄清', icon: 'QuestionFilled', color: '#F59E0B' },
  low_value: { label: '低价值', icon: 'Remove', color: '#94A3B8' },
}

const quadrantLabels: Record<number, { label: string; icon: string; color: string; bg: string }> = {
  1: { label: '重要紧急', icon: 'Flag', color: '#EF4444', bg: 'rgba(239, 68, 68, 0.12)' },
  2: { label: '重要不紧急', icon: 'Flag', color: '#3B82F6', bg: 'rgba(59, 130, 246, 0.12)' },
  3: { label: '紧急不重要', icon: 'Flag', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.12)' },
  4: { label: '不重要不紧急', icon: 'Remove', color: '#94A3B8', bg: 'rgba(148, 163, 184, 0.14)' },
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

const openItemDetail = async (item: TodoItem, fromStack = false) => {
  if (!fromStack && showDetailModal.value && selectedItem.value && selectedItem.value.id !== item.id) {
    detailStack.value.push({ ...selectedItem.value })
  }
  selectedItem.value = { ...item }
  detailChildren.value = []
  detailLoading.value = true
  showDetailModal.value = true

  // 加载评论（历史想法 / 经验沉淀）
  newComment.value = ''
  newLesson.value = ''
  loadComments(item.id)

  // 获取完整详情（首页列表数据可能字段不全）
  try {
    const res = await fetch(`${TODO_API_BASE}/${item.id}`)
    if (res.ok) {
      const fullItem = await res.json()
      selectedItem.value = fullItem
    }
  } catch { /* 使用已有数据 */ }

  // 获取子任务（专用端点，不受列表分页影响）
  try {
    const res = await fetch(`${TODO_API_BASE}/${item.id}/children`)
    if (res.ok) {
      detailChildren.value = await res.json()
    }
  } catch { /* 静默 */ }

  detailLoading.value = false
}

const closeDetail = () => {
  showDetailModal.value = false
  selectedItem.value = null
  detailChildren.value = []
  comments.value = []
  newComment.value = ''
  detailStack.value = []
}

const backToParent = () => {
  const parent = detailStack.value.pop()
  if (parent) openItemDetail(parent, true)
  else closeDetail()
}

const toggleChildComplete = async (child: TodoItem) => {
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
      // 父任务完成数同步，勾选后进度徽章立即变化
      const nowCompleted = updated.status === 'completed'
      if (child.parent_id && nowCompleted !== wasCompleted) {
        bumpChildStat(child.parent_id, 'child_done', nowCompleted ? 1 : -1)
      }
    }
  } catch { /* 静默 */ }
}

// 完成任务记录耗时
const showCompleteModal = ref(false)
const completingItem = ref<TodoItem | null>(null)
const actualMinutes = ref<number | null>(null)
const completionNote = ref('')
const existingNotes = ref<Array<{ content: string; timestamp: string }>>([])

const openCompleteModal = async (item: TodoItem) => {
  // 如果已完成，直接 toggle 回去
  if (item.status === 'completed') {
    await toggleComplete(item)
    return
  }
  completingItem.value = item
  actualMinutes.value = item.estimated_minutes || null
  completionNote.value = ''
  // 加载已有备注
  existingNotes.value = item.completion_notes || []
  showCompleteModal.value = true
}

const submitComplete = async () => {
  if (!completingItem.value) return
  try {
    const params = new URLSearchParams()
    params.set('todo_id', String(completingItem.value.id))
    if (actualMinutes.value) {
      params.set('actual_minutes', String(actualMinutes.value))
    }
    if (completionNote.value.trim()) {
      params.set('completion_note', completionNote.value.trim())
    }
    const res = await fetch(`${TODO_API_BASE}/complete-with-time?${params}`, { method: 'PATCH' })
    if (res.ok) {
      const updated = await res.json()
      const target = completingItem.value!
      if (target.parent_id) {
        const child = detailChildren.value.find(c => c.id === target.id)
        if (child && child.status !== 'completed') {
          child.status = updated.status
          child.completed_at = updated.completed_at
          child.completion_notes = updated.completion_notes
          bumpChildStat(target.parent_id, 'child_done', 1)
        }
        const inToday = todayItems.value.find(i => i.id === target.id)
        if (inToday) {
          inToday.status = updated.status
          inToday.completed_at = updated.completed_at
          inToday.completion_notes = updated.completion_notes
        }
        showCompleteModal.value = false
        completingItem.value = null
        actualMinutes.value = null
        completionNote.value = ''
        existingNotes.value = []
        return
      }
      // 更新本地状态
      const todayFound = todayItems.value.find(i => i.id === completingItem.value!.id)
      if (todayFound) {
        todayFound.status = updated.status
        todayFound.completed_at = updated.completed_at
        todayFound.actual_minutes = updated.actual_minutes
        todayFound.completion_notes = updated.completion_notes
      }
      for (const q of [1, 2, 3, 4]) {
        const found = quadrantItems.value[q]?.find((i: TodoItem) => i.id === completingItem.value!.id)
        if (found) {
          found.status = updated.status
          found.completed_at = updated.completed_at
          found.completion_notes = updated.completion_notes
        }
      }
      // 父任务完成时，同步更新详情弹窗中的子任务状态
      if (updated.status === 'completed' && detailChildren.value.length > 0) {
        detailChildren.value.forEach(child => {
          if (child.status !== 'completed') {
            child.status = 'completed'
            child.completed_at = updated.completed_at
          }
        })
      }
      // 同步更新 today 列表中的子任务状态
      if (updated.status === 'completed') {
        todayItems.value.forEach(ti => {
          if (ti.parent_id === completingItem.value!.id && ti.status !== 'completed') {
            ti.status = 'completed'
            ti.completed_at = updated.completed_at
          }
        })
        for (const q of [1, 2, 3, 4]) {
          quadrantItems.value[q]?.forEach((qi: TodoItem) => {
            if (qi.parent_id === completingItem.value!.id && qi.status !== 'completed') {
              qi.status = 'completed'
              qi.completed_at = updated.completed_at
            }
          })
        }
      }
      // 刷新总览
      try {
        const overviewRes = await fetch(`${TODO_API_BASE}/overview`)
        if (overviewRes.ok) overview.value = await overviewRes.json()
      } catch { /* 静默 */ }
    }
  } catch { /* 静默 */ }
  showCompleteModal.value = false
  completingItem.value = null
  actualMinutes.value = null
  completionNote.value = ''
  existingNotes.value = []
}

const cancelComplete = () => {
  showCompleteModal.value = false
  completingItem.value = null
  actualMinutes.value = null
  completionNote.value = ''
  existingNotes.value = []
}

const markWontFix = async () => {
  if (!completingItem.value) return
  try {
    const res = await fetch(`${TODO_API_BASE}/${completingItem.value.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'wont_fix' }),
    })
    if (res.ok) {
      await res.json()
      // 更新本地状态
      const todayFound = todayItems.value.find(i => i.id === completingItem.value!.id)
      if (todayFound) { todayFound.status = 'wont_fix' }
      for (const q of [1, 2, 3, 4]) {
        const found = quadrantItems.value[q]?.find((i: TodoItem) => i.id === completingItem.value!.id)
        if (found) { found.status = 'wont_fix' }
      }
    }
  } catch { /* 静默 */ }
  showCompleteModal.value = false
  completingItem.value = null
  actualMinutes.value = null
  completionNote.value = ''
  existingNotes.value = []
}

const goToEdit = () => {
  if (selectedItem.value) {
    // 导航到全部待办列表页，让用户可以编辑
    navigateTo('/todo/list')
  }
  closeDetail()
}

onMounted(() => {
  fetchData()
  checkDailyWelcome()
})
</script>

<template>
  <div class="todo-dashboard">
    <!-- 每日欢迎弹窗 -->
    <Transition name="welcome-fade">
      <div v-if="showWelcome" class="welcome-overlay" @click="showWelcome = false">
        <div class="welcome-card" @click.stop>
          <span class="welcome-card__emoji">🌟</span>
          <p class="welcome-card__text">亲爱的陆兴，美好而充实的一天又开始了</p>
          <button class="welcome-card__close" @click="showWelcome = false">开始吧!</button>
        </div>
      </div>
    </Transition>

    <div class="todo-dashboard__header">
      <div>
        <h1><Check class="ep-icon" /> 待办系统</h1>
        <p class="todo-dashboard__subtitle">AI 智能任务管理</p>
      </div>
      <div class="todo-dashboard__header-actions">
        <button class="btn btn--calendar" @click="navigateTo('/todo/calendar')"><Calendar class="ep-icon" /> 日历规划</button>
      </div>
    </div>

    <!-- 加载 / 错误 -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
      <p>加载中...</p>
    </div>

    <div v-else-if="error" class="error-card">
      <p>{{ error }}</p>
      <button class="btn btn--ghost" @click="fetchData">重试</button>
    </div>

    <template v-else-if="overview">
      <!-- 统计卡片 -->
      <div class="stats-grid">
        <div class="stat-card" @click="navigateTo('/todo/list')">
          <span class="stat-card__icon"><Document class="ep-icon" /></span>
          <span class="stat-card__value">{{ overview.total_count }}</span>
          <span class="stat-card__label">待办总数</span>
        </div>
        <div class="stat-card">
          <span class="stat-card__icon"><Calendar class="ep-icon" /></span>
          <span class="stat-card__value">{{ overview.today_count }}</span>
          <span class="stat-card__label">今日计划</span>
        </div>
        <div class="stat-card" @click="navigateTo('/todo/review')">
          <span class="stat-card__icon">✨</span>
          <span class="stat-card__value">{{ overview.week_completed }}</span>
          <span class="stat-card__label">本周完成</span>
        </div>
        <div class="stat-card" @click="navigateTo('/todo/habits')">
          <span class="stat-card__icon">🔥</span>
          <span class="stat-card__value">{{ overview.max_streak }}</span>
          <span class="stat-card__label">最长连续</span>
        </div>
      </div>

      <!-- 今日计划（在四象限上方，突出显示） -->
      <div class="section-card today-plan today-plan--top">
        <div class="section-card__header">
          <h3><Calendar class="ep-icon" /> 今日计划</h3>
          <div class="today-plan__header-right">
            <button class="btn btn--sm btn--ghost" @click="navigateTo('/todo/calendar')">去安排 →</button>
            <span v-if="todayItems.length > 0" class="today-plan__sort-hint">按优先级排序</span>
            <div class="today-plan__progress">
              <div class="today-plan__progress-bar">
                <div class="today-plan__progress-fill" :style="{ width: todayProgress + '%' }"></div>
              </div>
              <span class="today-plan__progress-text">{{ todayProgress }}%</span>
            </div>
          </div>
        </div>
        <div v-if="todayItems.length === 0" class="empty-state">
          <span class="empty-state__icon">☕</span>
          <p>今日暂无计划，<a href="javascript:;" @click="navigateTo('/todo/calendar')" style="color: #EC4899; text-decoration: underline;">去日历安排任务</a></p>
        </div>
        <div v-else class="today-list">
          <div
            v-for="(item, idx) in todayItems"
            :key="item.id"
            class="today-item"
            :class="{
              'today-item--done': item.status === 'completed',
              'today-item--urgent': item.quadrant === 1,
              'today-item--important': item.quadrant === 2,
            }"
            @click="openItemDetail(item)"
          >
            <label class="checkbox" @click.stop="openCompleteModal(item)">
              <input type="checkbox" :checked="item.status === 'completed'" @change.prevent />
              <span class="checkbox__mark"></span>
            </label>
            <span class="today-item__rank" :class="`today-item__rank--q${item.quadrant}`">{{ idx + 1 }}</span>
            <div class="today-item__content">
              <span class="today-item__title" :style="{ color: quadrantConfig[item.quadrant - 1]?.color }">{{ stripMarkdown(item.title) }}</span>
              <ChildProgressBadge v-if="item.child_total" :total="item.child_total" :done="item.child_done || 0" />
              <div class="today-item__info">
                <span class="today-item__quadrant" :style="{ color: quadrantConfig[item.quadrant - 1]?.color, background: quadrantConfig[item.quadrant - 1]?.bgColor }">
                  <component :is="quadrantConfig[item.quadrant - 1]?.icon" class="ep-icon" /> {{ quadrantConfig[item.quadrant - 1]?.name }}
                </span>
                <span v-if="item.category" class="today-item__category">{{ categoryLabels[item.category] || item.category }}</span>
                <span v-if="item.estimated_minutes" class="today-item__time"><Timer class="ep-icon" />️ {{ item.estimated_minutes }}min</span>
                <span v-if="item.actual_minutes" class="today-item__time today-item__time--actual"><Check class="ep-icon" /> {{ item.actual_minutes }}min</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 四象限矩阵 -->
      <div class="quadrant-matrix">
        <div
          v-for="q in quadrantConfig"
          :key="q.id"
          class="quadrant-cell"
          :style="{ background: q.bgColor, borderColor: q.borderColor }"
        >
          <div class="quadrant-cell__header">
            <span :style="{ color: q.color }"><component :is="q.icon" class="ep-icon" /> {{ q.name }}</span>
            <span class="quadrant-cell__count" :style="{ color: q.color }">{{ overview.quadrant_distribution[q.id] || 0 }}</span>
          </div>
          <div class="quadrant-cell__list">
            <div
              v-for="item in quadrantItems[q.id]"
              :key="item.id"
              class="quadrant-item"
              :class="{ 'quadrant-item--done': item.status === 'completed' }"
              @click="openItemDetail(item)"
            >
              <label class="checkbox" @click.stop="item.status === 'completed' ? toggleComplete(item) : openCompleteModal(item)">
                <input type="checkbox" :checked="item.status === 'completed'" @change.prevent />
                <span class="checkbox__mark"></span>
              </label>
              <span class="quadrant-item__title" :style="{ color: quadrantConfig[item.quadrant - 1]?.color }">{{ stripMarkdown(item.title) }}</span>
              <ChildProgressBadge v-if="item.child_total" compact :total="item.child_total" :done="item.child_done || 0" />
            </div>
            <div v-if="!quadrantItems[q.id]?.length" class="quadrant-cell__empty">暂无</div>
          </div>
          <button
            v-if="(overview.quadrant_distribution[q.id] || 0) > 5"
            class="btn btn--sm btn--ghost"
            @click="navigateTo(`/todo/list?quadrant=${q.id}`)"
          >查看更多 →</button>
        </div>
      </div>

      <div class="todo-dashboard__bottom">
        <!-- AI 建议 -->
        <div class="section-card ai-suggestions">
          <div class="section-card__header">
            <h3><MagicStick class="ep-icon" /> AI 建议</h3>
            <button class="btn btn--sm btn--ghost" @click="fetchSuggestions" :disabled="suggestionsLoading">
              {{ suggestionsLoading ? '获取中...' : (suggestions.length > 0 ? '刷新建议' : '获取建议') }}
            </button>
          </div>
          <div v-if="suggestionsLoading" class="loading loading--sm">
            <div class="loading__spinner loading__spinner--sm"></div>
          </div>
          <div v-else-if="suggestions.length === 0" class="empty-state">
            <span class="empty-state__icon"><Opportunity class="ep-icon" /></span>
            <p>点击「获取建议」让 AI 根据你的待办和日记给出推荐</p>
          </div>
          <div v-else class="suggestions-list">
            <div v-for="(s, idx) in suggestions" :key="idx" class="suggestion-card">
              <div class="suggestion-card__content">
                <h4>{{ s.title }}</h4>
                <p>{{ s.description }}</p>
                <span v-if="s.reason" class="suggestion-card__reason"><Opportunity class="ep-icon" /> {{ s.reason }}</span>
              </div>
              <button class="btn btn--sm btn--primary" @click="adoptSuggestion(s)">采纳</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 灵感墙 -->
      <div v-if="inspirations.length > 0" class="section-card inspiration-wall">
        <div class="section-card__header">
          <h3><Star class="ep-icon" /> 灵感墙</h3>
          <button class="btn btn--sm btn--ghost" @click="navigateTo('/todo/list')">查看全部</button>
        </div>
        <div class="inspiration-grid">
          <div
            v-for="item in inspirations"
            :key="item.id"
            class="inspiration-card"
          >
            <div class="inspiration-card__title">{{ stripMarkdown(item.title) }}</div>
            <div v-if="item.category" class="inspiration-card__category">
              {{ categoryLabels[item.category] || item.category }}
            </div>
            <div class="inspiration-card__date">{{ item.created_at?.split('T')[0] }}</div>
          </div>
        </div>
      </div>

    </template>

    <!-- 详情弹窗 -->
    <div v-if="showDetailModal && selectedItem" class="detail-overlay" @click.self="closeDetail">
      <div class="detail-modal">
        <div class="detail-modal__header">
          <h3>待办详情</h3>
          <div class="modal__header-actions">
            <button v-if="detailStack.length" class="btn btn--sm btn--ghost" @click="backToParent">返回父任务</button>
            <button class="btn btn--sm btn--ghost" @click="toggleAllSections">{{ detailAllExpanded ? '一键折叠' : '一键展开' }}</button>
            <button class="btn btn--sm btn--ghost" @click="closeDetail"><Close class="ep-icon" /></button>
          </div>
        </div>
        <div class="detail-modal__body">
          <h4 class="detail-modal__title">{{ stripMarkdown(selectedItem.title) }}</h4>
          <div class="detail-modal__tags">
            <!-- 直接解答类不显示四象限，显示"已解答"标签 -->
            <template v-if="selectedItem.ai_category === 'answerable'">
              <span class="detail-modal__tag detail-modal__tag--answered"><Lightning class="ep-icon" /> 已解答</span>
            </template>
            <template v-else>
              <span class="detail-modal__tag" :style="{ color: quadrantLabels[selectedItem.quadrant]?.color, background: quadrantLabels[selectedItem.quadrant]?.bg }">
                <component :is="quadrantLabels[selectedItem.quadrant]?.icon" class="ep-icon" /> {{ quadrantLabels[selectedItem.quadrant]?.label }}
              </span>
            </template>
            <span v-if="selectedItem.category" class="detail-modal__tag detail-modal__tag--category">
              {{ categoryLabels[selectedItem.category] || selectedItem.category }}
            </span>
            <span class="detail-modal__tag" :style="{ color: statusLabels[selectedItem.status]?.color }">
              {{ statusLabels[selectedItem.status]?.label }}
            </span>
            <span v-if="selectedItem.ai_category && selectedItem.ai_category !== 'answerable'" class="detail-modal__tag" :style="{ color: aiCategoryLabels[selectedItem.ai_category]?.color }">
              <component :is="aiCategoryLabels[selectedItem.ai_category]?.icon" class="ep-icon" /> {{ aiCategoryLabels[selectedItem.ai_category]?.label }}
            </span>
          </div>

          <!-- 原始输入 & AI 评估 (折叠) -->
          <div v-if="selectedItem.original_text || selectedItem.ai_evaluation" class="detail-modal__collapse">
            <button class="detail-modal__collapse-toggle" @click="detailExpanded = !detailExpanded">
              {{ detailExpanded ? '▼ 收起' : '▶ 原始输入 / AI 评估' }}
            </button>
            <template v-if="detailExpanded">
              <div v-if="selectedItem.original_text" class="detail-modal__section detail-modal__section--highlight">
                <div class="detail-modal__section-label"><Document class="ep-icon" /> 原始输入</div>
                <div class="detail-modal__section-value">{{ selectedItem.original_text }}</div>
              </div>
              <div v-if="selectedItem.ai_evaluation" class="detail-modal__section detail-modal__section--ai">
                <div class="detail-modal__section-label"><MagicStick class="ep-icon" /> AI 评估</div>
                <div class="detail-modal__section-value detail-modal__markdown" v-html="renderMarkdown(selectedItem.ai_evaluation)"></div>
              </div>
            </template>
          </div>

          <!-- AI 解答 -->
          <div v-if="selectedItem.ai_answer && selectedItem.ai_category !== 'inspiration'" class="detail-modal__section detail-modal__section--answer">
            <div class="detail-modal__section-label"><Lightning class="ep-icon" /> AI 解答</div>
            <div class="detail-modal__section-value detail-modal__section-value--answer detail-modal__markdown" v-html="renderMarkdown(selectedItem.ai_answer)"></div>
          </div>

          <!-- 灵感点评 -->
          <div v-if="selectedItem.ai_answer && selectedItem.ai_category === 'inspiration'" class="detail-modal__section detail-modal__section--inspiration">
            <div class="detail-modal__section-label"><Star class="ep-icon" /> 灵感点评</div>
            <div class="detail-modal__section-value detail-modal__section-value--inspiration detail-modal__markdown" v-html="renderMarkdown(selectedItem.ai_answer)"></div>
          </div>

          <!-- 核心任务标记 -->
          <div class="detail-core">
            <span class="detail-core__label">★ 核心任务：</span>
            <button
              class="detail-core__btn detail-core__btn--week"
              :class="{ 'detail-core__btn--on': isCoreActive(selectedItem) && selectedItem.core_scope === 'week' }"
              @click="toggleCore('week')"
            >{{ isCoreActive(selectedItem) && selectedItem.core_scope === 'week' ? '★ 本周核心（点击取消）' : '设为本周核心' }}</button>
            <button
              class="detail-core__btn detail-core__btn--month"
              :class="{ 'detail-core__btn--on': isCoreActive(selectedItem) && selectedItem.core_scope === 'month' }"
              @click="toggleCore('month')"
            >{{ isCoreActive(selectedItem) && selectedItem.core_scope === 'month' ? '★ 本月核心（点击取消）' : '设为本月核心' }}</button>
            <button
              class="detail-core__btn detail-core__btn--year"
              :class="{ 'detail-core__btn--on': isCoreActive(selectedItem) && selectedItem.core_scope === 'year' }"
              @click="toggleCore('year')"
            >{{ isCoreActive(selectedItem) && selectedItem.core_scope === 'year' ? '★ 年度目标（点击取消）' : '设为年度目标' }}</button>
          </div>

          <!-- 描述（默认折叠） -->
          <div v-if="selectedItem.description" class="detail-modal__collapse">
            <button class="detail-modal__collapse-toggle" @click="descExpanded = !descExpanded">
              {{ descExpanded ? '▼ 收起描述' : '▶ 描述' }}
            </button>
            <div v-if="descExpanded" class="detail-modal__section">
              <div class="detail-modal__section-value detail-modal__markdown" v-html="renderMarkdown(selectedItem.description)"></div>
            </div>
          </div>

          <!-- 子任务 -->
          <div class="detail-modal__section">
            <button class="detail-modal__section-label detail-modal__section-label--toggle" @click="childrenExpanded = !childrenExpanded">
              <FolderOpened class="ep-icon" /> 子任务 ({{ detailChildren.length }}) <span>{{ childrenExpanded ? '▾' : '▸' }}</span>
            </button>
            <template v-if="childrenExpanded">
            <div v-if="detailChildren.length > 0" class="detail-modal__children">
              <div v-for="child in detailChildren" :key="child.id" class="detail-modal__child"
                :class="{ 'detail-modal__child--done': child.status === 'completed' }">
                <label class="checkbox" @click.stop="toggleChildComplete(child)">
                  <input type="checkbox" :checked="child.status === 'completed'" @change.prevent />
                  <span class="checkbox__mark"></span>
                </label>
                <span class="detail-modal__child-flag" :style="{ color: quadrantLabels[child.quadrant]?.color }" :title="quadrantLabels[child.quadrant]?.label">
                  <component :is="quadrantLabels[child.quadrant]?.icon" class="ep-icon" />
                </span>
                <span class="detail-modal__child-title" @click.stop="openItemDetail(child)">{{ stripMarkdown(child.title) }}</span>
                <select class="detail-modal__child-urg" :value="child.urgency" @click.stop @change="patchChildUrgency(child, $event)">
                  <option v-for="n in [5,4,3,2,1]" :key="n" :value="n">紧急{{ n }}</option>
                </select>
                <span class="detail-modal__child-status" :style="{ color: statusLabels[child.status]?.color }">
                  {{ statusLabels[child.status]?.label }}
                </span>
              </div>
            </div>
            <div class="detail-modal__add-child">
              <input v-model="newChildTitle" class="detail-modal__add-child-input" placeholder="＋ 添加子任务" @keydown.enter.prevent="addChildTask" />
              <button v-if="newChildTitle.trim()" class="btn btn--sm btn--primary" @click="addChildTask">添加</button>
            </div>
            </template>
          </div>

          <!-- 完成备注 -->
          <div v-if="selectedItem.completion_notes && selectedItem.completion_notes.length > 0" class="detail-modal__notes">
            <div class="detail-modal__notes-title"><ChatLineSquare class="ep-icon" /> 完成备注</div>
            <div class="detail-modal__notes-list">
              <div v-for="(note, idx) in selectedItem.completion_notes" :key="idx" class="detail-modal__note-item">
                <span class="detail-modal__note-content">{{ note.content }}</span>
                <span class="detail-modal__note-time">{{ note.timestamp?.split('T')[0] || '' }}</span>
              </div>
            </div>
          </div>

          <!-- 评论：随时记录想法，支持二次编辑 -->
          <div class="detail-modal__comments">
            <button class="detail-modal__notes-title detail-modal__section-label--toggle" @click="commentsExpanded = !commentsExpanded">
              <ChatLineSquare class="ep-icon" /> 想法记录 ({{ ideaComments.length }}) <span>{{ commentsExpanded ? '▾' : '▸' }}</span>
            </button>
            <template v-if="commentsExpanded">
            <div v-if="ideaComments.length > 0" class="detail-modal__notes-list">
              <div v-for="c in ideaComments" :key="c.id" class="detail-modal__note-item">
                <template v-if="editingCommentId === c.id">
                  <input v-model="editingCommentText" class="detail-comment-edit" @keydown.enter.exact.prevent="saveComment(c)" />
                  <button class="detail-modal__note-edit" @click.stop="saveComment(c)">保存</button>
                  <button class="detail-modal__note-edit" @click.stop="editingCommentId = null">取消</button>
                </template>
                <template v-else>
                  <span class="detail-modal__note-content">{{ c.content }}</span>
                  <span class="detail-modal__note-time">{{ c.created_at?.replace('T', ' ').slice(0, 16) || '' }}</span>
                  <button class="detail-modal__note-edit" @click.stop="startEditComment(c)" title="编辑">✎</button>
                  <button class="detail-modal__note-del" @click.stop="deleteComment(c.id)" title="删除"><Close class="ep-icon" /></button>
                </template>
              </div>
            </div>
            <div class="detail-modal__comment-input">
              <textarea
                v-model="newComment"
                class="detail-modal__comment-textarea"
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

          <div class="detail-modal__comments">
            <button class="detail-modal__notes-title detail-modal__section-label--toggle" @click="lessonsExpanded = !lessonsExpanded">
              <Notebook class="ep-icon" /> 经验沉淀 ({{ lessonComments.length }}) <span>{{ lessonsExpanded ? '▾' : '▸' }}</span>
            </button>
            <template v-if="lessonsExpanded">
            <div v-if="lessonComments.length > 0" class="detail-modal__notes-list">
              <div v-for="c in lessonComments" :key="c.id" class="detail-modal__note-item">
                <template v-if="editingCommentId === c.id">
                  <input v-model="editingCommentText" class="detail-comment-edit" @keydown.enter.exact.prevent="saveComment(c)" />
                  <button class="detail-modal__note-edit" @click.stop="saveComment(c)">保存</button>
                  <button class="detail-modal__note-edit" @click.stop="editingCommentId = null">取消</button>
                </template>
                <template v-else>
                  <span class="detail-modal__note-content">{{ c.content }}</span>
                  <span class="detail-modal__note-time">{{ c.created_at?.replace('T', ' ').slice(0, 16) || '' }}</span>
                  <button class="detail-modal__note-edit" @click.stop="startEditComment(c)" title="编辑">✎</button>
                  <button class="detail-modal__note-del" @click.stop="deleteComment(c.id)" title="删除"><Close class="ep-icon" /></button>
                </template>
              </div>
            </div>
            <div class="detail-modal__comment-input">
              <textarea
                v-model="newLesson"
                class="detail-modal__comment-textarea"
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
          <div class="detail-modal__meta">
            <button class="detail-modal__notes-title detail-modal__section-label--toggle" @click="metaExpanded = !metaExpanded">
              创建信息 <span>{{ metaExpanded ? '▾' : '▸' }}</span>
            </button>
            <div v-show="metaExpanded" class="detail-modal__meta-grid">
            <div><span class="detail-modal__meta-label">紧急度</span> {{ selectedItem.urgency }}/5</div>
            <div><span class="detail-modal__meta-label">重要度</span> {{ selectedItem.importance }}/5</div>
            <div v-if="selectedItem.due_date"><span class="detail-modal__meta-label">截止日期</span> {{ selectedItem.due_date }}</div>
            <div v-if="selectedItem.source"><span class="detail-modal__meta-label">来源</span> {{ selectedItem.source }}</div>
            <div v-if="selectedItem.estimated_minutes"><span class="detail-modal__meta-label">预估时间</span> {{ selectedItem.estimated_minutes }}分钟</div>
            <div v-if="selectedItem.actual_minutes"><span class="detail-modal__meta-label">实际用时</span> {{ selectedItem.actual_minutes }}分钟</div>
            <div><span class="detail-modal__meta-label">创建于</span> {{ selectedItem.created_at?.split('T')[0] }}</div>
            <div v-if="selectedItem.completed_at"><span class="detail-modal__meta-label">完成于</span> {{ selectedItem.completed_at?.split('T')[0] }}</div>
            </div>
          </div>
        </div>
        <div class="detail-modal__actions">
          <button class="btn btn--ghost" @click="closeDetail">关闭</button>
          <button class="btn btn--primary" @click="goToEdit">去编辑</button>
        </div>
      </div>
    </div>

    <!-- 完成记录耗时弹窗 -->
    <div v-if="showCompleteModal && completingItem" class="detail-overlay" @click.self="cancelComplete">
      <div class="detail-modal detail-modal--complete">
        <div class="detail-modal__header">
          <h3><Check class="ep-icon" /> 完成任务</h3>
          <button class="btn btn--sm btn--ghost" @click="cancelComplete"><Close class="ep-icon" /></button>
        </div>
        <div class="detail-modal__body">
          <p class="complete-modal__title">{{ stripMarkdown(completingItem.title) }}</p>
          <div class="complete-modal__field">
            <label>实际耗时（分钟，可不填）</label>
            <div class="complete-modal__input-row">
              <button v-for="t in [5, 15, 30, 60, 120]" :key="t" class="btn btn--sm" :class="{ 'btn--primary': actualMinutes === t }" @click="actualMinutes = t">{{ t }}min</button>
              <button class="btn btn--sm" :class="{ 'btn--primary': actualMinutes === null }" @click="actualMinutes = null">不记录</button>
            </div>
            <input type="number" v-model.number="actualMinutes" min="1" placeholder="自定义分钟数" class="complete-modal__input" />
          </div>
          <!-- 已有备注 -->
          <div v-if="existingNotes.length > 0" class="complete-modal__field">
            <label><ChatLineSquare class="ep-icon" /> 已有备注</label>
            <div class="complete-modal__notes-list">
              <div v-for="(note, idx) in existingNotes" :key="idx" class="complete-modal__note-item">
                <span class="complete-modal__note-content">{{ note.content }}</span>
                <span class="complete-modal__note-time">{{ note.timestamp?.split('T')[0] || '' }}</span>
              </div>
            </div>
          </div>
          <div class="complete-modal__field">
            <label>{{ existingNotes.length > 0 ? '追加备注（可选）' : '备注（可选）' }}</label>
            <textarea v-model="completionNote" class="complete-modal__textarea" rows="2" placeholder="记录些什么..."></textarea>
          </div>
          <p v-if="completingItem.estimated_minutes" class="complete-modal__hint">
            预估耗时：{{ completingItem.estimated_minutes }} 分钟
            <template v-if="actualMinutes">
              <span v-if="actualMinutes <= completingItem.estimated_minutes" style="color: #10B981"> → 比预期快 👏</span>
              <span v-else style="color: #F59E0B"> → 比预期多 {{ actualMinutes - completingItem.estimated_minutes }} 分钟</span>
            </template>
          </p>
        </div>
        <div class="detail-modal__actions">
          <button class="btn btn--ghost" @click="cancelComplete">取消</button>
          <button class="btn btn--ghost" @click="markWontFix" title="标记为不解决，不记录耗时">🚫 不解决</button>
          <button class="btn btn--primary" @click="submitComplete"><Check class="ep-icon" /> 确认完成</button>
        </div>
      </div>
    </div>

    <!-- 心力快捷记录 -->
    <WellbeingQuickBar />

    <!-- 浮动新增按钮 -->
    <button class="fab" @click="showCreateModal = true" title="新增待办">+</button>

    <!-- 新建待办 Modal -->
    <div v-if="showCreateModal" class="detail-overlay" @click.self="showCreateModal = false">
      <div class="detail-modal detail-modal--create">
        <div class="detail-modal__header">
          <h3><Document class="ep-icon" /> 快速新增待办</h3>
          <button class="btn btn--sm btn--ghost" @click="showCreateModal = false"><Close class="ep-icon" /></button>
        </div>
        <div class="detail-modal__body">
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
                <option :value="1">🔴 重要且紧急</option>
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
              <label>计划日期</label>
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
        <div class="detail-modal__actions">
          <button class="btn btn--ghost" @click="showCreateModal = false" :disabled="creating">取消</button>
          <button class="btn btn--primary" @click="createItem" :disabled="!newTitle.trim() || creating">
            <MagicStick v-if="creating" class="ep-icon" /> {{ creating ? 'AI 分类中...' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.todo-dashboard {
  &__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: $spacing-lg;

    h1 {
      font-size: $font-size-xl;
      @media (max-width: $breakpoint-sm) { font-size: $font-size-lg; }
    }
  }

  &__subtitle {
    color: $text-secondary;
    font-size: $font-size-sm;
    margin-top: $spacing-xs;
  }

  &__bottom {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: $spacing-lg;
    margin-top: $spacing-lg;

    @media (max-width: $breakpoint-md) {
      grid-template-columns: 1fr;
    }
  }
}

// 统计卡片
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $spacing-md;
  margin-bottom: $spacing-lg;

  @media (max-width: $breakpoint-md) { grid-template-columns: repeat(2, 1fr); }
  @media (max-width: $breakpoint-sm) { gap: $spacing-sm; }
}

.stat-card {
  @include glass-card;
  padding: $spacing-lg;
  text-align: center;
  cursor: pointer;
  @include hover-lift;

  @media (max-width: $breakpoint-sm) { padding: $spacing-md; }

  &__icon { font-size: 32px; display: block; margin-bottom: $spacing-sm; }
  &__value {
    font-size: $font-size-xxl; font-weight: 700;
    background: linear-gradient(135deg, #EC4899, #8B5CF6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    display: block;
    @media (max-width: $breakpoint-sm) { font-size: $font-size-xl; }
  }
  &__label { font-size: $font-size-sm; color: $text-secondary; margin-top: $spacing-xs; display: block; }
}

// 四象限矩阵
.quadrant-matrix {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-md;

  @media (max-width: $breakpoint-sm) {
    grid-template-columns: 1fr;
    gap: $spacing-sm;
  }
}

.quadrant-cell {
  @include glass-card;
  padding: $spacing-md;
  border: 1px solid;
  min-height: 180px;
  overflow: hidden;

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: $font-size-sm;
    font-weight: 600;
    margin-bottom: $spacing-sm;
  }

  &__count {
    font-size: $font-size-xs;
    background: rgba(0,0,0,0.06);
    padding: 2px 8px;
    border-radius: 10px;
  }

  &__list {
    display: flex;
    flex-direction: column;
    gap: $spacing-xs;
  }

  &__empty {
    text-align: center;
    color: $text-muted;
    font-size: $font-size-sm;
    padding: $spacing-md 0;
  }
}

.quadrant-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-xs $spacing-sm;
  border-radius: $border-radius-sm;
  background: rgba(255,255,255,0.6);
  transition: all $transition-fast;
  cursor: pointer;
  min-width: 0;

  &:hover { background: rgba(255,255,255,0.9); }
  &:active { transform: scale(0.98); }

  &--done {
    opacity: 0.5;
    .quadrant-item__title { text-decoration: line-through; color: $text-muted; }
  }

  &__title {
    flex: 1;
    font-size: $font-size-sm;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
  }
}

// Checkbox
.checkbox {
  position: relative;
  display: flex;
  align-items: center;
  cursor: pointer;
  flex-shrink: 0;

  input {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
  }

  &__mark {
    width: 18px;
    height: 18px;
    border: 2px solid $border-color;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all $transition-fast;

    &::after {
      content: '';
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: transparent;
      transition: all $transition-fast;
    }
  }

  input:checked + .checkbox__mark {
    border-color: #10B981;
    background: #10B981;

    &::after {
      background: white;
    }
  }
}

// 今日计划
.today-plan {
  &__header-right {
    display: flex;
    align-items: center;
    gap: $spacing-md;

    @media (max-width: $breakpoint-sm) {
      gap: $spacing-xs;
    }
  }

  &__sort-hint {
    font-size: $font-size-xs;
    color: $text-muted;
    font-style: italic;

    @media (max-width: $breakpoint-sm) {
      display: none;
    }
  }

  &__progress {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    flex-shrink: 0;
  }

  &__progress-bar {
    width: 100px;
    height: 6px;
    background: rgba($primary-color, 0.1);
    border-radius: 3px;
    overflow: hidden;

    @media (max-width: $breakpoint-sm) {
      width: 60px;
    }
  }

  &__progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #10B981, #06B6D4);
    border-radius: 3px;
    transition: width 0.5s ease;
  }

  &__progress-text {
    font-size: $font-size-xs;
    font-weight: 600;
    color: #10B981;
  }
}

.today-list { display: flex; flex-direction: column; gap: $spacing-xs; }

.today-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-sm;
  background: rgba(255,255,255,0.5);
  transition: all $transition-fast;
  cursor: pointer;
  min-width: 0;

  &:hover { background: rgba(255,255,255,0.8); }
  &:active { transform: scale(0.98); }

  &--done {
    opacity: 0.5;
    .today-item__title { text-decoration: line-through; color: $text-muted; }
  }

  &--urgent {
    background: rgba(239, 68, 68, 0.06);
    border-left: 3px solid #EF4444;
  }

  &--important {
    background: rgba(59, 130, 246, 0.04);
    border-left: 3px solid #3B82F6;
  }

  &__rank {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    flex-shrink: 0;
    color: white;
    background: $text-muted;

    &--q1 { background: #EF4444; }
    &--q2 { background: #3B82F6; }
    &--q3 { background: #F59E0B; }
    &--q4 { background: #94A3B8; }
  }

  &__content { flex: 1; min-width: 0; }
  &__title {
    font-size: $font-size-sm;
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__info {
    display: flex;
    gap: $spacing-sm;
    margin-top: 2px;
  }

  &__quadrant {
    font-size: 10px;
    white-space: nowrap;
  }

  &__category {
    font-size: 10px;
    padding: 0 4px;
    border-radius: 4px;
    background: rgba(139, 92, 246, 0.1);
    color: #8B5CF6;
    white-space: nowrap;
  }
}

// AI 建议
.suggestions-list { display: flex; flex-direction: column; gap: $spacing-sm; }

.suggestion-card {
  display: flex;
  align-items: flex-start;
  gap: $spacing-md;
  padding: $spacing-md;
  border-radius: $border-radius-md;
  background: linear-gradient(135deg, rgba(236, 72, 153, 0.05), rgba(139, 92, 246, 0.05));
  border: 1px solid rgba(236, 72, 153, 0.15);
  transition: all $transition-fast;

  @media (max-width: $breakpoint-sm) {
    flex-direction: column;
    gap: $spacing-sm;
  }

  &:hover { border-color: rgba(236, 72, 153, 0.3); }

  &__content {
    flex: 1;
    min-width: 0;

    h4 {
      font-size: $font-size-sm;
      font-weight: 600;
      margin-bottom: $spacing-xs;
      word-break: break-word;
    }
    p {
      font-size: $font-size-xs;
      color: $text-secondary;
      margin-bottom: $spacing-xs;
      word-break: break-word;
    }
  }

  &__reason {
    font-size: $font-size-xs;
    color: #8B5CF6;
    word-break: break-word;
  }
}

// 灵感墙
.inspiration-wall {
  grid-column: 1 / -1;
}

.inspiration-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: $spacing-sm;

  @media (max-width: $breakpoint-md) { grid-template-columns: repeat(2, 1fr); }
  @media (max-width: $breakpoint-sm) { grid-template-columns: 1fr; }
}

.inspiration-card {
  padding: $spacing-md;
  border-radius: $border-radius-md;
  background: linear-gradient(135deg, rgba(244, 114, 182, 0.06), rgba(139, 92, 246, 0.04));
  border: 1px dashed rgba(244, 114, 182, 0.3);
  transition: all $transition-fast;
  cursor: default;

  &:hover {
    border-color: rgba(244, 114, 182, 0.5);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(244, 114, 182, 0.1);
  }

  &__title {
    font-size: $font-size-sm;
    font-weight: 500;
    margin-bottom: $spacing-xs;
    line-height: 1.5;
  }

  &__category {
    display: inline-block;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    background: rgba(244, 114, 182, 0.1);
    color: #F472B6;
    margin-bottom: $spacing-xs;
  }

  &__date {
    font-size: $font-size-xs;
    color: $text-muted;
  }
}

// 共用
.section-card {
  @include glass-card;
  padding: $spacing-lg;

  @media (max-width: $breakpoint-sm) { padding: $spacing-md; }

  h3 { font-size: $font-size-md; margin-bottom: $spacing-md; }

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $spacing-md;
    gap: $spacing-sm;
    h3 { margin-bottom: 0; white-space: nowrap; }

    @media (max-width: $breakpoint-sm) {
      flex-wrap: wrap;
    }
  }
}

.empty-state {
  text-align: center;
  padding: $spacing-lg;
  color: $text-secondary;
  &__icon { font-size: 36px; display: block; margin-bottom: $spacing-sm; }
  p { font-size: $font-size-sm; }
}

.loading {
  text-align: center;
  padding: $spacing-xxl;
  color: $text-secondary;

  &--sm { padding: $spacing-lg; }

  &__spinner {
    width: 40px; height: 40px;
    border: 3px solid $border-color;
    border-top-color: #EC4899;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto $spacing-md;

    &--sm { width: 24px; height: 24px; border-width: 2px; }
  }
}

.error-card {
  @include glass-card;
  padding: $spacing-xl;
  text-align: center;
  color: $danger-color;
}

.btn {
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  font-weight: 500;
  cursor: pointer;
  transition: all $transition-fast;
  border: none;

  &--primary {
    background: linear-gradient(135deg, #EC4899, #8B5CF6);
    color: white;
    &:hover { opacity: 0.9; transform: translateY(-1px); }
  }

  &--ghost {
    background: transparent;
    color: $text-secondary;
    &:hover { color: #EC4899; }
  }

  &--sm { padding: 4px 12px; font-size: $font-size-xs; }

  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

// 每日欢迎弹窗
.welcome-overlay {
  position: fixed;
  inset: 0;
  z-index: 300;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: $spacing-lg;
}

.welcome-card {
  background: white;
  border-radius: 20px;
  padding: $spacing-xl $spacing-xxl;
  text-align: center;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  max-width: 360px;
  animation: welcome-pop 0.5s ease;

  &__emoji {
    font-size: 48px;
    display: block;
    margin-bottom: $spacing-md;
  }

  &__text {
    font-size: $font-size-md;
    color: $text-primary;
    line-height: 1.8;
    font-weight: 500;
    margin-bottom: $spacing-lg;
  }

  &__close {
    background: linear-gradient(135deg, #EC4899, #8B5CF6);
    color: white;
    border: none;
    padding: $spacing-sm $spacing-xl;
    border-radius: 24px;
    font-size: $font-size-sm;
    font-weight: 600;
    cursor: pointer;
    transition: all $transition-fast;

    &:hover { opacity: 0.9; transform: scale(1.05); }
  }
}

@keyframes welcome-pop {
  0% { transform: scale(0.8); opacity: 0; }
  100% { transform: scale(1); opacity: 1; }
}

.welcome-fade-enter-active { transition: opacity 0.3s ease; }
.welcome-fade-leave-active { transition: opacity 0.5s ease; }
.welcome-fade-enter-from, .welcome-fade-leave-to { opacity: 0; }

// 详情弹窗
.detail-overlay {
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

.detail-modal {
  @include glass-card;
  width: 100%;
  max-width: 520px;
  max-height: 85vh;
  overflow-y: auto;
  animation: detail-slide-up 0.3s ease;

  @media (max-width: $breakpoint-sm) {
    max-width: 100%;
    max-height: 90vh;
    border-radius: 16px 16px 0 0;
  }

  &--ask {
    max-width: 600px;
  }

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: $spacing-md $spacing-lg;
    border-bottom: 1px solid rgba(0,0,0,0.06);

    h3 { font-size: $font-size-md; font-weight: 600; margin: 0; }
  }

  &__body {
    padding: $spacing-lg;
  }

  &__title {
    font-size: $font-size-md;
    font-weight: 600;
    line-height: 1.6;
    margin-bottom: $spacing-md;
    word-break: break-word;
  }

  &__tags {
    display: flex;
    gap: $spacing-xs;
    flex-wrap: wrap;
    margin-bottom: $spacing-md;
  }

  &__tag {
    font-size: $font-size-xs;
    padding: 2px 10px;
    border-radius: 12px;
    background: rgba(0,0,0,0.04);
    white-space: nowrap;

    &--category {
      background: rgba(139, 92, 246, 0.1);
      color: #8B5CF6;
    }

    &--answered {
      background: linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(6, 182, 212, 0.1));
      color: #0369A1;
      font-weight: 600;
      border: 1px solid rgba(59, 130, 246, 0.2);
    }
  }

  &__section {
    margin-bottom: $spacing-md;
    padding-bottom: $spacing-md;
    border-bottom: 1px solid rgba(0,0,0,0.06);

    &:last-of-type { border-bottom: none; }

    &--highlight {
      background: rgba(236, 72, 153, 0.04);
      padding: $spacing-md;
      border-radius: $border-radius-sm;
      border-bottom: none;
      margin-bottom: $spacing-sm;
    }

    &--ai {
      background: rgba(139, 92, 246, 0.04);
      padding: $spacing-md;
      border-radius: $border-radius-sm;
      border-bottom: none;
      margin-bottom: $spacing-sm;
    }

    &--answer {
      background: rgba(59, 130, 246, 0.04);
      padding: $spacing-md;
      border-radius: $border-radius-sm;
      border-bottom: none;
      margin-bottom: $spacing-sm;
    }

    &--inspiration {
      background: linear-gradient(135deg, rgba(244, 114, 182, 0.06), rgba(139, 92, 246, 0.04));
      padding: $spacing-md;
      border-radius: $border-radius-sm;
      border: 1px dashed rgba(244, 114, 182, 0.3);
      border-bottom: none;
      margin-bottom: $spacing-sm;
    }
  }

  &__section-label {
    font-size: $font-size-sm;
    font-weight: 700;
    color: #1F2937;
    margin-bottom: $spacing-xs;

    &--toggle {
      display: inline-flex; align-items: center; gap: 6px;
      border: none; background: transparent; cursor: pointer; padding: 4px 0;
      span { color: $text-muted; font-size: 11px; }
      &:hover { color: $primary-color; }
    }
  }

  &__note-edit {
    border: none; background: transparent; cursor: pointer;
    color: $text-muted; font-size: 12px; padding: 0 4px;
    &:hover { color: $primary-color; }
  }

  .detail-comment-edit {
    flex: 1; min-width: 0; padding: 4px 8px;
    border: 1px solid $primary-color; border-radius: 6px;
    font-size: 12px; font-family: inherit;
  }

  &__section-value {
    font-size: $font-size-sm;
    line-height: 1.6;
    color: $text-primary;
    white-space: pre-wrap;

    &--answer { color: #1e40af; }
    &--inspiration { color: #be185d; }
  }

  &__children {
    display: flex;
    flex-direction: column;
    gap: $spacing-xs;
  }

  &__child {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    padding: $spacing-xs $spacing-sm;
    border-radius: $border-radius-sm;
    background: rgba(255,255,255,0.6);

    &--done {
      opacity: 0.5;
      .detail-modal__child-title { text-decoration: line-through; }
    }
  }

  &__child-title { flex: 1; font-size: $font-size-sm; cursor: pointer; }
  &__child-flag { display: inline-flex; flex-shrink: 0; }
  &__child-urg {
    font-size: 11px;
    border: 1px solid $border-color;
    border-radius: 6px;
    background: #fff;
    color: $text-secondary;
    padding: 1px 4px;
  }
  &__child-status { font-size: 10px; white-space: nowrap; }

  &__notes {
    margin-top: $spacing-md;
    padding-top: $spacing-md;
    border-top: 1px solid rgba(0,0,0,0.06);
  }

  &__notes-title {
    font-size: $font-size-sm;
    color: #1F2937;
    margin-bottom: $spacing-sm;
    font-weight: 700;
  }

  &__notes-list {
    display: flex;
    flex-direction: column;
    gap: $spacing-xs;
  }

  &__note-item {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: $spacing-sm;
    padding: $spacing-xs $spacing-sm;
    border-radius: $border-radius-sm;
    background: rgba(16, 185, 129, 0.06);
    border-left: 2px solid rgba(16, 185, 129, 0.3);
  }

  &__note-content {
    font-size: $font-size-sm;
    color: $text-primary;
    font-weight: 600;
    flex: 1;
    word-break: break-word;
    white-space: pre-wrap;  // 保留换行符
  }

  &__note-time {
    font-size: 10px;
    color: $text-muted;
    white-space: nowrap;
    flex-shrink: 0;
  }

  &__comments {
    margin-bottom: $spacing-md;
  }

  &__note-del {
    background: none;
    border: none;
    color: $text-muted;
    cursor: pointer;
    padding: 0 2px;
    flex-shrink: 0;
    font-size: 12px;
    &:hover { color: $danger-color; }
  }

  &__comment-input {
    display: flex;
    gap: $spacing-sm;
    align-items: flex-end;
    margin-top: $spacing-xs;
  }

  &__comment-textarea {
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

  &__meta {
    font-size: $font-size-sm;
    color: $text-secondary;
    margin-top: $spacing-md;
    &-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: $spacing-sm;
    }
    padding-top: $spacing-md;
    border-top: 1px solid rgba(0,0,0,0.06);
  }

  &__meta-label {
    font-size: $font-size-xs;
    color: #1F2937;
    font-weight: 700;
    margin-right: $spacing-xs;
  }

  &__actions {
    display: flex;
    gap: $spacing-md;
    justify-content: flex-end;
    padding: $spacing-md $spacing-lg;
    border-top: 1px solid rgba(0,0,0,0.06);
  }
}

// header actions
.todo-dashboard__header-actions {
  display: flex;
  gap: $spacing-sm;
  align-items: center;
}

// 提问按钮
.btn--ask {
  background: linear-gradient(135deg, #3B82F6, #06B6D4);
  color: white;
  &:hover { opacity: 0.9; transform: translateY(-1px); }
}

// 日历按钮
.btn--calendar {
  background: linear-gradient(135deg, #10B981, #06B6D4);
  color: white;
  white-space: nowrap;
  &:hover { opacity: 0.9; transform: translateY(-1px); }
}

// AI 扫描按钮
.btn--scan {
  background: linear-gradient(135deg, #8B5CF6, #EC4899);
  color: white;
  white-space: nowrap;
  &:hover { opacity: 0.9; transform: translateY(-1px); }
  &:disabled { opacity: 0.6; cursor: not-allowed; }
}

// AI 扫描面板
.ai-scan-panel {
  .scan-summary {
    padding: $spacing-md;
    background: rgba(139, 92, 246, 0.05);
    border-radius: $border-radius-sm;
    margin-bottom: $spacing-md;
    p { margin: 0 0 $spacing-sm 0; line-height: 1.6; color: $text-primary; }
  }
  .scan-stats {
    display: flex; gap: $spacing-md; font-size: 13px; color: $text-secondary;
    span { background: rgba(0,0,0,0.04); padding: 2px 8px; border-radius: 4px; }
  }
  .scan-items { display: flex; flex-direction: column; gap: $spacing-sm; }
  .scan-item {
    padding: $spacing-md;
    background: rgba(0,0,0,0.02);
    border-radius: $border-radius-sm;
    border-left: 3px solid #ddd;
    transition: all 0.2s;
    &--applied { opacity: 0.5; }
    &__header { display: flex; align-items: center; gap: $spacing-sm; margin-bottom: 4px; }
    &__badge { font-size: 13px; font-weight: 600; white-space: nowrap; }
    &__title { font-size: 14px; font-weight: 500; color: $text-primary; }
    &__reason { font-size: 13px; color: $text-secondary; margin-bottom: 4px; }
    &__suggestion {
      font-size: 13px; color: #4B5563;
      background: rgba(59, 130, 246, 0.05);
      padding: 6px 10px; border-radius: 4px; margin-bottom: 6px; line-height: 1.5;
    }
    &__actions { display: flex; gap: $spacing-xs; }
    &__applied { font-size: 13px; color: #10B981; }
  }
}

// 今日计划置顶样式
.today-plan--top {
  margin-bottom: $spacing-lg;
  background: linear-gradient(135deg, rgba(236, 72, 153, 0.03), rgba(139, 92, 246, 0.03));
  border: 1px solid rgba(236, 72, 153, 0.12);
}

// 耗时标签
.today-item__time {
  font-size: 10px;
  padding: 0 4px;
  border-radius: 4px;
  background: rgba(59, 130, 246, 0.1);
  color: #3B82F6;
  white-space: nowrap;

  &--actual {
    background: rgba(16, 185, 129, 0.1);
    color: #10B981;
  }
}

// 完成记录耗时弹窗
.detail-modal--complete {
  max-width: 420px;
}

.complete-modal {
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

    &:focus {
      outline: none;
      border-color: #EC4899;
      box-shadow: 0 0 0 3px rgba(236, 72, 153, 0.1);
    }
  }

  &__hint {
    font-size: $font-size-xs;
    color: $text-muted;
    margin-top: $spacing-sm;
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
    white-space: pre-wrap;  // 保留换行符
  }

  &__note-time {
    font-size: 10px;
    color: $text-muted;
    white-space: nowrap;
    flex-shrink: 0;
  }
}

// 提问弹窗
.ask-input {
  display: flex;
  gap: $spacing-sm;
  align-items: flex-end;
  margin-bottom: $spacing-md;

  &__textarea {
    flex: 1;
    border: 2px solid $border-color;
    border-radius: $border-radius-md;
    padding: $spacing-sm $spacing-md;
    font-size: $font-size-sm;
    font-family: inherit;
    resize: vertical;
    min-height: 60px;
    background: rgba(255,255,255,0.6);
    transition: border-color $transition-fast;
    line-height: 1.6;

    &:focus {
      outline: none;
      border-color: #3B82F6;
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }

    &::placeholder { color: $text-muted; }
    &:disabled { opacity: 0.5; }
  }
}

.ask-loading {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-md;
  color: $text-secondary;
  font-size: $font-size-sm;
}

.ask-result {
  &__answer {
    @include glass-card;
    padding: $spacing-md;
    margin-bottom: $spacing-md;
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.05), rgba(6, 182, 212, 0.05));
    border: 1px solid rgba(59, 130, 246, 0.15);

    p {
      font-size: $font-size-sm;
      line-height: 1.8;
      color: $text-primary;
      white-space: pre-wrap;
      margin: 0;
    }
  }

  &__label {
    font-size: $font-size-xs;
    font-weight: 600;
    color: $text-secondary;
    margin-bottom: $spacing-sm;
  }

  &__todo-list {
    display: flex;
    flex-direction: column;
    gap: $spacing-xs;
  }
}

.ask-todo-card {
  @include glass-card;
  display: flex;
  align-items: flex-start;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-md;
  transition: all $transition-fast;

  &:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }

  &--done {
    opacity: 0.6;
    .ask-todo-card__title { text-decoration: line-through; color: $text-muted; }
  }

  &__content {
    flex: 1;
    cursor: pointer;
    min-width: 0;
  }

  &__title {
    font-size: $font-size-sm;
    font-weight: 500;
    display: block;
    word-break: break-word;
    line-height: 1.5;
  }

  &__info {
    display: flex;
    gap: $spacing-sm;
    margin-top: 2px;
    font-size: 10px;
    flex-wrap: wrap;
  }

  &__category {
    padding: 0 4px;
    border-radius: 4px;
    background: rgba(139, 92, 246, 0.1);
    color: #8B5CF6;
  }
}

@keyframes detail-slide-up {
  0% { transform: translateY(20px); opacity: 0; }
  100% { transform: translateY(0); opacity: 1; }
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
  transition: all $transition-fast;
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
.detail-modal--create {
  max-width: 480px;
}

.create-form {
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

  &__input {
    width: 100%;
    padding: $spacing-sm $spacing-md;
    border: 2px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-sm;
    font-family: inherit;
    background: rgba(255, 255, 255, 0.6);
    transition: border-color $transition-fast;

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

.detail-modal__collapse {
  margin-bottom: $spacing-sm;
}
.detail-modal__collapse-toggle {
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
.detail-modal__add-child {
  display: flex; align-items: center; gap: 8px; margin-top: 8px;
}
.detail-modal__add-child-input {
  flex: 1; border: 1px dashed $border-color; border-radius: 8px; padding: 6px 12px;
  font-size: 13px; font-family: inherit; background: transparent; box-sizing: border-box;
  &:focus { outline: none; border-color: $primary-color; border-style: solid; }
}
</style>
