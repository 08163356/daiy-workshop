/**
 * SSE POST 公共 composable —— 合并 ChatView / TodoInbox 两套手写解析的重复实现
 * 服务端协议：data: {json}\n\n 行块，data: [DONE] 结束
 */
export async function* ssePost<T = any>(
  url: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<T, void> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}))
    throw new Error(errData.detail || `请求失败 (${res.status})`)
  }
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data:')) continue
          const data = line.slice(5).trim()
          if (!data) continue
          if (data === '[DONE]') return
          try {
            yield JSON.parse(data) as T
          } catch { /* 忽略坏行 */ }
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}
