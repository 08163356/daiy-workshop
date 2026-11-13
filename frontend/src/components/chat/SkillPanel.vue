<script setup lang="ts">
/**
 * Skill 快捷面板（AI 助手页输入区 🧩 入口）
 * 左列表右编辑：查看/就地编辑当前生效的 skill，保存即生效
 */
import { ref, onMounted } from 'vue'
import { API_BASE } from '@/config'

interface SkillItem {
  name: string
  title: string
  description: string
  content: string
  bind_pipeline: string | null
  is_persona: boolean
  is_builtin: boolean
  enabled: boolean
  revision: number
  use_count: number
}

const emit = defineEmits<{ close: [] }>()

const skills = ref<SkillItem[]>([])
const loading = ref(true)
const selected = ref<SkillItem | null>(null)
const draft = ref({ title: '', description: '', content: '' })
const saving = ref(false)
const savedTip = ref(false)
// 新建模式
const creating = ref(false)
const createDraft = ref({ name: '', title: '', description: '', content: '' })
const createError = ref('')

const fetchSkills = async () => {
  loading.value = true
  try {
    const res = await fetch(`${API_BASE}/api/prompt-skills`)
    if (res.ok) skills.value = (await res.json()).items || []
  } finally {
    loading.value = false
  }
}

const pick = (s: SkillItem) => {
  selected.value = s
  creating.value = false
  draft.value = { title: s.title, description: s.description, content: s.content }
  savedTip.value = false
}

const startCreate = () => {
  creating.value = true
  selected.value = null
  createDraft.value = { name: '', title: '', description: '', content: '' }
  createError.value = ''
}

const createSkill = async () => {
  const d = createDraft.value
  if (!d.name.trim() || !d.title.trim() || !d.content.trim()) {
    createError.value = '名称/显示名/内容都要填'
    return
  }
  saving.value = true
  createError.value = ''
  try {
    const res = await fetch(`${API_BASE}/api/prompt-skills`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...d, name: d.name.trim() }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '创建失败')
    creating.value = false
    await fetchSkills()
    const created = skills.value.find(s => s.name === d.name.trim())
    if (created) pick(created)
  } catch (e: any) {
    createError.value = e.message
  } finally {
    saving.value = false
  }
}

const save = async () => {
  if (!selected.value) return
  saving.value = true
  try {
    const res = await fetch(`${API_BASE}/api/prompt-skills/${selected.value.name}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(draft.value),
    })
    if (res.ok) {
      savedTip.value = true
      fetchSkills()
      setTimeout(() => (savedTip.value = false), 2000)
    }
  } finally {
    saving.value = false
  }
}

onMounted(fetchSkills)
</script>

<template>
  <div class="skill-panel-mask" @click.self="emit('close')">
    <div class="skill-panel">
      <div class="skill-panel__head">
        <span>🧩 Skills</span>
        <span class="skill-panel__hint">改动保存后下次对话立即生效；新建的也会出现在 / 面板</span>
        <button class="skill-panel__new" @click="startCreate">+ 新建</button>
        <button class="skill-panel__close" @click="emit('close')">×</button>
      </div>
      <div class="skill-panel__body">
        <div class="skill-panel__list">
          <div v-if="loading" class="skill-panel__empty">加载中...</div>
          <button
            v-for="s in skills" :key="s.name"
            class="skill-panel__item"
            :class="{ 'skill-panel__item--active': selected?.name === s.name, 'skill-panel__item--off': !s.enabled }"
            @click="pick(s)"
          >
            <span class="skill-panel__item-title">
              {{ s.title }}
              <span v-if="s.bind_pipeline" class="skill-panel__tag">管线</span>
              <span v-if="s.is_persona" class="skill-panel__tag skill-panel__tag--persona">人格</span>
            </span>
            <span class="skill-panel__item-desc">{{ s.description }}</span>
          </button>
        </div>
        <div class="skill-panel__editor">
          <template v-if="creating">
            <label class="skill-panel__label">名称（kebab-case，如 morning-plan；/ 面板和 AI 据此识别）</label>
            <input v-model="createDraft.name" class="skill-panel__input" placeholder="my-skill" />
            <label class="skill-panel__label">显示名</label>
            <input v-model="createDraft.title" class="skill-panel__input" placeholder="我的技能" />
            <label class="skill-panel__label">描述（AI 据此判断何时自动调用；前一句话最关键）</label>
            <input v-model="createDraft.description" class="skill-panel__input" placeholder="什么时候用这个技能" />
            <label class="skill-panel__label">内容（prompt 正文，可用 {user_profile} 占位）</label>
            <textarea v-model="createDraft.content" class="skill-panel__textarea" rows="10" placeholder="你是一位…"></textarea>
            <div v-if="createError" class="skill-panel__error">{{ createError }}</div>
            <div class="skill-panel__ops">
              <button class="skill-panel__save" :disabled="saving" @click="createSkill">{{ saving ? '创建中...' : '创建' }}</button>
              <button class="skill-panel__cancel" @click="creating = false">取消</button>
            </div>
          </template>
          <template v-else-if="selected">
            <label class="skill-panel__label">名称</label>
            <input v-model="draft.title" class="skill-panel__input" />
            <label class="skill-panel__label">描述（AI 据此判断何时调用）</label>
            <input v-model="draft.description" class="skill-panel__input" />
            <label class="skill-panel__label">内容</label>
            <textarea v-model="draft.content" class="skill-panel__textarea" rows="12"></textarea>
            <div class="skill-panel__ops">
              <button class="skill-panel__save" :disabled="saving" @click="save">{{ saving ? '保存中...' : '保存' }}</button>
              <span v-if="savedTip" class="skill-panel__saved">✓ 已保存</span>
              <span class="skill-panel__rev">v{{ selected.revision }}</span>
            </div>
          </template>
          <div v-else class="skill-panel__empty">← 选择一个 Skill 查看/编辑，或点「+ 新建」</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.skill-panel-mask {
  position: fixed; inset: 0; z-index: 500;
  background: rgba(0, 0, 0, 0.35);
  display: flex; align-items: center; justify-content: center;
  padding: $spacing-md;
  backdrop-filter: blur(4px);
}

.skill-panel {
  background: rgba(255, 255, 255, 0.95);
  border-radius: $border-radius-lg;
  width: 100%; max-width: 860px; height: min(600px, 85vh);
  display: flex; flex-direction: column;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.2);
  overflow: hidden;

  &__head {
    display: flex; align-items: center; gap: $spacing-sm;
    padding: $spacing-md $spacing-lg; border-bottom: 1px solid $border-color;
    font-weight: 600; font-size: $font-size-sm;
  }
  &__hint { font-size: $font-size-xs; color: $text-muted; font-weight: 400; flex: 1; }
  &__close {
    border: none; background: rgba(0,0,0,0.05); width: 28px; height: 28px; border-radius: 50%;
    cursor: pointer; color: $text-muted; font-size: 14px;
    &:hover { background: rgba(0,0,0,0.1); }
  }
  &__new {
    border: 1px solid rgba($primary-color, 0.4); background: rgba($primary-color, 0.08);
    color: $primary-color; font-size: $font-size-xs; font-weight: 600;
    padding: 4px 12px; border-radius: 99px; cursor: pointer;
    &:hover { background: rgba($primary-color, 0.15); }
  }

  &__body {
    display: flex; flex: 1; min-height: 0;
    // 手机端：上下布局（列表横向滚动在上，编辑区在下），不再左右挤
    @media (max-width: $breakpoint-sm) { flex-direction: column; }
  }

  &__list {
    width: 240px; border-right: 1px solid $border-color; overflow-y: auto; flex-shrink: 0;
    @media (max-width: $breakpoint-sm) {
      width: 100%;
      border-right: none;
      border-bottom: 1px solid $border-color;
      display: flex;
      overflow-x: auto;
      overflow-y: hidden;
      max-height: 96px;
    }
  }
  &__item {
    display: flex; flex-direction: column; gap: 2px; width: 100%;
    padding: $spacing-sm $spacing-md; border: none; background: transparent;
    cursor: pointer; text-align: left; border-bottom: 1px solid rgba(0,0,0,0.04);
    &:hover { background: rgba($primary-color, 0.04); }
    &--active { background: rgba($primary-color, 0.08); }
    &--off { opacity: 0.45; }
    @media (max-width: $breakpoint-sm) {
      width: auto; flex-shrink: 0; border-bottom: none;
      border-right: 1px solid rgba(0,0,0,0.04);
      min-width: 110px;
    }
  }
  &__item-title { font-size: $font-size-sm; font-weight: 600; display: flex; gap: 4px; align-items: center; }
  &__item-desc {
    font-size: 10px; color: $text-muted;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  &__tag {
    font-size: 9px; padding: 0 5px; border-radius: 99px;
    background: rgba(#3B82F6, 0.12); color: #1D4ED8;
    &--persona { background: rgba(#8B5CF6, 0.12); color: #6D28D9; }
  }

  &__editor { flex: 1; padding: $spacing-md $spacing-lg; overflow-y: auto; min-width: 0; }
  &__label { display: block; font-size: $font-size-xs; font-weight: 600; color: $text-secondary; margin: $spacing-sm 0 4px; }
  &__input {
    width: 100%; padding: 6px 10px; border: 1px solid $border-color; border-radius: $border-radius-sm;
    font-size: $font-size-sm; box-sizing: border-box;
    &:focus { outline: none; border-color: $primary-color; }
  }
  &__textarea {
    width: 100%; padding: $spacing-sm; border: 1px solid $border-color; border-radius: $border-radius-sm;
    font-size: $font-size-xs; font-family: ui-monospace, monospace; resize: vertical; box-sizing: border-box;
    line-height: 1.6;
    &:focus { outline: none; border-color: $primary-color; }
  }
  &__ops { display: flex; align-items: center; gap: $spacing-sm; margin-top: $spacing-sm; }
  &__save {
    padding: 6px 18px; border: none; border-radius: $border-radius-sm; cursor: pointer;
    background: linear-gradient(135deg, #EC4899, #8B5CF6); color: #fff; font-size: $font-size-sm;
    &:disabled { opacity: 0.5; }
  }
  &__saved { font-size: $font-size-xs; color: #10B981; }
  &__rev { font-size: 10px; color: $text-muted; }
  &__empty { padding: $spacing-lg; color: $text-muted; font-size: $font-size-sm; text-align: center; }
  &__cancel {
    padding: 6px 14px; border: 1px solid $border-color; border-radius: $border-radius-sm;
    background: transparent; color: $text-muted; font-size: $font-size-sm; cursor: pointer;
    &:hover { color: $text-secondary; }
  }
  &__error { font-size: $font-size-xs; color: #EF4444; margin-top: $spacing-sm; }
}
</style>
