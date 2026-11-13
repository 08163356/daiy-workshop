/**
 * 心愿清单模块 API 客户端
 */
import { WISHLIST_API_BASE } from '@/config'

// ==================== 类型定义 ====================

export const WISH_CATEGORIES = [
  { value: 'health', label: '健康', color: '#10B981' },
  { value: 'career', label: '事业', color: '#3B82F6' },
  { value: 'wealth', label: '财富', color: '#FBBF24' },
  { value: 'relationship', label: '关系', color: '#FB7185' },
  { value: 'growth', label: '个人成长', color: '#8B5CF6' },
  { value: 'material', label: '物质', color: '#06B6D4' },
] as const

export type WishCategory = typeof WISH_CATEGORIES[number]['value'] | 'custom'

export interface Milestone {
  text: string
  type: 'self' | 'ai'
  completed: boolean | null
  ai_evaluation?: string | null
  ai_score?: number | null
}

export interface WishSummary {
  id: number
  content: string
  category: string
  status: 'active' | 'achieved' | 'archived'
  progress: number
  milestones_count: number
  completed_milestones_count: number
  linked_todo_category?: string | null
  achieved_at?: string | null
  created_at: string
}

export interface WishDetail extends WishSummary {
  milestones?: Milestone[] | null
  progress_step: number
  achieved_note?: string | null
  updated_at: string
}

export interface WishCreate {
  content: string
  category: string
  milestones?: Milestone[]
  linked_todo_category?: string | null
  progress_step?: number
}

export interface WishUpdate {
  content?: string
  category?: string
  linked_todo_category?: string | null
  progress_step?: number
  progress?: number
}

export interface WishLogEntry {
  id: number
  wish_id: number
  content: string
  ai_processed: boolean
  created_at: string
  pending_candidate?: ProgressCandidatePreview | null
}

export interface ProgressCandidatePreview {
  id: number
  suggested_progress: number | null
  suggested_milestone_index: number | null
  ai_confidence: number
  ai_reason: string | null
}

export interface ProgressCandidate extends ProgressCandidatePreview {
  wish_id: number
  source_id: number
  status: string
  extract_status: string
  created_at: string
}

export interface WishDashboard {
  total: number
  active_count: number
  achieved_count: number
  pending_candidates: number
  by_category: Record<string, number>
}

// ==================== API 调用 ====================

async function handle<T>(resp: Response, errMsg: string): Promise<T> {
  if (!resp.ok) {
    let detail = ''
    try {
      const data = await resp.json()
      detail = data?.detail || ''
    } catch { /* ignore */ }
    throw new Error(`${errMsg}: ${resp.status} ${detail}`)
  }
  return resp.json()
}

export const wishlistApi = {
  // ---- 心愿 CRUD ----
  async list(params?: { category?: string; status?: string; skip?: number; limit?: number }): Promise<{ total: number; items: WishSummary[] }> {
    const sp = new URLSearchParams()
    if (params?.category) sp.set('category', params.category)
    if (params?.status) sp.set('status', params.status)
    if (params?.skip) sp.set('skip', String(params.skip))
    if (params?.limit) sp.set('limit', String(params.limit))
    const resp = await fetch(`${WISHLIST_API_BASE}?${sp}`)
    return handle(resp, '获取心愿列表失败')
  },

  async create(data: WishCreate): Promise<WishDetail> {
    const resp = await fetch(WISHLIST_API_BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    return handle(resp, '创建心愿失败')
  },

  async get(id: number): Promise<WishDetail> {
    const resp = await fetch(`${WISHLIST_API_BASE}/${id}`)
    return handle(resp, '获取心愿详情失败')
  },

  async update(id: number, data: WishUpdate): Promise<WishDetail> {
    const resp = await fetch(`${WISHLIST_API_BASE}/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    return handle(resp, '更新心愿失败')
  },

  async remove(id: number): Promise<{ message: string }> {
    const resp = await fetch(`${WISHLIST_API_BASE}/${id}`, { method: 'DELETE' })
    return handle(resp, '删除心愿失败')
  },

  // ---- 里程碑 ----
  async addMilestone(wishId: number, text: string, type: 'self' | 'ai' = 'self'): Promise<WishDetail> {
    const resp = await fetch(`${WISHLIST_API_BASE}/${wishId}/milestones`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, type }),
    })
    return handle(resp, '新增里程碑失败')
  },

  async toggleMilestone(wishId: number, index: number): Promise<WishDetail> {
    const resp = await fetch(`${WISHLIST_API_BASE}/${wishId}/milestones/${index}/toggle`, { method: 'PATCH' })
    return handle(resp, '切换里程碑状态失败')
  },

  async deleteMilestone(wishId: number, index: number): Promise<WishDetail> {
    const resp = await fetch(`${WISHLIST_API_BASE}/${wishId}/milestones/${index}`, { method: 'DELETE' })
    return handle(resp, '删除里程碑失败')
  },

  // ---- 进展日志 ----
  async createLog(wishId: number, content: string): Promise<WishLogEntry> {
    const resp = await fetch(`${WISHLIST_API_BASE}/${wishId}/logs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    })
    return handle(resp, '写进展日志失败')
  },

  async listLogs(wishId: number): Promise<{ items: WishLogEntry[] }> {
    const resp = await fetch(`${WISHLIST_API_BASE}/${wishId}/logs`)
    return handle(resp, '获取进展日志失败')
  },

  // ---- 候选审核 ----
  async listCandidates(params?: { status?: string; wish_id?: number }): Promise<{ items: ProgressCandidate[] }> {
    const sp = new URLSearchParams()
    if (params?.status) sp.set('status', params.status)
    if (params?.wish_id) sp.set('wish_id', String(params.wish_id))
    const resp = await fetch(`${WISHLIST_API_BASE}/candidates?${sp}`)
    return handle(resp, '获取候选列表失败')
  },

  async reviewCandidate(candidateId: number, action: 'accept' | 'reject'): Promise<{ message: string; wish?: WishDetail }> {
    const resp = await fetch(`${WISHLIST_API_BASE}/candidates/${candidateId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    })
    return handle(resp, '审核候选失败')
  },

  // ---- 实现仪式 ----
  async achieve(wishId: number, note?: string): Promise<{ message: string; wish: WishDetail }> {
    const resp = await fetch(`${WISHLIST_API_BASE}/${wishId}/achieve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    })
    return handle(resp, '实现心愿失败')
  },

  // ---- Dashboard ----
  async getDashboard(): Promise<WishDashboard> {
    const resp = await fetch(`${WISHLIST_API_BASE}/dashboard`)
    return handle(resp, '获取心愿墙统计失败')
  },
}

export function categoryMeta(category: string) {
  return WISH_CATEGORIES.find(c => c.value === category) || { value: category, label: category, color: '#94A3B8' }
}
