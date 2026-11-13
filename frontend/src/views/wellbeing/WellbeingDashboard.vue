<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWellbeingStore } from '@/stores/useWellbeingStore'
import wellbeingApi, { type WellbeingEntry } from '@/api/wellbeing'

const router = useRouter()
const store = useWellbeingStore()

const showQuickAdd = ref(false)
const quickType = ref<'achievement' | 'gratitude'>('achievement')
const quickContent = ref('')
const quickIntensity = ref(3)
const quickCategory = ref('')
const quickDate = ref(new Date().toISOString().slice(0, 10))
const submitting = ref(false)

const flipCard = ref<WellbeingEntry | null>(null)
const flipping = ref(false)

const CATEGORIES = ['工作', '家庭', '健康', '关系', '学习', '其他']

const overview = computed(() => store.overview)

async function loadAll() {
  await store.fetchOverview()
}

async function pickRandomEntry() {
  flipping.value = true
  flipCard.value = null
  try {
    const res = await wellbeingApi.listEntries({ limit: 100 })
    if (res.items.length === 0) {
      flipCard.value = null
    } else {
      const idx = Math.floor(Math.random() * res.items.length)
      flipCard.value = res.items[idx]
    }
  } finally {
    setTimeout(() => { flipping.value = false }, 200)
  }
}

async function submitQuick() {
  if (!quickContent.value.trim()) return
  submitting.value = true
  try {
    await store.createEntry({
      type: quickType.value,
      content: quickContent.value.trim(),
      category: quickCategory.value || null,
      intensity: quickIntensity.value,
      occurred_at: quickDate.value,
      source_type: 'manual',
    })
    quickContent.value = ''
    quickCategory.value = ''
    quickIntensity.value = 3
    showQuickAdd.value = false
    await store.fetchOverview()
  } catch (e: any) {
    alert(e.message || '保存失败')
  } finally {
    submitting.value = false
  }
}

function maxTrend() {
  if (!overview.value) return 1
  let m = 1
  for (const p of overview.value.trend_90d) {
    m = Math.max(m, p.achievement + p.gratitude)
  }
  return m
}

onMounted(loadAll)
</script>

<template>
  <div class="wb-dashboard">
    <!-- 顶部欢迎条 -->
    <div class="wb-hero">
      <div class="wb-hero__text">
        <div class="wb-hero__title"><Lightning class="ep-icon" /> 心力账户</div>
        <div class="wb-hero__sub" v-if="overview">
          你已经积累了 <strong>{{ overview.total_achievement }}</strong> 个成就 ·
          <strong>{{ overview.total_gratitude }}</strong> 份感恩
        </div>
        <div class="wb-hero__sub" v-else>正在加载你的心力账户…</div>
      </div>
      <div class="wb-hero__actions">
        <button class="btn-primary" @click="showQuickAdd = !showQuickAdd">
          ＋ 快速记一条
        </button>
        <button class="btn-ghost" @click="router.push('/wellbeing/anxiety')">🌿 焦虑模式</button>
      </div>
    </div>

    <!-- 快速录入 -->
    <Transition name="slide">
      <div v-if="showQuickAdd" class="wb-quick">
        <div class="wb-quick__row">
          <button
            class="wb-quick__type"
            :class="{ 'wb-quick__type--active': quickType === 'achievement' }"
            @click="quickType = 'achievement'"
          ><Trophy class="ep-icon" /> 成就</button>
          <button
            class="wb-quick__type"
            :class="{ 'wb-quick__type--active': quickType === 'gratitude' }"
            @click="quickType = 'gratitude'"
          >🙏 感恩</button>
        </div>
        <textarea
          v-model="quickContent"
          rows="2"
          placeholder="一句话写下这件事，比如：今天 6 点起床完成了晨跑"
        />
        <div class="wb-quick__row">
          <select v-model="quickCategory">
            <option value="">无分类</option>
            <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
          </select>
          <input type="date" v-model="quickDate" />
          <div class="wb-quick__stars">
            <span
              v-for="n in 5"
              :key="n"
              class="wb-quick__star"
              :class="{ 'wb-quick__star--on': n <= quickIntensity }"
              @click="quickIntensity = n"
            >★</span>
          </div>
          <button class="btn-primary" :disabled="submitting" @click="submitQuick">
            {{ submitting ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </Transition>

    <div v-if="store.loading && !overview" class="wb-loading">加载中…</div>

    <template v-else-if="overview">
      <!-- 数字卡片矩阵 -->
      <div class="wb-stats">
        <div class="wb-stat wb-stat--ach">
          <div class="wb-stat__icon"><Trophy class="ep-icon" /></div>
          <div class="wb-stat__value">{{ overview.total_achievement }}</div>
          <div class="wb-stat__label">累计成就</div>
        </div>
        <div class="wb-stat wb-stat--grat">
          <div class="wb-stat__icon">🙏</div>
          <div class="wb-stat__value">{{ overview.total_gratitude }}</div>
          <div class="wb-stat__label">累计感恩</div>
        </div>
        <div class="wb-stat">
          <div class="wb-stat__icon"><Calendar class="ep-icon" /></div>
          <div class="wb-stat__value">{{ overview.week_new }}</div>
          <div class="wb-stat__label">本周新增</div>
        </div>
        <div class="wb-stat">
          <div class="wb-stat__icon">🔥</div>
          <div class="wb-stat__value">{{ overview.streak_days }}</div>
          <div class="wb-stat__label">连续天数</div>
        </div>
      </div>

      <!-- 候选提醒 -->
      <div
        v-if="overview.pending_candidates > 0"
        class="wb-candidate-tip"
        @click="router.push('/wellbeing/candidates')"
      >
        <MagicStick class="ep-icon" /> AI 从你最近的日记里发现了
        <strong>{{ overview.pending_candidates }}</strong>
        个值得记下的瞬间，<a>去审核 →</a>
      </div>

      <!-- 90 天趋势 -->
      <div class="wb-card">
        <div class="wb-card__title"><TrendCharts class="ep-icon" /> 近 90 天累积趋势</div>
        <div v-if="overview.trend_90d.length === 0" class="wb-empty">还没有数据，记下第一条吧。</div>
        <div v-else class="wb-trend">
          <div
            v-for="p in overview.trend_90d"
            :key="p.date"
            class="wb-trend__col"
            :title="`${p.date}  成就 ${p.achievement}  感恩 ${p.gratitude}`"
          >
            <div
              class="wb-trend__bar wb-trend__bar--ach"
              :style="{ height: ((p.achievement / maxTrend()) * 100) + '%' }"
            ></div>
            <div
              class="wb-trend__bar wb-trend__bar--grat"
              :style="{ height: ((p.gratitude / maxTrend()) * 100) + '%' }"
            ></div>
          </div>
        </div>
        <div class="wb-trend__legend">
          <span><i class="wb-dot wb-dot--ach"></i> 成就</span>
          <span><i class="wb-dot wb-dot--grat"></i> 感恩</span>
        </div>
      </div>

      <div class="wb-grid-2">
        <!-- 分类分布 -->
        <div class="wb-card">
          <div class="wb-card__title"><Collection class="ep-icon" />️ 分类分布</div>
          <div v-if="overview.category_distribution.length === 0" class="wb-empty">暂无分类数据</div>
          <div v-else class="wb-cats">
            <div v-for="c in overview.category_distribution" :key="c.category" class="wb-cat">
              <div class="wb-cat__head">
                <span>{{ c.category }}</span>
                <span class="wb-cat__count">{{ c.count }} 条 · 平均强度 {{ c.avg_intensity.toFixed(1) }}</span>
              </div>
              <div class="wb-cat__bar">
                <div
                  class="wb-cat__bar-fill"
                  :style="{ width: ((c.count / overview.category_distribution[0].count) * 100) + '%' }"
                ></div>
              </div>
            </div>
          </div>
        </div>

        <!-- 翻牌：随机抽一张 -->
        <div class="wb-card wb-card--flip">
          <div class="wb-card__title">🃏 翻一张你过去的好</div>
          <div class="wb-flip">
            <Transition name="flip">
              <div v-if="flipCard" :key="flipCard.id" class="wb-flip__card">
                <div class="wb-flip__type">
                  <Trophy v-if="flipCard.type === 'achievement'" class="ep-icon" /> {{ flipCard.type === 'achievement' ? '成就' : '🙏 感恩' }}
                </div>
                <div class="wb-flip__content">{{ flipCard.content }}</div>
                <div class="wb-flip__meta">
                  <span v-if="flipCard.category">{{ flipCard.category }}</span>
                  <span>{{ '★'.repeat(flipCard.intensity) }}</span>
                  <span>{{ flipCard.occurred_at }}</span>
                </div>
              </div>
              <div v-else class="wb-flip__placeholder" :key="'placeholder'">
                点击下面的按钮，随机翻一张过去的瞬间
              </div>
            </Transition>
          </div>
          <button class="btn-primary wb-flip__btn" :disabled="flipping" @click="pickRandomEntry">
            {{ flipping ? '翻牌中…' : '翻一张' }}
          </button>
        </div>
      </div>

      <!-- AI 关联洞察 -->
      <div class="wb-insight" v-if="overview.insight">
        <span class="wb-insight__icon">✨</span>
        <span>{{ overview.insight }}</span>
        <button class="btn-ghost btn-sm" @click="router.push('/wellbeing/reports')">看完整报告 →</button>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
$mint: #14B8A6;
$peach: #F97316;
$soft-bg: linear-gradient(135deg, rgba(20, 184, 166, 0.08), rgba(249, 115, 22, 0.06));

.wb-dashboard {
  display: flex; flex-direction: column; gap: $spacing-lg;
}

.wb-hero {
  @include glass-card;
  padding: $spacing-lg $spacing-xl;
  display: flex; justify-content: space-between; align-items: center;
  background: $soft-bg, $glass-bg;
  flex-wrap: wrap; gap: $spacing-md;

  &__title { font-size: 24px; font-weight: 700; color: $text-primary; }
  &__sub { font-size: $font-size-sm; color: $text-secondary; margin-top: 4px; }
  &__actions { display: flex; gap: $spacing-sm; flex-wrap: wrap; }
}

.btn-primary {
  padding: 10px 18px; border: none; border-radius: 10px;
  background: linear-gradient(135deg, $mint, $peach);
  color: white; font-weight: 600; cursor: pointer;
  transition: transform .2s, box-shadow .2s;
  &:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba($mint, .35); }
  &:disabled { opacity: .6; cursor: not-allowed; }
}
.btn-ghost {
  padding: 10px 18px; border-radius: 10px; cursor: pointer;
  background: transparent; border: 1px solid $border-color; color: $text-secondary;
  &:hover { color: $mint; border-color: $mint; }
}
.btn-sm { padding: 4px 12px; font-size: 12px; }

.wb-quick {
  @include glass-card;
  padding: $spacing-md;
  display: flex; flex-direction: column; gap: $spacing-sm;
  &__row { display: flex; gap: $spacing-sm; align-items: center; flex-wrap: wrap; }
  textarea {
    width: 100%; padding: 10px; border-radius: 8px; border: 1px solid $border-color;
    resize: vertical; font-family: inherit; font-size: 14px; outline: none;
    &:focus { border-color: $mint; }
  }
  select, input[type="date"] {
    padding: 8px 10px; border-radius: 8px; border: 1px solid $border-color;
    background: white; font-size: 13px; outline: none;
    &:focus { border-color: $mint; }
  }
  &__type {
    padding: 6px 14px; border-radius: 999px; border: 1px solid $border-color;
    background: white; cursor: pointer; font-size: 13px;
    &--active {
      background: linear-gradient(135deg, $mint, $peach);
      color: white; border-color: transparent;
    }
  }
  &__stars { display: flex; gap: 2px; }
  &__star {
    font-size: 20px; color: #cbd5e1; cursor: pointer; user-select: none;
    transition: color .15s;
    &--on { color: #f59e0b; }
  }
}

.wb-loading { padding: 40px; text-align: center; color: $text-muted; }

.wb-stats {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: $spacing-md;
  @media (max-width: $breakpoint-md) { grid-template-columns: repeat(2, 1fr); }
}
.wb-stat {
  @include glass-card;
  padding: $spacing-lg; text-align: center;
  display: flex; flex-direction: column; gap: 6px; align-items: center;
  transition: transform .2s, box-shadow .2s;
  &:hover { transform: translateY(-2px); box-shadow: $shadow-lg; }
  &__icon { font-size: 28px; }
  &__value { font-size: 28px; font-weight: 700; color: $text-primary; }
  &__label { font-size: 12px; color: $text-muted; }
  &--ach { background: linear-gradient(135deg, rgba($mint, .12), $glass-bg); }
  &--grat { background: linear-gradient(135deg, rgba($peach, .12), $glass-bg); }
}

.wb-candidate-tip {
  @include glass-card;
  padding: $spacing-md $spacing-lg;
  background: linear-gradient(135deg, rgba(168, 85, 247, .1), $glass-bg);
  cursor: pointer;
  display: flex; align-items: center; gap: 6px;
  font-size: $font-size-sm; color: $text-primary;
  a { color: #a855f7; font-weight: 600; margin-left: 4px; }
  &:hover { box-shadow: $shadow-lg; }
}

.wb-card {
  @include glass-card;
  padding: $spacing-lg;
  &__title { font-size: $font-size-md; font-weight: 600; margin-bottom: $spacing-md; color: $text-primary; }
}
.wb-empty { text-align: center; padding: 30px; color: $text-muted; font-size: 13px; }

.wb-trend {
  display: flex; align-items: flex-end; gap: 2px;
  height: 120px; padding: 0 4px;
  &__col {
    flex: 1; display: flex; flex-direction: column; justify-content: flex-end;
    gap: 1px; min-width: 2px; height: 100%;
  }
  &__bar {
    border-radius: 2px 2px 0 0;
    &--ach { background: $mint; min-height: 0; }
    &--grat { background: $peach; min-height: 0; }
  }
  &__legend {
    display: flex; gap: $spacing-md; margin-top: $spacing-sm;
    font-size: 12px; color: $text-muted;
  }
}
.wb-dot {
  display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px;
  &--ach { background: $mint; }
  &--grat { background: $peach; }
}

.wb-grid-2 {
  display: grid; grid-template-columns: 1fr 1fr; gap: $spacing-md;
  @media (max-width: $breakpoint-md) { grid-template-columns: 1fr; }
}

.wb-cats { display: flex; flex-direction: column; gap: $spacing-sm; }
.wb-cat {
  &__head {
    display: flex; justify-content: space-between; font-size: 13px;
    color: $text-primary; margin-bottom: 4px;
  }
  &__count { color: $text-muted; font-size: 12px; }
  &__bar {
    height: 8px; background: rgba($mint, .1); border-radius: 4px; overflow: hidden;
    &-fill {
      height: 100%; background: linear-gradient(90deg, $mint, $peach);
      border-radius: 4px; transition: width .4s ease;
    }
  }
}

.wb-card--flip { display: flex; flex-direction: column; gap: $spacing-md; }
.wb-flip {
  flex: 1; min-height: 140px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, rgba($mint, .05), rgba($peach, .05));
  border-radius: 12px; padding: $spacing-md; position: relative; overflow: hidden;
  &__card {
    width: 100%;
    &__type, &__content, &__meta { /* placeholder */ }
  }
  &__type { font-size: 12px; color: $text-muted; margin-bottom: 6px; }
  &__content { font-size: $font-size-md; color: $text-primary; line-height: 1.6; }
  &__meta {
    display: flex; gap: $spacing-md; margin-top: $spacing-sm;
    font-size: 12px; color: $text-muted;
  }
  &__placeholder { color: $text-muted; font-size: 13px; text-align: center; }
  &__btn { align-self: stretch; }
}
.flip-enter-active, .flip-leave-active { transition: transform .4s, opacity .3s; }
.flip-enter-from { transform: rotateY(90deg); opacity: 0; }
.flip-leave-to { transform: rotateY(-90deg); opacity: 0; }

.wb-insight {
  @include glass-card;
  padding: $spacing-md $spacing-lg;
  display: flex; align-items: center; gap: $spacing-sm; flex-wrap: wrap;
  background: linear-gradient(135deg, rgba(99, 102, 241, .08), $glass-bg);
  font-size: $font-size-sm; color: $text-primary;
  &__icon { font-size: 18px; }
}

.slide-enter-active, .slide-leave-active { transition: all .25s ease; max-height: 400px; }
.slide-enter-from, .slide-leave-to { opacity: 0; max-height: 0; padding: 0 $spacing-md; }
</style>
