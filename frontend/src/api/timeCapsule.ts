/**
 * 时光胶囊信件模块 API 客户端
 */
import { TIME_CAPSULE_API_BASE } from '@/config'

// ==================== 类型定义 ====================

export interface GoalItem {
  text: string
  type: 'self' | 'ai'
  completed: boolean | null
  ai_evaluation?: string | null
  ai_score?: number | null
}

export interface LetterCreate {
  title: string
  recipient?: string
  content: string
  goals?: GoalItem[]
  images?: string[]
  open_date: string // YYYY-MM-DD
  remind_days?: number
  template_id?: string
  tags?: string[]
}

export interface LetterSummary {
  id: number
  title: string
  recipient: string
  seal_date: string
  open_date: string
  status: 'sealed' | 'pending' | 'opened'
  days_until_open: number
  template_id?: string
  tags?: string[]
  goals_count: number
  has_reflection: boolean
  has_ai_review: boolean
  created_at: string
}

export interface LetterDetail extends LetterSummary {
  content?: string
  content_preview?: string
  is_locked?: boolean
  goals?: GoalItem[]
  images?: string[]
  remind_days: number
  reflection?: string
  reflection_at?: string
  ai_review?: string
  ai_review_at?: string
  opened_at?: string
}

export interface PendingLetter {
  id: number
  title: string
  recipient: string
  seal_date: string
  open_date: string
  days_diff: number
  content: string
  goals?: GoalItem[]
  images?: string[]
  template_id?: string
}

export interface TemplateSection {
  section: string
  prompt: string
  placeholder: string
}

export interface LetterTemplate {
  id?: number
  key: string
  name: string
  description: string
  icon: string
  sections: TemplateSection[]
  suggested_goals?: string[]
  category: string
  is_system?: boolean
}

export interface DashboardData {
  total: number
  sealed_count: number
  opened_count: number
  nearest_letter: {
    id: number
    title: string
    recipient: string
    open_date: string
    days_until: number
    seal_date: string
  } | null
}

// ==================== API 调用 ====================

export const timeCapsuleApi = {
  //---- 信件 CRUD ----
  async createLetter(data: LetterCreate): Promise<{ id: number; message: string }> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/letters`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!resp.ok) throw new Error(`创建信件失败: ${resp.status}`)
    return resp.json()
  },

  async getLetters(params?: { status?: string; skip?: number; limit?: number }): Promise<{ total: number; items: LetterSummary[] }> {
    const searchParams = new URLSearchParams()
    if (params?.status) searchParams.set('status', params.status)
    if (params?.skip) searchParams.set('skip', String(params.skip))
    if (params?.limit) searchParams.set('limit', String(params.limit))
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/letters?${searchParams}`)
    if (!resp.ok) throw new Error(`获取信件列表失败: ${resp.status}`)
    return resp.json()
  },

  async getLetter(id: number): Promise<LetterDetail> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/letters/${id}`)
    if (!resp.ok) throw new Error(`获取信件详情失败: ${resp.status}`)
    return resp.json()
  },

  async getPendingLetters(): Promise<{ count: number; letters: PendingLetter[] }> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/letters/pending`)
    if (!resp.ok) throw new Error(`获取待开封信件失败: ${resp.status}`)
    return resp.json()
  },

  async openLetter(id: number): Promise<any> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/letters/${id}/open`, { method: 'POST' })
    if (!resp.ok) throw new Error(`开封信件失败: ${resp.status}`)
    return resp.json()
  },

  async addReflection(id: number, reflection: string): Promise<any> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/letters/${id}/reflection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reflection }),
    })
    if (!resp.ok) throw new Error(`保存感想失败: ${resp.status}`)
    return resp.json()
  },

  async evaluateGoal(letterId: number, goalIndex: number, completed: boolean): Promise<any> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/letters/${letterId}/evaluate-goal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal_index: goalIndex, completed }),
    })
    if (!resp.ok) throw new Error(`评估目标失败: ${resp.status}`)
    return resp.json()
  },

  async deleteLetter(id: number): Promise<any> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/letters/${id}`, { method: 'DELETE' })
    if (!resp.ok) throw new Error(`删除信件失败: ${resp.status}`)
    return resp.json()
  },

  async generateAiReview(id: number): Promise<any> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/letters/${id}/ai-review`, { method: 'POST' })
    if (!resp.ok) throw new Error(`生成 AI 点评失败: ${resp.status}`)
    return resp.json()
  },

  // ---- Dashboard----
  async getDashboard(): Promise<DashboardData> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/dashboard`)
    if (!resp.ok) throw new Error(`获取 Dashboard 数据失败: ${resp.status}`)
    return resp.json()
  },

  // ---- Timeline ----
  async getTimelineEvents(): Promise<{ events: any[] }> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/timeline`)
    if (!resp.ok) throw new Error(`获取时间线事件失败: ${resp.status}`)
    return resp.json()
  },

  // ---- 模板 ----
  async getTemplates(category?: string): Promise<{ templates: LetterTemplate[] }> {
    const params = category ? `?category=${category}` : ''
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/templates${params}`)
    if (!resp.ok) throw new Error(`获取模板失败: ${resp.status}`)
    return resp.json()
  },

  async getTemplate(key: string): Promise<LetterTemplate> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/templates/${key}`)
    if (!resp.ok) throw new Error(`获取模板详情失败: ${resp.status}`)
    return resp.json()
  },

  async initTemplates(): Promise<any> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/templates/init`, { method: 'POST' })
    if (!resp.ok) throw new Error(`初始化模板失败: ${resp.status}`)
    return resp.json()
  },

  async generatePersonalizedTemplate(): Promise<any> {
    const resp = await fetch(`${TIME_CAPSULE_API_BASE}/templates/generate`, { method: 'POST' })
    if (!resp.ok) throw new Error(`生成个性化模板失败: ${resp.status}`)
    return resp.json()
  },
}
