<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useWellbeingStore } from '@/stores/useWellbeingStore'
import { wellbeingApi, type WellbeingEntry } from '@/api/wellbeing'
import { WELLBEING_API_BASE } from '@/config'
import DiaryRangeCalendar from '@/views/diary/DiaryRangeCalendar.vue'

const router = useRouter()
const store = useWellbeingStore()

const filterType = ref<'all' | 'achievement' | 'gratitude'>('all')
const filterCategory = ref('')
const filterMinIntensity = ref(0)
const keyword = ref('')
const startDate = ref('')
const endDate = ref('')
const dateOpen = ref(false)
const recordDates = ref<string[]>([])
const entries = ref<WellbeingEntry[]>([])
const total = ref(0)
const loading = ref(false)
const skip = ref(0)
const openMonths = ref<Record<string, boolean>>({})
const PAGE_SIZE = 20

const CATEGORIES = ['工作', '家庭', '健康', '关系', '学习', '其他']

const rangeLabel = computed(() => {
  if (startDate.value && endDate.value && startDate.value !== endDate.value) return `${startDate.value} 至 ${endDate.value}`
  return startDate.value || endDate.value || '选择日期'
})

async function load(reset = true) {
  loading.value = true
  if (reset) skip.value = 0
  try {
    const res = await wellbeingApi.listEntries({
      type: filterType.value === 'all' ? undefined : filterType.value,
      category: filterCategory.value || undefined,
      min_intensity: filterMinIntensity.value || undefined,
      keyword: keyword.value || undefined,
      start_date: startDate.value || undefined,
      end_date: endDate.value || undefined,
      skip: skip.value,
      limit: PAGE_SIZE,
    })
    entries.value = reset ? res.items : entries.value.concat(res.items)
    total.value = res.total
    skip.value = entries.value.length
  } finally {
    loading.value = false
  }
}

function onRangeChange(start: string, end: string) {
  startDate.value = start
  endDate.value = end
  dateOpen.value = false
  load(true)
}

watch([filterType, filterCategory, filterMinIntensity], () => load(true))

let kwTimer: any = null
watch(keyword, () => {
  if (kwTimer) clearTimeout(kwTimer)
  kwTimer = setTimeout(load, 300)
})

// 按月分组
const grouped = computed(() => {
  const m: Record<string, typeof store.entries> = {}
  for (const e of entries.value) {
    const k = e.occurred_at.slice(0, 7)
    if (!m[k]) m[k] = []
    m[k].push(e)
  }
  return Object.entries(m).sort((a, b) => b[0].localeCompare(a[0]))
})

async function remove(id: number) {
  if (!confirm('确定删除这条记录？')) return
  await store.deleteEntry(id)
  entries.value = entries.value.filter(item => item.id !== id)
  total.value = Math.max(0, total.value - 1)
  skip.value = entries.value.length
}

function toggleMonth(month: string) {
  openMonths.value = { ...openMonths.value, [month]: !openMonths.value[month] }
}

function jumpSource(e: any) {
  if (e.source_type === 'diary' && e.source_id) {
    router.push(`/diary/${e.source_id}`)
  }
}

onMounted(async () => {
  load(true)
  try {
    const res = await fetch(`${WELLBEING_API_BASE}/dates`)
    if (res.ok) recordDates.value = ((await res.json()).dates || []).map((value: string) => String(value).slice(0, 10))
  } catch { /* 日期标记失败不影响列表 */ }
})
</script>

<template>
  <div class="wb-list">
    <!-- 筛选条 -->
    <div class="wb-filter">
      <div class="wb-filter__tabs">
        <button
          v-for="t in (['all','achievement','gratitude'] as const)"
          :key="t"
          :class="{ active: filterType === t }"
          @click="filterType = t"
        >
          <Trophy v-if="t === 'achievement'" class="ep-icon" /> {{ t === 'all' ? '全部' : t === 'achievement' ? '成就' : '🙏 感恩' }}
        </button>
      </div>
      <div class="wb-filter__row">
        <select v-model="filterCategory">
          <option value="">全部分类</option>
          <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
        </select>
        <select v-model.number="filterMinIntensity">
          <option :value="0">全部强度</option>
          <option v-for="n in 5" :key="n" :value="n">≥ {{ n }} 星</option>
        </select>
        <input v-model="keyword" type="text" placeholder="搜索关键词…" />
        <div class="wb-filter__date">
          <button type="button" @click="dateOpen = !dateOpen">{{ rangeLabel }}</button>
          <div v-if="dateOpen" class="wb-filter__panel">
            <DiaryRangeCalendar
              :start="startDate"
              :end="endDate"
              :dates="recordDates"
              @change="onRangeChange"
            />
          </div>
        </div>
        <span class="wb-filter__total">共 {{ total }} 条，已显示 {{ entries.length }} 条</span>
      </div>
    </div>

    <div v-if="loading && entries.length === 0" class="wb-empty">加载中…</div>
    <div v-else-if="entries.length === 0" class="wb-empty">
      🌱 这里会留下你所有值得被记住的瞬间。<br>
      回到总览页快速记一条吧。
    </div>

    <div v-else class="wb-groups">
      <div v-for="[month, items] in grouped" :key="month" class="wb-group">
        <button class="wb-group__head" type="button" @click="toggleMonth(month)">
          <h3>{{ openMonths[month] ? '▾' : '▸' }} {{ month }}</h3>
          <span>{{ items.length }} 条</span>
        </button>
        <div v-show="openMonths[month]" class="wb-group__cards">
          <div
            v-for="e in items"
            :key="e.id"
            class="wb-card"
            :class="`wb-card--${e.type}`"
          >
            <div class="wb-card__head">
              <span class="wb-card__type">
                <Trophy v-if="e.type === 'achievement'" class="ep-icon" /> {{ e.type === 'achievement' ? '成就' : '🙏 感恩' }}
              </span>
              <span class="wb-card__date">{{ e.occurred_at }}</span>
            </div>
            <div class="wb-card__content">{{ e.content }}</div>
            <!-- 原文片段（AI提取的条目才有） -->
            <div v-if="e.source_excerpt" class="wb-card__excerpt">
              「{{ e.source_excerpt }}」
            </div>
            <!-- AI 识别理由（候选采纳时保留） -->
            <div v-if="e.ai_reason" class="wb-card__reason">
              💭 {{ e.ai_reason }}
            </div>
        <div class="wb-card__meta">
     <span v-if="e.category" class="wb-tag">{{ e.category }}</span>
     <span class="wb-stars">{{ '★'.repeat(e.intensity) }}<span class="dim">{{ '★'.repeat(5 - e.intensity) }}</span></span>
    <span
    v-if="e.source_type === 'diary' && e.source_id"
           class="wb-source wb-source--link"
   @click="jumpSource(e)"
       ><EditPen class="ep-icon" /> 查看原日记</span>
       <span v-else-if="e.source_type === 'note' && e.source_id" class="wb-source"><Reading class="ep-icon" /> 来自笔记</span>
        <button class="wb-del" @click="remove(e.id)" title="删除"><Close class="ep-icon" /></button>
  </div>
          </div>
        </div>
      </div>
      <button v-if="entries.length < total" class="wb-more" type="button" :disabled="loading" @click="load(false)">
        {{ loading ? '加载中…' : `加载更多（剩余 ${total - entries.length} 条）` }}
      </button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
$mint: #14B8A6;
$peach: #F97316;

.wb-list { display: flex; flex-direction: column; gap: $spacing-lg; }

.wb-filter {
  @include glass-card;
  padding: $spacing-md;
  display: flex; flex-direction: column; gap: $spacing-sm;
  &__tabs { display: flex; gap: 6px; flex-wrap: wrap; }
  &__tabs button {
    padding: 6px 14px; border: 1px solid $border-color; background: white;
    border-radius: 999px; cursor: pointer; font-size: 13px;
    &.active { background: linear-gradient(135deg, $mint, $peach); color: white; border-color: transparent; }
  }
  &__row {
    display: flex; gap: $spacing-sm; align-items: center; flex-wrap: wrap;
    select, input {
      padding: 7px 10px; border: 1px solid $border-color; border-radius: 8px;
      background: white; font-size: 13px; outline: none;
      &:focus { border-color: $mint; }
    }
    input { flex: 1; min-width: 120px; }
  }
  &__total { color: $text-muted; font-size: 12px; }
  &__date { position: relative; }
  &__date > button {
    min-height: 36px;
    padding: 0 12px;
    border: 1px solid $border-color;
    border-radius: 8px;
    background: white;
    cursor: pointer;
  }
  &__panel {
    position: absolute;
    z-index: 30;
    top: calc(100% + 8px);
    right: 0;
    box-shadow: $shadow-lg;
  }
}

.wb-more {
  min-height: 44px;
  border: 1px solid rgba($mint, 0.4);
  background: rgba($mint, 0.06);
  color: $mint;
  border-radius: 8px;
  cursor: pointer;
}

.wb-empty { @include glass-card; padding: 40px; text-align: center; color: $text-muted; }

.wb-groups { display: flex; flex-direction: column; gap: $spacing-lg; }
.wb-group {
  &__head {
    display: flex; align-items: baseline; gap: $spacing-md;
    margin-bottom: $spacing-sm;
    width: 100%;
    border: none;
    background: transparent;
    cursor: pointer;
    text-align: left;
    padding: 8px 0;
    h3 { font-size: $font-size-md; color: $text-primary; margin: 0; }
    span { color: $text-muted; font-size: 12px; }
  }
  &__cards {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: $spacing-md;
  }
}

.wb-card {
  @include glass-card;
  padding: $spacing-md;
  display: flex; flex-direction: column; gap: 8px;
  border-left: 3px solid transparent;
  transition: transform .2s, box-shadow .2s;
  &:hover { transform: translateY(-2px); box-shadow: $shadow-lg; }
  &--achievement { border-left-color: $mint; }
  &--gratitude { border-left-color: $peach; }

  &__head {
    display: flex; justify-content: space-between; font-size: 12px; color: $text-muted;
  }
  &__type { font-weight: 600; color: $text-primary; }
  &__content { font-size: $font-size-sm; color: $text-primary; line-height: 1.6; }
  &__meta {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
    font-size: 11px; color: $text-muted;
  }
}

.wb-tag {
  padding: 2px 8px; border-radius: 999px;
  background: rgba($mint, .12); color: $mint;
}
.wb-stars {
  color: #f59e0b;
  .dim { color: #e5e7eb; }
}
.wb-source { color: #6366f1; font-size: 12px; }
.wb-source--link { cursor: pointer; &:hover { text-decoration: underline; } }
.wb-card__excerpt {
  font-size: 12px;
  color: #64748b;
  background: rgba(99, 102, 241, 0.04);
  border-left: 2px solid #6366f1;
  padding: 4px 8px;
  margin: 6px 0;
  border-radius: 4px;
  font-style: italic;
}
.wb-card__reason {
  font-size: 12px;
  color: #6366f1;
  margin: 4px 0;
}
.wb-del {
  margin-left: auto; background: transparent; border: none; color: $text-muted;
  cursor: pointer; font-size: 14px;
  &:hover { color: $danger-color; }
}
</style>
