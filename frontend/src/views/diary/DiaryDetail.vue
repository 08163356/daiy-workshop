<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DIARY_API_BASE, API_BASE } from '@/config'
import { marked } from 'marked'
import ContentActions from '@/components/ContentActions.vue'
import ComfortPopover from '@/components/wellbeing/ComfortPopover.vue'
import DiaryRangeCalendar from './DiaryRangeCalendar.vue'
import { detectNegativeEmotion } from '@/config/negativeKeywords'

const route = useRoute()
const router = useRouter()

interface DiaryEntry {
  id: number
  date: string
  title: string
  content: string
  ai_analysis: string | null
  mood: string | null
  tags: string[] | null
  key_issues: string[] | null
  action_items: string[] | null
  images: string[] | null
  source: string
  created_at: string
}

interface DiaryNeighbor {
  id: number
  date: string
  title: string
}

const entry = ref<DiaryEntry | null>(null)
const loading = ref(true)
const error = ref('')
const activeTab = ref<'split' | 'original' | 'analysis'>('split')
const prevEntry = ref<DiaryNeighbor | null>(null)
const nextEntry = ref<DiaryNeighbor | null>(null)
const diaryDates = ref<string[]>([])
const dateOpen = ref(false)
const dateWrap = ref<HTMLElement | null>(null)
const dayChoices = ref<DiaryNeighbor[]>([])

// 焦虑模式触发
const showComfort = ref(false)
const comfortKeywords = ref<string[]>([])

const moodEmojis: Record<string, string> = {
  '积极': '😊', '平静': '😌', '焦虑': '😰', '低落': '😔',
  '纠结': '🤔', '兴奋': '🤩', '迷茫': '😶‍🌫️',
}

function checkNegative(text: string) {
  // 24h 内已点了「不再提示」
  const snoozeUntil = Number(localStorage.getItem('wb_comfort_snooze_until') || 0)
  if (snoozeUntil > Date.now()) return
  // 当前页面已经显示过一次也不重复弹
  if (sessionStorage.getItem('wb_comfort_shown_' + (route.params.id || ''))) return

  const result = detectNegativeEmotion(text)
  if (result.hit) {
    comfortKeywords.value = result.keywords
    showComfort.value = true
    sessionStorage.setItem('wb_comfort_shown_' + (route.params.id || ''), '1')
  }
}

const fetchEntry = async () => {
  loading.value = true
  error.value = ''
  showComfort.value = false
  try {
    const res = await fetch(`${DIARY_API_BASE}/${route.params.id}`)
    if (!res.ok) throw new Error('日记不存在')
    entry.value = await res.json()
    if (entry.value?.content) checkNegative(entry.value.content)
  } catch (e: any) {
    error.value = e.message
    entry.value = null
  } finally {
    loading.value = false
  }
}

const loadNeighbors = async () => {
  prevEntry.value = null
  nextEntry.value = null
  try {
    const res = await fetch(`${DIARY_API_BASE}/${route.params.id}/neighbors`)
    if (!res.ok) return
    const data = await res.json()
    prevEntry.value = data.prev
    nextEntry.value = data.next
  } catch { /* 相邻日记加载失败不影响正文 */ }
}

const loadDates = async () => {
  try {
    const res = await fetch(`${DIARY_API_BASE}/dates`)
    if (res.ok) {
      const body = await res.json()
      diaryDates.value = (body.dates || []).map((value: string) => String(value).slice(0, 10))
    }
  } catch { /* 日期标记失败不影响阅读 */ }
}

const openDiary = (id: number) => {
  dateOpen.value = false
  dayChoices.value = []
  if (id !== Number(route.params.id)) router.push(`/diary/${id}`)
}

const onPickDay = async (iso: string) => {
  try {
    const res = await fetch(`${DIARY_API_BASE}/by-date?date=${iso}`)
    if (!res.ok) return
    const items: DiaryNeighbor[] = (await res.json()).items || []
    if (items.length === 1) openDiary(items[0].id)
    else dayChoices.value = items
  } catch { /* 保持当前日记 */ }
}

const onDocClick = (event: MouseEvent) => {
  if (!dateOpen.value || !dateWrap.value) return
  if (event.target instanceof Node && !dateWrap.value.contains(event.target)) {
    dateOpen.value = false
    dayChoices.value = []
  }
}

const onDocKey = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    dateOpen.value = false
    dayChoices.value = []
  }
}

const goBack = () => router.push('/diary/list')

// 删除日记（二次确认，级联删除衍生的心力记录/候选/AI 提问）
const deleting = ref(false)
const buildDeleteConfirmText = async (id: number, title: string): Promise<string> => {
  let text = `确定删除「${title}」吗？`
  try {
    const res = await fetch(`${DIARY_API_BASE}/${id}/derived-counts`)
    if (res.ok) {
      const c = await res.json()
      const parts: string[] = []
      if (c.wellbeing_entries) parts.push(`${c.wellbeing_entries} 条心力记录`)
      if (c.wellbeing_candidates) parts.push(`${c.wellbeing_candidates} 条待审心力候选`)
      if (c.ai_questions) parts.push(`${c.ai_questions} 个 AI 提问`)
      if (parts.length) text += `\n\n同时会删除这篇日记衍生的：${parts.join('、')}。`
    }
  } catch { /* 计数失败不影响删除 */ }
  return text + '\n\n删除后不可恢复。'
}
const deleteEntry = async () => {
  if (!entry.value) return
  const text = await buildDeleteConfirmText(entry.value.id, entry.value.title)
  if (!confirm(text)) return
  deleting.value = true
  try {
    const res = await fetch(`${DIARY_API_BASE}/${entry.value.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error('删除失败')
    router.push('/diary/list')
  } catch (e: any) {
    alert(e.message || '删除失败')
  } finally {
    deleting.value = false
  }
}

// 教练式深挖：带来源 id 进入教练对话（正文由服务端注入，不再塞全文进气泡）
const startCoachDeepDive = () => {
  if (!entry.value) return
  router.push({ path: '/assistant', query: { origin: `diary:${entry.value.id}` } })
}

const renderMarkdown = (md: string): string => {
  if (!md) return ''
  try {
    return marked.parse(md, { breaks: true, gfm: true }) as string
  } catch {
    return md.replace(/\n/g, '<br>')
  }
}

const hasTable = (text?: string) => !!text && (/<table[\s>]/i.test(text) || /^\s*\|.+\|\s*$/m.test(text))

watch(() => route.params.id, () => {
  dayChoices.value = []
  dateOpen.value = false
  fetchEntry()
  loadNeighbors()
})
onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onDocKey)
  fetchEntry()
  loadNeighbors()
  loadDates()
})
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onDocKey)
})
</script>

<template>
  <div class="diary-detail">
    <div class="diary-detail__topbar">
      <button class="diary-detail__back" type="button" @click="goBack">
        <ArrowLeft class="ep-icon" /> 返回列表
      </button>
      <button v-if="entry" class="diary-detail__delete" type="button" :disabled="deleting" @click="deleteEntry">
        {{ deleting ? '删除中...' : '删除' }}
      </button>
    </div>

    <div v-if="entry" class="diary-nav">
      <button class="diary-nav__side" type="button" :disabled="!prevEntry" @click="prevEntry && openDiary(prevEntry.id)">
        <ArrowLeft class="ep-icon" />
        <span>
          <small>上一篇</small>
          <strong>{{ prevEntry ? prevEntry.title : '没有更新的日记' }}</strong>
          <em v-if="prevEntry">{{ prevEntry.date }}</em>
        </span>
      </button>
      <div ref="dateWrap" class="diary-nav__jump">
        <button
          class="diary-nav__date"
          type="button"
          aria-haspopup="dialog"
          :aria-expanded="dateOpen"
          @click="dateOpen = !dateOpen"
        >
          <Calendar class="ep-icon" />
          <span>{{ entry.date }}</span>
        </button>
        <div v-if="dateOpen" class="diary-nav__panel" role="dialog" aria-label="选择其他日期" @click.stop>
          <DiaryRangeCalendar
            selection="day"
            :start="String(entry.date).slice(0, 10)"
            :end="String(entry.date).slice(0, 10)"
            :dates="diaryDates"
            @pick="onPickDay"
          />
          <ul v-if="dayChoices.length > 1" class="diary-nav__choices">
            <li v-for="item in dayChoices" :key="item.id">
              <button type="button" @click="openDiary(item.id)">{{ item.title }}</button>
            </li>
          </ul>
        </div>
      </div>
      <button class="diary-nav__side diary-nav__side--next" type="button" :disabled="!nextEntry" @click="nextEntry && openDiary(nextEntry.id)">
        <span>
          <small>下一篇</small>
          <strong>{{ nextEntry ? nextEntry.title : '没有更早的日记' }}</strong>
          <em v-if="nextEntry">{{ nextEntry.date }}</em>
        </span>
        <ArrowRight class="ep-icon" />
      </button>
    </div>

    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
    </div>

    <div v-else-if="error" class="error">{{ error }}</div>

    <template v-else-if="entry">
      <!-- 头部信息 -->
      <div class="diary-detail__header">
        <h1>{{ entry.title }}</h1>
        <div class="diary-detail__meta">
          <span class="diary-detail__date"><Calendar class="ep-icon" /> {{ entry.date }}</span>
          <span v-if="entry.mood" class="diary-detail__mood">
            {{ moodEmojis[entry.mood] || '😐' }} {{ entry.mood }}
          </span>
          <span v-if="entry.source === 'sync'" class="diary-detail__source"><FolderOpened class="ep-icon" /> 文件同步</span>
        </div>
        <div v-if="entry.tags?.length" class="diary-detail__tags">
          <span v-for="tag in entry.tags" :key="tag" class="diary-detail__tag">#{{ tag }}</span>
        </div>
      </div>

      <!-- 关键问题 & 行动建议 -->
      <div class="diary-detail__summary" v-if="entry.key_issues?.length || entry.action_items?.length">
        <div v-if="entry.key_issues?.length" class="summary-section">
          <h3><Search class="ep-icon" /> 关键问题</h3>
          <ul>
            <li v-for="issue in entry.key_issues" :key="issue">{{ issue }}</li>
          </ul>
        </div>
        <div v-if="entry.action_items?.length" class="summary-section">
          <h3><Aim class="ep-icon" /> 行动建议</h3>
          <ul>
            <li v-for="item in entry.action_items" :key="item">{{ item }}</li>
          </ul>
        </div>
      </div>

      <!-- 视图切换 + 操作按钮 -->
      <div class="view-tabs">
        <button :class="{ active: activeTab === 'split' }" @click="activeTab = 'split'">分栏</button>
        <button :class="{ active: activeTab === 'original' }" @click="activeTab = 'original'">原文</button>
        <button :class="{ active: activeTab === 'analysis' }" @click="activeTab = 'analysis'">AI 分析</button>
        <span class="view-tabs__spacer"></span>
        <ContentActions :text="entry.ai_analysis || entry.content || ''" />
      </div>

      <!-- 内容区 -->
      <div class="diary-detail__content" :class="{ 'diary-detail__content--split': activeTab === 'split' }">
        <div v-if="activeTab !== 'analysis'" class="content-panel content-panel--original">
          <h3 class="content-panel__title"><Document class="ep-icon" /> 原文</h3>
          <div class="content-panel__body">
            <div v-if="hasTable(entry.content)" class="markdown-body" v-html="renderMarkdown(entry.content)"></div>
            <pre v-else>{{ entry.content }}</pre>
          </div>
          <!-- 图片展示 -->
          <div v-if="entry.images && entry.images.length > 0" class="content-panel__images">
            <div v-for="(url, idx) in entry.images" :key="idx" class="content-panel__img-item">
              <img :src="url.startsWith('http') ? url : `${API_BASE}${url}`" alt="" loading="lazy" />
            </div>
          </div>
        </div>

        <div v-if="activeTab !== 'original' && entry.ai_analysis" class="content-panel content-panel--analysis">
          <h3 class="content-panel__title"><MagicStick class="ep-icon" /> AI 分析</h3>
          <div class="content-panel__body" v-html="renderMarkdown(entry.ai_analysis)"></div>
        </div>

        <div v-if="activeTab !== 'original' && !entry.ai_analysis" class="content-panel content-panel--empty">
          <p>暂无 AI 分析</p>
        </div>
      </div>

      <!-- 教练式深挖入口 -->
      <div class="diary-detail__coach">
        <button class="diary-detail__coach-btn" @click="startCoachDeepDive">
          <span class="diary-detail__coach-icon"><Aim class="ep-icon" /></span>
          <span class="diary-detail__coach-text">
            <strong>和 AI 教练深挖这篇日记</strong>
            <em>让 AI 先提问、不急着下结论，看见描述背后的盲区</em>
          </span>
          <span class="diary-detail__coach-arrow">→</span>
        </button>
      </div>
    </template>

    <!-- 焦虑模式安抚浮层 -->
    <ComfortPopover
      v-if="showComfort"
      :trigger-keywords="comfortKeywords"
      @close="showComfort = false"
      @snooze="showComfort = false"
    />
  </div>
</template>

<style lang="scss" scoped>
.diary-detail {
  &__back {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-height: 44px;
    background: transparent;
    border: none;
    color: $text-secondary;
    cursor: pointer;
    font-size: $font-size-md;
    padding: 0;

    &:hover { color: $primary-color; }
    &:focus-visible { outline: 2px solid $primary-color; outline-offset: 2px; }
  }

  &__topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $spacing-sm;
  }
}

.diary-nav {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: $spacing-sm;
  margin-bottom: $spacing-md;
  align-items: stretch;

  @media (max-width: $breakpoint-sm) {
    grid-template-columns: 1fr 1fr;

    &__jump { grid-column: 1 / -1; order: -1; }
  }

  &__side,
  &__date,
  &__choices button {
    cursor: pointer;
  }

  &__side {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 44px;
    min-width: 0;
    padding: 8px 12px;
    border: 1px solid $border-color;
    border-radius: $border-radius-md;
    background: rgba(255, 255, 255, 0.8);
    text-align: left;
    color: $text-primary;

    span { min-width: 0; display: flex; flex-direction: column; }
    small { color: $text-muted; font-size: $font-size-xs; }
    strong {
      font-size: $font-size-sm;
      font-weight: 500;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    em { font-style: normal; color: $text-secondary; font-size: $font-size-xs; }

    &:hover:not(:disabled) { border-color: $primary-color; }
    &:focus-visible { outline: 2px solid $primary-color; outline-offset: 2px; }
    &:disabled { opacity: 0.45; cursor: not-allowed; }

    &--next { text-align: right; span { align-items: flex-end; } }
  }

  &__jump { position: relative; }

  &__date {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    width: 100%;
    min-height: 44px;
    padding: 0 14px;
    border: 1px solid $border-color;
    border-radius: $border-radius-md;
    background: rgba(255, 255, 255, 0.8);
    color: $text-primary;
    font-size: $font-size-md;

    &:hover { border-color: $primary-color; }
    &:focus-visible { outline: 2px solid $primary-color; outline-offset: 2px; }
  }

  &__panel {
    position: absolute;
    z-index: $z-index-dropdown;
    top: calc(100% + 8px);
    left: 50%;
    transform: translateX(-50%);
    box-shadow: $shadow-lg;

    @media (max-width: $breakpoint-sm) {
      left: 0;
      transform: none;
    }
  }

  &__choices {
    list-style: none;
    margin: 0;
    padding: 8px;
    background: #fff;
    border: 1px solid $border-color;
    border-top: none;
    border-radius: 0 0 $border-radius-md $border-radius-md;
    max-height: 180px;
    overflow: auto;

    button {
      width: 100%;
      min-height: 44px;
      border: none;
      background: transparent;
      text-align: left;
      font-size: $font-size-sm;
      border-radius: $border-radius-sm;
      padding: 0 8px;

      &:hover { background: rgba($primary-color, 0.08); }
      &:focus-visible { outline: 2px solid $primary-color; }
    }
  }
}

.diary-detail {

  &__delete {
    min-height: 44px;
    background: transparent;
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: #EF4444;
    cursor: pointer;
    font-size: $font-size-sm;
    padding: 0 16px;
    border-radius: 99px;
    transition: background 0.15s, color 0.15s;

    &:hover:not(:disabled) { background: rgba(239, 68, 68, 0.08); }
    &:focus-visible { outline: 2px solid $danger-color; outline-offset: 2px; }
    &:disabled { opacity: 0.5; cursor: not-allowed; }
  }

  &__header {
    @include glass-card;
    padding: $spacing-lg;
    margin-bottom: $spacing-md;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-md;
      border-radius: $border-radius-md;
    }

    h1 {
      font-size: $font-size-xl;
      margin-bottom: $spacing-sm;

      @media (max-width: $breakpoint-sm) {
        font-size: $font-size-lg;
      }
    }
  }

  &__meta {
    display: flex;
    gap: $spacing-md;
    font-size: $font-size-sm;
    color: $text-secondary;
    flex-wrap: wrap;
  }

  &__tags {
    display: flex;
    gap: $spacing-sm;
    margin-top: $spacing-sm;
  }

  &__tag {
    padding: 2px 8px;
    background: rgba($accent-color, 0.1);
    color: $accent-color;
    border-radius: 99px;
    font-size: $font-size-xs;
  }

  &__summary {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: $spacing-md;
    margin-bottom: $spacing-md;

    @media (max-width: $breakpoint-md) { grid-template-columns: 1fr; }
  }

  &__content {
    &--split {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: $spacing-md;

      @media (max-width: $breakpoint-md) { grid-template-columns: 1fr; }
    }
  }

  &__coach {
    margin-top: $spacing-md;
  }

  &__coach-btn {
    width: 100%;
    display: flex;
    align-items: center;
    gap: $spacing-md;
    padding: $spacing-md $spacing-lg;
    border: 1px dashed rgba($primary-color, 0.4);
    border-radius: $border-radius-md;
    background: linear-gradient(135deg, rgba($primary-color, 0.05), rgba($accent-color, 0.05));
    cursor: pointer;
    text-align: left;
    transition: all $transition-fast;

    &:hover {
      border-style: solid;
      border-color: $primary-color;
      background: linear-gradient(135deg, rgba($primary-color, 0.1), rgba($accent-color, 0.1));
    }
  }

  &__coach-icon {
    font-size: 24px;
    flex-shrink: 0;
  }

  &__coach-text {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;

    strong { font-size: $font-size-sm; color: $text-primary; }
    em { font-size: $font-size-xs; color: $text-secondary; font-style: normal; }
  }

  &__coach-arrow {
    color: $text-muted;
    font-size: 18px;
    flex-shrink: 0;
  }
}

.summary-section {
  @include glass-card;
  padding: $spacing-md;

  h3 { font-size: $font-size-sm; margin-bottom: $spacing-sm; }
  ul { padding-left: $spacing-lg; }
  li { font-size: $font-size-sm; margin-bottom: $spacing-xs; color: $text-secondary; }
}

.view-tabs {
  display: flex;
  gap: $spacing-xs;
  margin-bottom: $spacing-md;
  align-items: center;

  &__spacer { flex: 1; }
  &__icon-btn {
    width: 36px; height: 36px; border-radius: 8px; border: 1px solid $border-color;
    background: transparent; cursor: pointer; font-size: 16px; display: flex; align-items: center; justify-content: center;
    transition: all 0.15s;
    &:hover { border-color: $primary-color; background: rgba($primary-color, 0.05); }
  }

  button {
    padding: $spacing-sm $spacing-md;
    border-radius: $border-radius-sm;
    border: 1px solid $border-color;
    background: transparent;
    color: $text-secondary;
    font-size: $font-size-sm;
    cursor: pointer;
    transition: all $transition-fast;

    &:hover { border-color: $primary-color; color: $primary-color; }

    &.active {
      background: linear-gradient(135deg, $primary-color, $accent-color);
      color: white;
      border-color: transparent;
    }
  }
}

.content-panel {
  @include glass-card;
  padding: $spacing-lg;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    border-radius: $border-radius-md;
  }

  &__title {
    font-size: $font-size-md;
    margin-bottom: $spacing-md;
    padding-bottom: $spacing-sm;
    border-bottom: 2px solid $border-color;
  }

  &__body {
    font-size: $font-size-sm;
    line-height: 1.8;
    max-height: 600px;
    overflow-y: auto;
    @include custom-scrollbar;

    pre {
      white-space: pre-wrap;
      word-wrap: break-word;
      font-family: inherit;
      margin: 0;
    }
  }

  &--analysis .content-panel__body {
    :deep(h3) { font-size: $font-size-md; margin: $spacing-md 0 $spacing-sm; color: $primary-color; }
    :deep(h4) { font-size: $font-size-sm; margin: $spacing-sm 0; font-weight: 600; }
    :deep(strong) { color: $text-primary; }
    :deep(blockquote) { border-left: 3px solid $primary-color; padding-left: $spacing-md; color: $text-secondary; margin: $spacing-sm 0; }
    :deep(code) { background: rgba($primary-color, 0.1); padding: 1px 4px; border-radius: 3px; }
    :deep(li) { margin-bottom: $spacing-xs; }
  }

  &__images {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: $spacing-md;
    padding-top: $spacing-md;
    border-top: 1px solid rgba(0, 0, 0, 0.06);
  }

  &__img-item {
    width: 100px;
    height: 100px;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid rgba(0, 0, 0, 0.08);

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      cursor: pointer;
    }

    @media (max-width: $breakpoint-sm) {
      width: 80px;
      height: 80px;
    }
  }

  &--empty {
    @include flex-center;
    color: $text-muted;
    min-height: 200px;
  }
}

.loading {
  text-align: center;
  padding: $spacing-xxl;

  &__spinner {
    width: 40px; height: 40px;
    border: 3px solid $border-color;
    border-top-color: $primary-color;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto;
  }
}

.error {
  @include glass-card;
  padding: $spacing-xl;
  text-align: center;
  color: $danger-color;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.rewrite-overlay { position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; padding: 20px; }
.rewrite-modal { background: white; border-radius: 12px; width: 100%; max-width: 600px; max-height: 80vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.2);
  &__header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid #eee; h3 { margin: 0; } }
  &__body { padding: 20px; }
}
.btn-close { background: none; border: none; font-size: 18px; cursor: pointer; color: #666; &:hover { color: #333; } }
.btn-primary { padding: 10px 20px; border-radius: 8px; border: none; background: linear-gradient(135deg, $primary-color, $accent-color); color: white; font-size: 14px; font-weight: 600; cursor: pointer; &:hover { opacity: 0.9; } &:disabled { opacity: 0.5; } }
.rewrite-platforms { display: flex; flex-wrap: wrap; gap: 8px; }
.rewrite-platform-btn { padding: 8px 16px; border-radius: 8px; border: 1px solid #d0d7de; background: white; cursor: pointer; font-size: 14px; transition: all 0.15s;
  &:hover { border-color: $primary-color; color: $primary-color; }
  &--active { background: rgba($primary-color, 0.1); border-color: $primary-color; color: $primary-color; font-weight: 600; }
}
.rewrite-result { margin-top: 12px; position: relative;
  &__copy { position: absolute; top: 8px; right: 8px; background: rgba(255,255,255,0.9); border: 1px solid #d0d7de; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 14px; z-index: 1; &:hover { border-color: $primary-color; } }
  &__text { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 16px; font-size: 14px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; max-height: 400px; overflow-y: auto; font-family: inherit; }
}
</style>
