<script setup lang="ts">
/**
 * ContentActions - 语音播报 + 转发布按钮组
 * 使用方式: <ContentActions :text="aiAnalysisText" />
 */
import { ref, onUnmounted } from 'vue'
import { CHAT_API_BASE } from '@/config'

const props = defineProps<{ text: string }>()

// 语音播报
const isSpeaking = ref(false)

function stripMd(md: string): string {
  return md.replace(/```[\s\S]*?```/g, '').replace(/`[^`]*`/g, '').replace(/!\[.*?\]\(.*?\)/g, '')
    .replace(/\[([^\]]*)\]\(.*?\)/g, '$1').replace(/#{1,6}\s*/g, '').replace(/[*_~]{1,3}/g, '')
    .replace(/>\s?/g, '').replace(/[-*+]\s/g, '').replace(/\d+\.\s/g, '').replace(/\|.*\|/g, '')
    .replace(/---+/g, '').replace(/\n{3,}/g, '\n\n').trim()
}

function toggleSpeech() {
  if (isSpeaking.value) { speechSynthesis.cancel(); isSpeaking.value = false; return }
  if (!props.text) return
  const u = new SpeechSynthesisUtterance(stripMd(props.text))
  u.lang = 'zh-CN'; u.rate = 1.0
  u.onend = () => { isSpeaking.value = false }
  u.onerror = () => { isSpeaking.value = false }
  isSpeaking.value = true
  speechSynthesis.speak(u)
}

// 转发布
const showRewrite = ref(false)
const rewritePlatform = ref('xiaohongshu')
const rewriting = ref(false)
const rewriteResult = ref('')
const rewriteCopyState = ref<'idle' | 'copied'>('idle')
const platformOptions = [
  { value: 'xiaohongshu', label: '小红书', icon: '📕' },
  { value: 'gongzhonghao', label: '公众号', icon: '💬' },
  { value: 'travel', label: '游记', icon: '✈️' },
  { value: 'thread', label: '连贴', icon: '🧵' },
]

async function startRewrite() {
  if (!props.text) return
  rewriting.value = true; rewriteResult.value = ''
  try {
    const res = await fetch(`${CHAT_API_BASE}/rewrite`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: props.text, platform: rewritePlatform.value }),
    })
    if (res.ok) { rewriteResult.value = (await res.json()).rewritten || '' }
    else { rewriteResult.value = '改写失败' }
  } catch { rewriteResult.value = '网络错误' }
  finally { rewriting.value = false }
}

async function copyRewrite() {
  if (!rewriteResult.value) return
  try { await navigator.clipboard.writeText(rewriteResult.value); rewriteCopyState.value = 'copied'; setTimeout(() => { rewriteCopyState.value = 'idle' }, 2000) } catch {}
}

onUnmounted(() => { if (isSpeaking.value) speechSynthesis.cancel() })
</script>

<template>
  <button class="ca-btn" @click="toggleSpeech" :title="isSpeaking ? '停止播报' : '语音播报'">{{ isSpeaking ? '⏹️' : '🔊' }}</button>
  <button class="ca-btn" @click="showRewrite = true" title="转发布">📤</button>

  <Teleport to="body">
    <div v-if="showRewrite" class="ca-overlay" @click.self="showRewrite = false">
      <div class="ca-modal">
        <div class="ca-modal__header">
          <h3>📤 转发布</h3>
          <button class="ca-close" @click="showRewrite = false">✕</button>
        </div>
        <div class="ca-modal__body">
          <div class="ca-platforms">
            <button v-for="p in platformOptions" :key="p.value" class="ca-plat" :class="{ 'ca-plat--active': rewritePlatform === p.value }" @click="rewritePlatform = p.value">{{ p.icon }} {{ p.label }}</button>
          </div>
          <button class="ca-primary" @click="startRewrite" :disabled="rewriting" style="margin:12px 0">{{ rewriting ? '改写中...' : '开始改写' }}</button>
          <div v-if="rewriting" style="color:#64748B;font-size:14px">AI 正在改写...</div>
          <div v-if="rewriteResult" class="ca-result">
            <button class="ca-result__copy" @click="copyRewrite">{{ rewriteCopyState === 'copied' ? '✅' : '📋' }}</button>
            <pre class="ca-result__text">{{ rewriteResult }}</pre>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ca-btn { width: 32px; height: 32px; border-radius: 6px; border: 1px solid #d0d7de; background: transparent; cursor: pointer; font-size: 14px; display: inline-flex; align-items: center; justify-content: center; transition: all 0.15s; }
.ca-btn:hover { border-color: #4080ff; background: rgba(64,128,255,0.05); }
.ca-overlay { position: fixed; inset: 0; z-index: 9999; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; padding: 20px; }
.ca-modal { background: white; border-radius: 12px; width: 100%; max-width: 600px; max-height: 80vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.2); }
.ca-modal__header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid #eee; }
.ca-modal__header h3 { margin: 0; font-size: 18px; }
.ca-modal__body { padding: 20px; }
.ca-close { background: none; border: none; font-size: 18px; cursor: pointer; color: #666; }
.ca-close:hover { color: #333; }
.ca-primary { padding: 10px 20px; border-radius: 8px; border: none; background: linear-gradient(135deg, #667eea, #764ba2); color: white; font-size: 14px; font-weight: 600; cursor: pointer; }
.ca-primary:hover { opacity: 0.9; }
.ca-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.ca-platforms { display: flex; flex-wrap: wrap; gap: 8px; }
.ca-plat { padding: 8px 16px; border-radius: 8px; border: 1px solid #d0d7de; background: white; cursor: pointer; font-size: 14px; transition: all 0.15s; }
.ca-plat:hover { border-color: #4080ff; color: #4080ff; }
.ca-plat--active { background: rgba(64,128,255,0.1); border-color: #4080ff; color: #4080ff; font-weight: 600; }
.ca-result { margin-top: 12px; position: relative; }
.ca-result__copy { position: absolute; top: 8px; right: 8px; background: rgba(255,255,255,0.9); border: 1px solid #d0d7de; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 14px; z-index: 1; }
.ca-result__copy:hover { border-color: #4080ff; }
.ca-result__text { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 16px; font-size: 14px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; max-height: 400px; overflow-y: auto; font-family: inherit; }
</style>
