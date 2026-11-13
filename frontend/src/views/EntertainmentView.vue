<script setup lang="ts">
import { ref } from 'vue'

const loading = ref(true)
const iframeError = ref(false)
const entertainmentUrl = import.meta.env.VITE_ENTERTAINMENT_URL || ''

const onIframeLoad = () => {
  loading.value = false
}

const onIframeError = () => {
  loading.value = false
  iframeError.value = true
}

const refreshIframe = () => {
  loading.value = true
  iframeError.value = false
  const iframe = document.querySelector('.entertainment__iframe') as HTMLIFrameElement
  if (iframe) {
    iframe.src = iframe.src
  }
}
</script>

<template>
  <div class="entertainment">
    <div v-if="!entertainmentUrl" class="entertainment__error">
      <p>未配置娱乐页面。请设置 VITE_ENTERTAINMENT_URL。</p>
    </div>
    <template v-else>
    <!-- 加载状态 -->
    <div v-if="loading" class="entertainment__loading">
      <div class="entertainment__spinner"></div>
      <span>加载中...</span>
    </div>

    <!-- 错误状态 -->
    <div v-if="iframeError" class="entertainment__error">
      <span class="entertainment__error-icon">😵</span>
      <p>页面加载失败</p>
      <button class="entertainment__retry-btn" @click="refreshIframe">重新加载</button>
    </div>

    <!-- iframe 内容 -->
    <iframe
      class="entertainment__iframe"
      :src="entertainmentUrl"
      frameborder="0"
      allowfullscreen
      @load="onIframeLoad"
      @error="onIframeError"
    ></iframe>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.entertainment {
  position: relative;
  width: 100%;
  height: calc(100vh - 80px);
  border-radius: $border-radius-lg;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(10px);
  box-shadow: $shadow-md;

  @media (max-width: $breakpoint-md) {
    height: calc(100vh - 60px - #{$mobile-tab-height} - env(safe-area-inset-bottom, 0px));
    border-radius: $border-radius-md;
  }

  &__loading {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: $spacing-md;
    background: rgba(255, 255, 255, 0.9);
    z-index: 10;
    color: $text-secondary;
    font-size: $font-size-md;
  }

  &__spinner {
    width: 40px;
    height: 40px;
    border: 3px solid rgba($primary-color, 0.2);
    border-top-color: $primary-color;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  &__error {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: $spacing-md;
    background: rgba(255, 255, 255, 0.95);
    z-index: 10;

    &-icon {
      font-size: 48px;
    }

    p {
      color: $text-secondary;
      font-size: $font-size-md;
    }
  }

  &__retry-btn {
    padding: $spacing-sm $spacing-lg;
    border-radius: $border-radius-md;
    background: linear-gradient(135deg, $primary-color, $accent-color);
    color: white;
    font-size: $font-size-sm;
    font-weight: 600;
    cursor: pointer;
    transition: all $transition-fast;

    &:hover {
      transform: translateY(-1px);
      box-shadow: $shadow-md;
    }
  }

  &__iframe {
    width: 100%;
    height: 100%;
    border: none;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
