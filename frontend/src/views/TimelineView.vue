<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import { api } from '@/api'
import { API_BASE } from '@/config'
import type { TimelineItem } from '@/types/graph'
import ContentActions from '@/components/ContentActions.vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { CalendarDays, Trash2, Bot, RefreshCcw, MessageSquareText } from '@lucide/vue'

marked.setOptions({ breaks: true, gfm: true })

const loading = ref(true)
const timelineData = ref<TimelineItem[]>([])
const expandedItems = ref<Set<number>>(new Set())
const activeTab = ref<Map<number, string>>(new Map()) // 每个 item 的当前 tab
const dateFrom = ref('')
const dateTo = ref('')

// 来源类型筛选（book=读书 course=课程 self=随笔）
const sourceType = ref('')
const SOURCE_TABS = [
  { key: '', label: '全部' },
  { key: 'book', label: '📚 读书' },
  { key: 'course', label: '🎓 课程' },
  { key: 'self', label: '✏️ 随笔' },
]
const SOURCE_BADGES: Record<string, { label: string; cls: string }> = {
  book: { label: '读书', cls: 'badge--book' },
  course: { label: '课程', cls: 'badge--course' },
  self: { label: '随笔', cls: 'badge--self' },
}
const switchSourceType = (key: string) => {
  sourceType.value = key
  loadData(1)
}

// 分页
const PAGE_SIZE = 10
const currentPage = ref(1)
const totalItems = ref(0)
const totalPages = computed(() => Math.ceil(totalItems.value / PAGE_SIZE))
const loadingMore = ref(false)

// 删除和分析状态
const deletingId = ref<number | null>(null)
const analyzingId = ref<number | null>(null)
const router = useRouter()

// 教练深挖：带来源 id 进教练对话（正文由服务端注入）
const deepDive = (id: number) => {
  router.push({ path: '/assistant', query: { origin: `note:${id}` } })
}

// 结构化数据折叠状态（每个 item 独立）
const sectionCollapsed = ref<Map<string, boolean>>(new Map())

const getSectionKey = (index: number, section: string) => `${index}-${section}`
const isSectionOpen = (index: number, section: string) => sectionCollapsed.value.get(getSectionKey(index, section)) || false
const toggleSectionCollapse = (index: number, section: string) => {
  const key = getSectionKey(index, section)
  sectionCollapsed.value.set(key, !sectionCollapsed.value.get(key))
  sectionCollapsed.value = new Map(sectionCollapsed.value)
}

// 筛选后的数据
const filteredData = computed(() => {
  if (!dateFrom.value && !dateTo.value) return timelineData.value
  
  return timelineData.value.filter(item => {
    const itemDate = item.date.replace(/\./g, '-')
    if (dateFrom.value && itemDate < dateFrom.value) return false
    if (dateTo.value && itemDate > dateTo.value) return false
    return true
  })
})

const clearFilter = () => {
  dateFrom.value = ''
  dateTo.value = ''
}

// 加载数据
const loadData = async (page: number) => {
  const skip = (page - 1) * PAGE_SIZE
  try {
    const result = await api.getTimeline(skip, PAGE_SIZE, sourceType.value || undefined)
    totalItems.value = result.total
    timelineData.value = result.items || []
    currentPage.value = page
  } catch (e) {
    console.error('加载时间线失败:', e)
  }
}

// 翻页
const goToPage = async (page: number) => {
  if (page < 1 || page > totalPages.value || loadingMore.value) return
  loadingMore.value = true
  await loadData(page)
  loadingMore.value = false
  // 滚动到顶部
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// 删除笔记
const deleteNote = async (noteId: number, index: number) => {
  if (!confirm('确定要删除这篇笔记吗？此操作不可撤销。')) return
  deletingId.value = noteId
  try {
    const result = await api.deleteNote(noteId)
    if (result.message === '删除成功') {
      // 从列表中移除
      timelineData.value.splice(index, 1)
      totalItems.value -= 1
      // 如果当前页没有数据了且不是第一页，回到上一页
      if (timelineData.value.length === 0 && currentPage.value > 1) {
        await goToPage(currentPage.value - 1)
      }
    } else {
      alert(result.message || '删除失败')
    }
  } catch (e) {
    alert('删除失败，请重试')
  }
  deletingId.value = null
}

// AI 分析
const analyzeNote = async (noteId: number, index: number) => {
  analyzingId.value = noteId
  try {
    const result = await api.analyzeNote(noteId)
    if (result.status === 'success') {
      // 更新本条数据的 AI 分析
      if (timelineData.value[index]) {
        timelineData.value[index] = {
          ...timelineData.value[index],
          ai_analysis: result.ai_analysis,
        }
      }
      alert('AI 分析完成！')
    } else {
      alert(result.message || '分析失败')
    }
  } catch (e) {
    alert('AI 分析失败，请重试')
  }
  analyzingId.value = null
}

// 切换展开状态
const toggleExpand = (index: number) => {
  if (expandedItems.value.has(index)) {
    expandedItems.value.delete(index)
  } else {
    expandedItems.value.add(index)
    // 默认选中"摘要" tab
    if (!activeTab.value.has(index)) {
      activeTab.value.set(index, 'summary')
    }
  }
}

// 获取某个 item 的当前 tab
const getTab = (index: number): string => {
  return activeTab.value.get(index) || 'summary'
}

// 设置某个 item 的 tab
const setTab = (index: number, tab: string) => {
  activeTab.value.set(index, tab)
  // 触发响应式更新
  activeTab.value = new Map(activeTab.value)
}

// 提取关键收获
const getKeyPoints = (item: TimelineItem): string[] => {
  if (item.key_points && item.key_points.length > 0) {
    return item.key_points.slice(0, 5)
  }
  return []
}

// 获取结构化数据统计
const getStructuredStats = (item: TimelineItem) => {
  const sd = item.structured_data
  if (!sd) return []
  const stats: { label: string; count: number; icon: string }[] = []
  if (sd.tags?.length)           stats.push({ label: '标签',     count: sd.tags.length,           icon: 'tag' })
  if (sd.key_issues?.length)     stats.push({ label: '关键问题',  count: sd.key_issues.length,     icon: 'search' })
  if (sd.action_items?.length)   stats.push({ label: '行动建议',  count: sd.action_items.length,   icon: 'target' })
  if (sd.concepts?.length)       stats.push({ label: '概念',      count: sd.concepts.length,       icon: 'lightbulb' })
  if (sd.models?.length)         stats.push({ label: '思维模型',  count: sd.models.length,         icon: 'brain' })
  if (sd.relations?.length)      stats.push({ label: '关系',      count: sd.relations.length,      icon: 'link-2' })
  if (sd.books_mentioned?.length) stats.push({ label: '提到的书', count: sd.books_mentioned.length, icon: 'book-open' })
  if (item.key_points?.length)   stats.push({ label: '知识点',    count: item.key_points.length,   icon: 'star' })
  return stats
}

// 渲染 markdown
const renderMarkdown = (md: string): string => {
  if (!md) return ''
  try {
    return marked.parse(md) as string
  } catch {
    return md.replace(/\n/g, '<br>')
  }
}

// 判断 item 是否有原文
const hasOriginal = (item: TimelineItem) => !!item.original_content
const hasTable = (text?: string) => !!text && (/<table[\s>]/i.test(text) || /^\s*\|.+\|\s*$/m.test(text))
const imageSrc = (url: string) => url.startsWith('http') ? url : `${API_BASE}${url}`
// 判断 item 是否有 AI 分析
const hasAnalysis = (item: TimelineItem) => !!item.ai_analysis

onMounted(async () => {
  loading.value = true
  await loadData(1)
  loading.value = false
})
</script>

<template>
  <div class="timeline-view">
    <!-- 页面标题 -->
    <header class="timeline-view__header animate-slideUp">
      <h1 class="timeline-view__title">
        <CalendarDays :size="28" :stroke-width="1.75" class="timeline-view__title-icon" />
        阅读时间线
      </h1>
      <p class="timeline-view__subtitle">回顾你的阅读历程，记录每一次知识的收获</p>
    </header>
    
    <!-- 加载状态 -->
    <div v-if="loading" class="timeline-view__loading">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
    </div>
    
    <!-- 空状态 -->
    <div v-else-if="timelineData.length === 0" class="timeline-view__empty card">
      <div class="empty-state">
        <BookOpen :size="40" :stroke-width="1.5" class="empty-state__icon" />
        <h3>还没有阅读记录</h3>
        <p>开始阅读并记录你的第一本书吧！</p>
      </div>
    </div>
    
    <!-- 时间线内容 -->
    <div v-else class="timeline-view__content">
      <!-- 筛选栏 -->
      <div class="timeline-view__filter card animate-slideUp" style="animation-delay: 0.05s">
        <!-- 来源类型 tab -->
        <div class="source-tabs">
          <button
            v-for="t in SOURCE_TABS" :key="t.key"
            class="source-tabs__btn"
            :class="{ 'source-tabs__btn--active': sourceType === t.key }"
            @click="switchSourceType(t.key)"
          >{{ t.label }}</button>
        </div>
        <div class="filter-row">
          <div class="filter-group">
            <label>从</label>
            <input type="date" v-model="dateFrom" class="filter-input" />
          </div>
          <div class="filter-group">
            <label>到</label>
            <input type="date" v-model="dateTo" class="filter-input" />
          </div>
          <button v-if="dateFrom || dateTo" class="filter-clear" @click="clearFilter">清除筛选</button>
        </div>
        <div v-if="dateFrom || dateTo" class="filter-result">
          共 {{ filteredData.length }} / {{ timelineData.length }} 条记录
        </div>
      </div>

      <!-- 统计摘要 -->
      <div class="timeline-view__summary card animate-slideUp" style="animation-delay: 0.1s">
        <div class="summary-item">
          <span class="summary-item__value">{{ filteredData.length }}</span>
          <span class="summary-item__label">篇笔记</span>
        </div>
        <div class="summary-item">
          <span class="summary-item__value">{{ filteredData.reduce((sum, item) => sum + (item.key_points?.length || 0), 0) }}</span>
          <span class="summary-item__label">个知识点</span>
        </div>
      </div>
      
      <!-- 空筛选结果 -->
      <div v-if="filteredData.length === 0" class="timeline-view__empty card">
        <div class="empty-state">
          <AppIcon name="search" :size="40" :stroke-width="1.5" class="empty-state__icon" />
          <h3>没有找到匹配的记录</h3>
          <p>试试调整日期范围</p>
        </div>
      </div>

      <!-- 时间线 -->
      <div v-else class="timeline">
        <div
          v-for="(item, index) in filteredData"
          :key="index"
          class="timeline__item card animate-slideUp"
          :class="{ 'timeline__item--expanded': expandedItems.has(index) }"
          :style="{ animationDelay: `${0.1 + index * 0.03}s` }"
        >
          <!-- 时间点 -->
          <div class="timeline__dot"></div>
          
          <!-- 日期 -->
          <div class="timeline__date">{{ item.date }}</div>
          
          <!-- 内容 -->
          <div class="timeline__content">
            <div class="timeline__title-row">
              <h3 class="timeline__title" @click="toggleExpand(index)">
                <span
                  v-if="(item as any).source_type && (item as any).source_type !== 'book'"
                  class="source-badge"
                  :class="SOURCE_BADGES[(item as any).source_type]?.cls"
                >{{ SOURCE_BADGES[(item as any).source_type]?.label }}</span>
                {{ item.title }}
                <span v-if="(item as any).course_meta?.instructor" class="timeline__instructor">👤 {{ (item as any).course_meta.instructor }}</span>
                <span class="timeline__expand-icon">{{ expandedItems.has(index) ? '▼' : '▶' }}</span>
              </h3>
              <!-- 操作按钮 -->
              <div class="timeline__actions">
                <button
                  v-if="(item as any).id"
                  class="timeline__action-btn"
                  @click.stop="deepDive((item as any).id)"
                  title="和 AI 教练深挖这条"
                >
                  <MessageSquareText :size="13" />
                </button>
                <button
                  v-if="!hasAnalysis(item) && (item as any).id"
                  class="timeline__action-btn timeline__action-btn--analyze"
                  :disabled="analyzingId === (item as any).id"
                  @click.stop="analyzeNote((item as any).id, index)"
                  :title="analyzingId === (item as any).id ? '分析中...' : 'AI 分析'"
                >
                  <RefreshCcw v-if="analyzingId === (item as any).id" :size="13" class="spinning" />
                  <Bot v-else :size="13" />
                </button>
                <button
                  v-if="(item as any).id"
                  class="timeline__action-btn timeline__action-btn--delete"
                  :disabled="deletingId === (item as any).id"
                  @click.stop="deleteNote((item as any).id, index)"
                  title="删除"
                >
                  <Trash2 :size="13" />
                </button>
              </div>
            </div>
            
            <!-- 折叠状态：关键点预览 + 结构化数据统计 -->
            <div v-if="!expandedItems.has(index)">
              <div class="timeline__keypoints">
                <span 
                  v-for="(point, i) in getKeyPoints(item)" 
                  :key="i" 
                  class="timeline__keypoint-tag"
                >
                  {{ point.replace('：', '') }}
                </span>
              </div>
              <div v-if="getStructuredStats(item).length > 0" class="timeline__stats-preview">
                <span
                  v-for="stat in getStructuredStats(item)"
                  :key="stat.label"
                  class="timeline__stat-badge"
                  :title="stat.label"
                >
                  <AppIcon :name="stat.icon" :size="10" style="margin-right:2px;" />{{ stat.label }} {{ stat.count }}项
                </span>
              </div>
            </div>
            
            <!-- 展开详情：Tab 切换 -->
            <div v-if="expandedItems.has(index)" class="timeline__detail">
              <!-- Tab 栏 -->
              <div class="timeline__tabs">
                <button class="timeline__tab" :class="{ 'timeline__tab--active': getTab(index) === 'summary' }" @click="setTab(index, 'summary')">
                  <AppIcon name="clipboard-list" :size="13" style="margin-right:4px;" />知识提炼
                </button>
                <button v-if="hasOriginal(item)" class="timeline__tab" :class="{ 'timeline__tab--active': getTab(index) === 'original' }" @click="setTab(index, 'original')">
                  <AppIcon name="file-text" :size="13" style="margin-right:4px;" />原文
                </button>
                <button v-if="hasAnalysis(item)" class="timeline__tab" :class="{ 'timeline__tab--active': getTab(index) === 'analysis' }" @click="setTab(index, 'analysis')">
                  <AppIcon name="bot" :size="13" style="margin-right:4px;" />AI 分析
                </button>
                <span style="flex:1"></span>
                <ContentActions :text="item.ai_analysis || item.content || ''" />
              </div>
              
              <!-- Tab 内容 -->
              <div class="timeline__tab-content">
                <!-- 摘要 Tab -->
                <div v-if="getTab(index) === 'summary'" class="timeline__tab-panel">
                  <div class="timeline__detail-content" v-html="item.content"></div>
                  
                  <!-- 结构化数据详情 -->
                  <div v-if="item.structured_data" class="timeline__structured">
                    <div v-if="item.structured_data.tags?.length" class="structured-section">
                      <h4 class="structured-section__title"><AppIcon name="tag" :size="12" style="margin-right:4px;" />标签</h4>
                      <div class="structured-section__tags">
                        <span v-for="tag in item.structured_data.tags" :key="tag" class="structured-tag">{{ tag }}</span>
                      </div>
                    </div>
                    <div v-if="item.structured_data.mood" class="structured-section">
                      <h4 class="structured-section__title">😊 情绪</h4>
                      <span class="structured-tag structured-tag--mood">{{ item.structured_data.mood }}</span>
                    </div>
                    
                    <div v-if="item.structured_data.key_issues?.length" class="structured-section structured-section--collapsible" :class="{ 'structured-section--open': isSectionOpen(index, 'key_issues') }">
                      <h4 class="structured-section__title structured-section__title--clickable" @click="toggleSectionCollapse(index, 'key_issues')">
                        <AppIcon name="search" :size="12" style="margin-right:4px;" />关键问题 ({{ item.structured_data.key_issues.length }}项)
                        <span class="structured-section__arrow">{{ isSectionOpen(index, 'key_issues') ? '▼' : '▶' }}</span>
                      </h4>
                      <ul v-if="isSectionOpen(index, 'key_issues')" class="structured-section__list">
                        <li v-for="issue in item.structured_data.key_issues" :key="issue">{{ issue }}</li>
                      </ul>
                    </div>
                    <div v-if="item.structured_data.action_items?.length" class="structured-section structured-section--collapsible" :class="{ 'structured-section--open': isSectionOpen(index, 'action_items') }">
                      <h4 class="structured-section__title structured-section__title--clickable" @click="toggleSectionCollapse(index, 'action_items')">
                        <AppIcon name="target" :size="12" style="margin-right:4px;" />行动建议 ({{ item.structured_data.action_items.length }}项)
                        <span class="structured-section__arrow">{{ isSectionOpen(index, 'action_items') ? '▼' : '▶' }}</span>
                      </h4>
                      <ul v-if="isSectionOpen(index, 'action_items')" class="structured-section__list structured-section__list--action">
                        <li v-for="action in item.structured_data.action_items" :key="action">{{ action }}</li>
                      </ul>
                    </div>
                    <div v-if="item.structured_data.concepts?.length" class="structured-section structured-section--collapsible" :class="{ 'structured-section--open': isSectionOpen(index, 'concepts') }">
                      <h4 class="structured-section__title structured-section__title--clickable" @click="toggleSectionCollapse(index, 'concepts')">
                        <AppIcon name="lightbulb" :size="12" style="margin-right:4px;" />概念 ({{ item.structured_data.concepts.length }}项)
                        <span class="structured-section__arrow">{{ isSectionOpen(index, 'concepts') ? '▼' : '▶' }}</span>
                      </h4>
                      <div v-if="isSectionOpen(index, 'concepts')" class="structured-section__concepts">
                        <div v-for="c in item.structured_data.concepts" :key="c.name" class="concept-chip">
                          <span class="concept-chip__name">{{ c.name }}</span>
                          <span v-if="c.category" class="concept-chip__cat">{{ c.category }}</span>
                          <span v-if="c.action === 'merge'" class="concept-chip__badge concept-chip__badge--merge">合并</span>
                          <span v-else-if="c.action === 'new'" class="concept-chip__badge concept-chip__badge--new">新增</span>
                        </div>
                      </div>
                    </div>
                    <div v-if="item.structured_data.models?.length" class="structured-section structured-section--collapsible" :class="{ 'structured-section--open': isSectionOpen(index, 'models') }">
                      <h4 class="structured-section__title structured-section__title--clickable" @click="toggleSectionCollapse(index, 'models')">
                        <AppIcon name="brain" :size="12" style="margin-right:4px;" />思维模型 ({{ item.structured_data.models.length }}项)
                        <span class="structured-section__arrow">{{ isSectionOpen(index, 'models') ? '▼' : '▶' }}</span>
                      </h4>
                      <div v-if="isSectionOpen(index, 'models')" class="structured-section__models">
                        <div v-for="m in item.structured_data.models" :key="m.title" class="model-card-mini">
                          <span class="model-card-mini__title">{{ m.title }}</span>
                          <span v-if="m.action === 'merge'" class="concept-chip__badge concept-chip__badge--merge">合并</span>
                          <span v-else-if="m.action === 'new'" class="concept-chip__badge concept-chip__badge--new">新增</span>
                        </div>
                      </div>
                    </div>
                    <div v-if="item.structured_data.books_mentioned?.length" class="structured-section structured-section--collapsible" :class="{ 'structured-section--open': isSectionOpen(index, 'books') }">
                      <h4 class="structured-section__title structured-section__title--clickable" @click="toggleSectionCollapse(index, 'books')">
                        <AppIcon name="book-open" :size="12" style="margin-right:4px;" />提到的书 ({{ item.structured_data.books_mentioned.length }}项)
                        <span class="structured-section__arrow">{{ isSectionOpen(index, 'books') ? '▼' : '▶' }}</span>
                      </h4>
                      <div v-if="isSectionOpen(index, 'books')" class="structured-section__tags">
                        <span v-for="book in item.structured_data.books_mentioned" :key="book" class="structured-tag structured-tag--book">{{ book }}</span>
                      </div>
                    </div>
                  </div>
                </div>
                
                <!-- 原文 Tab -->
                <div v-if="getTab(index) === 'original'" class="timeline__tab-panel">
                  <div class="timeline__original-content">
                    <div v-if="hasTable(item.original_content)" class="timeline__detail-content markdown-body" v-html="renderMarkdown(item.original_content || '')"></div>
                    <pre v-else>{{ item.original_content }}</pre>
                    <div v-if="item.images?.length" class="note-images">
                      <img v-for="(url, i) in item.images" :key="i" :src="imageSrc(url)" alt="" loading="lazy" />
                    </div>
                  </div>
                </div>
                
                <!-- AI 分析 Tab -->
                <div v-if="getTab(index) === 'analysis'" class="timeline__tab-panel">
                  <div class="timeline__analysis-content" v-html="renderMarkdown(item.ai_analysis || '')"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页控件 -->
      <div v-if="totalPages > 1" class="timeline-view__pagination card animate-slideUp">
        <button 
          class="pagination__btn" 
          :disabled="currentPage <= 1 || loadingMore"
          @click="goToPage(currentPage - 1)"
        >
          ← 上一页
        </button>
        <div class="pagination__pages">
          <template v-for="p in totalPages" :key="p">
            <button
              v-if="p === 1 || p === totalPages || (p >= currentPage - 2 && p <= currentPage + 2)"
              class="pagination__page"
              :class="{ 'pagination__page--active': p === currentPage }"
              :disabled="loadingMore"
              @click="goToPage(p)"
            >
              {{ p }}
            </button>
            <span
              v-else-if="p === currentPage - 3 || p === currentPage + 3"
              class="pagination__ellipsis"
            >...</span>
          </template>
        </div>
        <button 
          class="pagination__btn" 
          :disabled="currentPage >= totalPages || loadingMore"
          @click="goToPage(currentPage + 1)"
        >
          下一页 →
        </button>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.timeline-view {
  &__header {
    margin-bottom: $spacing-xl;
  }
  
  &__title {
    font-size: $font-size-xxl;
    font-weight: 700;
    color: $text-primary;
    display: flex;
    align-items: center;
    gap: $spacing-sm;

    @media (max-width: $breakpoint-sm) {
      font-size: $font-size-xl;
    }
    
    &-icon {
      font-size: 36px;

      @media (max-width: $breakpoint-sm) {
        font-size: 28px;
      }
    }
  }
  
  &__subtitle {
    color: $text-secondary;
    margin-top: $spacing-xs;
  }
  
  &__loading {
    @include glass-card;
    @include flex-center;
    flex-direction: column;
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
    padding: $spacing-xxl;
    
    .empty-state {
      text-align: center;
      color: $text-secondary;
      
      &__icon {
        display: flex;
        justify-content: center;
        align-items: center;
        margin-bottom: $spacing-lg;
        color: $text-muted;
        opacity: 0.6;
      }
      
      h3 {
        font-size: $font-size-lg;
        color: $text-primary;
        margin-bottom: $spacing-sm;
      }
    }
  }
  
  &__summary {
    display: flex;
    justify-content: center;
    gap: $spacing-xxl;
    padding: $spacing-lg $spacing-xl;
    margin-bottom: $spacing-xl;
    
    @media (max-width: $breakpoint-sm) {
      gap: $spacing-lg;
    }
  }

  &__filter {
    padding: $spacing-md $spacing-lg;
    margin-bottom: $spacing-lg;
  }
}

// 摘要项
.summary-item {
  text-align: center;
  
  &__value {
    display: block;
    font-size: $font-size-xxl;
    font-weight: 700;
    background: linear-gradient(135deg, $primary-color, $accent-color);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  
  &__label {
    font-size: $font-size-sm;
    color: $text-muted;
  }
}

// 时间线
.timeline {
  position: relative;
  padding-left: 40px;
  
  @media (max-width: $breakpoint-sm) {
    padding-left: 28px;
  }
  
  // 垂直线
  &::before {
    content: '';
    position: absolute;
    left: 12px;
    top: 20px;
    bottom: 20px;
    width: 3px;
    background: linear-gradient(to bottom, $primary-color, $accent-color);
    border-radius: 2px;

    @media (max-width: $breakpoint-sm) {
      left: 6px;
      width: 2px;
    }
  }
  
  &__item {
    position: relative;
    padding: $spacing-lg;
    margin-bottom: $spacing-lg;
    transition: all 0.3s ease;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-md;
      margin-bottom: $spacing-md;
    }
    
    &:last-child {
      margin-bottom: 0;
    }
    
    &--expanded {
      box-shadow: 0 8px 32px rgba($primary-color, 0.15);
    }
  }
  
  &__dot {
    position: absolute;
    left: -34px;
    top: 24px;
    width: 16px;
    height: 16px;
    background: linear-gradient(135deg, $primary-color, $accent-color);
    border-radius: 50%;
    border: 3px solid $bg-base;
    box-shadow: 0 0 0 3px rgba($primary-color, 0.2);

    @media (max-width: $breakpoint-sm) {
      left: -25px;
      top: 18px;
      width: 12px;
      height: 12px;
      border-width: 2px;
    }
  }
  
  &__date {
    font-size: $font-size-sm;
    font-weight: 600;
    color: $primary-color;
    margin-bottom: $spacing-sm;
    padding: 4px 12px;
    background: rgba($primary-color, 0.1);
    border-radius: $border-radius-sm;
    display: inline-block;
  }
  
  &__title {
    font-size: $font-size-lg;
    font-weight: 600;
    color: $text-primary;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    margin-bottom: $spacing-md;

    @media (max-width: $breakpoint-sm) {
      font-size: $font-size-md;
    }
    
    &:hover {
      color: $primary-color;
    }
  }
  
  &__expand-icon {
    font-size: $font-size-xs;
    color: $text-muted;
    transition: transform 0.3s;
  }
  
  &__keypoints {
    display: flex;
    flex-wrap: wrap;
    gap: $spacing-xs;
  }
  
  &__keypoint-tag {
    font-size: $font-size-xs;
    color: $text-secondary;
    background: rgba($primary-color, 0.08);
    padding: 4px 10px;
    border-radius: $border-radius-sm;
    border: 1px solid rgba($primary-color, 0.15);
  }
  
  &__detail {
    margin-top: $spacing-md;
    padding-top: $spacing-md;
    border-top: 1px solid rgba($primary-color, 0.1);
    
    &-content {
      font-size: $font-size-sm;
      color: $text-secondary;
      line-height: 1.8;
      
      :deep(strong) {
        color: $text-primary;
        font-weight: 600;
      }
      
      :deep(br) {
        display: block;
        content: '';
        margin-top: $spacing-sm;
      }
    }
  }

  &__tabs {
    display: flex;
    gap: $spacing-xs;
    margin-bottom: $spacing-md;
    align-items: center;
  }

  &__tab {
    padding: $spacing-xs $spacing-md;
    border-radius: $border-radius-sm;
    border: 1px solid $border-color;
    background: transparent;
    color: $text-secondary;
    font-size: $font-size-xs;
    cursor: pointer;
    transition: all $transition-fast;

    &:hover { border-color: $primary-color; color: $primary-color; }

    &--active {
      background: linear-gradient(135deg, $primary-color, $accent-color);
      color: white;
      border-color: transparent;
      &:hover { color: white; }
    }
  }

  &__tab-content {
    min-height: 100px;
  }

  &__tab-panel {
    animation: fadeIn 0.2s ease;
  }

  &__original-content {
    pre {
      white-space: pre-wrap;
      word-wrap: break-word;
      font-family: inherit;
      font-size: $font-size-sm;
      line-height: 1.8;
      color: $text-secondary;
      margin: 0;
      max-height: 500px;
      overflow-y: auto;
      @include custom-scrollbar;
    }
  }

  &__analysis-content {
    font-size: $font-size-sm;
    line-height: 1.8;
    max-height: 600px;
    overflow-y: auto;
    @include custom-scrollbar;

    :deep(h1) { font-size: $font-size-xl; margin: $spacing-lg 0 $spacing-md; }
    :deep(h2) { font-size: $font-size-lg; margin: $spacing-md 0 $spacing-sm; }
    :deep(h3) { font-size: $font-size-md; margin: $spacing-md 0 $spacing-sm; color: $primary-color; }
    :deep(h4) { font-size: $font-size-sm; margin: $spacing-sm 0; font-weight: 600; }
    :deep(strong) { color: $text-primary; }
    :deep(code) { background: rgba($primary-color, 0.1); padding: 1px 4px; border-radius: 3px; font-size: 0.9em; }
    :deep(blockquote) {
      border-left: 3px solid $primary-color;
      padding: $spacing-sm $spacing-md;
      color: $text-secondary;
      margin: $spacing-sm 0;
      background: rgba($primary-color, 0.03);
      border-radius: 0 $border-radius-sm $border-radius-sm 0;
    }
    :deep(ul), :deep(ol) { padding-left: $spacing-lg; margin: $spacing-xs 0; }
    :deep(li) { margin-bottom: $spacing-xs; }
    :deep(hr) { border: none; border-top: 1px solid $border-color; margin: $spacing-md 0; }
    :deep(p) { margin: $spacing-xs 0; }
  }

  &__structured {
    margin-top: $spacing-lg;
    display: grid;
    gap: $spacing-md;
  }

  &__stats-preview {
    display: flex;
    flex-wrap: wrap;
    gap: $spacing-xs;
    margin-top: $spacing-sm;
  }

  &__stat-badge {
    font-size: 11px;
    color: $text-muted;
    background: rgba($accent-color, 0.06);
    padding: 2px 8px;
    border-radius: $border-radius-sm;
    border: 1px solid rgba($accent-color, 0.12);
  }
}

.filter-row {
  display: flex;
  align-items: center;
  gap: $spacing-lg;
  flex-wrap: wrap;

  @media (max-width: $breakpoint-sm) {
    gap: $spacing-sm;
  }
}

// 来源类型 tab
.source-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;

  &__btn {
    padding: 5px 14px;
    border-radius: 99px;
    border: 1px solid $border-color;
    background: transparent;
    font-size: 13px;
    color: $text-secondary;
    cursor: pointer;
    transition: all 0.15s;

    &:hover { border-color: $primary-color; color: $primary-color; }

    &--active {
      background: rgba($primary-color, 0.1);
      border-color: $primary-color;
      color: $primary-color;
      font-weight: 600;
    }
  }
}

// 来源徽章
.source-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 600;
  margin-right: 6px;
  vertical-align: 2px;

  &.badge--course { background: rgba(#8B5CF6, 0.12); color: #7C3AED; }
  &.badge--self { background: rgba(#EC4899, 0.12); color: #DB2777; }
}

.timeline__instructor {
  font-size: 12px;
  color: $text-muted;
  font-weight: 400;
  margin-left: 6px;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: $spacing-sm;

  @media (max-width: $breakpoint-sm) {
    flex: 1;
    min-width: 0;
  }
  
  label {
    font-size: $font-size-sm;
    color: $text-secondary;
    font-weight: 500;
    flex-shrink: 0;
  }
}

.filter-input {
  padding: 6px 12px;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  color: $text-primary;
  background: white;
  transition: border-color $transition-fast;
  
  @media (max-width: $breakpoint-sm) {
    width: 100%;
    min-width: 0;
  }

  &:focus {
    outline: none;
    border-color: $primary-color;
  }
}

.filter-clear {
  padding: 6px 14px;
  border: none;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  color: $danger-color;
  background: rgba($danger-color, 0.08);
  cursor: pointer;
  transition: all $transition-fast;
  
  &:hover {
    background: rgba($danger-color, 0.15);
  }
}

.filter-result {
  margin-top: $spacing-sm;
  font-size: $font-size-xs;
  color: $text-muted;
}

// 结构化数据区块
.structured-section {
  background: rgba($primary-color, 0.02);
  border-radius: $border-radius-md;
  padding: $spacing-md;
  border: 1px solid rgba($primary-color, 0.06);

  &__title {
    font-size: $font-size-sm;
    font-weight: 600;
    color: $text-primary;
    margin: 0 0 $spacing-sm 0;

    &--clickable {
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      user-select: none;
      margin-bottom: 0;
      transition: color $transition-fast;

      &:hover { color: $primary-color; }
    }
  }

  &__arrow {
    font-size: 10px;
    color: $text-muted;
  }

  // 可折叠状态
  &--collapsible &__title--clickable {
    margin-bottom: 0;
  }

  &--open &__title--clickable {
    margin-bottom: $spacing-sm;
  }

  &__tags {
    display: flex;
    flex-wrap: wrap;
    gap: $spacing-xs;
  }

  &__list {
    padding-left: $spacing-lg;
    margin: 0;

    li {
      font-size: $font-size-sm;
      color: $text-secondary;
      line-height: 1.6;
      margin-bottom: $spacing-xs;
    }

    &--action li {
      color: $primary-color;
      &::marker { color: $accent-color; }
    }
  }

  &__concepts {
    display: flex;
    flex-wrap: wrap;
    gap: $spacing-xs;
  }

  &__models {
    display: grid;
    gap: $spacing-xs;
  }
}

.structured-tag {
  font-size: $font-size-xs;
  padding: 3px 10px;
  border-radius: 99px;
  background: rgba($primary-color, 0.08);
  color: $primary-color;
  border: 1px solid rgba($primary-color, 0.15);

  &--book {
    background: rgba($accent-color, 0.08);
    color: $accent-color;
    border-color: rgba($accent-color, 0.15);
  }

  &--mood {
    background: rgba($success-color, 0.08);
    color: $success-color;
    border-color: rgba($success-color, 0.15);
    font-size: $font-size-sm;
  }
}

.concept-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: $border-radius-sm;
  background: rgba($accent-color, 0.06);
  border: 1px solid rgba($accent-color, 0.12);
  font-size: $font-size-xs;

  &__name { font-weight: 500; color: $text-primary; }
  &__cat { color: $text-muted; font-size: 10px; }
  &__badge {
    font-size: 9px;
    padding: 0 5px;
    border-radius: 99px;
    font-weight: 600;

    &--merge { background: rgba($primary-color, 0.15); color: $primary-color; }
    &--new { background: rgba($success-color, 0.15); color: $success-color; }
  }
}

.model-card-mini {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-xs $spacing-sm;
  background: rgba($primary-color, 0.04);
  border-radius: $border-radius-sm;
  border: 1px solid rgba($primary-color, 0.08);

  &__title {
    font-size: $font-size-xs;
    font-weight: 600;
    color: $text-primary;
  }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

// 分页
.timeline-view__pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $spacing-md;
  padding: $spacing-md $spacing-lg;
  margin-top: $spacing-xl;

  @media (max-width: $breakpoint-sm) {
    gap: $spacing-sm;
    padding: $spacing-sm;
  }
}

.pagination__btn {
  padding: $spacing-xs $spacing-md;
  border-radius: $border-radius-sm;
  border: 1px solid $border-color;
  background: white;
  color: $text-secondary;
  font-size: $font-size-sm;
  cursor: pointer;
  transition: all $transition-fast;

  &:hover:not(:disabled) {
    border-color: $primary-color;
    color: $primary-color;
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-xs $spacing-sm;
    font-size: $font-size-xs;
  }
}

.pagination__pages {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pagination__page {
  width: 36px;
  height: 36px;
  border-radius: $border-radius-sm;
  border: 1px solid $border-color;
  background: white;
  color: $text-secondary;
  font-size: $font-size-sm;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all $transition-fast;

  &:hover:not(:disabled) {
    border-color: $primary-color;
    color: $primary-color;
  }

  &--active {
    background: linear-gradient(135deg, $primary-color, $accent-color);
    color: white;
    border-color: transparent;
    font-weight: 600;

    &:hover:not(:disabled) {
      color: white;
    }
  }

  @media (max-width: $breakpoint-sm) {
    width: 30px;
    height: 30px;
    font-size: $font-size-xs;
  }
}

.pagination__ellipsis {
  font-size: $font-size-sm;
  color: $text-muted;
  padding: 0 $spacing-xs;
}

.note-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;

  img {
    max-width: 100%;
    max-height: 240px;
    border-radius: 8px;
    object-fit: contain;
    background: rgba(0, 0, 0, 0.03);
  }
}
</style>
