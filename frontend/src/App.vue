<script setup lang="ts">
import { ref, onMounted, onUnmounted, provide } from 'vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import CapsuleDetector from '@/views/timeCapsule/CapsuleDetector.vue'
import { API_BASE } from '@/config'
import { LockKeyhole, Eye } from '@lucide/vue'

const AUTH_API = `${API_BASE}/api/auth`
const GUEST_URL = import.meta.env.VITE_DEMO_URL || ''
const TOKEN_KEY = 'daily_auth_token'

// 演示模式：/daily-show/ 路径下跳过认证和锁屏
const isDemo = import.meta.env.BASE_URL === '/daily-show/'

const authed = ref(false)
const checking = ref(true)
const password = ref('')
const loginError = ref('')
const loginLoading = ref(false)

async function checkToken() {
  // 演示模式直接放行
  if (isDemo) { authed.value = true; checking.value = false; return }

  const token = localStorage.getItem(TOKEN_KEY)
  if (!token) { checking.value = false; return }
  try {
    const res = await fetch(`${AUTH_API}/check`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    })
    if (res.ok) { authed.value = true }
    else { localStorage.removeItem(TOKEN_KEY) }
  } catch { /* 后端不可用时也放行（本地开发） */ authed.value = true }
  checking.value = false
}

async function login() {
  if (!password.value.trim()) return
  loginLoading.value = true
  loginError.value = ''
  try {
    const res = await fetch(`${AUTH_API}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: password.value }),
    })
    if (res.ok) {
      const data = await res.json()
      localStorage.setItem(TOKEN_KEY, data.token)
      authed.value = true
    } else {
      const err = await res.json()
      loginError.value = err.detail || '密码错误'
    }
  } catch (e: any) {
    if (e.message?.includes('fetch')) { authed.value = true }
    else { loginError.value = '网络错误' }
  } finally {
    loginLoading.value = false
  }
}

function goGuest() {
  if (GUEST_URL) window.location.href = GUEST_URL
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') login()
}

// ==================== 锁屏功能 ====================

const locked = ref(false)
const autoLockMinutes = ref(13)
const lockCountdown = ref<number | null>(null)
const unlockPassword = ref('')
const unlockError = ref('')
const unlockLoading = ref(false)

let lastActivityTime = Date.now()
let idleCheckInterval: ReturnType<typeof setInterval> | null = null
let countdownInterval: ReturnType<typeof setInterval> | null = null

function resetActivity() {
  lastActivityTime = Date.now()
}

function checkIdle() {
  if (isDemo || locked.value || !authed.value) return
  if (lockCountdown.value !== null) return
  const idleMs = Date.now() - lastActivityTime
  if (idleMs >= autoLockMinutes.value * 60 * 1000) {
    lockApp()
  }
}

function lockApp() {
  if (isDemo) return
  locked.value = true
  lockCountdown.value = null
  // 清空残存密码，避免下次解锁时输入框还带着旧密码
  unlockPassword.value = ''
  unlockError.value = ''
  if (countdownInterval) { clearInterval(countdownInterval); countdownInterval = null }
}

function startCountdownLock(minutes: number) {
  lockCountdown.value = minutes * 60
  if (countdownInterval) clearInterval(countdownInterval)
  countdownInterval = setInterval(() => {
    if (lockCountdown.value !== null) {
      lockCountdown.value--
      if (lockCountdown.value <= 0) lockApp()
    }
  }, 1000)
}

function cancelCountdown() {
  lockCountdown.value = null
  if (countdownInterval) { clearInterval(countdownInterval); countdownInterval = null }
}

async function unlockApp() {
  if (!unlockPassword.value.trim()) return
  unlockLoading.value = true
  unlockError.value = ''
  try {
    const res = await fetch(`${AUTH_API}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: unlockPassword.value }),
    })
    if (res.ok) {
      locked.value = false
      unlockPassword.value = ''
      lastActivityTime = Date.now()
    } else {
      unlockError.value = '密码错误'
    }
  } catch {
    locked.value = false
    unlockPassword.value = ''
  } finally {
    unlockLoading.value = false
  }
}

function handleUnlockKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') unlockApp()
}

async function fetchLockSettings() {
  try {
    const res = await fetch(`${AUTH_API}/lock-settings`)
    if (res.ok) {
      const data = await res.json()
      autoLockMinutes.value = data.auto_lock_minutes
    }
  } catch { /* use default */ }
}

async function saveLockSettings(minutes: number) {
  autoLockMinutes.value = minutes
  try {
    await fetch(`${AUTH_API}/lock-settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto_lock_minutes: minutes }),
    })
  } catch { /* silent */ }
}

function handleVisibilityChange() {
  if (document.visibilityState === 'visible') checkIdle()
}

provide('lockApp', lockApp)
provide('startCountdownLock', startCountdownLock)
provide('cancelCountdown', cancelCountdown)
provide('lockCountdown', lockCountdown)
provide('autoLockMinutes', autoLockMinutes)
provide('saveLockSettings', saveLockSettings)
provide('isDemo', isDemo)

const ACTIVITY_EVENTS = ['mousemove', 'keydown', 'click', 'touchstart', 'scroll']

onMounted(() => {
  checkToken()
  fetchLockSettings()
  ACTIVITY_EVENTS.forEach(e => window.addEventListener(e, resetActivity, { passive: true }))
  document.addEventListener('visibilitychange', handleVisibilityChange)
  idleCheckInterval = setInterval(checkIdle, 5000)
})

onUnmounted(() => {
  ACTIVITY_EVENTS.forEach(e => window.removeEventListener(e, resetActivity))
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  if (idleCheckInterval) clearInterval(idleCheckInterval)
  if (countdownInterval) clearInterval(countdownInterval)
})
</script>

<template>
  <!-- 检查中：空白 -->
  <div v-if="checking" class="auth-loading">
    <div class="auth-spinner"></div>
  </div>

  <!-- 未认证：登录门 -->
  <div v-else-if="!authed" class="auth-gate">
    <div class="app-bg">
      <div class="app-bg__circle app-bg__circle--1"></div>
      <div class="app-bg__circle app-bg__circle--2"></div>
    </div>
    <div class="auth-card">
      <div class="auth-card__icon"><LockKeyhole :size="36" :stroke-width="1.5" /></div>
      <h1 class="auth-card__title">Daily System</h1>
      <p class="auth-card__subtitle">个人知识操作系统</p>

      <div class="auth-card__form">
        <input
          v-model="password"
          type="password"
          class="auth-input"
          placeholder="请输入访问密码"
          @keydown="handleKeydown"
          autofocus
        />
        <button class="auth-btn auth-btn--primary" @click="login" :disabled="loginLoading">
          {{ loginLoading ? '验证中...' : '进入系统' }}
        </button>
        <div v-if="loginError" class="auth-error">{{ loginError }}</div>
      </div>

      <div class="auth-card__divider">
        <span>或</span>
      </div>

      <button v-if="GUEST_URL" class="auth-btn auth-btn--ghost" @click="goGuest">
        <Eye :size="16" style="margin-right:6px;vertical-align:middle;" /> 游客模式（查看演示版）
      </button>
    </div>
  </div>

  <!-- 已认证：正常应用 -->
  <div v-else class="app">
    <div class="app-bg">
      <div class="app-bg__circle app-bg__circle--1"></div>
      <div class="app-bg__circle app-bg__circle--2"></div>
      <div class="app-bg__circle app-bg__circle--3"></div>
    </div>
    <AppHeader />
    <main class="app-main">
      <router-view v-slot="{ Component, route }">
        <component :is="Component" :key="route.path" />
      </router-view>
    </main>
    <!-- 时光胶囊开封检测 -->
    <CapsuleDetector />

    <!-- 锁屏覆盖层 -->
    <Transition name="lock-fade">
      <div v-if="locked" class="lock-overlay">
        <div class="lock-card">
          <div class="lock-card__icon"><LockKeyhole :size="48" :stroke-width="1.2" /></div>
          <h2 class="lock-card__title">已锁定</h2>
          <p class="lock-card__subtitle">输入密码以解锁系统</p>
          <div class="lock-card__form">
            <input
              v-model="unlockPassword"
              type="password"
              class="auth-input"
              placeholder="请输入访问密码"
              @keydown="handleUnlockKeydown"
              autofocus
            />
            <button class="auth-btn auth-btn--primary" @click="unlockApp" :disabled="unlockLoading">
              {{ unlockLoading ? '验证中...' : '解锁' }}
            </button>
            <div v-if="unlockError" class="auth-error">{{ unlockError }}</div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style lang="scss" scoped>
.auth-loading {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.auth-spinner {
  width: 32px; height: 32px;
  border: 3px solid rgba($primary-color, 0.2);
  border-top-color: $primary-color;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.auth-gate {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.auth-card {
  @include glass-card;
  padding: 48px 40px;
  max-width: 400px;
  width: 90%;
  text-align: center;
  z-index: 1;

  &__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 16px;
    color: $primary-color;
  }
  &__title {
    font-size: 28px; font-weight: 700; color: $text-primary;
    margin-bottom: 4px;
  }
  &__subtitle {
    font-size: 14px; color: $text-secondary; margin-bottom: 32px;
  }
  &__form {
    display: flex; flex-direction: column; gap: 12px;
  }
  &__divider {
    display: flex; align-items: center; gap: 16px;
    margin: 24px 0;
    &::before, &::after {
      content: ''; flex: 1; height: 1px; background: $border-color;
    }
    span { font-size: 13px; color: $text-muted; }
  }
}

.auth-input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid $border-color;
  border-radius: 10px;
  font-size: 16px;
  background: rgba(255, 255, 255, 0.8);
  transition: border-color 0.2s, box-shadow 0.2s;
  outline: none;
  &:focus {
    border-color: $primary-color;
    box-shadow: 0 0 0 3px rgba($primary-color, 0.15);
  }
}

.auth-btn {
  padding: 12px 24px;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  border: none;

  &--primary {
    background: linear-gradient(135deg, $primary-color, $accent-color);
    color: white;
    &:hover { opacity: 0.9; transform: translateY(-1px); box-shadow: 0 4px 12px rgba($primary-color, 0.3); }
    &:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
  }
  &--ghost {
    background: transparent;
    color: $text-secondary;
    border: 1px solid $border-color;
    &:hover { color: $primary-color; border-color: $primary-color; background: rgba($primary-color, 0.05); }
  }
}

.auth-error {
  font-size: 13px; color: $danger-color; margin-top: 4px;
}

.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow-x: hidden;
}

.app-bg {
  position: fixed;
  top: 0; left: 0;
  width: 100%; height: 100%;
  pointer-events: none;
  z-index: -1;
  overflow: hidden;

  &__circle {
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    opacity: 0.5;

    &--1 {
      width: 600px; height: 600px;
      background: linear-gradient(135deg, rgba($primary-color, 0.3), rgba($accent-color, 0.2));
      top: -200px; right: -100px;
      animation: float 20s ease-in-out infinite;
    }
    &--2 {
      width: 400px; height: 400px;
      background: linear-gradient(135deg, rgba($accent-color, 0.2), rgba($primary-color, 0.1));
      bottom: -100px; left: -100px;
      animation: float 25s ease-in-out infinite reverse;
    }
    &--3 {
      width: 300px; height: 300px;
      background: linear-gradient(135deg, rgba($success-color, 0.15), rgba($primary-color, 0.1));
      top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      animation: float 30s ease-in-out infinite;
    }
  }
}

.app-main {
  flex: 1;
  padding: $spacing-lg;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;

  @media (max-width: $breakpoint-md) {
    padding: $spacing-md;
    padding-bottom: calc(#{$mobile-tab-height} + #{$spacing-md} + env(safe-area-inset-bottom, 0px));
  }
}

@keyframes float {
  0%, 100% { transform: translate(0, 0); }
  25% { transform: translate(30px, -30px); }
  50% { transform: translate(-20px, 20px); }
  75% { transform: translate(20px, 30px); }
}
@keyframes spin { to { transform: rotate(360deg); } }

// 锁屏覆盖层
.lock-overlay {
  position: fixed;
  top: 0; left: 0;
  width: 100%; height: 100%;
  z-index: 10000;
  backdrop-filter: blur(24px);
  background: rgba(255, 255, 255, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
}

.lock-card {
  @include glass-card;
  padding: 48px 40px;
  max-width: 380px;
  width: 90%;
  text-align: center;

  &__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 16px;
    color: $primary-color;
    opacity: 0.8;
  }
  &__title {
    font-size: 24px; font-weight: 700; color: $text-primary;
    margin-bottom: 4px;
  }
  &__subtitle {
    font-size: 13px; color: $text-secondary; margin-bottom: 28px;
  }
  &__form {
    display: flex; flex-direction: column; gap: 12px;
  }
}

.lock-fade-enter-active { transition: opacity 0.3s ease; }
.lock-fade-leave-active { transition: opacity 0.2s ease; }
.lock-fade-enter-from,
.lock-fade-leave-to { opacity: 0; }
</style>
