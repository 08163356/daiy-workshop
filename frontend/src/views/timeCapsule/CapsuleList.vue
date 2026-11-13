<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { timeCapsuleApi } from '@/api/timeCapsule'
import type { LetterSummary } from '@/api/timeCapsule'
import { Hourglass, PenLine, Lock, Clock, BookOpen, Inbox, CalendarDays, Bot, MessageCircle, Target, Trash2 } from '@lucide/vue'

const router = useRouter()
const loading = ref(true)
const letters = ref<LetterSummary[]>([])
const total = ref(0)
const currentFilter = ref<string>('')

const fetchLetters = async (status?: string) => {
  loading.value = true
  try {
    const data = await timeCapsuleApi.getLetters({ status: status || undefined, limit: 50 })
    letters.value = data.items
    total.value = data.total
  } catch (e) {
    console.error('获取信件列表失败:', e)
  }
  loading.value = false
}

const setFilter = (status: string) => {
  currentFilter.value = status
  fetchLetters(status)
}

const goToWrite = () => router.push('/time-capsule/write')
const goToDetail = (id: number) => router.push(`/time-capsule/${id}`)

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = { sealed: '已封存', pending: '待开封', opened: '已开封' }
  return map[status] || status
}

const getStatusClass = (status: string) => `status--${status}`

const formatDate = (dateStr: string) => {
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

const getDaysText = (days: number) => {
  if (days > 0) return `${days} 天后开封`
  if (days === 0) return '今天开封！'
  return `已过期 ${Math.abs(days)} 天`
}

const deleteLetter = async (id: number, e: Event) => {
  e.stopPropagation()
  if (!confirm('确定删除这封信吗？删除后不可恢复。')) return
  try {
    await timeCapsuleApi.deleteLetter(id)
    fetchLetters(currentFilter.value)
  } catch (err) {
    console.error('删除失败:', err)
  }
}

onMounted(() => fetchLetters())
</script>

<template>
  <div class="capsule-list">
    <header class="capsule-list__header animate-slideUp">
      <div class="capsule-list__title-row">
        <h1 class="capsule-list__title">
          <Hourglass :size="28" :stroke-width="1.75" class="capsule-list__title-icon" />
          时光胶囊
        </h1>
        <button class="btn btn-primary" @click="goToWrite">
          <PenLine :size="14" style="margin-right:6px;" />写一封信
        </button>
      </div>
      <p class="capsule-list__subtitle">写给未来的自己，封存此刻的思绪</p>
    </header>

    <div class="capsule-list__filters animate-slideUp" style="animation-delay: 0.1s">
      <button :class="['filter-btn', { active: currentFilter === '' }]" @click="setFilter('')">全部 ({{ total }})</button>
      <button :class="['filter-btn', { active: currentFilter === 'sealed' }]" @click="setFilter('sealed')">
        <Lock :size="12" style="margin-right:4px;" />已封存
      </button>
      <button :class="['filter-btn', { active: currentFilter === 'pending' }]" @click="setFilter('pending')">
        <Clock :size="12" style="margin-right:4px;" />待开封
      </button>
      <button :class="['filter-btn', { active: currentFilter === 'opened' }]" @click="setFilter('opened')">
        <BookOpen :size="12" style="margin-right:4px;" />已开封
      </button>
    </div>

    <div v-if="loading" class="capsule-list__loading">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
    </div>

    <div v-else-if="letters.length === 0" class="capsule-list__empty animate-slideUp">
      <Inbox :size="48" :stroke-width="1.5" class="empty-icon" />
      <h3>还没有信件</h3>
      <p>写一封给未来自己的信，记录此刻的感悟和期待</p>
      <button class="btn btn-primary" @click="goToWrite">开始写信</button>
    </div>

    <div v-else class="capsule-list__grid">
      <div
        v-for="letter in letters"
        :key="letter.id"
        :class="['letter-card', `letter-card--${letter.status}`, 'animate-slideUp']"
        @click="goToDetail(letter.id)"
      >
        <div class="letter-card__header">
          <span :class="['letter-card__status', getStatusClass(letter.status)]">{{ getStatusLabel(letter.status) }}</span>
          <button class="letter-card__delete" @click="deleteLetter(letter.id, $event)" title="删除">
            <Trash2 :size="13" />
          </button>
        </div>
        <h3 class="letter-card__title">{{ letter.title }}</h3>
        <p class="letter-card__recipient">写给：{{ letter.recipient }}</p>
        <div class="letter-card__dates">
          <span class="letter-card__seal">封存于 {{ formatDate(letter.seal_date) }}</span>
          <span class="letter-card__open">
            <CalendarDays :size="12" style="margin-right:3px;vertical-align:middle;" />{{ formatDate(letter.open_date) }}
          </span>
        </div>
        <div class="letter-card__footer">
          <span v-if="letter.status !== 'opened'" class="letter-card__countdown">{{ getDaysText(letter.days_until_open) }}</span>
          <span v-else class="letter-card__opened-info">
            <span v-if="letter.has_ai_review"><Bot :size="12" style="margin-right:2px;vertical-align:middle;" />已点评</span>
            <span v-if="letter.has_reflection"><MessageCircle :size="12" style="margin-right:2px;vertical-align:middle;" />有感想</span>
          </span>
          <span v-if="letter.goals_count > 0" class="letter-card__goals">
            <Target :size="12" style="margin-right:2px;vertical-align:middle;" />{{ letter.goals_count }} 个目标
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.capsule-list {
  &__header {
    margin-bottom: $spacing-xl;
  }

  &__title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  &__title {
    font-size: $font-size-xxl;
    font-weight: 700;
    color: $text-primary;
    display: flex;
    align-items: center;
    gap: $spacing-sm;

    &-icon { display: flex; align-items: center; color: #8B5CF6; }
  }

  &__subtitle {
    color: $text-secondary;
    margin-top: $spacing-xs;
  }

  &__filters {
    display: flex;
    gap: $spacing-sm;
    margin-bottom: $spacing-lg;
    flex-wrap: wrap;
  }

  &__loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: $spacing-md;
    padding: $spacing-xxl;
    color: $text-secondary;

    .loading-spinner {
      width: 40px;
      height: 40px;
      border: 3px solid rgba($primary-color, 0.2);
      border-top-color: $primary-color;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
  }

  &__empty {
    text-align: center;
    padding: $spacing-xxl * 2;
    color: $text-secondary;

    .empty-icon { display: flex; justify-content: center; margin-bottom: $spacing-md; color: $text-muted; }
    h3 { font-size: $font-size-xl; color: $text-primary; margin-bottom: $spacing-sm; }
    p { margin-bottom: $spacing-lg; }
  }

  &__grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: $spacing-lg;

    @media (max-width: $breakpoint-sm) {
      grid-template-columns: 1fr;
    }
  }
}

.filter-btn {
  padding: $spacing-xs $spacing-md;
  border-radius: 99px;
  border: 1px solid rgba($primary-color, 0.2);
  background: transparent;
  color: $text-secondary;
  cursor: pointer;
  font-size: $font-size-sm;
  transition: all $transition-fast;

  &:hover { border-color: $primary-color; color: $primary-color; }
  &.active {
    background: $primary-color;
    color: white;
    border-color: $primary-color;
  }
}

.letter-card {
  @include glass-card;
  padding: $spacing-lg;
  cursor: pointer;
  @include hover-lift;
  position: relative;

  &--sealed { border-left: 4px solid #8b5cf6; }
  &--pending { border-left: 4px solid #f59e0b; }
  &--opened { border-left: 4px solid #10b981; }

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $spacing-sm;
  }

  &__status {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 99px;
    font-weight: 500;
  }

  &__delete {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: none;
    background: transparent;
    color: $text-muted;
    cursor: pointer;
    font-size: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: all $transition-fast;

    &:hover { background: rgba(#ef4444, 0.1); color: #ef4444; }
  }

  &:hover &__delete { opacity: 1; }

  &__title {
    font-size: $font-size-lg;
    font-weight: 600;
    color: $text-primary;
    margin-bottom: $spacing-xs;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  &__recipient {
    font-size: $font-size-sm;
    color: $text-secondary;
    margin-bottom: $spacing-md;
  }

  &__dates {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: $font-size-xs;
    color: $text-muted;
    margin-bottom: $spacing-md;
  }

  &__footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: $spacing-sm;
    border-top: 1px solid rgba($primary-color, 0.06);
  }

  &__countdown {
    font-size: $font-size-sm;
    font-weight: 600;
    color: #f59e0b;
  }

  &__opened-info {
    display: flex;
    gap: $spacing-sm;
    font-size: $font-size-xs;
    color: $text-secondary;
  }

  &__goals {
    font-size: $font-size-xs;
    color: $text-secondary;
  }
}

.status--sealed { background: rgba(#8b5cf6, 0.1); color: #8b5cf6; }
.status--pending { background: rgba(#f59e0b, 0.1); color: #f59e0b; }
.status--opened { background: rgba(#10b981, 0.1); color: #10b981; }

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
