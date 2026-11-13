<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { timeCapsuleApi } from '@/api/timeCapsule'
import type { LetterTemplate, GoalItem } from '@/api/timeCapsule'
import { PenLine, FileText, ClipboardList, Sparkles, CheckCircle2, Target, Bot, Lock } from '@lucide/vue'

const router = useRouter()

// ---- 写信模式 ----
type WriteMode = 'choose' | 'freewrite' | 'template'
const mode = ref<WriteMode>('choose')

// ---- 模板数据 ----
const templates = ref<LetterTemplate[]>([])
const selectedTemplate = ref<LetterTemplate | null>(null)
const templateAnswers = ref<Record<number, string>>({})
const loadingTemplates = ref(false)
const personalizedTemplate = ref<any>(null)
const loadingPersonalized = ref(false)

// ---- 表单数据 ----
const title = ref('')
const recipient = ref('未来的自己')
const content = ref('')
const openDate = ref('')
const remindDays = ref(3)
const tags = ref<string[]>([])
const tagInput = ref('')

// ---- 目标数据 ----
const goals = ref<{ text: string; type: 'self' | 'ai' }[]>([])
const goalInput = ref('')
const goalType = ref<'self' | 'ai'>('self')

// ---- 快捷日期 ----
const quickDates = [
  { label: '1年后', months: 12 },
  { label: '2年后', months: 24 },
  { label: '5年后', months: 60 },
  { label: '10年后', months: 120 },
  { label: '下个生日', custom: 'birthday' },
]

const setQuickDate = (item: any) => {
  if (item.months) {
    const d = new Date()
    d.setMonth(d.getMonth() + item.months)
    openDate.value = d.toISOString().split('T')[0]
  }
}

// ---- 模板相关 ----
const fetchTemplates = async () => {
  loadingTemplates.value = true
  try {
    // 先尝试初始化模板
    await timeCapsuleApi.initTemplates()
    const data = await timeCapsuleApi.getTemplates()
    templates.value = data.templates
  } catch (e) {
    console.error('获取模板失败:', e)
  }
  loadingTemplates.value = false
}

const selectTemplate = (tpl: LetterTemplate) => {
  selectedTemplate.value = tpl
  mode.value = 'template'
  templateAnswers.value = {}
  // 如果模板有建议目标，预填
  if (tpl.suggested_goals) {
    goals.value = tpl.suggested_goals.map(g => ({ text: g, type: 'self' as const }))
  }
}

const generatePersonalized = async () => {
  loadingPersonalized.value = true
  try {
    personalizedTemplate.value = await timeCapsuleApi.generatePersonalizedTemplate()
  } catch (e) {
    console.error('生成个性化模板失败:', e)
  }
  loadingPersonalized.value = false
}

const selectPersonalized = () => {
  if (!personalizedTemplate.value) return
  const p = personalizedTemplate.value
  selectedTemplate.value = {
    key: 'personalized',
    name: '为你定制',
    description: '基于你的个人数据生成的专属模板',
    icon: '✨',
    sections: p.sections,
    suggested_goals: p.suggested_goals,
    category: 'personalized',
  }
  mode.value = 'template'
  templateAnswers.value = {}
  if (p.suggested_goals) {
    goals.value = p.suggested_goals.map((g: string) => ({ text: g, type: 'ai' as const }))
  }
}

// ---- 目标管理 ----
const addGoal = () => {
  const text = goalInput.value.trim()
  if (!text) return
  goals.value.push({ text, type: goalType.value })
  goalInput.value = ''
}

const removeGoal = (index: number) => {
  goals.value.splice(index, 1)
}

// ---- 标签管理 ----
const addTag = () => {
  const tag = tagInput.value.trim()
  if (!tag || tags.value.includes(tag)) return
  tags.value.push(tag)
  tagInput.value = ''
}

const removeTag = (index: number) => {
  tags.value.splice(index, 1)
}

// ---- 从模板组装正文 ----
const assembleContent = (): string => {
  if (mode.value === 'freewrite') return content.value
  if (!selectedTemplate.value) return content.value

  const parts: string[] = []
  selectedTemplate.value.sections.forEach((section, i) => {
    const answer = templateAnswers.value[i]?.trim()
    if (answer) {
      parts.push(`## ${section.section}\n\n${answer}`)
    }
  })
  return parts.join('\n\n---\n\n')
}

// ---- 提交----
const submitting = ref(false)
const submitError = ref('')

const canSubmit = computed(() => {
  if (!title.value.trim()) return false
  if (!openDate.value) return false
  if (mode.value === 'freewrite' && !content.value.trim()) return false
  if (mode.value === 'template') {
    // 至少填了一个引导
    return Object.values(templateAnswers.value).some(v => v?.trim())
  }
  return true
})

const submit = async () => {
  if (!canSubmit.value) return
  submitting.value = true
  submitError.value = ''

  try {
    const letterContent = assembleContent()
    const goalItems: GoalItem[] = goals.value.map(g => ({
      text: g.text,
      type: g.type,
      completed: null,
      ai_evaluation: null,
      ai_score: null,
    }))

    await timeCapsuleApi.createLetter({
      title: title.value.trim(),
      recipient: recipient.value.trim() || '未来的自己',
      content: letterContent,
      goals: goalItems.length > 0 ? goalItems : undefined,
      open_date: openDate.value,
      remind_days: remindDays.value,
      template_id: selectedTemplate.value?.key || undefined,
      tags: tags.value.length > 0 ? tags.value : undefined,
    })

    // 成功后跳转
    router.push('/time-capsule')
  } catch (e: any) {
    submitError.value = e.message || '提交失败'
  }
  submitting.value = false
}

onMounted(() => {
  fetchTemplates()
})
</script>

<template>
  <div class="write-letter">
    <!-- 返回 -->
    <button class="write-letter__back" @click="router.push('/time-capsule')">
      ← 返回信件列表
    </button>

    <!-- 步骤一：选择模式 -->
    <div v-if="mode === 'choose'" class="mode-choose animate-slideUp">
      <header class="write-letter__header">
        <h1><PenLine :size="22" :stroke-width="1.75" style="margin-right:8px;vertical-align:middle;" />写一封给未来的信</h1>
        <p>选择你的写信方式</p>
      </header>

      <div class="mode-cards">
        <div class="mode-card" @click="mode = 'freewrite'">
          <div class="mode-card__icon"><FileText :size="32" :stroke-width="1.5" /></div>
          <h3>自由写作</h3>
          <p>没有模板约束，想到什么写什么，自由表达此刻的心声</p>
        </div>

        <div class="mode-card mode-card--templates">
          <div class="mode-card__icon"><ClipboardList :size="32" :stroke-width="1.5" /></div>
          <h3>模板引导</h3>
          <p>通过引导性问题，帮你系统性地记录和思考</p>
          <div class="template-grid" v-if="templates.length > 0">
            <div v-for="tpl in templates" :key="tpl.key" class="template-chip" @click.stop="selectTemplate(tpl)">
              <span class="template-chip__icon">{{ tpl.icon }}</span>
              <span class="template-chip__name">{{ tpl.name }}</span>
            </div>
          </div>
          <div v-else-if="loadingTemplates" class="template-loading">加载模板中...</div>
        </div>

        <div class="mode-card mode-card--ai" @click="generatePersonalized">
          <div class="mode-card__icon"><Sparkles :size="32" :stroke-width="1.5" /></div>
          <h3>AI 为你定制</h3>
          <p>基于你的日记、心力等历史数据，生成专属引导模板</p>
          <div v-if="loadingPersonalized" class="ai-loading">
            <span class="dots"><span></span><span></span><span></span></span>
            正在分析你的数据...
          </div>
          <div v-else-if="personalizedTemplate" class="ai-ready" @click.stop="selectPersonalized">
            <span><CheckCircle2 :size="13" style="margin-right:4px;vertical-align:middle;color:#10b981;" />模板已生成，点击使用</span>
            <small>基于 {{ personalizedTemplate.data_summary?.diary_count || 0 }} 篇日记生成</small>
          </div>
        </div>
      </div>
    </div>

    <!-- 步骤二：编辑信件 -->
    <div v-else class="letter-editor animate-slideUp">
      <header class="write-letter__header">
        <h1 v-if="mode === 'freewrite'"><FileText :size="20" :stroke-width="1.75" style="margin-right:8px;vertical-align:middle;" />自由写作</h1>
        <h1 v-else>{{ selectedTemplate?.icon }} {{ selectedTemplate?.name }}</h1>
        <button class="btn-link" @click="mode = 'choose'">← 重新选择模式</button>
      </header>

      <!-- 基础信息 -->
      <section class="editor-section">
        <h2>基础信息</h2>
        <div class="form-row">
          <div class="form-group form-group--flex">
            <label>信件标题</label>
            <input v-model="title" type="text" placeholder="给这封信起个标题..." class="input" />
          </div>
          <div class="form-group">
            <label>收件人</label>
            <input v-model="recipient" type="text" placeholder="未来的自己" class="input" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>解封日期</label>
            <input v-model="openDate" type="date" class="input" :min="new Date().toISOString().split('T')[0]" />
            <div class="quick-dates">
              <button
                v-for="qd in quickDates"
                :key="qd.label"
                class="quick-date-btn"
                @click="setQuickDate(qd)"
                :disabled="!!qd.custom"
              >{{ qd.label }}</button>
            </div>
          </div>
          <div class="form-group">
            <label>提前提醒天数</label>
            <input v-model.number="remindDays" type="number" min="0" max="30" class="input input--sm" />
            <small class="form-hint">解封日前后 {{ remindDays }} 天登录时弹出提醒</small>
          </div>
        </div>
      </section>

      <!-- 正文区域 -->
      <section class="editor-section">
        <h2>信件内容</h2>

        <!-- 自由模式 -->
        <div v-if="mode === 'freewrite'" class="freewrite-area">
          <textarea
            v-model="content"
            class="textarea"
            placeholder="亲爱的未来的自己，此刻的我想对你说..."
            rows="12"
          ></textarea>
        </div>

        <!-- 模板模式 -->
        <div v-else-if="selectedTemplate" class="template-area">
          <div
            v-for="(section, index) in selectedTemplate.sections"
            :key="index"
            class="template-section"
          >
            <h3 class="template-section__title">{{ section.section }}</h3>
            <p class="template-section__prompt">{{ section.prompt }}</p>
            <textarea
              v-model="templateAnswers[index]"
              :placeholder="section.placeholder"
              class="textarea textarea--section"
              rows="4"
            ></textarea>
          </div>
        </div>
      </section>

      <!-- 目标清单 -->
      <section class="editor-section">
        <h2><Target :size="16" :stroke-width="1.75" style="margin-right:6px;vertical-align:middle;" />我的目标清单 <small>（选填）</small></h2>
        <p class="section-desc">给未来的自己设定目标，到期时检验是否达成</p>

        <div class="goals-list" v-if="goals.length > 0">
          <div v-for="(goal, index) in goals" :key="index" class="goal-item">
            <span class="goal-item__type" :class="`goal-type--${goal.type}`">
              <Bot v-if="goal.type === 'ai'" :size="11" style="margin-right:3px;vertical-align:middle;" />{{ goal.type === 'ai' ? 'AI评估' : '自评' }}
            </span>
            <span class="goal-item__text">{{ goal.text }}</span>
            <button class="goal-item__remove" @click="removeGoal(index)">×</button>
          </div>
        </div>

        <div class="goal-add">
          <input
            v-model="goalInput"
            type="text"
            class="input"
            placeholder="输入一个目标..."
            @keyup.enter="addGoal"
          />
          <select v-model="goalType" class="select">
            <option value="self">自评</option>
            <option value="ai">AI评估</option>
          </select>
          <button class="btn btn-ghost" @click="addGoal" :disabled="!goalInput.trim()">+ 添加</button>
        </div>
        <small class="form-hint">
          「自评」= 开封时你自己勾选是否完成 ｜ 「AI评估」= AI根据你的日记/记录自动判断
        </small>
      </section>

      <!-- 标签 -->
      <section class="editor-section">
        <h2>标签 <small>（选填）</small></h2>
        <div class="tags-area">
          <span v-for="(tag, i) in tags" :key="i" class="tag">
            {{ tag }} <button @click="removeTag(i)">×</button>
          </span>
          <input
            v-model="tagInput"
            type="text"
            class="input input--inline"
            placeholder="添加标签..."
            @keyup.enter="addTag"
          />
        </div>
      </section>

      <!-- 提交 -->
      <section class="editor-submit">
        <p v-if="submitError" class="error-text">{{ submitError }}</p>
        <button
          class="btn btn-primary btn-lg"
          :disabled="!canSubmit || submitting"
          @click="submit"
        >
          {{ submitting ? '封存中...' : '' }}<Lock v-if="!submitting" :size="14" style="margin-right:6px;vertical-align:middle;" />{{ submitting ? '' : '封存这封信' }}
        </button>
        <p class="submit-hint">封存后将在 {{ openDate || '指定日期' }} 开封</p>
      </section>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.write-letter {
  max-width: 800px;
  margin: 0 auto;

  &__back {
    background: none;
    border: none;
    color: $text-secondary;
    cursor: pointer;
    font-size: $font-size-sm;
    margin-bottom: $spacing-lg;
    padding: $spacing-xs 0;
    &:hover { color: $primary-color; }
  }

  &__header {
    margin-bottom: $spacing-xl;
    h1 {
      font-size: $font-size-xxl;
      font-weight: 700;
      color: $text-primary;
      margin-bottom: $spacing-xs;
    }
    p, .btn-link {
      color: $text-secondary;
      font-size: $font-size-sm;
    }
    .btn-link {
      background: none;
      border: none;
      cursor: pointer;
      &:hover { color: $primary-color; }
    }
  }
}

//---- 模式选择 ----
.mode-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: $spacing-lg;
}

.mode-card {
  @include glass-card;
  padding: $spacing-xl;
  cursor: pointer;
  @include hover-lift;
  text-align: center;

  &__icon { display: flex; justify-content: center; align-items: center; margin-bottom: $spacing-md; color: $primary-color; }
  h3 { font-size: $font-size-lg; font-weight: 600; color: $text-primary; margin-bottom: $spacing-sm; }
  p { font-size: $font-size-sm; color: $text-secondary; }

  &--templates {
    cursor: default;
    p { margin-bottom: $spacing-md; }
  }

  &--ai {
    background: linear-gradient(135deg, rgba(#8b5cf6, 0.05), rgba(#06b6d4, 0.05));
    border-color: rgba(#8b5cf6, 0.2);
  }
}

.template-grid {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-xs;
  justify-content: center;
  margin-top: $spacing-sm;
}

.template-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: $spacing-xs $spacing-sm;
  border-radius: 99px;
  background: rgba($primary-color, 0.08);
  font-size: $font-size-xs;
  cursor: pointer;
  transition: all $transition-fast;

  &:hover { background: rgba($primary-color, 0.2); transform: scale(1.05); }
  &__icon { font-size: 14px; }
  &__name { color: $text-primary; }
}

.template-loading, .ai-loading {
  font-size: $font-size-sm;
  color: $text-muted;
  margin-top: $spacing-sm;
}

.ai-loading {
  .dots {
    display: inline-flex;
    gap: 3px;
    margin-right: $spacing-xs;
    span {
      width: 6px; height: 6px;
      border-radius: 50%;
      background: $primary-color;
      animation: bounce 1.4s ease-in-out infinite;
      &:nth-child(2) { animation-delay: 0.2s; }
      &:nth-child(3) { animation-delay: 0.4s; }
    }
  }
}

.ai-ready {
  margin-top: $spacing-sm;
  padding: $spacing-sm;
  background: rgba(#10b981, 0.1);
  border-radius: $border-radius-sm;
  cursor: pointer;
  span { font-size: $font-size-sm; color: #10b981; font-weight: 500; }
  small { display: block; font-size: 11px; color: $text-muted; margin-top: 2px; }
  &:hover { background: rgba(#10b981, 0.15); }
}

// ---- 编辑器 ----
.editor-section {
  @include glass-card;
  padding: $spacing-lg;
  margin-bottom: $spacing-lg;

  h2 {
    font-size: $font-size-lg;
    font-weight: 600;
    color: $text-primary;
    margin-bottom: $spacing-md;
    small { font-weight: 400; color: $text-muted; font-size: $font-size-sm; }
  }
}

.section-desc {
  font-size: $font-size-sm;
  color: $text-secondary;
  margin-bottom: $spacing-md;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: $spacing-md;
  margin-bottom: $spacing-md;

  @media (max-width: $breakpoint-sm) {
    grid-template-columns: 1fr;
  }
}

.form-group {
  label {
    display: block;
    font-size: $font-size-sm;
    font-weight: 500;
    color: $text-secondary;
    margin-bottom: $spacing-xs;
  }
  &--flex { grid-column: span 1; }
}

.input, .textarea, .select {
  width: 100%;
  padding: $spacing-sm $spacing-md;
  border: 1px solid rgba($primary-color, 0.15);
  border-radius: $border-radius-sm;
  background: rgba($primary-color, 0.02);
  color: $text-primary;
  font-size: $font-size-sm;
  transition: border-color $transition-fast;
  font-family: inherit;

  &:focus { outline: none; border-color: $primary-color; background: white; }
  &--sm { max-width: 100px; }
  &--inline { display: inline-block; width: auto; min-width: 120px; }
}

.textarea {
  resize: vertical;
  min-height: 120px;
  line-height: 1.8;
  &--section { min-height: 100px; }
}

.select {
  appearance: none;
  background-image: url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='none' stroke='%236b7280' viewBox='0 0 12 12'%3E%3Cpath d='M3 5l3 3 3-3'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  padding-right: 28px;
  width: auto;
}

.quick-dates {
  display: flex;
  gap: $spacing-xs;
  margin-top: $spacing-xs;
  flex-wrap: wrap;
}

.quick-date-btn {
  padding: 2px $spacing-sm;
  border-radius: 99px;
  border: 1px solid rgba($primary-color, 0.2);
  background: transparent;
  color: $text-secondary;
  font-size: 11px;
  cursor: pointer;
  &:hover:not(:disabled) { border-color: $primary-color; color: $primary-color; }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
}

.form-hint {
  display: block;
  font-size: 11px;
  color: $text-muted;
  margin-top: $spacing-xs;
}

// ---- 模板引导 ----
.template-section {
  margin-bottom: $spacing-lg;
  padding-bottom: $spacing-lg;
  border-bottom: 1px solid rgba($primary-color, 0.06);

  &:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }

  &__title {
    font-size: $font-size-md;
    font-weight: 600;
    color: $text-primary;
    margin-bottom: $spacing-xs;
  }
  &__prompt {
    font-size: $font-size-sm;
    color: $primary-color;
    font-style: italic;
    margin-bottom: $spacing-sm;
  }
}

// ---- 目标 ----
.goals-list {
  margin-bottom: $spacing-md;
}

.goal-item {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-md;
  background: rgba($primary-color, 0.03);
  border-radius: $border-radius-sm;
  margin-bottom: $spacing-xs;

  &__type {
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 99px;
    white-space: nowrap;
  }
  &__text { flex: 1; font-size: $font-size-sm; color: $text-primary; }
  &__remove {
    width: 20px; height: 20px;
    border-radius: 50%;
    border: none;
    background: transparent;
    color: $text-muted;
    cursor: pointer;
    font-size: 14px;
    &:hover { background: rgba(#ef4444, 0.1); color: #ef4444; }
  }
}

.goal-type--self { background: rgba(#3b82f6, 0.1); color: #3b82f6; }
.goal-type--ai { background: rgba(#8b5cf6, 0.1); color: #8b5cf6; }

.goal-add {
  display: flex;
  gap: $spacing-sm;
  align-items: center;
  .input { flex: 1; }
}

// ---- 标签 ----
.tags-area {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-xs;
  align-items: center;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px $spacing-sm;
  background: rgba($accent-color, 0.1);
  border-radius: 99px;
  font-size: $font-size-xs;
  color: $accent-color;

  button {
    border: none;
    background: none;
    color: inherit;
    cursor: pointer;
    font-size: 12px;
    &:hover { color: #ef4444; }
  }
}

// ---- 提交 ----
.editor-submit {
  text-align: center;
  padding: $spacing-xl 0;
}

.btn-lg {
  padding: $spacing-md $spacing-xl;
  font-size: $font-size-lg;
}

.submit-hint {
  font-size: $font-size-sm;
  color: $text-muted;
  margin-top: $spacing-sm;
}

.error-text {
  color: #ef4444;
  font-size: $font-size-sm;
  margin-bottom: $spacing-sm;
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
