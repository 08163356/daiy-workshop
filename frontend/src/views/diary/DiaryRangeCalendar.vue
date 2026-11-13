<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  start: string
  end: string
  dates: string[]
  selection?: 'range' | 'day'
}>(), {
  selection: 'range',
})

const emit = defineEmits<{
  change: [start: string, end: string]
  pick: [iso: string]
}>()

const pad = (n: number) => String(n).padStart(2, '0')
const toIso = (y: number, m: number, d: number) => `${y}-${pad(m)}-${pad(d)}`

const now = new Date()
const todayIso = toIso(now.getFullYear(), now.getMonth() + 1, now.getDate())
const viewYear = ref(now.getFullYear())
const viewMonth = ref(now.getMonth() + 1)
const pendingStart = ref('')
const viewPinned = ref(false)

const dateSet = computed(() => new Set(props.dates))

const yearOptions = computed(() => {
  const set = new Set<number>([viewYear.value, now.getFullYear()])
  for (const value of props.dates) {
    const year = Number(value.slice(0, 4))
    if (year) set.add(year)
  }
  return [...set].sort((a, b) => b - a)
})

watch(() => props.dates, (list) => {
  if (viewPinned.value || props.start || !list.length) return
  viewYear.value = Number(list[0].slice(0, 4))
  viewMonth.value = Number(list[0].slice(5, 7))
  viewPinned.value = true
}, { immediate: true })

watch(() => props.start, (value) => {
  if (!value || pendingStart.value) return
  viewYear.value = Number(value.slice(0, 4))
  viewMonth.value = Number(value.slice(5, 7))
  viewPinned.value = true
}, { immediate: true })

const cells = computed(() => {
  const year = viewYear.value
  const month = viewMonth.value
  const firstDow = (new Date(year, month - 1, 1).getDay() + 6) % 7
  const days = new Date(year, month, 0).getDate()
  const prev = new Date(year, month - 1, 0)
  const prevYear = prev.getFullYear()
  const prevMonth = prev.getMonth() + 1
  const prevDays = prev.getDate()
  const next = new Date(year, month, 1)
  const nextYear = next.getFullYear()
  const nextMonth = next.getMonth() + 1
  const out: { iso: string; day: number; inMonth: boolean }[] = []

  for (let i = 0; i < firstDow; i++) {
    const day = prevDays - firstDow + 1 + i
    out.push({ iso: toIso(prevYear, prevMonth, day), day, inMonth: false })
  }
  for (let day = 1; day <= days; day++) {
    out.push({ iso: toIso(year, month, day), day, inMonth: true })
  }
  let extra = 1
  while (out.length % 7 !== 0) {
    out.push({ iso: toIso(nextYear, nextMonth, extra), day: extra, inMonth: false })
    extra++
  }
  return out
})

const rangeStart = computed(() => pendingStart.value || props.start)
const rangeEnd = computed(() => (pendingStart.value ? '' : props.end))

const summary = computed(() => {
  if (pendingStart.value) return `开始 ${pendingStart.value}，再点一天作为结束`
  if (props.start && props.end && props.start !== props.end) return `${props.start} 至 ${props.end}`
  if (props.start) return props.start
  return '未选择时间，显示全部日记'
})

const between = (iso: string) => {
  if (!rangeStart.value || !rangeEnd.value) return false
  const lo = rangeStart.value < rangeEnd.value ? rangeStart.value : rangeEnd.value
  const hi = rangeStart.value < rangeEnd.value ? rangeEnd.value : rangeStart.value
  return iso > lo && iso < hi
}

const isEdge = (iso: string) => iso === rangeStart.value || (!!rangeEnd.value && iso === rangeEnd.value)

const shiftMonth = (delta: number) => {
  const cursor = new Date(viewYear.value, viewMonth.value - 1 + delta, 1)
  viewYear.value = cursor.getFullYear()
  viewMonth.value = cursor.getMonth() + 1
  viewPinned.value = true
}

const pick = (cell: { iso: string; inMonth: boolean }) => {
  viewPinned.value = true
  if (!cell.inMonth) {
    viewYear.value = Number(cell.iso.slice(0, 4))
    viewMonth.value = Number(cell.iso.slice(5, 7))
  }
  if (props.selection === 'day') {
    if (dateSet.value.has(cell.iso)) emit('pick', cell.iso)
    return
  }
  if (!pendingStart.value) {
    pendingStart.value = cell.iso
    return
  }
  let start = pendingStart.value
  let end = cell.iso
  if (end < start) [start, end] = [end, start]
  pendingStart.value = ''
  emit('change', start, end)
}

const pickYear = () => {
  const year = viewYear.value
  pendingStart.value = ''
  emit('change', `${year}-01-01`, `${year}-12-31`)
}

const pickMonth = () => {
  const year = viewYear.value
  const month = viewMonth.value
  const last = new Date(year, month, 0).getDate()
  pendingStart.value = ''
  emit('change', toIso(year, month, 1), toIso(year, month, last))
}

const clearAll = () => {
  pendingStart.value = ''
  emit('change', '', '')
}
</script>

<template>
  <div class="cal">
    <div class="cal__nav">
      <button class="cal__arrow" type="button" aria-label="上个月" @click="shiftMonth(-1)">
        <ArrowLeft class="ep-icon" />
      </button>
      <select v-model.number="viewYear" class="cal__select" aria-label="年份" @change="viewPinned = true">
        <option v-for="year in yearOptions" :key="year" :value="year">{{ year }}年</option>
      </select>
      <select v-model.number="viewMonth" class="cal__select" aria-label="月份" @change="viewPinned = true">
        <option v-for="month in 12" :key="month" :value="month">{{ month }}月</option>
      </select>
      <button class="cal__arrow" type="button" aria-label="下个月" @click="shiftMonth(1)">
        <ArrowRight class="ep-icon" />
      </button>
    </div>

    <p v-if="selection !== 'day'" class="cal__summary">{{ summary }}</p>

    <div class="cal__week">
      <span v-for="label in ['一', '二', '三', '四', '五', '六', '日']" :key="label">{{ label }}</span>
    </div>
    <div class="cal__grid">
      <button
        v-for="cell in cells"
        :key="cell.iso"
        type="button"
        class="cal__day"
        :class="{
          'is-out': !cell.inMonth,
          'is-today': cell.iso === todayIso,
          'is-edge': isEdge(cell.iso),
          'in-range': between(cell.iso),
        }"
        :aria-label="dateSet.has(cell.iso) ? `${cell.iso} 有日记` : cell.iso"
        @click="pick(cell)"
      >
        <span>{{ cell.day }}</span>
        <i v-if="dateSet.has(cell.iso)" class="cal__dot" />
      </button>
    </div>

    <div v-if="selection !== 'day'" class="cal__actions">
      <button type="button" @click="pickYear">这一年</button>
      <button type="button" @click="pickMonth">这个月</button>
      <button v-if="start || end || pendingStart" type="button" @click="clearAll">清除</button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.cal {
  width: 336px;
  max-width: 100%;
  padding: $spacing-md;
  border: 1px solid $border-color;
  border-radius: $border-radius-md;
  background: rgba(255, 255, 255, 0.86);

  @media (max-width: $breakpoint-sm) {
    width: 100%;
  }

  &__nav {
    display: flex;
    align-items: center;
    gap: $spacing-xs;
  }

  &__arrow {
    width: 44px;
    height: 44px;
    border: none;
    border-radius: $border-radius-sm;
    background: transparent;
    color: $text-secondary;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;

    &:hover { background: rgba($primary-color, 0.08); color: $primary-color; }
  }

  &__select {
    flex: 1;
    min-width: 0;
    padding: 4px 6px;
    border: 1px solid $border-color;
    border-radius: $border-radius-sm;
    background: #fff;
    font-size: $font-size-sm;
  }

  &__summary {
    margin: $spacing-sm 0;
    font-size: $font-size-xs;
    color: $text-secondary;
    min-height: 1.4em;
  }

  &__week,
  &__grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
  }

  &__week span {
    text-align: center;
    font-size: $font-size-xs;
    color: $text-muted;
    padding-bottom: 4px;
  }

  &__day {
    position: relative;
    height: 44px;
    border: none;
    background: transparent;
    border-radius: 8px;
    font-size: $font-size-sm;
    color: $text-primary;
    cursor: pointer;

    &:hover { background: rgba($primary-color, 0.08); }
    &:focus-visible { outline: 2px solid $primary-color; outline-offset: 1px; }
    &.is-out { color: $text-muted; }
    &.is-today { box-shadow: inset 0 0 0 1px rgba($primary-color, 0.45); }
    &.in-range { background: rgba($primary-color, 0.12); border-radius: 0; }
    &.is-edge {
      background: $primary-color;
      color: #fff;
      border-radius: 8px;
    }
  }

  &__dot {
    position: absolute;
    left: 50%;
    bottom: 4px;
    width: 5px;
    height: 5px;
    margin-left: -2.5px;
    border-radius: 50%;
    background: $danger-color;
    box-shadow: 0 0 0 1px #fff;
  }

  &__actions {
    display: flex;
    gap: $spacing-sm;
    margin-top: $spacing-sm;

    button {
      border: none;
      background: rgba($primary-color, 0.08);
      color: $primary-color;
      min-height: 44px;
      border-radius: $border-radius-sm;
      padding: 0 12px;
      font-size: $font-size-sm;
      cursor: pointer;

      &:hover { background: rgba($primary-color, 0.16); }
      &:focus-visible { outline: 2px solid $primary-color; outline-offset: 1px; }
    }
  }

}

@media (prefers-reduced-motion: reduce) {
  .cal__day { transition: none; }
}
</style>
