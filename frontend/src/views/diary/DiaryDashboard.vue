<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { DIARY_API_BASE } from '@/config'

const router = useRouter()

interface DiaryOverview {
  total_count: number
  mood_distribution: Record<string, number>
  tag_distribution: Record<string, number>
  recent_entries: any[]
  monthly_count: Record<string, number>
}

const overview = ref<DiaryOverview | null>(null)
const loading = ref(true)
const error = ref('')

const moodEmojis: Record<string, string> = {
  '积极': '😊', '平静': '😌', '焦虑': '😰', '低落': '😔',
  '纠结': '🤔', '兴奋': '🤩', '迷茫': '😶‍🌫️', '愤怒': '😤',
  '感恩': '🙏', '释然': '😮‍💨',
}

const fetchOverview = async () => {
  loading.value = true
  try {
    const res = await fetch(`${DIARY_API_BASE}/overview`)
    if (!res.ok) throw new Error('加载失败')
    overview.value = await res.json()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const goToChat = () => router.push({ path: '/assistant', query: { prefill: '/日记 ' } })
const goToList = () => router.push('/diary/list')
const goToDetail = (id: number) => router.push(`/diary/${id}`)

const recentMonths = computed(() => {
  const raw = overview.value?.monthly_count || {}
  return Object.entries(raw)
    .filter(([month]) => /^\d{4}-\d{2}$/.test(month))
    .sort((a, b) => b[0].localeCompare(a[0]))
    .slice(0, 8)
    .map(([month, count]) => ({ month, count }))
})

const moodMax = computed(() => {
  const values = Object.values(overview.value?.mood_distribution || {})
  return Math.max(1, ...values)
})

const openMonth = (month: string) => {
  const [year, rawMonth] = month.split('-').map(Number)
  const last = new Date(year, rawMonth, 0).getDate()
  const mm = String(rawMonth).padStart(2, '0')
  router.push({
    path: '/diary/list',
    query: {
      start: `${year}-${mm}-01`,
      end: `${year}-${mm}-${String(last).padStart(2, '0')}`,
    },
  })
}

onMounted(fetchOverview)
</script>

<template>
  <div class="diary-dashboard">
    <div class="diary-dashboard__header">
      <div>
        <h1><Notebook class="ep-icon" />日记系统</h1>
        <p class="diary-dashboard__subtitle">记录生活，认识自己</p>
      </div>
      <button class="btn btn--primary" type="button" @click="goToChat">
        <EditPen class="ep-icon" />写新日记
      </button>
    </div>

    <!-- 加载 / 错误 -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
      <p>加载中...</p>
    </div>

    <div v-else-if="error" class="error-card">
      <p>{{ error }}</p>
      <button class="btn btn--ghost" @click="fetchOverview">重试</button>
    </div>

    <template v-else-if="overview">
      <!-- 统计卡片 -->
      <div class="stats-grid">
        <div class="stat-card">
          <span class="stat-card__icon"><Document class="ep-icon" /></span>
          <span>
            <span class="stat-card__value">{{ overview.total_count }}</span>
            <span class="stat-card__label">日记总数</span>
          </span>
        </div>
        <div class="stat-card">
          <span class="stat-card__icon"><Calendar class="ep-icon" /></span>
          <span>
            <span class="stat-card__value">{{ Object.keys(overview.monthly_count).length }}</span>
            <span class="stat-card__label">记录月份</span>
          </span>
        </div>
        <div class="stat-card">
          <span class="stat-card__icon"><Histogram class="ep-icon" /></span>
          <span>
            <span class="stat-card__value">{{ Object.keys(overview.mood_distribution).length }}</span>
            <span class="stat-card__label">情绪类型</span>
          </span>
        </div>
        <div class="stat-card">
          <span class="stat-card__icon"><PriceTag class="ep-icon" /></span>
          <span>
            <span class="stat-card__value">{{ Object.keys(overview.tag_distribution).length }}</span>
            <span class="stat-card__label">标签数量</span>
          </span>
        </div>
      </div>

      <div v-if="recentMonths.length" class="month-row" aria-label="按月份查看">
        <button
          v-for="item in recentMonths"
          :key="item.month"
          class="month-chip"
          type="button"
          @click="openMonth(item.month)"
        >
          <span>{{ item.month }}</span>
          <strong>{{ item.count }}</strong>
        </button>
      </div>

      <div class="diary-dashboard__grid">
        <!-- 情绪分布 -->
        <div class="section-card" v-if="Object.keys(overview.mood_distribution).length > 0">
          <h3><Histogram class="ep-icon" />情绪分布</h3>
          <div class="mood-list">
            <div v-for="(count, mood) in overview.mood_distribution" :key="mood" class="mood-item">
              <span class="mood-item__name">{{ moodEmojis[mood] || '' }} {{ mood }}</span>
              <div class="mood-item__bar">
                <div class="mood-item__fill" :style="{ width: (count / moodMax * 100) + '%' }"></div>
              </div>
              <span class="mood-item__count">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- 最近日记 -->
        <div class="section-card">
          <div class="section-card__header">
            <h3><List class="ep-icon" />最近日记</h3>
            <button class="btn btn--sm btn--ghost" type="button" @click="goToList">查看全部</button>
          </div>
          <div v-if="overview.recent_entries.length === 0" class="empty-state">
            <span class="empty-state__icon"><Document class="ep-icon" /></span>
            <p>还没有日记</p>
            <button class="btn btn--primary" @click="goToChat">写第一篇日记</button>
          </div>
          <div v-else class="entry-list">
            <div
              v-for="entry in overview.recent_entries"
              :key="entry.id"
              class="entry-item"
              role="link"
              tabindex="0"
              @click="goToDetail(entry.id)"
              @keydown.enter="goToDetail(entry.id)"
            >
              <div class="entry-item__header">
                <span class="entry-item__date">{{ entry.date }}</span>
                <span v-if="entry.mood" class="entry-item__mood">{{ moodEmojis[entry.mood] || '😐' }} {{ entry.mood }}</span>
              </div>
              <span class="entry-item__title">{{ entry.title }}</span>
              <div class="entry-item__tags" v-if="entry.tags?.length">
                <span v-for="tag in entry.tags.slice(0, 3)" :key="tag" class="entry-item__tag">#{{ tag }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.diary-dashboard {
  &__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: $spacing-lg;

    h1 {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: $font-size-xl;

      @media (max-width: $breakpoint-sm) {
        font-size: $font-size-lg;
      }
    }
  }

  &__subtitle {
    color: $text-secondary;
    font-size: $font-size-sm;
    margin-top: $spacing-xs;
  }

  &__grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: $spacing-lg;

    @media (max-width: $breakpoint-md) {
      grid-template-columns: 1fr;
    }

    @media (max-width: $breakpoint-sm) {
      gap: $spacing-md;
    }
  }
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $spacing-md;
  margin-bottom: $spacing-lg;

  @media (max-width: $breakpoint-md) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (max-width: $breakpoint-sm) {
    gap: $spacing-sm;
  }
}

.stat-card {
  @include glass-card;
  display: flex;
  align-items: center;
  gap: $spacing-md;
  padding: $spacing-md $spacing-lg;
  text-align: left;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    border-radius: $border-radius-md;
  }

  &__icon {
    width: 44px;
    height: 44px;
    border-radius: 12px;
    display: flex;
    justify-content: center;
    align-items: center;
    flex-shrink: 0;
    font-size: 20px;
    color: $primary-color;
    background: rgba($primary-color, 0.1);
  }
  &__value {
    font-size: $font-size-xl; font-weight: 700; color: $text-primary; display: block; line-height: 1.2;
  }
  &__label { font-size: $font-size-sm; color: $text-secondary; margin-top: 2px; display: block; }
}

.month-row {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-sm;
  margin-bottom: $spacing-lg;
}

.month-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid $border-color;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  color: $text-primary;
  cursor: pointer;
  font-size: $font-size-sm;

  strong { color: $primary-color; }
  &:hover { border-color: $primary-color; }
  &:focus-visible { outline: 2px solid $primary-color; outline-offset: 2px; }
}

.section-card {
  @include glass-card;
  padding: $spacing-lg;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    border-radius: $border-radius-md;
  }

  h3 {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: $font-size-md;
    margin-bottom: $spacing-md;
  }

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $spacing-md;

    h3 { margin-bottom: 0; }
  }
}

.mood-list {
  display: grid;
  gap: $spacing-sm;
  // 超过约 20 条出滚动条（单行约 28px + 间距）
  max-height: 640px;
  overflow-y: auto;
  padding-right: 4px;
}

.mood-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;

  &__name { min-width: 72px; font-size: $font-size-sm; color: $text-primary; }
  &__bar { flex: 1; height: 8px; background: rgba($primary-color, 0.1); border-radius: 4px; overflow: hidden; }
  &__fill { height: 100%; background: linear-gradient(90deg, $primary-color, $accent-color); border-radius: 4px; transition: width 0.2s ease; }
  &__count { font-size: $font-size-xs; color: $text-muted; min-width: 24px; text-align: right; }
}

.entry-list { display: grid; gap: $spacing-sm; }

.entry-item {
  min-height: 44px;
  padding: $spacing-md;
  border-radius: $border-radius-sm;
  background: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  transition: background $transition-fast;

  &:hover {
    @media (hover: hover) and (pointer: fine) {
      background: rgba($primary-color, 0.05);
    }
  }

  &:focus-visible {
    outline: 2px solid $primary-color;
    outline-offset: 2px;
  }

  &__header {
    display: flex;
    justify-content: space-between;
    margin-bottom: $spacing-xs;
  }

  &__date { font-size: $font-size-xs; color: $text-muted; }
  &__mood { font-size: $font-size-xs; }
  &__title { font-weight: 500; font-size: $font-size-md; line-height: 1.5; }

  &__tags {
    display: flex;
    gap: $spacing-xs;
    margin-top: $spacing-xs;
  }

  &__tag {
    font-size: $font-size-xs;
    color: $accent-color;
  }
}

.empty-state {
  text-align: center;
  padding: $spacing-xl;
  color: $text-secondary;

  &__icon { font-size: 40px; display: flex; justify-content: center; margin-bottom: $spacing-md; color: $text-muted; }
}

.loading {
  text-align: center;
  padding: $spacing-xxl;
  color: $text-secondary;

  &__spinner {
    width: 40px; height: 40px;
    border: 3px solid $border-color;
    border-top-color: $primary-color;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto $spacing-md;
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
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 44px;
    background: linear-gradient(135deg, $primary-color, $accent-color);
    color: white;
    &:hover { opacity: 0.9; }
    &:focus-visible { outline: 2px solid $primary-color; outline-offset: 2px; }
  }

  &--ghost {
    min-height: 44px;
    background: transparent;
    color: $text-secondary;
    &:hover { color: $primary-color; }
    &:focus-visible { outline: 2px solid $primary-color; outline-offset: 2px; }
  }

  &--sm { padding: 4px 12px; font-size: $font-size-xs; }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .mood-item__fill, .entry-item, .btn { transition: none; }
  .loading__spinner { animation: none; }
}
</style>
