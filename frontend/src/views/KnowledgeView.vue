<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api } from '@/api'
import type { KnowledgeCategory } from '@/types/graph'

const loading = ref(true)
const knowledgeData = ref<KnowledgeCategory[]>([])
const searchQuery = ref('')
const expandedCategories = ref<Set<number>>(new Set([0])) // 默认展开第一个

// 搜索过滤
const filteredKnowledge = computed(() => {
  if (!searchQuery.value.trim()) return knowledgeData.value
  const query = searchQuery.value.toLowerCase()
  return knowledgeData.value.map(category => ({
    ...category,
    items: category.items.filter(item =>
      item.name.toLowerCase().includes(query) ||
      item.description.toLowerCase().includes(query)
    )
  })).filter(category => category.items.length > 0)
})

// 统计总知识点数
const totalItems = computed(() => 
  knowledgeData.value.reduce((sum, cat) => sum + cat.items.length, 0)
)

// 切换分类展开
const toggleCategory = (index: number) => {
  if (expandedCategories.value.has(index)) {
    expandedCategories.value.delete(index)
  } else {
    expandedCategories.value.add(index)
  }
}

// 提取图标
const getIcon = (title: string): string => {
  const match = title.match(/^([\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}])/u)
  return match ? match[0] : '📚'
}

// 清理标题
const cleanTitle = (title: string): string => {
  return title.replace(/^[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}]\s*/u, '')
}

// 获取分类颜色
const getCategoryColor = (index: number): string => {
  const colors = [
    '#6366F1', '#10B981', '#8B5CF6', '#F59E0B', '#EF4444',
    '#3B82F6', '#06B6D4', '#EC4899', '#22C55E', '#A855F7',
    '#F97316', '#14B8A6', '#84CC16', '#7C3AED'
  ]
  return colors[index % colors.length]
}

onMounted(async () => {
  loading.value = true
  try {
    knowledgeData.value = await api.getKnowledge()
  } catch (e) {
    console.error('加载知识分类失败:', e)
  }
  loading.value = false
})
</script>

<template>
  <div class="knowledge-view">
    <!-- 页面标题 -->
    <header class="knowledge-view__header animate-slideUp">
      <h1 class="knowledge-view__title">
        <span class="knowledge-view__title-icon">📚</span>
        知识分类
      </h1>
      <p class="knowledge-view__subtitle">系统化的知识体系，让学习更有条理</p>
    </header>
    
    <!-- 搜索和统计 -->
    <div class="knowledge-view__toolbar card animate-slideUp" style="animation-delay: 0.05s">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索知识点..."
        class="search-input"
      />
      <div class="stats">
        <span class="stats__item">
          <strong>{{ knowledgeData.length }}</strong> 个分类
        </span>
        <span class="stats__item">
          <strong>{{ totalItems }}</strong> 个知识点
        </span>
      </div>
    </div>
    
    <!-- 加载状态 -->
    <div v-if="loading" class="knowledge-view__loading">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
    </div>
    
    <!-- 知识分类列表 -->
    <div v-else class="knowledge-view__categories">
      <div
        v-for="(category, catIndex) in filteredKnowledge"
        :key="catIndex"
        class="category card animate-slideUp"
        :style="{ animationDelay: `${0.1 + catIndex * 0.03}s` }"
      >
        <!-- 分类标题 -->
        <div 
          class="category__header"
          :style="{ '--cat-color': getCategoryColor(catIndex) }"
          @click="toggleCategory(catIndex)"
        >
          <span class="category__icon">{{ getIcon(category.title) }}</span>
          <h2 class="category__title">{{ cleanTitle(category.title) }}</h2>
          <span class="category__count">{{ category.items.length }} 个</span>
          <span class="category__toggle">
            {{ expandedCategories.has(catIndex) ? '▼' : '▶' }}
          </span>
        </div>
        
        <!-- 知识点列表 -->
        <div 
          v-if="expandedCategories.has(catIndex)" 
          class="category__items"
        >
          <div
            v-for="(item, itemIndex) in category.items"
            :key="itemIndex"
            class="knowledge-item"
          >
            <div class="knowledge-item__name">
              <span 
                class="knowledge-item__dot"
                :style="{ background: getCategoryColor(catIndex) }"
              ></span>
              {{ item.name }}
            </div>
            <p class="knowledge-item__desc">{{ item.description }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.knowledge-view {
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
  
  &__toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: $spacing-md;
    padding: $spacing-md $spacing-lg;
    margin-bottom: $spacing-xl;
    flex-wrap: wrap;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-sm $spacing-md;
      margin-bottom: $spacing-lg;
    }
    
    .search-input {
      flex: 1;
      min-width: 200px;
      border: none;
      background: transparent;
      font-size: $font-size-md;
      color: $text-primary;
      outline: none;
      
      &::placeholder {
        color: $text-muted;
      }
    }
    
    .stats {
      display: flex;
      gap: $spacing-lg;
      
      &__item {
        font-size: $font-size-sm;
        color: $text-secondary;
        
        strong {
          color: $primary-color;
          font-weight: 600;
        }
      }
    }
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
  
  &__categories {
    display: flex;
    flex-direction: column;
    gap: $spacing-md;
  }
}

.category {
  overflow: hidden;
  
  &__header {
    display: flex;
    align-items: center;
    gap: $spacing-md;
    padding: $spacing-lg;
    cursor: pointer;
    transition: background 0.3s;
    border-left: 4px solid var(--cat-color, $primary-color);

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-md;
      gap: $spacing-sm;
    }
    
    &:hover {
      background: rgba($primary-color, 0.03);
    }
  }
  
  &__icon {
    font-size: 24px;
  }
  
  &__title {
    flex: 1;
    font-size: $font-size-lg;
    font-weight: 600;
    color: $text-primary;
  }
  
  &__count {
    font-size: $font-size-sm;
    color: $text-muted;
    background: rgba($primary-color, 0.1);
    padding: 4px 12px;
    border-radius: $border-radius-sm;
  }
  
  &__toggle {
    font-size: $font-size-xs;
    color: $text-muted;
  }
  
  &__items {
    padding: 0 $spacing-lg $spacing-lg;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: $spacing-md;
    
    @media (max-width: $breakpoint-md) {
      grid-template-columns: 1fr;
    }
  }
}

.knowledge-item {
  padding: $spacing-md;
  background: rgba($primary-color, 0.02);
  border-radius: $border-radius-md;
  border: 1px solid rgba($primary-color, 0.08);
  transition: all 0.3s;
  
  &:hover {
    background: rgba($primary-color, 0.05);
    border-color: rgba($primary-color, 0.15);
  }
  
  &__name {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    font-size: $font-size-md;
    font-weight: 600;
    color: $text-primary;
    margin-bottom: $spacing-xs;
  }
  
  &__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  
  &__desc {
    font-size: $font-size-sm;
    color: $text-secondary;
    line-height: 1.6;
    padding-left: 16px;
  }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
