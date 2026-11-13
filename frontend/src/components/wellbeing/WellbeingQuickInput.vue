<script setup lang="ts">
/**
 * 嵌入式快速录入：在日记/详情页底部使用
 * 支持成就 + 感恩 双栏快速记录
 */
import { ref } from 'vue'
import wellbeingApi from '@/api/wellbeing'

const props = defineProps<{
  /** 关联日记 id（可选） */
  diaryId?: number
  /** 默认日期 */
  date?: string
}>()

const emit = defineEmits<{
  (e: 'created', count: number): void
}>()

interface DraftItem {
  content: string
  intensity: number
  category: string
}

const ach = ref<DraftItem>({ content: '', intensity: 3, category: '' })
const grat = ref<DraftItem>({ content: '', intensity: 3, category: '' })

const submitting = ref(false)
const justSaved = ref(0)

const CATEGORIES = ['工作', '家庭', '健康', '关系', '学习', '其他']
const today = props.date || new Date().toISOString().slice(0, 10)

async function save() {
  const tasks: Promise<any>[] = []
  if (ach.value.content.trim()) {
    tasks.push(wellbeingApi.createEntry({
      type: 'achievement',
      content: ach.value.content.trim(),
      category: ach.value.category || null,
      intensity: ach.value.intensity,
      occurred_at: today,
      source_type: props.diaryId ? 'diary' : 'manual',
      source_id: props.diaryId,
    }))
  }
  if (grat.value.content.trim()) {
    tasks.push(wellbeingApi.createEntry({
      type: 'gratitude',
      content: grat.value.content.trim(),
      category: grat.value.category || null,
      intensity: grat.value.intensity,
      occurred_at: today,
      source_type: props.diaryId ? 'diary' : 'manual',
      source_id: props.diaryId,
    }))
  }
  if (tasks.length === 0) return

  submitting.value = true
  try {
    await Promise.all(tasks)
    justSaved.value = tasks.length
    ach.value = { content: '', intensity: 3, category: '' }
    grat.value = { content: '', intensity: 3, category: '' }
    emit('created', tasks.length)
    setTimeout(() => { justSaved.value = 0 }, 2400)
  } catch (e: any) {
    alert('保存失败：' + (e.message || ''))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="wb-qi">
    <div class="wb-qi__head">
      <span class="wb-qi__title">💚 顺手记一笔心力账户</span>
      <Transition name="fade">
        <span v-if="justSaved > 0" class="wb-qi__saved">已保存 {{ justSaved }} 条 ✓</span>
      </Transition>
    </div>

    <div class="wb-qi__cols">
      <!-- 成就 -->
      <div class="wb-qi__col">
        <div class="wb-qi__col-title">🏆 今日成就</div>
        <textarea
          v-model="ach.content"
          rows="2"
          placeholder="今天你做到的一件事，再小都算"
        />
        <div class="wb-qi__row">
          <select v-model="ach.category">
            <option value="">分类</option>
            <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
          </select>
          <div class="wb-qi__stars">
            <span v-for="n in 5" :key="n" :class="{ on: n <= ach.intensity }" @click="ach.intensity = n">★</span>
          </div>
        </div>
      </div>

      <!-- 感恩 -->
      <div class="wb-qi__col wb-qi__col--grat">
        <div class="wb-qi__col-title">🙏 今日感恩</div>
        <textarea
          v-model="grat.content"
          rows="2"
          placeholder="今天值得感恩的瞬间"
        />
        <div class="wb-qi__row">
          <select v-model="grat.category">
            <option value="">分类</option>
            <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
          </select>
          <div class="wb-qi__stars">
            <span v-for="n in 5" :key="n" :class="{ on: n <= grat.intensity }" @click="grat.intensity = n">★</span>
          </div>
        </div>
      </div>
    </div>

    <div class="wb-qi__foot">
      <button class="wb-qi__btn" :disabled="submitting" @click="save">
        {{ submitting ? '保存中…' : '保存到心力账户' }}
      </button>
    </div>
  </div>
</template>

<style lang="scss" scoped>
$mint: #14B8A6;
$peach: #F97316;

.wb-qi {
  border-radius: 12px;
  background: linear-gradient(135deg, rgba($mint, .06), rgba($peach, .06));
  border: 1px dashed rgba($mint, .3);
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 10px;

  &__head {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 13px; color: $text-secondary;
  }
  &__title { font-weight: 600; color: $text-primary; }
  &__saved { color: $mint; font-size: 12px; }

  &__cols {
    display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
    @media (max-width: $breakpoint-md) { grid-template-columns: 1fr; }
  }
  &__col {
    background: rgba(255,255,255,.6); border-radius: 10px; padding: 10px;
    display: flex; flex-direction: column; gap: 6px;
    border-left: 3px solid $mint;
    &--grat { border-left-color: $peach; }
  }
  &__col-title { font-size: 12px; font-weight: 600; color: $text-primary; }
  textarea {
    width: 100%; padding: 8px; border: 1px solid $border-color; border-radius: 6px;
    font-family: inherit; font-size: 13px; outline: none; resize: vertical;
    background: white;
    &:focus { border-color: $mint; }
  }
  &__row {
    display: flex; gap: 8px; align-items: center;
    select {
      padding: 4px 8px; border: 1px solid $border-color; border-radius: 6px;
      background: white; font-size: 12px; outline: none;
      &:focus { border-color: $mint; }
    }
  }
  &__stars {
    display: flex; gap: 1px; margin-left: auto;
    span {
      font-size: 16px; cursor: pointer; user-select: none; color: #cbd5e1;
      &.on { color: #f59e0b; }
    }
  }

  &__foot { display: flex; justify-content: flex-end; }
  &__btn {
    padding: 8px 18px; border: none; border-radius: 8px; cursor: pointer;
    background: linear-gradient(135deg, $mint, $peach); color: white;
    font-size: 13px; font-weight: 600;
    &:hover { opacity: .9; }
    &:disabled { opacity: .5; cursor: not-allowed; }
  }
}

.fade-enter-active, .fade-leave-active { transition: opacity .25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
