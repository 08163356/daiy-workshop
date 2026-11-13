<script setup lang="ts">
/**
 * 工具调用卡片：头部 = 图标 + 工具名 + 参数摘要（截断），点击展开结果摘要
 * 运行中带脉冲动画；失败红边
 */
import { computed, ref } from 'vue'

const props = defineProps<{
  name: string
  args?: Record<string, any>
  summary?: string
  error?: boolean
  running?: boolean
}>()

const emit = defineEmits<{
  'open-record': [payload: { type: 'todo' | 'diary'; id: number }]
}>()

const expanded = ref(false)

const linkedSummary = computed(() => {
  const safe = (props.summary || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  return safe.replace(
    /\[([^\]]+)\]\((todo|diary):(\d+)\)/g,
    '<a href="$2:$3" class="record-link">$1</a>',
  )
})

function openRecord(event: MouseEvent) {
  const anchor = (event.target as HTMLElement).closest('a')
  const href = anchor?.getAttribute('href') || ''
  const match = href.match(/^(todo|diary):(\d+)$/)
  if (!match) return
  event.preventDefault()
  emit('open-record', { type: match[1] as 'todo' | 'diary', id: Number(match[2]) })
}

const TOOL_LABELS: Record<string, string> = {
  query_todos: '查询待办',
  query_diaries: '查询日记',
  query_notes: '查询笔记',
  query_wellbeing: '查询心力记录',
  query_investments: '查询投资记录',
  get_user_profile: '读取用户画像',
  get_period_summary: '读取本期记录',
  search_knowledge: '检索知识库',
  search_blog: '检索个人博客',
  search_interview: '检索面试材料',
  scan_todos: '待办体检',
  propose_schedule: '生成排期建议',
  save_knowledge: '收入知识库',
  apply_schedule: '写入排期',
  search_conversations: '搜索历史对话',
}

const label = computed(() => TOOL_LABELS[props.name] || props.name)

const argsSummary = computed(() => {
  if (!props.args || !Object.keys(props.args).length) return ''
  const text = Object.entries(props.args)
    .map(([k, v]) => `${k}=${v}`)
    .join(' ')
  return text.length > 60 ? text.slice(0, 60) + '…' : text
})
</script>

<template>
  <div class="tool-card" :class="{ 'tool-card--error': error, 'tool-card--running': running }">
    <button class="tool-card__head" @click="expanded = !expanded">
      <Wrench class="ep-icon tool-card__icon" />
      <span class="tool-card__name">{{ label }}</span>
      <span v-if="argsSummary" class="tool-card__args">{{ argsSummary }}</span>
      <span class="tool-card__status">
        <template v-if="running">调用中…</template>
        <template v-else-if="error">失败</template>
        <template v-else>完成</template>
      </span>
      <span class="tool-card__arrow">{{ expanded ? '▼' : '▶' }}</span>
    </button>
    <div v-if="expanded && summary" class="tool-card__result" @click="openRecord" v-html="linkedSummary"></div>
  </div>
</template>

<style scoped lang="scss">
.tool-card {
  margin-bottom: 6px;
  border: 1px solid $border-color;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.7);
  overflow: hidden;

  &--running {
    border-color: rgba(#3B82F6, 0.4);
    animation: tool-pulse 1.2s ease-in-out infinite;
  }

  @keyframes tool-pulse {
    50% { box-shadow: 0 0 0 3px rgba(#3B82F6, 0.08); }
  }

  &--error { border-color: rgba(#EF4444, 0.4); }

  &__head {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 10px;
    border: none;
    background: transparent;
    cursor: pointer;
    text-align: left;
  }

  &__icon { color: $text-muted; flex-shrink: 0; }

  &__name {
    font-size: 12px;
    font-weight: 600;
    color: $text-primary;
    white-space: nowrap;
  }

  &__args {
    flex: 1;
    min-width: 0;
    font-size: 11px;
    color: $text-muted;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__status {
    font-size: 10px;
    color: $text-muted;
    flex-shrink: 0;
  }

  &--running &__status { color: #3B82F6; }
  &--error &__status { color: #EF4444; }

  &__arrow { font-size: 9px; color: $text-muted; flex-shrink: 0; }

  &__result {
    padding: 8px 12px;
    border-top: 1px solid $border-color;
    font-size: 12px;
    line-height: 1.6;
    color: $text-secondary;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 240px;
    overflow-y: auto;
    background: rgba(0, 0, 0, 0.015);

    :deep(a) { color: $primary-color; cursor: pointer; }
  }
}
</style>
