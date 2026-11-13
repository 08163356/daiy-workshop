<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { wereadApi, type WeReadStatus, type WeReadBook, type WeReadStats } from '@/api/weread'

const router = useRouter()

const loading = ref(true)
const status = ref<WeReadStatus | null>(null)
const books = ref<WeReadBook[]>([])
const totalBooks = ref(0)
const stats = ref<WeReadStats | null>(null)

const shelfSyncing = ref(false)
const allSyncing = ref(false)
const bookSyncingMap = ref<Record<string, boolean>>({})
const toast = ref('')
const toastType = ref<'success' | 'error'>('success')

let toastTimer: ReturnType<typeof setTimeout> | null = null

const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
  toast.value = msg
  toastType.value = type
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 3500)
}

const fetchData = async () => {
  loading.value = true
  try {
    const [s, shelf, st] = await Promise.allSettled([
      wereadApi.getStatus(),
      wereadApi.getShelf({ limit: 200 }),
      wereadApi.getStats(),
    ])
    if (s.status === 'fulfilled') status.value = s.value
    if (shelf.status === 'fulfilled') {
      books.value = shelf.value.books
      totalBooks.value = shelf.value.total
    }
    if (st.status === 'fulfilled') stats.value = st.value
  } finally {
    loading.value = false
  }
}

const syncShelf = async () => {
  if (shelfSyncing.value) return
  shelfSyncing.value = true
  try {
    const result = await wereadApi.syncShelf()
    showToast(`✓ ${result.message}`)
    await fetchData()
  } catch (e: any) {
    showToast(e.message || '同步失败', 'error')
  } finally {
    shelfSyncing.value = false
  }
}

const syncAll = async () => {
  if (allSyncing.value) return
  allSyncing.value = true
  try {
    const result = await wereadApi.syncAll()
    showToast(`✓ ${result.message}`)
    await fetchData()
  } catch (e: any) {
    showToast(e.message || '全量同步失败', 'error')
  } finally {
    allSyncing.value = false
  }
}

const syncBook = async (bookId: string) => {
  if (bookSyncingMap.value[bookId]) return
  bookSyncingMap.value[bookId] = true
  try {
    const result = await wereadApi.syncBook(bookId)
    showToast(`✓ ${result.message}`)
    const idx = books.value.findIndex(b => b.book_id === bookId)
    if (idx !== -1) {
      books.value[idx].note_count = result.highlights_count + result.reviews_count
      books.value[idx].last_synced_at = new Date().toISOString()
    }
    if (status.value) status.value.total_notes_synced += 1
  } catch (e: any) {
    showToast(e.message || '同步失败', 'error')
  } finally {
    delete bookSyncingMap.value[bookId]
  }
}

const formatDate = (s: string | null) => {
  if (!s) return ''
  return new Date(s).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

const formatMinutes = (m: number | null) => {
  if (!m) return '—'
  if (m < 60) return `${m}分`
  return `${Math.floor(m / 60)}h${m % 60}m`
}

const hasStats = computed(() =>
  stats.value && (stats.value.today_minutes || stats.value.week_minutes || stats.value.month_minutes || stats.value.total_minutes)
)

onMounted(fetchData)
</script>

<template>
  <div class="weread-page">
    <!-- Toast提示 -->
    <Transition name="toast-fade">
      <div v-if="toast" class="toast" :class="`toast--${toastType}`">{{ toast }}</div>
    </Transition>

    <!-- 页头 -->
    <header class="weread-header animate-slideUp">
      <div class="weread-header__left">
        <h1>📚 微信读书</h1>
        <p v-if="status?.configured">
          <span v-if="status.last_sync_at">上次同步：{{ formatDate(status.last_sync_at) }} · 书架{{ status.total_books }} 本</span>
          <span v-else>已配置，尚未同步书架</span>
        </p>
        <p v-else class="not-configured">
          未配置 API Key，请前往
          <button class="link-btn" @click="router.push('/settings')">设置页</button>
          配置
        </p>
      </div>
      <div v-if="status?.configured" class="weread-header__actions">
        <button class="action-btn" :disabled="shelfSyncing" @click="syncShelf">
          <span v-if="shelfSyncing" class="spinning">⟳</span>
          <span v-else>🔄</span>
          同步书架
        </button>
        <button class="action-btn action-btn--primary" :disabled="allSyncing || !status?.shelf_synced" @click="syncAll">
          <span v-if="allSyncing" class="spinning">⟳</span>
          <span v-else>✨</span>
          全量同步笔记
        </button>
      </div>
    </header>

    <!-- 加载 -->
    <div v-if="loading" class="page-loading">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
    </div>

    <template v-else>
      <!-- 统计栏 -->
      <section v-if="hasStats || status?.configured" class="weread-stats animate-slideUp" style="animation-delay:0.1s">
        <div class="stat-chip">
          <span class="val">{{ formatMinutes(stats?.today_minutes ?? null) }}</span>
          <span class="lbl">今日</span>
        </div>
        <div class="stat-chip">
          <span class="val">{{ formatMinutes(stats?.week_minutes ?? null) }}</span>
          <span class="lbl">本周</span>
        </div>
        <div class="stat-chip">
          <span class="val">{{ formatMinutes(stats?.month_minutes ?? null) }}</span>
          <span class="lbl">本月</span>
        </div>
        <div class="stat-chip">
          <span class="val">{{ stats?.total_days ?? '—' }}</span>
          <span class="lbl">累计天数</span>
        </div>
        <div class="stat-chip stat-chip--accent">
          <span class="val">{{ status?.total_notes_synced ?? 0 }}</span>
          <span class="lbl">已同步笔记</span>
        </div>
        <div class="stat-chip">
          <span class="val">{{ totalBooks }}</span>
          <span class="lbl">书架总数</span>
        </div>
      </section>

      <!-- 书架 -->
      <section v-if="books.length > 0" class="weread-shelf animate-slideUp" style="animation-delay:0.15s">
        <div class="shelf-header">
          <h2>书架（{{ totalBooks }} 本）</h2>
        </div>
        <div class="book-grid">
          <div
            v-for="book in books"
            :key="book.book_id"
            class="book-card"
            :class="{ 'book-card--synced': book.note_count > 0 }"
          >
            <!-- 封面 -->
            <div class="book-card__cover">
              <img
                v-if="book.cover"
                :src="book.cover"
                :alt="book.title"
                loading="lazy"
                @error="($event.target as HTMLImageElement).style.display='none'"
              />
              <div v-else class="cover-placeholder">{{ book.title[0] }}</div>
              <span v-if="book.note_count > 0" class="synced-badge">✓</span>
            </div>
            <!-- 信息 -->
            <div class="book-card__info">
              <p class="book-card__title">{{ book.title }}</p>
              <p class="book-card__author">{{ book.author || '未知作者' }}</p>
              <div class="book-card__footer">
                <span v-if="book.note_count > 0" class="note-count">{{ book.note_count }} 条笔记</span>
                <span v-else class="note-count note-count--empty">暂无笔记</span>
                <button
                  class="sync-btn"
                  :disabled="!!bookSyncingMap[book.book_id]"
                  @click.stop="syncBook(book.book_id)"
                >
                <span v-if="bookSyncingMap[book.book_id]" class="spinning">⟳</span>
                  <span v-else>{{ book.note_count > 0 ? '更新' : '同步' }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 空状态 -->
      <div v-else-if="status?.configured" class="empty-state animate-slideUp">
        <div class="empty-state__icon">📚</div>
        <h3>书架为空</h3>
        <p>先点击"同步书架"拉取书目信息</p>
        <button class="action-btn action-btn--primary" @click="syncShelf" :disabled="shelfSyncing">
          {{ shelfSyncing ? '同步中...' : '🔄 同步书架' }}
        </button>
      </div>

      <div v-else class="empty-state animate-slideUp">
        <div class="empty-state__icon">🔑</div>
        <h3>先配置微信读书 API Key</h3>
        <p>在设置页面填写你的 WeRead Skill API Key，即可同步书架和笔记</p>
        <button class="action-btn action-btn--primary" @click="router.push('/settings')">前往设置</button>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.weread-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: $spacing-lg;
  position: relative;
}

.toast {
  position: fixed;
  top: 72px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 500;
  padding: 10px 20px;
  border-radius: $border-radius-md;
  font-size: $font-size-sm;
  font-weight: 500;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  pointer-events: none;

  &--success { background: #10b981; color: #fff; }
  &--error { background: #ef4444; color: #fff; }
}
.toast-fade-enter-active, .toast-fade-leave-active { transition: all 0.3s ease; }
.toast-fade-enter-from, .toast-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(-10px); }

.weread-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $spacing-md;
  margin-bottom: $spacing-xl;
  flex-wrap: wrap;

  h1 { font-size: $font-size-xxl; font-weight: 700; color: $text-primary; margin-bottom: $spacing-xs; }
  p { font-size: $font-size-sm; color: $text-secondary; }
  .not-configured { color: $text-muted; }
  .link-btn {
    color: $primary-color;
    background: none;
    border: none;
    cursor: pointer;
    font-size: inherit;
    padding: 0;
    text-decoration: underline;
  }
  &__actions { display: flex; gap: $spacing-sm; flex-shrink: 0; align-items: center; }
}

.action-btn {
  display: flex;
  align-items: center;
  gap: $spacing-xs;
  padding: 8px 16px;
  border-radius: $border-radius-md;
  font-size: $font-size-sm;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  background: rgba($primary-color, 0.08);
  color: $primary-color;
  border: 1px solid rgba($primary-color, 0.2);

  &:hover:not(:disabled) {
    background: rgba($primary-color, 0.15);
  }
  &:disabled { opacity: 0.5; cursor: not-allowed; }

  &--primary {
    background: linear-gradient(135deg, $primary-color, $accent-color);
    color: #fff;
    border: none;
    &:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
  }
}

.page-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $spacing-md;
  padding: $spacing-xxl * 2;
  color: $text-secondary;
  .loading-spinner {
    width: 36px; height: 36px;
    border: 3px solid rgba($primary-color, 0.2);
    border-top-color: $primary-color;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
}

.weread-stats {
  display: flex;
  gap: $spacing-sm;
  flex-wrap: wrap;
  margin-bottom: $spacing-xl;

  .stat-chip {
    @include glass-card;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: $spacing-md $spacing-lg;
    min-width: 80px;
    flex: 1;

    .val { font-size: $font-size-xl; font-weight: 700; color: $text-primary; }
    .lbl { font-size: 11px; color: $text-muted; margin-top: 2px; }

    &--accent .val { color: $primary-color; }
  }
}

.shelf-header {
  display: flex;
  align-items: center;
  margin-bottom: $spacing-lg;
  h2 { font-size: $font-size-lg; font-weight: 600; color: $text-primary; }
}

.book-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: $spacing-md;

  @media (max-width: 1100px) { grid-template-columns: repeat(4, 1fr); }
  @media (max-width: 860px) { grid-template-columns: repeat(3, 1fr); }
  @media (max-width: 600px) { grid-template-columns: repeat(2, 1fr); }
}

.book-card {
  @include glass-card;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;

  &:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }

  &--synced .book-card__cover { border-bottom: 2px solid rgba(#10b981, 0.3); }

  &__cover {
    position: relative;
    aspect-ratio: 3/4;
    background: rgba($primary-color, 0.06);
    overflow: hidden;

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .cover-placeholder {
      width: 100%; height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 32px;
      font-weight: 700;
      color: $primary-color;
      background: linear-gradient(135deg, rgba($primary-color,0.08), rgba($accent-color,0.08));
    }

    .synced-badge {
      position: absolute;
      top: 6px;
      right: 6px;
      width: 20px;
      height: 20px;
      background: #10b981;
      color: #fff;
      border-radius: 50%;
      font-size: 11px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
    }
  }

  &__info {
    padding: $spacing-sm;
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  &__title {
    font-size: $font-size-xs;
    font-weight: 600;
    color: $text-primary;
    line-height: 1.4;
    @include text-ellipsis;
    margin-bottom: 2px;
  }

  &__author {
    font-size: 10px;
    color: $text-muted;
    @include text-ellipsis;
    margin-bottom: $spacing-xs;
  }

  &__footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: auto;
    gap: 4px;
  }
}

.note-count {
  font-size: 10px;
  color: #10b981;
  font-weight: 500;
  &--empty { color: $text-muted; }
}

.sync-btn {
  padding: 3px 8px;
  border-radius: $border-radius-sm;
  font-size: 10px;
  font-weight: 500;
  background: rgba($primary-color, 0.08);
  color: $primary-color;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;

  &:hover:not(:disabled) { background: rgba($primary-color, 0.15); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.empty-state {
  text-align: center;
  padding: $spacing-xxl * 2;
  &__icon { font-size: 64px; margin-bottom: $spacing-md; }
  h3 { font-size: $font-size-xl; font-weight: 600; color: $text-primary; margin-bottom: $spacing-sm; }
  p { font-size: $font-size-sm; color: $text-secondary; margin-bottom: $spacing-lg; }
}

.spinning {
  display: inline-block;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }
</style>
