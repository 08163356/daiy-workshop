<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useGraphStore } from '@/stores'
import KnowledgeGraph from '@/components/charts/KnowledgeGraph.vue'
import type { GraphNode } from '@/types/graph'
import { CATEGORY_COLORS, getCategoryIcon } from '@/types/graph'

const graphStore = useGraphStore()
const graphRef = ref<InstanceType<typeof KnowledgeGraph>>()

const loading = computed(() => graphStore.loading)
const error = computed(() => graphStore.error)
const graphData = computed(() => graphStore.graphData)
const selectedNode = computed(() => graphStore.selectedNode)
const highlightedNodeIds = computed(() => graphStore.highlightedNodeIds)
const relatedNodes = computed(() => graphStore.relatedNodes)

// 统计各分类数量
const categoryStats = computed(() => {
  const stats: Record<string, number> = {}
  for (const node of graphStore.nodes) {
    const cat = node.category || '未分类'
    stats[cat] = (stats[cat] || 0) + 1
  }
  return Object.entries(stats)
    .sort((a, b) => b[1] - a[1])
    .map(([name, count]) => ({ name, count, color: CATEGORY_COLORS[name] || '#64748B' }))
})

// 节点点击处理
const handleNodeClick = (node: GraphNode) => {
  graphStore.selectNode(node.id)
}

// 背景点击处理
const handleBackgroundClick = () => {
  graphStore.clearSelection()
}

// 适应屏幕
const fitToScreen = () => {
  graphRef.value?.zoomToFit()
}

// 重置缩放
const resetZoom = () => {
  graphRef.value?.resetZoom()
}

onMounted(async () => {
  if (graphStore.nodes.length === 0) {
    await graphStore.loadGraphData()
  }
})
</script>

<template>
  <div class="graph-view">
    <!-- 页面标题 -->
    <header class="graph-view__header animate-slideUp">
      <div class="graph-view__title-section">
        <h1 class="graph-view__title">
          <span class="graph-view__title-icon">🕸️</span>
          知识图谱
        </h1>
        <p class="graph-view__subtitle">探索书籍、概念与作者之间的关联</p>
      </div>
      
      <div class="graph-view__actions">
        <button class="btn btn-secondary" @click="fitToScreen">
          🔍 适应屏幕
        </button>
        <button class="btn btn-secondary" @click="resetZoom">
          ↺ 重置
        </button>
      </div>
    </header>
    
    <!-- 主要内容 -->
    <div class="graph-view__content animate-slideUp" style="animation-delay: 0.1s">
      <!-- 加载状态 -->
      <div v-if="loading" class="graph-view__loading">
        <div class="loading-spinner"></div>
        <span>加载图谱数据...</span>
      </div>
      
      <!-- 错误状态 -->
      <div v-else-if="error" class="graph-view__error">
        <span class="error-icon">⚠️</span>
        <span>{{ error }}</span>
        <button class="btn btn-primary" @click="graphStore.loadGraphData">重试</button>
      </div>
      
      <!-- 图谱组件 -->
      <template v-else>
        <div class="graph-view__main">
          <!-- 图例面板 -->
          <aside class="graph-view__legend">
            <h4>知识分类</h4>
            <div class="legend-list">
              <div
                v-for="cat in categoryStats"
                :key="cat.name"
                class="legend-item"
              >
                <span class="legend-item__color" :style="{ background: cat.color }"></span>
                <span class="legend-item__name">{{ cat.name }}</span>
                <span class="legend-item__count">{{ cat.count }}</span>
              </div>
            </div>
          </aside>
          
          <!-- 图谱区域 -->
          <div class="graph-view__graph">
            <KnowledgeGraph
              ref="graphRef"
              :data="graphData"
              :selected-node-id="selectedNode?.id || null"
              :highlighted-node-ids="highlightedNodeIds"
              @node-click="handleNodeClick"
              @background-click="handleBackgroundClick"
            />
          </div>
          
          <!-- 详情面板 -->
          <aside
            class="graph-view__sidebar"
            :class="{ 'graph-view__sidebar--visible': selectedNode }"
          >
            <template v-if="selectedNode">
              <div class="detail-panel">
                <div class="detail-panel__header">
                  <span class="detail-panel__icon">
                    {{ getCategoryIcon(selectedNode.category) }}
                  </span>
                  <div class="detail-panel__title">
                    <h3>{{ selectedNode.name }}</h3>
                    <span 
                      class="detail-panel__type"
                      :style="{ background: CATEGORY_COLORS[selectedNode.category || '未分类'] + '20', color: CATEGORY_COLORS[selectedNode.category || '未分类'] }"
                    >
                      {{ selectedNode.category || '未分类' }}
                    </span>
                  </div>
                  <button class="detail-panel__close" @click="graphStore.clearSelection">
                    ✕
                  </button>
                </div>
                
                <div class="detail-panel__body">
                  <p v-if="selectedNode.description" class="detail-panel__desc">
                    {{ selectedNode.description }}
                  </p>
                  
                  <div class="detail-panel__meta" v-if="selectedNode.importance">
                    <div class="meta-item">
                      <span class="meta-item__label">重要度</span>
                      <span class="meta-item__value">
                        <span v-for="i in (selectedNode.importance || 1)" :key="i">⭐</span>
                      </span>
                    </div>
                  </div>
                  
                  <!-- 关联节点 -->
                  <div class="detail-panel__related" v-if="relatedNodes.length > 0">
                    <h4>关联概念 ({{ relatedNodes.length }})</h4>
                    <div class="related-list">
                      <div
                        v-for="node in relatedNodes"
                        :key="node.id"
                        class="related-item"
                        @click="handleNodeClick(node)"
                      >
                        <span class="related-item__icon">
                          {{ getCategoryIcon(node.category) }}
                        </span>
                        <span class="related-item__name">{{ node.name }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            
            <template v-else>
              <div class="detail-panel detail-panel--empty">
                <div class="empty-hint">
                  <span class="empty-hint__icon">👆</span>
                  <p>点击节点查看详情</p>
                </div>
              </div>
            </template>
          </aside>
        </div>
      </template>
    </div>
    
    <!-- 使用提示 -->
    <footer class="graph-view__tips animate-slideUp" style="animation-delay: 0.2s">
      <div class="tip-item">🖱️ 拖拽节点可移动位置</div>
      <div class="tip-item">🔍 滚轮缩放，拖拽画布平移</div>
      <div class="tip-item">👆 点击节点高亮关联</div>
    </footer>
  </div>
</template>

<style lang="scss" scoped>
.graph-view {
  display: flex;
  flex-direction: column;
  gap: $spacing-lg;
  height: calc(100vh - 140px);

  @media (max-width: $breakpoint-md) {
    height: calc(100vh - 180px);
    gap: $spacing-md;
  }
  
  &__header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: $spacing-md;

    @media (max-width: $breakpoint-sm) {
      gap: $spacing-sm;
    }
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

    @media (max-width: $breakpoint-sm) {
      font-size: $font-size-sm;
    }
  }
  
  &__actions {
    display: flex;
    gap: $spacing-sm;

    @media (max-width: $breakpoint-sm) {
      .btn {
        font-size: $font-size-xs;
        padding: $spacing-xs $spacing-sm;
      }
    }
  }
  
  &__content {
    flex: 1;
    min-height: 0;
  }
  
  &__loading,
  &__error {
    @include glass-card;
    @include flex-center;
    flex-direction: column;
    gap: $spacing-md;
    height: 100%;
    color: $text-secondary;
    
    .loading-spinner {
      width: 40px;
      height: 40px;
      border: 3px solid rgba($primary-color, 0.2);
      border-top-color: $primary-color;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
    
    .error-icon {
      font-size: 48px;
    }
  }
  
  &__main {
    display: flex;
    gap: $spacing-lg;
    height: 100%;
  }
  
  &__legend {
    width: 200px;
    flex-shrink: 0;
    @include glass-card;
    padding: $spacing-md;
    overflow-y: auto;
    @include custom-scrollbar;
    
    h4 {
      font-size: $font-size-sm;
      color: $text-muted;
      margin-bottom: $spacing-md;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
    
    @media (max-width: $breakpoint-lg) {
      display: none;
    }
  }
  
  &__graph {
    flex: 1;
    min-width: 0;
    height: 100%;
  }
  
  &__sidebar {
    width: 320px;
    transition: all $transition-normal;
    
    @media (max-width: $breakpoint-lg) {
      position: fixed;
      right: -340px;
      top: 80px;
      bottom: 0;
      z-index: 50;
      padding: $spacing-md;
      
      &--visible {
        right: 0;
      }
    }
  }
  
  &__tips {
    display: flex;
    justify-content: center;
    gap: $spacing-xl;
    padding: $spacing-md;
    
    .tip-item {
      font-size: $font-size-sm;
      color: $text-muted;
    }
    
    @media (max-width: $breakpoint-md) {
      flex-direction: column;
      align-items: center;
      gap: $spacing-sm;
    }
  }
}

// 详情面板
.detail-panel {
  @include glass-card;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  
  &--empty {
    @include flex-center;
  }
  
  &__header {
    display: flex;
    align-items: flex-start;
    gap: $spacing-md;
    padding: $spacing-lg;
    border-bottom: 1px solid $border-color;
  }
  
  &__icon {
    font-size: 40px;
  }
  
  &__title {
    flex: 1;
    
    h3 {
      font-size: $font-size-lg;
      font-weight: 600;
      color: $text-primary;
      margin-bottom: $spacing-xs;
    }
  }
  
  &__type {
    font-size: $font-size-xs;
    color: $text-muted;
    background: rgba($primary-color, 0.1);
    padding: 2px 8px;
    border-radius: $border-radius-sm;
  }
  
  &__close {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: transparent;
    color: $text-muted;
    @include flex-center;
    transition: all $transition-fast;
    
    &:hover {
      background: rgba($danger-color, 0.1);
      color: $danger-color;
    }
  }
  
  &__body {
    flex: 1;
    padding: $spacing-lg;
    overflow-y: auto;
    @include custom-scrollbar;
  }
  
  &__desc {
    color: $text-secondary;
    line-height: 1.6;
    margin-bottom: $spacing-lg;
  }
  
  &__meta {
    display: flex;
    flex-direction: column;
    gap: $spacing-sm;
    margin-bottom: $spacing-lg;
    
    .meta-item {
      display: flex;
      align-items: center;
      gap: $spacing-md;
      
      &__label {
        font-size: $font-size-sm;
        color: $text-muted;
        min-width: 50px;
      }
      
      &__value {
        font-weight: 500;
        color: $text-primary;
      }
    }
  }
  
  &__related {
    h4 {
      font-size: $font-size-sm;
      color: $text-muted;
      margin-bottom: $spacing-md;
      text-transform: uppercase;
      letter-spacing: 1px;
    }
  }
}

// 关联列表
.related-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
}

.related-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-md;
  background: rgba($primary-color, 0.05);
  border-radius: $border-radius-sm;
  cursor: pointer;
  transition: all $transition-fast;
  
  &:hover {
    background: rgba($primary-color, 0.1);
    transform: translateX(4px);
  }
  
  &__icon {
    font-size: 16px;
  }
  
  &__name {
    font-size: $font-size-sm;
    color: $text-primary;
    @include text-ellipsis;
  }
}

// 空状态提示
.empty-hint {
  text-align: center;
  color: $text-muted;
  
  &__icon {
    font-size: 48px;
    display: block;
    margin-bottom: $spacing-md;
  }
  
  p {
    font-size: $font-size-sm;
  }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

// 图例
.legend-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-xs 0;
  
  &__color {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  
  &__name {
    flex: 1;
    font-size: $font-size-xs;
    color: $text-primary;
    @include text-ellipsis;
  }
  
  &__count {
    font-size: $font-size-xs;
    color: $text-muted;
    background: rgba($primary-color, 0.1);
    padding: 2px 6px;
    border-radius: $border-radius-sm;
  }
}
</style>
