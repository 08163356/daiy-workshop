<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, inject, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { TIME_API_BASE, getApiBase } from '@/config'
import AppIcon from '@/components/common/AppIcon.vue'
import { ssePost } from '@/views/chat/useSse'
import {
  pendingQuestions,
  refreshPendingQuestions,
  answerQuestion,
  dismissQuestion,
} from '@/composables/useAiQuestions'

const route = useRoute()
const router = useRouter()

// ==================== 状态计时 ====================

interface StatusPreset {
  label: string
  emoji: string
  color: string
}

interface TimerStatus {
  is_running: boolean
  todo_id?: number
  todo_title?: string
  start_time?: string
  elapsed_seconds: number
  time_log_id?: number
  activity_type: string
  status_label?: string
  status_emoji?: string
}

const showStatusPicker = ref(false)
const presets = ref<StatusPreset[]>([])
const customPresets = ref<StatusPreset[]>([])  // 用户自定义的状态列表
const currentTimer = ref<TimerStatus | null>(null)
const elapsedDisplay = ref('')
const customLabel = ref('')
const showCustomInput = ref(false)
let tickInterval: ReturnType<typeof setInterval> | null = null
let pollInterval: ReturnType<typeof setInterval> | null = null

// 从 localStorage 加载自定义状态
const CUSTOM_STATUS_KEY = 'custom_status_presets'
function loadCustomPresets() {
  try {
    const saved = localStorage.getItem(CUSTOM_STATUS_KEY)
    if (saved) {
      customPresets.value = JSON.parse(saved)
    }
  } catch { /* 静默 */ }
}

function saveCustomPresets() {
  try {
    localStorage.setItem(CUSTOM_STATUS_KEY, JSON.stringify(customPresets.value))
  } catch { /* 静默 */ }
}

// 合并后的全部状态列表
const allPresets = computed(() => [...presets.value, ...customPresets.value])

// 获取预设状态
async function fetchPresets() {
  try {
    const res = await fetch(`${TIME_API_BASE}/status/presets`)
    if (res.ok) presets.value = await res.json()
    else console.warn('[状态] 获取预设失败:', res.status, await res.text())
  } catch (e) { console.error('[状态] 获取预设异常:', e) }
}

// 获取当前计时状态
async function fetchCurrentTimer() {
  try {
    const res = await fetch(`${TIME_API_BASE}/current`)
    if (res.ok) {
      const data = await res.json()
      currentTimer.value = data.is_running ? data : null
      updateElapsed()
    } else {
      console.warn('[状态] 获取当前计时失败:', res.status)
    }
  } catch (e) { console.error('[状态] 获取当前计时异常:', e) }
}

// 更新已耗时显示
function updateElapsed() {
  if (!currentTimer.value || !currentTimer.value.start_time) {
    elapsedDisplay.value = ''
    return
  }
  const start = new Date(currentTimer.value.start_time).getTime()
  const now = Date.now()
  const secs = Math.floor((now - start) / 1000)
  const mins = Math.floor(secs / 60)
  const hrs = Math.floor(mins / 60)
  if (hrs > 0) {
    elapsedDisplay.value = `${hrs}h${mins % 60}m`
  } else if (mins > 0) {
    elapsedDisplay.value = `${mins}min`
  } else {
    elapsedDisplay.value = `${secs}s`
  }
}

// 开始状态计时
async function startStatus(preset: StatusPreset) {
  try {
    const res = await fetch(`${TIME_API_BASE}/status/start?label=${encodeURIComponent(preset.label)}&emoji=${encodeURIComponent(preset.emoji)}`, { method: 'POST' })
    if (res.ok) {
      await fetchCurrentTimer()
    } else {
      const errText = await res.text()
      console.error('[状态] 开始计时失败:', res.status, errText)
    }
  } catch (e) { console.error('[状态] 开始计时异常:', e) }
  showStatusPicker.value = false
  showCustomInput.value = false
}

// 开始自定义状态
async function startCustomStatus() {
  const label = customLabel.value.trim()
  if (!label) return
  const preset: StatusPreset = { label, emoji: '⏱️', color: '#64748B' }
  // 如果不在默认预设和自定义列表中，保存到自定义列表
  const existsInPresets = presets.value.some(p => p.label === label)
  const existsInCustom = customPresets.value.some(p => p.label === label)
  if (!existsInPresets && !existsInCustom) {
    customPresets.value.push(preset)
    saveCustomPresets()
  }
  await startStatus(preset)
  customLabel.value = ''
  showCustomInput.value = false
}

// 停止当前状态
async function stopCurrentStatus() {
  if (!currentTimer.value) return
  try {
    let res: Response
    if (currentTimer.value.activity_type === 'status') {
      res = await fetch(`${TIME_API_BASE}/status/stop`, { method: 'POST' })
    } else if (currentTimer.value.todo_id) {
      res = await fetch(`${TIME_API_BASE}/stop/${currentTimer.value.todo_id}`, { method: 'POST' })
    } else {
      return
    }
    if (!res!.ok) console.error('[状态] 停止计时失败:', res!.status, await res!.text())
    currentTimer.value = null
    elapsedDisplay.value = ''
  } catch (e) { console.error('[状态] 停止计时异常:', e) }
}

// 切换状态选择器
function toggleStatusPicker() {
  showStatusPicker.value = !showStatusPicker.value
  showCustomInput.value = false
}

// 点击外部关闭
function onClickOutside(e: Event) {
  const target = e.target as HTMLElement
  if (!target.closest('.status-picker-wrapper')) {
    showStatusPicker.value = false
    showCustomInput.value = false
  }
}

onMounted(() => {
  loadCustomPresets()
  fetchPresets()
  fetchCurrentTimer()
  tickInterval = setInterval(updateElapsed, 1000)
  pollInterval = setInterval(fetchCurrentTimer, 5000)
  document.addEventListener('click', onClickOutside)
  document.addEventListener('click', onClickOutsideLockMenu)
  document.addEventListener('click', onClickOutsideQuestions)
  // AI 提问队列：进页面拉一次，之后每分钟轮询红点
  refreshPendingQuestions()
  questionPollInterval = setInterval(() => refreshPendingQuestions(), 60000)
})

onUnmounted(() => {
  if (tickInterval) clearInterval(tickInterval)
  if (pollInterval) clearInterval(pollInterval)
  document.removeEventListener('click', onClickOutside)
  document.removeEventListener('click', onClickOutsideLockMenu)
  document.removeEventListener('click', onClickOutsideQuestions)
  if (questionPollInterval) clearInterval(questionPollInterval)
})

// 系统定义
interface SystemConfig {
  id: string
  name: string
  icon: string
  path: string
  color: string
}

const systems: SystemConfig[] = [
  { id: 'todo', name: '待办', icon: 'square-check-big', path: '/todo/calendar', color: '#EC4899' },
  { id: 'reading', name: '读书', icon: 'book-open', path: '/reading', color: '#3B82F6' },
  { id: 'investment', name: '投资', icon: 'trending-up', path: '/investment', color: '#10B981' },
  { id: 'diary', name: '日记', icon: 'notebook-pen', path: '/diary', color: '#F59E0B' },
  { id: 'wellbeing', name: '心力', icon: 'heart-pulse', path: '/wellbeing', color: '#14B8A6' },
  { id: 'basketball', name: '篮球反思', icon: 'dumbbell', path: '/basketball', color: '#D97706' },
  { id: 'timeCapsule', name: '时光胶囊', icon: 'hourglass', path: '/time-capsule', color: '#8B5CF6' },
  { id: 'wishlist', name: '心愿清单', icon: 'sparkles', path: '/wishlist', color: '#F43F5E' },
  { id: 'entertainment', name: '娱乐', icon: 'gamepad-2', path: '/entertainment', color: '#A855F7' },
  { id: 'kb', name: '知识库', icon: 'library', path: '/kb', color: '#6366F1' },
  { id: 'review', name: '审批中心', icon: 'clipboard-check', path: '/review', color: '#0EA5E9' },
]

// 各系统的导航项
interface NavItem {
  path: string
  name: string
  icon: string
}

const systemNavItems: Record<string, NavItem[]> = {
  reading: [
    { path: '/reading', name: '总览', icon: 'layout-dashboard' },
    { path: '/timeline', name: '时间线', icon: 'calendar-days' },
    { path: '/models', name: '思维模型', icon: 'target' },
    { path: '/knowledge', name: '知识分类', icon: 'layers' },
    { path: '/weread', name: '微信读书', icon: 'book-marked' },
  ],
  investment: [
    { path: '/investment', name: '总览', icon: 'layout-dashboard' },
    { path: '/investment/principles', name: '投资原则', icon: 'clipboard-list' },
    { path: '/investment/cognitions', name: '认知迭代', icon: 'rotate-ccw' },
    { path: '/investment/qa', name: 'Q&A', icon: 'circle-help' },
    { path: '/investment/decisions', name: '决策日志', icon: 'bar-chart-3' },
    { path: '/investment/emotions', name: '情绪复盘', icon: 'drama' },
    { path: '/investment/knowledge', name: '知识体系', icon: 'lightbulb' },
  ],
  diary: [
    { path: '/diary', name: '总览', icon: 'layout-dashboard' },
    { path: '/diary/list', name: '日记列表', icon: 'list' },
  ],
  entertainment: [
    { path: '/entertainment', name: '娱乐', icon: 'gamepad-2' },
  ],
  todo: [
    { path: '/todo/calendar', name: '日程规划', icon: 'calendar-days' },
    { path: '/todo', name: '总览', icon: 'layout-dashboard' },
    { path: '/todo/list', name: '全部待办', icon: 'list' },
    { path: '/todo/review', name: '总结报告', icon: 'file-bar-chart' },
    { path: '/todo/habits', name: '习惯追踪', icon: 'flame' },
  ],
  kb: [
    { path: '/kb', name: '总览', icon: 'layout-dashboard' },
    { path: '/kb/list', name: '知识列表', icon: 'list' },
  ],
  wellbeing: [
    { path: '/wellbeing', name: '总览', icon: 'layout-dashboard' },
    { path: '/wellbeing/list', name: '列表', icon: 'list' },
    { path: '/wellbeing/candidates', name: '候选', icon: 'wand-2' },
    { path: '/wellbeing/reports', name: '周月报', icon: 'file-bar-chart' },
    { path: '/wellbeing/anxiety', name: '焦虑模式', icon: 'leaf' },
  ],
  basketball: [
    { path: '/basketball', name: '总览', icon: 'layout-dashboard' },
    { path: '/basketball/new', name: '写复盘', icon: 'pen-line' },
    { path: '/basketball/list', name: '历史', icon: 'list' },
    { path: '/basketball/goals', name: '阶段目标', icon: 'target' },
  ],
  timeCapsule: [
    { path: '/time-capsule', name: '信件列表', icon: 'mail' },
    { path: '/time-capsule/write', name: '写信', icon: 'pen-line' },
  ],
  wishlist: [
    { path: '/wishlist', name: '心愿墙', icon: 'sparkles' },
  ],
  review: [
    { path: '/review', name: '审批中心', icon: 'clipboard-check' },
  ],
}

// 当前系统
const currentSystem = computed(() => {
  const path = route.path
  if (path.startsWith('/investment')) return 'investment'
  if (path.startsWith('/diary')) return 'diary'
  if (path.startsWith('/wellbeing')) return 'wellbeing'
  if (path.startsWith('/basketball')) return 'basketball'
  if (path.startsWith('/entertainment')) return 'entertainment'
  if (path.startsWith('/todo')) return 'todo'
  if (path.startsWith('/kb')) return 'kb'
  if (path.startsWith('/time-capsule')) return'timeCapsule'
  if (path.startsWith('/wishlist')) return 'wishlist'
  if (path.startsWith('/review')) return 'review'
  if (path.startsWith('/reading') || path.startsWith('/timeline') || path.startsWith('/models') || path.startsWith('/knowledge') || path.startsWith('/weread')) return 'reading'
  if (path.startsWith('/settings')) return 'settings'
  // AI 助手/旧对话页归入待办分组
  if (path.startsWith('/assistant') || path.startsWith('/chat')) return 'todo'
  return 'todo'
})

// 当前系统配置（默认待办）
const currentSystemConfig = computed(() => {
  return systems.find(s => s.id === currentSystem.value) || systems.find(s => s.id === 'todo')!
})

// 当前导航项（默认待办）
const currentNavItems = computed(() => {
  return systemNavItems[currentSystem.value] || systemNavItems.todo
})

const currentPath = computed(() => route.path)

// 侧边抽屉
const showDrawer = ref(false)

const navigateTo = (path: string) => {
  router.push(path)
}

const switchSystem = (system: SystemConfig) => {
  showDrawer.value = false
  router.push(system.path)
}

const openDrawer = () => {
  showDrawer.value = true
}

const closeDrawer = () => {
  showDrawer.value = false
}

// ==================== 锁屏控制 ====================

const lockApp = inject<() => void>('lockApp')!
const startCountdownLock = inject<(minutes: number) => void>('startCountdownLock')!
const cancelCountdown = inject<() => void>('cancelCountdown')!
const lockCountdown = inject<Ref<number | null>>('lockCountdown')!
const autoLockMinutes = inject<Ref<number>>('autoLockMinutes')!
const saveLockSettings = inject<(minutes: number) => Promise<void>>('saveLockSettings')!
const isDemo = inject<boolean>('isDemo', false)

const showLockMenu = ref(false)
const editingAutoLock = ref(false)
const tempAutoLockMinutes = ref(13)

function toggleLockMenu() {
  showLockMenu.value = !showLockMenu.value
  if (showLockMenu.value) {
    tempAutoLockMinutes.value = autoLockMinutes.value
    editingAutoLock.value = false
  }
}

function closeLockMenu() {
  showLockMenu.value = false
  editingAutoLock.value = false
}

function handleLockNow() {
  lockApp()
  closeLockMenu()
}

function handleCountdownLock(minutes: number) {
  startCountdownLock(minutes)
  closeLockMenu()
}

function handleCancelCountdown() {
  cancelCountdown()
  closeLockMenu()
}

function saveAutoLockTime() {
  const val = Math.max(1, Math.min(120, tempAutoLockMinutes.value || 13))
  saveLockSettings(val)
  editingAutoLock.value = false
}

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function onClickOutsideLockMenu(e: Event) {
  const target = e.target as HTMLElement
  if (!target.closest('.header__lock-wrapper')) {
    closeLockMenu()
  }
}

// ==================== AI 提问队列（顶栏红点入口） ====================

interface AIQuestion {
  id: number
  question: string
  context: string | null
  source_type: string
  created_at: string
}

interface ThreadMsg { role: 'user' | 'assistant'; content: string }

const showQuestions = ref(false)
const answeringId = ref<number | null>(null)
const answerText = ref('')
const questionSaving = ref(false)
const questionFeedback = ref('')
const followText = ref('')
const threadQuestion = ref<AIQuestion | null>(null)
const threadMessages = ref<ThreadMsg[]>([])
const threadSessionId = ref<number | null>(null)
const threadSending = ref(false)
let questionPollInterval: ReturnType<typeof setInterval> | null = null
const AGENT_CHAT = `${getApiBase()}/api/agent/chat`

function toggleQuestions() {
  showQuestions.value = !showQuestions.value
  if (showQuestions.value) refreshPendingQuestions()
}

function closeQuestions() {
  showQuestions.value = false
  answeringId.value = null
}

function startAnswer(q: AIQuestion) {
  answeringId.value = q.id
  answerText.value = ''
}

async function streamCoachReply(text: string, originId?: number) {
  threadSending.value = true
  const assistant: ThreadMsg = { role: 'assistant', content: '' }
  threadMessages.value.push(assistant)
  try {
    for await (const ev of ssePost<any>(AGENT_CHAT, {
      content: text,
      session_id: threadSessionId.value,
      origin_type: threadSessionId.value ? undefined : 'question',
      origin_id: threadSessionId.value ? undefined : originId,
    })) {
      if (ev.type === 'session' && ev.session_id) threadSessionId.value = ev.session_id
      if (ev.type === 'content' && ev.delta) assistant.content += ev.delta
    }
    if (!assistant.content) assistant.content = '记下了。'
  } catch {
    assistant.content = assistant.content || '这次没回上，可以再试一次，或点「继续聊」进对话页。'
  }
  threadSending.value = false
}

async function submitAnswer(q: AIQuestion) {
  if (!answerText.value.trim()) return
  questionSaving.value = true
  const text = answerText.value.trim()
  try {
    await answerQuestion(q.id, text)
    answeringId.value = null
    answerText.value = ''
    threadQuestion.value = q
    threadMessages.value = [{ role: 'user', content: text }]
    threadSessionId.value = null
    questionFeedback.value = ''
    await streamCoachReply(text, q.id)
  } catch { /* 静默 */ }
  questionSaving.value = false
}

async function sendFollowup() {
  const text = followText.value.trim()
  if (!text || threadSending.value) return
  followText.value = ''
  threadMessages.value.push({ role: 'user', content: text })
  await streamCoachReply(text)
}

async function dismissQuestionItem(q: AIQuestion) {
  try {
    await dismissQuestion(q.id)
  } catch { /* 静默 */ }
}

function questionSourceLabel(q: AIQuestion): string {
  const date = q.created_at?.slice(5, 10) || ''
  const typeMap: Record<string, string> = { diary: '日记', note: '笔记', manual: '主动提问' }
  return `来自 ${date} ${typeMap[q.source_type] || '记录'}`
}

// 提问继续聊/深挖：带着问题进教练对话（服务端按 question id 注入上下文，并自动移出队列）
function deepDiveQuestion(q: AIQuestion) {
  closeQuestions()
  router.push({ path: '/assistant', query: { origin: `question:${q.id}` } })
}

function onClickOutsideQuestions(e: Event) {
  const target = e.target as HTMLElement
  if (!target.closest('.header__questions-wrapper')) {
    closeQuestions()
  }
}
</script>

<template>
  <header class="header">
    <div class="header__container">
      <!-- Logo + 系统切换 -->
      <div class="header__brand">
        <div class="header__logo" @click="navigateTo(currentSystemConfig.path)">
          <AppIcon :name="currentSystemConfig.icon" :size="24" :stroke-width="1.75" class="header__logo-icon" />
          <span class="header__logo-text">Daily 系统</span>
        </div>
        
        <!-- 系统切换器（点击打开侧边抽屉） -->
        <div class="header__system-switcher" @click="openDrawer">
          <span class="header__system-current" :style="{ color: currentSystemConfig.color }">
            {{ currentSystemConfig.name }}
          </span>
          <span class="header__system-arrow">☰</span>
        </div>

        <!-- 状态选择器 -->
        <div class="status-picker-wrapper" @click.stop>
          <button
            v-if="currentTimer"
            class="status-chip status-chip--active"
            @click="toggleStatusPicker"
          >
            <span class="status-chip__emoji">{{ currentTimer.activity_type === 'status' ? currentTimer.status_emoji : '📋' }}</span>
            <span class="status-chip__label">{{ currentTimer.activity_type === 'status' ? currentTimer.status_label : (currentTimer.todo_title || '任务') }}</span>
            <span class="status-chip__time">{{ elapsedDisplay }}</span>
            <span class="status-chip__stop" @click.stop="stopCurrentStatus" title="停止">⏹</span>
          </button>
          <button
            v-else
            class="status-chip status-chip--idle"
            @click="toggleStatusPicker"
          >
            <AppIcon name="minus" :size="14" class="status-chip__emoji" />
            <span class="status-chip__label">设置状态</span>
          </button>

          <!-- 下拉选择器 -->
          <Transition name="picker-fade">
            <div v-if="showStatusPicker" class="status-picker">
              <div class="status-picker__header">选择当前状态</div>
              <div class="status-picker__grid">
                <button
                  v-for="p in allPresets"
                  :key="p.label"
                  class="status-picker__item"
                  :class="{ 'status-picker__item--active': currentTimer?.status_label === p.label }"
                  :style="{ '--status-color': p.color }"
                  @click="startStatus(p)"
                >
                  <span class="status-picker__item-emoji">{{ p.emoji }}</span>
                  <span class="status-picker__item-label">{{ p.label }}</span>
                </button>
              </div>
              <!-- 自定义已存状态可删除 -->
              <div v-if="customPresets.length" class="status-picker__custom-list">
                <div v-for="(cp, idx) in customPresets" :key="cp.label" class="status-picker__custom-tag">
                  <span>{{ cp.emoji }} {{ cp.label }}</span>
                  <button class="status-picker__custom-del" @click.stop="customPresets.splice(idx, 1); saveCustomPresets()" title="删除">✕</button>
                </div>
              </div>
              <div class="status-picker__custom">
              <button v-if="!showCustomInput" class="status-picker__custom-btn" @click="showCustomInput = true">
                <AppIcon name="pen-line" :size="12" style="margin-right:4px;" /> 自定义
              </button>
                <div v-else class="status-picker__custom-input">
                  <input
                    v-model="customLabel"
                    placeholder="输入自定义状态"
                    @keyup.enter="startCustomStatus"
                    maxlength="20"
                  />
                  <button @click="startCustomStatus">开始</button>
                </div>
              </div>
              <button v-if="currentTimer" class="status-picker__stop" @click="stopCurrentStatus">
                ⏹ 停止当前计时
              </button>
            </div>
          </Transition>
        </div>
      </div>
      
      <!-- 导航菜单 -->
      <nav class="header__nav">
        <button
          v-for="item in currentNavItems"
          :key="item.path"
          class="header__nav-item"
          :class="{ 'header__nav-item--active': currentPath === item.path }"
          @click="navigateTo(item.path)"
        >
          <AppIcon :name="item.icon" :size="16" class="header__nav-icon" />
          <span class="header__nav-text">{{ item.name }}</span>
        </button>
      </nav>
      
      <!-- 右侧操作区 -->
      <div class="header__actions">
        <button class="header__action-btn header__action-btn--chat" title="AI 助手" @click="navigateTo('/assistant')">
          <AppIcon name="message-square" :size="18" />
        </button>

        <!-- AI 想了解你（提问队列，演示版与正式版同一入口） -->
        <div class="header__questions-wrapper" @click.stop>
          <button
            class="header__action-btn"
            :class="{ 'header__action-btn--active': showQuestions }"
            :title="pendingQuestions.length ? `AI 想了解你：${pendingQuestions.length} 个待答问题` : 'AI 想了解你'"
            @click="toggleQuestions"
          >
            <AppIcon name="circle-help" :size="18" />
            <span v-if="pendingQuestions.length" class="header__questions-badge">{{ pendingQuestions.length }}</span>
          </button>

          <Transition name="picker-fade">
            <div v-if="showQuestions" class="questions-menu">
              <div class="questions-menu__head">
                <strong>AI 想了解你</strong>
                <span class="questions-menu__hint">回答会沉淀到你的画像</span>
              </div>
              <div v-if="questionFeedback" class="questions-menu__feedback">{{ questionFeedback }}</div>
              <div v-if="threadQuestion" class="questions-menu__item questions-menu__item--thread">
                <div class="questions-menu__q">{{ threadQuestion.question }}</div>
                <div class="questions-menu__thread">
                  <div v-for="(m, i) in threadMessages" :key="i" class="questions-menu__bubble" :class="'questions-menu__bubble--' + m.role">{{ m.content }}</div>
                </div>
                <div class="questions-menu__answer-row">
                  <input
                    v-model="followText"
                    class="questions-menu__input"
                    placeholder="继续说…"
                    :disabled="threadSending"
                    @keydown.enter="sendFollowup"
                  />
                  <button class="questions-menu__send" :disabled="!followText.trim() || threadSending" @click="sendFollowup">发送</button>
                </div>
                <div class="questions-menu__ops">
                  <button class="questions-menu__op questions-menu__op--deep" @click="deepDiveQuestion(threadQuestion)">全屏继续聊</button>
                </div>
              </div>
              <div v-if="pendingQuestions.length === 0 && !threadQuestion" class="questions-menu__empty">
                暂无待答问题。写日记/笔记后，AI 发现有想澄清的点会在这里问你。
              </div>
              <div v-for="q in pendingQuestions" :key="q.id" class="questions-menu__item">
                <div class="questions-menu__q">{{ q.question }}</div>
                <div class="questions-menu__meta">{{ questionSourceLabel(q) }}</div>
                <div v-if="answeringId === q.id" class="questions-menu__answer-row">
                  <input
                    v-model="answerText"
                    class="questions-menu__input"
                    placeholder="输入回答，Enter 提交"
                    :disabled="questionSaving"
                    @keydown.enter="submitAnswer(q)"
                    autofocus
                  />
                  <button class="questions-menu__send" :disabled="!answerText.trim() || questionSaving" @click="submitAnswer(q)">提交</button>
                </div>
                <div v-else class="questions-menu__ops">
                  <button class="questions-menu__op questions-menu__op--answer" @click="startAnswer(q)">回答</button>
                  <button class="questions-menu__op questions-menu__op--deep" title="带着这个问题进教练对话继续聊" @click="deepDiveQuestion(q)">继续聊</button>
                  <button class="questions-menu__op" @click="dismissQuestionItem(q)">忽略</button>
                </div>
              </div>
            </div>
          </Transition>
        </div>

        <!-- 锁屏按钮（演示模式隐藏） -->
        <div v-if="!isDemo" class="header__lock-wrapper" @click.stop>
          <button
            class="header__action-btn"
            :class="{ 'header__action-btn--countdown': lockCountdown !== null }"
            :title="lockCountdown !== null ? `${formatCountdown(lockCountdown)}后锁定` : '锁屏'"
            @click="toggleLockMenu"
          >
            <AppIcon name="lock" :size="18" />
            <span v-if="lockCountdown !== null" class="header__lock-badge">{{ formatCountdown(lockCountdown) }}</span>
          </button>

          <Transition name="picker-fade">
            <div v-if="showLockMenu" class="lock-menu">
              <button class="lock-menu__item lock-menu__item--primary" @click="handleLockNow">
                <span class="lock-menu__icon">🔒</span> 立即锁定
              </button>

              <div class="lock-menu__divider"></div>

              <template v-if="lockCountdown === null">
                <div class="lock-menu__label">定时锁定</div>
                <button v-for="m in [1, 5, 10, 15, 30]" :key="m" class="lock-menu__item" @click="handleCountdownLock(m)">
                  <span class="lock-menu__icon">⏱️</span> {{ m }} 分钟后锁定
                </button>
              </template>
              <template v-else>
                <div class="lock-menu__label">倒计时进行中：{{ formatCountdown(lockCountdown) }}</div>
                <button class="lock-menu__item lock-menu__item--cancel" @click="handleCancelCountdown">
                  <span class="lock-menu__icon">✕</span> 取消定时锁定
                </button>
              </template>

              <div class="lock-menu__divider"></div>

              <div class="lock-menu__setting">
                <span class="lock-menu__setting-label">自动锁定（无操作）</span>
                <div class="lock-menu__setting-row">
                  <template v-if="!editingAutoLock">
                    <strong>{{ autoLockMinutes }} 分钟</strong>
                    <button class="lock-menu__edit-btn" @click="editingAutoLock = true">修改</button>
                  </template>
                  <template v-else>
                    <input
                      v-model.number="tempAutoLockMinutes"
                      type="number"
                      min="1"
                      max="120"
                      class="lock-menu__input"
                      @keydown.enter="saveAutoLockTime"
                    />
                    <span class="lock-menu__unit">分钟</span>
                    <button class="lock-menu__edit-btn lock-menu__edit-btn--save" @click="saveAutoLockTime">确定</button>
                  </template>
                </div>
              </div>
            </div>
          </Transition>
        </div>

        <button class="header__action-btn" title="设置" @click="navigateTo('/settings')">
          <AppIcon name="settings" :size="18" />
        </button>
      </div>
    </div>
  </header>

  <!-- 侧边抽屉遮罩 -->
  <Transition name="drawer-overlay">
    <div v-if="showDrawer" class="drawer-overlay" @click="closeDrawer" />
  </Transition>

  <!-- 侧边抽屉 -->
  <Transition name="drawer">
    <div v-if="showDrawer" class="drawer">
      <!-- 抽屉头部 -->
      <div class="drawer__header">
        <span class="drawer__title">切换系统</span>
        <button class="drawer__close" @click="closeDrawer">✕</button>
      </div>

      <!-- 系统列表 -->
      <div class="drawer__body">
        <button
          v-for="system in systems"
          :key="system.id"
          class="drawer__item"
          :class="{ 'drawer__item--active': currentSystem === system.id }"
          :style="currentSystem === system.id ? { borderLeftColor: system.color } : {}"
          @click="switchSystem(system)"
        >
          <AppIcon :name="system.icon" :size="20" class="drawer__item-icon" />
          <span class="drawer__item-name">{{ system.name }}</span>
          <span v-if="currentSystem === system.id" class="drawer__item-check" :style="{ color: system.color }">✓</span>
        </button>
      </div>

      <!-- 抽屉底部快捷操作 -->
      <div class="drawer__footer">
        <button class="drawer__footer-btn" @click="navigateTo('/assistant'); closeDrawer()">
          <AppIcon name="message-square" :size="20" />
          <span>AI 助手</span>
        </button>
        <button class="drawer__footer-btn" @click="navigateTo('/settings'); closeDrawer()">
          <AppIcon name="settings" :size="20" />
          <span>设置</span>
        </button>
      </div>
    </div>
  </Transition>

  <!-- 移动端底部导航栏 -->
  <nav class="mobile-tab-bar">
    <button
      v-for="item in currentNavItems"
      :key="item.path"
      class="mobile-tab-bar__item"
      :class="{ 'mobile-tab-bar__item--active': currentPath === item.path }"
        @click="navigateTo(item.path)"
      >
        <AppIcon :name="item.icon" :size="20" class="mobile-tab-bar__icon" />
        <span class="mobile-tab-bar__text">{{ item.name }}</span>
    </button>
    <template v-if="currentSystem !== 'todo'">
      <button
        class="mobile-tab-bar__item"
        :class="{ 'mobile-tab-bar__item--active': currentPath === '/assistant' || currentPath === '/chat' }"
        @click="navigateTo('/assistant')"
      >
        <AppIcon name="message-square" :size="20" class="mobile-tab-bar__icon" />
        <span class="mobile-tab-bar__text">AI</span>
      </button>
      <button
        class="mobile-tab-bar__item"
        :class="{ 'mobile-tab-bar__item--active': currentPath === '/settings' }"
        @click="navigateTo('/settings')"
      >
        <AppIcon name="settings" :size="20" class="mobile-tab-bar__icon" />
        <span class="mobile-tab-bar__text">设置</span>
      </button>
    </template>
  </nav>
</template>

<style lang="scss" scoped>
.header {
  @include glass-card;
  position: sticky;
  top: 0;
  z-index: 100;
  border-radius: 0;
  border-top: none;
  border-left: none;
  border-right: none;
  
  &__container {
    max-width: 1400px;
    margin: 0 auto;
    padding: $spacing-md $spacing-lg;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: $spacing-lg;

    @media (max-width: $breakpoint-md) {
      padding: $spacing-sm $spacing-md;
    }
  }
  
  &__brand {
    display: flex;
    align-items: center;
    gap: $spacing-md;
  }
  
  &__logo {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    cursor: pointer;
    transition: transform $transition-fast;
    
    &:hover {
      transform: scale(1.02);
    }
    
    &-icon {
      display: flex;
      align-items: center;
      color: inherit;
      flex-shrink: 0;

      @media (max-width: $breakpoint-md) {
        svg { width: 20px !important; height: 20px !important; }
      }
    }
    
    &-text {
      font-size: $font-size-lg;
      font-weight: 700;
      background: linear-gradient(135deg, $primary-color, $accent-color);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;

      @media (max-width: $breakpoint-md) {
        font-size: $font-size-md;
      }
    }
  }
  
  &__system-switcher {
    display: flex;
    align-items: center;
    gap: $spacing-xs;
    padding: $spacing-xs $spacing-sm;
    border-radius: $border-radius-md;
    background: rgba($primary-color, 0.1);
    cursor: pointer;
    transition: all $transition-fast;
    
    &:hover {
      background: rgba($primary-color, 0.15);
    }
  }
  
  &__system-current {
    font-size: $font-size-sm;
    font-weight: 600;
  }
  
  &__system-arrow {
    font-size: 14px;
    color: $text-secondary;
  }
  
  &__nav {
    display: flex;
    align-items: center;
    gap: $spacing-xs;
    
    @media (max-width: $breakpoint-md) {
      display: none;
    }
  }
  
  &__nav-item {
    display: flex;
    align-items: center;
    gap: $spacing-xs;
    padding: $spacing-sm $spacing-md;
    border-radius: $border-radius-md;
    background: transparent;
    color: $text-secondary;
    font-size: $font-size-sm;
    font-weight: 500;
    transition: all $transition-fast;
    
    &:hover {
      background: rgba($primary-color, 0.1);
      color: $primary-color;
    }
    
    &--active {
      background: linear-gradient(135deg, $primary-color, $accent-color);
      color: white;
      
      &:hover {
        background: linear-gradient(135deg, $primary-color, $accent-color);
        color: white;
      }
    }
  }
  
  &__nav-icon {
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }
  
  &__nav-text {
    @media (max-width: $breakpoint-lg) {
      display: none;
    }
  }
  
  &__actions {
    display: flex;
    align-items: center;
    gap: $spacing-sm;

    @media (max-width: $breakpoint-md) {
      display: none;
    }
  }
  
  &__action-btn {
    width: 40px;
    height: 40px;
    border-radius: $border-radius-md;
    background: transparent;
    font-size: 18px;
    @include flex-center;
    transition: all $transition-fast;
    
    &:hover {
      background: rgba($primary-color, 0.1);
      transform: scale(1.1);
    }

    &--chat {
      background: linear-gradient(135deg, rgba($primary-color, 0.1), rgba($accent-color, 0.1));
      
      &:hover {
        background: linear-gradient(135deg, rgba($primary-color, 0.2), rgba($accent-color, 0.2));
      }
    }

    &--countdown {
      position: relative;
      color: #F59E0B;
    }
  }

  &__lock-wrapper {
    position: relative;
  }

  &__questions-wrapper {
    position: relative;
  }

  &__questions-badge {
    position: absolute;
    top: -4px;
    right: -8px;
    font-size: 10px;
    font-weight: 700;
    color: #fff;
    background: #14B8A6;
    padding: 1px 5px;
    border-radius: 8px;
    line-height: 1.3;
    pointer-events: none;
    white-space: nowrap;
  }

  &__lock-badge {
    position: absolute;
    top: -4px;
    right: -8px;
    font-size: 10px;
    font-weight: 700;
    color: #fff;
    background: #F59E0B;
    padding: 1px 5px;
    border-radius: 8px;
    line-height: 1.3;
    pointer-events: none;
    white-space: nowrap;
  }
}

// 锁屏下拉菜单
.lock-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 220px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(12px);
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  z-index: 300;
  padding: 6px 0;

  &__item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 9px 14px;
    font-size: 13px;
    color: $text-primary;
    background: transparent;
    border: none;
    cursor: pointer;
    transition: background 0.15s;
    text-align: left;

    &:hover { background: rgba($primary-color, 0.06); }

    &--primary {
      font-weight: 600;
      color: $primary-color;
    }

    &--cancel {
      color: $danger-color;
      &:hover { background: rgba($danger-color, 0.06); }
    }
  }

  &__icon {
    width: 18px;
    text-align: center;
    flex-shrink: 0;
  }

  &__divider {
    height: 1px;
    background: $border-color;
    margin: 4px 10px;
  }

  &__label {
    padding: 6px 14px 2px;
    font-size: 11px;
    color: $text-muted;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  &__setting {
    padding: 8px 14px;
    font-size: 12px;
    color: $text-secondary;
  }

  &__setting-label {
    display: block;
    margin-bottom: 6px;
    color: $text-muted;
    font-size: 11px;
  }

  &__setting-row {
    display: flex;
    align-items: center;
    gap: 6px;

    strong {
      color: $text-primary;
      font-size: 13px;
    }
  }

  &__edit-btn {
    font-size: 11px;
    color: $primary-color;
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 4px;

    &:hover { background: rgba($primary-color, 0.1); }

    &--save {
      background: $primary-color;
      color: #fff;
      font-weight: 600;
      &:hover { background: darken($primary-color, 8%); }
    }
  }

  &__input {
    width: 52px;
    padding: 3px 6px;
    border: 1px solid $border-color;
    border-radius: 6px;
    font-size: 13px;
    text-align: center;
    outline: none;
    &:focus { border-color: $primary-color; }
  }

  &__unit {
    font-size: 12px;
    color: $text-muted;
  }
}

// 侧边抽屉遮罩
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 200;
  backdrop-filter: blur(2px);
}

// 侧边抽屉
.drawer {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: 260px;
  max-width: 80vw;
  background: white;
  z-index: 201;
  display: flex;
  flex-direction: column;
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.15);

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: $spacing-lg $spacing-md;
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  }

  &__title {
    font-size: $font-size-md;
    font-weight: 700;
    color: $text-primary;
  }

  &__close {
    width: 32px;
    height: 32px;
    border-radius: $border-radius-sm;
    background: transparent;
    color: $text-secondary;
    font-size: 14px;
    @include flex-center;
    transition: all $transition-fast;

    &:hover {
      background: rgba($primary-color, 0.1);
      color: $primary-color;
    }
  }

  &__body {
    flex: 1;
    overflow-y: auto;
    padding: $spacing-sm;
  }

  &__item {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    width: 100%;
    padding: $spacing-md;
    border-radius: $border-radius-md;
    background: transparent;
    color: $text-primary;
    font-size: $font-size-sm;
    transition: all $transition-fast;
    border-left: 3px solid transparent;
    margin-bottom: $spacing-xs;

    &:hover {
      background: rgba($primary-color, 0.06);
    }

    &--active {
      background: rgba($primary-color, 0.08);
      font-weight: 600;
    }

    &-icon {
      font-size: 22px;
      flex-shrink: 0;
    }

    &-name {
      flex: 1;
      text-align: left;
    }

    &-check {
      font-size: 16px;
      font-weight: 700;
    }
  }

  &__footer {
    padding: $spacing-sm $spacing-sm calc(#{$spacing-sm} + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid rgba(148, 163, 184, 0.2);
    display: flex;
    gap: $spacing-xs;
  }

  &__footer-btn {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    padding: $spacing-sm;
    border-radius: $border-radius-md;
    background: transparent;
    color: $text-secondary;
    font-size: 11px;
    transition: all $transition-fast;

    span:first-child {
      font-size: 20px;
    }

    &:hover {
      background: rgba($primary-color, 0.08);
      color: $primary-color;
    }
  }
}

// 抽屉动画
.drawer-enter-active,
.drawer-leave-active {
  transition: transform 0.25s ease;
}
.drawer-enter-from,
.drawer-leave-to {
  transform: translateX(-100%);
}

.drawer-overlay-enter-active,
.drawer-overlay-leave-active {
  transition: opacity 0.25s ease;
}
.drawer-overlay-enter-from,
.drawer-overlay-leave-to {
  opacity: 0;
}

// 移动端底部 Tab 栏
.mobile-tab-bar {
  display: none;

  @media (max-width: $breakpoint-md) {
    display: flex;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 100;
    background: rgba(255, 255, 255, 0.92);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-top: 1px solid rgba(148, 163, 184, 0.2);
    padding: $spacing-xs $spacing-xs calc(#{$spacing-xs} + env(safe-area-inset-bottom, 0px));
    justify-content: space-around;
    align-items: center;
    box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.05);
  }

  &__item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: $spacing-xs $spacing-sm;
    border-radius: $border-radius-sm;
    background: transparent;
    color: $text-muted;
    font-size: 10px;
    transition: all $transition-fast;
    min-width: 0;
    flex: 1;
    max-width: 80px;

    &--active {
      color: $primary-color;

      .mobile-tab-bar__icon {
        transform: scale(1.1);
      }
    }

    &:active {
      background: rgba($primary-color, 0.08);
    }
  }

  &__icon {
    font-size: 20px;
    line-height: 1;
    transition: transform $transition-fast;
  }

  &__text {
    font-size: 10px;
    font-weight: 500;
    @include text-ellipsis;
    max-width: 100%;
  }
}

// ==================== 状态选择器 ====================
.status-picker-wrapper {
  position: relative;
}

.status-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
  white-space: nowrap;

  &--idle {
    background: rgba(148, 163, 184, 0.12);
    color: $text-secondary;

    &:hover {
      background: rgba(139, 92, 246, 0.12);
      color: #8B5CF6;
    }
  }

  &--active {
    background: linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(236, 72, 153, 0.12));
    color: #7C3AED;
    animation: pulse-soft 2s ease-in-out infinite;
  }

  &__emoji {
    font-size: 14px;
    line-height: 1;
  }

  &__label {
    max-width: 60px;
    overflow: hidden;
    text-overflow: ellipsis;

    @media (min-width: $breakpoint-md) {
      max-width: 100px;
    }
  }

  &__time {
    font-size: 11px;
    color: #8B5CF6;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }

  &__stop {
    margin-left: 2px;
    font-size: 12px;
    opacity: 0.6;
    cursor: pointer;
    transition: opacity 0.2s;
    background: none;
    border: none;
    padding: 0;

    &:hover {
      opacity: 1;
    }
  }
}

@keyframes pulse-soft {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.85; }
}

.status-picker {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  width: 280px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15), 0 2px 8px rgba(0, 0, 0, 0.08);
  z-index: 300;
  overflow: hidden;

  @media (max-width: $breakpoint-md) {
    left: -60px;
    width: 260px;
  }

  &__header {
    padding: 12px 16px 8px;
    font-size: 12px;
    font-weight: 600;
    color: $text-muted;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  &__grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px;
    padding: 4px 12px;
  }

  &__item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 8px 4px;
    border-radius: 8px;
    background: transparent;
    border: 2px solid transparent;
    cursor: pointer;
    transition: all 0.15s ease;
    color: $text-primary;

    &:hover {
      background: rgba(139, 92, 246, 0.08);
      border-color: rgba(139, 92, 246, 0.2);
    }

    &--active {
      background: rgba(139, 92, 246, 0.12);
      border-color: #8B5CF6;
    }

    &-emoji {
      font-size: 22px;
      line-height: 1;
    }

    &-label {
      font-size: 11px;
      font-weight: 500;
      color: $text-secondary;
    }
  }

  &__custom-list {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 6px 12px;
    border-top: 1px solid rgba(148, 163, 184, 0.1);
  }

  &__custom-tag {
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 2px 8px;
    border-radius: 12px;
    background: rgba(100, 116, 139, 0.08);
    font-size: 11px;
    color: $text-secondary;
  }

  &__custom-del {
    width: 14px;
    height: 14px;
    border: none;
    background: transparent;
    font-size: 9px;
    color: $text-muted;
    cursor: pointer;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;

    &:hover {
      background: rgba(239, 68, 68, 0.15);
      color: #EF4444;
    }
  }

  &__custom {
    padding: 8px 12px;
    border-top: 1px solid rgba(148, 163, 184, 0.15);

    &-btn {
      width: 100%;
      padding: 6px;
      font-size: 12px;
      color: $text-secondary;
      background: transparent;
      border: 1px dashed rgba(148, 163, 184, 0.3);
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;

      &:hover {
        border-color: #8B5CF6;
        color: #8B5CF6;
        background: rgba(139, 92, 246, 0.04);
      }
    }

    &-input {
      display: flex;
      gap: 6px;

      input {
        flex: 1;
        padding: 6px 10px;
        font-size: 12px;
        border: 1px solid rgba(148, 163, 184, 0.3);
        border-radius: 6px;
        outline: none;
        background: rgba(248, 250, 252, 0.8);

        &:focus {
          border-color: #8B5CF6;
          box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.1);
        }
      }

      button {
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 600;
        color: white;
        background: linear-gradient(135deg, #8B5CF6, #7C3AED);
        border: none;
        border-radius: 6px;
        cursor: pointer;
        white-space: nowrap;

        &:hover {
          opacity: 0.9;
        }
      }
    }
  }

  &__stop {
    width: 100%;
    padding: 10px;
    font-size: 12px;
    font-weight: 600;
    color: #EF4444;
    background: rgba(239, 68, 68, 0.06);
    border: none;
    border-top: 1px solid rgba(148, 163, 184, 0.15);
    cursor: pointer;
    transition: all 0.15s;

    &:hover {
      background: rgba(239, 68, 68, 0.12);
    }
  }
}

// 下拉动画
.picker-fade-enter-active,
.picker-fade-leave-active {
  transition: all 0.2s ease;
}
.picker-fade-enter-from,
.picker-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

// AI 提问队列下拉面板
.questions-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 360px;
  max-width: calc(100vw - 24px);
  max-height: 520px;
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.97);
  backdrop-filter: blur(12px);
  border: 1px solid $border-color;
  border-radius: $border-radius-lg;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  z-index: 300;
  padding: 10px;

  &__head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 2px 4px 10px;
    border-bottom: 1px solid $border-color;
    margin-bottom: 8px;

    strong { font-size: 13px; color: $text-primary; }
  }

  &__hint { font-size: 11px; color: $text-muted; }

  &__feedback {
    padding: 6px 8px; margin-bottom: 6px;
    background: rgba(#10B981, 0.08); color: #047857;
    border-radius: 6px; font-size: 11px; line-height: 1.5;
  }

  &__empty {
    padding: 16px 8px;
    font-size: 12px;
    color: $text-muted;
    line-height: 1.7;
  }

  &__item {
    padding: 8px;
    border-radius: 8px;
    margin-bottom: 6px;
    background: rgba($primary-color, 0.03);
    border: 1px solid rgba($primary-color, 0.1);

    &:last-child { margin-bottom: 0; }
  }

  &__q {
    font-size: 13px;
    color: $text-primary;
    line-height: 1.5;
    font-weight: 500;
  }

  &__meta { font-size: 11px; color: $text-muted; margin-top: 3px; }

  &__ops { display: flex; gap: 10px; margin-top: 6px; }

  &__op {
    background: none;
    border: none;
    padding: 0;
    font-size: 12px;
    color: $text-muted;
    cursor: pointer;

    &:hover { color: $text-primary; }
    &--answer { color: $primary-color; font-weight: 600; }
    &--deep { color: #8B5CF6; font-weight: 600; &:hover { color: #7C3AED; } }
  }

  &__answer-row {
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }

  &__input {
    flex: 1;
    min-width: 0;
    border: 1px solid $border-color;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    background: #fff;
    outline: none;

    &:focus { border-color: $primary-color; }
  }

  &__send {
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #fff;
    background: $primary-color;
    cursor: pointer;
    white-space: nowrap;

    &:disabled { opacity: 0.5; cursor: not-allowed; }
  }

  &__thread {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: 8px;
    max-height: 220px;
    overflow-y: auto;
  }

  &__bubble {
    font-size: 12px;
    line-height: 1.5;
    padding: 6px 8px;
    border-radius: 8px;
    white-space: pre-wrap;

    &--user { align-self: flex-end; background: rgba($primary-color, 0.12); }
    &--assistant { align-self: flex-start; background: rgba(0, 0, 0, 0.04); }
  }
}
</style>
