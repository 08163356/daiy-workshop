<script setup lang="ts">
/**
 * 篮球反思看板
 */
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useBasketballStore } from '@/stores/useBasketballStore'
import SkillEvolutionTimeline from '@/components/basketball/SkillEvolutionTimeline.vue'

const router = useRouter()
const store = useBasketballStore()

onMounted(async () => {
  await Promise.all([store.fetchDashboard(), store.fetchSkillHistory(90)])
})

const dash = computed(() => store.dashboard)
const skill = computed(() => store.skillHistory)

const shootingRate = computed(() => {
  const r = dash.value?.avg_shooting_rate
  return r != null ? `${Math.round(r * 100)}%` : '—'
})

const goalProgress = computed(() => {
  const p = dash.value?.active_goal_progress
  if (!p) return null
  const todoPct = p.todos_total ? Math.round(p.todos_done / p.todos_total * 100) : 0
  const dayPct = p.days_total ? Math.round(p.days_passed / p.days_total * 100) : 0
  return { todoPct, dayPct, ...p }
})

function fmtTypeLabel(type: string) {
  return type === 'match' ? '比赛' : '散场'
}
</script>

<template>
  <div class="bb-dash">
    <!-- 顶部欢迎 -->
    <div class="bb-dash__hero">
      <div class="bb-dash__hero-text">
        <h1 class="bb-dash__title">🏀 篮球反思</h1>
        <p class="bb-dash__subtitle">认真复盘，让球场上的每一次失误，都不白吃。</p>
      </div>
      <button class="bb-dash__write-btn" @click="router.push('/basketball/new')">
        ✍️ 写新复盘
      </button>
    </div>

    <!-- 数字卡矩阵 -->
    <div class="bb-stats">
      <div class="bb-stat">
        <div class="bb-stat__num">{{ dash?.month_session_count ?? 0 }}</div>
        <div class="bb-stat__label">本月场次</div>
      </div>
      <div class="bb-stat">
        <div class="bb-stat__num">{{ dash?.month_total_minutes ?? 0 }}<span class="bb-stat__unit">min</span></div>
        <div class="bb-stat__label">本月总时长</div>
      </div>
      <div class="bb-stat">
        <div class="bb-stat__num">{{ shootingRate }}</div>
        <div class="bb-stat__label">平均命中率</div>
      </div>
      <div class="bb-stat">
        <div class="bb-stat__num">{{ dash?.streak_days ?? 0 }}<span class="bb-stat__unit">天</span></div>
        <div class="bb-stat__label">连续训练</div>
      </div>
    </div>

    <!-- 当前阶段目标 -->
    <div class="bb-goal" v-if="dash?.active_goal">
      <div class="bb-goal__head">
        <span class="bb-goal__badge">当前阶段目标</span>
        <span class="bb-goal__focus">焦点：{{ dash.active_goal.focus_area }}</span>
        <button class="bb-goal__btn" @click="router.push('/basketball/goals')">查看 →</button>
      </div>
      <div class="bb-goal__title">{{ dash.active_goal.title }}</div>
      <div v-if="dash.active_goal.description" class="bb-goal__desc">{{ dash.active_goal.description }}</div>
      <div v-if="goalProgress" class="bb-goal__progress">
        <div class="bb-goal__progress-row">
          <span class="bb-goal__progress-label">训练完成</span>
          <div class="bb-goal__bar"><div class="bb-goal__bar-fill" :style="{ width: goalProgress.todoPct + '%' }"></div></div>
          <span class="bb-goal__progress-text">{{ goalProgress.todos_done }}/{{ goalProgress.todos_total }}</span>
        </div>
        <div class="bb-goal__progress-row">
          <span class="bb-goal__progress-label">时间进度</span>
          <div class="bb-goal__bar"><div class="bb-goal__bar-fill bb-goal__bar-fill--time" :style="{ width: goalProgress.dayPct + '%' }"></div></div>
          <span class="bb-goal__progress-text">{{ goalProgress.days_passed }}/{{ goalProgress.days_total }}天</span>
        </div>
      </div>
    </div>
    <div v-else class="bb-goal bb-goal--empty" @click="router.push('/basketball/goals')">
      <span class="bb-goal__empty-icon">🎯</span>
      <span>暂无阶段目标，去让 AI 教练给你定一个 →</span>
    </div>

    <!-- 技术进化史 -->
    <div class="bb-section">
      <div class="bb-section__head">
        <h2 class="bb-section__title">📈 技术进化史</h2>
        <span class="bb-section__sub">近 90 天，看哪些维度从红→绿</span>
      </div>
      <SkillEvolutionTimeline :timeline="skill?.timeline || []" />
    </div>

    <!-- 进步 / 倒退 -->
    <div class="bb-changes" v-if="skill && (skill.top_progress.length || skill.top_regress.length)">
      <div class="bb-changes__col">
        <h3 class="bb-changes__title bb-changes__title--up">📈 进步 Top</h3>
        <div v-if="!skill.top_progress.length" class="bb-changes__empty">暂无明显进步项</div>
        <div v-for="p in skill.top_progress" :key="p.dim" class="bb-changes__item">
          <span class="bb-changes__dim">{{ p.dim }}</span>
          <span class="bb-changes__delta bb-changes__delta--up">+{{ p.delta }}</span>
        </div>
      </div>
      <div class="bb-changes__col">
        <h3 class="bb-changes__title bb-changes__title--down">📉 倒退 Top</h3>
        <div v-if="!skill.top_regress.length" class="bb-changes__empty">暂无明显倒退项</div>
        <div v-for="r in skill.top_regress" :key="r.dim" class="bb-changes__item">
          <span class="bb-changes__dim">{{ r.dim }}</span>
          <span class="bb-changes__delta bb-changes__delta--down">{{ r.delta }}</span>
        </div>
      </div>
    </div>

    <!-- 近 3 场速览 -->
    <div class="bb-section">
      <div class="bb-section__head">
        <h2 class="bb-section__title">📋 最近的复盘</h2>
        <button class="bb-section__more" @click="router.push('/basketball/list')">全部 →</button>
      </div>
      <div v-if="!dash?.recent_sessions.length" class="bb-recent-empty">
        <p>还没有复盘记录。</p>
        <button class="bb-section__more" @click="router.push('/basketball/new')">写第一篇 →</button>
      </div>
      <div v-else class="bb-recent">
        <div
          v-for="s in dash.recent_sessions"
          :key="s.id"
          class="bb-recent__card"
          @click="router.push(`/basketball/${s.id}`)"
        >
          <div class="bb-recent__head">
            <span class="bb-recent__type" :class="{ 'bb-recent__type--match': s.type === 'match' }">{{ fmtTypeLabel(s.type) }}</span>
            <span class="bb-recent__date">{{ s.date }}</span>
          </div>
          <div class="bb-recent__line">{{ s.one_line_summary }}</div>
          <div class="bb-recent__foot">
            <span v-if="s.duration_min">⏱ {{ s.duration_min }}min</span>
            <span v-if="s.shots_attempted">🎯 {{ s.shots_made }}/{{ s.shots_attempted }}</span>
            <span class="bb-recent__intensity">强度 {{ '★'.repeat(s.intensity) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.bb-dash {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px;
  display: flex; flex-direction: column;
  gap: 24px;
  background: linear-gradient(180deg, #FAF7F2 0%, #FFFFFF 200px);
  min-height: 100%;

  @media (max-width: 768px) {
    padding: 16px;
  }
}

.bb-dash__hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 28px;
  background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
  border-radius: 16px;
  color: white;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.15);

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
    padding: 20px;
  }
}

.bb-dash__title {
  font-size: 26px; font-weight: 700; margin: 0 0 4px 0;
  letter-spacing: 0.5px;
}

.bb-dash__subtitle {
  font-size: 14px; color: #94A3B8; margin: 0;
}

.bb-dash__write-btn {
  flex-shrink: 0;
  padding: 12px 22px;
  background: linear-gradient(135deg, #D97706, #B45309);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  box-shadow: 0 4px 12px rgba(217, 119, 6, 0.3);

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(217, 119, 6, 0.4);
  }
}

.bb-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;

  @media (max-width: 768px) {
    grid-template-columns: repeat(2, 1fr);
  }
}

.bb-stat {
  background: white;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 12px;
  padding: 18px 20px;
  transition: transform 0.2s, box-shadow 0.2s;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(217, 119, 6, 0.08);
  }

  &__num {
    font-size: 28px;
    font-weight: 700;
    color: #D97706;
    font-family: ui-monospace, monospace;
    margin-bottom: 4px;
  }

  &__unit {
    font-size: 14px;
    color: #94A3B8;
    margin-left: 2px;
    font-weight: 500;
  }

  &__label {
    font-size: 13px;
    color: #64748B;
  }
}

.bb-goal {
  background: white;
  border: 1px solid rgba(217, 119, 6, 0.15);
  border-left: 4px solid #D97706;
  border-radius: 12px;
  padding: 18px 22px;

  &--empty {
    cursor: pointer;
    background: rgba(217, 119, 6, 0.04);
    border-style: dashed;
    border-left-style: dashed;
    color: #94A3B8;
    text-align: center;
    padding: 20px;
    display: flex; align-items: center; justify-content: center; gap: 10px;

    &:hover {
      background: rgba(217, 119, 6, 0.08);
      color: #B45309;
    }
  }

  &__empty-icon {
    font-size: 24px;
  }

  &__head {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }

  &__badge {
    padding: 3px 10px;
    background: #D97706;
    color: white;
    font-size: 11px;
    font-weight: 600;
    border-radius: 4px;
  }

  &__focus {
    font-size: 12px;
    color: #94A3B8;
    flex: 1;
  }

  &__btn {
    padding: 4px 10px;
    background: transparent;
    border: 1px solid rgba(217, 119, 6, 0.3);
    color: #D97706;
    font-size: 12px;
    border-radius: 6px;
    cursor: pointer;

    &:hover { background: rgba(217, 119, 6, 0.1); }
  }

  &__title {
    font-size: 18px;
    font-weight: 700;
    color: #1F2937;
    margin-bottom: 4px;
  }

  &__desc {
    font-size: 13px;
    color: #64748B;
    line-height: 1.6;
    margin-bottom: 12px;
  }

  &__progress {
    display: flex; flex-direction: column; gap: 6px;
    margin-top: 12px;
  }

  &__progress-row {
    display: flex; align-items: center; gap: 10px;
  }

  &__progress-label {
    width: 70px;
    font-size: 12px;
    color: #64748B;
    flex-shrink: 0;
  }

  &__bar {
    flex: 1;
    height: 8px;
    background: #F1F5F9;
    border-radius: 4px;
    overflow: hidden;
  }

  &__bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #D97706, #F59E0B);
    transition: width 0.5s ease;

    &--time {
      background: linear-gradient(90deg, #1E40AF, #3B82F6);
    }
  }

  &__progress-text {
    font-size: 11px;
    font-family: ui-monospace, monospace;
    color: #94A3B8;
    width: 60px;
    text-align: right;
  }
}

.bb-section {
  display: flex; flex-direction: column; gap: 12px;
}

.bb-section__head {
  display: flex; align-items: baseline; justify-content: space-between;
}

.bb-section__title {
  font-size: 18px;
  font-weight: 700;
  color: #1F2937;
  margin: 0;
}

.bb-section__sub {
  font-size: 12px;
  color: #94A3B8;
}

.bb-section__more {
  background: transparent;
  border: none;
  color: #D97706;
  font-size: 13px;
  cursor: pointer;
  &:hover { color: #B45309; }
}

.bb-changes {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }

  &__col {
    background: white;
    border: 1px solid rgba(15, 23, 42, 0.06);
    border-radius: 12px;
    padding: 16px 20px;
  }

  &__title {
    font-size: 14px;
    font-weight: 700;
    margin: 0 0 10px 0;

    &--up { color: #16A34A; }
    &--down { color: #DC2626; }
  }

  &__empty {
    color: #94A3B8;
    font-size: 13px;
    padding: 8px 0;
  }

  &__item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 0;
  }

  &__dim {
    font-size: 14px;
    color: #1F2937;
  }

  &__delta {
    font-family: ui-monospace, monospace;
    font-size: 13px;
    font-weight: 700;

    &--up { color: #16A34A; }
    &--down { color: #DC2626; }
  }
}

.bb-recent {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
}

.bb-recent-empty {
  background: white;
  border: 1px dashed rgba(15, 23, 42, 0.1);
  border-radius: 12px;
  padding: 30px;
  text-align: center;
  color: #94A3B8;

  p { margin: 0 0 10px 0; }
}

.bb-recent__card {
  background: white;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 12px;
  padding: 14px 16px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(217, 119, 6, 0.1);
    border-color: rgba(217, 119, 6, 0.3);
  }
}

.bb-recent__head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}

.bb-recent__type {
  padding: 2px 8px;
  background: #D97706;
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;

  &--match {
    background: #DC2626;
  }
}

.bb-recent__date {
  font-size: 12px;
  color: #94A3B8;
  font-family: ui-monospace, monospace;
}

.bb-recent__line {
  font-size: 14px;
  color: #1F2937;
  line-height: 1.5;
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.bb-recent__foot {
  display: flex; gap: 12px;
  font-size: 11px;
  color: #94A3B8;
  flex-wrap: wrap;
}

.bb-recent__intensity {
  color: #D97706;
}
</style>
