<script setup lang="ts">
/**
 * 时光胶囊全局检测器
 *挂在 App.vue 中，登录后自动检测是否有待开封的信件
 */
import { ref, onMounted } from 'vue'
import { timeCapsuleApi } from '@/api/timeCapsule'
import type { PendingLetter } from '@/api/timeCapsule'
import CapsuleCeremony from './CapsuleCeremony.vue'

const showCeremony = ref(false)
const currentLetter = ref<PendingLetter | null>(null)
const pendingLetters = ref<PendingLetter[]>([])
const currentIndex = ref(0)

const checkPending = async () => {
  try {
    const data = await timeCapsuleApi.getPendingLetters()
    if (data.count > 0) {
      pendingLetters.value = data.letters
      // 检查 session storage，避免同一会话重复弹出
      const dismissedKey = `capsule_dismissed_${new Date().toDateString()}`
      const dismissed = sessionStorage.getItem(dismissedKey)
      if (!dismissed) {
        currentLetter.value = data.letters[0]
        currentIndex.value = 0
        showCeremony.value = true
      }
    }
  } catch (e) {
    // 静默失败，不影响主流程
    console.warn('时光胶囊检测失败:', e)
  }
}

const handleClose = () => {
  showCeremony.value = false
  // 标记今天已关闭
  const dismissedKey = `capsule_dismissed_${new Date().toDateString()}`
  sessionStorage.setItem(dismissedKey, '1')
  
  // 如果还有其他待开封信件，不再自动弹出（用户可在列表页查看）
}

const handleOpened = (letterId: number) => {
  // 信件已开封
  console.log('信件已开封:', letterId)
}

onMounted(() => {
  // 延迟 2 秒检测，避免干扰页面加载
  setTimeout(checkPending, 2000)
})
</script>

<template>
  <CapsuleCeremony
    v-if="showCeremony && currentLetter"
    :letter="currentLetter"
    @close="handleClose"
    @opened="handleOpened"
  />
</template>
