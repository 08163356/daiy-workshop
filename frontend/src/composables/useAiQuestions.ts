import { ref } from 'vue'
import { getApiBase } from '@/config'
import { emitQuestionsChanged } from '@/utils/dailyEvents'

export interface AIQuestion {
  id: number
  question: string
  context: string | null
  source_type: string
  created_at: string
}

const API = `${getApiBase()}/api/ai-questions`
export const pendingQuestions = ref<AIQuestion[]>([])

export async function refreshPendingQuestions(limit = 20) {
  try {
    const res = await fetch(`${API}?status=pending&limit=${limit}`)
    if (res.ok) pendingQuestions.value = await res.json()
  } catch { /* 静默 */ }
}

export function removePending(id: number) {
  pendingQuestions.value = pendingQuestions.value.filter(x => x.id !== id)
  emitQuestionsChanged()
}

export async function answerQuestion(id: number, answer: string) {
  const res = await fetch(`${API}/${id}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer }),
  })
  if (!res.ok) throw new Error('回答失败')
  removePending(id)
}

export async function dismissQuestion(id: number) {
  const res = await fetch(`${API}/${id}/dismiss`, { method: 'POST' })
  if (!res.ok) throw new Error('忽略失败')
  removePending(id)
}
