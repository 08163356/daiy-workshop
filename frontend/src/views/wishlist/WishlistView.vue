<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { wishlistApi, WISH_CATEGORIES, categoryMeta, type WishSummary } from '@/api/wishlist'
import AppIcon from '@/components/common/AppIcon.vue'

const router = useRouter()

const wishes = ref<WishSummary[]>([])
const loading = ref(false)
const activeCategories = ref<string[]>([])
const statusTab = ref<'active' | 'achieved'>('active')

const showCreateModal = ref(false)
const creating = ref(false)
const newContent = ref('')
const newCategory = ref<string>('growth')
const newLinkedCategory = ref('')

async function load() {
  loading.value = true
  try {
    const res = await wishlistApi.list({ status: statusTab.value, limit: 200 })
    wishes.value = res.items
  } catch (e) {
    console.error('加载心愿列表失败', e)
  } finally {
    loading.value = false
  }
}

const filteredWishes = computed(() => {
  if (activeCategories.value.length === 0) return wishes.value
  return wishes.value.filter(w => activeCategories.value.includes(w.category))
})

function toggleCategory(cat: string) {
  const idx = activeCategories.value.indexOf(cat)
  if (idx >= 0) activeCategories.value.splice(idx, 1)
  else activeCategories.value.push(cat)
}

function openWish(id: number) {
  router.push(`/wishlist/${id}`)
}

function openCreateModal() {
  newContent.value = ''
  newCategory.value = 'growth'
  newLinkedCategory.value = ''
  showCreateModal.value = true
}

async function submitCreate() {
  if (!newContent.value.trim()) return
  creating.value = true
  try {
    await wishlistApi.create({
      content: newContent.value.trim(),
      category: newCategory.value,
      linked_todo_category: newLinkedCategory.value.trim() || null,
    })
    showCreateModal.value = false
    await load()
  } catch (e) {
    console.error('创建心愿失败', e)
    alert('创建失败，请稍后再试')
  } finally {
    creating.value = false
  }
}

async function switchTab(tab: 'active' | 'achieved') {
  statusTab.value = tab
  await load()
}

onMounted(load)
</script>

<template>
  <div class="wish-page">
    <div class="wish-hero">
      <div class="wish-hero__text">
        <h1><AppIcon name="sparkles" :size="26" class="wish-hero__icon" /> 心愿清单</h1>
        <p>不限大小地写下你的愿望——健康、事业、财富、关系、成长、物质，写下来，就是吸引它靠近的第一步。</p>
      </div>
      <div class="wish-hero__tabs">
        <button :class="{ active: statusTab === 'active' }" @click="switchTab('active')">进行中</button>
        <button :class="{ active: statusTab === 'achieved' }" @click="switchTab('achieved')">✨ 已实现</button>
      </div>
    </div>

    <div class="wish-filters">
      <button
        v-for="c in WISH_CATEGORIES"
        :key="c.value"
        class="wish-filter-chip"
        :class="{ active: activeCategories.includes(c.value) }"
        :style="{ '--chip-color': c.color }"
        @click="toggleCategory(c.value)"
      >
        <span class="dot" :style="{ background: c.color }"></span>
        {{ c.label }}
      </button>
    </div>

    <div v-if="loading" class="wish-empty">加载中…</div>
    <div v-else-if="filteredWishes.length === 0" class="wish-empty">
      <AppIcon name="sparkles" :size="32" />
      <p v-if="statusTab === 'active'">还没有写下心愿，点击右下角开始吧</p>
      <p v-else>还没有心愿被实现，继续加油～</p>
    </div>

    <div v-else class="wish-grid">
      <div
        v-for="w in filteredWishes"
        :key="w.id"
        class="wish-card"
        :class="{ 'wish-card--achieved': w.status === 'achieved' }"
        :style="{ '--cat-color': categoryMeta(w.category).color }"
        @click="openWish(w.id)"
      >
        <div class="wish-card__bar"></div>
        <div class="wish-card__body">
          <div class="wish-card__cat">
            <span class="dot" :style="{ background: categoryMeta(w.category).color }"></span>
            {{ categoryMeta(w.category).label }}
          </div>
          <p class="wish-card__content">{{ w.content }}</p>

          <template v-if="w.status === 'achieved'">
            <div class="wish-card__achieved-badge">✨ 已实现</div>
          </template>
          <template v-else>
            <div class="wish-card__progress">
              <div class="wish-card__progress-track">
                <div class="wish-card__progress-fill" :style="{ width: w.progress + '%' }"></div>
              </div>
              <span class="wish-card__progress-text">{{ w.progress }}%</span>
            </div>
            <div class="wish-card__meta">
              <span v-if="w.milestones_count > 0" class="wish-card__badge">
                <AppIcon name="check-circle-2" :size="12" /> {{ w.completed_milestones_count }}/{{ w.milestones_count }}
              </span>
              <span v-if="w.linked_todo_category" class="wish-card__badge wish-card__badge--todo">
                🔗 {{ w.linked_todo_category }}
              </span>
            </div>
          </template>
        </div>
      </div>
    </div>

    <button class="wish-fab" @click="openCreateModal" title="写心愿">
      <AppIcon name="plus" :size="24" />
    </button>

    <!-- 写心愿 Modal -->
    <Transition name="modal-fade">
      <div v-if="showCreateModal" class="wish-modal-overlay" @click.self="showCreateModal = false">
        <div class="wish-modal">
          <div class="wish-modal__header">
            <h3>✨ 写下一个心愿</h3>
            <button class="wish-modal__close" @click="showCreateModal = false"><AppIcon name="x" :size="18" /></button>
          </div>
          <p class="wish-modal__hint">不限大小，不用考虑能否实现，写下来就好。</p>
          <textarea v-model="newContent" rows="3" placeholder="例如：养成每天运动30分钟的习惯 / 存够一年的应急基金 / 和家人一起去看一次极光…" />

          <div class="wish-modal__field">
            <label>属于哪个维度？</label>
            <div class="wish-modal__cats">
              <button
                v-for="c in WISH_CATEGORIES"
                :key="c.value"
                class="wish-modal__cat-btn"
                :class="{ active: newCategory === c.value }"
                :style="{ '--chip-color': c.color }"
                @click="newCategory = c.value"
              >{{ c.label }}</button>
            </div>
          </div>

          <div class="wish-modal__field">
            <label>关联待办分类（可选，完成该分类待办会自动推进进度）</label>
            <input v-model="newLinkedCategory" placeholder="例如：健身 / 阅读" />
          </div>

          <div class="wish-modal__actions">
            <button class="btn-ghost" @click="showCreateModal = false">取消</button>
            <button class="btn-primary" :disabled="creating || !newContent.trim()" @click="submitCreate">
              {{ creating ? '保存中…' : '写下这个心愿' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style lang="scss" scoped>
.wish-page {
  padding: $spacing-lg;
  max-width: 1200px;
  margin: 0 auto;
  padding-bottom: 100px;

  @media (max-width: $breakpoint-md) {
    padding: $spacing-md;
    padding-bottom: 90px;
  }
}

.wish-hero {
  @include glass-card;
  padding: $spacing-lg;
  margin-bottom: $spacing-lg;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: $spacing-md;
  background: linear-gradient(135deg, rgba(#F43F5E, 0.06), rgba(#FBBF24, 0.06));
  flex-wrap: wrap;

  &__text {
    h1 {
      margin: 0 0 6px;
      font-size: 24px;
      font-weight: 700;
      color: $text-primary;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    p {
      margin: 0;
      color: $text-secondary;
      font-size: 13px;
      max-width: 520px;
      line-height: 1.6;
    }
  }

  &__icon { color: #F43F5E; }

  &__tabs {
    display: flex;
    gap: 6px;
    flex-shrink: 0;

    button {
      padding: 8px 16px;
      border-radius: 999px;
      border: 1px solid $border-color;
      background: white;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      color: $text-secondary;
      transition: all $transition-fast;

      &.active {
        background: linear-gradient(135deg, #F43F5E, #FBBF24);
        color: white;
        border-color: transparent;
        box-shadow: 0 4px 12px rgba(#F43F5E, 0.3);
      }
    }
  }
}

.wish-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: $spacing-lg;
}

.wish-filter-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid $border-color;
  background: white;
  cursor: pointer;
  font-size: 13px;
  color: $text-secondary;
  transition: all $transition-fast;

  .dot { width: 8px; height: 8px; border-radius: 50%; }

  &.active {
    border-color: var(--chip-color);
    color: var(--chip-color);
    background: color-mix(in srgb, var(--chip-color) 10%, white);
    font-weight: 600;
  }

  &:hover { border-color: var(--chip-color); }
}

.wish-empty {
  @include glass-card;
  padding: 60px 20px;
  text-align: center;
  color: $text-muted;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.wish-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: $spacing-md;
}

.wish-card {
  @include glass-card;
  @include hover-lift;
  cursor: pointer;
  overflow: hidden;
  display: flex;
  transition: opacity $transition-normal, transform $transition-normal, box-shadow $transition-normal;

  &__bar {
    width: 6px;
    flex-shrink: 0;
    background: linear-gradient(180deg, var(--cat-color), rgba(255,255,255,0));
  }

  &__body {
    flex: 1;
    padding: $spacing-md;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-width: 0;
  }

  &__cat {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--cat-color);

    .dot { width: 7px; height: 7px; border-radius: 50%; }
  }

  &__content {
    margin: 0;
    font-size: 15px;
    color: $text-primary;
    line-height: 1.6;
    @include text-clamp(3);
  }

  &__progress {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  &__progress-track {
    flex: 1;
    height: 6px;
    border-radius: 999px;
    background: rgba(0,0,0,0.06);
    overflow: hidden;
  }

  &__progress-fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #F43F5E, #FBBF24);
    transition: width 0.6s cubic-bezier(0.22, 1, 0.36, 1);
  }

  &__progress-text {
    font-size: 12px;
    font-weight: 700;
    color: $text-secondary;
    min-width: 34px;
    text-align: right;
  }

  &__meta {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }

  &__badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 2px 8px;
    border-radius: 999px;
    background: rgba(0,0,0,0.04);
    font-size: 11px;
    color: $text-secondary;

    &--todo { background: rgba(#3B82F6, 0.1); color: #3B82F6; }
  }

  &__achieved-badge {
    display: inline-flex;
    align-self: flex-start;
    padding: 3px 12px;
    border-radius: 999px;
    background: linear-gradient(135deg, #FBBF24, #F59E0B);
    color: white;
    font-size: 12px;
    font-weight: 700;
  }

  &--achieved {
    opacity: 0.55;

    .wish-card__content {
      text-decoration: line-through;
      text-decoration-color: rgba(0,0,0,0.3);
    }
  }
}

.wish-fab {
  position: fixed;
  right: 28px;
  bottom: 32px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #F43F5E, #FB7185);
  color: white;
  @include flex-center;
  box-shadow: 0 8px 24px rgba(#F43F5E, 0.4);
  cursor: pointer;
  transition: transform $transition-fast;
  z-index: 90;

  &:hover { transform: scale(1.08) rotate(90deg); }

  @media (max-width: $breakpoint-md) {
    bottom: calc(#{$mobile-tab-height} + 16px);
    right: 20px;
    width: 50px;
    height: 50px;
  }
}

// ==================== Modal ====================
.wish-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  backdrop-filter: blur(4px);
  z-index: $z-index-modal;
  @include flex-center;
  padding: $spacing-md;
}

.wish-modal {
  background: white;
  border-radius: $border-radius-lg;
  padding: $spacing-lg;
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: $shadow-lg;

  &__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;

    h3 { margin: 0; font-size: 18px; color: $text-primary; }
  }

  &__close {
    border: none; background: transparent; color: $text-muted; cursor: pointer;
    width: 28px; height: 28px; @include flex-center; border-radius: 50%;
    &:hover { background: rgba(0,0,0,0.06); }
  }

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

    &:focus { border-color: #F43F5E; box-shadow: 0 0 0 2px rgba(#F43F5E, 0.1); }
  }

  &__field {
    margin-bottom: $spacing-md;

    label { display: block; font-size: 12px; color: $text-secondary; margin-bottom: 6px; font-weight: 600; }

    input {
      width: 100%;
      padding: 8px 12px;
      border: 1px solid $border-color;
      border-radius: $border-radius-md;
      font-size: 13px;
      outline: none;
      &:focus { border-color: #F43F5E; }
    }
  }

  &__cats {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  &__cat-btn {
    padding: 5px 12px;
    border-radius: 999px;
    border: 1px solid $border-color;
    background: white;
    font-size: 12px;
    cursor: pointer;
    color: $text-secondary;

    &.active {
      border-color: var(--chip-color);
      background: var(--chip-color);
      color: white;
      font-weight: 600;
    }
  }

  &__actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: $spacing-sm;
  }
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
}

.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity 0.2s ease; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
</style>
