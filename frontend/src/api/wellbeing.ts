/**
 * 心力模块（成就 + 感恩）API 客户端
 */
import { WELLBEING_API_BASE } from '@/config'

// ==================== 类型定义 ====================

export type WellbeingType = 'achievement' | 'gratitude'

export interface WellbeingEntry {
  id: number
  type: WellbeingType
  content: string
  category?: string | null
  intensity: number
  occurred_at: string
  source_type: string
  source_id?: number | null
  source_excerpt?: string | null
  mood_tag?: string | null
  image_url?: string | null
  ai_tags?: string[] | null
  ai_reason?: string | null   // AI 识别理由（候选采纳时保留）
  created_at: string
  updated_at: string
}

export interface WellbeingEntryCreate {
  type: WellbeingType
  content: string
  category?: string | null
  intensity?: number
  occurred_at: string
  source_type?: string
  source_id?: number | null
  mood_tag?: string | null
  image_url?: string | null
  ai_tags?: string[] | null
}

export interface WellbeingEntryUpdate {
  content?: string
  category?: string | null
  intensity?: number
  occurred_at?: string
  mood_tag?: string | null
  image_url?: string | null
  ai_tags?: string[] | null
}

export interface WellbeingCandidate {
  id: number
  source_type: string
  source_id: number
  source_excerpt?: string | null
  suggested_type: WellbeingType
  suggested_content: string
  suggested_category?: string | null
  suggested_intensity: number
  suggested_tags?: string[] | null
  ai_confidence: number
  ai_reason?: string | null
  status: 'pending' | 'accepted' | 'rejected'
  reviewed_at?: string | null
  accepted_entry_id?: number | null
  created_at: string
}

export interface CandidateReviewAction {
  action: 'accept' | 'reject'
  content?: string
  category?: string
  intensity?: number
  occurred_at?: string
}

export interface WellbeingReport {
  id: number
  period_type: 'week' | 'month'
  period_key: string
  period_start: string
  period_end: string
  content: string
  structured_data?: Record<string, any> | null
  achievement_count: number
  gratitude_count: number
  model_used?: string | null
  tokens_used: number
  generated_at: string
}

export interface ComfortCardEntry {
  id: number
  type: WellbeingType
  content: string
  category?: string | null
  intensity: number
  occurred_at: string
}

export interface ComfortCardResponse {
  soothing_message: string
  achievements: ComfortCardEntry[]
  gratitudes: ComfortCardEntry[]
  fallback: boolean
}

export interface TrendPoint {
  date: string
  achievement: number
  gratitude: number
}

export interface CategoryStat {
  category: string
  count: number
  avg_intensity: number
}

export interface WellbeingOverview {
  total_achievement: number
  total_gratitude: number
  week_new: number
  streak_days: number
  trend_90d: TrendPoint[]
  category_distribution: CategoryStat[]
  intensity_radar: Record<string, number>
  pending_candidates: number
  insight?: string | null
}

export interface CorrelationItem {
  label: string
  score: number
  note?: string | null
}

export interface WellbeingInsights {
  summary: string
  correlations: CorrelationItem[]
  suggestions: string[]
}

// ==================== 通用 fetch ====================

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${WELLBEING_API_BASE}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = ''
    try {
      const data = await res.json()
      detail = data.detail || data.message || ''
    } catch {
      detail = await res.text()
    }
    throw new Error(`${res.status} ${detail || res.statusText}`)
  }
  return res.json()
}

// ==================== 总览 ====================

export const wellbeingApi = {
  getOverview: () => request<WellbeingOverview>('/overview'),

  // ---- 条目 ----
  listEntries: (params: {
    type?: WellbeingType
    category?: string
    min_intensity?: number
    keyword?: string
    start_date?: string
    end_date?: string
    skip?: number
    limit?: number
  } = {}) => {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.append(k, String(v))
    })
    return request<{ total: number; items: WellbeingEntry[] }>(
      `/entries${qs.toString() ? `?${qs}` : ''}`,
    )
  },
  getEntry: (id: number) => request<WellbeingEntry>(`/entries/${id}`),
  createEntry: (data: WellbeingEntryCreate) =>
    request<WellbeingEntry>('/entries', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateEntry: (id: number, data: WellbeingEntryUpdate) =>
    request<WellbeingEntry>(`/entries/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteEntry: (id: number) =>
    request<{ message: string }>(`/entries/${id}`, { method: 'DELETE' }),

  // ---- 候选 ----
  listCandidates: (status: 'pending' | 'accepted' | 'rejected' | 'all' = 'pending', limit = 50) =>
    request<WellbeingCandidate[]>(`/candidates?status=${status}&limit=${limit}`),
  reviewCandidate: (id: number, action: CandidateReviewAction) =>
    request<{ message: string; entry?: WellbeingEntry }>(
      `/candidates/${id}/review`,
      { method: 'POST', body: JSON.stringify(action) },
    ),

  // ---- 报告 ----
  getReport: (
    period_type: 'week' | 'month' = 'week',
    period_key?: string,
    force_refresh = false,
  ) => {
    const qs = new URLSearchParams({ period_type })
    if (period_key) qs.append('period_key', period_key)
    if (force_refresh) qs.append('force_refresh', 'true')
    return request<WellbeingReport>(`/reports?${qs}`)
  },
  listReports: (period_type?: 'week' | 'month', limit = 20) => {
    const qs = new URLSearchParams({ limit: String(limit) })
    if (period_type) qs.append('period_type', period_type)
    return request<WellbeingReport[]>(`/reports/history?${qs}`)
  },

  // ---- 安抚卡 ----
  getComfortCard: (achievements_n = 3, gratitudes_n = 2) =>
    request<ComfortCardResponse>(
      `/comfort?achievements_n=${achievements_n}&gratitudes_n=${gratitudes_n}`,
    ),

  // ---- 关联洞察 ----
  getInsights: (days = 90) => request<WellbeingInsights>(`/insights?days=${days}`),
}

export default wellbeingApi
