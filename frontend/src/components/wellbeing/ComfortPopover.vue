<script setup lang="ts">
/**
 * 焦虑模式触发浮层：检测到负面情绪关键词后从右侧滑入。
 * 支持「展开焦虑模式」「关闭」「24h 不再提示」三个动作。
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import wellbeingApi, { type ComfortCardResponse } from '@/api/wellbeing'

const props = defineProps<{
  /** 触发命中的关键词，用于显示 */
  triggerKeywords?: string[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'snooze'): void
}>()

const router = useRouter()
const data = ref<ComfortCardResponse | null>(null)
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    data.value = await wellbeingApi.getComfortCard(3, 2)
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

function expand() {
  router.push('/wellbeing/anxiety')
  emit('close')
}

function snooze24h() {
  const until = Date.now() + 24 * 60 * 60 * 1000
  localStorage.setItem('wb_comfort_snooze_until', String(until))
  emit('snooze')
}

onMounted(load)
</script>

<template>
  <Transition name="comfort-slide">
    <div class="comfort-pop">
      <div class="comfort-pop__head">
        <span class="comfort-pop__title">💚 看看你之前的好</span>
        <button class="comfort-pop__close" @click="emit('close')">✕</button>
      </div>

      <div v-if="props.triggerKeywords?.length" class="comfort-pop__hint">
        发现你提到「{{ props.triggerKeywords.slice(0, 3).join('、') }}」，先停一下。
      </div>

      <div v-if="loading" class="comfort-pop__loading">为你寻找温暖瞬间…</div>

      <template v-else-if="data">
        <p class="comfort-pop__msg">{{ data.soothing_message }}</p>

        <div v-if="data.achievements.length || data.gratitudes.length" class="comfort-pop__cards">
          <div v-for="e in data.achievements" :key="'a-' + e.id" class="comfort-pop__card comfort-pop__card--ach">
            <span class="comfort-pop__card-tag">🏆</span>
            <span class="comfort-pop__card-text">{{ e.content }}</span>
          </div>
          <div v-for="e in data.gratitudes" :key="'g-' + e.id" class="comfort-pop__card comfort-pop__card--grat">
            <span class="comfort-pop__card-tag">🙏</span>
            <span class="comfort-pop__card-text">{{ e.content }}</span>
          </div>
        </div>
      </template>

      <div class="comfort-pop__actions">
        <button class="comfort-pop__btn comfort-pop__btn--primary" @click="expand">展开焦虑模式 →</button>
        <button class="comfort-pop__btn comfort-pop__btn--ghost" @click="emit('close')">我好点了</button>
        <button class="comfort-pop__snooze" @click="snooze24h">24h 不再提示</button>
      </div>
    </div>
  </Transition>
</template>

<style lang="scss" scoped>
$mint: #14B8A6;
$peach: #F97316;

.comfort-pop {
  position: fixed;
  right: $spacing-lg;
  bottom: $spacing-lg;
  width: 340px;
  max-width: calc(100vw - #{$spacing-lg * 2});
  z-index: 9000;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(20px);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(20, 184, 166, .25), 0 4px 16px rgba(0,0,0,.08);
  border: 1px solid rgba($mint, .25);
  padding: 16px;
  display: flex; flex-direction: column; gap: 10px;

  @media (max-width: $breakpoint-md) {
    right: $spacing-sm; left: $spacing-sm; bottom: 80px;
    width: auto;
  }

  &__head {
    display: flex; justify-content: space-between; align-items: center;
  }
  &__title { font-size: 14px; font-weight: 600; color: $text-primary; }
  &__close {
    background: transparent; border: none; cursor: pointer; color: $text-muted;
    width: 24px; height: 24px; border-radius: 50%;
    &:hover { background: rgba(0,0,0,.05); color: $text-primary; }
  }

  &__hint { font-size: 12px; color: $text-muted; }
  &__loading { padding: 20px; text-align: center; color: $text-muted; font-size: 12px; }
  &__msg {
    font-size: 13px; line-height: 1.7; color: $text-primary;
    background: linear-gradient(135deg, rgba($mint, .08), rgba($peach, .08));
    padding: 10px 12px; border-radius: 10px; margin: 0;
  }

  &__cards { display: flex; flex-direction: column; gap: 6px; }
  &__card {
    display: flex; gap: 8px; align-items: flex-start;
    padding: 8px 10px; border-radius: 8px;
    background: rgba(255,255,255,.7);
    border-left: 3px solid $mint;
    font-size: 12px; line-height: 1.6;
    &--grat { border-left-color: $peach; }
    &-tag { flex-shrink: 0; }
    &-text { color: $text-primary; }
  }

  &__actions {
    display: flex; gap: 6px; flex-wrap: wrap; align-items: center;
    margin-top: 4px;
  }
  &__btn {
    padding: 6px 12px; border-radius: 8px; cursor: pointer; font-size: 12px;
    border: none;
    &--primary {
      background: linear-gradient(135deg, $mint, $peach); color: white; font-weight: 600;
      &:hover { opacity: .9; }
    }
    &--ghost {
      background: transparent; color: $text-secondary; border: 1px solid $border-color;
      &:hover { color: $mint; border-color: $mint; }
    }
  }
  &__snooze {
    margin-left: auto; background: transparent; border: none; cursor: pointer;
    font-size: 11px; color: $text-muted; text-decoration: underline;
    &:hover { color: $text-primary; }
  }
}

.comfort-slide-enter-active, .comfort-slide-leave-active {
  transition: all .35s cubic-bezier(.4,0,.2,1);
}
.comfort-slide-enter-from {
  opacity: 0; transform: translateX(20px) translateY(10px);
}
.comfort-slide-leave-to {
  opacity: 0; transform: translateY(20px);
}
</style>
