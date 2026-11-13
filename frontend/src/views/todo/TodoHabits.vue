<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { TODO_API_BASE } from '@/config'

interface RecurringTask {
  id: number
  title: string
  description: string | null
  frequency: string
  frequency_detail: string | null
  category: string | null
  next_due: string
  streak: number
  total_completed: number
  last_checked_at: string | null
  is_active: boolean
  auto_event: string | null
  auto_keywords: string | null
  last_checkin_auto: boolean
  created_at: string
}

const habits = ref<RecurringTask[]>([])
const loading = ref(true)
const showCreateForm = ref(false)
const checkingIn = ref<number | null>(null)
const editingId = ref<number | null>(null)

// 新建/编辑表单
const newTitle = ref('')
const newDescription = ref('')
const newFrequency = ref('daily')
const newCategory = ref('')
const newAutoEvent = ref('')
const newAutoKeywords = ref('')

const autoEventLabels: Record<string, string> = {
  diary: '写日记时',
  basketball: '保存篮球复盘后',
}

const categoryLabels: Record<string, string> = {
  work: '工作/项目', learning: '学习/成长', life: '生活/事务',
  health: '健康/运动', social: '社交/关系', finance: '财务/投资', creative: '创意/探索',
}

const frequencyLabels: Record<string, string> = {
  daily: '每日', weekly: '每周', custom: '自定义',
}

const fetchHabits = async () => {
  loading.value = true
  try {
    const res = await fetch(`${TODO_API_BASE}/recurring`)
    if (!res.ok) throw new Error('加载失败')
    const data = await res.json()
    const items: RecurringTask[] = data.items || []
    // 已打卡的排末尾，未打卡的排前面
    items.sort((a, b) => {
      const aChecked = isCheckedToday(a) ? 1 : 0
      const bChecked = isCheckedToday(b) ? 1 : 0
      return aChecked - bChecked
    })
    habits.value = items
  } catch (e) {
    habits.value = []
  } finally {
    loading.value = false
  }
}

const checkIn = async (id: number) => {
  checkingIn.value = id
  try {
    const res = await fetch(`${TODO_API_BASE}/recurring/${id}/check-in`, { method: 'POST' })
    if (!res.ok) {
      const data = await res.json()
      alert(data.detail || '打卡失败')
      return
    }
    fetchHabits()
  } catch (e) {
    alert('打卡失败')
  } finally {
    checkingIn.value = null
  }
}

const resetForm = () => {
  newTitle.value = ''
  newDescription.value = ''
  newFrequency.value = 'daily'
  newCategory.value = ''
  newAutoEvent.value = ''
  newAutoKeywords.value = ''
  editingId.value = null
}

const editHabit = (habit: RecurringTask) => {
  newTitle.value = habit.title
  newDescription.value = habit.description || ''
  newFrequency.value = habit.frequency
  newCategory.value = habit.category || ''
  newAutoEvent.value = habit.auto_event || ''
  newAutoKeywords.value = habit.auto_keywords || ''
  editingId.value = habit.id
  showCreateForm.value = true
}

const createHabit = async () => {
  if (!newTitle.value.trim()) return
  const payload = {
    title: newTitle.value,
    description: newDescription.value || null,
    frequency: newFrequency.value,
    category: newCategory.value || null,
    auto_event: newAutoEvent.value || null,
    auto_keywords: newAutoKeywords.value.trim() || null,
  }
  try {
    const res = editingId.value
      ? await fetch(`${TODO_API_BASE}/recurring/${editingId.value}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
      : await fetch(`${TODO_API_BASE}/recurring`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
    if (res.ok) {
      showCreateForm.value = false
      resetForm()
      fetchHabits()
    }
  } catch (e) { /* */ }
}

const undoCheckIn = async (habit: RecurringTask) => {
  try {
    const res = await fetch(`${TODO_API_BASE}/recurring/${habit.id}/undo-check-in`, { method: 'POST' })
    if (!res.ok) {
      const data = await res.json()
      alert(data.detail || '撤销失败')
      return
    }
    fetchHabits()
  } catch (e) {
    alert('撤销失败')
  }
}

const toggleActive = async (habit: RecurringTask) => {
  try {
    await fetch(`${TODO_API_BASE}/recurring/${habit.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: !habit.is_active }),
    })
    fetchHabits()
  } catch (e) { /* */ }
}

const isCheckedToday = (habit: RecurringTask) => {
  if (!habit.last_checked_at) return false
  const today = new Date().toISOString().split('T')[0]
  return habit.last_checked_at.split('T')[0] === today
}

const completionRate = (habit: RecurringTask) => {
  const days = Math.max(1, Math.ceil((Date.now() - new Date(habit.created_at).getTime()) / (1000 * 60 * 60 * 24)))
  if (habit.frequency === 'weekly') {
    const weeks = Math.max(1, Math.ceil(days / 7))
    return Math.min(100, Math.round((habit.total_completed / weeks) * 100))
  }
  return Math.min(100, Math.round((habit.total_completed / days) * 100))
}

// 简单热力图（最近30天）- 保留供后续使用
// const heatmapDays = computed(() => {
//   const days = []
//   for (let i = 29; i >= 0; i--) {
//     const d = new Date()
//     d.setDate(d.getDate() - i)
//     days.push(d.toISOString().split('T')[0])
//   }
//   return days
// })

onMounted(fetchHabits)
</script>

<template>
  <div class="todo-habits">
    <div class="todo-habits__header">
      <div>
        <h1>🔥 习惯追踪</h1>
        <p class="todo-habits__subtitle">坚持每天的小进步</p>
      </div>
      <button class="btn btn--primary" @click="showCreateForm = !showCreateForm; if (!showCreateForm) resetForm()">
        {{ showCreateForm ? '取消' : '+ 新习惯' }}
      </button>
    </div>

    <!-- 新建/编辑表单 -->
    <div v-if="showCreateForm" class="create-form">
      <div class="form-row">
        <div class="form-group form-group--flex">
          <label>习惯名称</label>
          <input v-model="newTitle" class="form-input" placeholder="例如: 每天运动30分钟" />
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>频率</label>
          <select v-model="newFrequency" class="form-input">
            <option value="daily">每日</option>
            <option value="weekly">每周</option>
          </select>
        </div>
        <div class="form-group">
          <label>分类</label>
          <select v-model="newCategory" class="form-input">
            <option value="">无</option>
            <option v-for="(label, key) in categoryLabels" :key="key" :value="key">{{ label }}</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>描述（可选）</label>
        <input v-model="newDescription" class="form-input" placeholder="补充说明" />
      </div>
      <!-- 自动打卡配置 -->
      <div class="auto-config">
        <div class="auto-config__title">🤖 自动打卡（可选）</div>
        <div class="form-row">
          <div class="form-group">
            <label>触发事件</label>
            <select v-model="newAutoEvent" class="form-input">
              <option value="">无</option>
              <option v-for="(label, key) in autoEventLabels" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>关键词（命中即打卡）</label>
            <input v-model="newAutoKeywords" class="form-input" placeholder="逗号分隔，如: 洗澡,冲凉" />
          </div>
        </div>
        <p class="auto-config__hint">关键词会在日记、时间记录状态、完成的任务名中匹配；事件触发优先级更高</p>
      </div>
      <button class="btn btn--primary" @click="createHabit" :disabled="!newTitle.trim()">
        {{ editingId ? '保存' : '创建' }}
      </button>
    </div>

    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
    </div>

    <div v-else-if="habits.length === 0 && !showCreateForm" class="empty-state">
      <span class="empty-state__icon">🌱</span>
      <p>还没有习惯，创建一个开始吧</p>
      <button class="btn btn--primary" @click="showCreateForm = true">+ 新习惯</button>
    </div>

    <!-- 习惯卡片网格 -->
    <div v-else class="habits-grid">
      <div
        v-for="habit in habits"
        :key="habit.id"
        class="habit-card"
        :class="{ 'habit-card--inactive': !habit.is_active, 'habit-card--checked': isCheckedToday(habit) }"
      >
        <div class="habit-card__header">
          <div>
            <h3>{{ habit.title }}</h3>
            <div class="habit-card__meta">
              <span class="habit-card__freq">{{ frequencyLabels[habit.frequency] || habit.frequency }}</span>
              <span v-if="habit.category" class="habit-card__cat">{{ categoryLabels[habit.category] || habit.category }}</span>
              <span
                v-if="habit.auto_event || habit.auto_keywords"
                class="habit-card__auto"
                :title="`自动打卡：${habit.auto_event ? autoEventLabels[habit.auto_event] : ''}${habit.auto_event && habit.auto_keywords ? '；' : ''}${habit.auto_keywords ? '关键词 ' + habit.auto_keywords : ''}`"
              >🤖 自动</span>
            </div>
          </div>
          <div class="habit-card__actions">
            <button class="toggle-btn" title="编辑" @click="editHabit(habit)">✏️</button>
            <button class="toggle-btn" :title="habit.is_active ? '暂停' : '启用'" @click="toggleActive(habit)">
              {{ habit.is_active ? '⏸️' : '▶️' }}
            </button>
          </div>
        </div>

        <div class="habit-card__streak">
          <span class="habit-card__streak-num">{{ habit.streak }}</span>
          <span class="habit-card__streak-label">连续天数</span>
        </div>

        <div class="habit-card__stats">
          <div class="habit-card__stat">
            <span class="habit-card__stat-value">{{ habit.total_completed }}</span>
            <span class="habit-card__stat-label">总次数</span>
          </div>
          <div class="habit-card__stat">
            <span class="habit-card__stat-value">{{ completionRate(habit) }}%</span>
            <span class="habit-card__stat-label">完成率</span>
          </div>
        </div>

        <!-- 完成率进度条 -->
        <div class="habit-card__progress">
          <div class="habit-card__progress-fill" :style="{ width: completionRate(habit) + '%' }"></div>
        </div>

        <button
          v-if="habit.is_active"
          class="checkin-btn"
          :class="{ 'checkin-btn--done': isCheckedToday(habit) }"
          :disabled="isCheckedToday(habit) || checkingIn === habit.id"
          @click="checkIn(habit.id)"
        >
          <span v-if="isCheckedToday(habit)">{{ habit.last_checkin_auto ? '🤖 已自动打卡' : '✅ 已打卡' }}</span>
          <span v-else-if="checkingIn === habit.id">打卡中...</span>
          <span v-else>🎯 打卡</span>
        </button>
        <button
          v-if="habit.is_active && isCheckedToday(habit)"
          class="undo-btn"
          @click="undoCheckIn(habit)"
        >撤销今日打卡</button>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.todo-habits {
  &__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: $spacing-lg;

    h1 { font-size: $font-size-xl; }
  }

  &__subtitle {
    color: $text-secondary;
    font-size: $font-size-sm;
    margin-top: $spacing-xs;
  }
}

// 新建表单
.create-form {
  @include glass-card;
  padding: $spacing-lg;
  margin-bottom: $spacing-lg;
  border: 1px dashed rgba(236, 72, 153, 0.3);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-md;

  @media (max-width: $breakpoint-sm) { grid-template-columns: 1fr; }
}

.form-group {
  margin-bottom: $spacing-md;
  label { display: block; font-size: $font-size-xs; font-weight: 600; color: $text-secondary; margin-bottom: $spacing-xs; }
  &--flex { grid-column: 1 / -1; }
}

.form-input {
  width: 100%;
  padding: $spacing-sm $spacing-md;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  font-family: inherit;
  background: rgba(255,255,255,0.8);
  &:focus { outline: none; border-color: #EC4899; }
}

// 习惯网格
.habits-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: $spacing-md;
}

.habit-card {
  @include glass-card;
  padding: $spacing-lg;
  transition: all $transition-fast;

  &:hover { box-shadow: 0 8px 24px rgba(236, 72, 153, 0.1); }

  &--inactive { opacity: 0.5; }

  &--checked {
    border: 1px solid rgba(16, 185, 129, 0.3);
    background: rgba(16, 185, 129, 0.03);
  }

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: $spacing-md;

    h3 { font-size: $font-size-sm; font-weight: 600; }
  }

  &__meta {
    display: flex;
    gap: $spacing-xs;
    margin-top: $spacing-xs;
  }

  &__freq, &__cat {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    background: rgba(0,0,0,0.04);
    color: $text-muted;
  }

  &__cat { background: rgba(139, 92, 246, 0.1); color: #8B5CF6; }

  &__auto {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    background: rgba(59, 130, 246, 0.1);
    color: #3B82F6;
    cursor: help;
  }

  &__actions {
    display: flex;
    gap: $spacing-xs;
    flex-shrink: 0;
  }

  &__streak {
    text-align: center;
    margin-bottom: $spacing-md;

    &-num {
      font-size: 40px;
      font-weight: 700;
      background: linear-gradient(135deg, #EC4899, #F59E0B);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      display: block;
      line-height: 1;
    }

    &-label {
      font-size: $font-size-xs;
      color: $text-muted;
    }
  }

  &__stats {
    display: flex;
    justify-content: space-around;
    margin-bottom: $spacing-sm;
  }

  &__stat {
    text-align: center;

    &-value { font-size: $font-size-md; font-weight: 600; display: block; }
    &-label { font-size: $font-size-xs; color: $text-muted; }
  }

  &__progress {
    height: 4px;
    background: rgba(236, 72, 153, 0.1);
    border-radius: 2px;
    overflow: hidden;
    margin-bottom: $spacing-md;

    &-fill {
      height: 100%;
      background: linear-gradient(90deg, #EC4899, #8B5CF6);
      border-radius: 2px;
      transition: width 0.5s ease;
    }
  }
}

.toggle-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: rgba(0,0,0,0.04);
  cursor: pointer;
  font-size: 14px;
  transition: all $transition-fast;
  &:hover { background: rgba(0,0,0,0.08); }
}

.checkin-btn {
  width: 100%;
  padding: $spacing-sm;
  border-radius: $border-radius-md;
  border: none;
  font-size: $font-size-sm;
  font-weight: 600;
  cursor: pointer;
  transition: all $transition-fast;
  background: linear-gradient(135deg, #EC4899, #8B5CF6);
  color: white;

  &:hover { opacity: 0.9; transform: translateY(-1px); }
  &:disabled { cursor: not-allowed; transform: none !important; }

  &--done {
    background: rgba(16, 185, 129, 0.1);
    color: #10B981;
  }
}

.undo-btn {
  width: 100%;
  margin-top: $spacing-xs;
  padding: 4px;
  border: none;
  background: transparent;
  color: $text-muted;
  font-size: $font-size-xs;
  cursor: pointer;
  border-radius: $border-radius-sm;
  transition: all $transition-fast;

  &:hover { color: #EF4444; background: rgba(239, 68, 68, 0.06); }
}

// 自动打卡配置区
.auto-config {
  border: 1px dashed rgba(59, 130, 246, 0.3);
  border-radius: $border-radius-sm;
  padding: $spacing-md;
  margin-bottom: $spacing-md;
  background: rgba(59, 130, 246, 0.03);

  &__title {
    font-size: $font-size-xs;
    font-weight: 600;
    color: #3B82F6;
    margin-bottom: $spacing-sm;
  }

  &__hint {
    font-size: 10px;
    color: $text-muted;
    margin: 0;
  }

  .form-group { margin-bottom: $spacing-sm; }
}

// 共用
.empty-state {
  text-align: center;
  padding: $spacing-xxl;
  color: $text-secondary;
  &__icon { font-size: 48px; display: block; margin-bottom: $spacing-md; }
}

.loading {
  text-align: center;
  padding: $spacing-xxl;
  &__spinner {
    width: 40px; height: 40px;
    border: 3px solid $border-color;
    border-top-color: #EC4899;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto;
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
