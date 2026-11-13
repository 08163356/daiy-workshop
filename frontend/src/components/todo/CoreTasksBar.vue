<script setup lang="ts">
/**
 * 核心任务条 —— 日历规划页顶部通栏
 * 展示当前本周/本月核心任务（后端按周期 key 过滤，过期自动失效），
 * 点击任务打开详情，右侧「对齐检查」按钮触发 AI 对照分析
 */
import { ref, onMounted, watch } from 'vue'
import { TODO_API_BASE } from '@/config'

// 日历选中的日期：按该日期所在周/月取核心任务（点历史月份时回看当时设的核心）
const props = defineProps<{ selectedDate?: string | null }>()

interface CoreTask {
  id: number
  title: string
  status: string
  quadrant: number
}

const emit = defineEmits<{
  'open-task': [task: CoreTask]
  'review': []
}>()

const weekCore = ref<CoreTask[]>([])
const monthCore = ref<CoreTask[]>([])
const yearCore = ref<CoreTask[]>([])

const load = async () => {
  try {
    const q = props.selectedDate ? `?date=${props.selectedDate}` : ''
    const res = await fetch(`${TODO_API_BASE}/core${q}`)
    if (res.ok) {
      const data = await res.json()
      weekCore.value = data.week || []
      monthCore.value = data.month || []
      yearCore.value = data.year || []
    }
  } catch { /* 静默，条带缺席不影响页面 */ }
}

watch(() => props.selectedDate, load)
defineExpose({ reload: load })
onMounted(load)
</script>

<template>
  <div class="core-bar">
    <div class="core-bar__groups">
      <div class="core-bar__group">
        <span class="core-bar__label core-bar__label--week"><Star class="ep-icon" /> 本周核心</span>
        <template v-if="weekCore.length">
          <button
            v-for="t in weekCore" :key="t.id"
            class="core-bar__chip"
            :class="{ 'core-bar__chip--done': t.status === 'completed' }"
            @click="emit('open-task', t)"
          >{{ t.title }}</button>
        </template>
        <span v-else class="core-bar__empty" title="打开任意任务详情，点「设为本周核心」即可">未设置（任务详情里设置）</span>
      </div>
      <div class="core-bar__group">
        <span class="core-bar__label core-bar__label--month"><Calendar class="ep-icon" /> 本月核心</span>
        <template v-if="monthCore.length">
          <button
            v-for="t in monthCore" :key="t.id"
            class="core-bar__chip core-bar__chip--month"
            :class="{ 'core-bar__chip--done': t.status === 'completed' }"
            @click="emit('open-task', t)"
          >{{ t.title }}</button>
        </template>
        <span v-else class="core-bar__empty" title="打开任意任务详情，点「设为本月核心」即可">未设置（任务详情里设置）</span>
      </div>
      <div class="core-bar__group">
        <span class="core-bar__label core-bar__label--year"><Trophy class="ep-icon" /> 年度目标</span>
        <template v-if="yearCore.length">
          <button
            v-for="t in yearCore" :key="t.id"
            class="core-bar__chip core-bar__chip--year"
            :class="{ 'core-bar__chip--done': t.status === 'completed' }"
            @click="emit('open-task', t)"
          >{{ t.title }}</button>
        </template>
        <span v-else class="core-bar__empty" title="打开任意任务详情，点「设为年度目标」即可">未设置（任务详情里设置）</span>
      </div>
    </div>
    <button
      class="core-bar__review"
      :disabled="!weekCore.length && !monthCore.length && !yearCore.length"
      title="AI 对照本期实际记录，分析核心任务的推进对齐情况"
      @click="emit('review')"
    >
      <Aim class="ep-icon" /> 对齐检查
    </button>
  </div>
</template>

<style scoped lang="scss">
.core-bar {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  padding: $spacing-sm $spacing-md;
  margin-bottom: $spacing-md;
  @include glass-card;
  flex-wrap: wrap;

  &__groups {
    display: flex;
    align-items: center;
    gap: $spacing-lg;
    flex: 1;
    flex-wrap: wrap;
    min-width: 0;
  }

  &__group {
    display: flex;
    align-items: center;
    gap: $spacing-xs;
    flex-wrap: wrap;
    min-width: 0;
  }

  &__label {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: $font-size-xs;
    font-weight: 600;
    white-space: nowrap;

    &--week { color: #F97316; }
    &--month { color: #3B82F6; }
    &--year { color: #8B5CF6; }
  }

  &__chip {
    max-width: 220px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding: 3px 10px;
    border-radius: 99px;
    border: 1px solid rgba(#F97316, 0.35);
    background: rgba(#F97316, 0.08);
    color: #C2410C;
    font-size: $font-size-xs;
    cursor: pointer;
    transition: all 0.15s;

    &:hover { background: rgba(#F97316, 0.16); transform: translateY(-1px); }

    &--month {
      border-color: rgba(#3B82F6, 0.35);
      background: rgba(#3B82F6, 0.08);
      color: #1D4ED8;
      &:hover { background: rgba(#3B82F6, 0.16); }
    }

    &--year {
      border-color: rgba(#8B5CF6, 0.35);
      background: rgba(#8B5CF6, 0.08);
      color: #6D28D9;
      &:hover { background: rgba(#8B5CF6, 0.16); }
    }

    &--done { opacity: 0.55; text-decoration: line-through; }
  }

  &__empty { font-size: $font-size-xs; color: $text-muted; }

  &__review {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 14px;
    border-radius: 99px;
    border: 1px solid $primary-color;
    background: rgba($primary-color, 0.08);
    color: $primary-color;
    font-size: $font-size-xs;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.15s;

    &:hover:not(:disabled) { background: rgba($primary-color, 0.16); }
    &:disabled { opacity: 0.45; cursor: not-allowed; }
  }
}

@media (max-width: $breakpoint-sm) {
  .core-bar { padding: $spacing-sm; }
  .core-bar__chip { max-width: 140px; }
}
</style>
