<script setup lang="ts">
import { ref, computed, onMounted, watch, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { TODO_API_BASE, TIME_API_BASE } from '@/config'
import ChildProgressBadge from '@/components/todo/ChildProgressBadge.vue'
import TaskCreateExtras from '@/components/todo/TaskCreateExtras.vue'
import { isCoreActive } from '@/utils/corePeriod'

// 去除 markdown 格式符号（**加粗**等）
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

const route = useRoute()

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
  deferred_until: string | null
  completed_at: string | null
  completion_note: string | null
  completion_notes: Array<{ content: string; timestamp: string }> | null
  created_at: string
  updated_at: string
  // 核心任务标记（后端按周期过滤过期，前端用 isCoreActive 判断当前生效）
  core_scope?: 'week' | 'month' | 'year' | null
  core_period_key?: string | null
  // 子任务完成统计（后端聚合返回）
  child_total?: number
  child_done?: number
}

const items = ref<TodoItem[]>([])
const total = ref(0)
const loading = ref(true)
const page = ref(0)
const limit = 20

// 折叠展开
const expandedItems = ref<Set<number>>(new Set())

// 筛选条件
const filterStatus = ref('')
const filterQuadrant = ref<number | null>(null)
const filterCategory = ref('')
const filterKeyword = ref('')
const filterCompletion = ref('')
const sortBy = ref('smart')

// 编辑模态框
const editingItem = ref<TodoItem | null>(null)
const showEditModal = ref(false)
const showCreateModal = ref(false)
const isEditing = ref(false) // 详情弹窗中是否在编辑模式
const createMode = ref<'manual' | 'ai'>('manual')
const newTitle = ref('')
const newDescription = ref('')
const newQuadrant = ref(4)
const newCategory = ref('')
const newDueDate = ref('')
const newSubtasks = ref<string[]>([])
const newIsWork = ref(false)
const newMarkDone = ref(false)
const newAiEval = ref(true)
const addNewSubtask = () => { newSubtasks.value.push(''); nextTick(() => { const els = document.querySelectorAll('.form-sub-input'); (els[els.length-1] as HTMLInputElement)?.focus() }) }
const removeNewSubtask = (i: number) => { newSubtasks.value.splice(i, 1) }

// AI 分析相关
const aiInput = ref('')
const aiAnalyzing = ref(false)
const aiResult = ref<{
  title: string
  quadrant: number
  category: string
  ai_evaluation: string
  ai_category: string
  original_text: string
} | null>(null)

// 子任务
const childItems = ref<TodoItem[]>([])
// 记录子任务原始快照，用于 saveEdit 时判断哪些被修改
const childItemsSnapshot = ref<Record<number, { title: string; status: string }>>({})
const detailExpanded = ref(false)
const descExpanded = ref(false)
const newChildTitle = ref('')

// 详情区块折叠（创建信息默认折叠；支持一键折叠/展开）
const metaExpanded = ref(false)
const childrenExpanded = ref(true)
const commentsExpanded = ref(true)
const lessonsExpanded = ref(true)
const detailStack = ref<TodoItem[]>([])
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
  if (!content || !editingItem.value) return
  if (kind === 'lesson') lessonSaving.value = true
  else commentSaving.value = true
  try {
    const res = await fetch(`${TODO_API_BASE}/${editingItem.value.id}/comments`, {
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

async function deleteComment(commentId: number) {
  if (!confirm('确定删除这条想法？')) return
  try {
    const res = await fetch(`${TODO_API_BASE}/comments/${commentId}`, { method: 'DELETE' })
    if (res.ok) comments.value = comments.value.filter(c => c.id !== commentId)
  } catch { /* */ }
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

const addChildTask = async () => {
  if (!newChildTitle.value.trim() || !editingItem.value) return
  try {
    const res = await fetch(`${TODO_API_BASE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newChildTitle.value.trim(), status: editingItem.value.status, source: 'manual', parent_id: editingItem.value.id }),
    })
    if (res.ok) {
      const child = await res.json()
      childItems.value.push(child)
      childItems.value.sort((a, b) => (b.urgency || 0) - (a.urgency || 0))
      childItemsSnapshot.value[child.id] = { title: child.title, status: child.status }
      // 同步进列表数据：本页进度由列表里的子任务实时算出，
      // 加进去后父任务的进度徽章立刻反映新增的子任务
      if (!items.value.some(i => i.id === child.id)) items.value.push(child)
      newChildTitle.value = ''
    }
  } catch { /* */ }
}

const categoryLabels: Record<string, string> = {
  work: '工作/项目', learning: '学习/成长', life: '生活/事务',
  health: '健康/运动', social: '社交/关系', finance: '财务/投资', creative: '创意/探索',
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

const quadrantLabels: Record<number, { label: string; icon: string; color: string; bg: string }> = {
  1: { label: '重要紧急', icon: 'Flag', color: '#EF4444', bg: 'rgba(239, 68, 68, 0.12)' },
  2: { label: '重要不紧急', icon: 'Flag', color: '#3B82F6', bg: 'rgba(59, 130, 246, 0.12)' },
  3: { label: '紧急不重要', icon: 'Flag', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.12)' },
  4: { label: '不重要不紧急', icon: 'Remove', color: '#94A3B8', bg: 'rgba(148, 163, 184, 0.14)' },
}

const fetchItems = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (filterStatus.value) params.set('status', filterStatus.value)
    if (filterQuadrant.value) params.set('quadrant', String(filterQuadrant.value))
    if (filterCategory.value) params.set('category', filterCategory.value)
    if (filterKeyword.value) params.set('keyword', filterKeyword.value)
    if (filterCompletion.value) params.set('completion', filterCompletion.value)
    params.set('sort_by', sortBy.value)
    params.set('skip', String(page.value * limit))
    params.set('limit', String(limit))
    params.set('include_children', 'true')  // 全部待办需要子任务做展开

    const res = await fetch(`${TODO_API_BASE}?${params}`)
    if (!res.ok) throw new Error('加载失败')
    const data = await res.json()
    items.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    items.value = []
  } finally {
    loading.value = false
  }
}

const toggleComplete = async (item: TodoItem) => {
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
  } catch (e) { /* */ }
}

// 子任务勾掉时同样弹出完成框；已完成再点则直接改回未完成
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
      // 同步详情弹窗里的子任务状态（如果同一对象引用）
      const idx = childItems.value.findIndex(c => c.id === child.id)
      if (idx >= 0) {
        childItems.value[idx] = { ...childItems.value[idx], status: updated.status, completed_at: updated.completed_at }
      }
      // 同步列表里的同一条，父任务进度才能实时变化
      const inList = items.value.find(i => i.id === child.id)
      if (inList) {
        inList.status = updated.status
        inList.completed_at = updated.completed_at
      }
      // 父任务统计同步（本页统计来自列表，以上同步已覆盖；这里兜住后端字段）
      const nowCompleted = updated.status === 'completed'
      const parent = child.parent_id ? items.value.find(i => i.id === child.parent_id) : null
      if (parent && nowCompleted !== wasCompleted) {
        parent.child_done = Math.max(0, (parent.child_done || 0) + (nowCompleted ? 1 : -1))
      }
    }
  } catch (e) { /* */ }
}

// 完成任务弹窗
const showCompleteModal = ref(false)
const completingItem = ref<TodoItem | null>(null)
const actualMinutes = ref<number | null>(null)
const completionNote = ref('')
const existingNotes = ref<Array<{ content: string; timestamp: string }>>([])
const timeLogMinutes = ref<number | null>(null) // TimeLog 累计时间

const openCompleteModal = async (item: TodoItem) => {
  completingItem.value = item
  actualMinutes.value = (item as any).estimated_minutes || null
  completionNote.value = ''
  existingNotes.value = (item as any).completion_notes || []
  timeLogMinutes.value = null

  // 自动查询 TimeLog 累计时间
  try {
    const res = await fetch(`${TIME_API_BASE}/total/${item.id}`)
    if (res.ok) {
      const data = await res.json()
      if (data.total_minutes > 0) {
        timeLogMinutes.value = data.total_minutes
        actualMinutes.value = data.total_minutes
      }
    }
  } catch { /* */ }

  // 如果正在计时，先停止
  if (timerTodoId.value === item.id) {
    await stopTimer(item.id)
  }

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
      const idx = childItems.value.findIndex(c => c.id === completingItem.value!.id)
      if (idx >= 0) {
        childItems.value[idx] = {
          ...childItems.value[idx],
          status: updated.status,
          completed_at: updated.completed_at,
          completion_notes: updated.completion_notes,
          actual_minutes: updated.actual_minutes,
        }
      }
      fetchItems()
    }
  } catch { /* */ }
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
    if (res.ok) fetchItems()
  } catch { /* */ }
  showCompleteModal.value = false
  completingItem.value = null
  actualMinutes.value = null
  completionNote.value = ''
  existingNotes.value = []
}

const deleteItem = async (id: number) => {
  if (!confirm('确定删除？')) return
  try {
    await fetch(`${TODO_API_BASE}/${id}`, { method: 'DELETE' })
    fetchItems()
  } catch (e) { /* */ }
}

const deferItem = async (item: TodoItem) => {
  try {
    await fetch(`${TODO_API_BASE}/${item.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'deferred' }),
    })
    fetchItems()
  } catch (e) { /* */ }
}

const aiCategoryLabels: Record<string, { label: string; icon: string; color: string }> = {
  actionable: { label: '可执行', icon: 'Check', color: '#10B981' },
  answerable: { label: '直接解答', icon: 'Opportunity', color: '#3B82F6' },
  splittable: { label: '需拆分', icon: 'Sort', color: '#8B5CF6' },
  inspiration: { label: '灵感', icon: 'Star', color: '#F472B6' },
  questionable: { label: '需澄清', icon: 'QuestionFilled', color: '#F59E0B' },
  low_value: { label: '低价值', icon: 'Remove', color: '#94A3B8' },
}

// 输入框随内容自动撑开（上限 400px，超出后内部滚动）
const autoGrow = (e: Event) => {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 400) + 'px'
}

// 弹窗打开后让所有 textarea 按已有内容撑开
const growAllTextareas = () => {
  nextTick(() => {
    document.querySelectorAll<HTMLTextAreaElement>('.modal .form-textarea').forEach(el => {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 400) + 'px'
    })
  })
}

// 标记/取消核心任务（各周期最多 3 条，后端校验）
const toggleCore = async (scope: 'week' | 'month' | 'year') => {
  if (!editingItem.value) return
  const isActive = isCoreActive(editingItem.value) && editingItem.value.core_scope === scope
  try {
    const res = await fetch(`${TODO_API_BASE}/${editingItem.value.id}/core`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: isActive ? null : scope }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '设置失败')
    editingItem.value = { ...editingItem.value, core_scope: data.core_scope, core_period_key: data.core_period_key }
    fetchItems()
  } catch (e: any) {
    alert(e.message || '设置核心失败')
  }
}

const closeDetail = () => {
  showEditModal.value = false
  detailStack.value = []
}

const backToParent = () => {
  const parent = detailStack.value.pop()
  if (parent) openEdit(parent, true)
  else closeDetail()
}

const openEdit = async (item: TodoItem, fromStack = false) => {
  if (!fromStack && showEditModal.value && editingItem.value && editingItem.value.id !== item.id) {
    detailStack.value.push({ ...editingItem.value })
  }
  editingItem.value = { ...item }
  isEditing.value = false
  showEditModal.value = true
  growAllTextareas()
  // 加载评论（历史想法）
  newComment.value = ''
  loadComments(item.id)
  // 获取子任务（专用端点，不受列表分页影响）
  childItems.value = []
  childItemsSnapshot.value = {}
  try {
    const res = await fetch(`${TODO_API_BASE}/${item.id}/children`)
    if (res.ok) {
      childItems.value = await res.json()
      // 保存快照
      for (const c of childItems.value) {
        childItemsSnapshot.value[c.id] = { title: c.title, status: c.status }
      }
    }
  } catch (e) { /* */ }
}

const saveEdit = async () => {
  if (!editingItem.value) return
  try {
    // 保存父任务
    const res = await fetch(`${TODO_API_BASE}/${editingItem.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: editingItem.value.title,
        description: editingItem.value.description,
        quadrant: editingItem.value.quadrant,
        category: editingItem.value.category,
        status: editingItem.value.status,
        due_date: editingItem.value.due_date,
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

    showEditModal.value = false
    fetchItems()
  } catch (e) { /* */ }
}

const deleteChildItem = async (childId: number) => {
  if (!confirm('确定删除该子任务？')) return
  try {
    const res = await fetch(`${TODO_API_BASE}/${childId}`, { method: 'DELETE' })
    if (res.ok) {
      childItems.value = childItems.value.filter(c => c.id !== childId)
      delete childItemsSnapshot.value[childId]
    }
  } catch (e) { /* */ }
}

const createItem = async () => {
  if (!newTitle.value.trim()) return
  try {
    const subs = newSubtasks.value.map(s => s.trim()).filter(Boolean)
    const res = await fetch(`${TODO_API_BASE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: newTitle.value,
        description: newDescription.value,
        quadrant: newQuadrant.value,
        category: newIsWork.value ? 'work' : (newCategory.value || null),
        due_date: newDueDate.value || null,
        status: newMarkDone.value ? 'completed' : 'planned',
        skip_ai_eval: !newAiEval.value,
        ...(subs.length > 0 ? { sub_tasks: subs } : {}),
      }),
    })
    if (res.ok) {
      showCreateModal.value = false
      newTitle.value = ''
      newDescription.value = ''
      newQuadrant.value = 4
      newCategory.value = ''
      newDueDate.value = ''
      newSubtasks.value = []
      newIsWork.value = false
      newMarkDone.value = false
      const aiEvalRequested = newAiEval.value
      newAiEval.value = true
      fetchItems()
      // AI 评估是异步的（v4-pro 约 12-20s），延迟刷新让列表按评估后的重要度重新排列
      if (aiEvalRequested) setTimeout(() => fetchItems(), 20000)
    }
  } catch (e) { /* */ }
}

const analyzeWithAI = async () => {
  if (!aiInput.value.trim()) return
  aiAnalyzing.value = true
  aiResult.value = null
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 90000) // 90秒前端超时
  try {
    const res = await fetch(`${TODO_API_BASE}/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: aiInput.value }),
      signal: controller.signal,
    })
    clearTimeout(timeoutId)
    if (!res.ok) {
      const errText = await res.text().catch(() => '')
      throw new Error(errText || 'AI 分析失败')
    }
    const data = await res.json()
    // 取第一条结果
    const items = data.items || []
    if (items.length > 0) {
      const first = items[0]
      aiResult.value = {
        title: first.title || aiInput.value,
        quadrant: first.quadrant || 4,
        category: first.category || '',
        ai_evaluation: first.ai_evaluation || '',
        ai_category: first.ai_category || 'actionable',
        original_text: aiInput.value,
      }
    } else {
      aiResult.value = {
        title: aiInput.value,
        quadrant: 4,
        category: '',
        ai_evaluation: '',
        ai_category: 'actionable',
        original_text: aiInput.value,
      }
    }
  } catch (e: any) {
    clearTimeout(timeoutId)
    if (e.name === 'AbortError') {
      alert('AI 分析超时（90秒），请稍后重试')
    } else {
      alert('AI 分析失败：' + (e.message || '请重试'))
    }
  } finally {
    aiAnalyzing.value = false
  }
}

const saveAiResult = async () => {
  if (!aiResult.value) return
  try {
    const res = await fetch(`${TODO_API_BASE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: aiResult.value.title,
        quadrant: aiResult.value.quadrant,
        category: aiResult.value.category || null,
        ai_evaluation: aiResult.value.ai_evaluation,
        ai_category: aiResult.value.ai_category,
        original_text: aiResult.value.original_text,
        status: 'evaluated',
        source: 'ai_quick',
      }),
    })
    if (res.ok) {
      showCreateModal.value = false
      aiInput.value = ''
      aiResult.value = null
      createMode.value = 'manual'
      fetchItems()
    }
  } catch (e) { /* */ }
}

const daysSince = (dateStr: string) => {
  const diff = Date.now() - new Date(dateStr).getTime()
  return Math.floor(diff / (1000 * 60 * 60 * 24))
}

// 获取某个父任务的子任务
const getChildren = (parentId: number) => {
  return items.value.filter(i => i.parent_id === parentId)
}

// 判断是否有子任务
const hasChildren = (itemId: number) => {
  return items.value.some(i => i.parent_id === itemId)
}

// 子任务进度：父任务未展开时也能一眼看到完成比例
const childProgress = (parentId: number) => {
  const kids = getChildren(parentId)
  const total = kids.length
  const done = kids.filter(k => k.status === 'completed').length
  const percent = total > 0 ? Math.round((done / total) * 100) : 0
  return { done, total, percent }
}

// 卡片左侧色条
const progressCardClass = (parentId: number) => {
  if (!hasChildren(parentId)) return ''
  const { percent } = childProgress(parentId)
  if (percent >= 100) return 'todo-card--progress-full'
  if (percent > 0) return 'todo-card--progress-partial'
  return 'todo-card--progress-none'
}

// 是否为子任务（有 parent_id）
const isChild = (item: TodoItem) => !!item.parent_id

// 展开/折叠
const toggleExpand = (itemId: number) => {
  if (expandedItems.value.has(itemId)) {
    expandedItems.value.delete(itemId)
  } else {
    expandedItems.value.add(itemId)
  }
}

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

// 从 URL query 初始化筛选
onMounted(() => {
  const q = route.query.quadrant
  if (q) filterQuadrant.value = Number(q)
  fetchItems()
  fetchCurrentTimer()
})

onUnmounted(() => {
  stopTimerTick()
})

watch([filterStatus, filterQuadrant, filterCategory, filterCompletion, sortBy], () => {
  page.value = 0
  fetchItems()
})
</script>

<template>
  <div class="todo-list">
    <div class="todo-list__header">
      <div>
        <h1><Document class="ep-icon" /> 全部待办</h1>
        <p class="todo-list__subtitle">共 {{ total }} 条待办</p>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <select v-model="filterStatus" class="filter-select">
        <option value="">全部状态</option>
        <option v-for="(cfg, key) in statusLabels" :key="key" :value="key">{{ cfg.label }}</option>
      </select>

      <div class="filter-quadrants">
        <button
          v-for="q in [1,2,3,4]"
          :key="q"
          class="filter-quadrant-btn"
          :class="{ 'filter-quadrant-btn--active': filterQuadrant === q }"
          :style="{ borderColor: quadrantLabels[q].color, color: quadrantLabels[q].color }"
          @click="filterQuadrant = filterQuadrant === q ? null : q"
        >
          <component :is="quadrantLabels[q].icon" class="ep-icon" />
        </button>
      </div>

      <select v-model="filterCategory" class="filter-select">
        <option value="">全部分类</option>
        <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
      </select>

      <select v-model="filterCompletion" class="filter-select">
        <option value="">全部完成情况</option>
        <option value="undone">未完成</option>
        <option value="done">已完成/已取消</option>
      </select>

      <input
        v-model="filterKeyword"
        class="filter-input"
        placeholder="搜索..."
        @keyup.enter="fetchItems"
      />

      <select v-model="sortBy" class="filter-select">
        <option value="smart">智能排序</option>
        <option value="created_at">按时间</option>
        <option value="urgency">按紧急度</option>
        <option value="importance">按重要度</option>
      </select>
    </div>

    <!-- 待办列表 -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
    </div>

    <div v-else-if="items.length === 0" class="empty-state">
      <span class="empty-state__icon">📭</span>
      <p>暂无待办</p>
      <button class="btn btn--primary" @click="showCreateModal = true">创建待办</button>
    </div>

    <div v-else class="items-list">
      <template v-for="item in items" :key="item.id">
        <!-- 跳过子任务（它们在父任务展开时显示） -->
        <template v-if="!isChild(item)">
          <div
            class="todo-card"
            :class="[{
              'todo-card--done': item.status === 'completed',
              'todo-card--deferred': item.status === 'deferred',
              'todo-card--parent': hasChildren(item.id),
              'todo-card--timing': timerTodoId === item.id,
            }, progressCardClass(item.id)]"
          >
            <label class="checkbox" @click.stop="toggleComplete(item)">
              <input type="checkbox" :checked="item.status === 'completed'" @change.prevent />
              <span class="checkbox__mark"></span>
            </label>

            <div class="todo-card__content" @click="openEdit(item)">
              <div class="todo-card__title-row">
                <span
                  v-if="isCoreActive(item)"
                  class="todo-card__core-star"
                  :class="{ 'todo-card__core-star--month': item.core_scope === 'month' }"
                  :title="item.core_scope === 'week' ? '本周核心任务' : '本月核心任务'"
                ><Star class="ep-icon" /></span>
                <span class="todo-card__title" :style="{ color: quadrantLabels[item.quadrant]?.color }">{{ stripMarkdown(item.title) }}</span>
                <ChildProgressBadge
                  v-if="hasChildren(item.id)"
                  :total="childProgress(item.id).total"
                  :done="childProgress(item.id).done"
                />
              </div>
              <div class="todo-card__bottom-row">
                <div class="todo-card__tags">
                  <span class="todo-card__quadrant-tag" :style="{ color: quadrantLabels[item.quadrant]?.color, background: quadrantLabels[item.quadrant]?.bg }">
                    <component :is="quadrantLabels[item.quadrant]?.icon" class="ep-icon" /> {{ quadrantLabels[item.quadrant]?.label }}
                  </span>
                  <span v-if="item.category" class="todo-card__category-tag">
                    {{ categoryLabels[item.category] || item.category }}
                  </span>
                  <span class="todo-card__status-tag" :style="{ color: statusLabels[item.status]?.color }">
                    {{ statusLabels[item.status]?.label || item.status }}
                  </span>
                  <span v-if="item.ai_category" class="todo-card__ai-tag" :style="{ color: aiCategoryLabels[item.ai_category]?.color }">
                    <component :is="aiCategoryLabels[item.ai_category]?.icon" class="ep-icon" />
                  </span>
                </div>
                <div class="todo-card__actions">
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
                  <!-- 折叠/展开按钮 -->
                  <button
                    v-if="hasChildren(item.id)"
                    class="expand-btn"
                    @click.stop="toggleExpand(item.id)"
                    :title="expandedItems.has(item.id) ? '收起子任务' : '展开子任务'"
                  >
                    <span class="expand-btn__icon" :class="{ 'expand-btn__icon--open': expandedItems.has(item.id) }">▶</span>
                    <span class="expand-btn__count">{{ getChildren(item.id).length }}</span>
                  </button>
                  <button class="action-btn" title="推迟" @click.stop="deferItem(item)" v-if="item.status !== 'completed' && item.status !== 'deferred'">⏸️</button>
                  <button class="action-btn action-btn--danger" title="删除" @click.stop="deleteItem(item.id)"><Delete class="ep-icon" />️</button>
                </div>
              </div>
              <div class="todo-card__meta">
                <span v-if="item.due_date">截止: {{ item.due_date }}</span>
                <span v-if="item.status !== 'completed'">等待 {{ daysSince(item.created_at) }} 天</span>
                <span v-if="item.completed_at">完成于 {{ item.completed_at.split('T')[0] }}</span>
              </div>
            </div>
          </div>

          <!-- 子任务列表（展开时显示） -->
          <div v-if="hasChildren(item.id) && expandedItems.has(item.id)" class="children-list">
            <div
              v-for="child in getChildren(item.id)"
              :key="child.id"
              class="todo-card todo-card--child"
              :class="{ 'todo-card--done': child.status === 'completed' }"
            >
              <label class="checkbox" @click.stop="toggleChildComplete(child)">
                <input type="checkbox" :checked="child.status === 'completed'" @change.prevent />
                <span class="checkbox__mark"></span>
              </label>
              <div class="todo-card__content" @click="openEdit(child)">
                <div class="todo-card__title-row">
                  <span
                    class="todo-card__quadrant-icon"
                    :style="{ color: quadrantLabels[child.quadrant]?.color }"
                    :title="quadrantLabels[child.quadrant]?.label"
                  ><component :is="quadrantLabels[child.quadrant]?.icon" class="ep-icon" /></span>
                  <span class="todo-card__title" :style="{ color: quadrantLabels[child.quadrant]?.color }">{{ stripMarkdown(child.title) }}</span>
                </div>
                <div class="todo-card__bottom-row">
                  <span class="todo-card__status-tag" :style="{ color: statusLabels[child.status]?.color }">
                    {{ statusLabels[child.status]?.label }}
                  </span>
                </div>
              </div>
              <div class="todo-card__actions">
                <button class="action-btn action-btn--danger" title="删除" @click="deleteItem(child.id)"><Delete class="ep-icon" />️</button>
              </div>
            </div>
          </div>
        </template>
      </template>
    </div>

    <!-- 分页 -->
    <div v-if="total > limit" class="pagination">
      <button class="btn btn--sm btn--ghost" :disabled="page === 0" @click="page--; fetchItems()">上一页</button>
      <span class="pagination__info">{{ page + 1 }} / {{ Math.ceil(total / limit) }}</span>
      <button class="btn btn--sm btn--ghost" :disabled="(page + 1) * limit >= total" @click="page++; fetchItems()">下一页</button>
    </div>

    <!-- 浮动新增按钮 -->
    <button class="fab" @click="showCreateModal = true" title="新增待办">+</button>

    <!-- 详情/编辑 Modal -->
    <div v-if="showEditModal && editingItem" class="modal-overlay" @click.self="closeDetail">
      <div class="modal modal--detail">
        <div class="modal__header">
          <h3>{{ isEditing ? '编辑待办' : '待办详情' }}</h3>
          <div class="modal__header-actions">
            <button v-if="detailStack.length" class="btn btn--sm btn--ghost" @click="backToParent">返回父任务</button>
            <button v-if="!isEditing" class="btn btn--sm btn--ghost" @click="toggleAllSections">{{ detailAllExpanded ? '一键折叠' : '一键展开' }}</button>
            <button v-if="!isEditing" class="btn btn--sm btn--ghost" @click="isEditing = true"><EditPen class="ep-icon" />️ 编辑</button>
            <button class="btn btn--sm btn--ghost" @click="closeDetail"><Close class="ep-icon" /></button>
          </div>
        </div>

        <!-- 详情视图 -->
        <template v-if="!isEditing">
          <div class="detail-section">
            <h4 class="detail-title">{{ editingItem.title }}</h4>
            <div class="detail-tags">
              <span class="detail-tag" :style="{ color: quadrantLabels[editingItem.quadrant]?.color, background: quadrantLabels[editingItem.quadrant]?.bg }">
                <component :is="quadrantLabels[editingItem.quadrant]?.icon" class="ep-icon" /> {{ quadrantLabels[editingItem.quadrant]?.label }}
              </span>
              <span v-if="editingItem.category" class="detail-tag detail-tag--category">
                {{ categoryLabels[editingItem.category] || editingItem.category }}
              </span>
              <span class="detail-tag" :style="{ color: statusLabels[editingItem.status]?.color }">
                {{ statusLabels[editingItem.status]?.label }}
              </span>
              <span v-if="editingItem.ai_category" class="detail-tag" :style="{ color: aiCategoryLabels[editingItem.ai_category]?.color }">
                <component :is="aiCategoryLabels[editingItem.ai_category]?.icon" class="ep-icon" /> {{ aiCategoryLabels[editingItem.ai_category]?.label }}
              </span>
            </div>
          </div>

          <!-- 核心任务标记 -->
          <div class="detail-core">
            <span class="detail-core__label"><Star class="ep-icon" /> 核心任务：</span>
            <button
              class="detail-core__btn detail-core__btn--week"
              :class="{ 'detail-core__btn--on': isCoreActive(editingItem) && editingItem.core_scope === 'week' }"
              @click="toggleCore('week')"
            >{{ isCoreActive(editingItem) && editingItem.core_scope === 'week' ? '★ 本周核心（点击取消）' : '设为本周核心' }}</button>
            <button
              class="detail-core__btn detail-core__btn--month"
              :class="{ 'detail-core__btn--on': isCoreActive(editingItem) && editingItem.core_scope === 'month' }"
              @click="toggleCore('month')"
            >{{ isCoreActive(editingItem) && editingItem.core_scope === 'month' ? '★ 本月核心（点击取消）' : '设为本月核心' }}</button>
            <button
              class="detail-core__btn detail-core__btn--year"
              :class="{ 'detail-core__btn--on': isCoreActive(editingItem) && editingItem.core_scope === 'year' }"
              @click="toggleCore('year')"
            >{{ isCoreActive(editingItem) && editingItem.core_scope === 'year' ? '★ 年度目标（点击取消）' : '设为年度目标' }}</button>
          </div>

          <!-- 原始输入 & AI 评估 (折叠) -->
          <div v-if="editingItem.original_text || editingItem.ai_evaluation" class="detail-collapse">
            <button class="detail-collapse__toggle" @click="detailExpanded = !detailExpanded">
              {{ detailExpanded ? '▼ 收起' : '▶ 原始输入 / AI 评估' }}
            </button>
            <template v-if="detailExpanded">
              <div v-if="editingItem.original_text" class="detail-section detail-section--highlight">
                <div class="detail-label"><EditPen class="ep-icon" /> 原始输入</div>
                <div class="detail-value">{{ editingItem.original_text }}</div>
              </div>
              <div v-if="editingItem.ai_evaluation" class="detail-section detail-section--ai">
                <div class="detail-label"><MagicStick class="ep-icon" /> AI 评估</div>
                <div class="detail-value">{{ editingItem.ai_evaluation }}</div>
              </div>
            </template>
          </div>

          <!-- AI 解答 -->
          <div v-if="editingItem.ai_answer && editingItem.ai_category !== 'inspiration'" class="detail-section detail-section--answer">
            <div class="detail-label"><Opportunity class="ep-icon" /> AI 解答</div>
            <div class="detail-value detail-value--answer">{{ editingItem.ai_answer }}</div>
          </div>

          <!-- 灵感点评 -->
          <div v-if="editingItem.ai_answer && editingItem.ai_category === 'inspiration'" class="detail-section detail-section--inspiration">
            <div class="detail-label"><Star class="ep-icon" /> 灵感点评</div>
            <div class="detail-value detail-value--inspiration">{{ editingItem.ai_answer }}</div>
          </div>

          <!-- 描述（默认折叠） -->
          <div v-if="editingItem.description" class="detail-collapse">
            <button class="detail-collapse__toggle" @click="descExpanded = !descExpanded">
              {{ descExpanded ? '▼ 收起描述' : '▶ 描述' }}
            </button>
            <div v-if="descExpanded" class="detail-section">
              <div class="detail-value">{{ editingItem.description }}</div>
            </div>
          </div>

          <!-- 子任务 -->
          <div class="detail-section">
            <button class="detail-label detail-label--toggle" @click="childrenExpanded = !childrenExpanded">
              <FolderOpened class="ep-icon" /> 子任务 ({{ childItems.length }}) <span>{{ childrenExpanded ? '▾' : '▸' }}</span>
            </button>
            <template v-if="childrenExpanded">
            <div v-if="childItems.length > 0" class="detail-children">
              <div v-for="child in childItems" :key="child.id" class="detail-child-item"
                :class="{ 'detail-child-item--done': child.status === 'completed' }">
                <label class="checkbox" @click.stop="toggleChildComplete(child)">
                  <input type="checkbox" :checked="child.status === 'completed'" @change.prevent />
                  <span class="checkbox__mark"></span>
                </label>
                <span class="detail-child-item__flag" :style="{ color: quadrantLabels[child.quadrant]?.color }" :title="quadrantLabels[child.quadrant]?.label">
                  <component :is="quadrantLabels[child.quadrant]?.icon" class="ep-icon" />
                </span>
                <span class="detail-child-item__title" @click.stop="openEdit(child)">{{ child.title }}</span>
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
          <div v-if="editingItem.completion_notes && editingItem.completion_notes.length > 0" class="detail-section detail-section--notes">
            <div class="detail-label"><EditPen class="ep-icon" /> 完成备注</div>
            <div class="detail-notes-list">
              <div v-for="(note, idx) in editingItem.completion_notes" :key="idx" class="detail-note-item">
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
                @keydown.enter.exact.prevent="addComment()"
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

          <!-- 创建信息（元信息，默认折叠） -->
          <div class="detail-section detail-section--meta">
            <button class="detail-label detail-label--toggle" @click="metaExpanded = !metaExpanded">
              创建信息 <span>{{ metaExpanded ? '▾' : '▸' }}</span>
            </button>
            <div v-show="metaExpanded" class="detail-meta-grid">
              <div><span class="detail-meta-label">紧急度</span> <span class="detail-meta-value">{{ editingItem.urgency }}/5</span></div>
              <div><span class="detail-meta-label">重要度</span> <span class="detail-meta-value">{{ editingItem.importance }}/5</span></div>
              <div v-if="editingItem.due_date"><span class="detail-meta-label">截止日期</span> <span class="detail-meta-value">{{ editingItem.due_date }}</span></div>
              <div><span class="detail-meta-label">来源</span> <span class="detail-meta-value">{{ editingItem.source }}</span></div>
              <div v-if="editingItem.estimated_minutes"><span class="detail-meta-label">预估时间</span> <span class="detail-meta-value">{{ editingItem.estimated_minutes }}分钟</span></div>
              <div v-if="editingItem.actual_minutes"><span class="detail-meta-label">实际用时</span> <span class="detail-meta-value">{{ editingItem.actual_minutes }}分钟</span></div>
              <div><span class="detail-meta-label">创建于</span> <span class="detail-meta-value">{{ editingItem.created_at?.split('T')[0] }}</span></div>
              <div v-if="editingItem.completed_at"><span class="detail-meta-label">完成于</span> <span class="detail-meta-value">{{ editingItem.completed_at?.split('T')[0] }}</span></div>
            </div>
          </div>
        </template>

        <!-- 编辑视图 -->
        <template v-else>
          <div class="form-group">
            <label>标题</label>
            <input v-model="editingItem.title" class="form-input" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="editingItem.description" class="form-textarea" rows="3" @input="autoGrow"></textarea>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>四象限</label>
              <select v-model="editingItem.quadrant" class="form-input">
                <option v-for="q in [1,2,3,4]" :key="q" :value="q">{{ quadrantLabels[q].label }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>分类</label>
              <select v-model="editingItem.category" class="form-input">
                <option value="">无</option>
                <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
              </select>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>状态</label>
              <select v-model="editingItem.status" class="form-input">
                <option v-for="(cfg, key) in statusLabels" :key="key" :value="key">{{ cfg.label }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>截止日期</label>
              <input v-model="editingItem.due_date" type="date" class="form-input" />
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
                <button class="action-btn action-btn--danger" title="删除子任务" @click="deleteChildItem(child.id)"><Delete class="ep-icon" />️</button>
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

    <!-- 新建 Modal -->
    <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
      <div class="modal">
        <h3>新建待办</h3>

        <!-- 模式切换 -->
        <div class="create-mode-toggle">
          <button
            class="create-mode-btn"
            :class="{ 'create-mode-btn--active': createMode === 'manual' }"
            @click="createMode = 'manual'"
          ><EditPen class="ep-icon" /> 手动填写</button>
          <button
            class="create-mode-btn"
            :class="{ 'create-mode-btn--active': createMode === 'ai' }"
            @click="createMode = 'ai'"
          ><MagicStick class="ep-icon" /> AI 帮我分析</button>
        </div>

        <!-- AI 模式 -->
        <template v-if="createMode === 'ai'">
          <div class="form-group">
            <label>输入你的想法（一句话即可，AI帮你分析分类）</label>
            <textarea
              v-model="aiInput"
              class="form-textarea"
              rows="3"
              placeholder="例如：我想学习Vue3、周末去健身房锻炼、下周要提交项目报告..."
              @input="autoGrow"
            ></textarea>
          </div>
          <div v-if="aiAnalyzing" class="ai-analyzing">
            <div class="loading__spinner loading__spinner--sm"></div>
            <span>AI 正在分析...</span>
          </div>
          <div v-if="aiResult" class="ai-result">
            <div class="ai-result__header"><MagicStick class="ep-icon" /> AI 分析结果</div>
            <div class="form-group">
              <label>标题</label>
              <input v-model="aiResult.title" class="form-input" />
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>四象限</label>
                <select v-model="aiResult.quadrant" class="form-input">
                  <option v-for="q in [1,2,3,4]" :key="q" :value="q">{{ quadrantLabels[q].label }}</option>
                </select>
              </div>
              <div class="form-group">
                <label>分类</label>
                <select v-model="aiResult.category" class="form-input">
                  <option value="">无</option>
                  <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
                </select>
              </div>
            </div>
            <div v-if="aiResult.ai_evaluation" class="ai-result__eval">
              <span class="ai-result__eval-label"><Opportunity class="ep-icon" /> AI 评估</span>
              <p>{{ aiResult.ai_evaluation }}</p>
            </div>
          </div>
          <div class="modal__actions">
            <button class="btn btn--ghost" @click="showCreateModal = false">取消</button>
            <button v-if="!aiResult" class="btn btn--primary" @click="analyzeWithAI" :disabled="aiAnalyzing || !aiInput.trim()">
              <MagicStick v-if="!aiAnalyzing" class="ep-icon" /> {{ aiAnalyzing ? '分析中...' : '开始分析' }}
            </button>
            <button v-else class="btn btn--primary" @click="saveAiResult">保存</button>
          </div>
        </template>

        <!-- 手动模式 -->
        <template v-else>
          <div class="form-group">
            <label>标题</label>
            <input v-model="newTitle" class="form-input" placeholder="输入待办标题" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="newDescription" class="form-textarea" rows="3" placeholder="可选" @input="autoGrow"></textarea>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>四象限</label>
              <select v-model="newQuadrant" class="form-input">
                <option v-for="q in [1,2,3,4]" :key="q" :value="q">{{ quadrantLabels[q].label }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>分类</label>
              <select v-model="newCategory" class="form-input">
                <option value="">无</option>
                <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label>截止日期</label>
            <input v-model="newDueDate" type="date" class="form-input" />
          </div>
          <!-- 子任务 -->
          <div class="form-group">
            <label>子任务（可选）</label>
            <div v-if="newSubtasks.length" class="form-sub-list">
              <div v-for="(_, i) in newSubtasks" :key="i" class="form-sub-row">
                <span class="form-sub-bullet">○</span>
                <input v-model="newSubtasks[i]" class="form-sub-input" :placeholder="`子任务 ${i+1}`" @keydown.enter.prevent="addNewSubtask" @keydown.backspace="!newSubtasks[i] && removeNewSubtask(i)" />
                <button class="form-sub-del" @click="removeNewSubtask(i)"><Close class="ep-icon" /></button>
              </div>
            </div>
            <button class="form-add-sub" @click="addNewSubtask" type="button">＋ 添加子任务</button>
          </div>
          <div class="form-group">
            <TaskCreateExtras v-model:work="newIsWork" v-model:markDone="newMarkDone" v-model:aiEval="newAiEval" />
          </div>
          <div class="modal__actions">
            <button class="btn btn--ghost" @click="showCreateModal = false">取消</button>
            <button class="btn btn--primary" @click="createItem">创建</button>
          </div>
        </template>
      </div>
    </div>

    <!-- 完成记录耗时弹窗 -->
    <div v-if="showCompleteModal && completingItem" class="modal-overlay" @click.self="cancelComplete">
      <div class="modal modal--complete">
        <div class="modal__header">
          <h3><Check class="ep-icon" /> 完成任务</h3>
          <button class="btn btn--sm btn--ghost" @click="cancelComplete"><Close class="ep-icon" /></button>
        </div>
        <div class="complete-modal__body">
          <p class="complete-modal__title">{{ stripMarkdown(completingItem.title) }}</p>
          <div class="complete-modal__field">
            <label>实际耗时（分钟，可不填）</label>
            <p v-if="timeLogMinutes" class="complete-modal__timelog-hint">
              <Timer class="ep-icon" />️ 计时记录累计 <strong>{{ timeLogMinutes >= 60 ? Math.floor(timeLogMinutes / 60) + ' 小时 ' + (timeLogMinutes % 60 > 0 ? timeLogMinutes % 60 + ' 分钟' : '') : timeLogMinutes + ' 分钟' }}</strong>，已自动填入
            </p>
            <div class="complete-modal__input-row">
              <button v-if="timeLogMinutes" class="btn btn--sm" :class="{ 'btn--primary': actualMinutes === timeLogMinutes }" @click="actualMinutes = timeLogMinutes">{{ timeLogMinutes }}min (计时)</button>
              <button v-for="t in [5, 15, 30, 60, 120]" :key="t" class="btn btn--sm" :class="{ 'btn--primary': actualMinutes === t }" @click="actualMinutes = t">{{ t }}min</button>
              <button class="btn btn--sm" :class="{ 'btn--primary': actualMinutes === null }" @click="actualMinutes = null">不记录</button>
            </div>
            <input type="number" v-model.number="actualMinutes" min="1" placeholder="自定义分钟数" class="complete-modal__input" />
          </div>
          <!-- 已有备注 -->
          <div v-if="existingNotes.length > 0" class="complete-modal__field">
            <label><EditPen class="ep-icon" /> 已有备注</label>
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
        </div>
        <div class="modal__actions">
          <button class="btn btn--ghost" @click="cancelComplete">取消</button>
          <button class="btn btn--ghost" @click="markWontFix" title="标记为不解决，不记录耗时">🚫 不解决</button>
          <button class="btn btn--primary" @click="submitComplete"><Check class="ep-icon" /> 确认完成</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.todo-list {
  &__header {
    margin-bottom: $spacing-lg;
    h1 { font-size: $font-size-xl; }
  }
  &__subtitle { color: $text-secondary; font-size: $font-size-sm; margin-top: $spacing-xs; }
}

// 筛选栏
.filter-bar {
  @include glass-card;
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-md;
  margin-bottom: $spacing-lg;
  flex-wrap: wrap;

  @media (max-width: $breakpoint-sm) {
    gap: $spacing-xs;
    padding: $spacing-xs $spacing-sm;
  }
}

.filter-select, .filter-input {
  padding: $spacing-xs $spacing-sm;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  font-size: $font-size-xs;
  background: white;
  &:focus { outline: none; border-color: #EC4899; }
}

.filter-input { flex: 1; min-width: 120px; }

.filter-quadrants {
  display: flex;
  gap: 4px;
}

.filter-quadrant-btn {
  width: 28px;
  height: 28px;
  border-radius: $border-radius-sm;
  border: 2px solid transparent;
  background: rgba(0,0,0,0.04);
  font-size: 14px;
  cursor: pointer;
  transition: all $transition-fast;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover { background: rgba(0,0,0,0.08); }
  &--active { background: rgba(236, 72, 153, 0.1); border-color: #EC4899; }
}

// 待办卡片
.items-list { display: flex; flex-direction: column; gap: $spacing-sm; }

.todo-card {
  @include glass-card;
  display: flex;
  align-items: flex-start;
  gap: $spacing-sm;
  padding: $spacing-md;
  transition: all $transition-fast;

  &:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }

  &--done {
    opacity: 0.6;
    .todo-card__title { text-decoration: line-through; color: $text-muted; }
  }

  &--deferred {
    opacity: 0.7;
    border-left: 3px solid #6B7280;
  }

  &--timing {
    border-left: 3px solid #EC4899;
    background: rgba(236, 72, 153, 0.04);
    animation: timing-pulse 2s ease-in-out infinite;
  }

  // 子任务进度：左侧色条，未展开也能一眼看出完成到哪
  &--progress-none { border-left: 3px solid #9CA3AF; }
  &--progress-partial { border-left: 3px solid #F59E0B; }
  &--progress-full { border-left: 3px solid #10B981; }

  &__content { flex: 1; cursor: pointer; min-width: 0; }

  &__title-row {
    margin-bottom: $spacing-xs;
    display: flex;
    align-items: flex-start;
    gap: 6px;
  }

  &__title {
    flex: 1;
    min-width: 0;
    font-size: $font-size-sm;
    font-weight: 500;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    line-height: 1.5;
    word-break: break-word;
  }

  // 子任务优先级旗子图标
  &__quadrant-icon {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    margin-top: 1px;
  }

  // 核心任务星标
  &__core-star {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    margin-top: 1px;
    color: #F97316;

    &--month { color: #3B82F6; }
  }

  &__bottom-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: $spacing-sm;
    flex-wrap: wrap;
  }

  &__tags {
    display: flex;
    gap: $spacing-xs;
    flex-wrap: wrap;
    flex: 1;
    min-width: 0;
  }

  &__actions {
    display: flex;
    gap: $spacing-xs;
    flex-shrink: 0;
    align-items: center;
  }

  &__quadrant-tag, &__category-tag, &__status-tag {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    background: rgba(0,0,0,0.04);
    white-space: nowrap;
  }

  &__category-tag { background: rgba(139, 92, 246, 0.1); color: #8B5CF6; }

  &__meta {
    display: flex;
    gap: $spacing-md;
    margin-top: $spacing-xs;
    font-size: $font-size-xs;
    color: $text-muted;
  }
}

.action-btn {
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
  transition: all $transition-fast;

  &:hover { background: rgba(0,0,0,0.06); }
  &--danger:hover { background: rgba(239, 68, 68, 0.1); }
}

// 折叠/展开按钮
.expand-btn {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  border-radius: $border-radius-sm;
  background: rgba(139, 92, 246, 0.08);
  border: 1px solid rgba(139, 92, 246, 0.15);
  cursor: pointer;
  font-size: $font-size-xs;
  color: #8B5CF6;
  transition: all $transition-fast;
  flex-shrink: 0;

  &:hover { background: rgba(139, 92, 246, 0.15); }

  &__icon {
    font-size: 10px;
    transition: transform 0.2s ease;
    &--open { transform: rotate(90deg); }
  }

  &__count {
    font-weight: 600;
  }
}

// 子任务列表
.children-list {
  margin-left: 28px;
  padding-left: $spacing-md;
  border-left: 2px solid rgba(139, 92, 246, 0.2);
  margin-bottom: $spacing-sm;
}

.todo-card--child {
  padding: $spacing-sm $spacing-md;
  background: rgba(139, 92, 246, 0.03);
  border: 1px solid rgba(139, 92, 246, 0.1);
  margin-bottom: $spacing-xs;

  .todo-card__title { font-size: $font-size-xs; }
}

.todo-card--parent {
  border-left: 3px solid rgba(139, 92, 246, 0.3);
}

.todo-card__ai-tag {
  font-size: 12px;
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
    transition: all $transition-fast;

    &::after {
      content: '';
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: transparent;
      transition: all $transition-fast;
    }
  }

  input:checked + .checkbox__mark {
    border-color: #10B981;
    background: #10B981;
    &::after { background: white; }
  }
}

// 浮动按钮
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

  @media (max-width: $breakpoint-md) { bottom: 80px; }
}

// Modal
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: $spacing-md;

  @media (max-width: $breakpoint-sm) {
    padding: 0;
  }
}

.modal {
  @include glass-card;
  padding: $spacing-xl;
  width: 100%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    max-width: 100%;
    max-height: 100vh;
    border-radius: 0;
    height: 100vh;
  }

  h3 { font-size: $font-size-lg; margin-bottom: $spacing-lg; }

  &--detail {
    max-width: 600px;
  }

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $spacing-lg;
    h3 { margin-bottom: 0; }
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
  }
}

// 详情样式
.detail-section {
  margin-bottom: $spacing-md;
  padding-bottom: $spacing-md;
  border-bottom: 1px solid rgba(0,0,0,0.06);

  &:last-child { border-bottom: none; }

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

  &--meta {
    border-bottom: none;
  }
}

.detail-title {
  font-size: $font-size-lg;
  font-weight: 600;
  margin-bottom: $spacing-sm;
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
  background: rgba(0,0,0,0.04);
  white-space: nowrap;

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

.detail-meta-label { font-weight: 700; color: #1F2937; }
.detail-note-content { font-weight: 600; }
.detail-note-edit {
  border: none; background: transparent; cursor: pointer;
  color: $text-muted; font-size: 12px; padding: 0 4px;
  &:hover { color: $primary-color; }
}
.detail-comment-edit {
  flex: 1; min-width: 0; padding: 4px 8px;
  border: 1px solid $primary-color; border-radius: 6px;
  font-size: 12px; font-family: inherit;
}

.detail-value {
  font-size: $font-size-sm;
  line-height: 1.6;
  color: $text-primary;
  white-space: pre-wrap;
  // 长文本不撑开弹窗，限高 + 滚动查看
  max-height: 220px;
  overflow-y: auto;

  &--answer {
    color: #1e40af;
  }

  &--inspiration {
    color: #be185d;
  }
}

.detail-meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-sm $spacing-lg;
}

.detail-meta-label {
  font-size: $font-size-xs;
  color: $text-muted;
}

.detail-meta-value {
  font-size: $font-size-xs;
  font-weight: 500;
  margin-left: $spacing-xs;
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
  flex: 1;
  word-break: break-word;
  white-space: pre-wrap;  // 保留换行符
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
  background: rgba(255,255,255,0.6);

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

.form-group {
  margin-bottom: $spacing-md;
  label { display: block; font-size: $font-size-xs; font-weight: 600; color: $text-secondary; margin-bottom: $spacing-xs; }
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-md;
}

.form-input, .form-textarea {
  width: 100%;
  padding: $spacing-sm $spacing-md;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  font-family: inherit;
  background: rgba(255,255,255,0.8);
  &:focus { outline: none; border-color: #EC4899; }
}

.form-textarea { resize: vertical; }

// 新建表单子任务输入
.form-sub-list { display: flex; flex-direction: column; gap: 4px; padding-left: 8px; border-left: 2px solid rgba(#8B5CF6, 0.15); margin-bottom: 6px; }
.form-sub-row { display: flex; align-items: center; gap: 6px; }
.form-sub-bullet { color: $text-muted; font-size: 12px; flex-shrink: 0; }
.form-sub-input { flex: 1; border: 1px solid $border-color; border-radius: 8px; padding: 6px 10px; font-size: 13px; font-family: inherit; box-sizing: border-box; &:focus { outline: none; border-color: #8B5CF6; } }
.form-sub-del { background: none; border: none; color: $text-muted; cursor: pointer; font-size: 12px; padding: 2px 4px; border-radius: 4px; flex-shrink: 0; &:hover { color: $danger-color; background: rgba($danger-color, 0.08); } }
.form-add-sub { align-self: flex-start; background: none; border: none; color: $text-secondary; font-size: 13px; cursor: pointer; padding: 4px 8px; border-radius: 6px; &:hover { color: #8B5CF6; background: rgba(#8B5CF6, 0.06); } }

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

// 分页
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $spacing-md;
  margin-top: $spacing-lg;

  &__info { font-size: $font-size-sm; color: $text-secondary; }
}

// 共用
.empty-state {
  text-align: center;
  padding: $spacing-xxl;
  color: $text-secondary;
  &__icon { font-size: 48px; display: block; margin-bottom: $spacing-md; }
}

.loading {
  text-align: center;
  padding: $spacing-xxl;
  &__spinner {
    width: 40px; height: 40px;
    border: 3px solid $border-color;
    border-top-color: #EC4899;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto;
  }
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
    &:hover { opacity: 0.9; }
  }
  &--ghost { background: transparent; color: $text-secondary; &:hover { color: #EC4899; } }
  &--sm { padding: 4px 12px; font-size: $font-size-xs; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

@keyframes spin { to { transform: rotate(360deg); } }

@keyframes timing-pulse {
  0%, 100% { background: rgba(236, 72, 153, 0.04); }
  50% { background: rgba(236, 72, 153, 0.08); }
}

// 计时按钮
.timer-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: $border-radius-sm;
  background: rgba(0, 0, 0, 0.04);
  border: 1px solid transparent;
  cursor: pointer;
  font-size: $font-size-xs;
  color: $text-secondary;
  transition: all $transition-fast;
  flex-shrink: 0;

  &:hover { background: rgba(0, 0, 0, 0.08); }

  &__icon { font-size: 12px; line-height: 1; }

  &__time {
    font-family: 'Courier New', monospace;
    font-weight: 600;
    font-size: 11px;
    min-width: 42px;
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
  50% { box-shadow: 0 0 6px 2px rgba(236, 72, 153, 0.2); }
}

// 创建模式切换
.create-mode-toggle {
  display: flex;
  gap: $spacing-xs;
  margin-bottom: $spacing-lg;
  background: rgba(0,0,0,0.03);
  border-radius: $border-radius-sm;
  padding: 3px;
}

.create-mode-btn {
  flex: 1;
  padding: $spacing-xs $spacing-sm;
  border: none;
  border-radius: $border-radius-sm;
  background: transparent;
  font-size: $font-size-xs;
  font-weight: 500;
  color: $text-secondary;
  cursor: pointer;
  transition: all $transition-fast;

  &--active {
    background: white;
    color: #EC4899;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
  }
}

.ai-analyzing {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-md;
  color: $text-secondary;
  font-size: $font-size-sm;

  .loading__spinner--sm {
    width: 20px;
    height: 20px;
    border: 2px solid $border-color;
    border-top-color: #EC4899;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }
}

.ai-result {
  background: rgba(139, 92, 246, 0.04);
  border: 1px solid rgba(139, 92, 246, 0.15);
  border-radius: $border-radius-md;
  padding: $spacing-md;
  margin-bottom: $spacing-md;

  &__header {
    font-size: $font-size-sm;
    font-weight: 600;
    color: #8B5CF6;
    margin-bottom: $spacing-md;
  }

  &__eval {
    background: rgba(255,255,255,0.6);
    border-radius: $border-radius-sm;
    padding: $spacing-sm $spacing-md;
    margin-top: $spacing-sm;
  }

  &__eval-label {
    font-size: $font-size-xs;
    font-weight: 600;
    color: $text-secondary;
    display: block;
    margin-bottom: $spacing-xs;
  }

  &__eval p {
    font-size: $font-size-sm;
    color: $text-primary;
    line-height: 1.6;
    margin: 0;
  }
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

.detail-collapse {
  margin-bottom: $spacing-sm;
}

// 核心任务标记行
.detail-core {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  margin-bottom: $spacing-md;
  flex-wrap: wrap;

  &__label {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: $font-size-xs;
    color: $text-secondary;
    font-weight: 600;
  }

  &__btn {
    padding: 3px 12px;
    border-radius: 99px;
    border: 1px solid $border-color;
    background: transparent;
    font-size: $font-size-xs;
    color: $text-muted;
    cursor: pointer;
    transition: all 0.15s;

    &--week:hover { border-color: #F97316; color: #F97316; }
    &--month:hover { border-color: #3B82F6; color: #3B82F6; }
    &--year:hover { border-color: #8B5CF6; color: #8B5CF6; }

    &.detail-core__btn--on {
      font-weight: 600;
      &.detail-core__btn--week { background: rgba(#F97316, 0.12); border-color: #F97316; color: #C2410C; }
      &.detail-core__btn--month { background: rgba(#3B82F6, 0.12); border-color: #3B82F6; color: #1D4ED8; }
      &.detail-core__btn--year { background: rgba(#8B5CF6, 0.12); border-color: #8B5CF6; color: #6D28D9; }
    }
  }
}
.detail-collapse__toggle {
  display: inline-block; padding: 3px 10px; border: none; background: rgba(0,0,0,0.03); border-radius: 6px;
  font-size: 12px; color: $text-muted; cursor: pointer; transition: all 0.15s;
  &:hover { background: rgba($primary-color, 0.08); color: $primary-color; }
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
