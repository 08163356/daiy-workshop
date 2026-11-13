<script setup lang="ts">
import { ref, onMounted, computed, watch, nextTick } from 'vue'
import { TODO_API_BASE, TIME_API_BASE } from '@/config'
import { Doughnut, Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  ArcElement,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(ArcElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

const loading = ref(false)
const summaryLoading = ref(false)
const stats = ref<any>(null)
const delayedItems = computed<Array<{ id: number; title: string; days_waiting: number }>>(
  () => Array.isArray(stats.value?.top_delayed) ? stats.value.top_delayed : [],
)
const summaryMarkdown = ref('')
const activeRange = ref('today')

const formatDate = (d: Date) => d.toISOString().split('T')[0]

// 动态计算 ranges，每次取值都用最新时间
const ranges = computed<Record<string, { label: string; start: Date; end: Date }>>(() => {
  const now = new Date()
  return {
    today: { label: '今日', start: new Date(now.getFullYear(), now.getMonth(), now.getDate()), end: now },
    week: {
      label: '本周',
      start: new Date(now.getFullYear(), now.getMonth(), now.getDate() - now.getDay() + 1),
      end: now,
    },
    month: {
      label: '本月',
      start: new Date(now.getFullYear(), now.getMonth(), 1),
      end: now,
    },
    last_week: {
      label: '上周',
      start: new Date(now.getFullYear(), now.getMonth(), now.getDate() - now.getDay() - 6),
      end: new Date(now.getFullYear(), now.getMonth(), now.getDate() - now.getDay()),
    },
    last_month: {
      label: '上月',
      start: new Date(now.getFullYear(), now.getMonth() - 1, 1),
      end: new Date(now.getFullYear(), now.getMonth(), 0),
    },
  }
})

const currentRange = computed(() => ranges.value[activeRange.value])

const quadrantLabels: Record<number, { label: string; color: string }> = {
  1: { label: '重要紧急', color: '#EF4444' },
  2: { label: '重要不紧急', color: '#3B82F6' },
  3: { label: '紧急不重要', color: '#F59E0B' },
  4: { label: '不重要不紧急', color: '#94A3B8' },
}

const categoryLabels: Record<string, string> = {
  work: '工作', learning: '学习', life: '生活',
  health: '健康', social: '社交', finance: '财务', creative: '创意',
}

const fetchStats = async () => {
  loading.value = true
  summaryMarkdown.value = ''
  try {
    const range = currentRange.value
    const res = await fetch(
      `${TODO_API_BASE}/review?start_date=${formatDate(range.start)}&end_date=${formatDate(range.end)}`
    )
    if (!res.ok) throw new Error('加载失败')
    stats.value = await res.json()
    nextTick(() => renderCharts())
  } catch (e) {
    stats.value = null
  } finally {
    loading.value = false
  }
}

const generateSummary = async () => {
  summaryLoading.value = true
  try {
    const range = currentRange.value
    const res = await fetch(`${TODO_API_BASE}/review/summary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_date: formatDate(range.start),
        end_date: formatDate(range.end),
      }),
    })
    if (!res.ok) throw new Error('生成失败')
    const data = await res.json()
    summaryMarkdown.value = data.markdown || ''
  } catch (e: any) {
    alert(e.message || '生成失败')
  } finally {
    summaryLoading.value = false
  }
}

const renderCharts = () => {
  // 图表通过 computed 和 SVG 直接渲染
}

// 四象限柱状图最大值，用于百分比计算
const maxQuadrantCount = computed(() => {
  if (!stats.value?.quadrant_stats) return 1
  let max = 1
  for (const q of [1, 2, 3, 4]) {
    const s = stats.value.quadrant_stats[q]
    if (s) {
      max = Math.max(max, s.created || 0, s.completed || 0)
    }
  }
  return max
})

// 趋势图最大值
const maxDailyCount = computed(() => {
  if (!stats.value?.daily_completion) return 1
  const vals = Object.values(stats.value.daily_completion) as number[]
  return Math.max(1, ...vals)
})

// ==================== 时间分析 ====================
const timeLoading = ref(false)
const timeAnalysis = ref<any>(null)

// 颜色映射 - 每个分类使用高区分度颜色（色相间隔 ≥ 30°）
// 后端已将 status:工作→work、status:学习→learning 等合并，这里只需标准分类
const categoryColorMap: Record<string, string> = {
  work: '#2563EB',         // 蓝色
  learning: '#7C3AED',     // 紫色
  life: '#059669',         // 绿色
  health: '#DC2626',       // 红色
  social: '#DB2777',       // 粉红
  finance: '#CA8A04',      // 金色
  creative: '#EA580C',     // 橙色
  uncategorized: '#6B7280',// 灰色
  // 保留 status:xxx 作为后备（自定义状态可能未映射）
  'status:通勤': '#D97706',
  'status:运动': '#16A34A',
  'status:吃饭': '#E11D48',
  'status:睡觉': '#4F46E5',
  'status:放空': '#9CA3AF',
  'status:娱乐': '#9333EA',
  'status:聚会': '#F472B6',
  'status:学习': '#0891B2',
  'status:工作': '#0284C7',
  'status:家务': '#78716C',
}

const categoryNameMap: Record<string, string> = {
  work: '💻 工作', learning: '📖 学习', life: '🏠 生活',
  health: '🏃 健康', social: '🍻 社交', finance: '💰 财务',
  creative: '🎮 创意', uncategorized: '未分类',
  // 后备
  'status:通勤': '🚌 通勤',
  'status:运动': '🏃 运动',
  'status:吃饭': '🍚 吃饭',
  'status:睡觉': '😴 睡觉',
  'status:放空': '☁️ 放空',
  'status:娱乐': '🎮 娱乐',
  'status:聚会': '🍻 聚会',
  'status:学习': '📖 学习',
  'status:工作': '💻 工作',
  'status:家务': '🧹 家务',
}

// 通用名称获取函数，处理未映射的 status:xxx 格式
const getCategoryName = (cat: string): string => {
  if (categoryNameMap[cat]) return categoryNameMap[cat]
  if (cat.startsWith('status:')) return cat.replace('status:', '')
  return cat
}

const formatDuration = (seconds: number): string => {
  if (!seconds || seconds <= 0) return '0m'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

const fetchTimeAnalysis = async () => {
  timeLoading.value = true
  try {
    const range = currentRange.value
    const params = new URLSearchParams()
    params.set('start_date', formatDate(range.start))
    params.set('end_date', formatDate(range.end))
    // 计算天数
    const days = Math.ceil((range.end.getTime() - range.start.getTime()) / (1000 * 60 * 60 * 24)) + 1
    params.set('days', String(Math.max(days, 7)))
    const res = await fetch(`${TIME_API_BASE}/analysis?${params}`)
    if (!res.ok) throw new Error('加载失败')
    timeAnalysis.value = await res.json()
  } catch {
    timeAnalysis.value = null
  } finally {
    timeLoading.value = false
  }
}

// ==================== 统一日期筛选（同时控制饼图和时间轴） ====================
const categoryFilterMode = ref<'all' | 'day'>('day')  // 默认按天显示当天
const selectedDay = ref<string>('')  // YYYY-MM-DD

// 可选的日期列表（从 daily_stats 中提取）
const availableDays = computed(() => {
  if (!timeAnalysis.value?.daily_stats?.length) return []
  return timeAnalysis.value.daily_stats
    .filter((d: any) => d.total_seconds > 0)
    .map((d: any) => d.date)
})

// 今天的日期字符串
const todayStr = computed(() => new Date().toISOString().split('T')[0])

// 当数据加载完成后，默认选中今天（或最后一天）
watch(() => timeAnalysis.value, (newVal) => {
  if (newVal && categoryFilterMode.value === 'day' && !selectedDay.value) {
    const days = availableDays.value
    if (days.includes(todayStr.value)) {
      selectedDay.value = todayStr.value
    } else if (days.length > 0) {
      selectedDay.value = days[days.length - 1]
    }
  }
}, { immediate: true })

// 当切换到按天模式时，默认选中今天
watch(categoryFilterMode, (mode) => {
  if (mode === 'day' && !selectedDay.value && availableDays.value.length) {
    const days = availableDays.value
    if (days.includes(todayStr.value)) {
      selectedDay.value = todayStr.value
    } else {
      selectedDay.value = days[days.length - 1]
    }
  }
})

// 当选中的日期变化时，重新拉取时间轴数据
const timelineLogs = ref<any[]>([])
const timelineDate = ref<string>('')  // 当前时间轴显示的日期

watch(selectedDay, async (newDay) => {
  if (!newDay || categoryFilterMode.value !== 'day') return
  await fetchDayTimeline(newDay)
})

watch(categoryFilterMode, async (mode) => {
  if (mode === 'all') {
    // 全部模式：使用今天的数据
    timelineLogs.value = timeAnalysis.value?.today_logs || []
    timelineDate.value = todayStr.value
  } else if (selectedDay.value) {
    await fetchDayTimeline(selectedDay.value)
  }
})

// 按天获取时间轴数据
const fetchDayTimeline = async (day: string) => {
  // 如果是今天，直接用已有数据
  if (day === todayStr.value && timeAnalysis.value?.today_logs?.length) {
    timelineLogs.value = timeAnalysis.value.today_logs
    timelineDate.value = day
    return
  }
  // 否则调用接口获取指定日期的时间轴
  try {
    const params = new URLSearchParams()
    params.set('start_date', day)
    params.set('end_date', day)
    params.set('days', '1')
    params.set('target_date', day)
    const res = await fetch(`${TIME_API_BASE}/analysis?${params}`)
    if (res.ok) {
      const data = await res.json()
      timelineLogs.value = data.today_logs || []
      timelineDate.value = day
    }
  } catch {
    timelineLogs.value = []
  }
}

// 当前时间轴使用的日志（统一入口）
const currentTimelineLogs = computed(() => {
  if (categoryFilterMode.value === 'day' && timelineLogs.value.length) {
    return timelineLogs.value
  }
  return timeAnalysis.value?.today_logs || []
})

// 筛选后的分类统计数据
const filteredCategoryStats = computed(() => {
  if (!timeAnalysis.value) return []

  // 整体模式：直接用 category_stats
  if (categoryFilterMode.value === 'all') {
    return timeAnalysis.value.category_stats || []
  }

  // 按天模式：从 daily_stats 中提取选中日期的数据
  if (!selectedDay.value || !timeAnalysis.value.daily_stats?.length) return []

  const dayData = timeAnalysis.value.daily_stats.find((d: any) => d.date === selectedDay.value)
  if (!dayData || !dayData.categories) return []

  return Object.entries(dayData.categories)
    .filter(([, seconds]) => (seconds as number) > 0)
    .map(([category, total_seconds]) => ({ category, total_seconds }))
    .sort((a, b) => (b.total_seconds as number) - (a.total_seconds as number))
})

// ==================== 统计卡片数据（跟随日期切换） ====================
const currentStatsLabel = computed(() => {
  if (categoryFilterMode.value === 'day' && selectedDay.value) {
    return selectedDay.value === todayStr.value ? '今日统计' : `${selectedDay.value.slice(5)} 统计`
  }
  return '汇总统计'
})

const currentStats = computed(() => {
  if (!timeAnalysis.value) return { totalSeconds: 0, totalTasks: 0, categoryCount: 0, logCount: 0 }

  if (categoryFilterMode.value === 'all') {
    // 全部模式：使用整体统计
    return {
      totalSeconds: timeAnalysis.value.total_seconds || 0,
      totalTasks: timeAnalysis.value.total_tasks || 0,
      categoryCount: timeAnalysis.value.category_stats?.length || 0,
      logCount: timeAnalysis.value.today_logs?.length || 0,
    }
  }

  // 按天模式：从 daily_stats 中提取选中日期的数据
  if (!selectedDay.value || !timeAnalysis.value.daily_stats?.length) {
    return { totalSeconds: 0, totalTasks: 0, categoryCount: 0, logCount: 0 }
  }

  const dayData = timeAnalysis.value.daily_stats.find((d: any) => d.date === selectedDay.value)
  if (!dayData) return { totalSeconds: 0, totalTasks: 0, categoryCount: 0, logCount: 0 }

  const categories = dayData.categories || {}
  const categoryCount = Object.keys(categories).filter((k: string) => categories[k] > 0).length

  return {
    totalSeconds: dayData.total_seconds || 0,
    totalTasks: currentTimelineLogs.value.filter((l: any) => l.todo_id).length,
    categoryCount,
    logCount: currentTimelineLogs.value.length,
  }
})

// 环形图数据
const doughnutData = computed(() => {
  const stats = filteredCategoryStats.value as Array<{ category: string; total_seconds: number }>
  if (!stats.length) {
    return { labels: [], datasets: [{ data: [], backgroundColor: [] }] }
  }
  return {
    labels: stats.map(s => getCategoryName(s.category)),
    datasets: [{
      data: stats.map(s => Math.round(s.total_seconds / 60)),
      backgroundColor: stats.map(s => categoryColorMap[s.category] || '#94A3B8'),
      borderWidth: 2,
      borderColor: '#ffffff',
    }],
  }
})

const doughnutOptions = {
  responsive: true,
  maintainAspectRatio: false,
  cutout: '65%',
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (ctx: any) => `${ctx.label}: ${ctx.raw}分钟`,
      },
    },
  },
}

// 堆叠柱状图数据
const stackedBarData = computed(() => {
  if (!timeAnalysis.value?.daily_stats?.length) {
    return { labels: [], datasets: [] }
  }
  const days = timeAnalysis.value.daily_stats as Array<{ date: string; categories: Record<string, number> }>

  // 收集所有出现过的分类
  const allCategories = new Set<string>()
  days.forEach(d => Object.keys(d.categories).forEach(c => allCategories.add(c)))

  const datasets = Array.from(allCategories).map(cat => ({
    label: getCategoryName(cat),
    data: days.map(d => Math.round((d.categories[cat] || 0) / 60)),
    backgroundColor: categoryColorMap[cat] || '#94A3B8',
    borderRadius: 3,
  }))

  return {
    labels: days.map(d => d.date.slice(5)), // MM-DD
    datasets,
  }
})

const stackedBarOptions = {
  responsive: true,
  maintainAspectRatio: false,
  scales: {
    x: { stacked: true, grid: { display: false } },
    y: {
      stacked: true,
      grid: { color: 'rgba(0,0,0,0.04)' },
      ticks: { callback: (v: any) => `${v}m` },
    },
  },
  plugins: {
    legend: {
      position: 'bottom' as const,
      labels: { boxWidth: 12, padding: 12, font: { size: 11 } },
    },
    tooltip: {
      callbacks: {
        label: (ctx: any) => `${ctx.dataset.label}: ${ctx.raw}分钟`,
      },
    },
  },
}

// 时间轴相关
const timelineHours = computed(() => {
  if (!currentTimelineLogs.value?.length) return { start: 8, end: 22 }
  const logs = currentTimelineLogs.value
  let minH = 24, maxH = 0
  for (const log of logs) {
    const startH = new Date(log.start_time).getHours()
    const endH = log.end_time ? new Date(log.end_time).getHours() + 1 : new Date().getHours() + 1
    minH = Math.min(minH, startH)
    maxH = Math.max(maxH, endH)
  }
  return { start: Math.max(0, minH - 1), end: Math.min(24, maxH + 1) }
})

// 问题4：智能间隔 - 根据时间跨度自动决定刻度显示间隔
const hourInterval = computed(() => {
  const span = timelineHours.value.end - timelineHours.value.start
  if (span <= 8) return 1   // 8小时以内，每小时显示
  if (span <= 14) return 2  // 14小时以内，每2小时显示
  return 3                   // 更多则每3小时
})

const getTimelineStyle = (log: any) => {
  const hours = timelineHours.value
  const totalMinutes = (hours.end - hours.start) * 60
  const startDate = new Date(log.start_time)
  const endDate = log.end_time ? new Date(log.end_time) : new Date()
  const startMin = (startDate.getHours() - hours.start) * 60 + startDate.getMinutes()
  const endMin = (endDate.getHours() - hours.start) * 60 + endDate.getMinutes()
  const left = Math.max(0, (startMin / totalMinutes) * 100)
  const width = Math.max(1, ((endMin - startMin) / totalMinutes) * 100)
  const color = categoryColorMap[log.category] || '#94A3B8'
  return {
    left: `${left}%`,
    width: `${width}%`,
    background: color,
  }
}

const getTimelineTooltip = (log: any) => {
  const start = new Date(log.start_time)
  const end = log.end_time ? new Date(log.end_time) : new Date()
  const startStr = `${String(start.getHours()).padStart(2, '0')}:${String(start.getMinutes()).padStart(2, '0')}`
  const endStr = `${String(end.getHours()).padStart(2, '0')}:${String(end.getMinutes()).padStart(2, '0')}`
  const dur = log.duration_seconds ? formatDuration(log.duration_seconds) : '进行中'
  return `${log.todo_title || '未知任务'}\n${startStr} - ${endStr} (${dur})`
}

watch(activeRange, () => {
  fetchStats()
  fetchTimeAnalysis()
  // 切换范围时重置为按天模式
  categoryFilterMode.value = 'day'
  selectedDay.value = ''
})
onMounted(() => {
  fetchStats()
  fetchTimeAnalysis()
})
</script>

<template>
  <div class="todo-review">
    <div class="todo-review__header">
      <div>
        <h1>📈 总结报告</h1>
        <p class="todo-review__subtitle">回顾数据，持续进步</p>
      </div>
    </div>

    <!-- 时间范围选择 -->
    <div class="range-bar">
      <button
        v-for="(cfg, key) in ranges"
        :key="key"
        class="range-btn"
        :class="{ 'range-btn--active': activeRange === key }"
        @click="activeRange = key"
      >
        {{ cfg.label }}
      </button>
    </div>

    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
    </div>

    <template v-else-if="stats">
      <!-- 核心指标 -->
      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-card__ring">
            <svg viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(236,72,153,0.1)" stroke-width="8" />
              <circle
                cx="50" cy="50" r="40" fill="none" stroke="#EC4899" stroke-width="8"
                stroke-linecap="round"
                :stroke-dasharray="`${stats.completion_rate * 2.51} 251`"
                transform="rotate(-90 50 50)"
                style="transition: stroke-dasharray 0.8s ease;"
              />
              <text x="50" y="50" text-anchor="middle" dominant-baseline="central" font-size="16" font-weight="700" fill="#EC4899">
                {{ stats.completion_rate }}%
              </text>
            </svg>
          </div>
          <span class="metric-card__label">完成率</span>
        </div>
        <div class="metric-card metric-card--simple">
          <span class="metric-card__value">{{ stats.total_completed }}</span>
          <span class="metric-card__label">已完成</span>
        </div>
        <div class="metric-card metric-card--simple">
          <span class="metric-card__value">{{ stats.total_created }}</span>
          <span class="metric-card__label">新增</span>
        </div>
        <div class="metric-card metric-card--simple">
          <span class="metric-card__value" style="color: #F59E0B;">{{ stats.total_deferred }}</span>
          <span class="metric-card__label">推迟</span>
        </div>
      </div>

      <div class="charts-grid">
        <!-- 四象限分布 -->
        <div class="chart-card">
          <h3>四象限分布</h3>
          <div class="bar-chart">
            <div v-for="q in [1,2,3,4]" :key="q" class="bar-row">
              <span class="bar-row__label" :style="{ color: quadrantLabels[q].color }">{{ quadrantLabels[q].label }}</span>
              <div class="bar-row__bars">
                <div class="bar-row__bar" :style="{
                  width: Math.max(4, (stats.quadrant_stats[q]?.created || 0) / maxQuadrantCount * 100) + '%',
                  background: quadrantLabels[q].color,
                  opacity: 0.4,
                }" :title="`新增 ${stats.quadrant_stats[q]?.created || 0}`"></div>
                <div class="bar-row__bar" :style="{
                  width: Math.max(4, (stats.quadrant_stats[q]?.completed || 0) / maxQuadrantCount * 100) + '%',
                  background: quadrantLabels[q].color,
                }" :title="`完成 ${stats.quadrant_stats[q]?.completed || 0}`"></div>
              </div>
              <span class="bar-row__value">
                {{ stats.quadrant_stats[q]?.completed || 0 }}/{{ stats.quadrant_stats[q]?.created || 0 }}
              </span>
            </div>
          </div>
          <div class="bar-legend">
            <span class="bar-legend__item"><span class="bar-legend__dot" style="opacity: 0.4;"></span>新增</span>
            <span class="bar-legend__item"><span class="bar-legend__dot"></span>完成</span>
          </div>
        </div>

        <!-- 分类分布 -->
        <div class="chart-card">
          <h3>分类分布</h3>
          <div v-if="Object.keys(stats.category_stats).length === 0" class="chart-empty">暂无数据</div>
          <div v-else class="pie-list">
            <div v-for="(count, cat) in stats.category_stats" :key="cat" class="pie-item">
              <span class="pie-item__name">{{ categoryLabels[String(cat)] || cat }}</span>
              <div class="pie-item__bar">
                <div class="pie-item__fill" :style="{
                  width: (count / stats.total_created * 100) + '%',
                }"></div>
              </div>
              <span class="pie-item__count">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- 每日完成趋势 -->
        <div class="chart-card chart-card--wide">
          <h3>完成趋势</h3>
          <div v-if="Object.keys(stats.daily_completion).length === 0" class="chart-empty">暂无数据</div>
          <div v-else class="trend-chart">
            <div
              v-for="(count, day) in stats.daily_completion"
              :key="day"
              class="trend-bar"
            >
              <div class="trend-bar__track">
                <div class="trend-bar__fill" :style="{ height: Math.max(4, Number(count) / maxDailyCount * 100) + '%' }"></div>
              </div>
              <span class="trend-bar__label">{{ String(day).slice(5) }}</span>
              <span class="trend-bar__value">{{ count }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ==================== 时间分析区块 ==================== -->
      <div class="time-analysis-section">
        <div class="time-analysis-header">
          <h2 class="section-title">⏱ 时间分析</h2>
          <div class="time-analysis-filter">
            <div class="category-filter">
              <button class="category-filter__btn"
                :class="{ 'category-filter__btn--active': categoryFilterMode === 'all' }"
                @click="categoryFilterMode = 'all'"
              >全部</button>
              <button class="category-filter__btn"
                :class="{ 'category-filter__btn--active': categoryFilterMode === 'day' }"
                @click="categoryFilterMode = 'day'"
              >按天</button>
            </div>
            <div v-if="categoryFilterMode === 'day'" class="day-picker day-picker--inline">
              <button class="day-picker__arrow" @click="selectedDay = availableDays[Math.max(0, availableDays.indexOf(selectedDay) - 1)]" :disabled="availableDays.indexOf(selectedDay) <= 0">‹</button>
              <select v-model="selectedDay" class="day-picker__select">
                <option v-for="d in availableDays" :key="d" :value="d">{{ d.slice(5) }}</option>
              </select>
              <button class="day-picker__arrow" @click="selectedDay = availableDays[Math.min(availableDays.length - 1, availableDays.indexOf(selectedDay) + 1)]" :disabled="availableDays.indexOf(selectedDay) >= availableDays.length - 1">›</button>
            </div>
          </div>
        </div>

        <div v-if="timeLoading" class="loading loading--sm">
          <div class="loading__spinner loading__spinner--sm"></div>
        </div>

        <template v-else-if="timeAnalysis">
          <!-- 时间轴（支持按天选择） -->
          <div v-if="currentTimelineLogs.length" class="chart-card chart-card--wide chart-card--timeline">
            <h3>📊 {{ categoryFilterMode === 'day' && selectedDay ? selectedDay.slice(5) : '今日' }} 时间轴</h3>
            <div class="timeline-container">
              <div class="timeline-hours">
                <span v-for="h in (timelineHours.end - timelineHours.start + 1)" :key="h"
                  class="timeline-hour"
                  v-show="(h - 1) % hourInterval === 0"
                  :style="{ left: ((h - 1) / (timelineHours.end - timelineHours.start)) * 100 + '%' }"
                >{{ timelineHours.start + h - 1 }}:00</span>
              </div>
              <div class="timeline-track">
                <div
                  v-for="(log, idx) in currentTimelineLogs"
                  :key="idx"
                  class="timeline-block"
                  :class="{ 'timeline-block--running': !log.end_time }"
                  :style="getTimelineStyle(log)"
                  :title="getTimelineTooltip(log)"
                ></div>
              </div>
            </div>
            <!-- 分类图例 -->
            <div class="timeline-legend">
              <span v-for="(color, cat) in categoryColorMap" :key="cat" class="timeline-legend__item"
                v-show="currentTimelineLogs.some((s: any) => s.category === cat)"
              >
                <span class="timeline-legend__dot" :style="{ background: color }"></span>
                {{ getCategoryName(cat) }}
              </span>
            </div>
          </div>

          <!-- 环形图 + 统计卡片 -->
          <div class="time-charts-row">
            <div class="chart-card">
              <h3>分类占比 {{ categoryFilterMode === 'day' && selectedDay ? '(' + selectedDay.slice(5) + ')' : '' }}</h3>
              <div v-if="!filteredCategoryStats?.length" class="chart-empty">暂无计时数据</div>
              <template v-else>
                <div class="doughnut-wrapper">
                  <Doughnut :data="doughnutData" :options="doughnutOptions" />
                </div>
                <div class="category-legend">
                  <div v-for="(stat, idx) in filteredCategoryStats" :key="idx" class="category-legend__item">
                    <span class="category-legend__dot" :style="{ background: categoryColorMap[stat.category] || '#94A3B8' }"></span>
                    <span class="category-legend__name">{{ getCategoryName(stat.category) }}</span>
                    <span class="category-legend__value">{{ formatDuration(stat.total_seconds) }}</span>
                  </div>
                </div>
              </template>
            </div>
            <div class="chart-card">
              <h3>{{ currentStatsLabel }}</h3>
              <div class="time-stats-grid">
                <div class="time-stat-item">
                  <span class="time-stat-item__value">{{ formatDuration(currentStats.totalSeconds) }}</span>
                  <span class="time-stat-item__label">总计时</span>
                </div>
                <div class="time-stat-item">
                  <span class="time-stat-item__value">{{ currentStats.totalTasks }}</span>
                  <span class="time-stat-item__label">计时任务数</span>
                </div>
                <div class="time-stat-item">
                  <span class="time-stat-item__value">{{ currentStats.categoryCount }}</span>
                  <span class="time-stat-item__label">涉及分类</span>
                </div>
                <div class="time-stat-item">
                  <span class="time-stat-item__value">{{ currentStats.logCount }}</span>
                  <span class="time-stat-item__label">计时次数</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 堆叠柱状图 - 最近 N 天趋势 -->
          <div v-if="timeAnalysis.daily_stats?.length" class="chart-card chart-card--wide">
            <h3>时间投入趋势</h3>
            <div class="stacked-bar-wrapper">
              <Bar :data="stackedBarData" :options="stackedBarOptions" />
            </div>
          </div>
        </template>

        <div v-else class="chart-empty">暂无时间分析数据，试试在全部待办中点击 ▶️ 开始计时吧</div>
      </div>

      <!-- 拖延排行榜 -->
      <div class="delay-section" v-if="delayedItems.length">
        <h3>⏰ 拖延排行榜</h3>
        <div class="delay-list">
          <div v-for="(item, idx) in delayedItems" :key="item.id" class="delay-item">
            <span class="delay-item__rank" :class="{ 'delay-item__rank--danger': idx < 2 }">
              #{{ idx + 1 }}
            </span>
            <span class="delay-item__title">{{ item.title }}</span>
            <span class="delay-item__days" :class="{ 'delay-item__days--danger': item.days_waiting > 14 }">
              {{ item.days_waiting }} 天
            </span>
          </div>
        </div>
      </div>

      <!-- AI 总结 -->
      <div class="summary-section">
        <div class="summary-section__header">
          <h3>🤖 AI 总结报告</h3>
          <button
            class="btn btn--primary"
            :disabled="summaryLoading"
            @click="generateSummary"
          >
            {{ summaryLoading ? '生成中...' : '生成 AI 总结' }}
          </button>
        </div>
        <div v-if="summaryLoading" class="loading loading--sm">
          <div class="loading__spinner loading__spinner--sm"></div>
          <p>AI 正在分析你的数据...</p>
        </div>
        <div v-else-if="summaryMarkdown" class="summary-content" v-html="renderMarkdown(summaryMarkdown)"></div>
        <div v-else class="chart-empty">点击上方按钮生成 AI 总结报告（纯展示不存储）</div>
      </div>
    </template>
  </div>
</template>

<script lang="ts">
// 简单的 markdown 渲染
function renderMarkdown(md: string): string {
  return md
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^# (.+)$/gm, '<h2>$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br/>')
}

export default {
  methods: { renderMarkdown },
}
</script>

<style lang="scss" scoped>
.todo-review {
  &__header {
    margin-bottom: $spacing-lg;
    h1 { font-size: $font-size-xl; }
  }
  &__subtitle { color: $text-secondary; font-size: $font-size-sm; margin-top: $spacing-xs; }
}

.range-bar {
  @include glass-card;
  display: flex;
  gap: $spacing-xs;
  padding: $spacing-sm;
  margin-bottom: $spacing-lg;
  flex-wrap: wrap;
}

.range-btn {
  padding: $spacing-xs $spacing-md;
  border-radius: $border-radius-md;
  border: none;
  background: transparent;
  font-size: $font-size-sm;
  font-weight: 500;
  color: $text-secondary;
  cursor: pointer;
  transition: all $transition-fast;

  &:hover { background: rgba(236, 72, 153, 0.08); color: #EC4899; }
  &--active {
    background: linear-gradient(135deg, #EC4899, #8B5CF6);
    color: white;
  }
}

// 核心指标
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: $spacing-md;
  margin-bottom: $spacing-lg;

  @media (max-width: $breakpoint-md) { grid-template-columns: repeat(2, 1fr); }
}

.metric-card {
  @include glass-card;
  padding: $spacing-lg;
  text-align: center;

  &__ring {
    width: 100px;
    height: 100px;
    margin: 0 auto $spacing-sm;
  }

  &__value {
    font-size: $font-size-xxl;
    font-weight: 700;
    color: #EC4899;
    display: block;
  }

  &__label {
    font-size: $font-size-sm;
    color: $text-secondary;
    display: block;
    margin-top: $spacing-xs;
  }

  &--simple {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }
}

// 图表
.charts-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-md;
  margin-bottom: $spacing-lg;

  @media (max-width: $breakpoint-md) { grid-template-columns: 1fr; }
}

.chart-card {
  @include glass-card;
  padding: $spacing-lg;

  h3 { font-size: $font-size-md; margin-bottom: $spacing-md; }

  &--wide { grid-column: 1 / -1; }

  &--timeline { margin-bottom: $spacing-md; }

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    h3 { font-size: $font-size-sm; margin-bottom: $spacing-sm; }
  }
}

.chart-empty {
  text-align: center;
  color: $text-muted;
  padding: $spacing-lg;
  font-size: $font-size-sm;
}

// 柱状图
.bar-chart { display: flex; flex-direction: column; gap: $spacing-sm; }

.bar-row {
  display: flex;
  align-items: center;
  gap: $spacing-sm;

  &__label {
    font-size: $font-size-xs;
    width: 80px;
    color: $text-secondary;
    flex-shrink: 0;

    @media (max-width: $breakpoint-sm) {
      width: 56px;
      font-size: 10px;
    }
  }
  &__bars { flex: 1; display: flex; gap: 4px; align-items: center; min-width: 0; }
  &__bar {
    height: 16px;
    border-radius: 4px;
    transition: width 0.5s ease;
    min-width: 4px;

    @media (max-width: $breakpoint-sm) { height: 12px; }
  }
  &__value {
    font-size: $font-size-xs;
    color: $text-muted;
    min-width: 40px;
    text-align: right;
    flex-shrink: 0;

    @media (max-width: $breakpoint-sm) {
      min-width: 32px;
      font-size: 10px;
    }
  }
}

.bar-legend {
  display: flex;
  gap: $spacing-md;
  margin-top: $spacing-sm;
  justify-content: center;

  &__item { display: flex; align-items: center; gap: $spacing-xs; font-size: $font-size-xs; color: $text-muted; }
  &__dot { width: 8px; height: 8px; border-radius: 2px; background: #EC4899; }
}

// 分类列表
.pie-list { display: flex; flex-direction: column; gap: $spacing-sm; }

.pie-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;

  &__name { font-size: $font-size-xs; width: 50px; }
  &__bar { flex: 1; height: 8px; background: rgba(139, 92, 246, 0.1); border-radius: 4px; overflow: hidden; }
  &__fill { height: 100%; background: linear-gradient(90deg, #EC4899, #8B5CF6); border-radius: 4px; transition: width 0.5s ease; }
  &__count { font-size: $font-size-xs; color: $text-muted; min-width: 24px; text-align: right; }
}

// 趋势图
.trend-chart {
  display: flex;
  align-items: flex-end;
  gap: $spacing-sm;
  height: 120px;
  padding-top: $spacing-md;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;

  @media (max-width: $breakpoint-sm) {
    gap: 4px;
    height: 100px;
  }
}

.trend-bar {
  flex: 1;
  min-width: 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;

  @media (max-width: $breakpoint-sm) {
    min-width: 22px;
  }

  &__track {
    width: 100%;
    max-width: 32px;
    height: 78px;
    display: flex;
    align-items: flex-end;

    @media (max-width: $breakpoint-sm) {
      max-width: 20px;
      height: 62px;
    }
  }

  &__fill {
    width: 100%;
    background: linear-gradient(180deg, #EC4899, #8B5CF6);
    border-radius: 4px 4px 0 0;
    transition: height 0.5s ease;
    min-height: 4px;
  }

  &__label {
    font-size: 10px;
    color: $text-muted;
    white-space: nowrap;

    @media (max-width: $breakpoint-sm) { font-size: 8px; }
  }
  &__value {
    font-size: 10px;
    color: $text-secondary;
    font-weight: 600;

    @media (max-width: $breakpoint-sm) { font-size: 8px; }
  }
}

// 拖延排行
.delay-section {
  @include glass-card;
  padding: $spacing-lg;
  margin-bottom: $spacing-lg;

  h3 { font-size: $font-size-md; margin-bottom: $spacing-md; }
}

.delay-list { display: flex; flex-direction: column; gap: $spacing-sm; }

.delay-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-sm;
  background: rgba(255,255,255,0.5);

  &__rank {
    font-size: $font-size-sm;
    font-weight: 700;
    color: $text-muted;
    width: 32px;

    &--danger { color: #EF4444; }
  }

  &__title { flex: 1; font-size: $font-size-sm; }

  &__days {
    font-size: $font-size-sm;
    font-weight: 600;
    color: $text-secondary;

    &--danger { color: #EF4444; }
  }
}

// AI 总结
.summary-section {
  @include glass-card;
  padding: $spacing-lg;

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: $spacing-md;

    h3 { font-size: $font-size-md; margin: 0; }
  }
}

.summary-content {
  padding: $spacing-md;
  background: rgba(255,255,255,0.5);
  border-radius: $border-radius-md;
  font-size: $font-size-sm;
  line-height: 1.8;

  :deep(h2) { font-size: $font-size-lg; margin: $spacing-md 0 $spacing-sm; }
  :deep(h3) { font-size: $font-size-md; margin: $spacing-md 0 $spacing-sm; }
  :deep(h4) { font-size: $font-size-sm; font-weight: 600; margin: $spacing-sm 0; }
  :deep(strong) { color: #EC4899; }
  :deep(ul) { margin: $spacing-sm 0; padding-left: $spacing-lg; }
  :deep(li) { margin-bottom: $spacing-xs; }
}

// ==================== 时间分析区块样式 ====================
.section-title {
  font-size: $font-size-lg;
  font-weight: 600;
  margin-bottom: 0;
  display: flex;
  align-items: center;
  gap: $spacing-xs;
}

.time-analysis-section {
  margin-bottom: $spacing-lg;
}

// 时间分析头部（标题 + 筛选器）
.time-analysis-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $spacing-md;
  flex-wrap: wrap;
  gap: $spacing-sm;
}

.time-analysis-filter {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
}

.time-charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-md;
  margin-bottom: $spacing-md;

  @media (max-width: $breakpoint-md) { grid-template-columns: 1fr; }
}

// 时间轴
.timeline-container {
  padding: $spacing-sm 0;
}

.timeline-hours {
  position: relative;
  height: 20px;
  margin-bottom: $spacing-xs;
}

.timeline-hour {
  position: absolute;
  font-size: 9px;
  color: $text-muted;
  transform: translateX(-50%);
  white-space: nowrap;
}

.timeline-track {
  position: relative;
  height: 28px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: $border-radius-sm;
  overflow: hidden;
}

.timeline-block {
  position: absolute;
  top: 2px;
  bottom: 2px;
  border-radius: 3px;
  opacity: 0.85;
  cursor: pointer;
  transition: opacity $transition-fast;
  min-width: 3px;

  &:hover { opacity: 1; z-index: 1; box-shadow: 0 0 6px rgba(0, 0, 0, 0.2); }

  &--running {
    animation: running-pulse 1.5s ease-in-out infinite;
  }
}

@keyframes running-pulse {
  0%, 100% { opacity: 0.85; }
  50% { opacity: 0.5; }
}

.timeline-legend {
  display: flex;
  gap: $spacing-md;
  margin-top: $spacing-sm;
  flex-wrap: wrap;

  &__item {
    display: flex;
    align-items: center;
    gap: $spacing-xs;
    font-size: $font-size-xs;
    color: $text-secondary;
  }

  &__dot {
    width: 8px;
    height: 8px;
    border-radius: 2px;
    flex-shrink: 0;
  }
}

// 环形图
.doughnut-wrapper {
  width: 160px;
  height: 160px;
  margin: 0 auto $spacing-md;

  @media (max-width: $breakpoint-sm) {
    width: 130px;
    height: 130px;
  }
}

// 分类占比卡片头部
.chart-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $spacing-md;

  h3 { margin-bottom: 0; }
}

// 分类筛选切换按钮
.category-filter {
  display: flex;
  gap: 2px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: $border-radius-sm;
  padding: 2px;

  &__btn {
    padding: 3px 10px;
    border: none;
    background: transparent;
    font-size: 11px;
    font-weight: 500;
    color: $text-muted;
    border-radius: 4px;
    cursor: pointer;
    transition: all $transition-fast;

    &:hover { color: $text-secondary; }

    &--active {
      background: white;
      color: #EC4899;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
  }
}

// 日期选择器
.day-picker {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $spacing-xs;
  margin-bottom: $spacing-md;

  &--inline {
    margin-bottom: 0;
  }

  &__arrow {
    width: 28px;
    height: 28px;
    border: 1px solid $border-color;
    background: white;
    border-radius: $border-radius-sm;
    font-size: 16px;
    font-weight: 600;
    color: $text-secondary;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all $transition-fast;

    &:hover:not(:disabled) {
      border-color: #EC4899;
      color: #EC4899;
    }

    &:disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }
  }

  &__select {
    padding: 4px 8px;
    border: 1px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-xs;
    color: $text-primary;
    background: white;
    cursor: pointer;
    outline: none;
    min-width: 80px;
    text-align: center;

    &:focus { border-color: #EC4899; }
  }
}

.category-legend {
  display: flex;
  flex-direction: column;
  gap: $spacing-xs;

  &__item {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    font-size: $font-size-xs;
  }

  &__dot {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    flex-shrink: 0;
  }

  &__name {
    flex: 1;
    color: $text-secondary;
  }

  &__value {
    font-weight: 600;
    color: $text-primary;
    font-family: 'Courier New', monospace;
  }
}

// 统计卡片
.time-stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-md;
  padding: $spacing-md 0;
}

.time-stat-item {
  text-align: center;
  padding: $spacing-md;
  border-radius: $border-radius-sm;
  background: rgba(236, 72, 153, 0.04);

  &__value {
    display: block;
    font-size: $font-size-lg;
    font-weight: 700;
    color: #EC4899;
    margin-bottom: $spacing-xs;
    font-family: 'Courier New', monospace;
  }

  &__label {
    display: block;
    font-size: $font-size-xs;
    color: $text-secondary;
  }
}

// 堆叠柱状图
.stacked-bar-wrapper {
  height: 200px;
  padding: $spacing-sm 0;

  @media (max-width: $breakpoint-sm) { height: 160px; }
}

// 共用
.loading {
  text-align: center;
  padding: $spacing-xxl;
  color: $text-secondary;

  &--sm { padding: $spacing-lg; }

  &__spinner {
    width: 40px; height: 40px;
    border: 3px solid $border-color;
    border-top-color: #EC4899;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto $spacing-md;

    &--sm { width: 24px; height: 24px; border-width: 2px; }
  }
}

.btn {
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  font-weight: 500;
  cursor: pointer;
  transition: all $transition-fast;
  border: none;

  &--primary {
    background: linear-gradient(135deg, #EC4899, #8B5CF6);
    color: white;
    &:hover { opacity: 0.9; }
  }

  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

@keyframes spin { to { transform: rotate(360deg); } }
</style>
