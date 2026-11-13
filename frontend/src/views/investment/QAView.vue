<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { INVESTMENT_API_BASE } from '@/config'

interface QA {
  id: number
  date: string
  question: string
  answer: string
  category: string | null
  source_reflection_id: number | null
  source_type: string
  tags: string[] | null
  is_resolved: boolean
  follow_up: string | null
  created_at: string
  updated_at: string
}

const qaList = ref<QA[]>([])
const loading = ref(true)
const error = ref('')
const selectedCategory = ref<string | null>(null)
const expandedId = ref<number | null>(null)

const categoryIcons: Record<string, string> = {
  '宏观经济': '🌍',
  '技术分析': '📊',
  '投资策略': '🎯',
  '风险管理': '🛡️',
  '心理情绪': '🧠',
  '市场观察': '👀',
}

const fetchQA = async () => {
  try {
    loading.value = true
    const url = selectedCategory.value 
      ? `${INVESTMENT_API_BASE}/qa?category=${encodeURIComponent(selectedCategory.value)}`
      : `${INVESTMENT_API_BASE}/qa`
    const response = await fetch(url)
    if (!response.ok) throw new Error('获取数据失败')
    const data = await response.json()
    qaList.value = data.items
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(fetchQA)

const selectCategory = (category: string | null) => {
  selectedCategory.value = category
  fetchQA()
}

const toggleExpand = (id: number) => {
  expandedId.value = expandedId.value === id ? null : id
}

// 获取所有分类
const categories = computed(() => {
  const cats = new Set(qaList.value.map(q => q.category).filter(Boolean))
  return Array.from(cats) as string[]
})

// 按日期分组
const groupedByDate = computed(() => {
  const groups: Record<string, QA[]> = {}
  qaList.value.forEach(qa => {
    const date = qa.date
    if (!groups[date]) groups[date] = []
    groups[date].push(qa)
  })
  // 按日期倒序
  const sortedKeys = Object.keys(groups).sort((a, b) => b.localeCompare(a))
  const result: Record<string, QA[]> = {}
  sortedKeys.forEach(key => {
    result[key] = groups[key]
  })
  return result
})

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { 
    year: 'numeric', 
    month: 'long', 
    day: 'numeric',
    weekday: 'short'
  })
}

const getSourceTypeLabel = (type: string) => {
  return type === 'explicit' ? '显式标记' : '自动识别'
}
</script>

<template>
  <div class="qa-view">
    <h1 class="page-title">
      <span class="page-title__icon">❓</span>
      Q&A 问答库
    </h1>

    <p class="page-desc">投资反思中提出的问题和 AI 解答</p>

    <!-- 分类筛选 -->
    <div class="category-filter" v-if="categories.length">
      <button 
        class="filter-btn" 
        :class="{ 'filter-btn--active': !selectedCategory }"
        @click="selectCategory(null)"
      >
        全部
      </button>
      <button 
        v-for="cat in categories"
        :key="cat"
        class="filter-btn"
        :class="{ 'filter-btn--active': selectedCategory === cat }"
        @click="selectCategory(cat)"
      >
        {{ categoryIcons[cat] || '📌' }} {{ cat }}
      </button>
    </div>

    <!-- 统计信息 -->
    <div class="stats-bar" v-if="qaList.length">
      <span class="stat-item">
        <span class="stat-icon">📝</span>
        共 {{ qaList.length }} 个问答
      </span>
      <span class="stat-item">
        <span class="stat-icon">📅</span>
        跨越 {{ Object.keys(groupedByDate).length }} 天
      </span>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-card">
      <p>{{ error }}</p>
      <button @click="fetchQA" class="retry-btn">重试</button>
    </div>

    <!-- Q&A 列表 -->
    <template v-else>
      <div v-if="qaList.length === 0" class="empty-state">
        <div class="empty-icon">❓</div>
        <h3>暂无问答记录</h3>
        <p>在投资反思中提出问题（用问号结尾或标记【问题】），AI 会识别并解答</p>
      </div>

      <div v-else class="qa-content">
        <div 
          v-for="(items, date) in groupedByDate" 
          :key="date"
          class="date-section"
        >
          <h2 class="date-title">
            <span class="date-icon">📅</span>
            {{ formatDate(date) }}
            <span class="date-count">{{ items.length }} 个问题</span>
          </h2>
          
          <div class="qa-list">
            <div 
              v-for="qa in items" 
              :key="qa.id"
              class="qa-card"
              :class="{ 'qa-card--expanded': expandedId === qa.id }"
            >
              <!-- 问题头部 -->
              <div class="qa-card__header" @click="toggleExpand(qa.id)">
                <div class="qa-card__question">
                  <span class="question-icon">Q</span>
                  <span class="question-text">{{ qa.question }}</span>
                </div>
                <div class="qa-card__meta">
                  <span v-if="qa.category" class="meta-tag category-tag">
                    {{ categoryIcons[qa.category] || '📌' }} {{ qa.category }}
                  </span>
                  <span class="meta-tag source-tag">
                    {{ getSourceTypeLabel(qa.source_type) }}
                  </span>
                  <span class="expand-icon">{{ expandedId === qa.id ? '▼' : '▶' }}</span>
                </div>
              </div>
              
              <!-- 答案展开区域 -->
              <div v-if="expandedId === qa.id" class="qa-card__body">
                <div class="answer-section">
                  <span class="answer-icon">A</span>
                  <div class="answer-content">{{ qa.answer }}</div>
                </div>
                
                <!-- 标签 -->
                <div v-if="qa.tags && qa.tags.length" class="tags-section">
                  <span 
                    v-for="tag in qa.tags" 
                    :key="tag" 
                    class="tag"
                  >
                    #{{ tag }}
                  </span>
                </div>
                
                <!-- 后续追问 -->
                <div v-if="qa.follow_up" class="follow-up-section">
                  <h4>💭 后续追问</h4>
                  <p>{{ qa.follow_up }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.qa-view {
  padding: $spacing-md;
}

.page-title {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  font-size: $font-size-xxl;
  font-weight: 700;
  margin-bottom: $spacing-sm;

  @media (max-width: $breakpoint-sm) {
    font-size: $font-size-xl;
  }
  
  &__icon {
    font-size: 36px;

    @media (max-width: $breakpoint-sm) {
      font-size: 28px;
    }
  }
}

.page-desc {
  color: $text-secondary;
  margin-bottom: $spacing-lg;
}

.category-filter {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-sm;
  margin-bottom: $spacing-lg;
}

.filter-btn {
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-md;
  background: rgba($primary-color, 0.1);
  color: $text-secondary;
  font-size: $font-size-sm;
  transition: all $transition-fast;
  
  &:hover {
    background: rgba($primary-color, 0.2);
  }
  
  &--active {
    background: $primary-color;
    color: white;
  }
}

.stats-bar {
  display: flex;
  gap: $spacing-lg;
  margin-bottom: $spacing-xl;
  padding: $spacing-md;
  background: rgba($primary-color, 0.05);
  border-radius: $border-radius-md;

  @media (max-width: $breakpoint-sm) {
    flex-wrap: wrap;
    gap: $spacing-md;
  }
}

.stat-item {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  color: $text-secondary;
  font-size: $font-size-sm;
  
  .stat-icon {
    font-size: $font-size-md;
  }
}

.loading {
  @include flex-center;
  flex-direction: column;
  gap: $spacing-md;
  padding: $spacing-xxl;
  
  &__spinner {
    width: 40px;
    height: 40px;
    border: 3px solid $border-color;
    border-top-color: $primary-color;
    border-radius: 50%;
    animation: spin 1s linear infinite;
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
  
  .retry-btn {
    margin-top: $spacing-md;
    padding: $spacing-sm $spacing-lg;
    background: $primary-color;
    color: white;
    border-radius: $border-radius-md;
  }
}

.empty-state {
  @include glass-card;
  @include flex-center;
  flex-direction: column;
  padding: $spacing-xxl;
  text-align: center;
  
  .empty-icon {
    font-size: 64px;
    margin-bottom: $spacing-md;
  }
  
  h3 {
    font-size: $font-size-lg;
    margin-bottom: $spacing-sm;
  }
  
  p {
    color: $text-secondary;
    max-width: 400px;
  }
}

.qa-content {
  display: flex;
  flex-direction: column;
  gap: $spacing-xl;
}

.date-section {
  @include glass-card;
  padding: $spacing-lg;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    border-radius: $border-radius-md;
  }
}

.date-title {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  font-size: $font-size-lg;
  font-weight: 600;
  margin-bottom: $spacing-lg;
  padding-bottom: $spacing-md;
  border-bottom: 1px solid $border-color;
  
  .date-icon {
    font-size: $font-size-xl;
  }
  
  .date-count {
    font-size: $font-size-sm;
    font-weight: normal;
    padding: 2px 8px;
    background: rgba($primary-color, 0.1);
    color: $primary-color;
    border-radius: $border-radius-sm;
    margin-left: auto;
  }
}

.qa-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.qa-card {
  background: rgba($primary-color, 0.03);
  border-radius: $border-radius-md;
  border-left: 4px solid $primary-color;
  overflow: hidden;
  transition: all $transition-fast;
  
  &:hover {
    background: rgba($primary-color, 0.06);
  }
  
  &--expanded {
    border-left-color: $success-color;
  }
  
  &__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: $spacing-md $spacing-lg;
    cursor: pointer;
    gap: $spacing-md;
  }
  
  &__question {
    display: flex;
    gap: $spacing-sm;
    flex: 1;
    
    .question-icon {
      flex-shrink: 0;
      width: 24px;
      height: 24px;
      background: $primary-color;
      color: white;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: $font-size-sm;
      font-weight: 700;
    }
    
    .question-text {
      font-weight: 500;
      line-height: 1.6;
    }
  }
  
  &__meta {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    flex-shrink: 0;
  }
  
  &__body {
    padding: 0 $spacing-lg $spacing-lg;
    border-top: 1px solid $border-color;
    margin-top: 0;
    padding-top: $spacing-md;
  }
}

.meta-tag {
  padding: 2px 8px;
  border-radius: $border-radius-sm;
  font-size: $font-size-xs;
  
  &.category-tag {
    background: rgba($primary-color, 0.1);
    color: $primary-color;
  }
  
  &.source-tag {
    background: rgba($text-muted, 0.1);
    color: $text-muted;
  }
}

.expand-icon {
  font-size: $font-size-xs;
  color: $text-muted;
  transition: transform $transition-fast;
}

.answer-section {
  display: flex;
  gap: $spacing-sm;
  
  .answer-icon {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    background: $success-color;
    color: white;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: $font-size-sm;
    font-weight: 700;
  }
  
  .answer-content {
    flex: 1;
    line-height: 1.8;
    color: $text-secondary;
    white-space: pre-wrap;
  }
}

.tags-section {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-xs;
  margin-top: $spacing-md;
  padding-left: 32px;
  
  .tag {
    padding: 2px 8px;
    background: rgba($info-color, 0.1);
    color: $info-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-xs;
  }
}

.follow-up-section {
  margin-top: $spacing-md;
  padding: $spacing-md;
  padding-left: 32px;
  background: rgba($warning-color, 0.05);
  border-radius: $border-radius-md;
  margin-left: 32px;

  @media (max-width: $breakpoint-sm) {
    margin-left: 0;
    padding-left: $spacing-md;
  }
  
  h4 {
    font-size: $font-size-sm;
    font-weight: 600;
    margin-bottom: $spacing-xs;
    color: $warning-color;
  }
  
  p {
    font-size: $font-size-sm;
    color: $text-secondary;
  }
}
</style>
