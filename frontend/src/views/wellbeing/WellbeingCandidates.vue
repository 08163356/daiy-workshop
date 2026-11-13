<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWellbeingStore } from '@/stores/useWellbeingStore'

const router = useRouter()
const store = useWellbeingStore()

const tab = ref<'pending' | 'accepted' | 'rejected'>('pending')

async function load() {
  await store.fetchCandidates(tab.value)
}

const editing = ref<Record<number, { content: string; category: string; intensity: number }>>({})

const list = computed(() => store.candidates.filter(c => c.status === tab.value))

function startEdit(id: number) {
  const c = store.candidates.find(x => x.id === id)
  if (!c) return
  editing.value[id] = {
    content: c.suggested_content,
    category: c.suggested_category || '',
    intensity: c.suggested_intensity,
  }
}

async function accept(id: number) {
  const e = editing.value[id]
  await store.reviewCandidate(id, {
    action: 'accept',
    content: e?.content,
    category: e?.category || undefined,
    intensity: e?.intensity,
  })
  delete editing.value[id]
  await store.fetchOverview()
}

async function reject(id: number) {
  await store.reviewCandidate(id, { action: 'reject' })
}

onMounted(load)
</script>

<template>
  <div class="wb-cands">
    <div class="wb-cands__head">
      <h2><MagicStick class="ep-icon" /> 候选审核区</h2>
      <p>AI 从你的日记里发现了一些值得记下的瞬间。看看哪些值得入库。</p>
    </div>

    <div class="wb-tabs">
      <button v-for="t in (['pending','accepted','rejected'] as const)" :key="t"
        :class="{ active: tab === t }" @click="tab = t; load()">
        {{ t === 'pending' ? '待审核' : t === 'accepted' ? '已采纳' : '已忽略' }}
      </button>
    </div>

    <div v-if="store.loading" class="wb-empty">加载中…</div>
    <div v-else-if="list.length === 0" class="wb-empty">
      <template v-if="tab === 'pending'">
        🎉 暂无待审核候选。继续写日记，AI 会自动发现新的瞬间。
      </template>
      <template v-else>这里还没有内容。</template>
    </div>

    <div v-else class="wb-cands__grid">
      <div v-for="c in list" :key="c.id" class="wb-cand"
        :class="`wb-cand--${c.suggested_type}`">
        <div class="wb-cand__head">
          <span class="wb-cand__type">
            <Trophy v-if="c.suggested_type === 'achievement'" class="ep-icon" /> {{ c.suggested_type === 'achievement' ? '成就' : '🙏 感恩' }}
          </span>
          <span class="wb-cand__conf">置信度 {{ (c.ai_confidence * 100).toFixed(0) }}%</span>
        </div>

        <div class="wb-cand__body" v-if="!editing[c.id]">
          <div class="wb-cand__content">{{ c.suggested_content }}</div>
          <div v-if="c.source_excerpt" class="wb-cand__excerpt">
            原文片段：「{{ c.source_excerpt }}」
          </div>
          <div v-if="c.ai_reason" class="wb-cand__reason">💭 {{ c.ai_reason }}</div>
          <div class="wb-cand__meta">
            <span v-if="c.suggested_category" class="wb-tag">{{ c.suggested_category }}</span>
            <span class="wb-stars">{{ '★'.repeat(c.suggested_intensity) }}</span>
            <a v-if="c.source_type === 'diary'" @click="router.push(`/diary/${c.source_id}`)">✒️ 查看原日记</a>
          </div>
        </div>

        <div class="wb-cand__body" v-else>
          <textarea v-model="editing[c.id].content" rows="2" />
          <div class="wb-cand__edit-row">
            <input v-model="editing[c.id].category" placeholder="分类" />
            <div class="wb-stars-input">
              <span v-for="n in 5" :key="n"
                :class="{ on: n <= editing[c.id].intensity }"
                @click="editing[c.id].intensity = n">★</span>
            </div>
          </div>
        </div>

        <div class="wb-cand__actions" v-if="tab === 'pending'">
          <template v-if="!editing[c.id]">
            <button class="btn-ghost" @click="startEdit(c.id)"><EditPen class="ep-icon" />️ 编辑</button>
            <button class="btn-ghost btn-danger" @click="reject(c.id)"><Close class="ep-icon" /> 忽略</button>
            <button class="btn-primary" @click="accept(c.id)">✓ 采纳</button>
          </template>
          <template v-else>
            <button class="btn-ghost" @click="delete editing[c.id]">取消</button>
            <button class="btn-primary" @click="accept(c.id)">保存并采纳</button>
          </template>
        </div>
        <div class="wb-cand__status" v-else>
          <Close v-if="tab !== 'accepted'" class="ep-icon" /> {{ tab === 'accepted' ? '✓ 已入库' : '已忽略' }}
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
$mint: #14B8A6;
$peach: #F97316;

.wb-cands {
  display: flex; flex-direction: column; gap: $spacing-md;
  &__head {
    h2 { margin: 0; font-size: 22px; color: $text-primary; }
    p { color: $text-muted; font-size: 13px; margin: 4px 0 0; }
  }
  &__grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: $spacing-md;
  }
}

.wb-tabs {
  display: flex; gap: 6px;
  button {
    padding: 6px 14px; border-radius: 999px; border: 1px solid $border-color;
    background: white; cursor: pointer; font-size: 13px;
    &.active { background: linear-gradient(135deg, $mint, $peach); color: white; border-color: transparent; }
  }
}

.wb-empty { @include glass-card; padding: 40px; text-align: center; color: $text-muted; }

.wb-cand {
  @include glass-card;
  padding: $spacing-md;
  display: flex; flex-direction: column; gap: $spacing-sm;
  border-top: 3px solid transparent;
  &--achievement { border-top-color: $mint; }
  &--gratitude { border-top-color: $peach; }

  &__head { display: flex; justify-content: space-between; }
  &__type { font-weight: 600; color: $text-primary; font-size: 14px; }
  &__conf { font-size: 11px; color: $text-muted; }

  &__body { display: flex; flex-direction: column; gap: 6px; }
  &__content { font-size: 14px; color: $text-primary; line-height: 1.6; }
  &__excerpt {
    font-size: 12px; color: $text-muted;
    background: rgba(0,0,0,.03); padding: 6px 10px; border-radius: 6px;
  }
  &__reason { font-size: 12px; color: #6366f1; }
  &__meta {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    font-size: 12px; color: $text-muted;
    a { color: #6366f1; cursor: pointer; }
  }
  &__edit-row { display: flex; gap: 8px; align-items: center; }
  textarea, input {
    width: 100%; padding: 8px; border: 1px solid $border-color; border-radius: 6px;
    font-family: inherit; font-size: 13px; outline: none;
    &:focus { border-color: $mint; }
  }
  input { flex: 1; }

  &__actions { display: flex; gap: 6px; justify-content: flex-end; }
  &__status { color: $text-muted; font-size: 12px; text-align: right; }
}

.wb-tag { padding: 2px 8px; border-radius: 999px; background: rgba($mint, .12); color: $mint; }
.wb-stars { color: #f59e0b; }
.wb-stars-input {
  display: flex; gap: 2px;
  span { font-size: 18px; cursor: pointer; color: #cbd5e1; &.on { color: #f59e0b; } }
}

.btn-primary {
  padding: 6px 14px; border: none; border-radius: 8px;
  background: linear-gradient(135deg, $mint, $peach); color: white;
  font-size: 13px; cursor: pointer; font-weight: 600;
  &:hover { opacity: .9; }
}
.btn-ghost {
  padding: 6px 14px; border-radius: 8px; cursor: pointer;
  background: transparent; border: 1px solid $border-color; color: $text-secondary;
  font-size: 13px;
  &:hover { color: $mint; border-color: $mint; }
  &.btn-danger:hover { color: $danger-color; border-color: $danger-color; }
}
</style>
