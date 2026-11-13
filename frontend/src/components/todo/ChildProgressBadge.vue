<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  total: number
  done: number
  compact?: boolean
}>(), {
  compact: false,
})

const safeTotal = computed(() => Math.max(0, props.total || 0))
const safeDone = computed(() => Math.min(safeTotal.value, Math.max(0, props.done || 0)))
const completed = computed(() => safeTotal.value > 0 && safeDone.value === safeTotal.value)
</script>

<template>
  <span
    class="child-progress"
    :class="{ 'child-progress--compact': compact, 'child-progress--completed': completed }"
    :title="`子任务进度：${safeDone}/${safeTotal}`"
  >
    <span class="child-progress__dot" aria-hidden="true"></span>
    {{ safeDone }}/{{ safeTotal }}
  </span>
</template>

<style scoped>
.child-progress {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
  padding: 2px 7px;
  border: 1px solid #dbe4f0;
  border-radius: 999px;
  background: #f8fafc;
  color: #64748b;
  font-size: 11px;
  line-height: 1.3;
  white-space: nowrap;
}

.child-progress__dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #94a3b8;
}

.child-progress--compact {
  gap: 3px;
  padding: 1px 5px;
  font-size: 10px;
}

.child-progress--completed {
  border-color: #bbf7d0;
  background: #f0fdf4;
  color: #15803d;
}

.child-progress--completed .child-progress__dot {
  background: #22c55e;
}
</style>
