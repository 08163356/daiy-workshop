/**
 * 微信读书模块 API 客户端
 */
import { WEREAD_API_BASE } from '@/config'

//==================== 类型定义 ====================

export interface WeReadStatus {
  configured: boolean
  last_sync_at: string | null
  total_books: number
  total_notes_synced: number
  shelf_synced: boolean
}

export interface WeReadBook {
  id: number
  book_id: string
  title: string
  author: string | null
  cover: string | null
  category: string | null
  reading_progress: number | null
  is_finished: boolean
  note_count: number
  last_synced_at: string | null
}

export interface WeReadShelfResponse {
  books: WeReadBook[]
  total: number
}

export interface WeReadStats {
  today_minutes: number | null
  week_minutes: number | null
  month_minutes: number | null
  total_minutes: number | null
  total_days: number | null
}

export interface SyncBookResult {
  book_id: string
  title: string
  note_id?: number
  highlights_count: number
  reviews_count: number
  message: string
}

export interface SyncAllResult {
  message: string
  results: Omit<SyncBookResult, 'note_id' | 'message'>[]
  total_synced: number
}

// ==================== API 调用 ====================

export const wereadApi = {
  async getStatus(): Promise<WeReadStatus> {
    const resp = await fetch(`${WEREAD_API_BASE}/status`)
    if (!resp.ok) throw new Error(`获取状态失败: ${resp.status}`)
    return resp.json()
  },

  async saveConfig(apiKey: string): Promise<{ message: string }> {
    const resp = await fetch(`${WEREAD_API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      throw new Error(data.detail || `保存失败: ${resp.status}`)
    }
    return resp.json()
  },

  async deleteConfig(): Promise<{ message: string }> {
    const resp = await fetch(`${WEREAD_API_BASE}/config`, { method: 'DELETE' })
    if (!resp.ok) throw new Error(`删除失败: ${resp.status}`)
    return resp.json()
  },

  async getShelf(params?: { skip?: number; limit?: number }): Promise<WeReadShelfResponse> {
    const q = new URLSearchParams()
    if (params?.skip) q.set('skip', String(params.skip))
    if (params?.limit) q.set('limit', String(params.limit))
    const resp = await fetch(`${WEREAD_API_BASE}/shelf?${q}`)
    if (!resp.ok) throw new Error(`获取书架失败: ${resp.status}`)
    return resp.json()
  },

  async getStats(): Promise<WeReadStats> {
    const resp = await fetch(`${WEREAD_API_BASE}/stats`)
    if (!resp.ok) throw new Error(`获取统计失败: ${resp.status}`)
    return resp.json()
  },

  async syncShelf(): Promise<{ message: string; synced_count: number; sync_key: string }> {
    const resp = await fetch(`${WEREAD_API_BASE}/sync/shelf`, { method: 'POST' })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      throw new Error(data.detail || `同步失败: ${resp.status}`)
    }
    return resp.json()
  },

  async syncBook(bookId: string): Promise<SyncBookResult> {
    const resp = await fetch(`${WEREAD_API_BASE}/sync/book/${bookId}`, { method: 'POST' })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      throw new Error(data.detail || `同步失败: ${resp.status}`)
    }
    return resp.json()
  },

  async syncAll(): Promise<SyncAllResult> {
    const resp = await fetch(`${WEREAD_API_BASE}/sync/all`, { method: 'POST' })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      throw new Error(data.detail || `全量同步失败: ${resp.status}`)
    }
    return resp.json()
  },
}
