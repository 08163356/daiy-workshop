<script setup lang="ts">
/**
 * 时光胶囊开封仪式弹窗
 * 全屏信封动画展开→ 展示信件内容 → AI点评 → 目标评估 → 写感想
 */
import { ref, computed } from 'vue'
import { marked } from 'marked'
import { timeCapsuleApi } from '@/api/timeCapsule'
import type { PendingLetter, GoalItem } from '@/api/timeCapsule'

marked.setOptions({ breaks: true, gfm: true })

const props = defineProps<{
  letter: PendingLetter
}>()

const emit = defineEmits<{
  close: []
  opened: [letterId: number]
}>()

//---- 状态 ----
type Phase = 'envelope' | 'opening' | 'content' | 'goals' | 'ai-review' | 'reflection'
const phase = ref<Phase>('envelope')
const aiReview = ref('')
const aiLoading = ref(false)
const goals = ref<GoalItem[]>(props.letter.goals || [])
const reflection = ref('')
const reflectionSaving = ref(false)

// ---- 动画相关 ----
const envelopeClicked = ref(false)

const openEnvelope = async () => {
  envelopeClicked.value = true
  phase.value = 'opening'
  
  // 开封 API
  try {
    await timeCapsuleApi.openLetter(props.letter.id)
  } catch (e) {
    console.error('开封失败:', e)
  }
  
  // 动画延迟
  setTimeout(() => {
    phase.value = 'content'
  }, 1500)
}

const goToGoals = () => {
  if (goals.value.length > 0) {
    phase.value = 'goals'
  } else {
    generateAiReview()
  }
}

const toggleGoal = async (index: number) => {
  const goal = goals.value[index]
  if (goal.type === 'self') {
    goal.completed = !goal.completed
    try {
      await timeCapsuleApi.evaluateGoal(props.letter.id, index, goal.completed)
    } catch (e) {
      console.error('评估失败:', e)
    }
  }
}

const generateAiReview = async () => {
  phase.value = 'ai-review'
  aiLoading.value = true
  try {
    const data = await timeCapsuleApi.generateAiReview(props.letter.id)
    aiReview.value = data.ai_review
    // 更新 AI 评估的目标
    if (data.goals) {
      goals.value = data.goals
    }
  } catch (e: any) {
    aiReview.value = `点评生成失败：${e.message}。你可以稍后在信件详情中重试。`
  }
  aiLoading.value = false
}

const goToReflection = () => {
  phase.value = 'reflection'
}

const saveReflection = async () => {
  if (!reflection.value.trim()) return
  reflectionSaving.value = true
  try {
    await timeCapsuleApi.addReflection(props.letter.id, reflection.value)
  } catch (e) {
    console.error('保存感想失败:', e)
  }
  reflectionSaving.value = false
  emit('opened', props.letter.id)
  emit('close')
}

const skipAndClose = () => {
  emit('opened', props.letter.id)
  emit('close')
}

// ---- 计算----
const formattedContent = computed(() => {
  try {
    return marked.parse(props.letter.content) as string
  } catch {
    return props.letter.content.replace(/\n/g, '<br>')
  }
})

const formattedAiReview = computed(() => {
  try {
    return marked.parse(aiReview.value) as string
  } catch {
    return aiReview.value.replace(/\n/g, '<br>')
  }
})

const completedGoals = computed(() => goals.value.filter(g => g.completed === true).length)
const totalGoals = computed(() => goals.value.length)
const completionRate = computed(() => totalGoals.value > 0 ? Math.round((completedGoals.value / totalGoals.value) * 100) : 0)

const timeDiff = computed(() => {
  const seal = new Date(props.letter.seal_date)
  const now = new Date()
  const days = Math.floor((now.getTime() - seal.getTime()) / (1000 * 60 * 60 * 24))
  if (days < 30) return `${days} 天`
  if (days < 365) return `${Math.floor(days / 30)} 个月`
  const years = Math.floor(days / 365)
  const months = Math.floor((days % 365) / 30)
  return months > 0 ? `${years} 年 ${months} 个月` : `${years} 年`
})
</script>

<template>
  <Teleport to="body">
    <div class="capsule-ceremony">
      <!-- 背景遮罩 -->
      <div class="ceremony-backdrop"></div>

      <!-- 阶段一：信封展示 -->
      <div v-if="phase === 'envelope' || phase === 'opening'" class="ceremony-envelope">
        <div class="envelope-scene" :class="{ 'envelope-scene--opening': phase === 'opening' }">
          <!-- 时间信息 -->
          <div class="envelope-intro" :class="{ 'fade-out': phase === 'opening' }">
            <p class="envelope-intro__from">来自 {{ timeDiff }} 前的你</p>
            <p class="envelope-intro__date">写于 {{ letter.seal_date }}</p>
          </div>

          <!-- 信封主体 -->
          <div class="envelope" :class="{ 'envelope--open': phase === 'opening' }" @click="openEnvelope">
            <div class="envelope__flap"></div>
            <div class="envelope__body">
              <div class="envelope__seal">🔒</div>
              <h2 class="envelope__title">{{ letter.title }}</h2>
              <p class="envelope__recipient">写给：{{ letter.recipient }}</p>
            </div>
            <div class="envelope__letter-peek" v-if="phase === 'opening'"></div>
          </div>

          <p v-if="phase === 'envelope'" class="envelope-hint">点击信封开封</p>
        </div>
      </div>

      <!-- 阶段二：信件内容 -->
      <div v-else-if="phase === 'content'" class="ceremony-content animate-fadeIn">
        <div class="content-scroll">
          <div class="content-header">
            <span class="content-header__badge">📮时光胶囊</span>
            <h1>{{ letter.title }}</h1>
            <div class="content-header__meta">
              <span>写给：{{ letter.recipient }}</span>
              <span>·</span>
              <span>{{ letter.seal_date }} → {{ letter.open_date }}</span>
              <span>·</span>
              <span>跨越 {{ timeDiff }}</span>
            </div>
          </div>

          <div class="content-body" v-html="formattedContent"></div>

          <div class="content-actions">
            <button class="btn btn-primary btn-ceremony" @click="goToGoals">
              {{ goals.length > 0 ? '查看目标完成情况 →' : '获取 AI 时光点评 →' }}
            </button>
            <button class="btn btn-ghost" @click="skipAndClose">稍后再看</button>
          </div>
        </div>
      </div>

      <!-- 阶段三：目标评估 -->
      <div v-else-if="phase === 'goals'" class="ceremony-goals animate-fadeIn">
        <div class="content-scroll">
          <div class="goals-header">
            <h2>🎯 目标回顾</h2>
            <div class="goals-progress">
              <div class="progress-ring">
                <svg viewBox="0 0 100 100">
                  <circle class="progress-ring__bg" cx="50" cy="50" r="42" />
                  <circle
                    class="progress-ring__fill"
                    cx="50" cy="50" r="42"
                    :style="{ strokeDashoffset: `${264 - (264 * completionRate / 100)}` }"
                  />
                </svg>
                <span class="progress-ring__text">{{ completionRate }}%</span>
              </div>
              <span class="goals-progress__label">{{ completedGoals }}/{{ totalGoals }} 完成</span>
            </div>
          </div>

          <div class="goals-list">
            <div
              v-for="(goal, index) in goals"
              :key="index"
              :class="['goal-card', { 'goal-card--done': goal.completed, 'goal-card--ai': goal.type === 'ai' }]"
              @click="toggleGoal(index)"
            >
              <div class="goal-card__check">
                <span v-if="goal.completed === true">✅</span>
                <span v-else-if="goal.completed === false">❌</span>
                <span v-else class="goal-card__checkbox">{{ goal.type === 'self' ? '☐' : '🤖' }}</span>
              </div>
              <div class="goal-card__content">
                <p class="goal-card__text">{{ goal.text }}</p>
                <span class="goal-card__type">{{ goal.type === 'ai' ? 'AI 评估' : '点击自评' }}</span>
                <p v-if="goal.ai_evaluation" class="goal-card__eval">{{ goal.ai_evaluation }}</p>
              </div>
              <div v-if="goal.ai_score !== null && goal.ai_score !== undefined" class="goal-card__score">
                {{ Math.round(goal.ai_score * 100) }}%
              </div>
            </div>
          </div>

          <div class="content-actions">
            <button class="btn btn-primary btn-ceremony" @click="generateAiReview">
              获取 AI 时光点评→
            </button>
            <button class="btn btn-ghost" @click="goToReflection">跳过，直接写感想</button>
          </div>
        </div>
      </div>

      <!-- 阶段四：AI 点评 -->
      <div v-else-if="phase === 'ai-review'" class="ceremony-ai animate-fadeIn">
        <div class="content-scroll">
          <h2>🤖 AI 时光见证者的话</h2>

          <div v-if="aiLoading" class="ai-loading-state">
            <div class="ai-dots"><span></span><span></span><span></span></div>
            <p>正在回顾你这段时间的经历，为你撰写专属点评...</p>
          </div>

          <div v-else class="ai-review-content" v-html="formattedAiReview"></div>

          <div class="content-actions" v-if="!aiLoading">
            <button class="btn btn-primary btn-ceremony" @click="goToReflection">
              写下此刻的感想 →
            </button>
            <button class="btn btn-ghost" @click="skipAndClose">稍后再写</button>
          </div>
        </div>
      </div>

      <!-- 阶段五：写感想 -->
      <div v-else-if="phase === 'reflection'" class="ceremony-reflection animate-fadeIn">
        <div class="content-scroll">
          <h2>💭 此刻的你想说什么？</h2>
          <p class="reflection-prompt">
            读完了{{ timeDiff }} 前自己写的信，现在的你有什么想说的？
          </p>

          <textarea
            v-model="reflection"
            class="reflection-textarea"
            placeholder="看到过去的自己写的这些话，我想说..."
            rows="8"
          ></textarea>

          <div class="content-actions">
            <button
              class="btn btn-primary btn-ceremony"
              :disabled="!reflection.trim() || reflectionSaving"
              @click="saveReflection"
            >
              {{ reflectionSaving ? '保存中...' : '保存感想，完成仪式 ✨' }}
            </button>
            <button class="btn btn-ghost" @click="skipAndClose">跳过</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style lang="scss" scoped>
.capsule-ceremony {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ceremony-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(10, 10, 30, 0.92);
  backdrop-filter: blur(8px);
}

//---- 信封阶段 ----
.ceremony-envelope {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.envelope-scene {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 32px;
  transition: all 0.5s ease;

  &--opening {
    transform: scale(1.05);
  }
}

.envelope-intro {
  text-align: center;
  transition: opacity 0.5s ease;

  &.fade-out { opacity: 0; }

  &__from {
    font-size: 20px;
    color: rgba(255, 255, 255, 0.9);
    font-weight: 300;
    margin-bottom: 8px;
  }
  &__date {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.5);
  }
}

.envelope {
  width: 320px;
  height: 220px;
  position: relative;
  cursor: pointer;
  perspective: 800px;
  transition: transform 0.3s ease;

  &:hover:not(.envelope--open) { transform: translateY(-8px); }

  &__flap {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 110px;
    background: linear-gradient(135deg, #c9a96e, #b8860b);
    clip-path: polygon(0 0, 50% 80%, 100% 0);
    transform-origin: top center;
    transition: transform 0.8s ease;
    z-index: 2;
  }

  &--open &__flap {
    transform: rotateX(180deg);
  }

  &__body {
    position: absolute;
    top: 40px;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(180deg, #f5e6c8, #e8d5a8);
    border-radius: 0 0 8px 8px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  }

  &__seal {
    font-size: 32px;
    margin-bottom: 4px;
  }

  &__title {
    font-size: 16px;
    color: #4a3728;
    font-weight: 600;
    text-align: center;
    padding: 0 16px;
  }

  &__recipient {
    font-size: 13px;
    color: #8b7355;
  }

  &__letter-peek {
    position: absolute;
    top: -40px;
    left: 20px;
    right: 20px;
    height: 60px;
    background: white;
    border-radius: 4px 4px 0 0;
    animation: letterRise 1s ease forwards;
    box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.1);
  }
}

.envelope-hint {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.4);
  animation: pulse 2s ease-in-out infinite;
}

// ---- 内容展示 ----
.ceremony-content,
.ceremony-goals,
.ceremony-ai,
.ceremony-reflection {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.content-scroll {
  max-width: 680px;
  max-height: 85vh;
  overflow-y: auto;
  padding: 40px;
  background: rgba(255, 255, 255, 0.97);
  border-radius: 16px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.3);
  margin: 20px;

  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-track { background: transparent; }
  &::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.1);
    border-radius: 3px;
  }
}

.content-header {
  text-align: center;
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);

  &__badge {
    display: inline-block;
    padding: 4px 12px;
    background: linear-gradient(135deg, rgba(#8b5cf6, 0.1), rgba(#06b6d4, 0.1));
    border-radius: 99px;
    font-size: 12px;
    color: #8b5cf6;
    margin-bottom: 12px;
  }

  h1 {
    font-size: 24px;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 8px;
  }

  &__meta {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    font-size: 13px;
    color: #6b7280;
    flex-wrap: wrap;
  }
}

.content-body {
  font-size: 15px;
  line-height: 2;
  color: #374151;
  margin-bottom: 32px;

  :deep(h2) {
    font-size: 18px;
    font-weight: 600;
    color: #1a1a2e;
    margin: 24px 0 12px;
  }

  :deep(p) { margin: 12px 0; }
  :deep(hr) { border: none; border-top: 1px solid rgba(0,0,0,0.06); margin: 24px 0; }
  :deep(strong) { color: #1a1a2e; }
}

.content-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding-top: 24px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.btn-ceremony {
  padding: 14px 32px;
  font-size: 16px;
  border-radius: 99px;
  font-weight: 600;
}

.btn-ghost {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
  &:hover { color: #374151; }
}

.btn-primary {
  background: linear-gradient(135deg, #8b5cf6, #06b6d4);
  color: white;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
  &:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(#8b5cf6, 0.3); }
  &:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
}

// ---- 目标评估 ----
.goals-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;

  h2 { font-size: 22px; font-weight: 700; color: #1a1a2e; }
}

.goals-progress {
  display: flex;
  align-items: center;
  gap: 12px;

  &__label { font-size: 14px; color: #6b7280; }
}

.progress-ring {
  position: relative;
  width: 60px;
  height: 60px;

  svg { width: 100%; height: 100%; transform: rotate(-90deg); }

  &__bg {
    fill: none;
    stroke: #e5e7eb;
    stroke-width: 6;
  }
  &__fill {
    fill: none;
    stroke: #10b981;
    stroke-width: 6;
    stroke-dasharray: 264;
    stroke-linecap: round;
    transition: stroke-dashoffset 0.5s ease;
  }
  &__text {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    font-weight: 600;
    color: #1a1a2e;
  }
}

.goals-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 32px;
}

.goal-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border-radius: 12px;
  background: #f9fafb;
  cursor: pointer;
  transition: all 0.2s;

  &:hover { background: #f3f4f6; }
  &--done { background: rgba(#10b981, 0.05); }
  &--ai { cursor: default; }

  &__check { font-size: 20px; min-width: 28px; text-align: center; }
  &__checkbox { color: #9ca3af; font-size: 18px; }
  &__content { flex: 1; }
  &__text { font-size: 15px; color: #1a1a2e; margin-bottom: 4px; }
  &__type { font-size: 12px; color: #6b7280; }
  &__eval { font-size: 13px; color: #6b7280; margin-top: 4px; font-style: italic; }
  &__score { font-size: 16px; font-weight: 600; color: #10b981; }
}

// ---- AI 点评 ----
.ai-loading-state {
  text-align: center;
  padding: 48px 0;

  p { color: #6b7280; font-size: 14px; margin-top: 16px; }
}

.ai-dots {
  display: flex;
  justify-content: center;
  gap: 6px;

  span {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: linear-gradient(135deg, #8b5cf6, #06b6d4);
    animation: aiBounce 1.4s ease-in-out infinite;
    &:nth-child(2) { animation-delay: 0.2s; }
    &:nth-child(3) { animation-delay: 0.4s; }
  }
}

.ai-review-content {
  font-size: 15px;
  line-height: 2;
  color: #374151;
  margin-bottom: 32px;

  :deep(h2), :deep(h3) { color: #1a1a2e; margin: 20px 0 8px; }
  :deep(strong) { color: #1a1a2e; }
  :deep(blockquote) {
    border-left: 3px solid #8b5cf6;
    padding: 8px 16px;
    background: rgba(#8b5cf6, 0.03);
    border-radius: 0 8px 8px 0;
    margin: 12px 0;
  }
}

// ---- 感想 ----
.reflection-prompt {
  font-size: 15px;
  color: #6b7280;
  margin-bottom: 20px;
}

.reflection-textarea {
  width: 100%;
  padding: 16px;
  border: 2px solid rgba(#8b5cf6, 0.2);
  border-radius: 12px;
  font-size: 15px;
  line-height: 1.8;
  color: #1a1a2e;
  resize: vertical;
  min-height: 160px;
  margin-bottom: 24px;
  font-family: inherit;
  transition: border-color 0.2s;

  &:focus { outline: none; border-color: #8b5cf6; }
  &::placeholder { color: #9ca3af; }
}

// ---- 动画 ----
@keyframes letterRise {
  from { transform: translateY(0); }
  to { transform: translateY(-50px); }
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

@keyframes aiBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.animate-fadeIn {
  animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
