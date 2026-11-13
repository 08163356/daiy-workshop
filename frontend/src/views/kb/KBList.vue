<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { API_BASE } from '@/config'
import KBCollect from './KBCollect.vue'

const KB_API_BASE = `${API_BASE}/api/kb`
const router = useRouter()
const route = useRoute()

interface ArticleItem {
  id: number
  title: string
  url: string | null
  item_type: string
  content_type: string
  summary: string | null
  read_status: string | null
  tags: string[] | null
  note_id: number | null
  created_at: string
  updated_at: string
}

interface TagInfo {
  name: string
  count: number
}

const articles = ref<ArticleItem[]>([])
const total = ref(0)
const totalPages = ref(0)
const loading = ref(true)
const tags = ref<TagInfo[]>([])
const showCollect = ref(false)

// 筛选
const keyword = ref((route.query.keyword as string) || '')
const itemType = ref((route.query.item_type as string) || '')
const tagFilter = ref((route.query.tag as string) || '')
const readStatus = ref((route.query.read_status as string) || '')
const sortBy = ref('created_at')
const sortOrder = ref('desc')
const page = ref(1)
const pageSize = ref(20)

// 批量选择
const selectedIds = ref<Set<number>>(new Set())
const selectMode = ref(false)

const hasSelected = computed(() => selectedIds.value.size > 0)

const fetchArticles = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (keyword.value) params.set('keyword', keyword.value)
    if (itemType.value) params.set('item_type', itemType.value)
    if (tagFilter.value) params.set('tag', tagFilter.value)
    if (readStatus.value) params.set('read_status', readStatus.value)
    params.set('sort_by', sortBy.value)
    params.set('sort_order', sortOrder.value)
    params.set('page', String(page.value))
    params.set('page_size', String(pageSize.value))

    const res = await fetch(`${KB_API_BASE}?${params}`)
    const data = await res.json()
    articles.value = data.items
    total.value = data.total
    totalPages.value = data.total_pages
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const fetchTags = async () => {
  try {
    const res = await fetch(`${KB_API_BASE}/tags`)
    tags.value = await res.json()
  } catch (e) {
    console.error(e)
  }
}

const search = () => {
  page.value = 1
  fetchArticles()
}

const goToDetail = (id: number) => {
  if (selectMode.value) {
    toggleSelect(id)
    return
  }
  router.push(`/kb/${id}`)
}

const toggleSelect = (id: number) => {
  if (selectedIds.value.has(id)) {
    selectedIds.value.delete(id)
  } else {
    selectedIds.value.add(id)
  }
  selectedIds.value = new Set(selectedIds.value)
}

const clearSelection = () => {
  selectedIds.value = new Set()
  selectMode.value = false
}

const batchMarkRead = async () => {
  try {
    await fetch(`${KB_API_BASE}/batch-read-status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: [...selectedIds.value], read_status: 'read' }),
    })
    clearSelection()
    await fetchArticles()
  } catch (e) {
    console.error(e)
  }
}

const changePage = (p: number) => {
  page.value = p
  fetchArticles()
}

const toggleSort = () => {
  if (sortBy.value === 'created_at' && sortOrder.value === 'desc') {
    sortOrder.value = 'asc'
  } else if (sortBy.value === 'created_at' && sortOrder.value === 'asc') {
    sortBy.value = 'title'
    sortOrder.value = 'asc'
  } else {
    sortBy.value = 'created_at'
    sortOrder.value = 'desc'
  }
  page.value = 1
  fetchArticles()
}

const sortLabel = computed(() => {
  if (sortBy.value === 'title') return '按标题'
  return sortOrder.value === 'desc' ? '最新' : '最旧'
})

const formatDate = (d: string) => {
  const date = new Date(d)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

const statusColor = (article: ArticleItem) => {
  if (article.item_type === 'tool') return '#8B5CF6'
  return article.read_status === 'unread' ? '#6366F1' : '#94A3B8'
}

const onCollectSaved = () => {
  showCollect.value = false
  fetchArticles()
  fetchTags()
}

onMounted(() => {
  fetchArticles()
  fetchTags()
})
</script>

<template>
  <div class="kb-list">
    <!-- Header -->
    <div class="kb-list__header">
      <div>
        <h1>📋 知识库列表</h1>
        <p class="kb-list__count">共 {{ total }} 条记录</p>
      </div>
      <div class="kb-list__actions">
        <button v-if="!selectMode" class="btn btn--ghost btn-sm" @click="selectMode = true">☑️ 批量</button>
        <button v-else class="btn btn--ghost btn-sm" @click="clearSelection">取消</button>
        <button class="kb-btn-primary" @click="showCollect = true">✨ 收集新知识</button>
      </div>
    </div>

    <!-- 筛选工具栏 -->
    <div class="filters-bar">
      <div class="filters-bar__search">
        <span class="filters-bar__search-icon">🔍</span>
        <input
          v-model="keyword"
          placeholder="搜索标题、内容..."
          @keyup.enter="search"
        />
      </div>
      <select v-model="itemType" @change="search" class="filters-bar__select">
        <option value="">全部类型</option>
        <option value="article">📄 文章</option>
        <option value="tool">🔧 工具</option>
      </select>
      <select v-model="tagFilter" @change="search" class="filters-bar__select">
        <option value="">全部标签</option>
        <option v-for="tag in tags" :key="tag.name" :value="tag.name">{{ tag.name }} ({{ tag.count }})</option>
      </select>
      <select v-model="readStatus" @change="search" class="filters-bar__select">
        <option value="">全部状态</option>
        <option value="unread">未读</option>
        <option value="read">已读</option>
      </select>
      <button class="btn btn--ghost btn-sm" @click="toggleSort">{{ sortLabel }} ↕</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
    </div>

    <!-- Empty -->
    <div v-else-if="articles.length === 0" class="empty">
      <span class="empty__icon">📖</span>
      <p>暂无记录</p>
      <button class="kb-btn-primary" @click="showCollect = true">✨ 开始收集</button>
    </div>

    <!-- 列表 -->
    <div v-else class="articles">
      <div
        v-for="article in articles"
        :key="article.id"
        class="article-card"
        :class="{ 'article-card--selected': selectedIds.has(article.id) }"
        @click="goToDetail(article.id)"
      >
        <div class="article-card__status-bar" :style="{ background: statusColor(article) }"></div>
        <div class="article-card__content">
          <div class="article-card__header">
            <span class="article-card__type">{{ article.item_type === 'tool' ? '🔧' : '📄' }}</span>
            <h3 class="article-card__title">{{ article.title }}</h3>
            <span v-if="article.item_type === 'article' && article.read_status === 'unread'" class="article-card__badge">未读</span>
            <input
              v-if="selectMode"
              type="checkbox"
              :checked="selectedIds.has(article.id)"
              class="article-card__checkbox"
              @click.stop="toggleSelect(article.id)"
            />
          </div>
          <p v-if="article.summary" class="article-card__summary">{{ article.summary }}</p>
          <p v-if="article.url" class="article-card__url">🔗 {{ article.url }}</p>
          <div class="article-card__footer">
            <div class="article-card__tags" v-if="article.tags?.length">
              <span v-for="tag in article.tags.slice(0, 3)" :key="tag" class="tag-badge">{{ tag }}</span>
              <span v-if="article.tags.length > 3" class="tag-badge tag-badge--more">+{{ article.tags.length - 3 }}</span>
            </div>
            <span class="article-card__time">{{ formatDate(article.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="totalPages > 1" class="pagination">
      <button class="pagination__btn" :disabled="page <= 1" @click="changePage(page - 1)">← 上一页</button>
      <span class="pagination__info">{{ page }} / {{ totalPages }}</span>
      <button class="pagination__btn" :disabled="page >= totalPages" @click="changePage(page + 1)">下一页 →</button>
    </div>

    <!-- 批量操作浮动栏 -->
    <Transition name="slide-up">
      <div v-if="hasSelected" class="batch-bar">
        <span>已选 {{ selectedIds.size }} 项</span>
        <button class="kb-btn-primary kb-btn--sm" @click="batchMarkRead">✅ 标记已读</button>
        <button class="btn btn--ghost btn-sm" @click="clearSelection">取消选择</button>
      </div>
    </Transition>

    <!-- 收集弹窗 -->
    <KBCollect v-if="showCollect" v-model="showCollect" @saved="onCollectSaved" />
  </div>
</template>

<style lang="scss" scoped>
$kb-primary: #6366F1;
$kb-primary-light: #818CF8;
$kb-primary-bg: rgba(99, 102, 241, 0.1);

.kb-list {
  max-width: 1000px;
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
    margin-bottom: $spacing-lg;

    h1 { font-size: $font-size-xl; font-weight: 700; }

    @media (max-width: $breakpoint-sm) {
      flex-direction: column;
      align-items: flex-start;
      gap: $spacing-sm;
    }
  }

  &__count {
    color: $text-secondary;
    font-size: $font-size-sm;
    margin-top: $spacing-xs;
  }

  &__actions {
    display: flex;
    gap: $spacing-sm;
  }
}

// 筛选
.filters-bar {
  @include glass-card;
  padding: $spacing-md;
  display: flex;
  gap: $spacing-sm;
  margin-bottom: $spacing-lg;
  flex-wrap: wrap;

  &__search {
    display: flex;
    align-items: center;
    flex: 1;
    min-width: 200px;
    background: rgba(0, 0, 0, 0.03);
    border-radius: $border-radius-sm;
    padding: 0 $spacing-sm;

    &-icon { font-size: 14px; margin-right: $spacing-xs; }

    input {
      flex: 1;
      border: none;
      background: transparent;
      padding: $spacing-sm 0;
      font-size: $font-size-sm;

      &:focus { box-shadow: none; }
    }
  }

  &__select {
    padding: $spacing-sm $spacing-md;
    border: 1px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-sm;
    background: white;
    min-width: 100px;

    &:focus {
      border-color: $kb-primary;
    }
  }
}

// 文章卡片
.articles {
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;
}

.article-card {
  @include glass-card;
  display: flex;
  cursor: pointer;
  overflow: hidden;
  transition: all $transition-normal;

  @media (hover: hover) {
    &:hover {
      transform: translateY(-2px);
      box-shadow: $shadow-lg;
    }
  }

  &--selected {
    border-color: $kb-primary;
    background: rgba($kb-primary, 0.05);
  }

  &__status-bar {
    width: 4px;
    flex-shrink: 0;
  }

  &__content {
    flex: 1;
    padding: $spacing-md;
    min-width: 0;
  }

  &__header {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    margin-bottom: $spacing-xs;
  }

  &__type { font-size: 18px; flex-shrink: 0; }

  &__title {
    flex: 1;
    font-size: $font-size-sm;
    font-weight: 600;
    @include text-ellipsis;
  }

  &__badge {
    padding: 2px 8px;
    border-radius: 10px;
    background: $kb-primary-bg;
    color: $kb-primary;
    font-size: 11px;
    font-weight: 600;
    flex-shrink: 0;
  }

  &__checkbox {
    flex-shrink: 0;
    width: 18px;
    height: 18px;
    accent-color: $kb-primary;
  }

  &__summary {
    font-size: $font-size-xs;
    color: $text-secondary;
    @include text-clamp(2);
    margin-bottom: $spacing-xs;
  }

  &__url {
    font-size: $font-size-xs;
    color: $text-muted;
    @include text-ellipsis;
    margin-bottom: $spacing-xs;
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
  padding: 1px 8px;
  border-radius: 10px;
  background: $kb-primary-bg;
  color: $kb-primary;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;

  &--more {
    background: rgba(0, 0, 0, 0.05);
    color: $text-muted;
  }
}

// 分页
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $spacing-md;
  padding: $spacing-lg 0;

  &__btn {
    padding: $spacing-sm $spacing-md;
    border-radius: $border-radius-sm;
    background: white;
    border: 1px solid $border-color;
    color: $text-secondary;
    font-size: $font-size-sm;
    transition: all $transition-fast;

    &:hover:not(:disabled) { border-color: $kb-primary; color: $kb-primary; }
    &:disabled { opacity: 0.4; cursor: not-allowed; }
  }

  &__info {
    font-size: $font-size-sm;
    color: $text-secondary;
  }
}

// 批量操作栏
.batch-bar {
  position: fixed;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  @include glass-card;
  padding: $spacing-sm $spacing-lg;
  display: flex;
  align-items: center;
  gap: $spacing-md;
  z-index: 100;
  box-shadow: $shadow-lg;

  span:first-child { font-size: $font-size-sm; font-weight: 600; color: $kb-primary; }
}

.slide-up-enter-active, .slide-up-leave-active {
  transition: all 0.25s ease;
}
.slide-up-enter-from, .slide-up-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(20px);
}

// 通用
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

  &:hover { transform: translateY(-1px); box-shadow: 0 4px 16px rgba($kb-primary, 0.4); }
  &:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
}

.kb-btn--sm { padding: $spacing-xs $spacing-md; font-size: $font-size-sm; }

.loading {
  @include flex-center;
  padding: $spacing-xxl;

  &__spinner {
    width: 32px; height: 32px;
    border: 3px solid $border-color;
    border-top-color: $kb-primary;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
}

@keyframes spin { to { transform: rotate(360deg); } }

.empty {
  @include glass-card;
  padding: $spacing-xxl;
  text-align: center;

  &__icon { font-size: 48px; display: block; margin-bottom: $spacing-md; }
  p { color: $text-secondary; margin-bottom: $spacing-lg; }
}
</style>
