<script setup lang="ts">
/**
 * 思维链折叠行（借鉴 harness）：
 * - 折叠态：流式期间单行摘要跟随（显示最新非空行并滚动到行尾），定稿后显示首行
 * - 展开态：完整思维链进入文档流
 */
import { computed, ref, watch, nextTick } from 'vue'

const props = defineProps<{
  thinking: string
  streaming: boolean
}>()

const expanded = ref(false)
const followLine = ref<HTMLElement | null>(null)

// 折叠态摘要：流式时取最新非空行，定稿后取首行
const summaryLine = computed(() => {
  const lines = (props.thinking || '').split('\n').map(l => l.trim()).filter(Boolean)
  if (!lines.length) return '思考中...'
  return props.streaming ? lines[lines.length - 1] : lines[0]
})

// 流式期间让摘要跟随滚动到行尾
watch(() => props.thinking, async () => {
  if (props.streaming && !expanded.value) {
    await nextTick()
    followLine.value?.scrollTo({ left: followLine.value.scrollWidth })
  }
})
</script>

<template>
  <div class="thinking-row" :class="{ 'thinking-row--streaming': streaming }">
    <button class="thinking-row__toggle" @click="expanded = !expanded">
      <span class="thinking-row__bar"></span>
      <span class="thinking-row__label">
        <span class="thinking-row__dot"></span>
        思维链{{ streaming ? '（思考中）' : '' }}
      </span>
      <span v-if="!expanded" ref="followLine" class="thinking-row__summary">{{ summaryLine }}</span>
      <span class="thinking-row__arrow">{{ expanded ? '▼' : '▶' }}</span>
    </button>
    <div v-if="expanded" class="thinking-row__full">{{ thinking }}</div>
  </div>
</template>

<style scoped lang="scss">
.thinking-row {
  margin-bottom: 6px;

  &__toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 4px 8px;
    border: none;
    background: transparent;
    cursor: pointer;
    border-radius: 6px;
    text-align: left;

    &:hover { background: rgba(0, 0, 0, 0.03); }
  }

  &__bar {
    width: 2px;
    align-self: stretch;
    border-radius: 2px;
    background: rgba(#3B82F6, 0.35);
    flex-shrink: 0;
  }

  &__label {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    font-weight: 600;
    color: #3B82F6;
    white-space: nowrap;
    flex-shrink: 0;
  }

  &__dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: #3B82F6;
  }

  &--streaming &__dot {
    animation: thinking-pulse 1s ease-in-out infinite;
  }

  @keyframes thinking-pulse {
    50% { opacity: 0.3; }
  }

  &__summary {
    flex: 1;
    min-width: 0;
    font-size: 11px;
    color: $text-muted;
    white-space: nowrap;
    overflow-x: auto;
    scrollbar-width: none;
    &::-webkit-scrollbar { display: none; }
  }

  &__arrow {
    font-size: 9px;
    color: $text-muted;
    flex-shrink: 0;
  }

  &__full {
    margin: 4px 0 4px 10px;
    padding: 8px 12px;
    border-left: 2px solid rgba(#3B82F6, 0.25);
    font-size: 12px;
    line-height: 1.7;
    color: $text-secondary;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 320px;
    overflow-y: auto;
  }
}
</style>
