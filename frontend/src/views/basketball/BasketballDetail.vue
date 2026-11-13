<script setup lang="ts">
/**
 * 复盘详情页 — 左用户原文，右教练点评+盲区
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBasketballStore } from '@/stores/useBasketballStore'
import CoachReviewCard from '@/components/basketball/CoachReviewCard.vue'
import BlindSpotsCard from '@/components/basketball/BlindSpotsCard.vue'

const route = useRoute()
const router = useRouter()
const store = useBasketballStore()

const regenerating = ref(false)
const deleting = ref(false)

onMounted(async () => {
  const id = Number(route.params.id)
  if (id) await store.fetchSession(id)
})

const s = computed(() => store.currentSession)

const shootingRate = computed(() => {
  if (!s.value?.shots_attempted) return null
  return Math.round((s.value.shots_made || 0) / s.value.shots_attempted * 100)
})

const isMatch = computed(() => s.value?.type === 'match')

const asyncReady = computed(() => {
  const st = s.value?.async_status || {}
  return {
    tech: st.tech === 'ok',
    highlights: st.highlights === 'ok',
    summary: st.summary === 'ok',
  }
})

async function regenerate() {
  if (!s.value) return
  regenerating.value = true
  try {
    await store.regenerateCoach(s.value.id)
  } finally {
    regenerating.value = false
  }
}

async function removeSession() {
  if (!s.value) return
  if (!confirm('确认删除这场复盘吗？教练的点评、技术抽取、关联待办都会保留（待办需手动清理）。')) return
  deleting.value = true
  try {
    const id = s.value.id
    const { deleteSession } = await import('@/api/basketball')
    await deleteSession(id)
    router.push('/basketball/list')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div v-if="s" class="bb-detail">
    <!-- 顶部 -->
    <header class="bb-detail__head">
      <button class="bb-detail__back" @click="router.back()">← 返回</button>
      <div class="bb-detail__title-group">
        <h1 class="bb-detail__title">
          <span class="bb-detail__type" :class="{ 'bb-detail__type--match': isMatch }">{{ isMatch ? '比赛' : '散场' }}</span>
          {{ s.date }} 篮球复盘
        </h1>
        <div class="bb-detail__meta">
          <span v-if="s.duration_min">⏱ {{ s.duration_min }}min</span>
          <span v-if="s.venue">📍 {{ s.venue }}</span>
          <span>强度 {{ '★'.repeat(s.intensity) }}</span>
          <span v-if="shootingRate != null">🎯 {{ s.shots_made }}/{{ s.shots_attempted }} ({{ shootingRate }}%)</span>
        </div>
      </div>
      <button class="bb-detail__del" @click="removeSession" :disabled="deleting">删除</button>
    </header>

    <!-- 内容栅格 -->
    <div class="bb-detail__grid">
      <!-- 左：用户原文 -->
      <div class="bb-detail__left">
        <div class="bb-detail__one-line">
          <span class="bb-detail__one-line-label">📝 一句话总结</span>
          <div class="bb-detail__one-line-text">{{ s.one_line_summary }}</div>
        </div>

        <div v-if="s.partners_desc" class="bb-detail__field">
          <span class="bb-detail__field-label">👥 一起打的人</span>
          <p class="bb-detail__field-text">{{ s.partners_desc }}</p>
        </div>

        <div v-if="s.highlights" class="bb-detail__field bb-detail__field--highlight">
          <span class="bb-detail__field-label">✨ 技术亮点</span>
          <p class="bb-detail__field-text">{{ s.highlights }}</p>
        </div>

        <div v-if="s.problems" class="bb-detail__field bb-detail__field--problem">
          <span class="bb-detail__field-label">🚧 技术问题</span>
          <p class="bb-detail__field-text">{{ s.problems }}</p>
        </div>

        <div v-if="s.key_moments" class="bb-detail__field">
          <span class="bb-detail__field-label">🎯 关键回合</span>
          <p class="bb-detail__field-text">{{ s.key_moments }}</p>
        </div>

        <div v-if="s.emotion" class="bb-detail__field">
          <span class="bb-detail__field-label">💭 场上情绪</span>
          <p class="bb-detail__field-text">{{ s.emotion }}</p>
        </div>

        <!-- 比赛字段 -->
        <template v-if="isMatch">
          <hr class="bb-detail__divider" />
          <div v-if="s.opponent" class="bb-detail__field">
            <span class="bb-detail__field-label">🏆 对手</span>
            <p class="bb-detail__field-text">{{ s.opponent }}</p>
          </div>
          <div v-if="s.matchup" class="bb-detail__field">
            <span class="bb-detail__field-label">⚔️ 对位</span>
            <p class="bb-detail__field-text">{{ s.matchup }}</p>
          </div>
          <div v-if="s.team_score != null" class="bb-detail__field">
            <span class="bb-detail__field-label">📊 比分</span>
            <p class="bb-detail__field-text bb-detail__score" :class="{ 'bb-detail__score--win': (s.team_score || 0) > (s.opp_score || 0) }">
              {{ s.team_score }} : {{ s.opp_score }}
              <span v-if="s.my_play_minutes != null" class="bb-detail__minutes">（我上 {{ s.my_play_minutes }} 分钟）</span>
            </p>
          </div>
          <div v-if="s.decisive_moment" class="bb-detail__field">
            <span class="bb-detail__field-label">⚡ 决胜时刻</span>
            <p class="bb-detail__field-text">{{ s.decisive_moment }}</p>
          </div>
          <div v-if="s.team_observation" class="bb-detail__field">
            <span class="bb-detail__field-label">🤝 团队观察</span>
            <p class="bb-detail__field-text">{{ s.team_observation }}</p>
          </div>
        </template>
      </div>

      <!-- 右：AI 产物 -->
      <div class="bb-detail__right">
        <CoachReviewCard
          :review="s.coach_review"
          :model-name="s.coach_model"
          :loading="regenerating"
        />
        <button class="bb-detail__regen" @click="regenerate" :disabled="regenerating">
          {{ regenerating ? '教练正在重看…' : '🔁 让教练重新看一遍' }}
        </button>

        <BlindSpotsCard :blind-spots="s.blind_spots" />

        <!-- 异步任务状态 -->
        <div class="bb-detail__async">
          <h3 class="bb-detail__async-title">⚙️ 后台增强</h3>
          <div class="bb-detail__async-grid">
            <div class="bb-detail__async-item" :class="{ 'bb-detail__async-item--ok': asyncReady.tech }">
              <span class="bb-detail__async-icon">{{ asyncReady.tech ? '✓' : '⏳' }}</span>
              <span>技术维度抽取</span>
            </div>
            <div class="bb-detail__async-item" :class="{ 'bb-detail__async-item--ok': asyncReady.highlights }">
              <span class="bb-detail__async-icon">{{ asyncReady.highlights ? '✓' : '⏳' }}</span>
              <span>高光时刻入心力</span>
            </div>
            <div class="bb-detail__async-item" :class="{ 'bb-detail__async-item--ok': asyncReady.summary }">
              <span class="bb-detail__async-icon">{{ asyncReady.summary ? '✓' : '⏳' }}</span>
              <span>同步到当天日记</span>
            </div>
          </div>
          <p class="bb-detail__async-hint">这些任务在后台运行（约需 10-30 秒）。刷新页面可看最新状态。</p>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="bb-detail__loading">加载中…</div>
</template>

<style lang="scss" scoped>
.bb-detail {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px;
  display: flex; flex-direction: column;
  gap: 18px;
  background: linear-gradient(180deg, #FAF7F2 0%, #FFFFFF 200px);
  min-height: 100%;
}

.bb-detail__loading {
  text-align: center;
  padding: 80px 20px;
  color: #94A3B8;
}

.bb-detail__head {
  display: flex; align-items: center; gap: 14px;

  @media (max-width: 768px) {
    flex-wrap: wrap;
  }
}

.bb-detail__back {
  background: transparent;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
  color: #64748B;
  cursor: pointer;
  flex-shrink: 0;
  &:hover { background: white; }
}

.bb-detail__title-group {
  flex: 1;
}

.bb-detail__title {
  font-size: 18px;
  font-weight: 700;
  color: #1F2937;
  margin: 0 0 6px 0;
  display: flex; align-items: center; gap: 10px;
  flex-wrap: wrap;
}

.bb-detail__type {
  padding: 2px 10px;
  background: #D97706;
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;

  &--match { background: #DC2626; }
}

.bb-detail__meta {
  display: flex; gap: 14px;
  font-size: 12px;
  color: #94A3B8;
  flex-wrap: wrap;
}

.bb-detail__del {
  background: transparent;
  border: 1px solid rgba(220, 38, 38, 0.3);
  color: #DC2626;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;

  &:hover { background: rgba(220, 38, 38, 0.05); }
  &:disabled { opacity: 0.6; }
}

.bb-detail__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;

  @media (max-width: 968px) {
    grid-template-columns: 1fr;
  }
}

.bb-detail__left,
.bb-detail__right {
  display: flex; flex-direction: column; gap: 12px;
}

.bb-detail__one-line {
  background: white;
  border: 2px solid rgba(217, 119, 6, 0.2);
  border-radius: 12px;
  padding: 14px 18px;

  &-label {
    font-size: 11px;
    color: #B45309;
    font-weight: 600;
    letter-spacing: 0.3px;
  }

  &-text {
    font-size: 17px;
    color: #1F2937;
    font-weight: 600;
    line-height: 1.5;
    margin-top: 4px;
  }
}

.bb-detail__field {
  background: white;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 10px;
  padding: 12px 16px;

  &-label {
    font-size: 12px;
    color: #64748B;
    font-weight: 600;
  }

  &-text {
    font-size: 14px;
    color: #1F2937;
    line-height: 1.7;
    margin: 6px 0 0 0;
    white-space: pre-wrap;
  }

  &--highlight {
    border-left: 3px solid #16A34A;
  }

  &--problem {
    border-left: 3px solid #DC2626;
  }
}

.bb-detail__divider {
  border: none;
  border-top: 1px dashed rgba(15, 23, 42, 0.1);
  margin: 6px 0;
}

.bb-detail__score {
  font-family: ui-monospace, monospace;
  font-size: 18px;
  font-weight: 700;
  color: #DC2626;

  &--win {
    color: #16A34A;
  }
}

.bb-detail__minutes {
  font-size: 12px;
  color: #94A3B8;
  font-family: inherit;
  font-weight: 400;
  margin-left: 8px;
}

.bb-detail__regen {
  background: white;
  border: 1px dashed rgba(217, 119, 6, 0.4);
  color: #B45309;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 12px;
  cursor: pointer;
  align-self: flex-start;
  font-family: inherit;

  &:hover:not(:disabled) {
    background: rgba(217, 119, 6, 0.06);
  }
  &:disabled { opacity: 0.6; cursor: not-allowed; }
}

.bb-detail__async {
  background: #F8FAFC;
  border-radius: 10px;
  padding: 12px 16px;
  border: 1px dashed rgba(15, 23, 42, 0.1);

  &-title {
    font-size: 12px;
    font-weight: 600;
    color: #64748B;
    margin: 0 0 8px 0;
  }

  &-grid {
    display: flex; flex-direction: column; gap: 4px;
  }

  &-item {
    display: flex; align-items: center; gap: 8px;
    font-size: 12px;
    color: #94A3B8;

    &--ok { color: #16A34A; }
  }

  &-icon {
    font-family: ui-monospace, monospace;
    width: 16px;
    text-align: center;
  }

  &-hint {
    margin-top: 6px;
    font-size: 11px;
    color: #94A3B8;
    line-height: 1.5;
  }
}
</style>
