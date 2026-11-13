<script setup lang="ts">
/**
 * 技术进化史时间轴
 * - 横轴：周
 * - 纵轴：20 个技术维度
 * - 节点：红=问题 / 绿=亮点 / 同维度叠加显示
 * - hover 一行：高亮该维度所有节点
 */
import { ref, computed } from 'vue'
import { SKILL_DIMENSIONS, DIMENSION_GROUP, type SkillDimension } from '@/config/basketballSkills'
import type { SkillTimelineWeek } from '@/api/basketball'

const props = defineProps<{
  timeline: SkillTimelineWeek[]
}>()

const hovered = ref<string | null>(null)

const groupColors: Record<string, string> = {
  shooting: '#F97316',
  finishing: '#EAB308',
  defense: '#3B82F6',
  playmaking: '#A855F7',
  physical: '#DC2626',
  mind: '#10B981',
}

const cellLookup = computed(() => {
  // dim → week_key → {problem, highlight}
  const map: Record<string, Record<string, { problem: number; highlight: number }>> = {}
  for (const dim of SKILL_DIMENSIONS) {
    map[dim] = {}
  }
  for (const wk of props.timeline) {
    for (const p of wk.points) {
      if (!map[p.dim]) map[p.dim] = {}
      map[p.dim][wk.week_key] = { problem: p.problem, highlight: p.highlight }
    }
  }
  return map
})

function cellOf(dim: string, weekKey: string) {
  return cellLookup.value[dim]?.[weekKey] || { problem: 0, highlight: 0 }
}

function cellLevel(c: { problem: number; highlight: number }) {
  // 返回 'empty' | 'highlight' | 'problem' | 'mixed'
  if (!c.problem && !c.highlight) return 'empty'
  if (c.highlight && !c.problem) return 'highlight'
  if (c.problem && !c.highlight) return 'problem'
  return 'mixed'
}
</script>

<template>
  <div class="evo-timeline">
    <div v-if="!timeline.length" class="evo-timeline__empty">
      <span class="evo-timeline__empty-icon">📈</span>
      <p>还没有足够的复盘数据。</p>
      <p class="evo-timeline__empty-sub">写 3-5 篇复盘后，技术进化史会在这里浮现。</p>
    </div>
    <div v-else class="evo-timeline__grid">
      <!-- 表头：周 -->
      <div class="evo-timeline__header">
        <div class="evo-timeline__corner"></div>
        <div
          v-for="wk in timeline"
          :key="wk.week_key"
          class="evo-timeline__week-label"
          :title="`${wk.date_start} 至 ${wk.date_end}`"
        >
          {{ wk.week_key.replace(/^\d{4}-/, '') }}
        </div>
      </div>

      <!-- 每个维度行 -->
      <div
        v-for="dim in SKILL_DIMENSIONS"
        :key="dim"
        class="evo-timeline__row"
        :class="{ 'evo-timeline__row--hovered': hovered === dim }"
        @mouseenter="hovered = dim"
        @mouseleave="hovered = null"
      >
        <div
          class="evo-timeline__row-label"
          :style="{ color: groupColors[DIMENSION_GROUP[dim as SkillDimension]] }"
        >
          {{ dim }}
        </div>
        <div
          v-for="wk in timeline"
          :key="wk.week_key"
          class="evo-timeline__cell"
          :class="`evo-timeline__cell--${cellLevel(cellOf(dim, wk.week_key))}`"
          :title="`${dim} · ${wk.week_key}: 问题 ${cellOf(dim, wk.week_key).problem} | 亮点 ${cellOf(dim, wk.week_key).highlight}`"
        >
          <span v-if="cellOf(dim, wk.week_key).highlight" class="evo-timeline__cell-num">
            {{ cellOf(dim, wk.week_key).highlight }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.evo-timeline {
  background: white;
  border-radius: 12px;
  padding: 20px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  overflow-x: auto;

  &__empty {
    text-align: center;
    padding: 50px 20px;
    color: #64748B;

    &-icon {
      font-size: 48px;
      display: block;
      margin-bottom: 12px;
    }

    &-sub {
      color: #94A3B8;
      font-size: 13px;
      margin-top: 4px;
    }
  }

  &__grid {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: max-content;
  }

  &__header {
    display: flex;
    gap: 2px;
    padding-bottom: 6px;
    border-bottom: 1px solid #F1F5F9;
    margin-bottom: 4px;
  }

  &__corner {
    width: 80px;
    flex-shrink: 0;
  }

  &__week-label {
    width: 38px;
    flex-shrink: 0;
    font-size: 10px;
    color: #94A3B8;
    text-align: center;
    font-family: ui-monospace, monospace;
  }

  &__row {
    display: flex;
    gap: 2px;
    align-items: center;
    transition: background 0.2s;

    &--hovered {
      background: rgba(217, 119, 6, 0.04);
    }
  }

  &__row-label {
    width: 80px;
    flex-shrink: 0;
    font-size: 13px;
    font-weight: 500;
    padding: 6px 8px 6px 0;
    text-align: right;
  }

  &__cell {
    width: 38px;
    height: 28px;
    flex-shrink: 0;
    border-radius: 4px;
    background: #F8FAFC;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px;
    font-weight: 600;
    color: white;
    cursor: pointer;
    transition: transform 0.15s;

    &:hover { transform: scale(1.15); }

    &--empty {
      background: #F8FAFC;
      border: 1px dashed #E2E8F0;
    }

    &--highlight {
      background: linear-gradient(135deg, #16A34A, #15803D);
    }

    &--problem {
      background: linear-gradient(135deg, #DC2626, #B91C1C);
    }

    &--mixed {
      background: linear-gradient(135deg, #16A34A 50%, #DC2626 50%);
    }
  }

  &__cell-num {
    color: white;
    font-size: 10px;
  }
}
</style>
