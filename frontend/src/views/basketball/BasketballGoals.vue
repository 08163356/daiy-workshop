<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useBasketballStore } from '@/stores/useBasketballStore'

const router = useRouter()
const store = useBasketballStore()

const generating = ref(false)
const evaluating = ref<number | null>(null)
const showGenerated = ref<any | null>(null)
const error = ref('')
const weeks = ref(2)
const createTodos = ref(true)

onMounted(async () => {
  await Promise.all([store.fetchActiveGoal(), store.fetchGoals()])
})

const active = computed(() => store.activeGoal)
const history = computed(() => store.goals.filter(g => g.status !== 'active'))

async function generate() {
  generating.value = true
  error.value = ''
  try {
    const res = await store.generateNextGoal(weeks.value, createTodos.value)
    showGenerated.value = res
    await store.fetchGoals()
  } catch (e: any) {
    error.value = e?.message || '生成失败'
  } finally {
    generating.value = false
  }
}

async function evaluateGoal(id: number) {
  evaluating.value = id
  try {
    await store.evaluateGoal(id)
    await Promise.all([store.fetchActiveGoal(), store.fetchGoals()])
  } finally {
    evaluating.value = null
  }
}
</script>

<template>
  <div class="bb-goals">
    <header class="bb-goals__head">
      <button class="bb-goals__back" @click="router.back()">← 返回</button>
      <h1 class="bb-goals__title">🎯 阶段训练目标</h1>
    </header>

    <!-- Active 目标卡 -->
    <div v-if="active" class="bb-goals__active">
      <div class="bb-goals__active-top">
        <span class="bb-goals__badge">进行中</span>
        <span class="bb-goals__period">{{ active.start_date }} → {{ active.end_date }}</span>
      </div>
      <h2 class="bb-goals__active-title">{{ active.title }}</h2>
      <div class="bb-goals__focus-row">
        <span class="bb-goals__focus-label">焦点</span>
        <span class="bb-goals__focus-tag">{{ active.focus_area }}</span>
      </div>
      <p v-if="active.description" class="bb-goals__desc">{{ active.description }}</p>

      <div v-if="active.related_todo_ids && active.related_todo_ids.length" class="bb-goals__todos">
        <span class="bb-goals__todos-icon">📋</span>
        <span>已派单 {{ active.related_todo_ids.length }} 项训练待办</span>
        <button class="bb-goals__link" @click="router.push('/todo/list')">去看 →</button>
      </div>

      <button
        class="bb-goals__btn-eval"
        @click="evaluateGoal(active.id)"
        :disabled="evaluating === active.id"
      >
        {{ evaluating === active.id ? '教练正在评价…' : '✓ 阶段已结束，让教练评价' }}
      </button>
    </div>

    <!-- 无 active：生成入口 -->
    <div v-else class="bb-goals__gen">
      <div class="bb-goals__gen-icon">🏀</div>
      <h2 class="bb-goals__gen-title">还没有训练目标</h2>
      <p class="bb-goals__gen-sub">让 AI 教练基于你最近 30 天的复盘，定一个聚焦的阶段目标。</p>

      <div class="bb-goals__gen-form">
        <label class="bb-goals__gen-field">
          <span>阶段长度</span>
          <select v-model.number="weeks" class="bb-goals__gen-select">
            <option :value="1">1 周</option>
            <option :value="2">2 周（推荐）</option>
            <option :value="3">3 周</option>
            <option :value="4">4 周</option>
          </select>
        </label>
        <label class="bb-goals__gen-check">
          <input type="checkbox" v-model="createTodos" />
          <span>自动生成训练待办</span>
        </label>
      </div>

      <button class="bb-goals__gen-btn" @click="generate" :disabled="generating">
        {{ generating ? '教练正在思考…（5-8 秒）' : '让 AI 教练给我定下一阶段目标 →' }}
      </button>

      <div v-if="error" class="bb-goals__error">{{ error }}</div>
    </div>

    <!-- 历史目标 -->
    <div v-if="history.length" class="bb-goals__history">
      <h2 class="bb-goals__history-title">📜 历史目标</h2>
      <div class="bb-goals__history-list">
        <div v-for="g in history" :key="g.id" class="bb-goals__history-card">
          <div class="bb-goals__history-head">
            <span class="bb-goals__history-status" :class="`bb-goals__history-status--${g.status}`">
              {{ g.status === 'done' ? '已完成' : '已放弃' }}
            </span>
            <span class="bb-goals__history-period">{{ g.start_date }} → {{ g.end_date }}</span>
            <span class="bb-goals__history-focus">{{ g.focus_area }}</span>
          </div>
          <h3 class="bb-goals__history-name">{{ g.title }}</h3>
          <div v-if="g.ai_evaluation" class="bb-goals__history-eval">
            <span class="bb-goals__history-eval-tag">教练评价</span>
            <p>{{ g.ai_evaluation }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 生成成功 modal -->
    <div v-if="showGenerated" class="bb-goals__modal-overlay" @click.self="showGenerated = null">
      <div class="bb-goals__modal">
        <h3 class="bb-goals__modal-title">🎯 教练给你定的下一阶段</h3>
        <div class="bb-goals__modal-goal">
          <h4>{{ showGenerated.goal.title }}</h4>
          <div class="bb-goals__modal-focus">焦点：{{ showGenerated.goal.focus_area }}</div>
          <p v-if="showGenerated.goal.description">{{ showGenerated.goal.description }}</p>
        </div>
        <div class="bb-goals__modal-summary">
          <strong>教练说：</strong>{{ showGenerated.summary }}
        </div>
        <div v-if="showGenerated.todos_created > 0" class="bb-goals__modal-todos">
          ✓ 已自动派单 {{ showGenerated.todos_created }} 项训练待办到待办系统
        </div>
        <button class="bb-goals__modal-close" @click="showGenerated = null">收到 →</button>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.bb-goals {
  max-width: 980px;
  margin: 0 auto;
  padding: 24px;
  display: flex; flex-direction: column; gap: 18px;
  background: linear-gradient(180deg, #FAF7F2 0%, #FFFFFF 200px);
  min-height: 100%;
}

.bb-goals__head {
  display: flex; align-items: center; gap: 14px;
}

.bb-goals__back {
  background: transparent;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
  color: #64748B;
  cursor: pointer;
  &:hover { background: white; }
}

.bb-goals__title {
  font-size: 22px; font-weight: 700; color: #1F2937; margin: 0;
}

.bb-goals__active {
  background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
  color: white;
  border-radius: 16px;
  padding: 24px 28px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    top: -40px; right: -40px;
    width: 120px; height: 120px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(217, 119, 6, 0.3) 0%, transparent 70%);
  }

  &-top {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 12px;
  }

  &-title {
    font-size: 24px;
    font-weight: 700;
    margin: 0 0 12px 0;
    line-height: 1.4;
  }
}

.bb-goals__badge {
  padding: 3px 10px;
  background: #D97706;
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
}

.bb-goals__period {
  font-size: 12px;
  color: #94A3B8;
  font-family: ui-monospace, monospace;
}

.bb-goals__focus-row {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px;
}

.bb-goals__focus-label {
  font-size: 12px;
  color: #94A3B8;
}

.bb-goals__focus-tag {
  padding: 4px 12px;
  background: rgba(217, 119, 6, 0.2);
  color: #FBBF24;
  font-size: 13px;
  font-weight: 600;
  border-radius: 6px;
}

.bb-goals__desc {
  font-size: 14px;
  color: #CBD5E1;
  line-height: 1.7;
  margin: 0 0 16px 0;
}

.bb-goals__todos {
  display: flex; align-items: center; gap: 10px;
  background: rgba(255, 255, 255, 0.06);
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;

  &-icon { font-size: 16px; }
}

.bb-goals__link {
  background: transparent;
  border: none;
  color: #FBBF24;
  font-size: 13px;
  cursor: pointer;
  margin-left: auto;
  font-family: inherit;
  &:hover { color: #F59E0B; }
}

.bb-goals__btn-eval {
  width: 100%;
  background: rgba(217, 119, 6, 0.2);
  border: 1px solid rgba(217, 119, 6, 0.4);
  color: #FBBF24;
  border-radius: 8px;
  padding: 10px;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 600;

  &:hover:not(:disabled) {
    background: rgba(217, 119, 6, 0.3);
  }
  &:disabled { opacity: 0.6; cursor: not-allowed; }
}

.bb-goals__gen {
  background: white;
  border: 2px dashed rgba(217, 119, 6, 0.3);
  border-radius: 16px;
  padding: 36px 28px;
  text-align: center;
  display: flex; flex-direction: column; align-items: center; gap: 12px;

  &-icon {
    font-size: 56px;
    margin-bottom: 4px;
  }

  &-title {
    font-size: 20px;
    font-weight: 700;
    color: #1F2937;
    margin: 0;
  }

  &-sub {
    color: #64748B;
    font-size: 14px;
    margin: 0;
  }

  &-form {
    display: flex; gap: 18px; align-items: center;
    margin: 12px 0;
    flex-wrap: wrap;
    justify-content: center;
  }

  &-field {
    display: flex; gap: 8px; align-items: center;
    font-size: 13px;
    color: #64748B;
  }

  &-select {
    border: 1px solid rgba(15, 23, 42, 0.1);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 13px;
    background: white;
    cursor: pointer;
  }

  &-check {
    display: flex; align-items: center; gap: 6px;
    font-size: 13px;
    color: #64748B;
    cursor: pointer;
  }

  &-btn {
    background: linear-gradient(135deg, #D97706, #B45309);
    color: white;
    border: none;
    border-radius: 10px;
    padding: 12px 28px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 6px 20px rgba(217, 119, 6, 0.3);

    &:hover:not(:disabled) {
      transform: translateY(-2px);
      box-shadow: 0 10px 28px rgba(217, 119, 6, 0.4);
    }
    &:disabled { opacity: 0.6; cursor: not-allowed; }
  }
}

.bb-goals__error {
  color: #DC2626;
  font-size: 13px;
  background: rgba(220, 38, 38, 0.06);
  padding: 8px 14px;
  border-radius: 6px;
  margin-top: 8px;
}

.bb-goals__history {
  &-title {
    font-size: 16px;
    font-weight: 700;
    color: #1F2937;
    margin: 0 0 12px 0;
  }

  &-list {
    display: flex; flex-direction: column; gap: 10px;
  }

  &-card {
    background: white;
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 10px;
    padding: 14px 18px;
  }

  &-head {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 6px;
    flex-wrap: wrap;
  }

  &-status {
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
    border-radius: 4px;

    &--done {
      background: rgba(22, 163, 74, 0.1);
      color: #16A34A;
    }

    &--abandoned {
      background: rgba(148, 163, 184, 0.15);
      color: #64748B;
    }
  }

  &-period {
    font-size: 11px;
    color: #94A3B8;
    font-family: ui-monospace, monospace;
  }

  &-focus {
    font-size: 11px;
    padding: 1px 8px;
    background: rgba(217, 119, 6, 0.1);
    color: #B45309;
    border-radius: 4px;
    margin-left: auto;
  }

  &-name {
    font-size: 15px;
    color: #1F2937;
    margin: 0 0 8px 0;
    font-weight: 600;
  }

  &-eval {
    background: rgba(30, 64, 175, 0.04);
    border-left: 2px solid #1E40AF;
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 12px;
    line-height: 1.6;

    &-tag {
      display: inline-block;
      padding: 1px 6px;
      background: #1E40AF;
      color: white;
      font-size: 10px;
      border-radius: 3px;
      margin-right: 8px;
      font-weight: 600;
    }

    p { margin: 0; color: #475569; display: inline; }
  }
}

.bb-goals__modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.bb-goals__modal {
  background: white;
  border-radius: 16px;
  padding: 28px 32px;
  max-width: 520px;
  width: 100%;
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.2);
  animation: modal-in 0.3s ease-out;

  &-title {
    font-size: 18px;
    font-weight: 700;
    color: #1F2937;
    margin: 0 0 16px 0;
  }

  &-goal {
    background: linear-gradient(135deg, #FFF8F0, #FEF3E2);
    border-left: 4px solid #D97706;
    border-radius: 8px;
    padding: 14px 18px;
    margin-bottom: 14px;

    h4 {
      font-size: 16px;
      color: #1F2937;
      margin: 0 0 6px 0;
      font-weight: 700;
    }

    p {
      font-size: 13px;
      color: #475569;
      line-height: 1.6;
      margin: 6px 0 0 0;
    }
  }

  &-focus {
    display: inline-block;
    padding: 2px 10px;
    background: rgba(217, 119, 6, 0.15);
    color: #B45309;
    font-size: 11px;
    font-weight: 600;
    border-radius: 4px;
  }

  &-summary {
    font-size: 13px;
    color: #475569;
    line-height: 1.7;
    padding: 12px 14px;
    background: #F8FAFC;
    border-radius: 8px;
    margin-bottom: 14px;

    strong { color: #1F2937; margin-right: 6px; }
  }

  &-todos {
    font-size: 12px;
    color: #16A34A;
    background: rgba(22, 163, 74, 0.06);
    padding: 8px 14px;
    border-radius: 6px;
    margin-bottom: 14px;
  }

  &-close {
    width: 100%;
    background: linear-gradient(135deg, #D97706, #B45309);
    color: white;
    border: none;
    border-radius: 10px;
    padding: 10px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }
}

@keyframes modal-in {
  from { opacity: 0; transform: scale(0.95); }
  to   { opacity: 1; transform: scale(1); }
}
</style>
