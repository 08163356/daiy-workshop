<script setup lang="ts">
/**
 * 对话页就地打开的待办预览抽屉：不离开 /assistant。
 * 只覆盖查看 + 轻操作（切完成、看子任务）；完整编辑仍可跳日历。
 */
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { TODO_API_BASE } from '@/config'

const props = defineProps<{ todoId: number | null }>()
const emit = defineEmits<{ close: [] }>()

const router = useRouter()
const loading = ref(false)
const error = ref('')
const item = ref<any | null>(null)
const children = ref<any[]>([])
const parentStack = ref<number[]>([])
const descOpen = ref(false)
const evalOpen = ref(false)

const quadrantName: Record<number, string> = {
  1: '重要紧急',
  2: '重要不紧急',
  3: '紧急不重要',
  4: '不紧急不重要',
}
const statusLabel: Record<string, string> = {
  pending: '待办',
  in_progress: '进行中',
  completed: '已完成',
  cancelled: '已取消',
}

async function load(id: number) {
  loading.value = true
  error.value = ''
  item.value = null
  children.value = []
  descOpen.value = false
  evalOpen.value = false
  try {
    const [detailRes, childRes] = await Promise.all([
      fetch(`${TODO_API_BASE}/${id}`),
      fetch(`${TODO_API_BASE}/${id}/children`),
    ])
    if (!detailRes.ok) throw new Error('任务不存在或加载失败')
    item.value = await detailRes.json()
    if (childRes.ok) children.value = await childRes.json()
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

watch(
  () => props.todoId,
  (id) => {
    parentStack.value = []
    if (id != null) load(id)
  },
  { immediate: true },
)

async function toggleComplete() {
  if (!item.value || item.value.status === 'cancelled') return
  const next = item.value.status === 'completed' ? 'pending' : 'completed'
  try {
    const res = await fetch(`${TODO_API_BASE}/${item.value.id}/toggle`, { method: 'PATCH' })
    if (res.ok) {
      const data = await res.json()
      item.value = { ...item.value, ...data }
    } else {
      const res2 = await fetch(`${TODO_API_BASE}/${item.value.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: next }),
      })
      if (res2.ok) item.value = { ...item.value, status: next }
    }
  } catch { /* ignore */ }
}

function openChild(id: number) {
  if (item.value?.id) parentStack.value.push(item.value.id)
  load(id)
}

function backToParent() {
  const pid = parentStack.value.pop()
  if (pid) load(pid)
}

function openInCalendar() {
  if (!item.value) return
  emit('close')
  router.push({ path: '/todo/calendar', query: { open: String(item.value.id) } })
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="todoId != null"
      class="todo-peek"
      @keydown="onKey"
    >
      <div class="todo-peek__mask" @click="emit('close')" />
      <aside class="todo-peek__panel" role="dialog" aria-label="待办详情" tabindex="-1">
        <header class="todo-peek__head">
          <h3>待办详情</h3>
          <div class="todo-peek__head-actions">
            <button v-if="parentStack.length" class="todo-peek__link" type="button" @click="backToParent">返回父任务</button>
            <button class="todo-peek__link" type="button" @click="openInCalendar">在日历打开</button>
            <button class="todo-peek__close" type="button" title="关闭" @click="emit('close')"><Close class="ep-icon" /></button>
          </div>
        </header>

        <div v-if="loading" class="todo-peek__state">加载中…</div>
        <div v-else-if="error" class="todo-peek__state todo-peek__state--err">{{ error }}</div>
        <div v-else-if="item" class="todo-peek__body">
          <h4 class="todo-peek__title">{{ item.title }}</h4>
          <div class="todo-peek__tags">
            <span class="todo-peek__tag">{{ quadrantName[item.quadrant] || `Q${item.quadrant}` }}</span>
            <span class="todo-peek__tag">{{ statusLabel[item.status] || item.status }}</span>
            <span v-if="item.category" class="todo-peek__tag">{{ item.category }}</span>
          </div>

          <div class="todo-peek__meta">
            <div v-if="item.scheduled_date">
              <span class="todo-peek__meta-k">计划</span>
              {{ item.scheduled_date }}{{ item.scheduled_end_date ? ` ~ ${item.scheduled_end_date}` : '' }}
            </div>
            <div v-if="item.due_date">
              <span class="todo-peek__meta-k">截止</span>
              {{ item.due_date }}
            </div>
            <div v-if="item.estimated_minutes">
              <span class="todo-peek__meta-k">预估</span>
              {{ item.estimated_minutes }} min
            </div>
          </div>

          <div v-if="item.description" class="todo-peek__block">
            <button type="button" class="todo-peek__toggle" @click="descOpen = !descOpen">
              {{ descOpen ? '▼ 收起描述' : '▶ 描述' }}
            </button>
            <p v-if="descOpen" class="todo-peek__text">{{ item.description }}</p>
          </div>

          <div v-if="item.ai_evaluation || item.original_text" class="todo-peek__block">
            <button type="button" class="todo-peek__toggle" @click="evalOpen = !evalOpen">
              {{ evalOpen ? '▼ 收起 AI 评估' : '▶ 原始输入 / AI 评估' }}
            </button>
            <template v-if="evalOpen">
              <p v-if="item.original_text" class="todo-peek__text"><strong>原始：</strong>{{ item.original_text }}</p>
              <p v-if="item.ai_evaluation" class="todo-peek__text"><strong>评估：</strong>{{ item.ai_evaluation }}</p>
            </template>
          </div>

          <div v-if="children.length" class="todo-peek__block">
            <div class="todo-peek__label">子任务 ({{ children.length }})</div>
            <ul class="todo-peek__children">
              <li
                v-for="c in children"
                :key="c.id"
                :class="{ 'is-done': c.status === 'completed' }"
              >
                <button type="button" class="todo-peek__child" @click="openChild(c.id)">
                  <span class="todo-peek__child-mark">{{ c.status === 'completed' ? '✓' : '○' }}</span>
                  {{ c.title }}
                  <small v-if="c.urgency">紧急{{ c.urgency }}</small>
                </button>
              </li>
            </ul>
          </div>

          <div class="todo-peek__actions">
            <button
              v-if="item.status !== 'cancelled'"
              type="button"
              class="todo-peek__btn"
              @click="toggleComplete"
            >
              {{ item.status === 'completed' ? '标为未完成' : '标为完成' }}
            </button>
          </div>
        </div>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.todo-peek {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  justify-content: flex-end;
}

.todo-peek__mask {
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.28);
}

.todo-peek__panel {
  position: relative;
  width: min(420px, 100vw);
  height: 100%;
  background: #fff;
  box-shadow: -8px 0 32px rgba(15, 23, 42, 0.12);
  display: flex;
  flex-direction: column;
  outline: none;
}

.todo-peek__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 16px;
  border-bottom: 1px solid $border-color;

  h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
  }
}

.todo-peek__head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.todo-peek__link {
  border: none;
  background: transparent;
  color: $primary-color;
  font-size: 12px;
  cursor: pointer;
  padding: 4px 6px;
}

.todo-peek__close {
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 4px;
  color: $text-muted;
}

.todo-peek__body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.todo-peek__state {
  padding: 32px 16px;
  text-align: center;
  color: $text-muted;
  font-size: 13px;

  &--err { color: #EF4444; }
}

.todo-peek__title {
  margin: 0 0 10px;
  font-size: 17px;
  line-height: 1.4;
  color: $text-primary;
}

.todo-peek__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.todo-peek__tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.04);
  color: $text-secondary;
}

.todo-peek__meta {
  display: grid;
  gap: 6px;
  margin-bottom: 14px;
  font-size: 12px;
  color: $text-secondary;
}

.todo-peek__meta-k {
  display: inline-block;
  min-width: 2.5em;
  color: $text-muted;
  margin-right: 6px;
}

.todo-peek__block {
  margin-bottom: 14px;
}

.todo-peek__toggle {
  border: none;
  background: transparent;
  color: $text-muted;
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  margin-bottom: 6px;
}

.todo-peek__label {
  font-size: 12px;
  font-weight: 600;
  color: $text-secondary;
  margin-bottom: 8px;
}

.todo-peek__text {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.6;
  color: $text-secondary;
  white-space: pre-wrap;
  word-break: break-word;
}

.todo-peek__children {
  list-style: none;
  margin: 0;
  padding: 0;

  li {
    border-bottom: 1px solid rgba(0, 0, 0, 0.04);
    &.is-done .todo-peek__child { color: $text-muted; text-decoration: line-through; }
  }
}

.todo-peek__child {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  border: none;
  background: transparent;
  text-align: left;
  padding: 8px 0;
  font-size: 13px;
  color: $text-primary;
  cursor: pointer;
  line-height: 1.4;
}

.todo-peek__child-mark {
  flex-shrink: 0;
  color: $text-muted;
  width: 1em;
}

.todo-peek__actions {
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px solid $border-color;
}

.todo-peek__btn {
  border: 1px solid $border-color;
  background: #fff;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  cursor: pointer;
  color: $text-primary;

  &:hover { border-color: $primary-color; color: $primary-color; }
}

@media (max-width: 640px) {
  .todo-peek__panel { width: 100vw; }
}
</style>
