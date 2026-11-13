<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { INVESTMENT_API_BASE } from '@/config'

interface Knowledge {
  id: number
  name: string
  description: string
  category: string
  source: string | null
  created_at: string
}

const knowledge = ref<Knowledge[]>([])
const loading = ref(true)
const error = ref('')
const selectedCategory = ref<string | null>(null)

const categoryIcons: Record<string, string> = {
  '宏观经济': '🌍',
  '行为金融': '🧠',
  '技术分析': '📊',
  '基本面分析': '📈',
  '量化策略': '🤖',
  '风险管理': '🛡️',
}

const fetchKnowledge = async () => {
  try {
    loading.value = true
    const url = selectedCategory.value 
      ? `${INVESTMENT_API_BASE}/knowledge?category=${encodeURIComponent(selectedCategory.value)}`
      : `${INVESTMENT_API_BASE}/knowledge`
    const response = await fetch(url)
    if (!response.ok) throw new Error('获取数据失败')
    const data = await response.json()
    knowledge.value = data.items
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(fetchKnowledge)

const selectCategory = (category: string | null) => {
  selectedCategory.value = category
  fetchKnowledge()
}

// 按分类分组
const groupedKnowledge = computed(() => {
  const groups: Record<string, Knowledge[]> = {}
  knowledge.value.forEach(k => {
    if (!groups[k.category]) groups[k.category] = []
    groups[k.category].push(k)
  })
  return groups
})

// 获取所有分类
const categories = computed(() => {
  const cats = new Set(knowledge.value.map(k => k.category))
  return Array.from(cats)
})
</script>

<template>
  <div class="knowledge-view">
    <h1 class="page-title">
      <span class="page-title__icon">💡</span>
      投资知识体系
    </h1>

    <p class="page-desc">系统化整理投资相关的知识和概念</p>

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

    <!-- 加载状态 -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-card">
      <p>{{ error }}</p>
      <button @click="fetchKnowledge" class="retry-btn">重试</button>
    </div>

    <!-- 知识列表 -->
    <template v-else>
      <div v-if="knowledge.length === 0" class="empty-state">
        <div class="empty-icon">💡</div>
        <h3>暂无知识记录</h3>
        <p>记录投资反思时，AI 会提取和补充投资知识</p>
      </div>

      <div v-else class="knowledge-content">
        <div 
          v-for="(items, category) in groupedKnowledge" 
          :key="category"
          class="category-section"
        >
          <h2 class="category-title">
            <span>{{ categoryIcons[category] || '📌' }}</span>
            {{ category }}
            <span class="category-count">{{ items.length }}</span>
          </h2>
          
          <div class="knowledge-grid">
            <div 
              v-for="item in items" 
              :key="item.id"
              class="knowledge-card"
            >
              <h3 class="knowledge-card__name">{{ item.name }}</h3>
              <p class="knowledge-card__desc">{{ item.description }}</p>
              <div v-if="item.source" class="knowledge-card__source">
                来源：{{ item.source }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.knowledge-view {
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
  margin-bottom: $spacing-xl;
}

.category-filter {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-sm;
  margin-bottom: $spacing-xl;
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
  }
}

.knowledge-content {
  display: flex;
  flex-direction: column;
  gap: $spacing-xl;
}

.category-section {
  @include glass-card;
  padding: $spacing-lg;
}

.category-title {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  font-size: $font-size-lg;
  font-weight: 600;
  margin-bottom: $spacing-lg;
  padding-bottom: $spacing-md;
  border-bottom: 1px solid $border-color;
  
  .category-count {
    font-size: $font-size-sm;
    padding: 2px 8px;
    background: rgba($primary-color, 0.1);
    color: $primary-color;
    border-radius: $border-radius-sm;
  }
}

.knowledge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: $spacing-md;
}

.knowledge-card {
  padding: $spacing-lg;
  background: rgba($primary-color, 0.03);
  border-radius: $border-radius-md;
  border-left: 3px solid $primary-color;
  transition: all $transition-fast;
  
  &:hover {
    background: rgba($primary-color, 0.06);
    transform: translateX(4px);
  }
  
  &__name {
    font-size: $font-size-md;
    font-weight: 600;
    margin-bottom: $spacing-sm;
    color: $primary-color;
  }
  
  &__desc {
    font-size: $font-size-sm;
    color: $text-secondary;
    line-height: 1.6;
  }
  
  &__source {
    margin-top: $spacing-md;
    padding-top: $spacing-sm;
    border-top: 1px solid $border-color;
    font-size: $font-size-xs;
    color: $text-muted;
  }
}
</style>
