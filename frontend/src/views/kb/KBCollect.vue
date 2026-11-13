<script setup lang="ts">
import { ref, computed } from 'vue'
import { API_BASE } from '@/config'

const KB_API_BASE = `${API_BASE}/api/kb`

defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [article: any]
}>()

const itemType = ref<'article' | 'tool'>('article')
const inputMode = ref<'url' | 'text'>('url')
const title = ref('')
const url = ref('')
const content = ref('')
const summary = ref('')
const tags = ref<string[]>([])
const tagInput = ref('')
const saving = ref(false)

const canSave = computed(() => {
  if (!title.value.trim()) return false
  if (inputMode.value === 'url' && !url.value.trim()) return false
  return true
})

const addTag = () => {
  const tag = tagInput.value.trim()
  if (tag && !tags.value.includes(tag)) {
    tags.value.push(tag)
  }
  tagInput.value = ''
}

const removeTag = (index: number) => {
  tags.value.splice(index, 1)
}

const close = () => {
  emit('update:modelValue', false)
}

const save = async () => {
  if (!canSave.value) return
  saving.value = true
  try {
    const body: any = {
      title: title.value.trim(),
      item_type: itemType.value,
      content_type: inputMode.value === 'url' ? 'url' : 'text',
      tags: tags.value.length > 0 ? tags.value : null,
      summary: summary.value.trim() || null,
    }
    if (inputMode.value === 'url') {
      body.url = url.value.trim()
    } else {
      body.content = content.value.trim() || null
    }

    const res = await fetch(KB_API_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error('保存失败')
    const article = await res.json()
    emit('saved', article)
    close()
  } catch (e: any) {
    alert(e.message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="modelValue" class="collect-overlay" @click.self="close">
        <div class="collect-dialog">
          <!-- Header -->
          <div class="collect-dialog__header">
            <h2>✨ 收集新知识</h2>
            <button class="collect-dialog__close" @click="close">✕</button>
          </div>

          <!-- 类型选择 -->
          <div class="collect-tabs">
            <button
              class="collect-tab"
              :class="{ 'collect-tab--active': itemType === 'article' }"
              @click="itemType = 'article'"
            >📄 文章资讯</button>
            <button
              class="collect-tab"
              :class="{ 'collect-tab--active': itemType === 'tool' }"
              @click="itemType = 'tool'"
            >🔧 工具收藏</button>
          </div>

          <!-- 输入模式 -->
          <div class="collect-tabs collect-tabs--sm">
            <button
              class="collect-tab collect-tab--sm"
              :class="{ 'collect-tab--active': inputMode === 'url' }"
              @click="inputMode = 'url'"
            >🔗 粘贴链接</button>
            <button
              class="collect-tab collect-tab--sm"
              :class="{ 'collect-tab--active': inputMode === 'text' }"
              @click="inputMode = 'text'"
            >✏️ 手动输入</button>
          </div>

          <!-- 输入区域 -->
          <div class="collect-form">
            <div v-if="inputMode === 'url'" class="form-group">
              <label>URL 链接 <span class="required">*</span></label>
              <input v-model="url" placeholder="https://..." class="form-input" />
            </div>

            <div v-else class="form-group">
              <label>内容</label>
              <textarea v-model="content" placeholder="粘贴或输入内容..." class="form-textarea" rows="5"></textarea>
            </div>

            <div class="form-group">
              <label>标题 <span class="required">*</span></label>
              <input v-model="title" placeholder="给这条知识起个名字" class="form-input" />
            </div>

            <div class="form-group">
              <label>标签</label>
              <div class="tags-input">
                <span v-for="(tag, i) in tags" :key="tag" class="tag-badge">
                  {{ tag }}
                  <button class="tag-badge__remove" @click="removeTag(i)">×</button>
                </span>
                <input
                  v-model="tagInput"
                  class="tags-input__field"
                  placeholder="输入标签，回车添加"
                  @keyup.enter="addTag"
                />
              </div>
            </div>

            <div class="form-group">
              <label>摘要</label>
              <textarea v-model="summary" placeholder="简要描述（可选）" class="form-textarea" rows="2"></textarea>
            </div>
          </div>

          <!-- Footer -->
          <div class="collect-dialog__footer">
            <button class="btn btn--ghost" @click="close">取消</button>
            <button class="kb-btn-primary" :disabled="!canSave || saving" @click="save">
              {{ saving ? '保存中...' : '💾 保存' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style lang="scss" scoped>
$kb-primary: #6366F1;
$kb-primary-light: #818CF8;
$kb-primary-bg: rgba(99, 102, 241, 0.1);

.collect-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  z-index: 9999;
  @include flex-center;
  padding: $spacing-md;
}

.collect-dialog {
  @include glass-card;
  width: 100%;
  max-width: 520px;
  max-height: 90vh;
  overflow-y: auto;
  @include custom-scrollbar;

  &__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: $spacing-lg;
    border-bottom: 1px solid $border-color;

    h2 {
      font-size: $font-size-lg;
      font-weight: 700;
    }
  }

  &__close {
    width: 32px;
    height: 32px;
    border-radius: $border-radius-sm;
    background: transparent;
    color: $text-secondary;
    font-size: 16px;
    @include flex-center;
    transition: all $transition-fast;

    &:hover {
      background: rgba($kb-primary, 0.1);
      color: $kb-primary;
    }
  }

  &__footer {
    display: flex;
    justify-content: flex-end;
    gap: $spacing-sm;
    padding: $spacing-md $spacing-lg;
    border-top: 1px solid $border-color;
  }
}

.collect-tabs {
  display: flex;
  gap: $spacing-xs;
  padding: $spacing-md $spacing-lg 0;

  &--sm {
    padding-top: $spacing-sm;
  }
}

.collect-tab {
  flex: 1;
  padding: $spacing-sm;
  border-radius: $border-radius-sm;
  background: transparent;
  color: $text-secondary;
  font-size: $font-size-sm;
  font-weight: 500;
  transition: all $transition-fast;
  border: 1px solid transparent;

  &:hover {
    background: $kb-primary-bg;
  }

  &--active {
    background: $kb-primary-bg;
    color: $kb-primary;
    border-color: rgba($kb-primary, 0.3);
    font-weight: 600;
  }

  &--sm {
    padding: $spacing-xs $spacing-sm;
    font-size: $font-size-xs;
  }
}

.collect-form {
  padding: $spacing-md $spacing-lg;
}

.form-group {
  margin-bottom: $spacing-md;

  label {
    display: block;
    font-size: $font-size-sm;
    font-weight: 500;
    color: $text-primary;
    margin-bottom: $spacing-xs;
  }

  .required {
    color: $danger-color;
  }
}

.form-input {
  width: 100%;
  padding: $spacing-sm $spacing-md;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  transition: all $transition-fast;

  &:focus {
    border-color: $kb-primary;
    box-shadow: 0 0 0 3px rgba($kb-primary, 0.1);
  }
}

.form-textarea {
  width: 100%;
  padding: $spacing-sm $spacing-md;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  resize: vertical;
  min-height: 60px;
  transition: all $transition-fast;

  &:focus {
    border-color: $kb-primary;
    box-shadow: 0 0 0 3px rgba($kb-primary, 0.1);
  }
}

.tags-input {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-xs;
  padding: $spacing-xs $spacing-sm;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  min-height: 38px;
  align-items: center;
  transition: border-color $transition-fast;

  &:focus-within {
    border-color: $kb-primary;
    box-shadow: 0 0 0 3px rgba($kb-primary, 0.1);
  }

  &__field {
    flex: 1;
    min-width: 100px;
    border: none;
    outline: none;
    font-size: $font-size-sm;
    padding: $spacing-xs;
    background: transparent;
  }
}

.tag-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 12px;
  background: $kb-primary-bg;
  color: $kb-primary;
  font-size: 12px;
  font-weight: 500;

  &__remove {
    background: none;
    border: none;
    color: $kb-primary;
    font-size: 14px;
    cursor: pointer;
    padding: 0;
    line-height: 1;

    &:hover {
      color: $danger-color;
    }
  }
}

.kb-btn-primary {
  display: inline-flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-sm $spacing-lg;
  border-radius: $border-radius-md;
  background: linear-gradient(135deg, $kb-primary, $kb-primary-light);
  color: white;
  font-weight: 600;
  font-size: $font-size-sm;
  border: none;
  cursor: pointer;
  transition: all $transition-fast;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba($kb-primary, 0.4);
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
  }
}

// Modal transition
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.25s ease;

  .collect-dialog {
    transition: transform 0.25s ease, opacity 0.25s ease;
  }
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;

  .collect-dialog {
    transform: scale(0.95);
    opacity: 0;
  }
}
</style>
