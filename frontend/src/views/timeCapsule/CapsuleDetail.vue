<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { marked } from 'marked'
import { timeCapsuleApi } from '@/api/timeCapsule'
import type { LetterDetail } from '@/api/timeCapsule'
import { Lock, FileText, Target, CheckCircle2, XCircle, Square, Bot, Sparkles, MessageCircle } from '@lucide/vue'

marked.setOptions({ breaks: true, gfm: true })

const router = useRouter()
const route = useRoute()
const loading = ref(true)
const letter = ref<LetterDetail | null>(null)

const letterId = computed(() => Number(route.params.id))
const aiReviewLoading = ref(false)
const aiReviewError = ref('')

const fetchLetter = async () => {
  loading.value = true
  try {
    letter.value = await timeCapsuleApi.getLetter(letterId.value)
  } catch (e) {
    console.error('获取信件详情失败:', e)
  }
  loading.value = false
}

const generateAiReview = async () => {
  if (!letter.value) return
  aiReviewLoading.value = true
  aiReviewError.value = ''
  try {
    await timeCapsuleApi.generateAiReview(letter.value.id)
    await fetchLetter()
  } catch (e: any) {
    aiReviewError.value = e.message || '生成失败，请稍后重试'
  }
  aiReviewLoading.value = false
}

const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

const renderMd = (md: string) => {
  try { return marked.parse(md) as string }
  catch { return md.replace(/\n/g, '<br>') }
}

const getStatusInfo = (status: string) => {
  const map: Record<string, { label: string; color: string }> = {
    sealed: { label: '已封存', color: '#8b5cf6' },
    pending: { label: '待开封', color: '#f59e0b' },
    opened: { label: '已开封', color: '#10b981' },
  }
  return map[status] || { label: status, color: '#6b7280' }
}

// 区块折叠（默认全部折叠）
const collapsed = ref({ content: true, ai: true, reflection: true })
const toggleSection = (key: 'content' | 'ai' | 'reflection') => {
  collapsed.value[key] = !collapsed.value[key]
}

onMounted(fetchLetter)
</script>

<template>
  <div class="capsule-detail">
    <button class="back-btn" @click="router.push('/time-capsule')">← 返回列表</button>

    <div v-if="loading" class="detail-loading">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
    </div>

    <template v-else-if="letter">
      <!-- 头部信息 -->
      <header class="detail-header animate-slideUp">
        <div class="detail-header__status" :style="{ background: `${getStatusInfo(letter.status).color}15`, color: getStatusInfo(letter.status).color }">
          {{ getStatusInfo(letter.status).label }}
        </div>
        <h1>{{ letter.title }}</h1>
        <div class="detail-header__meta">
          <span>写给：{{ letter.recipient }}</span>
          <span>封存于 {{ formatDate(letter.seal_date) }}</span>
          <span>解封日{{ formatDate(letter.open_date) }}</span>
        </div>
        <div v-if="letter.tags && letter.tags.length > 0" class="detail-header__tags">
          <span v-for="tag in letter.tags" :key="tag" class="tag-chip">{{ tag }}</span>
        </div>
      </header>

      <div v-if="letter.is_locked" class="detail-locked animate-slideUp" style="animation-delay:0.1s">
        <div class="locked-icon"><Lock :size="40" :stroke-width="1.5" /></div>
        <h2>信件已封存</h2>
        <p>距离开封还有 <strong>{{ letter.days_until_open }}</strong> 天</p>
        <p class="locked-hint">{{ letter.content_preview }}</p>
      </div>

      <template v-else>
        <section class="detail-content card animate-slideUp" style="animation-delay:0.1s">
          <h2 class="section-title" :class="{ 'section-title--collapsed': collapsed.content }" @click="toggleSection('content')">
            <FileText :size="16" :stroke-width="1.75" style="margin-right:8px;vertical-align:middle;" />信件内容
            <span class="section-title__arrow">{{ collapsed.content ? '▶' : '▼' }}</span>
          </h2>
          <div v-show="!collapsed.content" class="detail-content__body" v-html="renderMd(letter.content || '')"></div>
        </section>

        <section v-if="letter.goals && letter.goals.length > 0" class="detail-goals card animate-slideUp" style="animation-delay:0.15s">
          <h2><Target :size="16" :stroke-width="1.75" style="margin-right:8px;vertical-align:middle;" />目标清单</h2>
          <div class="goal-list">
            <div v-for="(goal, i) in letter.goals" :key="i" class="goal-row">
              <span class="goal-row__status">
                <CheckCircle2 v-if="goal.completed === true" :size="16" style="color:#10b981;" />
                <XCircle v-else-if="goal.completed === false" :size="16" style="color:#ef4444;" />
                <Square v-else :size="16" style="color:#9ca3af;" />
              </span>
              <div class="goal-row__body">
                <span class="goal-row__text">{{ goal.text }}</span>
                <span class="goal-row__type">
                  <Bot v-if="goal.type === 'ai'" :size="11" style="margin-right:3px;vertical-align:middle;" />AI评估
                  <template v-if="goal.type !== 'ai'">自评</template>
                </span>
                <p v-if="goal.ai_evaluation" class="goal-row__eval">{{ goal.ai_evaluation }}</p>
              </div>
            </div>
          </div>
        </section>

        <section v-if="letter.ai_review" class="detail-ai card animate-slideUp" style="animation-delay:0.2s">
          <h2 class="section-title" :class="{ 'section-title--collapsed': collapsed.ai }" @click="toggleSection('ai')">
            <Bot :size="16" :stroke-width="1.75" style="margin-right:8px;vertical-align:middle;" />AI 时光点评
            <span class="section-title__arrow">{{ collapsed.ai ? '▶' : '▼' }}</span>
          </h2>
          <div v-show="!collapsed.ai">
            <div class="detail-ai__body" v-html="renderMd(letter.ai_review)"></div>
            <small v-if="letter.ai_review_at" class="detail-ai__time">生成于 {{ formatDate(letter.ai_review_at as string) }}</small>
          </div>
        </section>

        <section v-else-if="letter.status === 'opened'" class="detail-ai-generate card animate-slideUp" style="animation-delay:0.2s">
          <h2><Bot :size="16" :stroke-width="1.75" style="margin-right:8px;vertical-align:middle;" />AI 时光点评</h2>
          <p class="generate-hint">让 AI 回顾你这段时间的日记、心力与读书笔记，为你生成专属的时光洞察</p>
          <p v-if="aiReviewError" class="error-hint">{{ aiReviewError }}</p>
          <button class="generate-btn" :class="{ loading: aiReviewLoading }" :disabled="aiReviewLoading" @click="generateAiReview">
            <span v-if="aiReviewLoading" class="loading-dots">
              生成中<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span>
            </span>
            <span v-else><Sparkles :size="14" style="margin-right:6px;vertical-align:middle;" />生成 AI 时光点评</span>
          </button>
        </section>

        <section v-if="letter.reflection" class="detail-reflection card animate-slideUp" style="animation-delay:0.25s">
          <h2 class="section-title" :class="{ 'section-title--collapsed': collapsed.reflection }" @click="toggleSection('reflection')">
            <MessageCircle :size="16" :stroke-width="1.75" style="margin-right:8px;vertical-align:middle;" />开封感想
            <span class="section-title__arrow">{{ collapsed.reflection ? '▶' : '▼' }}</span>
          </h2>
          <div v-show="!collapsed.reflection">
            <div class="detail-reflection__body">{{ letter.reflection }}</div>
            <small v-if="letter.reflection_at">写于 {{ formatDate(letter.reflection_at) }}</small>
          </div>
        </section>
      </template>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.capsule-detail {
  max-width: 760px;
  margin: 0 auto;
}

.back-btn {
  background: none;
  border: none;
  color: $text-secondary;
  cursor: pointer;
  font-size: $font-size-sm;
  margin-bottom: $spacing-lg;
  &:hover { color: $primary-color; }
}

.detail-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $spacing-md;
  padding: $spacing-xxl;
  color: $text-secondary;
  .loading-spinner {
    width: 40px; height: 40px;
    border: 3px solid rgba($primary-color, 0.2);
    border-top-color: $primary-color;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
}

.detail-header {
  margin-bottom: $spacing-xl;
  &__status {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 99px;
    font-size: 12px;
    font-weight: 500;
    margin-bottom: $spacing-sm;
  }
  h1 { font-size: $font-size-xxl; font-weight: 700; color: $text-primary; margin-bottom: $spacing-sm; }
  &__meta {
    display: flex;
    gap: $spacing-md;
    font-size: $font-size-sm;
    color: $text-secondary;
    flex-wrap: wrap;
  }
  &__tags {
    display: flex;
    gap: $spacing-xs;
    margin-top: $spacing-sm;
  }
}

.tag-chip {
  padding: 2px 8px;
  background: rgba($accent-color, 0.1);
  border-radius: 99px;
  font-size:11px;
  color: $accent-color;
}

.detail-locked {
  text-align: center;
  padding: $spacing-xxl * 2;
  .locked-icon { display: flex; justify-content: center; margin-bottom: $spacing-md; color: #8b5cf6; }
  h2 { color: $text-primary; margin-bottom: $spacing-sm; }
  p { color: $text-secondary; }
  .locked-hint { font-style: italic; color: $text-muted; margin-top: $spacing-md; }
}

.card {
  @include glass-card;
  padding: $spacing-lg;
  margin-bottom: $spacing-lg;
  h2 { font-size: $font-size-lg; font-weight: 600; color: $text-primary; margin-bottom: $spacing-md; }
}

// 可折叠区块标题
.section-title {
  display: flex;
  align-items: center;
  cursor: pointer;
  user-select: none;
  transition: color 0.15s;

  &:hover { color: $primary-color; }

  &--collapsed { margin-bottom: 0 !important; }

  &__arrow {
    margin-left: auto;
    font-size: 11px;
    color: $text-muted;
  }
}

.detail-content__body,
.detail-ai__body {
  font-size: $font-size-sm;
  line-height: 2;
  color: $text-secondary;
  :deep(h2) { font-size: $font-size-md; color: $text-primary; margin: $spacing-md 0 $spacing-sm; }
  :deep(p) { margin: $spacing-sm 0; }
  :deep(strong) { color: $text-primary; }
  :deep(blockquote) {
    border-left: 3px solid $primary-color;
    padding: $spacing-xs $spacing-md;
    background: rgba($primary-color, 0.03);
    border-radius: 0 $border-radius-sm $border-radius-sm 0;
    margin: $spacing-sm 0;
  }
}

.goal-list { display: flex; flex-direction: column; gap: $spacing-sm; }
.goal-row {
  display: flex; align-items: flex-start; gap: $spacing-sm;
  padding: $spacing-sm $spacing-md;
  background: rgba($primary-color, 0.03);
  border-radius: $border-radius-sm;
  &__status { font-size: 18px; min-width: 24px; }
  &__body { flex: 1; }
  &__text { font-size: $font-size-sm; color: $text-primary; }
  &__type { font-size: 11px; color: $text-muted; margin-left: $spacing-sm; }
  &__eval { font-size: $font-size-xs; color: $text-secondary; font-style: italic; margin-top: 4px; }
}

.detail-ai__time,
.detail-reflection small {
  display: block;
  font-size: 11px;
  color: $text-muted;
  margin-top: $spacing-sm;
}

.detail-ai-generate {
  text-align: center;
  padding: $spacing-xl $spacing-lg;
  .generate-hint {
    font-size: $font-size-sm;
    color: $text-secondary;
    margin-bottom: $spacing-lg;
    line-height: 1.6;
  }
  .error-hint {
    font-size: $font-size-xs;
    color: #ef4444;
    margin-bottom: $spacing-sm;
  }
  .generate-btn {
    padding: 10px 24px;
    background: linear-gradient(135deg, rgba($primary-color, 0.9), rgba($accent-color, 0.8));
    color: #fff;
    border: none;
    border-radius: $border-radius-md;
    font-size: $font-size-sm;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.2s, transform 0.2s;
    &:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
    &:disabled { opacity: 0.6; cursor: not-allowed; }
  }
  .loading-dots .dot {
    animation: blink 1.4s infinite;
    &:nth-child(2) { animation-delay: 0.2s; }
    &:nth-child(3) { animation-delay: 0.4s; }
  }
}

.detail-reflection__body {
  font-size: $font-size-sm;
  line-height: 1.8;
  color: $text-secondary;
  white-space: pre-wrap;
}

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes blink { 0%, 80%, 100% { opacity: 0; } 40% { opacity: 1; }}
</style>
