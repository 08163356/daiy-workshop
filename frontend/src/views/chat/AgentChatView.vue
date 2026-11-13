<script setup lang="ts">
/**
 * 统一 AI 助手对话页（借鉴 deepseek-harness 交互骨架）
 * 左侧会话列表（移动端折叠为抽屉）+ 右侧对话流
 * 思维链折叠行 / 工具调用卡片 / 流式输出 / 会话级模型绑定
 */
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import { API_BASE, CHAT_API_BASE, TODO_API_BASE, DIARY_API_BASE } from '@/config'
import { ssePost } from './useSse'
import { emitDiaryChanged } from '@/utils/dailyEvents'
import { pendingQuestions, refreshPendingQuestions, answerQuestion, dismissQuestion } from '@/composables/useAiQuestions'
import ThinkingRow from '@/components/chat/ThinkingRow.vue'
import ToolCallCard from '@/components/chat/ToolCallCard.vue'
import SkillPanel from '@/components/chat/SkillPanel.vue'
import TodoPeekPanel from '@/components/todo/TodoPeekPanel.vue'

const route = useRoute()
const router = useRouter()
const DIARY_API = DIARY_API_BASE

marked.setOptions({ breaks: true, gfm: true })

const AGENT_API = `${API_BASE}/api/agent`

interface SessionItem {
  id: number
  title: string | null
  status: string
  ai_config_id: number | null
  mode?: string
  summary?: string | null
  updated_at: string
}

interface ToolCall {
  name: string
  args?: Record<string, any>
  summary?: string
  error?: boolean
  running?: boolean
}

interface Msg {
  role: 'user' | 'assistant'
  content: string
  images?: string[]
  thinking?: string | null
  toolCalls?: ToolCall[]
  streaming?: boolean
  queued?: boolean      // 插话排队中（AI 还没读到）
  steerSeq?: number     // 插话事件 seq（撤销用）
  seq?: number          // 用户消息事件序号，编辑/重新生成用
}

interface AiConfigItem {
  id: number
  name: string
  provider: string
  model: string
  is_active: boolean
}

// ==================== 状态 ====================
const sessions = ref<SessionItem[]>([])
const sidebarCollapsed = ref(false)

// 会话按时间分段（按 updated_at 距今天数）
const SESSION_BUCKETS = [
  { label: '今天', maxDays: 1 },
  { label: '3天前', maxDays: 3 },
  { label: '一周前', maxDays: 7 },
  { label: '一个月前', maxDays: 30 },
  { label: '3个月前', maxDays: 90 },
  { label: '6个月前', maxDays: 180 },
  { label: '一年前', maxDays: 365 },
  { label: '更早', maxDays: Infinity },
]
const groupedSessions = computed(() => {
  const now = Date.now()
  const buckets = SESSION_BUCKETS.map(b => ({ label: b.label, items: [] as SessionItem[] }))
  for (const s of sessions.value) {
    const t = new Date(s.updated_at).getTime()
    const days = Number.isFinite(t) ? (now - t) / 86400000 : 0
    const idx = SESSION_BUCKETS.findIndex(b => days < b.maxDays)
    buckets[idx < 0 ? buckets.length - 1 : idx].items.push(s)
  }
  return buckets.filter(g => g.items.length > 0)
})

const currentId = ref<number | null>(null)
const messages = ref<Msg[]>([])
const input = ref('')
const pendingImages = ref<string[]>([])
const imageUploading = ref(false)
const imageInput = ref<HTMLInputElement | null>(null)
const MAX_CHAT_IMAGES = 9
const imageSrc = (url: string) => url.startsWith('http') ? url : `${API_BASE}${url}`
const sending = ref(false)
const error = ref('')
const sidebarOpen = ref(false)
const aiConfigs = ref<AiConfigItem[]>([])
const selectedConfigId = ref<number | null>(null)  // 新会话绑定模型，null=跟随全局
const currentMode = ref<'normal' | 'coach' | 'explore'>('normal')
interface CoachFollowup {
  text: string
  check_question: string
  review_on: string | null
  todo_id: number | null
  todo_draft?: { title: string; description?: string } | null
  status: string
}
const coachSummary = ref<{ summary: string | null; insights: string[]; followups?: CoachFollowup[] } | null>(null)
interface ExploreProfileItem {
  category: string
  key: string
  value: string
  evidence?: string
  conflict?: boolean
  existing_value?: string | null
  applied?: boolean
}
interface ExploreReport {
  summary: string | null
  insights: string[]
  core_problem: string
  diary_id: number | null
  profile_updates: ExploreProfileItem[]
  todo_draft: { title: string } | null
  todo_id: number | null
}
const exploreReport = ref<ExploreReport | null>(null)
const profileChecked = ref<boolean[]>([])
const exploreSaving = ref('')
// 深挖入口来源（?origin=diary:123），建会话时传给后端一次
const pendingOrigin = ref<{ origin_type: string; origin_id: number } | null>(null)
const finalizing = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
let abortController: AbortController | null = null

const renderMd = (text: string) => {
  const html = marked.parse(text || '') as string
  return html.replace(/href="(todo|diary):(\d+)"/g, 'href="$1:$2" class="record-link"')
}

const peekTodoId = ref<number | null>(null)

function openRecordLink(event: MouseEvent) {
  const anchor = (event.target as HTMLElement).closest('a')
  const href = anchor?.getAttribute('href') || ''
  const match = href.match(/^(todo|diary):(\d+)$/)
  if (!match) return
  event.preventDefault()
  openRecord({ type: match[1] as 'todo' | 'diary', id: Number(match[2]) })
}

function openRecord(payload: { type: 'todo' | 'diary'; id: number }) {
  if (payload.type === 'todo') peekTodoId.value = payload.id
  else router.push(`/diary/${payload.id}`)
}

function onPeekEscape(e: KeyboardEvent) {
  if (e.key === 'Escape' && peekTodoId.value != null) {
    peekTodoId.value = null
    e.stopPropagation()
  }
}

// 自动滚动：用户上翻查看历史时不打断；新内容到来时显示「回到底部」浮钮
const userScrolledUp = ref(false)
const hasNewBelow = ref(false)
const NEAR_BOTTOM_PX = 120

const onMessagesScroll = () => {
  const el = messagesEl.value
  if (!el) return
  const dist = el.scrollHeight - el.scrollTop - el.clientHeight
  const wasUp = userScrolledUp.value
  userScrolledUp.value = dist > NEAR_BOTTOM_PX
  if (!userScrolledUp.value) hasNewBelow.value = false
  // 从「在底部」变为「上翻」时不需要提示
  if (userScrolledUp.value && !wasUp) hasNewBelow.value = false
}

const scrollToBottom = async (force = false) => {
  await nextTick()
  const el = messagesEl.value
  if (!el) return
  if (userScrolledUp.value && !force) {
    hasNewBelow.value = true  // 用户在上面看历史，新内容用浮钮提示
    return
  }
  el.scrollTo({ top: el.scrollHeight })
  hasNewBelow.value = false
}

const jumpToLatest = () => {
  userScrolledUp.value = false
  hasNewBelow.value = false
  messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight, behavior: 'smooth' })
}

// ==================== 会话管理 ====================
const loadSessions = async () => {
  try {
    const res = await fetch(`${AGENT_API}/sessions`)
    if (res.ok) sessions.value = await res.json()
  } catch { /* 静默 */ }
}

const selectSession = async (id: number) => {
  if (sending.value) return
  currentId.value = id
  sidebarOpen.value = false
  error.value = ''
  try {
    const res = await fetch(`${AGENT_API}/sessions/${id}`)
    if (res.ok) {
      const data = await res.json()
      messages.value = data.messages.map((m: any) => ({
        role: m.role,
        content: m.content,
        images: m.images || [],
        thinking: m.thinking || null,
        toolCalls: m.toolCalls || [],
        seq: m.seq,
      }))
      selectedConfigId.value = data.session.ai_config_id
      clarifyCard.value = null  // 切会话清掉未答的提问卡
      tasklistDraft.value = null
      applySessionMeta(data.session)
      userScrolledUp.value = false
      scrollToBottom(true)  // 切换会话强制到底
    }
  } catch { /* 静默 */ }
}

const newSession = () => {
  if (sending.value) return
  currentId.value = null
  messages.value = []
  error.value = ''
  sidebarOpen.value = false
  currentMode.value = 'normal'
  coachSummary.value = null
  exploreReport.value = null
  profileChecked.value = []
}

const reportFromSession = (session: any): ExploreReport => {
  const pack = (session.followups || []).find((f: any) => f.kind === 'explore') || {}
  const insights = Array.isArray(session.insights) ? session.insights.filter((x: any) => typeof x === 'string') : []
  return {
    summary: session.summary,
    insights,
    core_problem: pack.core_problem || '',
    diary_id: pack.diary_id || null,
    profile_updates: pack.profile_updates || [],
    todo_draft: pack.todo_draft || null,
    todo_id: pack.todo_id || null,
  }
}

const applySessionMeta = (session: any) => {
  currentMode.value = session.mode || 'normal'
  coachSummary.value = null
  exploreReport.value = null
  profileChecked.value = []
  if (session.mode === 'coach' && session.summary) {
    coachSummary.value = {
      summary: session.summary,
      insights: Array.isArray(session.insights) ? session.insights : [],
      followups: session.followups || [],
    }
  }
  if (session.mode === 'explore' && session.summary) {
    exploreReport.value = reportFromSession(session)
    profileChecked.value = exploreReport.value.profile_updates.map(item => !item.applied && !item.conflict)
  }
}

// 沉淀卡片「建成待办」（fail-closed：用户点了才创建，回写跟进项 todo_id）
const buildingTodo = ref<number | null>(null)
const buildFollowupTodo = async (followupIndex: number) => {
  if (!currentId.value || buildingTodo.value !== null) return
  buildingTodo.value = followupIndex
  try {
    const res = await fetch(`${AGENT_API}/sessions/${currentId.value}/followup-todo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ followup_index: followupIndex }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '创建失败')
    const f = coachSummary.value?.followups?.[followupIndex]
    if (f) f.todo_id = data.todo_id
    loadSessions()
  } catch (e: any) {
    alert(e.message || '建成待办失败')
  } finally {
    buildingTodo.value = null
  }
}

/** 教练会话：结束并沉淀（总结/洞察入会话，画像更新） */
const finalizeCoach = async () => {
  if (!currentId.value || finalizing.value) return
  finalizing.value = true
  try {
    const res = await fetch(`${AGENT_API}/sessions/${currentId.value}/finalize-coach`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) {
      alert(data.detail || '沉淀失败')
      return
    }
    coachSummary.value = { summary: data.summary, insights: data.insights || [], followups: data.followups || [] }
    loadSessions()
  } finally {
    finalizing.value = false
  }
}

const finalizeExplore = async () => {
  if (!currentId.value || finalizing.value) return
  finalizing.value = true
  try {
    const res = await fetch(`${AGENT_API}/sessions/${currentId.value}/finalize-explore`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) {
      alert(data.detail || '生成评估失败')
      return
    }
    exploreReport.value = {
      summary: data.summary,
      insights: data.insights || [],
      core_problem: data.core_problem || '',
      diary_id: data.diary_id || null,
      profile_updates: data.profile_updates || [],
      todo_draft: data.todo_draft || null,
      todo_id: data.todo_id || null,
    }
    profileChecked.value = exploreReport.value.profile_updates.map(item => !item.applied && !item.conflict)
    loadSessions()
  } finally {
    finalizing.value = false
  }
}

const saveExploreDiary = async () => {
  if (!currentId.value || exploreSaving.value) return
  exploreSaving.value = 'diary'
  try {
    const res = await fetch(`${AGENT_API}/sessions/${currentId.value}/explore-diary`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '写入日记失败')
    if (exploreReport.value) exploreReport.value.diary_id = data.diary_id
  } catch (e: any) {
    alert(e.message || '写入日记失败')
  } finally {
    exploreSaving.value = ''
  }
}

const saveExploreProfile = async () => {
  if (!currentId.value || exploreSaving.value || !exploreReport.value) return
  const indices = profileChecked.value
    .map((checked, index) => checked && !exploreReport.value!.profile_updates[index]?.applied ? index : -1)
    .filter(index => index >= 0)
  if (!indices.length) {
    alert('先勾选要写入的画像')
    return
  }
  exploreSaving.value = 'profile'
  try {
    const res = await fetch(`${AGENT_API}/sessions/${currentId.value}/explore-profile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ indices }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '写入画像失败')
    exploreReport.value.profile_updates = data.profile_updates || []
    profileChecked.value = exploreReport.value.profile_updates.map(item => !item.applied && !item.conflict)
  } catch (e: any) {
    alert(e.message || '写入画像失败')
  } finally {
    exploreSaving.value = ''
  }
}

const saveExploreTodo = async () => {
  if (!currentId.value || exploreSaving.value) return
  exploreSaving.value = 'todo'
  try {
    const res = await fetch(`${AGENT_API}/sessions/${currentId.value}/explore-todo`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '建成待办失败')
    if (exploreReport.value) exploreReport.value.todo_id = data.todo_id
  } catch (e: any) {
    alert(e.message || '建成待办失败')
  } finally {
    exploreSaving.value = ''
  }
}

const deleteSession = async (id: number) => {
  if (!confirm('删除这个会话？消息记录会一并删除')) return
  try {
    const res = await fetch(`${AGENT_API}/sessions/${id}`, { method: 'DELETE' })
    if (res.ok) {
      sessions.value = sessions.value.filter(s => s.id !== id)
      if (currentId.value === id) newSession()
    }
  } catch { /* 静默 */ }
}

const renameSession = async (s: SessionItem) => {
  const title = prompt('会话名称', s.title || '')
  if (!title?.trim()) return
  try {
    const res = await fetch(`${AGENT_API}/sessions/${s.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title.trim() }),
    })
    if (res.ok) s.title = title.trim()
  } catch { /* 静默 */ }
}

const switchModel = async () => {
  // 切换当前会话的绑定模型；无会话时仅作为新会话的默认
  if (!currentId.value) return
  try {
    await fetch(`${AGENT_API}/sessions/${currentId.value}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ai_config_id: selectedConfigId.value }),
    })
  } catch { /* 静默 */ }
}

// ==================== 对话 ====================
const autoGrow = (e: Event) => {
  const el = e.target as HTMLTextAreaElement
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

const stop = () => {
  abortController?.abort()
}

// ==================== 写操作确认（fail-closed） ====================
const pendingConfirm = ref<{ name: string; args: Record<string, any> } | null>(null)

// ==================== 任务单草稿（AI 拆父子 → 用户编辑 → 确认才创建） ====================
interface TasklistChild { title: string; quadrant?: number; urgency?: number }
interface TasklistGroup { parent: string; description: string; quadrant: number; urgency?: number; category: string; children: TasklistChild[] }
const tasklistDraft = ref<TasklistGroup[] | null>(null)
const tasklistSaving = ref(false)

const addTasklistGroup = () => {
  tasklistDraft.value?.push({ parent: '', description: '', quadrant: 2, urgency: 3, category: '', children: [] })
}
const removeTasklistGroup = (i: number) => { tasklistDraft.value?.splice(i, 1) }
const addTasklistChild = (g: TasklistGroup) => { g.children.push({ title: '', quadrant: g.quadrant, urgency: g.urgency || 3 }) }
const removeTasklistChild = (g: TasklistGroup, i: number) => { g.children.splice(i, 1) }
const promoteChild = (gi: number, ci: number) => {
  const g = tasklistDraft.value?.[gi]
  if (!g) return
  const child = g.children.splice(ci, 1)[0]
  tasklistDraft.value?.push({ parent: child.title, description: '', quadrant: child.quadrant || g.quadrant, urgency: child.urgency || g.urgency || 3, category: g.category, children: [] })
}

const createTasklist = async () => {
  const groups = (tasklistDraft.value || []).filter(g => g.parent.trim())
  if (!groups.length || tasklistSaving.value) return
  tasklistSaving.value = true
  try {
    const res = await fetch(`${AGENT_API}/tasklist/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: currentId.value,
        groups: groups.map(g => ({
          parent: g.parent.trim(), description: g.description,
          quadrant: g.quadrant, urgency: g.urgency || 3, category: g.category || null,
          children: g.children.filter(c => c.title.trim()).map(c => ({
            title: c.title.trim(),
            quadrant: c.quadrant || g.quadrant,
            urgency: c.urgency || g.urgency || 3,
          })),
        })),
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '创建失败')
    messages.value.push({ role: 'assistant', content: `✅ 已按你的修改创建任务单：${data.parents} 个父任务、${data.children} 个子任务。`, toolCalls: [] })
    tasklistDraft.value = null
    scrollToBottom(true)
  } catch (e: any) {
    error.value = e.message || '创建失败'
  } finally {
    tasklistSaving.value = false
  }
}

// ==================== 澄清提问（分析中真实需要了解用户才弹出，回答经 AI 提炼进画像） ====================
// UI 参考 harness AskUserQuestion：可折叠卡片 + 字母徽章选项行 + 自定义回答行
interface ClarifyQuestion { question: string; options: string[]; answer: string; customOpen: boolean }
const clarifyCard = ref<{ batchId: string; questions: ClarifyQuestion[] } | null>(null)
const clarifyCollapsed = ref(false)
const submittingAnswers = ref(false)

const OPTION_LETTERS = ['A', 'B', 'C', 'D']

const pickOption = (q: ClarifyQuestion, opt: string) => {
  q.answer = q.answer === opt ? '' : opt  // 再点一次取消选择
  if (q.answer) q.customOpen = false  // 选了选项就收起自定义输入
}

const toggleCustom = (q: ClarifyQuestion) => {
  q.customOpen = !q.customOpen
}

const submitAnswers = async () => {
  const pq = clarifyCard.value
  if (!pq || submittingAnswers.value) return
  const answered = pq.questions.filter(q => q.answer.trim())
  if (!answered.length) return
  submittingAnswers.value = true
  try {
    // 问答进消息流；服务端会流式返回 AI 的反馈并继续对话
    messages.value.push({
      role: 'user',
      content: '【澄清回答】\n' + answered.map(q => `**${q.question}**\n${q.answer.trim()}`).join('\n'),
    })
    messages.value.push({ role: 'assistant', content: '', thinking: '', toolCalls: [], streaming: true })
    const assistantMsg = messages.value[messages.value.length - 1]
    clarifyCard.value = null
    const stream = ssePost(`${AGENT_API}/clarify`, {
      session_id: currentId.value,
      batch_id: pq.batchId,
      answers: answered.map(q => ({ question: q.question, answer: q.answer.trim() })),
    })
    await consumeStream(stream, assistantMsg)
    loadPendingQuestions()  // 右上角同步刷新（对话里答过的不再显示）
    scrollToBottom(true)
  } catch (e: any) {
    error.value = e.message || '提交回答失败'
  } finally {
    submittingAnswers.value = false
  }
}

const skipQuestions = () => { clarifyCard.value = null }

const TOOL_LABELS: Record<string, string> = {
  create_todo: '创建待办',
  complete_todo: '完成待办',
  save_knowledge: '收入知识库',
  apply_schedule: '写入排期',
  add_wellbeing: '记录心力',
  create_diary: '保存日记',
  create_note: '保存笔记',
  create_investment: '保存投资反思',
  write_analysis: '把分析写回记录',
  add_lesson: '记下经验沉淀',
  __save_record: '保存到系统（含本次 AI 分析）',
}
const toolLabel = (name: string) => TOOL_LABELS[name] || name

const confirmSummary = computed(() => {
  if (!pendingConfirm.value) return ''
  const a = pendingConfirm.value.args || {}
  if (Array.isArray(a.schedules)) {
    return `${a.summary || '写入排期'}（${a.schedules.length} 条）`
  }
  return a.summary || a.title || a.content || a.title_keyword || JSON.stringify(a)
})

/** 消费 SSE 事件流并更新 assistant 消息（发送与确认恢复共用） */
const consumeStream = async (stream: AsyncGenerator<any, void>, assistantMsg: Msg) => {
  assistantMsg.toolCalls = assistantMsg.toolCalls || []  // 兜底：澄清确认语等消息没有该字段
  for await (const ev of stream) {
    if (ev.type === 'session') {
      currentId.value = ev.session_id
    } else if (ev.type === 'thinking') {
      assistantMsg.thinking = (assistantMsg.thinking || '') + ev.delta
    } else if (ev.type === 'content') {
      assistantMsg.content += ev.delta
      scrollToBottom()
    } else if (ev.type === 'tool_call') {
      assistantMsg.toolCalls!.push({ name: ev.name, args: ev.args, running: true })
      scrollToBottom()
    } else if (ev.type === 'tool_result') {
      const card = [...assistantMsg.toolCalls!].reverse().find(c => c.name === ev.name && c.running)
      if (card) {
        card.running = false
        card.summary = ev.summary
        card.error = ev.error
      }
    } else if (ev.type === 'confirm_required') {
      // 写操作待确认：中断流，展示确认卡
      const card = [...assistantMsg.toolCalls!].reverse().find(c => c.name === ev.name && c.running)
      if (card) card.running = false
      pendingConfirm.value = { name: ev.name, args: ev.args }
    } else if (ev.type === 'tasklist_draft') {
      // 任务单草稿：可编辑，用户点「创建」才写待办
      tasklistDraft.value = (ev.groups || []).map((g: any) => ({
        parent: g.parent, description: g.description || '',
        quadrant: g.quadrant || 2, urgency: g.urgency || 3, category: g.category || '',
        children: (g.children || []).map((c: any) => ({
          title: typeof c === 'string' ? c : (c.title || ''),
          quadrant: typeof c === 'object' ? (c.quadrant || g.quadrant || 2) : (g.quadrant || 2),
          urgency: typeof c === 'object' ? (c.urgency || g.urgency || 3) : (g.urgency || 3),
        })),
      }))
      scrollToBottom()
    } else if (ev.type === 'questions') {
      // 澄清提问：AI 分析中真实需要了解用户的地方，弹卡片让用户回答（可跳过）
      clarifyCard.value = {
        batchId: ev.batch_id,
        questions: (ev.questions || []).map((q: any) => ({
          question: q.question, options: q.options || [], answer: '', customOpen: false,
        })),
      }
      clarifyCollapsed.value = false
      scrollToBottom()
    } else if (ev.type === 'steering_claimed') {
      // 插话被 AI 读取：排队气泡转正常
      for (const m of messages.value) {
        if (m.queued) m.queued = false
      }
    } else if (ev.type === 'done') {
      assistantMsg.streaming = false
      if (ev.title) {
        const s = sessions.value.find(x => x.id === currentId.value)
        if (s) s.title = ev.title
      }
    } else if (ev.type === 'error') {
      error.value = ev.message
      assistantMsg.streaming = false
    }
  }
}

const uploadChatImages = async (files: File[]) => {
  const room = MAX_CHAT_IMAGES - pendingImages.value.length
  const batch = files.filter(f => f.type.startsWith('image/')).slice(0, room)
  if (!batch.length) return
  imageUploading.value = true
  error.value = ''
  try {
    const form = new FormData()
    batch.forEach(f => form.append('files', f))
    const res = await fetch(`${API_BASE}/api/uploads/images`, { method: 'POST', body: form })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || '图片上传失败')
    const urls = (data.images || []).map((img: { url: string }) => img.url).filter(Boolean)
    pendingImages.value = [...pendingImages.value, ...urls].slice(0, MAX_CHAT_IMAGES)
  } catch (e: any) {
    error.value = e.message || '图片上传失败'
  } finally {
    imageUploading.value = false
  }
}

const onPasteImage = (e: ClipboardEvent) => {
  const items = Array.from(e.clipboardData?.items || [])
  const files = items
    .filter(item => item.type.startsWith('image/'))
    .map(item => item.getAsFile())
    .filter((f): f is File => !!f)
  if (!files.length) return
  e.preventDefault()
  const text = e.clipboardData?.getData('text/plain') || ''
  if (text) {
    const el = e.target as HTMLTextAreaElement
    const start = el.selectionStart ?? input.value.length
    const end = el.selectionEnd ?? start
    input.value = input.value.slice(0, start) + text + input.value.slice(end)
  }
  uploadChatImages(files)
}

const onPickImages = (e: Event) => {
  const inputEl = e.target as HTMLInputElement
  const files = Array.from(inputEl.files || [])
  inputEl.value = ''
  if (files.length) uploadChatImages(files)
}

const removePendingImage = (idx: number) => {
  pendingImages.value = pendingImages.value.filter((_, i) => i !== idx)
}

const send = async () => {
  // 生成中 → 转为插话（steering）。插话不带图片。
  if (sending.value) {
    if (pendingImages.value.length) {
      error.value = '这轮还在生成，图片请等结束后再发'
      return
    }
    await steer()
    return
  }
  const rawText = input.value.trim()
  // 句首 chip 参与路由（报告/记录管线靠前缀识别），气泡显示带标签
  const text = prefixChip.value
    ? `${prefixChip.value.prefix}${rawText ? ' ' + rawText : ''}`
    : rawText
  const images = [...pendingImages.value]
  if (!text && !images.length) return
  if (imageUploading.value) return
  if (!navigator.onLine) {
    pushOutbox({ id: String(Date.now()), kind: 'chat', text, images })
    input.value = ''
    prefixChip.value = null
    pendingImages.value = []
    localStorage.removeItem(DRAFT_KEY)
    notice.value = '没网，内容已暂存，联网后会放回输入框'
    return
  }
  if (text.startsWith('/教练')) currentMode.value = 'coach'  // 后端同步切模式，前端即时反映
  if (text.startsWith('/探索')) currentMode.value = 'explore'
  // @引用内容拼接到消息前（模型可见），气泡里只显示原文+引用标记
  let payloadText = text
  if (refChips.value.length) {
    const refBlock = refChips.value
      .map(r => `【引用${r.type === 'diary' ? '日记' : '待办'}：${r.label}】\n${r.content}`)
      .join('\n\n')
    payloadText = `${refBlock}\n\n${text}`
  }
  const chipTag = prefixChip.value ? `[${prefixChip.value.label}] ` : ''
  const displayText = refChips.value.length
    ? `📎 ${refChips.value.map(r => r.label).join('、')}\n\n${chipTag}${rawText}`
    : chipTag + rawText || text
  refChips.value = []
  prefixChip.value = null
  input.value = ''
  pendingImages.value = []
  error.value = ''
  pendingConfirm.value = null
  sending.value = true

  messages.value.push({ role: 'user', content: displayText, images })
  messages.value.push({ role: 'assistant', content: '', thinking: '', toolCalls: [], streaming: true })
  // 必须拿数组里的响应式代理：直接改原始对象不会触发 Vue 更新，思维链/正文会在结束后才一次性渲染
  const assistantMsg = messages.value[messages.value.length - 1] as Msg
  scrollToBottom(true)  // 用户主动发消息，强制滚到底

  abortController = new AbortController()
  try {
    const stream = ssePost(`${AGENT_API}/chat`, {
      session_id: currentId.value,
      content: payloadText,
      images,
      ai_config_id: currentId.value ? undefined : selectedConfigId.value,
      // 深挖入口：仅新建会话时带上，后端记到会话上
      ...(currentId.value ? {} : (pendingOrigin.value || {})),
    }, abortController.signal)
    pendingOrigin.value = null  // 只在建会话时传一次
    await consumeStream(stream, assistantMsg)
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      error.value = e.message || '对话失败'
    }
    assistantMsg.streaming = false
  } finally {
    sending.value = false
    abortController = null
    loadSessions()
    scrollToBottom()
  }
}

/** 生成中插话：追加 steering，AI 在轮次边界看到（harness steering 裁剪版） */
const steer = async () => {
  const text = input.value.trim()
  if (!text || !currentId.value) return
  input.value = ''
  try {
    const res = await fetch(`${AGENT_API}/steer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentId.value, content: text }),
    })
    const data = await res.json()
    if (!res.ok) {
      // 没在生成（刚好结束了）→ 退回输入框让用户直接发
      input.value = text
      return
    }
    messages.value.push({ role: 'user', content: text, queued: true, steerSeq: data.seq })
    scrollToBottom()
  } catch {
    input.value = text
  }
}

/** 撤销排队中的插话 */
const cancelSteer = async (msg: Msg) => {
  if (!currentId.value || !msg.steerSeq) return
  try {
    await fetch(`${AGENT_API}/steer/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentId.value, seq: msg.steerSeq }),
    })
    const i = messages.value.indexOf(msg)
    if (i >= 0) messages.value.splice(i, 1)
  } catch { /* 静默 */ }
}

/** 撤回：仅最后一条用户消息且 AI 未回复（后端校验），撤回后回填输入框 */
const recalling = ref(false)
const canRecall = computed(() =>
  !sending.value && messages.value.length > 0 && messages.value[messages.value.length - 1].role === 'user'
    && !messages.value[messages.value.length - 1].queued
)
const recallLast = async () => {
  if (!currentId.value || !canRecall.value) return
  recalling.value = true
  try {
    const res = await fetch(`${AGENT_API}/void`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentId.value }),
    })
    const data = await res.json()
    if (!res.ok) {
      alert(data.detail || '撤回失败')
      return
    }
    messages.value.pop()
    input.value = data.content || ''
    nextTick(() => {
      const el = document.querySelector<HTMLTextAreaElement>('.agent-chat__input')
      el?.focus()
      el?.setSelectionRange(input.value.length, input.value.length)
    })
  } finally {
    recalling.value = false
  }
}

const notice = ref('')
const OUTBOX_KEY = 'daily-record-outbox'
const DRAFT_KEY = 'daily-chat-draft'
const outboxCount = ref(0)

function todayIso() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function readOutbox() {
  try { return JSON.parse(localStorage.getItem(OUTBOX_KEY) || '[]') } catch { return [] }
}
function writeOutbox(items: any[]) {
  localStorage.setItem(OUTBOX_KEY, JSON.stringify(items))
  outboxCount.value = items.length
}
function pushOutbox(item: any) {
  const items = readOutbox()
  items.push(item)
  writeOutbox(items)
}

function focusInput() {
  nextTick(() => {
    const el = document.querySelector<HTMLTextAreaElement>('.agent-chat__input')
    el?.focus()
    if (el) el.setSelectionRange(el.value.length, el.value.length)
  })
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text || '')
    notice.value = '已复制'
  } catch {
    notice.value = '复制失败'
  }
}

async function rewindMessage(seq: number) {
  if (!currentId.value) return false
  const res = await fetch(`${AGENT_API}/rewind`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: currentId.value, seq }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    error.value = data.detail || '这条消息现在不能改'
    return false
  }
  return true
}

async function editUserMessage(msg: Msg, idx: number) {
  if (sending.value) return
  if (idx === messages.value.length - 1 && canRecall.value) {
    await recallLast()
    return
  }
  if (msg.seq && currentId.value) {
    const ok = await rewindMessage(msg.seq)
    if (!ok) return
    await selectSession(currentId.value)
  }
  input.value = msg.content || ''
  pendingImages.value = [...(msg.images || [])]
  focusInput()
}

async function regenerateFrom(msg: Msg) {
  if (sending.value || !msg.seq) return
  const text = msg.content || ''
  const images = [...(msg.images || [])]
  const ok = await rewindMessage(msg.seq)
  if (!ok || !currentId.value) return
  await selectSession(currentId.value)
  input.value = text
  pendingImages.value = images
  await send()
}

function previousUser(idx: number) {
  for (let i = idx - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user' && !messages.value[i].queued) return messages.value[i]
  }
  return null
}

function detectRecord(text: string) {
  const rules: Array<[string, 'diary' | 'todo' | 'invest' | 'wellbeing' | 'note', string?]> = [
    ['/日记', 'diary'],
    ['/待办', 'todo'],
    ['/投资', 'invest'],
    ['/心力', 'wellbeing'],
    ['/课程', 'note', 'course'],
    ['/笔记', 'note', 'book'],
    ['/随笔', 'note', 'self'],
  ]
  for (const [prefix, kind, sourceType] of rules) {
    if (text.startsWith(prefix)) return { kind, body: text.slice(prefix.length).trim(), sourceType }
  }
  return { kind: 'diary' as const, body: text, sourceType: undefined }
}

async function postDirect(item: { kind: string; text: string; images?: string[]; sourceType?: string }) {
  const day = todayIso()
  const title = item.text.split('\n')[0].trim().slice(0, 40) || `${day} 记录`
  let res: Response
  if (item.kind === 'todo') {
    res = await fetch(`${TODO_API_BASE}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, original_text: item.text, skip_ai_eval: true, status: 'planned' }),
    })
  } else if (item.kind === 'invest') {
    res = await fetch(`${API_BASE}/api/investment/reflections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: day, title: title || '投资反思', content: item.text }),
    })
  } else if (item.kind === 'wellbeing') {
    const grateful = /感恩|感谢|幸好/.test(item.text)
    res = await fetch(`${API_BASE}/api/wellbeing/entries`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: grateful ? 'gratitude' : 'achievement',
        content: item.text,
        occurred_at: day,
        intensity: 3,
        source_type: 'manual',
      }),
    })
  } else if (item.kind === 'note') {
    res = await fetch(`${API_BASE}/api/notes/plain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content: item.text, source_type: item.sourceType || 'self' }),
    })
  } else {
    res = await fetch(`${DIARY_API}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: day,
        title: `${day} 日记`,
        content: item.text,
        images: item.images || [],
        source: 'web',
      }),
    })
  }
  if (!res.ok) throw new Error('保存失败')
}

async function saveDirect() {
  const rawText = input.value.trim()
  const text = prefixChip.value
    ? `${prefixChip.value.prefix}${rawText ? ' ' + rawText : ''}`
    : rawText
  if (!text) return
  const parsed = detectRecord(text)
  if (!parsed.body) {
    notice.value = '先写内容，再直接保存'
    return
  }
  const item = {
    id: String(Date.now()),
    kind: parsed.kind,
    text: parsed.body,
    images: [...pendingImages.value],
    sourceType: parsed.sourceType,
  }
  input.value = ''
  prefixChip.value = null
  pendingImages.value = []
  localStorage.removeItem(DRAFT_KEY)
  if (!navigator.onLine) {
    pushOutbox(item)
    notice.value = '没网，已暂存，联网后自动入库'
    return
  }
  try {
    await postDirect(item)
    notice.value = '已直接保存，没有做 AI 分析'
    if (item.kind === 'diary') emitDiaryChanged()
  } catch {
    pushOutbox(item)
    notice.value = '没发出去，已暂存，联网后会再试'
  }
}

async function flushOutbox() {
  if (!navigator.onLine) return
  const pending = readOutbox()
  if (!pending.length) return
  const left: any[] = []
  for (const item of pending) {
    if (item.kind === 'chat') {
      if (!input.value.trim()) {
        input.value = item.text || ''
        pendingImages.value = item.images || []
        notice.value = '联网了，未发出的对话已放回输入框'
      } else {
        left.push(item)
      }
      continue
    }
    try { await postDirect(item) }
    catch { left.push(item) }
  }
  writeOutbox(left)
  if (!left.length && notice.value.startsWith('没')) notice.value = '暂存的内容已入库'
}

/** 用户点击 允许/拒绝 后恢复对话循环 */
const respondConfirm = async (approved: boolean) => {
  if (!currentId.value) return
  const confirmName = pendingConfirm.value?.name
  pendingConfirm.value = null
  error.value = ''
  sending.value = true
  // 目标消息：正常是带确认卡的分析消息；若最后是澄清确认语等新消息，则新开一条 assistant 承接恢复流
  let assistantMsg = messages.value[messages.value.length - 1] as Msg | undefined
  if (!assistantMsg || assistantMsg.role !== 'assistant' || !assistantMsg.toolCalls) {
    messages.value.push({ role: 'assistant', content: '', thinking: '', toolCalls: [], streaming: true })
    assistantMsg = messages.value[messages.value.length - 1] as Msg
  }
  assistantMsg.streaming = true

  abortController = new AbortController()
  try {
    const stream = ssePost(`${AGENT_API}/confirm`, {
      session_id: currentId.value,
      approved,
    }, abortController.signal)
    await consumeStream(stream, assistantMsg)
    if (approved && (confirmName === '__save_record' || confirmName === 'create_diary')) emitDiaryChanged()
  } catch (e: any) {
    if (e.name !== 'AbortError') {
      error.value = e.message || '确认失败'
    }
    assistantMsg.streaming = false
  } finally {
    sending.value = false
    abortController = null
    scrollToBottom()
  }
}

// ==================== 快捷指令（句首 chip，不覆盖输入框已有内容） ====================
// 报告类触发报告管线；记录类触发分析管线；都在句首加前缀 chip，原文保留可续写
interface PrefixChip { label: string; prefix: string }
const prefixChip = ref<PrefixChip | null>(null)
const quickCommands: PrefixChip[] = [
  { label: '教练', prefix: '/教练' },
  { label: '探索', prefix: '/探索' },
  { label: '日报', prefix: '/日报' },
  { label: '周报', prefix: '/周报' },
  { label: '月报', prefix: '/月报' },
  { label: '复盘', prefix: '/复盘' },
  { label: '日记', prefix: '/日记' },
  { label: '笔记', prefix: '/笔记' },
  { label: '课程', prefix: '/课程' },
  { label: '随笔', prefix: '/随笔' },
  { label: '心力', prefix: '/心力' },
  { label: '待办', prefix: '/待办' },
  { label: '任务单', prefix: '/任务单' },
  { label: '知识', prefix: '/知识' },
  { label: '投资', prefix: '/投资' },
]
// 点击只加句首 chip + 聚焦输入框，不覆盖已有内容，不发送
const runQuickCommand = (cmd: PrefixChip) => {
  if (sending.value) return
  prefixChip.value = cmd
  nextTick(() => {
    const el = document.querySelector<HTMLTextAreaElement>('.agent-chat__input')
    el?.focus()
    el?.setSelectionRange(input.value.length, input.value.length)
  })
}
const clearPrefixChip = () => { prefixChip.value = null }

// 输入 "/" 开头时弹出命令面板（选中=句首 chip，不覆盖已有内容）
// 面板 = 内置快捷指令 + user_invocable 的自定义 skill（新建后自动出现）
const skillCommands = ref<PrefixChip[]>([])
const loadSkillCommands = async () => {
  try {
    const res = await fetch(`${API_BASE}/api/prompt-skills?include_disabled=false`)
    if (!res.ok) return
    const items = (await res.json()).items || []
    skillCommands.value = items
      .filter((s: any) => s.user_invocable && !s.bind_pipeline && !s.is_persona)
      .map((s: any) => ({ label: `🧩 ${s.title}`, prefix: `/skill:${s.name}` }))
  } catch { /* 静默 */ }
}
const allCommands = computed(() => [...quickCommands, ...skillCommands.value])

const slashIndex = ref(0)
const slashMatches = computed(() => {
  if (!input.value.startsWith('/') || prefixChip.value) return []
  const kw = input.value.slice(1).trim()
  if (!kw) return allCommands.value
  return allCommands.value.filter(c => c.prefix.slice(1).includes(kw) || c.label.includes(kw))
})
const showSlash = computed(() => slashMatches.value.length > 0)
watch(slashMatches, () => { slashIndex.value = 0 })
const pickSlash = (cmd: PrefixChip) => {
  input.value = ''
  runQuickCommand(cmd)
}

// 命令面板打开时：↑↓ 选择，Enter 选中（不发送），Esc 关闭
const onInputKeydown = (e: KeyboardEvent) => {
  if (!showSlash.value) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    slashIndex.value = (slashIndex.value + 1) % slashMatches.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    slashIndex.value = (slashIndex.value - 1 + slashMatches.value.length) % slashMatches.value.length
  } else if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    pickSlash(slashMatches.value[slashIndex.value])
  } else if (e.key === 'Escape') {
    input.value = ''
  }
}
const onEnter = () => {
  if (showSlash.value) {
    pickSlash(slashMatches.value[slashIndex.value])
    return
  }
  send()
}

// ==================== @引用（把日记/待办喂给 AI） ====================
interface RefItem { type: 'diary' | 'todo'; id: number; label: string; content: string }
const refChips = ref<RefItem[]>([])
const showRefSearch = ref(false)
const showSkillPanel = ref(false)
const refKeyword = ref('')
const refResults = ref<RefItem[]>([])
const refSearching = ref(false)
let refSearchTimer: ReturnType<typeof setTimeout> | null = null

const onInputTrigger = (e: Event) => {
  autoGrow(e)
  // 输入 @ 触发引用搜索
  if (input.value.endsWith('@')) openRefSearch()
}

const openRefSearch = () => {
  showRefSearch.value = true
  refKeyword.value = ''
  refResults.value = []
}

const closeRefSearch = () => { showRefSearch.value = false }

const searchRefs = () => {
  if (refSearchTimer) clearTimeout(refSearchTimer)
  refSearchTimer = setTimeout(async () => {
    refSearching.value = true
    const kw = refKeyword.value.trim()
    try {
      const [diaryRes, todoRes] = await Promise.all([
        fetch(`${DIARY_API}?keyword=${encodeURIComponent(kw)}&limit=5`).then(r => r.ok ? r.json() : { items: [] }),
        fetch(`${TODO_API_BASE}?keyword=${encodeURIComponent(kw)}&limit=5`).then(r => r.ok ? r.json() : { items: [] }),
      ])
      refResults.value = [
        ...(diaryRes.items || []).map((d: any) => ({
          type: 'diary' as const, id: d.id,
          label: `${d.date} ${d.title || '日记'}`,
          content: (d.content || '').slice(0, 800),
        })),
        ...(todoRes.items || []).map((t: any) => ({
          type: 'todo' as const, id: t.id,
          label: t.title,
          content: `待办「${t.title}」状态 ${t.status}${t.description ? '：' + t.description.slice(0, 300) : ''}`,
        })),
      ]
    } catch { /* 静默 */ }
    refSearching.value = false
  }, 250)
}

const pickRef = (item: RefItem) => {
  if (!refChips.value.some(c => c.type === item.type && c.id === item.id)) {
    refChips.value.push(item)
  }
  // 去掉触发用的 @
  if (input.value.endsWith('@')) input.value = input.value.slice(0, -1)
  closeRefSearch()
}

const removeRefChip = (i: number) => refChips.value.splice(i, 1)

// ==================== 提问卡片入对话流（空态待答） ====================
const pendingAnswers = ref<Record<number, string>>({})
const pendingSaving = ref<number | null>(null)
const loadPendingQuestions = () => refreshPendingQuestions()

const answerPending = async (q: { id: number; question: string }) => {
  const ans = (pendingAnswers.value[q.id] || '').trim()
  if (!ans) return
  pendingSaving.value = q.id
  try {
    await answerQuestion(q.id, ans)
    input.value = `/教练 关于「${q.question}」，我的回答是：${ans}`
    send()
  } catch { /* 静默 */ }
  pendingSaving.value = null
}

const dismissPending = async (q: { id: number }) => {
  try {
    await dismissQuestion(q.id)
  } catch { /* 静默 */ }
}

// ==================== 生命周期 ====================
const chatRoot = ref<HTMLElement | null>(null)

/** 手机键盘弹出时，把对话区钉在可视区域里，避免输入框被顶出屏幕 */
function syncChatViewport() {
  const root = chatRoot.value
  const vv = window.visualViewport
  if (!root || !vv) return
  if (window.innerWidth > 640) {
    root.style.height = ''
    root.style.top = ''
    return
  }
  root.style.height = `${vv.height}px`
  root.style.top = `${vv.offsetTop}px`
}

onMounted(async () => {
  outboxCount.value = readOutbox().length
  if (!input.value) input.value = localStorage.getItem(DRAFT_KEY) || ''
  window.addEventListener('online', flushOutbox)
  window.addEventListener('keydown', onPeekEscape)
  flushOutbox()
  const vv = window.visualViewport
  if (vv) {
    vv.addEventListener('resize', syncChatViewport)
    vv.addEventListener('scroll', syncChatViewport)
    syncChatViewport()
  }
  await loadSessions()
  const sessionQ = Number(route.query.session || 0)
  if (sessionQ) await selectSession(sessionQ)
  loadPendingQuestions()
  loadSkillCommands()
  try {
    const res = await fetch(`${CHAT_API_BASE}/ai-config`)
    if (res.ok) aiConfigs.value = await res.json()
  } catch { /* 静默 */ }

  // 深挖入口：?origin=diary:123 / note:456 / question:789 → 建教练会话（服务端注入来源摘录）
  const originQ = route.query.origin as string | undefined
  if (originQ) {
    const [originType, originIdStr] = originQ.split(':')
    const originId = parseInt(originIdStr)
    if (['diary', 'note', 'question'].includes(originType) && originId) {
      pendingOrigin.value = { origin_type: originType, origin_id: originId }
      const originLabels: Record<string, string> = { diary: '这篇日记', note: '这条笔记', question: '这个提问' }
      input.value = `/教练 我想就${originLabels[originType]}深挖，请你以教练身份向我提问，帮我看到背后的全貌和盲区。`
      send()
      return
    }
  }

  // 教练深挖迁入：?prompt= 自动发送首条消息
  const prompt = route.query.prompt as string | undefined
  if (prompt) {
    const text = decodeURIComponent(prompt)
    input.value = text
    send()
  } else if (route.query.prefill) {
    // ?prefill= 只填充输入框不发送（如日记页「写新日记」填入 /日记 前缀）
    input.value = decodeURIComponent(route.query.prefill as string)
    nextTick(() => {
      const el = document.querySelector<HTMLTextAreaElement>('.agent-chat__input')
      el?.focus()
      el?.setSelectionRange(input.value.length, input.value.length)
    })
  }
})

watch(input, (value) => {
  if (value) localStorage.setItem(DRAFT_KEY, value)
  else localStorage.removeItem(DRAFT_KEY)
})

onUnmounted(() => {
  window.removeEventListener('online', flushOutbox)
  window.removeEventListener('keydown', onPeekEscape)
  abortController?.abort()
  const vv = window.visualViewport
  if (vv) {
    vv.removeEventListener('resize', syncChatViewport)
    vv.removeEventListener('scroll', syncChatViewport)
  }
})
</script>

<template>
  <div ref="chatRoot" class="agent-chat">
    <!-- 移动端顶部栏 -->
    <div class="agent-chat__mobilebar">
      <button class="agent-chat__hamburger agent-chat__back" title="返回待办" @click="$router.push('/todo/calendar')"><ArrowLeft class="ep-icon" /></button>
      <button class="agent-chat__hamburger" @click="sidebarOpen = true"><Menu class="ep-icon" /></button>
      <span class="agent-chat__mobilebar-title">AI 助手</span>
    </div>

    <!-- 左侧会话列表（移动端抽屉 / 桌面端可折叠） -->
    <aside class="agent-chat__sidebar" :class="{ 'agent-chat__sidebar--open': sidebarOpen, 'agent-chat__sidebar--collapsed': sidebarCollapsed }">
      <div class="agent-chat__sidebar-head">
        <button class="agent-chat__new-btn" @click="newSession"><Plus class="ep-icon" /> 新对话</button>
        <button class="agent-chat__sidebar-collapse" title="折叠侧栏" @click="sidebarCollapsed = true">«</button>
        <button class="agent-chat__drawer-close" @click="sidebarOpen = false"><Close class="ep-icon" /></button>
      </div>

      <div class="agent-chat__model-picker">
        <label>模型</label>
        <select v-model="selectedConfigId" class="agent-chat__model-select" @change="switchModel">
          <option :value="null">跟随全局默认</option>
          <option v-for="c in aiConfigs" :key="c.id" :value="c.id">{{ c.name }}（{{ c.model }}）</option>
        </select>
      </div>

      <div class="agent-chat__session-list">
        <template v-for="group in groupedSessions" :key="group.label">
          <div class="agent-chat__session-group">{{ group.label }}</div>
          <div
            v-for="s in group.items" :key="s.id"
            class="agent-chat__session"
            :class="{ 'agent-chat__session--active': s.id === currentId }"
            @click="selectSession(s.id)"
          >
            <span
              class="agent-chat__session-dot"
              :class="{ 'agent-chat__session-dot--running': s.status === 'running' }"
            ></span>
            <span class="agent-chat__session-title">
              <span v-if="s.mode === 'coach'" class="agent-chat__session-coach" title="教练对话">🎯</span><Compass v-if="s.mode === 'explore'" class="ep-icon agent-chat__session-explore" title="发展评估" />{{ s.title || '新对话' }}
            </span>
            <span class="agent-chat__session-ops">
              <button title="改名" @click.stop="renameSession(s)"><EditPen class="ep-icon" /></button>
              <button title="删除" @click.stop="deleteSession(s.id)"><Delete class="ep-icon" /></button>
            </span>
          </div>
        </template>
        <div v-if="sessions.length === 0" class="agent-chat__session-empty">还没有会话，说点什么吧</div>
      </div>
    </aside>
    <button v-if="sidebarCollapsed" class="agent-chat__sidebar-expand" title="展开侧栏" @click="sidebarCollapsed = false">»</button>
    <div v-if="sidebarOpen" class="agent-chat__drawer-mask" @click="sidebarOpen = false"></div>

    <!-- 右侧对话流 -->
    <main class="agent-chat__main">
      <!-- 教练模式横幅 -->
      <div v-if="currentMode === 'coach'" class="coach-banner">
        <span class="coach-banner__tag">🎯 教练模式</span>
        <span class="coach-banner__hint">多提问少说教；结束时可沉淀洞察到画像</span>
        <button
          v-if="!coachSummary"
          class="coach-banner__btn"
          :disabled="finalizing || sending || messages.length === 0"
          @click="finalizeCoach"
        >{{ finalizing ? '沉淀中...' : '结束并沉淀' }}</button>
      </div>
      <!-- 沉淀结果卡 -->
      <div v-if="currentMode === 'explore'" class="explore-banner">
        <Compass class="ep-icon" />
        <span class="explore-banner__tag">探索模式</span>
        <span class="explore-banner__hint">一次一问，心智、身体、精神、志业；结束时生成评估，写入要你点</span>
        <button
          v-if="!exploreReport"
          class="explore-banner__btn"
          :disabled="finalizing || sending || messages.length === 0"
          @click="finalizeExplore"
        >{{ finalizing ? '生成中...' : '结束并生成评估' }}</button>
      </div>
      <div v-if="exploreReport" class="explore-report">
        <div class="explore-report__title"><Compass class="ep-icon" /> 发展评估</div>
        <ul v-if="exploreReport.insights.length" class="explore-report__insights">
          <li v-for="(ins, i) in exploreReport.insights" :key="i">{{ ins }}</li>
        </ul>
        <div class="explore-report__body" v-html="renderMd(exploreReport.summary || '')"></div>
        <div class="explore-report__actions">
          <button class="explore-report__btn" :disabled="!!exploreReport.diary_id || exploreSaving === 'diary'" @click="saveExploreDiary">
            {{ exploreReport.diary_id ? `已写入日记 #${exploreReport.diary_id}` : (exploreSaving === 'diary' ? '写入中...' : '写入日记') }}
          </button>
          <button
            v-if="exploreReport.todo_draft"
            class="explore-report__btn explore-report__btn--todo"
            :disabled="!!exploreReport.todo_id || exploreSaving === 'todo'"
            @click="saveExploreTodo"
          >
            {{ exploreReport.todo_id ? `已建成待办 #${exploreReport.todo_id}` : (exploreSaving === 'todo' ? '创建中...' : `建成待办：${exploreReport.todo_draft.title}`) }}
          </button>
        </div>
        <div v-if="exploreReport.profile_updates.length" class="explore-report__profiles">
          <div class="explore-report__profile-title">写入画像（矛盾项默认不勾）</div>
          <label v-for="(item, i) in exploreReport.profile_updates" :key="i" class="explore-report__profile">
            <input type="checkbox" v-model="profileChecked[i]" :disabled="item.applied" />
            <span>
              <b>{{ item.category }} / {{ item.key }}</b>：{{ item.value }}
              <span v-if="item.conflict" class="explore-report__conflict">已有「{{ item.existing_value }}」，勾选才会覆盖</span>
              <span v-if="item.applied" class="explore-report__applied">已写入</span>
            </span>
          </label>
          <button class="explore-report__btn" :disabled="exploreSaving === 'profile'" @click="saveExploreProfile">
            {{ exploreSaving === 'profile' ? '写入中...' : '写入勾选的画像' }}
          </button>
        </div>
      </div>
      <div v-if="coachSummary" class="coach-summary">
        <div class="coach-summary__title">🎯 本次沉淀</div>
        <p class="coach-summary__text">{{ coachSummary.summary }}</p>
        <ul v-if="coachSummary.insights.length" class="coach-summary__insights">
          <li v-for="(ins, i) in coachSummary.insights" :key="i">💡 {{ ins }}</li>
        </ul>
        <!-- 跟进项：承诺 + 待建任务草稿（点了才真建，fail-closed） -->
        <div v-for="(f, fi) in (coachSummary.followups || [])" :key="fi" class="coach-summary__commitment">
          🎯 承诺的下一步：{{ f.text }}
          <span v-if="f.review_on" class="coach-summary__followup-tip">回看日 {{ f.review_on }}</span>
          <div v-if="f.todo_draft && !f.todo_id" class="coach-summary__todo-draft">
            <span class="coach-summary__draft-title">📋 可建成待办：{{ f.todo_draft.title }}</span>
            <button class="coach-summary__build-btn" :disabled="buildingTodo === fi" @click="buildFollowupTodo(fi)">
              {{ buildingTodo === fi ? '创建中…' : '建成待办' }}
            </button>
          </div>
          <div v-else-if="f.todo_id" class="coach-summary__todo-built">✅ 已关联待办 #{{ f.todo_id }}</div>
        </div>
      </div>
      <div ref="messagesEl" class="agent-chat__messages" @scroll.passive="onMessagesScroll">
        <div v-if="messages.length === 0" class="agent-chat__empty">
          <div class="agent-chat__empty-icon"><Bot class="ep-icon" /></div>
          <p class="agent-chat__empty-title">我是你的 AI 助手，连着你的整个 Daily 系统</p>
          <p class="agent-chat__empty-desc">可以直接问我：<br>「总结上个月我做了什么，不要评价，只总结」<br>「把下面这些整理成本周任务单」<br>我会查你的真实数据、拆成可编辑的任务单。</p>

          <!-- 待答问题卡片（AI 提问队列融入对话流） -->
          <div v-if="pendingQuestions.length > 0" class="pending-questions">
            <div class="pending-questions__title"><ChatDotRound class="ep-icon" /> AI 想了解你（{{ pendingQuestions.length }}）</div>
            <div v-for="q in pendingQuestions" :key="q.id" class="pending-questions__item">
              <div class="pending-questions__q">{{ q.question }}</div>
              <div class="pending-questions__row">
                <input
                  v-model="pendingAnswers[q.id]"
                  class="pending-questions__input"
                  placeholder="输入回答，Enter 提交"
                  :disabled="pendingSaving === q.id"
                  @keydown.enter="answerPending(q)"
                />
                <button class="pending-questions__send" :disabled="!(pendingAnswers[q.id] || '').trim() || pendingSaving === q.id" @click="answerPending(q)">提交</button>
                <button class="pending-questions__dismiss" @click="dismissPending(q)">忽略</button>
              </div>
            </div>
          </div>
        </div>

        <div
          v-for="(msg, idx) in messages" :key="idx"
          class="agent-chat__msg"
          :class="`agent-chat__msg--${msg.role}`"
        >
          <template v-if="msg.role === 'user'">
            <div class="agent-chat__turn">
              <div
                class="agent-chat__bubble agent-chat__bubble--user"
                :class="{ 'agent-chat__bubble--queued': msg.queued }"
              >
                {{ msg.content }}
                <div v-if="msg.images?.length" class="agent-chat__imgs">
                  <img v-for="(url, i) in msg.images" :key="i" :src="imageSrc(url)" alt="" loading="lazy" />
                </div>
                <span v-if="msg.queued" class="agent-chat__queued-tag">
                  排队中
                  <button class="agent-chat__queued-cancel" title="撤销这条插话" @click="cancelSteer(msg)">×</button>
                </span>
              </div>
              <div v-if="!msg.queued && msg.content" class="agent-chat__actions">
                <button type="button" title="复制" @click="copyText(msg.content)"><DocumentCopy class="ep-icon" /></button>
                <button type="button" title="编辑后重发" @click="editUserMessage(msg, idx)"><Edit class="ep-icon" /></button>
                <button v-if="msg.seq" type="button" title="重新生成" @click="regenerateFrom(msg)"><RefreshRight class="ep-icon" /></button>
              </div>
            </div>
          </template>
          <template v-else>
            <div class="agent-chat__assistant">
              <ThinkingRow v-if="msg.thinking" :thinking="msg.thinking" :streaming="!!msg.streaming" />
              <ToolCallCard
                v-for="(tc, i) in msg.toolCalls" :key="i"
                :name="tc.name"
                :args="tc.args"
                :summary="tc.summary"
                :error="tc.error"
                :running="tc.running"
                @open-record="openRecord"
              />
              <div v-if="msg.content" class="agent-chat__bubble agent-chat__bubble--assistant" @click="openRecordLink" v-html="renderMd(msg.content)"></div>
              <div v-if="msg.content && !msg.streaming" class="agent-chat__actions">
                <button type="button" title="复制" @click="copyText(msg.content)"><DocumentCopy class="ep-icon" /></button>
                <button
                  v-if="previousUser(idx)?.seq"
                  type="button"
                  title="重新生成"
                  @click="regenerateFrom(previousUser(idx)!)"
                ><RefreshRight class="ep-icon" /></button>
              </div>
              <div v-else-if="msg.streaming" class="agent-chat__bubble agent-chat__bubble--assistant agent-chat__bubble--waiting">
                <span class="agent-chat__wait-dot">●</span><span class="agent-chat__wait-dot">●</span><span class="agent-chat__wait-dot">●</span>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- 用户上翻时的「回到底部」浮钮 -->
      <button v-if="hasNewBelow && userScrolledUp" class="jump-latest" @click="jumpToLatest">
        ↓ 有新内容
      </button>

      <div v-if="notice" class="agent-chat__notice">{{ notice }}<button type="button" @click="notice = ''">×</button></div>
      <div v-if="outboxCount" class="agent-chat__notice">有 {{ outboxCount }} 条内容在本地等着入库</div>
      <div v-if="error" class="agent-chat__error">{{ error }}</div>

      <!-- 任务单草稿（可编辑，确认后才创建待办） -->
      <div v-if="tasklistDraft" class="tasklist-card">
        <div class="tasklist-card__head">
          <strong>📋 任务单草稿</strong>
          <span>改标题 / 增删 / 把子任务提升为独立任务，确认后再创建</span>
        </div>
        <div v-for="(g, gi) in tasklistDraft" :key="gi" class="tasklist-card__group">
          <div class="tasklist-card__row">
            <span class="tasklist-card__badge">父</span>
            <input v-model="g.parent" class="tasklist-card__input" placeholder="父任务标题" />
            <select v-model.number="g.quadrant" class="tasklist-card__select" title="象限">
              <option :value="1">重要紧急</option><option :value="2">重要不紧急</option>
              <option :value="3">紧急不重要</option><option :value="4">不重要不紧急</option>
            </select>
            <select v-model.number="g.urgency" class="tasklist-card__select" title="紧急度">
              <option :value="5">紧急5</option><option :value="4">紧急4</option>
              <option :value="3">紧急3</option><option :value="2">紧急2</option><option :value="1">紧急1</option>
            </select>
            <button class="tasklist-card__x" title="删除这组" @click="removeTasklistGroup(gi)">×</button>
          </div>
          <div v-for="(c, ci) in g.children" :key="ci" class="tasklist-card__row tasklist-card__row--child">
            <span class="tasklist-card__badge tasklist-card__badge--child">子</span>
            <input v-model="c.title" class="tasklist-card__input" placeholder="子任务标题" />
            <select v-model.number="c.urgency" class="tasklist-card__select" title="紧急度">
              <option :value="5">紧急5</option><option :value="4">紧急4</option>
              <option :value="3">紧急3</option><option :value="2">紧急2</option><option :value="1">紧急1</option>
            </select>
            <button class="tasklist-card__mini" title="提升为独立父任务" @click="promoteChild(gi, ci)">↑独立</button>
            <button class="tasklist-card__x" title="删除" @click="removeTasklistChild(g, ci)">×</button>
          </div>
          <button class="tasklist-card__add" @click="addTasklistChild(g)">+ 子任务</button>
        </div>
        <div class="tasklist-card__ops">
          <button class="tasklist-card__add" @click="addTasklistGroup">+ 新增一组</button>
          <span class="tasklist-card__spacer"></span>
          <button class="tasklist-card__cancel" @click="tasklistDraft = null">放弃</button>
          <button class="tasklist-card__create" :disabled="tasklistSaving || !tasklistDraft.some(g => g.parent.trim())" @click="createTasklist">
            {{ tasklistSaving ? '创建中…' : '确认创建任务' }}
          </button>
        </div>
      </div>

      <!-- 澄清提问卡（harness AskUserQuestion 式：可折叠 + 字母选项行 + 自定义回答） -->
      <div v-if="clarifyCard" class="clarify-card">
        <button class="clarify-card__header" @click="clarifyCollapsed = !clarifyCollapsed">
          <span class="clarify-card__header-icon">?</span>
          <span>想多了解你一点</span>
          <span class="clarify-card__chevron" :class="{ 'clarify-card__chevron--open': !clarifyCollapsed }">⌄</span>
        </button>
        <template v-if="!clarifyCollapsed">
          <div v-for="(q, qi) in clarifyCard.questions" :key="qi" class="clarify-card__q">
            <div class="clarify-card__question">{{ q.question }}</div>
            <button
              v-for="(opt, oi) in q.options" :key="opt"
              class="clarify-card__row"
              :class="{ 'clarify-card__row--on': q.answer === opt }"
              @click="pickOption(q, opt)"
            >
              <span class="clarify-card__letter" :class="{ 'clarify-card__letter--on': q.answer === opt }">{{ OPTION_LETTERS[oi] }}</span>
              <span class="clarify-card__row-label">{{ opt }}</span>
              <span class="clarify-card__row-arrow">›</span>
            </button>
            <!-- 自定义回答行 -->
            <button
              class="clarify-card__row"
              :class="{ 'clarify-card__row--on': q.customOpen }"
              @click="toggleCustom(q)"
            >
              <span class="clarify-card__letter" :class="{ 'clarify-card__letter--on': q.customOpen }">{{ OPTION_LETTERS[q.options.length] || '✎' }}</span>
              <span class="clarify-card__row-label clarify-card__row-label--dim">输入自定义回答…</span>
              <span class="clarify-card__row-arrow">›</span>
            </button>
            <textarea
              v-if="q.customOpen"
              v-model="q.answer"
              class="clarify-card__input"
              placeholder="直接说说…"
              rows="2"
              autofocus
            ></textarea>
          </div>
          <div class="clarify-card__ops">
            <button
              class="clarify-card__submit"
              :disabled="submittingAnswers || !clarifyCard.questions.some(q => q.answer.trim())"
              @click="submitAnswers"
            >{{ submittingAnswers ? '提交中…' : '提交回答' }}</button>
            <button class="clarify-card__skip" @click="skipQuestions">先不答</button>
          </div>
        </template>
      </div>

      <!-- 写操作确认卡（fail-closed：不确认不执行） -->
      <div v-if="pendingConfirm" class="confirm-card">
        <div class="confirm-card__title"><Warning class="ep-icon" /> AI 想要执行写操作</div>
        <div class="confirm-card__body">{{ toolLabel(pendingConfirm.name) }}：{{ confirmSummary }}</div>
        <!-- 记录类确认卡：展示情绪/标签/关键问题/行动建议（恢复旧版分析体验） -->
        <div v-if="pendingConfirm.name === '__save_record' && (pendingConfirm.args.mood || pendingConfirm.args.tags?.length)" class="confirm-card__meta">
          <div v-if="pendingConfirm.args.mood" class="confirm-card__mood">😊 {{ pendingConfirm.args.mood }}</div>
          <div v-if="pendingConfirm.args.tags?.length" class="confirm-card__tags">
            <span v-for="t in pendingConfirm.args.tags" :key="t">#{{ t }}</span>
          </div>
          <div v-if="pendingConfirm.args.key_issues?.length" class="confirm-card__list">
            <strong>关键问题</strong>
            <ul><li v-for="i in pendingConfirm.args.key_issues" :key="i">{{ i }}</li></ul>
          </div>
          <div v-if="pendingConfirm.args.action_items?.length" class="confirm-card__list">
            <strong>行动建议</strong>
            <ul><li v-for="i in pendingConfirm.args.action_items" :key="i">{{ i }}</li></ul>
          </div>
        </div>
        <div class="confirm-card__ops">
          <button class="confirm-card__btn confirm-card__btn--allow" @click="respondConfirm(true)">允许执行</button>
          <button class="confirm-card__btn confirm-card__btn--reject" @click="respondConfirm(false)">拒绝</button>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="agent-chat__input-wrap">
        <!-- 快捷指令行（承接日报/周报等原单发功能） -->
        <div class="agent-chat__quick-cmds">
          <button
            v-for="cmd in quickCommands" :key="cmd.prefix"
            class="agent-chat__quick-cmd"
            :disabled="sending"
            :title="`句首加入「${cmd.label}」前缀，不覆盖已有内容`"
            @click="runQuickCommand(cmd)"
          >{{ cmd.label }}</button>
          <button class="agent-chat__quick-cmd agent-chat__quick-cmd--ref" :disabled="sending" @click="openRefSearch" title="引用一篇日记或一条待办给 AI 看">
            <Link class="ep-icon" /> 引用
          </button>
          <button class="agent-chat__quick-cmd" :disabled="sending" title="查看/编辑/新建 Skill" @click="showSkillPanel = true">
            🧩 Skill
          </button>
        </div>

        <!-- 引用 chips -->
        <div v-if="refChips.length" class="agent-chat__chips">
          <span v-for="(c, i) in refChips" :key="i" class="agent-chat__chip">
            <Link class="ep-icon" /> {{ c.label }}
            <button class="agent-chat__chip-del" @click="removeRefChip(i)"><Close class="ep-icon" /></button>
          </span>
        </div>

        <div v-if="pendingImages.length" class="agent-chat__pending-imgs">
          <span v-for="(url, i) in pendingImages" :key="url" class="agent-chat__pending-img">
            <img :src="imageSrc(url)" alt="" />
            <button type="button" @click="removePendingImage(i)">×</button>
          </span>
          <span v-if="imageUploading" class="agent-chat__pending-tip">上传中...</span>
        </div>

        <div class="agent-chat__input-area">
          <!-- 句首前缀 chip（快捷指令/管线入口，不覆盖已有内容） -->
          <span v-if="prefixChip" class="prefix-chip">
            {{ prefixChip.label }}
            <button class="prefix-chip__x" title="移除前缀" @click="clearPrefixChip">×</button>
          </span>
          <!-- "/" 命令面板 -->
          <div v-if="showSlash" class="slash-panel">
            <button
              v-for="(c, i) in slashMatches" :key="c.prefix"
              class="slash-panel__item"
              :class="{ 'slash-panel__item--active': i === slashIndex }"
              @click="pickSlash(c)"
            >
              <span class="slash-panel__cmd">{{ c.prefix }}</span>
              <span class="slash-panel__desc">{{ { '日报': '生成今天的日报', '周报': '生成本周周报', '月报': '生成本月总结', '复盘': '本周结构化复盘', '教练': '进入教练对话模式', '探索': '四象限发展评估，一次一问', '日记': '分析并保存为日记', '笔记': '分析并保存读书笔记', '课程': '保存听课/课程内容（可带讲师平台）', '随笔': '保存个人随笔/想法', '心力': '记一条成就或感恩', '待办': '创建一条待办任务', '任务单': '把一段内容拆成父子任务草稿，确认后创建待办', '知识': '把一条知识收进知识库', '投资': '保存投资反思记录' }[c.label] }}</span>
            </button>
          </div>
          <textarea
            v-model="input"
            class="agent-chat__input"
            placeholder="问点什么；可粘贴多张图片，只随文字保存、不做分析；输入 / 快捷指令"
            rows="1"
            @paste="onPasteImage"
            @input="onInputTrigger"
            @keydown="onInputKeydown"
            @keydown.enter.exact.prevent="onEnter"
          ></textarea>
          <input ref="imageInput" class="agent-chat__file" type="file" accept="image/*" multiple @change="onPickImages" />
          <button class="agent-chat__img-btn" type="button" title="添加图片" :disabled="sending || pendingImages.length >= MAX_CHAT_IMAGES" @click="imageInput?.click()">
            <Picture class="ep-icon" />
          </button>
          <button v-if="sending" class="agent-chat__stop" @click="stop" title="停止">
            <span>⏹</span>
          </button>
          <button
            class="agent-chat__save"
            type="button"
            :disabled="sending || imageUploading || (!input.trim() && !prefixChip)"
            title="不经过 AI，直接保存。没网时先存在本地"
            @click="saveDirect"
          >直接保存</button>
          <button
            class="agent-chat__send"
            :class="{ 'agent-chat__send--steer': sending }"
            :disabled="(!input.trim() && !prefixChip && !pendingImages.length) || imageUploading"
            :title="sending ? '插话：AI 本轮结束后会看到' : '发送'"
            @click="send"
          >
            <Promotion v-if="!sending" class="ep-icon" />
            <span v-else class="agent-chat__steer-text">插话</span>
          </button>
        </div>

        <!-- Skill 快捷编辑/新建 -->
        <SkillPanel v-if="showSkillPanel" @close="showSkillPanel = false; loadSkillCommands()" />

        <!-- @引用搜索弹窗 -->
        <div v-if="showRefSearch" class="ref-search">
          <div class="ref-search__head">
            <input
              v-model="refKeyword"
              class="ref-search__input"
              placeholder="搜索日记 / 待办..."
              @input="searchRefs"
              autofocus
            />
            <button class="ref-search__close" @click="closeRefSearch"><Close class="ep-icon" /></button>
          </div>
          <div class="ref-search__results">
            <div v-if="refSearching" class="ref-search__hint">搜索中...</div>
            <div v-else-if="refResults.length === 0" class="ref-search__hint">
              {{ refKeyword ? '没有匹配的记录' : '输入关键词搜索日记和待办' }}
            </div>
            <button
              v-for="r in refResults" :key="`${r.type}-${r.id}`"
              class="ref-search__item"
              @click="pickRef(r)"
            >
              <span class="ref-search__type" :class="`ref-search__type--${r.type}`">{{ r.type === 'diary' ? '日记' : '待办' }}</span>
              {{ r.label }}
            </button>
          </div>
        </div>
      </div>
    </main>
  </div>

  <TodoPeekPanel :todo-id="peekTodoId" @close="peekTodoId = null" />
</template>

<style scoped lang="scss">
.agent-chat {
  display: flex;
  height: calc(100vh - 80px);
  min-height: 0;
  background: transparent;

  // ==================== 移动端顶栏 ====================
  &__mobilebar {
    display: none;
  }

  // ==================== 左侧会话列表 ====================
  &__sidebar {
    width: 240px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    border-right: 1px solid $border-color;
    background: rgba(255, 255, 255, 0.5);
    backdrop-filter: blur(8px);

    &--collapsed { display: none; }  // 桌面端折叠
  }

  &__sidebar-head {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: $spacing-md;
  }

  &__sidebar-collapse, &__sidebar-expand {
    border: 1px solid $border-color;
    background: rgba(255,255,255,0.8);
    color: $text-muted;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    line-height: 1;
    padding: 4px 8px;
    &:hover { color: $primary-color; border-color: $primary-color; }
  }
  &__sidebar-expand {
    position: absolute;
    top: 12px;
    left: 8px;
    z-index: 12;
  }

  &__session-group {
    padding: 10px 8px 4px;
    font-size: 10px;
    font-weight: 700;
    color: $text-muted;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }

  &__new-btn {
    flex: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    padding: 8px;
    border: none;
    border-radius: $border-radius-md;
    background: $primary-color;
    color: #fff;
    font-size: $font-size-sm;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    &:hover { opacity: 0.88; }
  }

  &__drawer-close { display: none; }

  &__model-picker {
    padding: 0 $spacing-md $spacing-md;
    label { display: block; font-size: 11px; color: $text-muted; margin-bottom: 4px; }
  }

  &__model-select {
    width: 100%;
    padding: 6px 8px;
    border: 1px solid $border-color;
    border-radius: 6px;
    font-size: 12px;
    background: #fff;
    outline: none;
    &:focus { border-color: $primary-color; }
  }

  &__session-list {
    flex: 1;
    overflow-y: auto;
    padding: 0 $spacing-sm $spacing-md;
  }

  &__session {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 10px;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s;

    &:hover { background: rgba($primary-color, 0.06); }
    &--active { background: rgba($primary-color, 0.1); }
  }

  &__session-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #D1D5DB;
    flex-shrink: 0;
    &--running { background: #3B82F6; animation: dot-blink 1s infinite; }
  }

  @keyframes dot-blink { 50% { opacity: 0.3; } }

  &__session-title {
    flex: 1;
    min-width: 0;
    font-size: $font-size-sm;
    color: $text-primary;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__session-ops {
    display: none;
    gap: 2px;
    flex-shrink: 0;

    button {
      background: none;
      border: none;
      color: $text-muted;
      cursor: pointer;
      padding: 2px;
      border-radius: 4px;
      &:hover { color: $text-primary; background: rgba(0, 0, 0, 0.05); }
    }
  }

  &__session:hover &__session-ops { display: flex; }

  &__session-empty {
    padding: $spacing-md;
    font-size: $font-size-xs;
    color: $text-muted;
    text-align: center;
  }

  // ==================== 右侧对话流 ====================
  &__main {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    position: relative;  // 「回到底部」浮钮定位基准
    overflow: hidden;
  }

  &__messages {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: $spacing-lg;
    display: flex;
    flex-direction: column;
    gap: $spacing-md;
  }

  &__empty {
    margin: auto;
    text-align: center;
    max-width: 420px;
    padding: $spacing-xl;
  }

  &__empty-icon {
    font-size: 40px;
    color: $primary-color;
    margin-bottom: $spacing-md;
    .ep-icon { width: 44px; height: 44px; }
  }

  &__empty-title { font-size: $font-size-md; font-weight: 600; color: $text-primary; margin-bottom: $spacing-sm; }
  &__empty-desc { font-size: $font-size-sm; color: $text-secondary; line-height: 1.8; }

  &__msg {
    display: flex;

    &--user { justify-content: flex-end; }
  }

  &__bubble {
    max-width: 78%;
    padding: 10px 14px;
    border-radius: 14px;
    font-size: $font-size-sm;
    line-height: 1.7;
    word-break: break-word;
    overflow-wrap: anywhere;

    :deep(pre), :deep(table) { max-width: 100%; overflow-x: auto; }
    :deep(img) { max-width: 100%; height: auto; }

    &--user {
      background: linear-gradient(135deg, rgba($primary-color, 0.12), rgba($primary-color, 0.18));
      border: 1px solid rgba($primary-color, 0.25);
      color: $text-primary;
      border-bottom-right-radius: 4px;
      white-space: pre-wrap;
    }

    &--assistant {
      background: rgba(255, 255, 255, 0.85);
      border: 1px solid $border-color;
      border-bottom-left-radius: 4px;
      color: $text-primary;

      :deep(p) { margin: 0 0 8px; &:last-child { margin-bottom: 0; } }
      :deep(ul), :deep(ol) { padding-left: 18px; margin: 6px 0; }
      :deep(h1), :deep(h2), :deep(h3) { font-size: 15px; margin: 10px 0 6px; }
      :deep(code) { background: rgba(0,0,0,0.05); padding: 1px 5px; border-radius: 4px; font-size: 12px; }
    }

    &--waiting { display: flex; gap: 4px; }
  }

  &__wait-dot {
    color: $text-muted;
    animation: wait-blink 1.2s infinite;
    &:nth-child(2) { animation-delay: 0.2s; }
    &:nth-child(3) { animation-delay: 0.4s; }
  }

  @keyframes wait-blink { 50% { opacity: 0.2; } }

  &__assistant {
    max-width: 85%;
    min-width: 0;
  }

  &__error {
    margin: 0 $spacing-lg $spacing-sm;
    padding: 8px 12px;
    border-radius: 8px;
    background: rgba(#EF4444, 0.08);
    border: 1px solid rgba(#EF4444, 0.25);
    color: #B91C1C;
    font-size: $font-size-sm;
  }

  // ==================== 任务单草稿卡 ====================
  .tasklist-card {
    margin: 0 $spacing-lg $spacing-sm;
    padding: 10px 14px;
    border-radius: 10px;
    background: rgba(#10B981, 0.05);
    border: 1px solid rgba(#10B981, 0.3);

    &__head {
      display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px;
      font-size: 13px; color: #047857;
      span { font-size: 11px; color: $text-muted; font-weight: 400; }
    }
    &__group {
      background: rgba(255,255,255,0.7); border-radius: 8px;
      padding: 6px 8px; margin-bottom: 6px;
    }
    &__row {
      display: flex; align-items: center; gap: 6px; margin-bottom: 4px;
      &--child { padding-left: 14px; }
    }
    &__badge {
      flex-shrink: 0; width: 18px; height: 18px; border-radius: 5px;
      background: rgba(#10B981, 0.15); color: #047857;
      display: inline-flex; align-items: center; justify-content: center;
      font-size: 10px; font-weight: 700;
      &--child { background: rgba(#3B82F6, 0.12); color: #2563EB; }
    }
    &__input {
      flex: 1; min-width: 0; padding: 4px 8px;
      border: 1px solid $border-color; border-radius: 6px;
      font-size: 12px; font-family: inherit;
      &:focus { outline: none; border-color: #10B981; }
    }
    &__select {
      padding: 4px; border: 1px solid $border-color; border-radius: 6px;
      font-size: 11px; max-width: 110px; background: #fff;
    }
    &__x {
      border: none; background: transparent; cursor: pointer;
      color: $text-muted; font-size: 15px; padding: 0 4px;
      &:hover { color: #EF4444; }
    }
    &__mini {
      border: 1px solid $border-color; background: #fff; border-radius: 5px;
      font-size: 10px; padding: 2px 6px; cursor: pointer; color: $text-muted;
      &:hover { color: #2563EB; border-color: #3B82F6; }
    }
    &__add {
      border: none; background: transparent; color: #059669;
      font-size: 11px; cursor: pointer; padding: 2px 4px;
      &:hover { text-decoration: underline; }
    }
    &__ops {
      display: flex; align-items: center; gap: 8px; margin-top: 8px;
      .tasklist-card__add { color: $text-secondary; }
    }
    &__spacer { flex: 1; }
    &__cancel, &__create {
      padding: 5px 14px; border-radius: 7px; font-size: 12px; cursor: pointer; font-weight: 600;
    }
    &__cancel { border: 1px solid $border-color; background: transparent; color: $text-muted; }
    &__create { border: none; background: #10B981; color: #fff; &:disabled { opacity: 0.5; } }
  }

  // ==================== 澄清提问卡（harness AskUserQuestion 列表式） ====================
  .clarify-card {
    margin: 0 $spacing-lg $spacing-sm;
    border-radius: 10px;
    background: rgba(#3B82F6, 0.04);
    border: 1px solid rgba(#3B82F6, 0.28);
    overflow-x: hidden;
    overflow-y: auto;
    max-height: min(42vh, 320px);
    flex-shrink: 1;
    min-height: 0;
    animation: jump-in 0.2s ease;

    &__header {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      padding: 10px 14px;
      border: none;
      background: transparent;
      font-size: 13px;
      font-weight: 600;
      color: #2563EB;
      cursor: pointer;
      text-align: left;

      &:hover { background: rgba(#3B82F6, 0.06); }
    }

    &__header-icon {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      border: 1.5px solid #3B82F6;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      flex-shrink: 0;
    }

    &__chevron {
      margin-left: auto;
      transition: transform 0.2s;
      font-size: 14px;
      color: $text-muted;

      &--open { transform: rotate(180deg); }
    }

    &__q {
      padding: 0 12px 10px;
    }

    &__question {
      font-size: 13px;
      color: $text-primary;
      margin: 2px 2px 8px;
      line-height: 1.5;
    }

    // 选项行：全宽列表行 + 字母徽章 + 右箭头
    &__row {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
      padding: 9px 12px;
      border: 1px solid $border-color;
      border-radius: 8px;
      background: #fff;
      cursor: pointer;
      text-align: left;
      margin-bottom: 6px;
      transition: all 0.15s;

      &:hover { border-color: #3B82F6; background: rgba(#3B82F6, 0.04); }
      &--on { border-color: #3B82F6; background: rgba(#3B82F6, 0.08); }
    }

    &__letter {
      width: 22px;
      height: 22px;
      border-radius: 6px;
      background: rgba(0, 0, 0, 0.05);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      font-weight: 700;
      color: $text-muted;
      flex-shrink: 0;

      &--on { background: #3B82F6; color: #fff; }
    }

    &__row-label {
      flex: 1;
      font-size: 13px;
      color: $text-primary;

      &--dim { color: $text-muted; }
    }

    &__row-arrow { color: $text-muted; font-size: 15px; }

    &__input {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid #3B82F6;
      border-radius: 8px;
      font-size: 13px;
      font-family: inherit;
      resize: none;
      background: #fff;
      margin-bottom: 6px;

      &:focus { outline: none; box-shadow: 0 0 0 3px rgba(#3B82F6, 0.15); }
    }

    &__ops {
      display: flex;
      align-items: center;
      gap: $spacing-sm;
      padding: 4px 12px 12px;
    }

    &__submit {
      padding: 6px 18px;
      border: none;
      border-radius: 8px;
      background: #3B82F6;
      color: #fff;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;

      &:hover:not(:disabled) { background: #2563EB; }
      &:disabled { opacity: 0.5; cursor: not-allowed; }
    }

    &__skip {
      padding: 6px 12px;
      border: none;
      background: transparent;
      color: $text-muted;
      font-size: 12px;
      cursor: pointer;

      &:hover { color: $text-secondary; }
    }
  }

  // ==================== 写操作确认卡 ====================
  .confirm-card {
    margin: 0 $spacing-lg $spacing-sm;
    padding: 12px 14px;
    border-radius: 10px;
    background: rgba(#F97316, 0.06);
    border: 1px solid rgba(#F97316, 0.35);
    max-height: min(42vh, 320px);
    overflow-y: auto;
    flex-shrink: 1;
    min-height: 0;

    &__title {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 600;
      color: #C2410C;
      margin-bottom: 6px;
    }

    &__body {
      font-size: 13px;
      color: $text-primary;
      line-height: 1.6;
      margin-bottom: 10px;
      word-break: break-word;
    }

    // 记录类确认卡的结构化摘要（情绪/标签/关键问题/行动建议）
    &__meta {
      margin-bottom: 10px;
      padding: 8px 10px;
      background: rgba(255, 255, 255, 0.6);
      border-radius: 8px;
    }
    &__mood { font-size: 13px; font-weight: 600; color: $text-primary; margin-bottom: 4px; }
    &__tags {
      display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px;
      span { font-size: 11px; color: #8B5CF6; }
    }
    &__list {
      font-size: 12px; color: $text-secondary; margin-top: 6px;
      strong { color: $text-primary; }
      ul { margin: 4px 0 0; padding-left: 18px; }
      li { margin: 2px 0; line-height: 1.5; }
    }

    &__ops { display: flex; gap: 8px; }

    &__btn {
      padding: 6px 16px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.15s;

      &--allow {
        background: #F97316;
        color: #fff;
        &:hover { opacity: 0.88; }
      }

      &--reject {
        background: transparent;
        border-color: $border-color;
        color: $text-secondary;
        &:hover { border-color: $text-muted; color: $text-primary; }
      }
    }
  }

  // ==================== 输入区 ====================
  &__input-area {
    display: flex;
    align-items: flex-end;
    gap: $spacing-sm;
    padding: $spacing-md $spacing-lg;
    border-top: 1px solid $border-color;
    background: rgba(255, 255, 255, 0.6);
    backdrop-filter: blur(8px);
  }

  &__input {
    flex: 1;
    min-width: 0;
    border: 1px solid $border-color;
    border-radius: 12px;
    padding: 10px 14px;
    font-size: $font-size-sm;
    line-height: 1.5;
    background: #fff;
    outline: none;
    resize: none;
    max-height: 200px;
    &:focus { border-color: $primary-color; }
  }

  &__file { display: none; }

  &__img-btn {
    width: 38px;
    height: 38px;
    flex-shrink: 0;
    border: 1px solid $border-color;
    border-radius: 50%;
    background: #fff;
    color: $text-secondary;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    &:disabled { opacity: 0.4; cursor: not-allowed; }
  }

  &__imgs, .agent-chat__pending-imgs {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }

  &__imgs img, .agent-chat__pending-img img {
    max-width: 160px;
    max-height: 120px;
    border-radius: 8px;
    object-fit: cover;
  }

  &__send, &__stop {
    width: 38px;
    height: 38px;
    flex-shrink: 0;
    border: none;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.15s;
  }

  &__send {
    background: $primary-color;
    color: #fff;
    &:hover:not(:disabled) { transform: scale(1.06); }
    &:disabled { opacity: 0.4; cursor: not-allowed; }
  }

  &__stop {
    background: rgba(#EF4444, 0.1);
    border: 1px solid rgba(#EF4444, 0.3);
    color: #EF4444;
  }
}

// ==================== 移动端 ====================
@media (max-width: $breakpoint-sm) {
  .agent-chat {
    flex-direction: column;
    // 全屏覆盖（含全局头部和底部 tab 栏）：此前用 100vh 减固定值，没算 AppHeader
    // 和 app-main 的 padding，输入框被底部 tab 栏遮挡。dvh 适配手机浏览器动态工具栏。
    position: fixed;
    inset: 0;
    height: 100dvh;
    overflow: hidden;
    z-index: 300;
    background: #F5F7FB;

    &__mobilebar {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: $spacing-sm $spacing-md;
      border-bottom: 1px solid $border-color;
      background: rgba(255, 255, 255, 0.7);
    }

    &__hamburger {
      background: none;
      border: none;
      padding: 4px;
      cursor: pointer;
      color: $text-primary;
      display: inline-flex;
    }

    &__mobilebar-title { font-size: $font-size-sm; font-weight: 600; }

    &__sidebar {
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      width: 260px;
      z-index: 400;
      background: #fff;
      transform: translateX(-100%);
      transition: transform 0.25s ease;
      box-shadow: 4px 0 24px rgba(0, 0, 0, 0.12);

      &--open { transform: translateX(0); }
      // 移动端始终是抽屉，桌面端的折叠状态不生效
      &--collapsed { display: flex; }
    }

    &__sidebar-collapse { display: none; }
    &__sidebar-expand { display: none; }

    &__drawer-close {
      display: inline-flex;
      background: none;
      border: none;
      color: $text-muted;
      cursor: pointer;
      padding: 4px;
    }

    &__drawer-mask {
      position: fixed;
      inset: 0;
      z-index: 390;
      background: rgba(0, 0, 0, 0.3);
    }

    &__messages { padding: $spacing-md; }
    &__bubble { max-width: 92%; }
    &__assistant { max-width: 96%; }
    &__input-area { padding: $spacing-sm $spacing-md; }
  }
}

// 「回到底部」浮钮
.jump-latest {
  position: absolute;
  bottom: 148px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 16px;
  border-radius: 99px;
  border: 1px solid rgba($primary-color, 0.3);
  background: rgba(#fff, 0.95);
  backdrop-filter: blur(8px);
  color: $primary-color;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  z-index: 15;
  animation: jump-in 0.2s ease;

  &:hover { background: $primary-color; color: #fff; }
}

@keyframes jump-in {
  from { opacity: 0; transform: translateX(-50%) translateY(6px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}

// ==================== 快捷指令 / 引用 ====================
.agent-chat__pending-img {
  position: relative;
  display: inline-flex;

  button {
    position: absolute;
    top: -6px;
    right: -6px;
    width: 18px;
    height: 18px;
    border: none;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.55);
    color: #fff;
    cursor: pointer;
    line-height: 18px;
  }
}

.agent-chat__input-wrap {
  position: relative;
  flex-shrink: 0;
  border-top: 1px solid $border-color;
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(8px);
}

.agent-chat__quick-cmds {
  display: flex;
  gap: 6px;
  padding: $spacing-sm $spacing-lg 0;
  // 超出横向滚动而不是换行（移动端命令多时保持输入区紧凑）
  flex-wrap: nowrap;
  overflow-x: auto;
  scrollbar-width: none;
  &::-webkit-scrollbar { display: none; }

  .agent-chat__quick-cmd { flex-shrink: 0; }
}

.agent-chat__quick-cmd {
  padding: 3px 12px;
  border-radius: 99px;
  border: 1px solid $border-color;
  background: transparent;
  font-size: 11px;
  color: $text-muted;
  cursor: pointer;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 4px;

  &:hover:not(:disabled) { border-color: $primary-color; color: $primary-color; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.agent-chat__chips {
  display: flex;
  gap: 6px;
  padding: $spacing-sm $spacing-lg 0;
  flex-wrap: wrap;
}

// "/" 命令面板
.agent-chat__input-area {
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: $spacing-xs;
}

// 句首前缀 chip
.prefix-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  padding: 4px 6px 4px 10px;
  margin-bottom: 6px;
  border-radius: 99px;
  background: linear-gradient(135deg, rgba(#EC4899, 0.12), rgba(#8B5CF6, 0.12));
  border: 1px solid rgba(#EC4899, 0.3);
  color: #C2410C;
  font-size: $font-size-xs;
  font-weight: 600;
  animation: chip-in 0.15s ease;

  &__x {
    border: none; background: rgba(0,0,0,0.06); width: 16px; height: 16px;
    border-radius: 50%; cursor: pointer; font-size: 10px; line-height: 1;
    color: $text-muted;
    &:hover { background: rgba(#EF4444, 0.15); color: #EF4444; }
  }
}

@keyframes chip-in {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}

// 撤回按钮（最后一条用户消息悬停显示）
.agent-chat__bubble--user {
  position: relative;

  .agent-chat__recall {
    position: absolute;
    top: -8px;
    right: -8px;
    opacity: 0;
    transition: opacity 0.15s;
    border: none;
    border-radius: 99px;
    background: rgba(0, 0, 0, 0.55);
    color: #fff;
    font-size: 10px;
    padding: 2px 8px;
    cursor: pointer;
    &:hover { background: rgba(#EF4444, 0.85); }
  }
  &:hover .agent-chat__recall { opacity: 1; }
}

.agent-chat__turn { max-width: min(78%, 640px); }
.agent-chat__msg--user .agent-chat__turn { margin-left: auto; }

.agent-chat__actions {
  display: flex;
  gap: 4px;
  margin-top: 4px;

  button {
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: $text-muted;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;

    &:hover { background: rgba(0, 0, 0, 0.06); color: $text-primary; }
  }
}

.agent-chat__msg--user .agent-chat__actions { justify-content: flex-end; }

.agent-chat__notice {
  margin: 0 16px 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba($primary-color, 0.08);
  color: $text-secondary;
  font-size: $font-size-sm;
  display: flex;
  justify-content: space-between;
  align-items: center;

  button { border: none; background: transparent; cursor: pointer; color: $text-muted; }
}

.agent-chat__save {
  min-height: 36px;
  padding: 0 10px;
  border: 1px solid $border-color;
  border-radius: 8px;
  background: #fff;
  color: $text-secondary;
  cursor: pointer;
  font-size: $font-size-xs;
  white-space: nowrap;

  &:disabled { opacity: 0.45; cursor: not-allowed; }
  &:hover:not(:disabled) { border-color: $primary-color; color: $primary-color; }
}

:deep(.record-link) { color: $primary-color; cursor: pointer; }

// 插话排队气泡（半透明）
.agent-chat__bubble--queued {
  opacity: 0.6;
}

.agent-chat__queued-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 8px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.85);
  background: rgba(255, 255, 255, 0.18);
  border-radius: 99px;
  padding: 1px 6px;
}

.agent-chat__queued-cancel {
  border: none; background: transparent; color: #fff; cursor: pointer;
  font-size: 11px; padding: 0; line-height: 1;
  &:hover { color: #FECACA; }
}

// 插话模式的发送键
.agent-chat__send--steer {
  background: linear-gradient(135deg, #3B82F6, #6366F1) !important;
  min-width: 52px;
}

// 教练模式横幅与沉淀卡
.coach-banner {
  display: flex; align-items: center; gap: $spacing-sm;
  padding: $spacing-xs $spacing-lg;
  background: rgba(#F97316, 0.06);
  border-bottom: 1px solid rgba(#F97316, 0.15);

  &__tag { font-size: $font-size-xs; font-weight: 700; color: #C2410C; }
  &__hint { flex: 1; font-size: 10px; color: $text-muted; }
  &__btn {
    border: 1px solid rgba(#F97316, 0.4); background: transparent; color: #C2410C;
    font-size: $font-size-xs; padding: 3px 12px; border-radius: 99px; cursor: pointer;
    &:hover:not(:disabled) { background: rgba(#F97316, 0.1); }
    &:disabled { opacity: 0.5; cursor: not-allowed; }
  }
}

.coach-summary {
  margin: $spacing-md $spacing-lg 0;
  padding: $spacing-md;
  border: 1px solid rgba(#F97316, 0.25);
  border-radius: $border-radius-md;
  background: rgba(#F97316, 0.04);

  &__title { font-size: $font-size-xs; font-weight: 700; color: #C2410C; margin-bottom: 4px; }
  &__text { font-size: $font-size-sm; color: $text-primary; line-height: 1.6; }
  &__insights { margin: 6px 0 0; padding-left: 18px; font-size: $font-size-xs; color: $text-secondary; line-height: 1.8; }

  &__commitment {
    margin-top: 8px; padding: 8px 10px;
    background: rgba(#10B981, 0.08); border-radius: 8px;
    font-size: $font-size-xs; color: #047857; line-height: 1.6;
  }
  &__followup-tip { color: $text-muted; margin-left: 6px; }
  &__todo-draft {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    margin-top: 6px; padding-top: 6px;
    border-top: 1px dashed rgba(#10B981, 0.25);
  }
  &__draft-title { color: $text-secondary; }
  &__build-btn {
    padding: 3px 12px; border: none; border-radius: 6px; flex-shrink: 0;
    background: #10B981; color: #fff; font-size: 11px; font-weight: 600; cursor: pointer;
    &:hover:not(:disabled) { background: #059669; }
    &:disabled { opacity: 0.5; }
  }
  &__todo-built { margin-top: 6px; font-size: 11px; color: #059669; }
}

.agent-chat__session-explore {
  width: 14px;
  height: 14px;
  margin-right: 4px;
  color: #0F766E;
  vertical-align: -2px;
}

.explore-banner {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-xs $spacing-lg;
  background: rgba(#0F766E, 0.06);
  border-bottom: 1px solid rgba(#0F766E, 0.16);

  .ep-icon { width: 14px; height: 14px; color: #0F766E; }
  &__tag { font-size: $font-size-xs; font-weight: 700; color: #0F766E; }
  &__hint { flex: 1; font-size: 10px; color: $text-muted; }
  &__btn {
    border: 1px solid rgba(#0F766E, 0.4); background: transparent; color: #0F766E;
    font-size: $font-size-xs; padding: 3px 12px; border-radius: 99px; cursor: pointer;
    &:hover:not(:disabled) { background: rgba(#0F766E, 0.1); }
    &:disabled { opacity: 0.5; cursor: not-allowed; }
  }
}

.explore-report {
  margin: $spacing-md $spacing-lg 0;
  padding: $spacing-md;
  border: 1px solid rgba(#0F766E, 0.25);
  border-radius: $border-radius-md;
  background: rgba(#0F766E, 0.04);

  &__title {
    display: flex; align-items: center; gap: 6px;
    font-size: $font-size-xs; font-weight: 700; color: #0F766E; margin-bottom: 6px;
    .ep-icon { width: 14px; height: 14px; }
  }
  &__insights {
    margin: 0 0 8px; padding-left: 18px;
    font-size: $font-size-xs; color: $text-secondary; line-height: 1.7;
  }
  &__body {
    max-height: 320px; overflow: auto;
    font-size: $font-size-sm; color: $text-primary; line-height: 1.6;
    padding-right: 4px;
  }
  &__actions, &__profiles { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 8px; }
  &__profiles { flex-direction: column; align-items: stretch; }
  &__profile-title { font-size: $font-size-xs; font-weight: 700; color: #0F766E; }
  &__profile {
    display: flex; gap: 8px; align-items: flex-start;
    font-size: $font-size-xs; color: $text-secondary; line-height: 1.5;
  }
  &__conflict { display: block; color: #B45309; }
  &__applied { display: block; color: #0F766E; }
  &__btn {
    border: none; border-radius: 6px; cursor: pointer;
    background: #0F766E; color: #fff; font-size: 11px; font-weight: 600;
    padding: 4px 12px;
    &:hover:not(:disabled) { background: #115E59; }
    &:disabled { opacity: 0.55; cursor: not-allowed; }
  }
  &__btn--todo { background: #10B981; &:hover:not(:disabled) { background: #059669; } }
}

.agent-chat__steer-text { font-size: 11px; font-weight: 600; }

.slash-panel {
  position: absolute;
  bottom: calc(100% + 6px);
  left: $spacing-md;
  right: $spacing-md;
  max-height: min(46vh, 280px);
  background: #fff;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  overflow-x: hidden;
  overflow-y: auto;
  z-index: 20;

  &__item {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    width: 100%;
    padding: 8px 12px;
    border: none;
    background: transparent;
    cursor: pointer;
    text-align: left;
    font-size: $font-size-sm;

    &--active, &:hover { background: rgba($primary-color, 0.06); }
  }

  &__cmd {
    font-weight: 600;
    color: $primary-color;
    flex-shrink: 0;
  }

  &__desc {
    color: $text-muted;
    font-size: $font-size-xs;
  }
}

.agent-chat__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 99px;
  background: rgba(#3B82F6, 0.08);
  border: 1px solid rgba(#3B82F6, 0.25);
  font-size: 11px;
  color: #1D4ED8;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &-del {
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    padding: 0;
    display: inline-flex;
    opacity: 0.6;
    &:hover { opacity: 1; }
  }
}

// 引用搜索弹窗
.ref-search {
  position: absolute;
  bottom: 100%;
  left: $spacing-lg;
  right: $spacing-lg;
  margin-bottom: 8px;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.14);
  z-index: 50;
  overflow: hidden;

  &__head {
    display: flex;
    gap: 6px;
    padding: 8px;
    border-bottom: 1px solid $border-color;
  }

  &__input {
    flex: 1;
    border: none;
    outline: none;
    font-size: 13px;
    padding: 4px 6px;
    background: transparent;
  }

  &__close {
    background: none;
    border: none;
    color: $text-muted;
    cursor: pointer;
    padding: 2px;
  }

  &__results {
    max-height: 240px;
    overflow-y: auto;
    padding: 6px;
  }

  &__hint { padding: 12px; font-size: 12px; color: $text-muted; text-align: center; }

  &__item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 8px 10px;
    border: none;
    background: none;
    border-radius: 6px;
    font-size: 12px;
    color: $text-primary;
    cursor: pointer;
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    &:hover { background: rgba($primary-color, 0.06); }
  }

  &__type {
    flex-shrink: 0;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 4px;

    &--diary { background: rgba(#F97316, 0.12); color: #C2410C; }
    &--todo { background: rgba(#3B82F6, 0.12); color: #1D4ED8; }
  }
}

// 待答问题卡片（空态融入对话流）
.pending-questions {
  margin-top: $spacing-lg;
  text-align: left;
  border-top: 1px dashed $border-color;
  padding-top: $spacing-md;

  &__title {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    color: #14B8A6;
    margin-bottom: $spacing-sm;
  }

  &__item {
    padding: 10px 12px;
    border-radius: 10px;
    background: rgba(#14B8A6, 0.05);
    border: 1px solid rgba(#14B8A6, 0.2);
    margin-bottom: $spacing-sm;
  }

  &__q { font-size: 13px; font-weight: 500; color: $text-primary; line-height: 1.5; }

  &__row { display: flex; gap: 6px; margin-top: 8px; align-items: center; }

  &__input {
    flex: 1;
    min-width: 0;
    border: 1px solid $border-color;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    background: #fff;
    outline: none;
    &:focus { border-color: #14B8A6; }
  }

  &__send {
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #fff;
    background: #14B8A6;
    cursor: pointer;
    white-space: nowrap;
    &:disabled { opacity: 0.5; }
  }

  &__dismiss {
    background: none;
    border: none;
    font-size: 12px;
    color: $text-muted;
    cursor: pointer;
    white-space: nowrap;
    &:hover { color: $text-primary; }
  }
}
</style>
