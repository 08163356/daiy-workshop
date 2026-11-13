<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DIARY_API_BASE } from '@/config'
import DiaryRangeCalendar from './DiaryRangeCalendar.vue'
import { DIARY_CHANGED } from '@/utils/dailyEvents'
const route = useRoute()
const router = useRouter()

interface DiaryItem {
  id: number
  date: string
  title: string
  mood: string | null
  tags: string[] | null
  source: string
  created_at: string
}

const PAGE_SIZE = 20

const entries = ref<DiaryItem[]>([])
const total = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const skip = ref(0)
const keyword = ref('')
const moodFilter = ref('')
const startDate = ref('')
const endDate = ref('')
const diaryDates = ref<string[]>([])
const dateOpen = ref(false)
const dateWrap = ref<HTMLElement | null>(null)

const rangeLabel = computed(() => {
  if (startDate.value && endDate.value && startDate.value !== endDate.value) {
    return `${startDate.value} 至 ${endDate.value}`
  }
  return startDate.value || endDate.value || '选择日期'
})

const dateParts = (value: string) => {
  const [y, m, d] = value.slice(0, 10).split('-')
  return { y, m: String(Number(m)), d: String(Number(d)) }
}

const onRangeChange = (start: string, end: string) => {
  startDate.value = start
  endDate.value = end
  dateOpen.value = false
  fetchEntries()
}

const onDocClick = (event: MouseEvent) => {
  if (!dateOpen.value || !dateWrap.value) return
  if (event.target instanceof Node && !dateWrap.value.contains(event.target)) dateOpen.value = false
}

const onDocKey = (event: KeyboardEvent) => {
  if (event.key === 'Escape') dateOpen.value = false
}

const moodEmojis: Record<string, string> = {
  '积极': '😊', '平静': '😌', '焦虑': '😰', '低落': '😔',
  '纠结': '🤔', '兴奋': '🤩', '迷茫': '😶‍🌫️', '愤怒': '😤',
  '感恩': '🙏', '释然': '😮‍💨',
}

const hasMore = () => skip.value + entries.value.length < total.value

const buildParams = (currentSkip: number) => {
  const p = new URLSearchParams()
  if (keyword.value) p.set('keyword', keyword.value)
  if (moodFilter.value) p.set('mood', moodFilter.value)
  if (startDate.value) p.set('start_date', startDate.value)
  if (endDate.value) p.set('end_date', endDate.value)
  p.set('limit', String(PAGE_SIZE))
  p.set('skip', String(currentSkip))
  return p
}

// 首次加载或筛选变更时，重置列表
const fetchEntries = async () => {
  loading.value = true
  skip.value = 0
  try {
    const res = await fetch(`${DIARY_API_BASE}?${buildParams(0)}`)
    const data = await res.json()
    entries.value = data.items
    total.value = data.total
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

// 追加下一页
const loadMore = async () => {
  if (loadingMore.value || !hasMore()) return
  loadingMore.value = true
  const nextSkip = skip.value + entries.value.length
  try {
    const res = await fetch(`${DIARY_API_BASE}?${buildParams(nextSkip)}`)
    const data = await res.json()
    entries.value.push(...data.items)
    skip.value = nextSkip
  } catch (e) {
    console.error(e)
  } finally {
    loadingMore.value = false
  }
}

const goToDetail = (id: number) => router.push(`/diary/${id}`)
const goToChat = () => router.push({ path: '/assistant', query: { prefill: '/日记 ' } })

// 删除日记（二次确认，级联删除衍生数据，不触发卡片跳转）
const deleteEntry = async (entry: DiaryItem) => {
  let text = `确定删除「${entry.title}」吗？`
  try {
    const res = await fetch(`${DIARY_API_BASE}/${entry.id}/derived-counts`)
    if (res.ok) {
      const c = await res.json()
      const parts: string[] = []
      if (c.wellbeing_entries) parts.push(`${c.wellbeing_entries} 条心力记录`)
      if (c.wellbeing_candidates) parts.push(`${c.wellbeing_candidates} 条待审心力候选`)
      if (c.ai_questions) parts.push(`${c.ai_questions} 个 AI 提问`)
      if (parts.length) text += `\n\n同时会删除这篇日记衍生的：${parts.join('、')}。`
    }
  } catch { /* 计数失败不影响删除 */ }
  if (!confirm(text + '\n\n删除后不可恢复。')) return
  try {
    const res = await fetch(`${DIARY_API_BASE}/${entry.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error('删除失败')
    entries.value = entries.value.filter(e => e.id !== entry.id)
    total.value = Math.max(0, total.value - 1)
  } catch (e: any) {
    alert(e.message || '删除失败')
  }
}

const loadDates = async () => {
  try {
    const res = await fetch(`${DIARY_API_BASE}/dates`)
    if (res.ok) {
      const body = await res.json()
      diaryDates.value = (body.dates || []).map((value: string) => String(value).slice(0, 10))
    }
  } catch { /* 日期标记加载失败不影响列表 */ }
}

const onDiaryChanged = () => {
  loadDates()
  fetchEntries()
}

onMounted(() => {
  const start = typeof route.query.start === 'string' ? route.query.start : ''
  const end = typeof route.query.end === 'string' ? route.query.end : ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(start)) startDate.value = start
  if (/^\d{4}-\d{2}-\d{2}$/.test(end)) endDate.value = end
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onDocKey)
  window.addEventListener(DIARY_CHANGED, onDiaryChanged)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') onDiaryChanged()
  })
  loadDates()
  fetchEntries()
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onDocKey)
  window.removeEventListener(DIARY_CHANGED, onDiaryChanged)
})
</script>

<template>
  <div class="diary-list">
    <div class="diary-list__header">
      <div>
        <h1>
          <Notebook class="ep-icon" />
          日记列表
        </h1>
        <p class="diary-list__count">
          共 {{ total }} 篇，已显示 {{ entries.length }} 篇
        </p>
      </div>
      <button class="btn btn--primary" @click="goToChat">
        <EditPen class="ep-icon" />写新日记
      </button>
    </div>

    <!-- 筛选 -->
    <div class="diary-list__filters">
      <div class="diary-list__search-wrap">
        <Search class="ep-icon diary-list__search-icon" />
        <input
          v-model="keyword"
          class="diary-list__search"
          placeholder="搜索日记内容..."
          @keyup.enter="fetchEntries"
        />
      </div>
      <select v-model="moodFilter" class="diary-list__mood-select" aria-label="情绪" @change="fetchEntries">
        <option value="">全部情绪</option>
        <option v-for="(emoji, mood) in moodEmojis" :key="mood" :value="mood">{{ emoji }} {{ mood }}</option>
      </select>
      <div ref="dateWrap" class="diary-list__date-wrap">
        <button
          class="diary-list__date-btn"
          type="button"
          aria-haspopup="dialog"
          :aria-expanded="dateOpen"
          @click="dateOpen = !dateOpen"
        >
          <Calendar class="ep-icon" />
          <span>{{ rangeLabel }}</span>
        </button>
        <div v-if="dateOpen" class="diary-list__date-panel" role="dialog" aria-label="选择日期范围" @click.stop>
          <DiaryRangeCalendar
            :start="startDate"
            :end="endDate"
            :dates="diaryDates"
            @change="onRangeChange"
          />
        </div>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="entries.length === 0" class="empty">
      <Document class="ep-icon empty__icon" />
      <p>暂无日记</p>
      <button class="btn btn--primary" @click="goToChat">写第一篇日记</button>
    </div>

    <!-- 列表 -->
    <div v-else class="entries">
      <div
        v-for="entry in entries"
        :key="entry.id"
        class="entry-card"
        role="link"
        tabindex="0"
        @click="goToDetail(entry.id)"
        @keydown.enter="goToDetail(entry.id)"
      >
        <div class="entry-card__left">
          <div class="entry-card__date-box">
            <span class="entry-card__day">{{ dateParts(entry.date).d }}</span>
            <span class="entry-card__month">{{ dateParts(entry.date).y }}.{{ dateParts(entry.date).m }}</span>
          </div>
        </div>
        <div class="entry-card__content">
          <h3 class="entry-card__title">{{ entry.title }}</h3>
          <div class="entry-card__meta">
            <span v-if="entry.mood" class="entry-card__mood">
              {{ moodEmojis[entry.mood] || '😐' }} {{ entry.mood }}
            </span>
            <span v-if="entry.tags?.length" class="entry-card__tags">
              <span v-for="tag in entry.tags.slice(0, 4)" :key="tag">#{{ tag }}</span>
            </span>
            <span v-if="entry.source === 'sync'" class="entry-card__source">
              <FolderOpened class="ep-icon" />文件同步
            </span>
          </div>
        </div>
        <button class="entry-card__delete" title="删除这篇日记" @click.stop="deleteEntry(entry)">×</button>
        <span class="entry-card__arrow">→</span>
      </div>

      <!-- 加载更多 -->
      <div class="load-more">
        <button
          v-if="hasMore()"
          class="load-more__btn"
          :disabled="loadingMore"
          @click="loadMore"
        >
          <span v-if="loadingMore" class="load-more__spinner"></span>
          <span v-else>加载更多（剩余 {{ total - entries.length }} 篇）</span>
        </button>
        <p v-else class="load-more__done">已显示全部 {{ total }} 篇</p>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.diary-list {
  &__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: $spacing-lg;

    h1 {
      font-size: $font-size-xl;
      display: flex;
      align-items: center;
      gap: 8px;

      @media (max-width: $breakpoint-sm) { font-size: $font-size-lg; }
    }
  }

  &__count {
    font-size: $font-size-sm;
    color: $text-secondary;
    margin-top: $spacing-xs;
  }

  &__filters {
    display: flex;
    gap: $spacing-sm;
    margin-bottom: $spacing-lg;
    flex-wrap: wrap;
    align-items: center;
  }

  &__search-wrap {
    flex: 1 1 220px;
    position: relative;
    display: flex;
    align-items: center;

    @media (max-width: $breakpoint-sm) { flex-basis: 100%; }
  }

  &__search-icon {
    position: absolute;
    left: 10px;
    color: $text-muted;
    pointer-events: none;
  }

  &__search {
    width: 100%;
    min-height: 44px;
    padding: $spacing-sm $spacing-md $spacing-sm 34px;
    border: 1px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-md;
    background: rgba(255, 255, 255, 0.7);

    &:focus-visible { outline: 2px solid $primary-color; outline-offset: 1px; }
  }

  &__mood-select,
  &__date-btn {
    min-height: 44px;
    padding: 0 $spacing-md;
    border: 1px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-md;
    background: rgba(255, 255, 255, 0.7);
  }

  &__mood-select {
    min-width: 128px;

    &:focus-visible { outline: 2px solid $primary-color; outline-offset: 1px; }

    @media (max-width: $breakpoint-sm) { flex: 1; }
  }

  &__date-wrap {
    position: relative;

    @media (max-width: $breakpoint-sm) { flex: 1; }
  }

  &__date-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    max-width: 280px;
    color: $text-primary;
    cursor: pointer;

    span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    &:hover { border-color: $primary-color; }
    &:focus-visible { outline: 2px solid $primary-color; outline-offset: 1px; }

    @media (max-width: $breakpoint-sm) { width: 100%; max-width: none; }
  }

  &__date-panel {
    position: absolute;
    z-index: $z-index-dropdown;
    top: calc(100% + 8px);
    right: 0;
    box-shadow: $shadow-lg;

    @media (max-width: $breakpoint-sm) {
      left: 0;
      right: auto;
    }
  }
}

.entries { display: grid; gap: $spacing-md; }

.entry-card {
  @include glass-card;
  padding: $spacing-md $spacing-lg;
  display: flex;
  align-items: center;
  gap: $spacing-lg;
  cursor: pointer;
  transition: all $transition-fast;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    gap: $spacing-md;
    border-radius: $border-radius-md;
  }

  &:focus-visible {
    outline: 2px solid $primary-color;
    outline-offset: 2px;
  }

  @media (hover: hover) and (pointer: fine) {
    &:hover { box-shadow: $shadow-lg; }
  }

  &__left { flex-shrink: 0; }

  &__date-box {
    width: 52px;
    text-align: center;
    padding: $spacing-sm;
    background: linear-gradient(135deg, $primary-color, $accent-color);
    border-radius: $border-radius-sm;
    color: white;
  }

  &__day { font-size: $font-size-xl; font-weight: 700; display: block; line-height: 1; }
  &__month { font-size: $font-size-xs; }
  &__content { flex: 1; min-width: 0; }
  &__title { font-size: $font-size-md; font-weight: 500; margin-bottom: $spacing-xs; line-height: 1.5; @include text-ellipsis; }

  &__meta {
    display: flex;
    gap: $spacing-md;
    font-size: $font-size-xs;
    color: $text-secondary;
    flex-wrap: wrap;
  }

  &__mood { font-weight: 500; }
  &__tags span { color: $accent-color; margin-right: $spacing-xs; }
  &__source { color: $text-muted; display: flex; align-items: center; }
  &__arrow { color: $text-muted; font-size: $font-size-lg; flex-shrink: 0; }

  &__delete {
    flex-shrink: 0;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    border: none;
    background: rgba(0, 0, 0, 0.04);
    color: $text-muted;
    font-size: 14px;
    line-height: 1;
    cursor: pointer;
    transition: all 0.15s;

    &:hover { background: rgba(239, 68, 68, 0.12); color: #EF4444; }
  }
}

.load-more {
  display: flex;
  justify-content: center;
  padding: $spacing-lg 0;

  &__btn {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    padding: 10px 28px;
    border: 1px solid rgba($primary-color, 0.3);
    border-radius: $border-radius-md;
    font-size: $font-size-sm;
    color: $primary-color;
    background: rgba($primary-color, 0.05);
    cursor: pointer;
    transition: all 0.2s;

    &:hover:not(:disabled) {
      background: rgba($primary-color, 0.12);
      border-color: $primary-color;
    }

    &:disabled { opacity: 0.6; cursor: not-allowed; }
  }

  &__spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba($primary-color, 0.25);
    border-top-color: $primary-color;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  &__done {
    font-size: $font-size-xs;
    color: $text-muted;
    padding: $spacing-sm 0;
  }
}

.empty {
  text-align: center;
  padding: $spacing-xxl;
  color: $text-secondary;

  &__icon {
    display: flex;
    justify-content: center;
    margin: 0 auto $spacing-md;
    font-size: 48px;
    color: $text-muted;
    opacity: 0.5;
  }
}

.loading {
  text-align: center;
  padding: $spacing-xxl;

  &__spinner {
    width: 40px;
    height: 40px;
    border: 3px solid $border-color;
    border-top-color: $primary-color;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto;
  }
}

.btn {
  display: flex;
  align-items: center;
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all $transition-fast;

  &--primary {
    min-height: 44px;
    gap: 6px;
    background: linear-gradient(135deg, $primary-color, $accent-color);
    color: white;
    &:hover { opacity: 0.9; }
    &:focus-visible { outline: 2px solid $primary-color; outline-offset: 2px; }
  }
}

@media (prefers-reduced-motion: reduce) {
  .entry-card, .btn, .load-more__btn { transition: none; }
}

@keyframes spin { to { transform: rotate(360deg); } }
</style>
