<script setup lang="ts">
/**
 * 底部固定栏式心力快捷记录组件
 * 默认折叠为一条横条，点击展开完整的成就+感恩双栏录入
 * 用于嵌入 TodoDashboard 和 ChatView 页面
 */
import { ref } from 'vue'
import WellbeingQuickInput from './WellbeingQuickInput.vue'

const expanded = ref(false)

const onCreated = (_count: number) => {
  // 保存成功后自动折叠
  setTimeout(() => { expanded.value = false }, 1500)
}
</script>

<template>
  <div class="wb-bar" :class="{ 'wb-bar--expanded': expanded }">
    <!-- 折叠状态 -->
    <div v-if="!expanded" class="wb-bar__collapsed" @click="expanded = true">
      <span class="wb-bar__icon">💚</span>
      <span class="wb-bar__text">顺手记一笔心力账户</span>
      <span class="wb-bar__arrow">▲</span>
    </div>

    <!-- 展开状态 -->
    <div v-else class="wb-bar__expanded">
      <div class="wb-bar__header">
        <span class="wb-bar__title">💚 快速记录心力账户</span>
        <button class="wb-bar__close" @click="expanded = false">✕</button>
      </div>
      <WellbeingQuickInput @created="onCreated" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.wb-bar {
  margin-top: 20px;
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s ease;

  &__collapsed {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 12px 20px;
    background: linear-gradient(135deg, rgba(20, 184, 166, 0.95), rgba(249, 115, 22, 0.85));
    color: white;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    border-radius: 12px;
    transition: all 0.2s;

    &:hover {
      padding: 14px 20px;
      box-shadow: 0 4px 16px rgba(20, 184, 166, 0.3);
    }
  }

  &__icon { font-size: 18px; }
  &__text { letter-spacing: 0.5px; }
  &__arrow {
    font-size: 10px;
    opacity: 0.7;
    transition: transform 0.2s;
  }

  &__expanded {
    background: white;
    border: 2px solid rgba(20, 184, 166, 0.3);
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
    padding: 16px 20px 20px;
    max-height: 380px;
    overflow-y: auto;
    animation: fadeIn 0.3s ease;
  }

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }

  &__title {
    font-size: 14px;
    font-weight: 600;
    color: #334155;
  }

  &__close {
    border: none;
    background: none;
    font-size: 16px;
    color: #94A3B8;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;

    &:hover {
      background: #f1f5f9;
      color: #475569;
    }
  }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

// 移动端适配
@media (max-width: 768px) {
  .wb-bar {
    margin-top: 16px;

    &__expanded {
      padding: 12px 16px 16px;
    }
  }
}
</style>
