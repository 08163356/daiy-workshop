<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  wishlistApi, categoryMeta,
  type WishDetail, type WishLogEntry, type Milestone,
} from '@/api/wishlist'
import AppIcon from '@/components/common/AppIcon.vue'

const route = useRoute()
const router = useRouter()
const wishId = computed(() => Number(route.params.id))

const wish = ref<WishDetail | null>(null)
const logs = ref<WishLogEntry[]>([])
const loading = ref(false)

const newMilestoneText = ref('')
const addingMilestone = ref(false)

const newLogContent = ref('')
const submittingLog = ref(false)

const showAchieveModal = ref(false)
const achieveNote = ref('')
const achieving = ref(false)
const justAchieved = ref(false)

const reviewingId = ref<number | null>(null)

async function loadWish() {
  wish.value = await wishlistApi.get(wishId.value)
}

async function loadLogs() {
  const res = await wishlistApi.listLogs(wishId.value)
  logs.value = res.items
}

async function loadAll() {
  loading.value = true
  try {
    await Promise.all([loadWish(), loadLogs()])
  } catch (e) {
    console.error('加载心愿详情失败', e)
  } finally {
    loading.value = false
  }
}

const milestones = computed<Milestone[]>(() => wish.value?.milestones || [])

async function addMilestone() {
  if (!newMilestoneText.value.trim() || !wish.value) return
  addingMilestone.value = true
  try {
    wish.value = await wishlistApi.addMilestone(wish.value.id, newMilestoneText.value.trim())
    newMilestoneText.value = ''
  } catch (e) {
    console.error('新增里程碑失败', e)
  } finally {
    addingMilestone.value = false
  }
}

async function toggleMilestone(index: number) {
  if (!wish.value) return
  wish.value = await wishlistApi.toggleMilestone(wish.value.id, index)
}

async function deleteMilestone(index: number) {
  if (!wish.value) return
  if (!confirm('确定删除这条里程碑？')) return
  wish.value = await wishlistApi.deleteMilestone(wish.value.id, index)
}

async function submitLog() {
  if (!newLogContent.value.trim() || !wish.value) return
  submittingLog.value = true
  try {
    await wishlistApi.createLog(wish.value.id, newLogContent.value.trim())
    newLogContent.value = ''
    await loadLogs()
  } catch (e) {
    console.error('写进展日志失败', e)
  } finally {
    submittingLog.value = false
  }
}

async function reviewCandidate(candidateId: number, action: 'accept' | 'reject') {
  reviewingId.value = candidateId
  try {
    await wishlistApi.reviewCandidate(candidateId, action)
    await Promise.all([loadWish(), loadLogs()])
  } catch (e) {
    console.error('审核候选失败', e)
  } finally {
    reviewingId.value = null
  }
}

function openAchieveModal() {
  achieveNote.value = ''
  showAchieveModal.value = true
}

async function submitAchieve() {
  if (!wish.value) return
  achieving.value = true
  try {
    const res = await wishlistApi.achieve(wish.value.id, achieveNote.value.trim() || undefined)
    wish.value = res.wish
    showAchieveModal.value = false
    justAchieved.value = true
  } catch (e) {
    console.error('实现心愿失败', e)
    alert('操作失败，请稍后再试')
  } finally {
    achieving.value = false
  }
}

async function removeWish() {
  if (!wish.value) return
  if (!confirm('确定删除这个心愿？此操作不可撤销。')) return
  await wishlistApi.remove(wish.value.id)
  router.push('/wishlist')
}

function goBack() {
  router.push('/wishlist')
}

function formatTime(iso: string) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

onMounted(loadAll)
</script>

<template>
  <div class="wd-page">
    <button class="wd-back" @click="goBack"><AppIcon name="arrow-left" :size="16" /> 返回心愿墙</button>

    <div v-if="loading" class="wd-empty">加载中…</div>

    <template v-else-if="wish">
      <div class="wd-hero" :style="{ '--cat-color': categoryMeta(wish.category).color }">
        <div class="wd-hero__cat">
          <span class="dot" :style="{ background: categoryMeta(wish.category).color }"></span>
          {{ categoryMeta(wish.category).label }}
        </div>
        <h1 :class="{ 'wd-hero__title--achieved': wish.status === 'achieved' }">{{ wish.content }}</h1>

        <div v-if="wish.status === 'achieved'" class="wd-achieved-banner">
          <span class="wd-achieved-badge">✨ 已实现</span>
          <span v-if="wish.achieved_note" class="wd-achieved-note">「{{ wish.achieved_note }}」</span>
        </div>

        <template v-else>
          <div class="wd-progress">
            <div class="wd-progress__track">
              <div class="wd-progress__fill" :style="{ width: wish.progress + '%' }"></div>
            </div>
            <span class="wd-progress__text">{{ wish.progress }}%</span>
          </div>
          <div class="wd-hero__actions">
            <button class="btn-primary" @click="openAchieveModal">🎉 实现这个心愿</button>
            <button class="btn-ghost btn-danger" @click="removeWish">删除</button>
          </div>
        </template>
      </div>

      <!-- 里程碑 -->
      <section class="wd-section">
        <h2>里程碑</h2>
        <div v-if="milestones.length === 0" class="wd-section__empty">还没有拆解出里程碑，可以在下面新增一条</div>
        <ul v-else class="wd-milestones">
          <li v-for="(m, idx) in milestones" :key="idx" class="wd-milestone">
            <button
              class="wd-milestone__check"
              :class="{ done: m.completed === true }"
              :disabled="wish.status === 'achieved'"
              @click="toggleMilestone(idx)"
            >
              <AppIcon v-if="m.completed" name="check-circle-2" :size="16" />
            </button>
            <span class="wd-milestone__text" :class="{ done: m.completed === true }">{{ m.text }}</span>
            <button v-if="wish.status !== 'achieved'" class="wd-milestone__del" @click="deleteMilestone(idx)">
              <AppIcon name="x" :size="14" />
            </button>
          </li>
        </ul>
        <div v-if="wish.status !== 'achieved'" class="wd-milestone-add">
          <input v-model="newMilestoneText" placeholder="新增一条里程碑…" @keyup.enter="addMilestone" />
          <button class="btn-primary btn-sm" :disabled="addingMilestone || !newMilestoneText.trim()" @click="addMilestone">添加</button>
        </div>
      </section>

      <!-- 进展日志 -->
      <section class="wd-section">
        <h2>进展日志</h2>
        <p class="wd-section__hint">随时写下你做了什么，AI 会悄悄帮你分析是否有进展，审核后再采纳。</p>

        <div v-if="wish.status !== 'achieved'" class="wd-log-input">
          <textarea v-model="newLogContent" rows="2" placeholder="今天为这个心愿做了什么…" @keyup.enter.exact.prevent="submitLog" />
          <button class="btn-primary btn-sm" :disabled="submittingLog || !newLogContent.trim()" @click="submitLog">记录</button>
        </div>

        <div v-if="logs.length === 0" class="wd-section__empty">还没有进展日志</div>
        <div v-else class="wd-log-list">
          <div v-for="log in logs" :key="log.id" class="wd-log-item">
            <div class="wd-log-item__time">{{ formatTime(log.created_at) }}</div>
            <div class="wd-log-item__content">{{ log.content }}</div>

            <div v-if="log.pending_candidate" class="wd-candidate">
              <div class="wd-candidate__head">
                <AppIcon name="wand-2" :size="14" /> AI 发现了一些进展
                <span class="wd-candidate__conf">置信度 {{ Math.round(log.pending_candidate.ai_confidence * 100) }}%</span>
              </div>
              <p v-if="log.pending_candidate.ai_reason" class="wd-candidate__reason">💭 {{ log.pending_candidate.ai_reason }}</p>
              <div class="wd-candidate__suggest">
                <span v-if="log.pending_candidate.suggested_progress !== null">
                  建议进度 → {{ log.pending_candidate.suggested_progress }}%
                </span>
                <span v-if="log.pending_candidate.suggested_milestone_index !== null">
                  建议完成里程碑 #{{ log.pending_candidate.suggested_milestone_index + 1 }}
                </span>
              </div>
              <div class="wd-candidate__actions">
                <button
                  class="btn-ghost btn-sm"
                  :disabled="reviewingId === log.pending_candidate.id"
                  @click="reviewCandidate(log.pending_candidate.id, 'reject')"
                >忽略</button>
                <button
                  class="btn-primary btn-sm"
                  :disabled="reviewingId === log.pending_candidate.id"
                  @click="reviewCandidate(log.pending_candidate.id, 'accept')"
                >采纳</button>
              </div>
            </div>
          </div>
        </div>
      </section>
    </template>

    <!-- 实现心愿 Modal -->
    <Transition name="modal-fade">
      <div v-if="showAchieveModal" class="wd-modal-overlay" @click.self="showAchieveModal = false">
        <div class="wd-modal">
          <h3>🎉 实现这个心愿</h3>
          <p class="wd-modal__hint">写下一句感恩留言，记录这一刻。</p>
          <textarea v-model="achieveNote" rows="3" placeholder="感谢自己的坚持，也感谢一路上帮助过我的人…" />
          <div class="wd-modal__actions">
            <button class="btn-ghost" @click="showAchieveModal = false">取消</button>
            <button class="btn-primary" :disabled="achieving" @click="submitAchieve">
              {{ achieving ? '正在实现…' : '确认实现' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <Transition name="modal-fade">
      <div v-if="justAchieved" class="wd-celebrate-overlay" @click="justAchieved = false">
        <div class="wd-celebrate">
          <div class="wd-celebrate__badge">✨</div>
          <h2>心愿已实现！</h2>
          <p>这份坚持，值得被记住。已同步到心力成就与你的成长画像。</p>
          <button class="btn-primary" @click="justAchieved = false">好的</button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style lang="scss" scoped>
.wd-page {
  padding: $spacing-lg;
  max-width: 720px;
  margin: 0 auto;
  padding-bottom: 60px;

  @media (max-width: $breakpoint-md) {
    padding: $spacing-md;
  }
}

.wd-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: transparent;
  color: $text-secondary;
  font-size: 13px;
  cursor: pointer;
  margin-bottom: $spacing-md;
  padding: 4px 0;

  &:hover { color: #F43F5E; }
}

.wd-empty {
  @include glass-card;
  padding: 60px 20px;
  text-align: center;
  color: $text-muted;
}

.wd-hero {
  @include glass-card;
  padding: $spacing-lg;
  margin-bottom: $spacing-lg;
  background: linear-gradient(135deg, rgba(#F43F5E, 0.06), rgba(#FBBF24, 0.06));

  &__cat {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 700;
    color: var(--cat-color);
    margin-bottom: 10px;

    .dot { width: 8px; height: 8px; border-radius: 50%; }
  }

  h1 {
    margin: 0 0 $spacing-md;
    font-size: 22px;
    font-weight: 700;
    color: $text-primary;
    line-height: 1.5;

    &--achieved { text-decoration: line-through; opacity: 0.7; }
  }

  &__actions {
    display: flex;
    gap: 8px;
    margin-top: $spacing-md;
  }
}

.wd-achieved-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.wd-achieved-badge {
  display: inline-flex;
  padding: 4px 14px;
  border-radius: 999px;
  background: linear-gradient(135deg, #FBBF24, #F59E0B);
  color: white;
  font-weight: 700;
  font-size: 13px;
}

.wd-achieved-note {
  color: $text-secondary;
  font-size: 13px;
  font-style: italic;
}

.wd-progress {
  display: flex;
  align-items: center;
  gap: 10px;

  &__track {
    flex: 1;
    height: 10px;
    border-radius: 999px;
    background: rgba(0,0,0,0.06);
    overflow: hidden;
  }

  &__fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #F43F5E, #FBBF24);
    transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
  }

  &__text {
    font-weight: 700;
    font-size: 14px;
    color: $text-primary;
    min-width: 40px;
    text-align: right;
  }
}

.wd-section {
  @include glass-card;
  padding: $spacing-lg;
  margin-bottom: $spacing-lg;

  h2 { margin: 0 0 4px; font-size: 16px; color: $text-primary; }
  &__hint { margin: 0 0 $spacing-md; font-size: 12px; color: $text-muted; }
  &__empty { color: $text-muted; font-size: 13px; padding: $spacing-sm 0; }
}

.wd-milestones {
  list-style: none;
  margin: 0 0 $spacing-md;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wd-milestone {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: $border-radius-md;
  background: rgba(0,0,0,0.02);

  &__check {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 2px solid $border-color;
    background: white;
    @include flex-center;
    flex-shrink: 0;
    cursor: pointer;
    color: white;
    transition: all 0.2s ease;

    &.done {
      background: linear-gradient(135deg, #F43F5E, #FBBF24);
      border-color: transparent;
    }
    &:disabled { cursor: not-allowed; opacity: 0.7; }
  }

  &__text {
    flex: 1;
    font-size: 14px;
    color: $text-primary;
    transition: all 0.2s ease;

    &.done { text-decoration: line-through; color: $text-muted; }
  }

  &__del {
    border: none;
    background: transparent;
    color: $text-muted;
    cursor: pointer;
    @include flex-center;
    width: 20px; height: 20px;
    border-radius: 50%;
    &:hover { background: rgba(239,68,68,0.1); color: #EF4444; }
  }
}

.wd-milestone-add {
  display: flex;
  gap: 8px;

  input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid $border-color;
    border-radius: $border-radius-md;
    font-size: 13px;
    outline: none;
    &:focus { border-color: #F43F5E; }
  }
}

.wd-log-input {
  display: flex;
  gap: 8px;
  margin-bottom: $spacing-md;
  align-items: flex-end;

  textarea {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid $border-color;
    border-radius: $border-radius-md;
    font-family: inherit;
    font-size: 13px;
    resize: vertical;
    outline: none;
    &:focus { border-color: #F43F5E; }
  }
}

.wd-log-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.wd-log-item {
  padding: 10px 12px;
  border-left: 2px solid rgba(#F43F5E, 0.3);
  padding-left: $spacing-md;

  &__time { font-size: 11px; color: $text-muted; margin-bottom: 4px; }
  &__content { font-size: 14px; color: $text-primary; line-height: 1.6; }
}

.wd-candidate {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: $border-radius-md;
  background: rgba(#FBBF24, 0.12);
  border: 1px solid rgba(#FBBF24, 0.3);

  &__head {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 700;
    color: #B45309;
  }
  &__conf { margin-left: auto; font-size: 11px; font-weight: 400; color: $text-muted; }
  &__reason { margin: 6px 0; font-size: 12px; color: $text-secondary; }
  &__suggest {
    display: flex; gap: 12px; flex-wrap: wrap;
    font-size: 12px; color: $text-primary; font-weight: 600; margin-bottom: 8px;
  }
  &__actions { display: flex; justify-content: flex-end; gap: 6px; }
}

// ==================== Modal ====================
.wd-modal-overlay, .wd-celebrate-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  backdrop-filter: blur(4px);
  z-index: $z-index-modal;
  @include flex-center;
  padding: $spacing-md;
}

.wd-modal {
  background: white;
  border-radius: $border-radius-lg;
  padding: $spacing-lg;
  width: 100%;
  max-width: 420px;
  box-shadow: $shadow-lg;

  h3 { margin: 0 0 4px; font-size: 17px; color: $text-primary; }
  &__hint { margin: 0 0 12px; font-size: 12px; color: $text-muted; }

  textarea {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid $border-color;
    border-radius: $border-radius-md;
    font-family: inherit;
    font-size: 14px;
    resize: vertical;
    outline: none;
    margin-bottom: $spacing-md;
    &:focus { border-color: #F43F5E; }
  }

  &__actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
}

.wd-celebrate {
  background: white;
  border-radius: $border-radius-lg;
  padding: $spacing-xl;
  text-align: center;
  max-width: 360px;
  box-shadow: $shadow-lg;
  animation: celebrate-in 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);

  &__badge {
    font-size: 48px;
    margin-bottom: 10px;
  }
  h2 { margin: 0 0 8px; color: $text-primary; }
  p { margin: 0 0 $spacing-md; color: $text-secondary; font-size: 13px; line-height: 1.6; }
}

@keyframes celebrate-in {
  0% { transform: scale(0.8); opacity: 0; }
  100% { transform: scale(1); opacity: 1; }
}

.btn-primary {
  padding: 8px 18px;
  border: none;
  border-radius: $border-radius-md;
  background: linear-gradient(135deg, #F43F5E, #FBBF24);
  color: white;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  &:hover { opacity: 0.92; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}
.btn-ghost {
  padding: 8px 18px;
  border-radius: $border-radius-md;
  border: 1px solid $border-color;
  background: transparent;
  color: $text-secondary;
  font-size: 13px;
  cursor: pointer;
  &:hover { color: $text-primary; border-color: $text-secondary; }
  &.btn-danger:hover { color: #EF4444; border-color: #EF4444; }
}
.btn-sm { padding: 6px 12px; font-size: 12px; }

.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
</style>
