<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { API_BASE } from '@/config'

const KB_API_BASE = `${API_BASE}/api/kb`
const router = useRouter()
const route = useRoute()

interface ArticleDetail {
  id: number
  title: string
  url: string | null
  content: string | null
  item_type: string
  content_type: string
  summary: string | null
  read_status: string | null
  tags: string[] | null
  note_id: number | null
  source_chat_id: number | null
  created_at: string
  updated_at: string
}

const article = ref<ArticleDetail | null>(null)
const loading = ref(true)
const error = ref('')
const editing = ref(false)
const showTodoDialog = ref(false)
const todoSaving = ref(false)

// 编辑表单
const editForm = ref({
  title: '',
  url: '',
  content: '',
  summary: '',
  tags: [] as string[],
  item_type: 'article',
})
const tagInput = ref('')

// 转待办表单
const todoForm = ref({
  title: '',
  description: '',
  due_date: '',
})

const articleId = computed(() => Number(route.params.id))
const isArticle = computed(() => article.value?.item_type === 'article')

const fetchDetail = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(`${KB_API_BASE}/${articleId.value}`)
    if (!res.ok) throw new Error('加载失败')
    article.value = await res.json()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const toggleReadStatus = async () => {
  if (!article.value || !isArticle.value) return
  const newStatus = article.value.read_status === 'read' ? 'unread' : 'read'
  try {
    const res = await fetch(`${KB_API_BASE}/${articleId.value}/read-status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ read_status: newStatus }),
    })
    if (!res.ok) throw new Error('更新失败')
    article.value = await res.json()
  } catch (e: any) {
    alert(e.message)
  }
}

const startEdit = () => {
  if (!article.value) return
  editForm.value = {
    title: article.value.title,
    url: article.value.url || '',
    content: article.value.content || '',
    summary: article.value.summary || '',
    tags: [...(article.value.tags || [])],
    item_type: article.value.item_type,
  }
  editing.value = true
}

const cancelEdit = () => {
  editing.value = false
}

const addTag = () => {
  const tag = tagInput.value.trim()
  if (tag && !editForm.value.tags.includes(tag)) {
    editForm.value.tags.push(tag)
  }
  tagInput.value = ''
}

const removeTag = (index: number) => {
  editForm.value.tags.splice(index, 1)
}

const saveEdit = async () => {
  try {
    const body: any = {
      title: editForm.value.title,
      summary: editForm.value.summary || null,
      tags: editForm.value.tags.length > 0 ? editForm.value.tags : null,
    }
    if (editForm.value.url) body.url = editForm.value.url
    if (editForm.value.content) body.content = editForm.value.content

    const res = await fetch(`${KB_API_BASE}/${articleId.value}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error('保存失败')
    article.value = await res.json()
    editing.value = false
  } catch (e: any) {
    alert(e.message)
  }
}

const deleteArticle = async () => {
  if (!confirm('确定删除这条记录吗？')) return
  try {
    const res = await fetch(`${KB_API_BASE}/${articleId.value}`, { method: 'DELETE' })
    if (!res.ok) throw new Error('删除失败')
    router.push('/kb/list')
  } catch (e: any) {
    alert(e.message)
  }
}

const openTodoDialog = () => {
  if (!article.value) return
  todoForm.value = {
    title: `阅读：${article.value.title}`,
    description: article.value.url ? `链接: ${article.value.url}` : '',
    due_date: '',
  }
  showTodoDialog.value = true
}

const saveTodo = async () => {
  todoSaving.value = true
  try {
    const body: any = {}
    if (todoForm.value.title) body.title = todoForm.value.title
    if (todoForm.value.description) body.description = todoForm.value.description
    if (todoForm.value.due_date) body.due_date = todoForm.value.due_date

    const res = await fetch(`${KB_API_BASE}/${articleId.value}/to-todo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error('创建待办失败')
    showTodoDialog.value = false
    alert('待办创建成功！')
  } catch (e: any) {
    alert(e.message)
  } finally {
    todoSaving.value = false
  }
}

const goToReadingNote = () => {
  if (!article.value) return
  // 跳转到 AI 对话页，带上文章信息
  const noteContent = `请帮我分析这篇文章的读后笔记：\n\n标题：${article.value.title}\n${article.value.url ? '链接：' + article.value.url + '\n' : ''}${article.value.summary ? '摘要：' + article.value.summary + '\n' : ''}${article.value.content ? '\n内容：\n' + article.value.content : ''}`
  router.push({ path: '/assistant', query: { prompt: `/笔记 ${noteContent}` } })
}

const goBack = () => router.push('/kb/list')

const formatDate = (d: string) => {
  const date = new Date(d)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

onMounted(fetchDetail)
</script>

<template>
  <div class="kb-detail">
    <!-- 顶部导航 -->
    <div class="kb-detail__nav">
      <button class="btn btn--ghost" @click="goBack">← 返回列表</button>
      <div class="kb-detail__nav-actions" v-if="article && !editing">
        <button class="btn btn--ghost btn-sm" @click="startEdit">✏️ 编辑</button>
        <button class="btn btn--ghost btn-sm" style="color: #EF4444" @click="deleteArticle">🗑️ 删除</button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading">
      <div class="loading__spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-card">
      <p>{{ error }}</p>
      <button class="btn btn--ghost" @click="fetchDetail">重试</button>
    </div>

    <template v-else-if="article">
      <!-- 文章信息卡片 -->
      <div class="info-card" v-if="!editing">
        <div class="info-card__top">
          <span class="info-card__type-badge" :class="article.item_type === 'tool' ? 'info-card__type-badge--tool' : ''">
            {{ article.item_type === 'tool' ? '🔧 工具收藏' : '📄 文章资讯' }}
          </span>
          <div v-if="isArticle" class="read-toggle" @click="toggleReadStatus">
            <span class="read-toggle__dot" :class="article.read_status === 'read' ? 'read-toggle__dot--read' : ''"></span>
            <span>{{ article.read_status === 'read' ? '已读' : '未读' }}</span>
          </div>
        </div>

        <h1 class="info-card__title">{{ article.title }}</h1>

        <!-- URL -->
        <a v-if="article.url" :href="article.url" target="_blank" class="url-card">
          <span class="url-card__icon">🔗</span>
          <span class="url-card__text">{{ article.url }}</span>
          <span class="url-card__arrow">↗</span>
        </a>

        <!-- 标签 -->
        <div class="info-card__tags" v-if="article.tags?.length">
          <span v-for="tag in article.tags" :key="tag" class="tag-badge">{{ tag }}</span>
        </div>

        <!-- 摘要 -->
        <div v-if="article.summary" class="info-card__section">
          <h3>📝 摘要</h3>
          <p>{{ article.summary }}</p>
        </div>

        <!-- 内容 -->
        <div v-if="article.content" class="info-card__section">
          <h3>📄 内容</h3>
          <div class="info-card__content-text">{{ article.content }}</div>
        </div>

        <!-- 时间 -->
        <div class="info-card__meta">
          <span>收集于 {{ formatDate(article.created_at) }}</span>
          <span v-if="article.updated_at !== article.created_at">
            · 更新于 {{ formatDate(article.updated_at) }}
          </span>
        </div>
      </div>

      <!-- 编辑模式 -->
      <div class="edit-card" v-else>
        <h2>✏️ 编辑</h2>
        <div class="form-group">
          <label>标题</label>
          <input v-model="editForm.title" class="form-input" />
        </div>
        <div class="form-group" v-if="editForm.url || article.content_type === 'url'">
          <label>URL</label>
          <input v-model="editForm.url" class="form-input" />
        </div>
        <div class="form-group" v-if="editForm.content || article.content_type === 'text'">
          <label>内容</label>
          <textarea v-model="editForm.content" class="form-textarea" rows="6"></textarea>
        </div>
        <div class="form-group">
          <label>摘要</label>
          <textarea v-model="editForm.summary" class="form-textarea" rows="3"></textarea>
        </div>
        <div class="form-group">
          <label>标签</label>
          <div class="tags-input">
            <span v-for="(tag, i) in editForm.tags" :key="tag" class="tag-badge tag-badge--editable">
              {{ tag }}
              <button class="tag-badge__remove" @click="removeTag(i)">×</button>
            </span>
            <input v-model="tagInput" class="tags-input__field" placeholder="回车添加" @keyup.enter="addTag" />
          </div>
        </div>
        <div class="edit-card__actions">
          <button class="btn btn--ghost" @click="cancelEdit">取消</button>
          <button class="kb-btn-primary" @click="saveEdit">💾 保存</button>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="actions-card" v-if="!editing">
        <button v-if="isArticle" class="kb-btn-primary kb-btn--lg" @click="goToReadingNote">
          📝 写读后笔记
        </button>
        <button class="btn btn--secondary" @click="openTodoDialog">
          📌 转为待办
        </button>
      </div>

      <!-- 关联笔记 -->
      <div v-if="article.note_id" class="note-card">
        <h3>📒 关联读后笔记</h3>
        <p>笔记 ID: {{ article.note_id }}</p>
      </div>
    </template>

    <!-- 转待办弹窗 -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showTodoDialog" class="todo-overlay" @click.self="showTodoDialog = false">
          <div class="todo-dialog">
            <h2>📌 转为待办</h2>
            <div class="form-group">
              <label>待办标题</label>
              <input v-model="todoForm.title" class="form-input" />
            </div>
            <div class="form-group">
              <label>描述</label>
              <textarea v-model="todoForm.description" class="form-textarea" rows="3"></textarea>
            </div>
            <div class="form-group">
              <label>截止日期</label>
              <input v-model="todoForm.due_date" type="date" class="form-input" />
            </div>
            <div class="todo-dialog__actions">
              <button class="btn btn--ghost" @click="showTodoDialog = false">取消</button>
              <button class="kb-btn-primary" :disabled="todoSaving" @click="saveTodo">
                {{ todoSaving ? '创建中...' : '✅ 创建待办' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style lang="scss" scoped>
$kb-primary: #6366F1;
$kb-primary-light: #818CF8;
$kb-primary-bg: rgba(99, 102, 241, 0.1);

.kb-detail {
  max-width: 800px;
  margin: 0 auto;
  padding: $spacing-lg;
  animation: slideUp 0.4s ease;

  @media (max-width: $breakpoint-md) {
    padding: $spacing-md;
    padding-bottom: calc(#{$spacing-lg} + 70px);
  }

  &__nav {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: $spacing-lg;
  }

  &__nav-actions {
    display: flex;
    gap: $spacing-sm;
  }
}

// 信息卡片
.info-card {
  @include glass-card;
  padding: $spacing-xl;
  margin-bottom: $spacing-lg;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-lg;
  }

  &__top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: $spacing-md;
  }

  &__type-badge {
    padding: $spacing-xs $spacing-md;
    border-radius: $border-radius-xl;
    background: $kb-primary-bg;
    color: $kb-primary;
    font-size: $font-size-sm;
    font-weight: 600;

    &--tool {
      background: rgba(139, 92, 246, 0.1);
      color: #8B5CF6;
    }
  }

  &__title {
    font-size: $font-size-xl;
    font-weight: 700;
    color: $text-primary;
    margin-bottom: $spacing-md;
    line-height: 1.4;
  }

  &__tags {
    display: flex;
    flex-wrap: wrap;
    gap: $spacing-xs;
    margin-bottom: $spacing-lg;
  }

  &__section {
    margin-bottom: $spacing-lg;

    h3 {
      font-size: $font-size-md;
      font-weight: 600;
      margin-bottom: $spacing-sm;
    }

    p {
      color: $text-secondary;
      line-height: 1.8;
    }
  }

  &__content-text {
    color: $text-primary;
    line-height: 1.8;
    white-space: pre-wrap;
    background: rgba(0, 0, 0, 0.02);
    padding: $spacing-md;
    border-radius: $border-radius-sm;
    max-height: 400px;
    overflow-y: auto;
    @include custom-scrollbar;
  }

  &__meta {
    font-size: $font-size-xs;
    color: $text-muted;
    padding-top: $spacing-md;
    border-top: 1px solid $border-color;
  }
}

// 阅读状态
.read-toggle {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  padding: $spacing-xs $spacing-md;
  border-radius: $border-radius-xl;
  background: $kb-primary-bg;
  cursor: pointer;
  font-size: $font-size-sm;
  font-weight: 500;
  color: $kb-primary;
  transition: all $transition-fast;

  &:hover { background: rgba($kb-primary, 0.15); }

  &__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: $kb-primary;
    transition: all $transition-fast;

    &--read {
      background: $text-muted;
    }
  }
}

// URL 卡片
.url-card {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-md;
  border-radius: $border-radius-md;
  background: rgba(0, 0, 0, 0.02);
  border: 1px solid $border-color;
  margin-bottom: $spacing-md;
  text-decoration: none;
  color: $text-primary;
  transition: all $transition-fast;

  &:hover {
    border-color: $kb-primary;
    background: $kb-primary-bg;
  }

  &__icon { font-size: 18px; flex-shrink: 0; }
  &__text { flex: 1; font-size: $font-size-sm; @include text-ellipsis; color: $kb-primary; }
  &__arrow { font-size: 14px; color: $text-muted; flex-shrink: 0; }
}

// 操作按钮
.actions-card {
  display: flex;
  gap: $spacing-md;
  margin-bottom: $spacing-lg;

  @media (max-width: $breakpoint-sm) {
    flex-direction: column;
  }
}

// 编辑
.edit-card {
  @include glass-card;
  padding: $spacing-xl;
  margin-bottom: $spacing-lg;

  h2 { margin-bottom: $spacing-lg; }

  &__actions {
    display: flex;
    justify-content: flex-end;
    gap: $spacing-sm;
    margin-top: $spacing-lg;
  }
}

// 笔记
.note-card {
  @include glass-card;
  padding: $spacing-lg;

  h3 { margin-bottom: $spacing-sm; }
  p { color: $text-secondary; }
}

// 表单
.form-group {
  margin-bottom: $spacing-md;

  label {
    display: block;
    font-size: $font-size-sm;
    font-weight: 500;
    margin-bottom: $spacing-xs;
  }
}

.form-input {
  width: 100%;
  padding: $spacing-sm $spacing-md;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;

  &:focus { border-color: $kb-primary; box-shadow: 0 0 0 3px rgba($kb-primary, 0.1); }
}

.form-textarea {
  width: 100%;
  padding: $spacing-sm $spacing-md;
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  resize: vertical;

  &:focus { border-color: $kb-primary; box-shadow: 0 0 0 3px rgba($kb-primary, 0.1); }
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

  &:focus-within { border-color: $kb-primary; }

  &__field {
    flex: 1;
    min-width: 80px;
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
    cursor: pointer;
    padding: 0;
    font-size: 14px;
    line-height: 1;

    &:hover { color: $danger-color; }
  }
}

// 按钮
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

  &:hover { transform: translateY(-1px); box-shadow: 0 4px 16px rgba($kb-primary, 0.4); }
  &:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
}

.kb-btn--lg { padding: $spacing-md $spacing-xl; font-size: $font-size-md; }

// 转待办弹窗
.todo-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  z-index: 9999;
  @include flex-center;
  padding: $spacing-md;
}

.todo-dialog {
  @include glass-card;
  width: 100%;
  max-width: 440px;
  padding: $spacing-xl;

  h2 { margin-bottom: $spacing-lg; }

  &__actions {
    display: flex;
    justify-content: flex-end;
    gap: $spacing-sm;
    margin-top: $spacing-lg;
  }
}

// Loading & Error
.loading {
  @include flex-center;
  flex-direction: column;
  gap: $spacing-md;
  padding: $spacing-xxl;
  color: $text-secondary;

  &__spinner {
    width: 32px; height: 32px;
    border: 3px solid $border-color;
    border-top-color: $kb-primary;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
}

@keyframes spin { to { transform: rotate(360deg); } }

.error-card {
  @include glass-card;
  padding: $spacing-xl;
  text-align: center;
  color: $danger-color;
}

// Transitions
.modal-enter-active, .modal-leave-active {
  transition: opacity 0.25s ease;
  .todo-dialog { transition: transform 0.25s ease; }
}
.modal-enter-from, .modal-leave-to {
  opacity: 0;
  .todo-dialog { transform: scale(0.95); }
}
</style>
