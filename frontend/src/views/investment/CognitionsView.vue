<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { INVESTMENT_API_BASE } from '@/config'

interface Cognition {
  id: number
  date: string
  old_cognition: string
  new_cognition: string
  trigger: string
  category: string | null
  created_at: string
}

const cognitions = ref<Cognition[]>([])
const loading = ref(true)
const error = ref('')

const fetchCognitions = async () => {
  try {
    loading.value = true
    const response = await fetch(`${INVESTMENT_API_BASE}/cognitions`)
    if (!response.ok) throw new Error('获取数据失败')
    const data = await response.json()
    cognitions.value = data.items
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(fetchCognitions)
</script>

<template>
  <div class="cognitions-view">
    <h1 class="page-title">
      <span class="page-title__icon">🔄</span>
      认知迭代
    </h1>

    <p class="page-desc">记录你在投资学习过程中的认知变化</p>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="error-card">
      <p>{{ error }}</p>
      <button @click="fetchCognitions" class="retry-btn">重试</button>
    </div>

    <!-- 认知列表 -->
    <template v-else>
      <div v-if="cognitions.length === 0" class="empty-state">
        <div class="empty-icon">🔄</div>
        <h3>暂无认知迭代记录</h3>
        <p>记录投资反思时，AI 会识别你的认知变化</p>
      </div>

      <div v-else class="timeline">
        <div 
          v-for="(cognition, index) in cognitions" 
          :key="cognition.id"
          class="timeline-item"
        >
          <div class="timeline-item__marker">
            <div class="timeline-item__dot"></div>
            <div v-if="index < cognitions.length - 1" class="timeline-item__line"></div>
          </div>
          
          <div class="timeline-item__content">
            <div class="timeline-item__header">
              <span class="timeline-item__date">{{ cognition.date }}</span>
              <span v-if="cognition.category" class="timeline-item__category">
                {{ cognition.category }}
              </span>
            </div>
            
            <div class="cognition-change">
              <div class="cognition-change__old">
                <span class="label">❌ 旧认知</span>
                <p>{{ cognition.old_cognition }}</p>
              </div>
              <div class="cognition-change__arrow">↓</div>
              <div class="cognition-change__new">
                <span class="label">✅ 新认知</span>
                <p>{{ cognition.new_cognition }}</p>
              </div>
            </div>
            
            <div class="timeline-item__trigger">
              <span class="label">💡 触发事件：</span>
              {{ cognition.trigger }}
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.cognitions-view {
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

.timeline {
  display: flex;
  flex-direction: column;
}

.timeline-item {
  display: flex;
  gap: $spacing-lg;
  
  &__marker {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 20px;
  }
  
  &__dot {
    width: 12px;
    height: 12px;
    background: $accent-color;
    border-radius: 50%;
    flex-shrink: 0;
  }
  
  &__line {
    width: 2px;
    flex: 1;
    background: linear-gradient(to bottom, $accent-color, transparent);
    margin-top: $spacing-xs;
  }
  
  &__content {
    @include glass-card;
    flex: 1;
    padding: $spacing-lg;
    margin-bottom: $spacing-lg;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-md;
      border-radius: $border-radius-md;
    }
  }
  
  &__header {
    display: flex;
    align-items: center;
    gap: $spacing-md;
    margin-bottom: $spacing-md;
  }
  
  &__date {
    font-weight: 600;
    color: $primary-color;
  }
  
  &__category {
    font-size: $font-size-xs;
    padding: 2px 8px;
    background: rgba($accent-color, 0.15);
    color: $accent-color;
    border-radius: $border-radius-sm;
  }
  
  &__trigger {
    margin-top: $spacing-md;
    padding-top: $spacing-md;
    border-top: 1px solid $border-color;
    font-size: $font-size-sm;
    color: $text-secondary;
    
    .label {
      font-weight: 600;
    }
  }
}

.cognition-change {
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;
  
  &__old, &__new {
    padding: $spacing-md;
    border-radius: $border-radius-md;
    
    .label {
      display: block;
      font-size: $font-size-sm;
      font-weight: 600;
      margin-bottom: $spacing-xs;
    }
    
    p {
      font-size: $font-size-md;
      line-height: 1.6;
    }
  }
  
  &__old {
    background: rgba($danger-color, 0.08);
    border-left: 3px solid $danger-color;
    
    .label {
      color: $danger-color;
    }
  }
  
  &__new {
    background: rgba($success-color, 0.08);
    border-left: 3px solid $success-color;
    
    .label {
      color: $success-color;
    }
  }
  
  &__arrow {
    @include flex-center;
    font-size: 24px;
    color: $accent-color;
  }
}
</style>
