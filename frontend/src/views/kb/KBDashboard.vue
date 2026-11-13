<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { API_BASE } from '@/config'

const KB_API_BASE = `${API_BASE}/api/kb`
const router = useRouter()

interface ArticleItem {
  id: number
  title: string
  url: string | null
  item_type: string
  content_type: string
  summary: string | null
  read_status: string | null
  tags: string[] | null
  created_at: string
  updated_at: string
}

interface KBOverview {
  total_count: number
  article_count: number
  tool_count: number
  unread_count: number
  read_count: number
  tag_count: number
  recent_articles: ArticleItem[]
  popular_tags: { name: string; count: number }[]
}

const overview = ref<KBOverview | null>(null)
const loading = ref(true)
const error = ref('')
const showCollect = ref(false)
const quickUrl = ref('')
const quickSaving = ref(false)

const fetchOverview = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(`${KB_API_BASE}/overview`)
    if (!res.ok) throw new Error('加载失败')
    overview.value = await res.json()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const quickCollectUrl = async () => {
  if (!quickUrl.value.trim()) return
  quickSaving.value = true
  try {
    const res = await fetch(KB_API_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: quickUrl.value.trim(),
        url: quickUrl.value.trim(),
        item_type: 'article',
        content_type: 'url',
      }),
    })
    if (!res.ok) throw new Error('保存失败')
    quickUrl.value = ''
    await fetchOverview()
  } catch (e: any) {
    alert(e.message)
  } finally {
    quickSaving.value = false
  }
}

const goToDetail = (id: number) => router.push(`/kb/${id}`)
const goToList = () => router.push('/kb/list')
const goToListWithTag = (tag: string) => router.push(`/kb/list?tag=${encodeURIComponent(tag)}`)

const formatDate = (d: string) => {
  const date = new Date(d)
  return `${date.getMonth() + 1}/${date.getDate()}`
}

const tagFontSize = (count: number) => {
  if (!overview.value?.popular_tags.length) return 14
  const max = Math.max(...overview.value.popular_tags.map(t => t.count))
  const min = Math.min(...overview.value.popular_tags.map(t => t.count))
  if (max === min) return 16
  return 12 + ((count - min) / (max - min)) * 14
}

const onCollectSaved = () => {
  showCollect.value = false
  fetchOverview()
}

onMounted(fetchOverview)
</script>

<template>
  <div class="kb-dashboard">
    <!-- Header -->
    <div class="kb-dashboard__header">
      <div>
        <h1>📖 知识库</h1>
        <p class="kb-dashboard__subtitle">收集、整理、检索你的知识</p>
      </div>
      <div class="kb-dashboard__actions">
        <button class="btn btn--ghost" @click="goToList">📋 查看全部</button>
        <button class="kb-btn-primary" @click="showCollect = true">✨ 收集新知识</button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-card">
      <p>{{ error }}</p>
      <button class="btn btn--ghost" @click="fetchOverview">重试</button>
    </div>

    <template v-else-if="overview">
      <!-- 统计卡片 -->
      <div class="stats-grid">
        <div class="stat-card" v-for="stat in [
          { icon: '📄', value: overview.total_count, label: '总条目', color: '#6366F1' },
          { icon: '📰', value: overview.unread_count, label: '未读文章', color: '#818CF8' },
          { icon: '✅', value: overview.read_count, label: '已读文章', color: '#10B981' },
          { icon: '🔧', value: overview.tool_count, label: '工具收藏', color: '#8B5CF6' },
          { icon: '🏷️', value: overview.tag_count, label: '标签数', color: '#F59E0B' },
        ]" :key="stat.label">
          <span class="stat-card__icon" :style="{ background: `${stat.color}20`, color: stat.color }">{{ stat.icon }}</span>
          <span class="stat-card__value">{{ stat.value }}</span>
          <span class="stat-card__label">{{ stat.label }}</span>
        </div>
      </div>

      <!-- 快速收集 -->
      <div class="quick-collect">
        <div class="quick-collect__title">⚡ 快速收集</div>
        <div class="quick-collect__row">
          <input
            v-model="quickUrl"
            class="quick-collect__input"
            placeholder="粘贴 URL 链接，快速收集文章..."
            @keyup.enter="quickCollectUrl"
          />
          <button class="kb-btn-primary kb-btn--sm" :disabled="quickSaving || !quickUrl.trim()" @click="quickCollectUrl">
            {{ quickSaving ? '保存中...' : '📥 收集' }}
          </button>
        </div>
        <div class="quick-collect__btns">
          <button class="btn btn--ghost btn-sm" @click="showCollect = true">✏️ 手动输入</button>
          <button class="btn btn--ghost btn-sm" @click="showCollect = true">🔧 收藏工具</button>
        </div>
      </div>

      <!-- 最近收集 -->
      <div class="section" v-if="overview.recent_articles.length">
        <div class="section__header">
          <h2>🕐 最近收集</h2>
          <button class="btn btn--ghost btn-sm" @click="goToList">查看全部 →</button>
        </div>
        <div class="recent-grid">
          <div
            v-for="article in overview.recent_articles"
            :key="article.id"
            class="recent-card"
            @click="goToDetail(article.id)"
          >
            <div class="recent-card__top">
              <span class="recent-card__type">{{ article.item_type === 'tool' ? '🔧' : '📄' }}</span>
              <span v-if="article.item_type === 'article' && article.read_status === 'unread'" class="recent-card__unread"></span>
            </div>
            <h3 class="recent-card__title">{{ article.title }}</h3>
            <p v-if="article.summary" class="recent-card__summary">{{ article.summary }}</p>
            <div class="recent-card__footer">
              <div class="recent-card__tags" v-if="article.tags?.length">
                <span v-for="tag in article.tags.slice(0, 2)" :key="tag" class="tag-badge">{{ tag }}</span>
              </div>
              <span class="recent-card__time">{{ formatDate(article.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 热门标签云 -->
      <div class="section" v-if="overview.popular_tags.length">
        <div class="section__header">
          <h2>🏷️ 热门标签</h2>
        </div>
        <div class="tag-cloud">
          <span
            v-for="tag in overview.popular_tags"
            :key="tag.name"
            class="tag-cloud__item"
            :style="{ fontSize: tagFontSize(tag.count) + 'px' }"
            @click="goToListWithTag(tag.name)"
          >
            {{ tag.name }}
            <sup class="tag-cloud__count">{{ tag.count }}</sup>
          </span>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="overview.total_count === 0" class="empty-state">
        <span class="empty-state__icon">📖</span>
        <h3>知识库还是空的</h3>
        <p>开始收集你遇到的好文章、工具和知识吧！</p>
        <button class="kb-btn-primary" @click="showCollect = true">✨ 开始收集</button>
      </div>
    </template>

    <!-- 收集弹窗 -->
    <KBCollect v-if="showCollect" v-model="showCollect" @saved="onCollectSaved" />
  </div>
</template>

<script lang="ts">
import KBCollect from './KBCollect.vue'
export default { components: { KBCollect } }
</script>

<style lang="scss" scoped>
$kb-primary: #6366F1;
$kb-primary-light: #818CF8;
$kb-primary-bg: rgba(99, 102, 241, 0.1);

.kb-dashboard {
  max-width: 1200px;
  margin: 0 auto;
  padding: $spacing-lg;
  animation: slideUp 0.4s ease;

  @media (max-width: $breakpoint-md) {
    padding: $spacing-md;
    padding-bottom: calc(#{$spacing-lg} + 70px);
  }

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: $spacing-xl;

    h1 {
      font-size: $font-size-xl;
      font-weight: 700;
    }

    @media (max-width: $breakpoint-md) {
      flex-direction: column;
      align-items: flex-start;
      gap: $spacing-md;
    }
  }

  &__subtitle {
    color: $text-secondary;
    font-size: $font-size-sm;
    margin-top: $spacing-xs;
  }

  &__actions {
    display: flex;
    gap: $spacing-sm;
  }
}

.kb-btn-primary {
  display: inline-flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-lg;
  border-radius: $border-radius-md;
  background: linear-gradient(135deg, $kb-primary, $kb-primary-light);
  color: white;
  font-weight: 600;
  font-size: $font-size-sm;
  border: none;
  cursor: pointer;
  transition: all $transition-fast;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(99, 102, 241, 0.4);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
  }
}

.kb-btn--sm {
  padding: $spacing-xs $spacing-md;
  font-size: $font-size-sm;
}

// 统计卡片
.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: $spacing-md;
  margin-bottom: $spacing-xl;

  @media (max-width: $breakpoint-lg) {
    grid-template-columns: repeat(3, 1fr);
  }
  @media (max-width: $breakpoint-sm) {
    grid-template-columns: repeat(2, 1fr);
  }
}

.stat-card {
  @include glass-card;
  padding: $spacing-lg;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $spacing-sm;
  @include hover-lift;
  cursor: default;

  &__icon {
    width: 48px;
    height: 48px;
    border-radius: $border-radius-md;
    @include flex-center;
    font-size: 22px;
  }

  &__value {
    font-size: 28px;
    font-weight: 700;
    color: $text-primary;
  }

  &__label {
    font-size: $font-size-xs;
    color: $text-secondary;
  }
}

// 快速收集
.quick-collect {
  @include glass-card;
  padding: $spacing-lg;
  margin-bottom: $spacing-xl;

  &__title {
    font-size: $font-size-md;
    font-weight: 600;
    margin-bottom: $spacing-md;
  }

  &__row {
    display: flex;
    gap: $spacing-sm;
    margin-bottom: $spacing-sm;
  }

  &__input {
    flex: 1;
    padding: $spacing-sm $spacing-md;
    border: 1px solid $border-color;
    border-radius: $border-radius-md;
    font-size: $font-size-sm;
    transition: border-color $transition-fast;

    &:focus {
      border-color: $kb-primary;
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
    }
  }

  &__btns {
    display: flex;
    gap: $spacing-sm;
  }
}

// 区块
.section {
  margin-bottom: $spacing-xl;

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: $spacing-md;

    h2 {
      font-size: $font-size-lg;
      font-weight: 600;
    }
  }
}

// 最近收集卡片
.recent-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: $spacing-md;

  @media (max-width: $breakpoint-lg) {
    grid-template-columns: repeat(2, 1fr);
  }
  @media (max-width: $breakpoint-sm) {
    grid-template-columns: 1fr;
  }
}

.recent-card {
  @include glass-card;
  padding: $spacing-md;
  cursor: pointer;
  @include hover-lift;

  &__top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: $spacing-sm;
  }

  &__type {
    font-size: 20px;
  }

  &__unread {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: $kb-primary;
    animation: pulse 2s infinite;
  }

  &__title {
    font-size: $font-size-sm;
    font-weight: 600;
    color: $text-primary;
    @include text-clamp(2);
    margin-bottom: $spacing-sm;
  }

  &__summary {
    font-size: $font-size-xs;
    color: $text-secondary;
    @include text-clamp(2);
    margin-bottom: $spacing-sm;
  }

  &__footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: $spacing-sm;
  }

  &__tags {
    display: flex;
    gap: 4px;
    flex: 1;
    overflow: hidden;
  }

  &__time {
    font-size: $font-size-xs;
    color: $text-muted;
    flex-shrink: 0;
  }
}

.tag-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  background: $kb-primary-bg;
  color: $kb-primary;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

// 标签云
.tag-cloud {
  @include glass-card;
  padding: $spacing-lg;
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-md;
  align-items: center;

  &__item {
    color: $kb-primary;
    cursor: pointer;
    transition: all $transition-fast;
    font-weight: 500;

    &:hover {
      color: darken(#6366F1, 10%);
      transform: scale(1.1);
    }
  }

  &__count {
    font-size: 10px;
    color: $text-muted;
    margin-left: 2px;
  }
}

// 空状态
.empty-state {
  @include glass-card;
  padding: $spacing-xxl;
  text-align: center;

  &__icon {
    font-size: 64px;
    display: block;
    margin-bottom: $spacing-md;
  }

  h3 {
    font-size: $font-size-lg;
    margin-bottom: $spacing-sm;
  }

  p {
    color: $text-secondary;
    margin-bottom: $spacing-lg;
  }
}

// Loading & Error
.loading {
  @include flex-center;
  flex-direction: column;
  gap: $spacing-md;
  padding: $spacing-xxl;
  color: $text-secondary;

  &__spinner {
    width: 32px;
    height: 32px;
    border: 3px solid $border-color;
    border-top-color: $kb-primary;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-card {
  @include glass-card;
  padding: $spacing-xl;
  text-align: center;
  color: $danger-color;
}
</style>
