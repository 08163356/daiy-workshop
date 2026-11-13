<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ saving: boolean }>()
const emit = defineEmits<{
  save: [payload: { name: string; title: string; description: string; content: string; is_persona: boolean }]
  cancel: []
}>()

const name = ref('')
const title = ref('')
const description = ref('')
const content = ref('')
const isPersona = ref(false)

const submit = () => {
  if (!name.value.trim() || !title.value.trim() || !description.value.trim() || !content.value.trim()) return
  emit('save', {
    name: name.value.trim(),
    title: title.value.trim(),
    description: description.value.trim(),
    content: content.value,
    is_persona: isPersona.value,
  })
}
</script>

<template>
  <div class="new-skill-form">
    <label class="label">唯一标识（kebab-case，如 meeting-notes）</label>
    <input v-model="name" class="input" placeholder="my-skill" />
    <label class="label">名称</label>
    <input v-model="title" class="input" placeholder="会议纪要" />
    <label class="label">描述（前 57 字符决定 AI 何时想到它，写触发语）</label>
    <input v-model="description" class="input" placeholder="把会议记录整理成结构化纪要。" />
    <label class="label">内容（prompt 正文，支持 {user_profile} {today} 占位符）</label>
    <textarea v-model="content" class="textarea" rows="10" placeholder="你是..."></textarea>
    <label class="checkbox">
      <input v-model="isPersona" type="checkbox" /> 这是人格（SOUL）技能
    </label>
    <div class="actions">
      <button class="btn btn--primary" :disabled="saving" @click="submit">创建</button>
      <button class="btn btn--ghost" @click="emit('cancel')">取消</button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.new-skill-form { display: flex; flex-direction: column; gap: 4px; }
.label { font-size: $font-size-xs; color: $text-secondary; font-weight: 600; margin-top: $spacing-sm; }
.input {
  padding: $spacing-sm $spacing-md; border: 1px solid $border-color; border-radius: $border-radius-sm;
  font-size: $font-size-sm; background: rgba(255,255,255,0.8);
  &:focus { outline: none; border-color: $primary-color; }
}
.textarea {
  padding: $spacing-sm $spacing-md; border: 1px solid $border-color; border-radius: $border-radius-sm;
  font-size: $font-size-sm; font-family: ui-monospace, monospace; resize: vertical; background: rgba(255,255,255,0.8);
  &:focus { outline: none; border-color: $primary-color; }
}
.checkbox { display: flex; align-items: center; gap: 6px; font-size: $font-size-sm; margin-top: $spacing-sm; }
.actions { display: flex; gap: $spacing-sm; margin-top: $spacing-md; }
.btn {
  padding: $spacing-sm $spacing-lg; border-radius: $border-radius-sm; font-size: $font-size-sm; cursor: pointer; border: none;
  &--primary { background: linear-gradient(135deg, #EC4899, #8B5CF6); color: #fff; }
  &--ghost { background: transparent; border: 1px solid $border-color; color: $text-secondary; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}
</style>
