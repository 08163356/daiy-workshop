<script setup lang="ts">
/**
 * 新建复盘页 — 散场/比赛模板切换
 */
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useBasketballStore } from '@/stores/useBasketballStore'

const router = useRouter()
const store = useBasketballStore()

const today = new Date().toISOString().slice(0, 10)
const sessionType = ref<'pickup' | 'match'>('pickup')

const form = ref({
  date: today,
  duration_min: 60 as number | null,
  venue: '',
  partners_desc: '',
  intensity: 3,
  fatigue: '',
  injury_note: '',
  shots_made: null as number | null,
  shots_attempted: null as number | null,
  highlights: '',
  problems: '',
  key_moments: '',
  emotion: '',
  one_line_summary: '',
  // match
  opponent: '',
  matchup: '',
  team_score: null as number | null,
  opp_score: null as number | null,
  my_play_minutes: null as number | null,
  decisive_moment: '',
  team_observation: '',
})

const showShootingRate = ref(false)
const submitting = ref(false)
const error = ref('')

const fatigueOptions = ['轻微', '中等', '严重']
const intensityLabels = ['😴', '🚶', '🏃', '💪', '🔥']

const isMatch = computed(() => sessionType.value === 'match')

const canSubmit = computed(() => form.value.one_line_summary.trim().length > 0)

async function submit() {
  if (!canSubmit.value) {
    error.value = '「一句话总结」是必填的，写一句吧。'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const created = await store.saveSession({
      ...form.value,
      type: sessionType.value,
      duration_min: form.value.duration_min || undefined,
      shots_made: form.value.shots_made ?? undefined,
      shots_attempted: form.value.shots_attempted ?? undefined,
      team_score: form.value.team_score ?? undefined,
      opp_score: form.value.opp_score ?? undefined,
      my_play_minutes: form.value.my_play_minutes ?? undefined,
    } as any)
    router.push(`/basketball/${created.id}`)
  } catch (e: any) {
    error.value = e?.message || '保存失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="bb-new">
    <!-- 标题 -->
    <header class="bb-new__head">
      <button class="bb-new__back" @click="router.back()">← 返回</button>
      <h1 class="bb-new__title">写一篇篮球复盘</h1>
    </header>

    <!-- 类型 Tab -->
    <div class="bb-new__type">
      <button
        class="bb-new__tab"
        :class="{ 'bb-new__tab--active': sessionType === 'pickup' }"
        @click="sessionType = 'pickup'"
      >
        🏃 散场
        <span class="bb-new__tab-sub">关注「自己」</span>
      </button>
      <button
        class="bb-new__tab"
        :class="{ 'bb-new__tab--active': sessionType === 'match', 'bb-new__tab--match': sessionType === 'match' }"
        @click="sessionType = 'match'"
      >
        🏆 比赛
        <span class="bb-new__tab-sub">关注「对抗+团队」</span>
      </button>
    </div>

    <form class="bb-new__form" @submit.prevent="submit">
      <!-- 基础 -->
      <section class="bb-new__section">
        <h2 class="bb-new__sec-title">基础信息</h2>
        <div class="bb-new__row">
          <label class="bb-new__field">
            <span class="bb-new__label">日期</span>
            <input type="date" v-model="form.date" class="bb-new__input" />
          </label>
          <label class="bb-new__field">
            <span class="bb-new__label">时长（分钟）</span>
            <input type="number" v-model.number="form.duration_min" class="bb-new__input" placeholder="60" min="1" max="300" />
          </label>
          <label class="bb-new__field">
            <span class="bb-new__label">场地</span>
            <input type="text" v-model="form.venue" class="bb-new__input" placeholder="如：公司楼下篮球场" />
          </label>
        </div>
        <label class="bb-new__field">
          <span class="bb-new__label">一起打的人</span>
          <input type="text" v-model="form.partners_desc" class="bb-new__input" placeholder="如：3v3 / 同事老王、阿强、阿明等" />
        </label>
      </section>

      <!-- 强度 / 体感 -->
      <section class="bb-new__section">
        <h2 class="bb-new__sec-title">强度 / 体感</h2>
        <div class="bb-new__intensity">
          <span class="bb-new__label">强度</span>
          <div class="bb-new__intensity-pick">
            <button
              type="button"
              v-for="(lab, i) in intensityLabels"
              :key="i"
              class="bb-new__intensity-btn"
              :class="{ 'bb-new__intensity-btn--active': form.intensity === i + 1 }"
              @click="form.intensity = i + 1"
            >
              <span class="bb-new__intensity-emoji">{{ lab }}</span>
              <span class="bb-new__intensity-num">{{ i + 1 }}</span>
            </button>
          </div>
        </div>
        <div class="bb-new__row">
          <label class="bb-new__field">
            <span class="bb-new__label">疲劳度</span>
            <select v-model="form.fatigue" class="bb-new__input">
              <option value="">不填</option>
              <option v-for="f in fatigueOptions" :key="f" :value="f">{{ f }}</option>
            </select>
          </label>
          <label class="bb-new__field bb-new__field--wide">
            <span class="bb-new__label">受伤标记（可选）</span>
            <input type="text" v-model="form.injury_note" class="bb-new__input" placeholder="如：左脚踝有点崴到" />
          </label>
        </div>
      </section>

      <!-- 命中率（折叠） -->
      <section class="bb-new__section">
        <button type="button" class="bb-new__toggle" @click="showShootingRate = !showShootingRate">
          🎯 命中率（可选） {{ showShootingRate ? '▾' : '▸' }}
        </button>
        <div v-if="showShootingRate" class="bb-new__row">
          <label class="bb-new__field">
            <span class="bb-new__label">命中数</span>
            <input type="number" v-model.number="form.shots_made" class="bb-new__input" min="0" />
          </label>
          <label class="bb-new__field">
            <span class="bb-new__label">出手数</span>
            <input type="number" v-model.number="form.shots_attempted" class="bb-new__input" min="0" />
          </label>
        </div>
      </section>

      <!-- 反思五要素 -->
      <section class="bb-new__section bb-new__section--reflect">
        <h2 class="bb-new__sec-title">反思 <span class="bb-new__sec-sub">— 这是教练能看到的全部素材</span></h2>

        <label class="bb-new__field">
          <span class="bb-new__label">✨ 技术亮点（今天什么动作出得舒服）</span>
          <textarea v-model="form.highlights" class="bb-new__textarea" rows="3" placeholder="如：右侧底角接球三分手感很好，教练教的低位翻身跳投今天试出来了"></textarea>
        </label>

        <label class="bb-new__field">
          <span class="bb-new__label">🚧 技术问题（什么动作出不来 / 被防死了）</span>
          <textarea v-model="form.problems" class="bb-new__textarea" rows="3" placeholder="如：横移跟不上突破，被对方一步过；接球第一拍处理球太慢"></textarea>
        </label>

        <label class="bb-new__field">
          <span class="bb-new__label">🎯 关键回合（写 1-3 个印象深刻的回合）</span>
          <textarea v-model="form.key_moments" class="bb-new__textarea" rows="3" placeholder="如：第三节最后 1 分钟，我抢到防守篮板后冒着对方夹击直接推快攻，传给侧翼空切的队友扣篮"></textarea>
        </label>

        <label class="bb-new__field">
          <span class="bb-new__label">💭 场上情绪</span>
          <textarea v-model="form.emotion" class="bb-new__textarea" rows="2" placeholder="如：开局有点慌，第二节稳定下来，结束时挺爽的"></textarea>
        </label>

        <label class="bb-new__field bb-new__field--required">
          <span class="bb-new__label">📝 一句话总结 <em class="bb-new__required">必填</em></span>
          <input type="text" v-model="form.one_line_summary" class="bb-new__input bb-new__input--important" placeholder="如：状态不错但防守端还是太松了" maxlength="200" />
        </label>
      </section>

      <!-- 比赛专属 -->
      <section v-if="isMatch" class="bb-new__section bb-new__section--match">
        <h2 class="bb-new__sec-title">比赛专属</h2>

        <label class="bb-new__field">
          <span class="bb-new__label">对手描述</span>
          <input type="text" v-model="form.opponent" class="bb-new__input" placeholder="如：A 公司队 / 街头联赛某队" />
        </label>
        <label class="bb-new__field">
          <span class="bb-new__label">主要对位球员</span>
          <input type="text" v-model="form.matchup" class="bb-new__input" placeholder="如：身高 188 的小前锋，左手很强" />
        </label>

        <div class="bb-new__row">
          <label class="bb-new__field">
            <span class="bb-new__label">己方分</span>
            <input type="number" v-model.number="form.team_score" class="bb-new__input" min="0" />
          </label>
          <label class="bb-new__field">
            <span class="bb-new__label">对方分</span>
            <input type="number" v-model.number="form.opp_score" class="bb-new__input" min="0" />
          </label>
          <label class="bb-new__field">
            <span class="bb-new__label">我上场（分钟）</span>
            <input type="number" v-model.number="form.my_play_minutes" class="bb-new__input" min="0" max="120" />
          </label>
        </div>

        <label class="bb-new__field">
          <span class="bb-new__label">决胜时刻（最后 2 分钟做了什么）</span>
          <textarea v-model="form.decisive_moment" class="bb-new__textarea" rows="3" placeholder="如：最后 30 秒持球失误送对方反击，下次该传球..."></textarea>
        </label>

        <label class="bb-new__field">
          <span class="bb-new__label">团队观察（队友谁打得好 / 自己作为队友做得如何）</span>
          <textarea v-model="form.team_observation" class="bb-new__textarea" rows="3" placeholder="如：阿强后场组织很稳，我自己当队友太黏球，下次多分球"></textarea>
        </label>
      </section>

      <!-- 错误提示 -->
      <div v-if="error" class="bb-new__error">{{ error }}</div>

      <!-- 提交 -->
      <div class="bb-new__submit">
        <button
          type="submit"
          class="bb-new__btn"
          :disabled="!canSubmit || submitting"
        >
          <span v-if="submitting" class="bb-new__btn-loading">
            <span class="bb-new__btn-dot"></span>
            <span class="bb-new__btn-dot"></span>
            <span class="bb-new__btn-dot"></span>
            教练正在看你的反思……
          </span>
          <span v-else>保存并请教练点评 →</span>
        </button>
      </div>
    </form>
  </div>
</template>

<style lang="scss" scoped>
.bb-new {
  max-width: 880px;
  margin: 0 auto;
  padding: 24px;
  display: flex; flex-direction: column;
  gap: 18px;
  background: linear-gradient(180deg, #FAF7F2 0%, #FFFFFF 200px);
  min-height: 100%;
}

.bb-new__head {
  display: flex; align-items: center; gap: 14px;
}

.bb-new__back {
  background: transparent;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
  color: #64748B;
  cursor: pointer;
  &:hover { background: white; }
}

.bb-new__title {
  font-size: 22px;
  font-weight: 700;
  color: #1F2937;
  margin: 0;
}

.bb-new__type {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.bb-new__tab {
  background: white;
  border: 2px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  padding: 14px 18px;
  cursor: pointer;
  display: flex; flex-direction: column; align-items: flex-start;
  gap: 4px;
  font-size: 16px;
  font-weight: 600;
  color: #64748B;
  transition: all 0.2s;

  &:hover {
    border-color: rgba(217, 119, 6, 0.4);
  }

  &--active {
    border-color: #D97706;
    background: linear-gradient(135deg, #FFF8F0, #FEF3E2);
    color: #B45309;
  }

  &--match.bb-new__tab--active {
    border-color: #DC2626;
    background: linear-gradient(135deg, #FEF2F2, #FEE2E2);
    color: #B91C1C;
  }

  &-sub {
    font-size: 11px;
    font-weight: 500;
    color: #94A3B8;
  }
}

.bb-new__form {
  display: flex; flex-direction: column;
  gap: 18px;
}

.bb-new__section {
  background: white;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 12px;
  padding: 18px 22px;
  display: flex; flex-direction: column; gap: 14px;

  &--match {
    border-color: rgba(220, 38, 38, 0.2);
    background: linear-gradient(180deg, #FEF2F2 0%, white 60px);
  }

  &--reflect {
    background: linear-gradient(180deg, rgba(217, 119, 6, 0.04) 0%, white 80px);
  }
}

.bb-new__sec-title {
  font-size: 14px;
  font-weight: 700;
  color: #1F2937;
  margin: 0 0 4px 0;
  display: flex; align-items: baseline; gap: 8px;
}

.bb-new__sec-sub {
  font-size: 12px;
  font-weight: 400;
  color: #94A3B8;
}

.bb-new__row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;

  @media (max-width: 640px) {
    grid-template-columns: 1fr;
  }
}

.bb-new__field {
  display: flex; flex-direction: column; gap: 6px;
  flex: 1;

  &--wide { flex: 2; }
  &--required {
    .bb-new__label em {
      color: #DC2626;
      margin-left: 6px;
      font-style: normal;
    }
  }
}

.bb-new__label {
  font-size: 12px;
  color: #64748B;
  font-weight: 500;
}

.bb-new__input,
.bb-new__textarea {
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 14px;
  font-family: inherit;
  color: #1F2937;
  background: #FAFAFA;
  outline: none;
  transition: all 0.15s;
  width: 100%;

  &:focus {
    border-color: #D97706;
    background: white;
    box-shadow: 0 0 0 3px rgba(217, 119, 6, 0.1);
  }

  &--important {
    border-color: #D97706;
    background: white;
  }
}

.bb-new__textarea {
  resize: vertical;
  line-height: 1.6;
}

.bb-new__intensity {
  display: flex; flex-direction: column; gap: 8px;
}

.bb-new__intensity-pick {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 6px;
}

.bb-new__intensity-btn {
  background: #FAFAFA;
  border: 2px solid rgba(15, 23, 42, 0.06);
  border-radius: 10px;
  padding: 10px 6px;
  cursor: pointer;
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  transition: all 0.15s;

  &:hover { border-color: rgba(217, 119, 6, 0.3); }

  &--active {
    border-color: #D97706;
    background: rgba(217, 119, 6, 0.08);
  }
}

.bb-new__intensity-emoji {
  font-size: 22px;
}

.bb-new__intensity-num {
  font-size: 11px;
  color: #94A3B8;
  font-weight: 600;
}

.bb-new__toggle {
  background: transparent;
  border: 1px dashed rgba(15, 23, 42, 0.15);
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  color: #64748B;
  cursor: pointer;
  text-align: left;
  font-family: inherit;

  &:hover {
    border-color: #D97706;
    color: #D97706;
  }
}

.bb-new__error {
  background: rgba(220, 38, 38, 0.08);
  border: 1px solid rgba(220, 38, 38, 0.2);
  color: #B91C1C;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
}

.bb-new__submit {
  position: sticky;
  bottom: 16px;
  display: flex; justify-content: center;
  margin-top: 10px;
}

.bb-new__btn {
  background: linear-gradient(135deg, #D97706, #B45309);
  color: white;
  border: none;
  border-radius: 12px;
  padding: 14px 32px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(217, 119, 6, 0.3);
  transition: transform 0.15s, box-shadow 0.15s;
  min-width: 280px;

  &:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 12px 28px rgba(217, 119, 6, 0.4);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

.bb-new__btn-loading {
  display: inline-flex; align-items: center; gap: 6px;
}

.bb-new__btn-dot {
  width: 6px; height: 6px;
  background: white;
  border-radius: 50%;
  animation: bb-bounce 1.4s ease-in-out infinite;
  &:nth-child(2) { animation-delay: 0.2s; }
  &:nth-child(3) { animation-delay: 0.4s; }
}

@keyframes bb-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
