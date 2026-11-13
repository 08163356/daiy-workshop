<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useWellbeingStore } from '@/stores/useWellbeingStore'

const router = useRouter()
const store = useWellbeingStore()
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    await store.fetchComfortCard(8, 6)
  } finally {
    loading.value = false
  }
}

function close() {
  router.back()
}

function openChat() {
  router.push('/assistant')
}

onMounted(load)
</script>

<template>
  <div class="anxiety">
    <div class="anxiety__bg"></div>

    <div class="anxiety__inner">
      <div class="anxiety__title">🌿 慢一点，没关系</div>

      <div v-if="loading" class="anxiety__loading">正在为你寻找温暖瞬间…</div>

      <template v-else>
        <div class="anxiety__msg">
          <div class="anxiety__msg-quote">「</div>
          <p>{{ store.comfortCard?.soothing_message }}</p>
          <div v-if="store.comfortCard?.fallback" class="anxiety__msg-fallback">
            （此刻 AI 暂时不可用，但这些话同样为你而备）
          </div>
        </div>

        <div class="anxiety__section" v-if="(store.comfortCard?.achievements?.length ?? 0) > 0">
          <div class="anxiety__section-title"><Trophy class="ep-icon" /> 你做到的事</div>
          <div class="anxiety__masonry">
            <div v-for="e in store.comfortCard?.achievements" :key="'a-' + e.id" class="anxiety__card anxiety__card--ach">
              <div class="anxiety__card-content">{{ e.content }}</div>
              <div class="anxiety__card-meta">
                <span v-if="e.category">{{ e.category }}</span>
                <span>{{ e.occurred_at }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="anxiety__section" v-if="(store.comfortCard?.gratitudes?.length ?? 0) > 0">
          <div class="anxiety__section-title">🙏 你被善待的瞬间</div>
          <div class="anxiety__masonry">
            <div v-for="e in store.comfortCard?.gratitudes" :key="'g-' + e.id" class="anxiety__card anxiety__card--grat">
              <div class="anxiety__card-content">{{ e.content }}</div>
              <div class="anxiety__card-meta">
                <span v-if="e.category">{{ e.category }}</span>
                <span>{{ e.occurred_at }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="(store.comfortCard?.achievements?.length ?? 0) === 0 && (store.comfortCard?.gratitudes?.length ?? 0) === 0" class="anxiety__empty">
          🌱 心力账户还是空的。<br>
          先回去记一条「今天虽然难，但我做到了……」吧。
        </div>

        <div class="anxiety__actions">
          <button class="anxiety__btn anxiety__btn--ghost" @click="close">我好点了，回去</button>
          <button class="anxiety__btn anxiety__btn--primary" @click="openChat"><ChatDotRound class="ep-icon" /> 找 AI 聊聊</button>
          <button class="anxiety__btn anxiety__btn--ghost" @click="load">换一组</button>
        </div>
      </template>
    </div>
  </div>
</template>

<style lang="scss" scoped>
$mint: #14B8A6;
$peach: #F97316;

.anxiety {
  position: relative;
  min-height: calc(100vh - 80px);
  padding: $spacing-xl 0;
  &__bg {
    position: fixed; inset: 0; z-index: -1;
    background: radial-gradient(ellipse at top left, rgba($mint, .25), transparent 50%),
                radial-gradient(ellipse at bottom right, rgba($peach, .2), transparent 50%),
                linear-gradient(135deg, #f0fdfa, #fff7ed);
    animation: breathe 12s ease-in-out infinite;
  }
  &__inner {
    max-width: 900px; margin: 0 auto;
    display: flex; flex-direction: column; gap: $spacing-xl;
    padding: 0 $spacing-md;
  }
  &__title {
    text-align: center; font-size: 32px; font-weight: 700; color: $text-primary;
    margin-top: $spacing-lg;
    @media (max-width: $breakpoint-md) { font-size: 26px; }
  }
  &__loading { text-align: center; color: $text-muted; padding: 40px; }
  &__empty { text-align: center; color: $text-muted; padding: 40px; line-height: 2; }

  &__msg {
    @include glass-card;
    padding: $spacing-xl;
    text-align: center; position: relative;
    background: rgba(255,255,255,.85);
    p {
      font-size: 18px; line-height: 2; color: $text-primary;
      margin: 0; font-weight: 500;
    }
    &-quote {
      position: absolute; top: -10px; left: 20px;
      font-size: 60px; color: rgba($mint, .3); line-height: 1; font-family: serif;
    }
    &-fallback { margin-top: 12px; font-size: 12px; color: $text-muted; }
  }

  &__section-title {
    font-size: $font-size-md; color: $text-secondary; margin-bottom: $spacing-md;
    text-align: center;
  }
  &__masonry {
    columns: 3 240px; column-gap: $spacing-md;
    > * { break-inside: avoid; margin-bottom: $spacing-md; }
  }
  &__card {
    @include glass-card;
    padding: $spacing-md;
    background: rgba(255,255,255,.9);
    transition: transform .3s ease;
    &:hover { transform: translateY(-3px) rotate(-.5deg); }
    &--ach { border-left: 3px solid $mint; }
    &--grat { border-left: 3px solid $peach; }

    &-content { font-size: 14px; line-height: 1.6; color: $text-primary; }
    &-meta {
      display: flex; gap: $spacing-md; margin-top: 8px;
      font-size: 11px; color: $text-muted;
    }
  }

  &__actions {
    display: flex; gap: $spacing-md; justify-content: center; flex-wrap: wrap;
    margin: $spacing-xl 0;
  }
  &__btn {
    padding: 12px 28px; border-radius: 999px; cursor: pointer; font-size: 14px;
    border: none; transition: all .2s;
    &--primary {
      background: linear-gradient(135deg, $mint, $peach); color: white;
      &:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba($mint, .4); }
    }
    &--ghost {
      background: transparent; color: $text-secondary;
      border: 1px solid rgba($text-secondary, .3);
      &:hover { color: $mint; border-color: $mint; }
    }
  }
}

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: .85; }
}
</style>
