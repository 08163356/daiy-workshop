<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { marked } from 'marked'
import { useWellbeingStore } from '@/stores/useWellbeingStore'

const store = useWellbeingStore()

const periodType = ref<'week' | 'month'>('week')
const selectedKey = ref<string>('')
const refreshing = ref(false)

const renderedHtml = computed(() => {
  if (!store.currentReport?.content) return ''
  return marked.parse(store.currentReport.content) as string
})

async function loadCurrent(force = false) {
  refreshing.value = force
  try {
    await store.fetchReport(periodType.value, selectedKey.value || undefined, force)
    if (!selectedKey.value && store.currentReport) {
      selectedKey.value = store.currentReport.period_key
    }
  } finally {
    refreshing.value = false
  }
}

async function loadHistory() {
  await store.fetchReportHistory(periodType.value)
}

async function switchPeriod(t: 'week' | 'month') {
  periodType.value = t
  selectedKey.value = ''
  await loadHistory()
  await loadCurrent()
}

async function selectHistoryKey(k: string) {
  selectedKey.value = k
  await loadCurrent()
}

onMounted(async () => {
  await loadHistory()
  await loadCurrent()
})
</script>

<template>
  <div class="wb-reports">
    <div class="wb-reports__head">
      <h2><Document class="ep-icon" /> AI 心力周/月报</h2>
      <div class="wb-reports__tabs">
        <button :class="{ active: periodType === 'week' }" @click="switchPeriod('week')">周报</button>
        <button :class="{ active: periodType === 'month' }" @click="switchPeriod('month')">月报</button>
      </div>
    </div>

    <div class="wb-reports__layout">
      <!-- 左侧：历史归档 -->
      <aside class="wb-reports__history">
        <div class="wb-reports__history-title">归档</div>
        <div v-if="store.reportHistory.length === 0" class="wb-empty-mini">暂无历史</div>
        <button
          v-for="r in store.reportHistory"
          :key="r.id"
          class="wb-reports__history-item"
          :class="{ active: r.period_key === selectedKey }"
          @click="selectHistoryKey(r.period_key)"
        >
          <div class="key">{{ r.period_key }}</div>
          <div class="meta"><Trophy class="ep-icon" />{{ r.achievement_count }} · 🙏{{ r.gratitude_count }}</div>
        </button>
      </aside>

      <!-- 右侧：报告主体 -->
      <main class="wb-reports__main">
        <div v-if="store.loading && !store.currentReport" class="wb-empty">加载中…</div>

        <template v-else-if="store.currentReport">
          <div class="wb-reports__header">
            <div>
              <div class="wb-reports__period">
                {{ store.currentReport.period_key }}
                <span class="dim">（{{ store.currentReport.period_start }} - {{ store.currentReport.period_end }}）</span>
              </div>
              <div class="wb-reports__counts">
                <Trophy class="ep-icon" /> {{ store.currentReport.achievement_count }} 条成就 ·
                🙏 {{ store.currentReport.gratitude_count }} 份感恩
              </div>
            </div>
            <button class="btn-ghost" :disabled="refreshing" @click="loadCurrent(true)">
              <Refresh v-if="!refreshing" class="ep-icon" /> {{ refreshing ? '生成中…' : '重新生成' }}
            </button>
          </div>

          <article class="wb-reports__article markdown-body" v-html="renderedHtml" />

          <div class="wb-reports__footer">
            <span class="dim">模型：{{ store.currentReport.model_used || '—' }}</span>
            <span class="dim">生成于 {{ new Date(store.currentReport.generated_at).toLocaleString() }}</span>
          </div>
        </template>

        <div v-else class="wb-empty">本期还没有报告，点击「重新生成」开始。</div>
      </main>
    </div>
  </div>
</template>

<style lang="scss" scoped>
$mint: #14B8A6;
$peach: #F97316;

.wb-reports {
  display: flex; flex-direction: column; gap: $spacing-md;
  &__head {
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;
    h2 { margin: 0; font-size: 22px; color: $text-primary; }
  }
  &__tabs button {
    padding: 6px 14px; border-radius: 999px; border: 1px solid $border-color;
    background: white; cursor: pointer; font-size: 13px; margin-left: 6px;
    &.active { background: linear-gradient(135deg, $mint, $peach); color: white; border-color: transparent; }
  }
  &__layout {
    display: grid; grid-template-columns: 220px 1fr; gap: $spacing-md;
    @media (max-width: $breakpoint-md) { grid-template-columns: 1fr; }
  }
  &__history {
    @include glass-card;
    padding: $spacing-md;
    display: flex; flex-direction: column; gap: 4px;
    max-height: 70vh; overflow-y: auto;
    &-title { font-size: 12px; color: $text-muted; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .5px; }
    &-item {
      text-align: left; padding: 8px 10px; border-radius: 8px;
      background: transparent; border: 1px solid transparent; cursor: pointer;
      transition: all .15s;
      .key { font-size: 13px; color: $text-primary; }
      .meta { font-size: 11px; color: $text-muted; }
      &:hover { background: rgba($mint, .06); }
      &.active { background: rgba($mint, .12); border-color: rgba($mint, .3); }
    }
  }
  &__main {
    @include glass-card;
    padding: $spacing-lg;
    min-height: 400px;
  }
  &__header {
    display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap;
    gap: $spacing-md; margin-bottom: $spacing-md;
    padding-bottom: $spacing-sm; border-bottom: 1px solid rgba($border-color, .5);
  }
  &__period { font-size: 18px; font-weight: 600; color: $text-primary; }
  &__counts { font-size: 13px; color: $text-secondary; margin-top: 4px; }
  &__article {
    color: $text-primary; line-height: 1.8;
    :deep(h3) { color: $mint; margin-top: $spacing-md; font-size: 16px; }
    :deep(p) { margin: 8px 0; }
    :deep(ul), :deep(ol) { padding-left: 24px; }
  }
  &__footer {
    margin-top: $spacing-md; padding-top: $spacing-sm;
    border-top: 1px dashed rgba($border-color, .4);
    display: flex; justify-content: space-between; font-size: 11px;
  }
}

.dim { color: $text-muted; }
.btn-ghost {
  padding: 8px 16px; border-radius: 8px; cursor: pointer;
  background: transparent; border: 1px solid $border-color; color: $text-secondary;
  font-size: 13px;
  &:hover { color: $mint; border-color: $mint; }
  &:disabled { opacity: .6; cursor: not-allowed; }
}
.wb-empty { padding: 40px; text-align: center; color: $text-muted; }
.wb-empty-mini { padding: 12px; text-align: center; color: $text-muted; font-size: 12px; }
</style>
