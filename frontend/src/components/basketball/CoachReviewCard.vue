<script setup lang="ts">
/**
 * 教练点评卡 — POPOVICH MODE
 * 视觉锚点：左侧暗橙竖条 + 顶部教练徽标 + Markdown 渲染
 */
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{ review?: string | null; modelName?: string | null; loading?: boolean }>()

const html = computed(() => {
  if (!props.review) return ''
  try {
    return marked.parse(props.review, { breaks: true, gfm: true }) as string
  } catch {
    return (props.review || '').replace(/\n/g, '<br>')
  }
})
</script>

<template>
  <div class="coach-card">
    <div class="coach-card__bar"></div>
    <div class="coach-card__head">
      <span class="coach-card__badge">教练 · POPOVICH MODE</span>
      <span v-if="modelName" class="coach-card__model">{{ modelName }}</span>
    </div>
    <div v-if="loading" class="coach-card__loading">
      <span class="coach-card__loading-dot"></span>
      <span class="coach-card__loading-dot"></span>
      <span class="coach-card__loading-dot"></span>
      <span class="coach-card__loading-text">教练正在看你的反思……</span>
    </div>
    <div
      v-else-if="review"
      class="coach-card__body markdown-body"
      v-html="html"
    />
    <div v-else class="coach-card__empty">
      暂无点评
    </div>
  </div>
</template>

<style lang="scss" scoped>
.coach-card {
  position: relative;
  background: linear-gradient(135deg, #FFFBF5 0%, #FFF8F0 100%);
  border: 1px solid rgba(217, 119, 6, 0.15);
  border-radius: 12px;
  padding: 20px 24px 20px 28px;
  box-shadow: 0 4px 16px rgba(217, 119, 6, 0.06);
  animation: coach-fade-in 0.4s ease-out;

  &__bar {
    position: absolute;
    left: 0; top: 12px; bottom: 12px;
    width: 4px;
    border-radius: 4px;
    background: linear-gradient(180deg, #D97706, #B45309);
  }

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  &__badge {
    display: inline-block;
    padding: 4px 10px;
    background: linear-gradient(135deg, #1E40AF, #1E3A8A);
    color: white;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    border-radius: 4px;
  }

  &__model {
    font-size: 11px;
    color: #94A3B8;
    font-family: ui-monospace, monospace;
  }

  &__body {
    color: #1F2937;
    line-height: 1.75;
    font-size: 15px;

    :deep(p) { margin: 0 0 10px 0; }
    :deep(strong) { color: #B45309; }
    :deep(blockquote) {
      border-left: 3px solid #D97706;
      padding-left: 12px;
      color: #475569;
      margin: 12px 0;
    }
    :deep(ul), :deep(ol) {
      padding-left: 22px;
      margin: 8px 0;
    }
  }

  &__loading {
    display: flex; align-items: center; gap: 6px;
    padding: 16px 0;
    color: #94A3B8;
  }

  &__loading-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: #D97706;
    animation: bounce 1.4s ease-in-out infinite;
    &:nth-child(2) { animation-delay: 0.2s; }
    &:nth-child(3) { animation-delay: 0.4s; }
  }

  &__loading-text {
    margin-left: 8px;
    font-size: 13px;
  }

  &__empty {
    padding: 20px 0;
    color: #94A3B8;
    text-align: center;
    font-size: 14px;
  }
}

@keyframes coach-fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
