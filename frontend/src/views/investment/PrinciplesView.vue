<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { INVESTMENT_API_BASE } from '@/config'

interface Principle {
  id: number
  title: string
  content: string
  category: string
  version: number
  is_active: boolean
  created_at: string
  updated_at: string
}

const principles = ref<Principle[]>([])
const loading = ref(true)
const error = ref('')
const selectedCategory = ref<string | null>(null)

const categories = ['风险管理', '仓位管理', '心态管理', '择时策略', '选标策略']
const categoryIcons: Record<string, string> = {
  '风险管理': '🛡️',
  '仓位管理': '📊',
  '心态管理': '🧘',
  '择时策略': '⏰',
  '选标策略': '🎯',
}

const fetchPrinciples = async () => {
  try {
    loading.value = true
    const url = selectedCategory.value 
      ? `${INVESTMENT_API_BASE}/principles?category=${encodeURIComponent(selectedCategory.value)}`
      : `${INVESTMENT_API_BASE}/principles`
    const response = await fetch(url)
    if (!response.ok) throw new Error('获取数据失败')
    const data = await response.json()
    principles.value = data.items
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(fetchPrinciples)

const selectCategory = (category: string | null) => {
  selectedCategory.value = category
  fetchPrinciples()
}

// 按分类分组
const groupedPrinciples = computed(() => {
  const groups: Record<string, Principle[]> = {}
  principles.value.forEach(p => {
    if (!groups[p.category]) groups[p.category] = []
    groups[p.category].push(p)
  })
  return groups
})
</script>

<template>
  <div class="principles-view">
    <h1 class="page-title">
      <span class="page-title__icon">📋</span>
      投资原则
    </h1>

    <!-- 分类筛选 -->
    <div class="category-filter">
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
        {{ categoryIcons[cat] }} {{ cat }}
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
      <button @click="fetchPrinciples" class="retry-btn">重试</button>
    </div>

    <!-- 原则列表 -->
    <template v-else>
      <div v-if="principles.length === 0" class="empty-state">
        <div class="empty-icon">📋</div>
        <h3>暂无投资原则</h3>
        <p>开始记录你的投资反思，AI 会帮你提炼投资原则</p>
      </div>

      <div v-else class="principles-content">
        <div 
          v-for="(items, category) in groupedPrinciples" 
          :key="category"
          class="category-group"
        >
          <h2 class="category-title">
            <span>{{ categoryIcons[category] || '📌' }}</span>
            {{ category }}
            <span class="category-count">{{ items.length }}</span>
          </h2>
          
          <div class="principle-cards">
            <div 
              v-for="principle in items" 
              :key="principle.id"
              class="principle-card"
            >
              <div class="principle-card__header">
                <h3 class="principle-card__title">{{ principle.title }}</h3>
                <span class="principle-card__version">v{{ principle.version }}</span>
              </div>
              <p class="principle-card__content">{{ principle.content }}</p>
              <div class="principle-card__footer">
                <span class="principle-card__date">
                  {{ new Date(principle.created_at).toLocaleDateString() }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.principles-view {
  padding: $spacing-md;
}

.page-title {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  font-size: $font-size-xxl;
  font-weight: 700;
  margin-bottom: $spacing-xl;

  @media (max-width: $breakpoint-sm) {
    font-size: $font-size-xl;
    margin-bottom: $spacing-lg;
  }
  
  &__icon {
    font-size: 36px;

    @media (max-width: $breakpoint-sm) {
      font-size: 28px;
    }
  }
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

.principles-content {
  display: flex;
  flex-direction: column;
  gap: $spacing-xl;
}

.category-group {
  @include glass-card;
  padding: $spacing-lg;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    border-radius: $border-radius-md;
  }
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

.principle-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: $spacing-md;

  @media (max-width: $breakpoint-md) {
    grid-template-columns: 1fr;
  }
}

.principle-card {
  padding: $spacing-lg;
  background: rgba($primary-color, 0.03);
  border-radius: $border-radius-md;
  border-left: 3px solid $success-color;
  transition: all $transition-fast;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
  }
  
  @media (hover: hover) and (pointer: fine) {
    &:hover {
      background: rgba($primary-color, 0.06);
      transform: translateX(4px);
    }
  }
  
  &__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: $spacing-sm;
  }
  
  &__title {
    font-size: $font-size-md;
    font-weight: 600;
    flex: 1;
  }
  
  &__version {
    font-size: $font-size-xs;
    padding: 2px 6px;
    background: rgba($accent-color, 0.15);
    color: $accent-color;
    border-radius: $border-radius-sm;
  }
  
  &__content {
    font-size: $font-size-sm;
    color: $text-secondary;
    line-height: 1.6;
    margin-bottom: $spacing-md;
  }
  
  &__footer {
    display: flex;
    justify-content: flex-end;
  }
  
  &__date {
    font-size: $font-size-xs;
    color: $text-muted;
  }
}
</style>
