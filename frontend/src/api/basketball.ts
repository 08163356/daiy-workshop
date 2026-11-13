/**
 * 篮球反思模块 API 客户端
 */
import { BASKETBALL_API_BASE } from '@/config'

// ==================== 类型 ====================

export interface BasketballSession {
  id: number
  date: string
  type: 'pickup' | 'match'
  duration_min?: number | null
  venue?: string | null
  partners_desc?: string | null
  intensity: number
  fatigue?: string | null
  injury_note?: string | null
  shots_made?: number | null
  shots_attempted?: number | null
  highlights?: string | null
  problems?: string | null
  key_moments?: string | null
  emotion?: string | null
  one_line_summary: string
  // match-only
  opponent?: string | null
  matchup?: string | null
  team_score?: number | null
  opp_score?: number | null
  my_play_minutes?: number | null
  decisive_moment?: string | null
  team_observation?: string | null
  // ai
  coach_review?: string | null
  blind_spots?: { title: string; evidence?: string; repeat_count: number }[] | null
  ai_summary?: string | null
  async_status?: Record<string, string> | null
  coach_model?: string | null
  created_at: string
  updated_at: string
}

export type BasketballSessionListItem = Pick<
  BasketballSession,
  'id' | 'date' | 'type' | 'duration_min' | 'intensity' | 'one_line_summary' | 'shots_made' | 'shots_attempted' | 'coach_review' | 'created_at'
>

export interface BasketballGoal {
  id: number
  title: string
  description?: string | null
  focus_area: string
  start_date: string
  end_date: string
  status: 'active' | 'done' | 'abandoned'
  ai_evaluation?: string | null
  related_todo_ids?: number[] | null
  ai_model?: string | null
  created_at: string
  updated_at: string
}

export interface DashboardOverview {
  month_session_count: number
  month_total_minutes: number
  avg_shooting_rate: number | null
  streak_days: number
  active_goal: BasketballGoal | null
  active_goal_progress: { todos_total: number; todos_done: number; days_passed: number; days_total: number } | null
  recent_sessions: BasketballSessionListItem[]
}

export interface SkillTimelineWeek {
  week_key: string
  date_start: string
  date_end: string
  points: { dim: string; problem: number; highlight: number }[]
}

export interface SkillHistoryResponse {
  dimensions: string[]
  timeline: SkillTimelineWeek[]
  top_progress: { dim: string; delta: number; before: any; after: any }[]
  top_regress: { dim: string; delta: number; before: any; after: any }[]
}

export interface StageGoalGenerateResponse {
  goal: BasketballGoal
  todos_created: number
  summary: string
}

// ==================== HTTP helper ====================

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASKETBALL_API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`)
  }
  return (await res.json()) as T
}

// ==================== Sessions ====================

export const listSessions = (params?: { type?: string; skill?: string; keyword?: string; limit?: number; offset?: number }) => {
  const qs = new URLSearchParams()
  if (params?.type) qs.set('type', params.type)
  if (params?.skill) qs.set('skill', params.skill)
  if (params?.keyword) qs.set('keyword', params.keyword)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  return api<BasketballSessionListItem[]>(`/sessions${qs.toString() ? '?' + qs.toString() : ''}`)
}

export const getSession = (id: number) => api<BasketballSession>(`/sessions/${id}`)

export const createSession = (data: Partial<BasketballSession>) =>
  api<BasketballSession>('/sessions', { method: 'POST', body: JSON.stringify(data) })

export const updateSession = (id: number, data: Partial<BasketballSession>) =>
  api<BasketballSession>(`/sessions/${id}`, { method: 'PUT', body: JSON.stringify(data) })

export const deleteSession = (id: number) =>
  api<{ ok: boolean }>(`/sessions/${id}`, { method: 'DELETE' })

export const regenerateCoach = (id: number) =>
  api<BasketballSession>(`/sessions/${id}/regenerate-coach`, { method: 'POST' })

// ==================== Dashboard / Skill ====================

export const getDashboard = () => api<DashboardOverview>('/dashboard')

export const getSkillHistory = (days = 90) =>
  api<SkillHistoryResponse>(`/skill-history?days=${days}`)

// ==================== Goals ====================

export const getActiveGoal = () => api<BasketballGoal | null>('/goals/active')

export const listGoals = (status?: string) =>
  api<BasketballGoal[]>(`/goals${status ? '?status=' + status : ''}`)

export const generateGoal = (weeks = 2, create_todos = true) =>
  api<StageGoalGenerateResponse>('/goals/generate', {
    method: 'POST',
    body: JSON.stringify({ weeks, create_todos }),
  })

export const evaluateGoal = (id: number) =>
  api<{ goal: BasketballGoal; summary: string }>(`/goals/${id}/evaluate`, { method: 'POST' })

export const deleteGoal = (id: number) =>
  api<{ ok: boolean }>(`/goals/${id}`, { method: 'DELETE' })
