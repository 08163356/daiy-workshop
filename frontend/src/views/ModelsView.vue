<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api } from '@/api'
import type { ThinkingModel } from '@/types/graph'

const loading = ref(true)
const modelsData = ref<ThinkingModel[]>([])
const searchQuery = ref('')
const expandedIndex = ref<number | null>(null)

// 搜索过滤
const filteredModels = computed(() => {
  if (!searchQuery.value.trim()) return modelsData.value
  const query = searchQuery.value.toLowerCase()
  return modelsData.value.filter(model => 
    model.title.toLowerCase().includes(query) ||
    model.description.toLowerCase().includes(query)
  )
})

// 切换展开
const toggleExpand = (index: number) => {
  expandedIndex.value = expandedIndex.value === index ? null : index
}

// 提取图标
const getIcon = (title: string): string => {
  const match = title.match(/^([\u{1F300}-\u{1F9FF}]|[\u{2600}-\u{26FF}])/u)
  return match ? match[0] : '💡'
}

// 清理标题（移除图标）
const cleanTitle = (title: string): string => {
  return title.replace(/^[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}]\s*/u, '')
}

onMounted(async () => {
  loading.value = true
  try {
    modelsData.value = await api.getModels()
  } catch (e) {
    console.error('加载思维模型失败:', e)
  }
  loading.value = false
})
</script>

<template>
  <div class="models-view">
    <!-- 页面标题 -->
    <header class="models-view__header animate-slideUp">
      <h1 class="models-view__title">
        <span class="models-view__title-icon">🎯</span>
        思维模型
      </h1>
      <p class="models-view__subtitle">构建你的思维工具箱，用模型解决问题</p>
    </header>
    
    <!-- 搜索栏 -->
    <div class="models-view__search card animate-slideUp" style="animation-delay: 0.05s">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="搜索思维模型..."
        class="search-input"
      />
      <span class="search-count">共 {{ filteredModels.length }} 个模型</span>
    </div>
    
    <!-- 加载状态 -->
    <div v-if="loading" class="models-view__loading">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
    </div>
    
    <!-- 模型网格 -->
    <div v-else class="models-view__grid">
      <div
        v-for="(model, index) in filteredModels"
        :key="index"
        class="model-card card animate-slideUp"
        :class="{ 'model-card--expanded': expandedIndex === index }"
        :style="{ animationDelay: `${0.1 + index * 0.03}s` }"
        @click="toggleExpand(index)"
      >
        <div class="model-card__header">
          <span class="model-card__icon">{{ getIcon(model.title) }}</span>
          <h3 class="model-card__title">{{ cleanTitle(model.title) }}</h3>
        </div>
        <div class="model-card__content" v-html="model.description"></div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.models-view {
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
  
  &__search {
    display: flex;
    align-items: center;
    gap: $spacing-md;
    padding: $spacing-md $spacing-lg;
    margin-bottom: $spacing-xl;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-sm $spacing-md;
      margin-bottom: $spacing-lg;
    }
    
    .search-input {
      flex: 1;
      border: none;
      background: transparent;
      font-size: $font-size-md;
      color: $text-primary;
      outline: none;
      
      &::placeholder {
        color: $text-muted;
      }
    }
    
    .search-count {
      font-size: $font-size-sm;
      color: $text-muted;
      white-space: nowrap;
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
  
  &__grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: $spacing-lg;
    
    @media (max-width: $breakpoint-md) {
      grid-template-columns: 1fr;
    }
  }
}

.model-card {
  padding: $spacing-lg;
  cursor: pointer;
  transition: all 0.3s ease;
  
  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba($primary-color, 0.12);
  }
  
  &--expanded {
    grid-column: 1 / -1;
    
    .model-card__content {
      max-height: none;
      -webkit-line-clamp: unset;
    }
  }
  
  &__header {
    display: flex;
    align-items: center;
    gap: $spacing-md;
    margin-bottom: $spacing-md;
  }
  
  &__icon {
    font-size: 28px;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, rgba($primary-color, 0.1), rgba($accent-color, 0.1));
    border-radius: $border-radius-lg;
  }
  
  &__title {
    flex: 1;
    font-size: $font-size-lg;
    font-weight: 600;
    color: $text-primary;
  }
  
  &__content {
    font-size: $font-size-sm;
    color: $text-secondary;
    line-height: 1.8;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    
    :deep(strong) {
      color: $text-primary;
      font-weight: 600;
    }
    
    :deep(br) {
      display: block;
      content: '';
      margin-top: $spacing-xs;
    }
  }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
