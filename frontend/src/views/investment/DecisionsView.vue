<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { INVESTMENT_API_BASE } from '@/config'

interface Decision {
  id: number
  date: string
  action: string
  target: string
  logic: string
  emotion_state: string | null
  position_percent: number | null
  result: string | null
  lesson: string | null
  created_at: string
}

const decisions = ref<Decision[]>([])
const loading = ref(true)
const error = ref('')

const actionIcons: Record<string, string> = {
  '买入': '📈',
  '卖出': '📉',
  '持有': '✋',
  '观望': '👀',
}

const emotionColors: Record<string, string> = {
  '冷静': '#10B981',
  '焦虑': '#F59E0B',
  '贪婪': '#EF4444',
  '恐惧': '#8B5CF6',
  'FOMO': '#EC4899',
}

const fetchDecisions = async () => {
  try {
    loading.value = true
    const response = await fetch(`${INVESTMENT_API_BASE}/decisions`)
    if (!response.ok) throw new Error('获取数据失败')
    const data = await response.json()
    decisions.value = data.items
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(fetchDecisions)
</script>

<template>
  <div class="decisions-view">
    <h1 class="page-title">
      <span class="page-title__icon">📈</span>
      决策日志
    </h1>

    <p class="page-desc">记录每次投资决策的逻辑和复盘</p>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-card">
      <p>{{ error }}</p>
      <button @click="fetchDecisions" class="retry-btn">重试</button>
    </div>

    <!-- 决策列表 -->
    <template v-else>
      <div v-if="decisions.length === 0" class="empty-state">
        <div class="empty-icon">📈</div>
        <h3>暂无决策记录</h3>
        <p>记录投资反思时，AI 会识别你的交易决策</p>
      </div>

      <div v-else class="decisions-list">
        <div 
          v-for="decision in decisions" 
          :key="decision.id"
          class="decision-card"
        >
          <div class="decision-card__header">
            <div class="decision-card__action">
              <span class="action-icon">{{ actionIcons[decision.action] || '📊' }}</span>
              <span class="action-text">{{ decision.action }}</span>
            </div>
            <span class="decision-card__target">{{ decision.target }}</span>
            <span class="decision-card__date">{{ decision.date }}</span>
          </div>

          <div class="decision-card__body">
            <div class="decision-card__logic">
              <span class="label">决策逻辑：</span>
              <p>{{ decision.logic }}</p>
            </div>

            <div class="decision-card__meta">
              <div v-if="decision.emotion_state" class="meta-item">
                <span class="label">情绪状态：</span>
                <span 
                  class="emotion-tag"
                  :style="{ color: emotionColors[decision.emotion_state] || '#64748B' }"
                >
                  {{ decision.emotion_state }}
                </span>
              </div>
              <div v-if="decision.position_percent !== null" class="meta-item">
                <span class="label">仓位：</span>
                <span class="position">{{ decision.position_percent }}%</span>
              </div>
            </div>
          </div>

          <!-- 复盘区域 -->
          <div v-if="decision.result || decision.lesson" class="decision-card__review">
            <div v-if="decision.result" class="review-item">
              <span class="label">📊 结果复盘：</span>
              <p>{{ decision.result }}</p>
            </div>
            <div v-if="decision.lesson" class="review-item">
              <span class="label">💡 经验教训：</span>
              <p>{{ decision.lesson }}</p>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.decisions-view {
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

.decisions-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-lg;
}

.decision-card {
  @include glass-card;
  overflow: hidden;
  
  &__header {
    display: flex;
    align-items: center;
    gap: $spacing-md;
    padding: $spacing-md $spacing-lg;
    background: rgba($primary-color, 0.05);
    border-bottom: 1px solid $border-color;
  }
  
  &__action {
    display: flex;
    align-items: center;
    gap: $spacing-xs;
    
    .action-icon {
      font-size: 24px;
    }
    
    .action-text {
      font-weight: 600;
      font-size: $font-size-md;
    }
  }
  
  &__target {
    padding: $spacing-xs $spacing-sm;
    background: rgba($accent-color, 0.15);
    color: $accent-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-sm;
    font-weight: 500;
  }
  
  &__date {
    margin-left: auto;
    color: $text-secondary;
    font-size: $font-size-sm;
  }
  
  &__body {
    padding: $spacing-lg;
  }
  
  &__logic {
    margin-bottom: $spacing-md;
    
    .label {
      font-size: $font-size-sm;
      color: $text-secondary;
      font-weight: 600;
    }
    
    p {
      margin-top: $spacing-xs;
      line-height: 1.6;
    }
  }
  
  &__meta {
    display: flex;
    flex-wrap: wrap;
    gap: $spacing-lg;
    
    .meta-item {
      display: flex;
      align-items: center;
      gap: $spacing-xs;
      
      .label {
        font-size: $font-size-sm;
        color: $text-secondary;
      }
      
      .emotion-tag {
        font-weight: 600;
      }
      
      .position {
        font-weight: 600;
        color: $primary-color;
      }
    }
  }
  
  &__review {
    padding: $spacing-lg;
    background: rgba($success-color, 0.05);
    border-top: 1px solid $border-color;
    
    .review-item {
      &:not(:last-child) {
        margin-bottom: $spacing-md;
      }
      
      .label {
        font-size: $font-size-sm;
        font-weight: 600;
        color: $success-color;
      }
      
      p {
        margin-top: $spacing-xs;
        font-size: $font-size-sm;
        color: $text-secondary;
        line-height: 1.6;
      }
    }
  }
}
</style>
