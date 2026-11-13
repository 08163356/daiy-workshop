<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { INVESTMENT_API_BASE } from '@/config'

interface Emotion {
  id: number
  date: string
  emotion: string
  trigger: string
  impact: string | null
  coping_strategy: string | null
  effectiveness: number | null
  created_at: string
}

const emotions = ref<Emotion[]>([])
const loading = ref(true)
const error = ref('')

const emotionIcons: Record<string, string> = {
  'FOMO': '😰',
  '恐惧': '😨',
  '贪婪': '🤑',
  '焦虑': '😟',
  '沮丧': '😔',
  '过度自信': '😎',
  '冷静': '😌',
}

const fetchEmotions = async () => {
  try {
    loading.value = true
    const response = await fetch(`${INVESTMENT_API_BASE}/emotions`)
    if (!response.ok) throw new Error('获取数据失败')
    const data = await response.json()
    emotions.value = data.items
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(fetchEmotions)

// 按情绪类型分组统计
const emotionStats = computed(() => {
  const stats: Record<string, number> = {}
  emotions.value.forEach(e => {
    stats[e.emotion] = (stats[e.emotion] || 0) + 1
  })
  return stats
})

// 有效性星级
const getStars = (effectiveness: number | null) => {
  if (!effectiveness) return ''
  return '⭐'.repeat(effectiveness)
}
</script>

<template>
  <div class="emotions-view">
    <h1 class="page-title">
      <span class="page-title__icon">🎭</span>
      情绪复盘
    </h1>

    <p class="page-desc">识别和管理投资中的情绪因素</p>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-card">
      <p>{{ error }}</p>
      <button @click="fetchEmotions" class="retry-btn">重试</button>
    </div>

    <!-- 情绪列表 -->
    <template v-else>
      <div v-if="emotions.length === 0" class="empty-state">
        <div class="empty-icon">🎭</div>
        <h3>暂无情绪记录</h3>
        <p>记录投资反思时，AI 会识别你的情绪状态</p>
      </div>

      <template v-else>
        <!-- 情绪统计 -->
        <div class="emotion-stats" v-if="Object.keys(emotionStats).length">
          <div 
            v-for="(count, emotion) in emotionStats" 
            :key="emotion"
            class="stat-item"
          >
            <span class="stat-item__icon">{{ emotionIcons[emotion] || '😐' }}</span>
            <span class="stat-item__name">{{ emotion }}</span>
            <span class="stat-item__count">{{ count }}次</span>
          </div>
        </div>

        <!-- 情绪记录列表 -->
        <div class="emotions-list">
          <div 
            v-for="emotion in emotions" 
            :key="emotion.id"
            class="emotion-card"
          >
            <div class="emotion-card__header">
              <span class="emotion-card__icon">{{ emotionIcons[emotion.emotion] || '😐' }}</span>
              <span class="emotion-card__type">{{ emotion.emotion }}</span>
              <span class="emotion-card__date">{{ emotion.date }}</span>
            </div>

            <div class="emotion-card__body">
              <div class="emotion-card__trigger">
                <span class="label">触发因素：</span>
                <p>{{ emotion.trigger }}</p>
              </div>

              <div v-if="emotion.impact" class="emotion-card__impact">
                <span class="label">对决策的影响：</span>
                <p>{{ emotion.impact }}</p>
              </div>

              <div v-if="emotion.coping_strategy" class="emotion-card__strategy">
                <span class="label">应对策略：</span>
                <p>{{ emotion.coping_strategy }}</p>
                <div v-if="emotion.effectiveness" class="effectiveness">
                  <span>有效性：</span>
                  <span class="stars">{{ getStars(emotion.effectiveness) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.emotions-view {
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

.emotion-stats {
  @include glass-card;
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-md;
  padding: $spacing-lg;
  margin-bottom: $spacing-xl;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-md;
  background: rgba($primary-color, 0.08);
  border-radius: $border-radius-md;
  
  &__icon {
    font-size: 24px;
  }
  
  &__name {
    font-weight: 500;
  }
  
  &__count {
    font-size: $font-size-sm;
    color: $primary-color;
    font-weight: 600;
  }
}

.emotions-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: $spacing-lg;
}

.emotion-card {
  @include glass-card;
  overflow: hidden;
  
  &__header {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    padding: $spacing-md $spacing-lg;
    background: rgba($warning-color, 0.1);
    border-bottom: 1px solid $border-color;
  }
  
  &__icon {
    font-size: 28px;
  }
  
  &__type {
    font-weight: 600;
    font-size: $font-size-lg;
  }
  
  &__date {
    margin-left: auto;
    color: $text-secondary;
    font-size: $font-size-sm;
  }
  
  &__body {
    padding: $spacing-lg;
    display: flex;
    flex-direction: column;
    gap: $spacing-md;
  }
  
  &__trigger, &__impact, &__strategy {
    .label {
      display: block;
      font-size: $font-size-sm;
      color: $text-secondary;
      font-weight: 600;
      margin-bottom: $spacing-xs;
    }
    
    p {
      line-height: 1.6;
    }
  }
  
  &__strategy {
    padding: $spacing-md;
    background: rgba($success-color, 0.08);
    border-radius: $border-radius-md;
    border-left: 3px solid $success-color;
    
    .label {
      color: $success-color;
    }
    
    .effectiveness {
      margin-top: $spacing-sm;
      font-size: $font-size-sm;
      color: $text-secondary;
      
      .stars {
        margin-left: $spacing-xs;
      }
    }
  }
}
</style>
