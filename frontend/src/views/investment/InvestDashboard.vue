<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { INVESTMENT_API_BASE } from '@/config'

const router = useRouter()

interface Overview {
  reflection_count: number
  principle_count: number
  cognition_count: number
  decision_count: number
  emotion_count: number
  knowledge_count: number
  qa_count: number
  principles_by_category: Record<string, number>
  emotions_by_type: Record<string, number>
  decisions_by_action: Record<string, number>
  qa_by_category: Record<string, number>
  recent_principles: Array<{
    id: number
    title: string
    category: string
  }>
  recent_cognitions: Array<{
    id: number
    date: string
    old_cognition: string
    new_cognition: string
  }>
  recent_qa: Array<{
    id: number
    date: string
    question: string
    category: string | null
  }>
}

const overview = ref<Overview | null>(null)
const loading = ref(true)
const error = ref('')

const fetchOverview = async () => {
  try {
    loading.value = true
    const response = await fetch(`${INVESTMENT_API_BASE}/overview`)
    if (!response.ok) throw new Error('获取数据失败')
    overview.value = await response.json()
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(fetchOverview)

// 统计卡片数据
const statCards = computed(() => {
  if (!overview.value) return []
  return [
    { label: '反思记录', value: overview.value.reflection_count, icon: '📝', color: '#3B82F6', route: '' },
    { label: '投资原则', value: overview.value.principle_count, icon: '📋', color: '#10B981', route: '/investment/principles' },
    { label: '认知迭代', value: overview.value.cognition_count, icon: '🔄', color: '#8B5CF6', route: '/investment/cognitions' },
    { label: 'Q&A 问答', value: overview.value.qa_count, icon: '❓', color: '#EC4899', route: '/investment/qa' },
    { label: '决策记录', value: overview.value.decision_count, icon: '📈', color: '#F59E0B', route: '/investment/decisions' },
    { label: '情绪记录', value: overview.value.emotion_count, icon: '🎭', color: '#EF4444', route: '/investment/emotions' },
    { label: '知识点', value: overview.value.knowledge_count, icon: '💡', color: '#06B6D4', route: '/investment/knowledge' },
  ]
})

const goToRoute = (route: string) => {
  if (route) router.push(route)
}

// 分类图标映射
const categoryIcons: Record<string, string> = {
  '风险管理': '🛡️',
  '仓位管理': '📊',
  '心态管理': '🧘',
  '择时策略': '⏰',
  '选标策略': '🎯',
}

const qaCategoryIcons: Record<string, string> = {
  '宏观经济': '🌍',
  '技术分析': '📊',
  '投资策略': '🎯',
  '风险管理': '🛡️',
  '心理情绪': '🧠',
  '市场观察': '👀',
}
</script>

<template>
  <div class="invest-dashboard">
    <h1 class="page-title">
      <span class="page-title__icon">💰</span>
      投资系统总览
    </h1>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-card">
      <p>{{ error }}</p>
      <p class="error-hint">请确保后端服务已启动：<code>daily-system\start-all.bat</code></p>
      <button @click="fetchOverview" class="retry-btn">重试</button>
    </div>

    <!-- 数据展示 -->
    <template v-else-if="overview">
      <!-- 统计卡片 -->
      <div class="stat-grid">
        <div
          v-for="stat in statCards"
          :key="stat.label"
          class="stat-card"
          :class="{ 'stat-card--clickable': stat.route }"
          :style="{ '--card-color': stat.color }"
          @click="goToRoute(stat.route)"
        >
          <span class="stat-card__icon">{{ stat.icon }}</span>
          <div class="stat-card__content">
            <span class="stat-card__value">{{ stat.value }}</span>
            <span class="stat-card__label">{{ stat.label }}</span>
          </div>
          <span v-if="stat.route" class="stat-card__arrow">→</span>
        </div>
      </div>

      <!-- 主要内容区 -->
      <div class="main-content">
        <!-- 左侧：原则分类 + 最近原则 -->
        <div class="content-section">
          <h2 class="section-title">
            <span>📋</span> 投资原则概览
          </h2>
          
          <!-- 分类统计 -->
          <div class="category-stats" v-if="Object.keys(overview.principles_by_category).length">
            <div
              v-for="(count, category) in overview.principles_by_category"
              :key="category"
              class="category-item"
            >
              <span class="category-item__icon">{{ categoryIcons[category] || '📌' }}</span>
              <span class="category-item__name">{{ category }}</span>
              <span class="category-item__count">{{ count }}</span>
            </div>
          </div>
          <div v-else class="empty-state">
            <p>暂无投资原则</p>
            <p class="empty-hint">开始记录你的投资反思，AI 会帮你提炼原则</p>
          </div>

          <!-- 最近原则 -->
          <div class="recent-list" v-if="overview.recent_principles.length">
            <h3 class="recent-title">最近添加</h3>
            <div
              v-for="principle in overview.recent_principles"
              :key="principle.id"
              class="recent-item"
            >
              <span class="recent-item__category">{{ principle.category }}</span>
              <span class="recent-item__title">{{ principle.title }}</span>
            </div>
          </div>
        </div>

        <!-- 右侧：最近认知迭代 -->
        <div class="content-section">
          <h2 class="section-title">
            <span>🔄</span> 最近认知迭代
          </h2>
          
          <div class="cognition-list" v-if="overview.recent_cognitions.length">
            <div
              v-for="cognition in overview.recent_cognitions"
              :key="cognition.id"
              class="cognition-item"
            >
              <div class="cognition-item__date">{{ cognition.date }}</div>
              <div class="cognition-item__change">
                <div class="cognition-item__old">
                  <span class="label">旧认知：</span>
                  {{ cognition.old_cognition }}
                </div>
                <div class="cognition-item__arrow">→</div>
                <div class="cognition-item__new">
                  <span class="label">新认知：</span>
                  {{ cognition.new_cognition }}
                </div>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">
            <p>暂无认知迭代记录</p>
            <p class="empty-hint">记录投资反思时，AI 会识别你的认知变化</p>
          </div>
        </div>
      </div>

      <!-- 最近 Q&A -->
      <div class="qa-section" v-if="overview.recent_qa && overview.recent_qa.length">
        <div class="content-section">
          <h2 class="section-title">
            <span>❓</span> 最近问答
            <router-link to="/investment/qa" class="see-all-link">查看全部 →</router-link>
          </h2>
          
          <div class="qa-list">
            <div
              v-for="qa in overview.recent_qa"
              :key="qa.id"
              class="qa-item"
            >
              <div class="qa-item__header">
                <span class="qa-item__date">{{ qa.date }}</span>
                <span v-if="qa.category" class="qa-item__category">
                  {{ qaCategoryIcons[qa.category] || '📌' }} {{ qa.category }}
                </span>
              </div>
              <div class="qa-item__question">{{ qa.question }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 情绪和决策统计 -->
      <div class="bottom-stats" v-if="Object.keys(overview.emotions_by_type).length || Object.keys(overview.decisions_by_action).length">
        <!-- 情绪统计 -->
        <div class="stats-section" v-if="Object.keys(overview.emotions_by_type).length">
          <h3>🎭 情绪分布</h3>
          <div class="stats-bars">
            <div
              v-for="(count, emotion) in overview.emotions_by_type"
              :key="emotion"
              class="stats-bar"
            >
              <span class="stats-bar__label">{{ emotion }}</span>
              <div class="stats-bar__track">
                <div
                  class="stats-bar__fill"
                  :style="{ width: `${Math.min(count * 20, 100)}%` }"
                ></div>
              </div>
              <span class="stats-bar__count">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- 决策统计 -->
        <div class="stats-section" v-if="Object.keys(overview.decisions_by_action).length">
          <h3>📈 决策分布</h3>
          <div class="stats-bars">
            <div
              v-for="(count, action) in overview.decisions_by_action"
              :key="action"
              class="stats-bar"
            >
              <span class="stats-bar__label">{{ action }}</span>
              <div class="stats-bar__track">
                <div
                  class="stats-bar__fill stats-bar__fill--green"
                  :style="{ width: `${Math.min(count * 20, 100)}%` }"
                ></div>
              </div>
              <span class="stats-bar__count">{{ count }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.invest-dashboard {
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

.loading {
  @include flex-center;
  flex-direction: column;
  gap: $spacing-md;
  padding: $spacing-xxl;
  color: $text-secondary;
  
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
  
  .error-hint {
    margin-top: $spacing-md;
    color: $text-secondary;
    font-size: $font-size-sm;
    
    code {
      background: rgba($primary-color, 0.1);
      padding: 2px 8px;
      border-radius: 4px;
    }
  }
  
  .retry-btn {
    margin-top: $spacing-md;
    padding: $spacing-sm $spacing-lg;
    background: $primary-color;
    color: white;
    border-radius: $border-radius-md;
    
    &:hover {
      background: darken($primary-color, 10%);
    }
  }
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: $spacing-md;
  margin-bottom: $spacing-xl;

  @media (max-width: $breakpoint-sm) {
    grid-template-columns: repeat(2, 1fr);
    gap: $spacing-sm;
    margin-bottom: $spacing-lg;
  }
}

.stat-card {
  @include glass-card;
  @include hover-lift;
  padding: $spacing-lg;
  display: flex;
  align-items: center;
  gap: $spacing-md;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    border-radius: $border-radius-md;
    gap: $spacing-sm;
    flex-direction: column;
    text-align: center;
  }
  
  &--clickable {
    cursor: pointer;
    
    &:hover {
      border-color: rgba(var(--card-color), 0.3);
      
      .stat-card__arrow {
        transform: translateX(4px);
        color: var(--card-color);
      }
    }
  }
  
  &__icon {
    font-size: 32px;
  }
  
  &__content {
    display: flex;
    flex-direction: column;
    flex: 1;
  }
  
  &__value {
    font-size: $font-size-xl;
    font-weight: 700;
    color: var(--card-color);
  }
  
  &__label {
    font-size: $font-size-sm;
    color: $text-secondary;
  }
  
  &__arrow {
    font-size: $font-size-lg;
    color: $text-muted;
    transition: all $transition-fast;
  }
}

.main-content {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: $spacing-lg;
  margin-bottom: $spacing-xl;

  @media (max-width: $breakpoint-md) {
    grid-template-columns: 1fr;
  }

  @media (max-width: $breakpoint-sm) {
    gap: $spacing-md;
    margin-bottom: $spacing-lg;
  }
}

.content-section {
  @include glass-card;
  padding: $spacing-lg;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    border-radius: $border-radius-md;
  }
}

.section-title {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  font-size: $font-size-lg;
  font-weight: 600;
  margin-bottom: $spacing-lg;
  padding-bottom: $spacing-md;
  border-bottom: 1px solid $border-color;
}

.category-stats {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-sm;
  margin-bottom: $spacing-lg;
}

.category-item {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  padding: $spacing-xs $spacing-md;
  background: rgba($primary-color, 0.1);
  border-radius: $border-radius-md;
  font-size: $font-size-sm;
  
  &__icon {
    font-size: 16px;
  }
  
  &__count {
    font-weight: 600;
    color: $primary-color;
  }
}

.empty-state {
  text-align: center;
  padding: $spacing-xl;
  color: $text-secondary;
  
  .empty-hint {
    font-size: $font-size-sm;
    margin-top: $spacing-sm;
  }
}

.recent-list {
  margin-top: $spacing-lg;
}

.recent-title {
  font-size: $font-size-sm;
  color: $text-secondary;
  margin-bottom: $spacing-md;
}

.recent-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-sm;
  border-radius: $border-radius-sm;
  
  &:hover {
    background: rgba($primary-color, 0.05);
  }
  
  &__category {
    font-size: $font-size-xs;
    padding: 2px 8px;
    background: rgba($success-color, 0.15);
    color: $success-color;
    border-radius: $border-radius-sm;
  }
  
  &__title {
    font-size: $font-size-sm;
  }
}

.cognition-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.cognition-item {
  padding: $spacing-md;
  background: rgba($primary-color, 0.03);
  border-radius: $border-radius-md;
  border-left: 3px solid $accent-color;
  
  &__date {
    font-size: $font-size-xs;
    color: $text-secondary;
    margin-bottom: $spacing-sm;
  }
  
  &__change {
    display: flex;
    flex-direction: column;
    gap: $spacing-xs;
    font-size: $font-size-sm;
  }
  
  &__arrow {
    color: $accent-color;
    font-weight: bold;
    align-self: center;
  }
  
  &__old, &__new {
    .label {
      font-weight: 600;
      color: $text-secondary;
    }
  }
  
  &__new {
    color: $success-color;
  }
}

.bottom-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: $spacing-lg;

  @media (max-width: $breakpoint-md) {
    grid-template-columns: 1fr;
  }

  @media (max-width: $breakpoint-sm) {
    gap: $spacing-md;
  }
}

.qa-section {
  margin-bottom: $spacing-xl;
}

.see-all-link {
  margin-left: auto;
  font-size: $font-size-sm;
  font-weight: normal;
  color: $primary-color;
  text-decoration: none;
  
  &:hover {
    text-decoration: underline;
  }
}

.qa-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.qa-item {
  padding: $spacing-md;
  background: rgba($primary-color, 0.03);
  border-radius: $border-radius-md;
  border-left: 3px solid #EC4899;
  transition: all $transition-fast;
  
  &:hover {
    background: rgba($primary-color, 0.06);
    transform: translateX(4px);
  }
  
  &__header {
    display: flex;
    align-items: center;
    gap: $spacing-md;
    margin-bottom: $spacing-sm;
  }
  
  &__date {
    font-size: $font-size-xs;
    color: $text-secondary;
  }
  
  &__category {
    font-size: $font-size-xs;
    padding: 2px 8px;
    background: rgba(#EC4899, 0.1);
    color: #EC4899;
    border-radius: $border-radius-sm;
  }
  
  &__question {
    font-size: $font-size-sm;
    line-height: 1.6;
    color: $text-primary;
  }
}

.stats-section {
  @include glass-card;
  padding: $spacing-lg;
  
  h3 {
    font-size: $font-size-md;
    margin-bottom: $spacing-lg;
  }
}

.stats-bars {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.stats-bar {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  
  &__label {
    width: 60px;
    font-size: $font-size-sm;
    color: $text-secondary;
  }
  
  &__track {
    flex: 1;
    height: 8px;
    background: rgba($primary-color, 0.1);
    border-radius: 4px;
    overflow: hidden;
  }
  
  &__fill {
    height: 100%;
    background: $accent-color;
    border-radius: 4px;
    transition: width $transition-normal;
    
    &--green {
      background: $success-color;
    }
  }
  
  &__count {
    width: 30px;
    text-align: right;
    font-size: $font-size-sm;
    font-weight: 600;
  }
}
</style>
