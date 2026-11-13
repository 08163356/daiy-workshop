// ============================================
// API 入口 — 数据库优先架构 v2
// ============================================
// 所有数据全部从后端 API 获取（数据库 + 缓存）
// 仅在后端不可用时 fallback 到本地 JSON 文件

import type { GraphData, Statistics } from '@/types/graph'
import { API_BASE, DATA_BASE } from '@/config'

/**
 * API 接口定义
 */
interface ApiInterface {
  getGraphData: () => Promise<GraphData>
  getStatistics: () => Promise<Statistics>
  getTimeline: (skip?: number, limit?: number, sourceType?: string) => Promise<{ total: number; items: any[] }>
  getModels: () => Promise<any[]>
  getKnowledge: () => Promise<any[]>
  getDailyInsight: (forceRefresh?: boolean) => Promise<any>
  deleteNote: (noteId: number) => Promise<any>
  analyzeNote: (noteId: number) => Promise<any>
}

/**
 * JSON 文件 fallback（后端不可用时使用）
 */
const jsonFallback = {
  async getGraphData(): Promise<GraphData> {
    try {
      const response = await fetch(`${DATA_BASE}data/graph.json`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      return {
        nodes: data.nodes.map((n: any) => ({
          id: String(n.id),
          name: n.label || n.name,
          type: n.category || 'concept',
          description: n.description,
          category: n.category,
          importance: n.importance,
          size: n.size,
        })),
        links: data.edges.map((e: any) => ({
          id: `${e.source}-${e.target}`,
          source: String(e.source),
          target: String(e.target),
          type: e.type || 'co_occurs',
          strength: e.strength || 1,
        })),
      }
    } catch {
      return { nodes: [], links: [] }
    }
  },

  async getStatistics(): Promise<Statistics> {
    try {
      const response = await fetch(`${DATA_BASE}data/overview.json`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      return {
        totalBooks: data.books_count || 0,
        totalNotes: data.ai_comments || 0,
        totalConcepts: data.concepts_count || 0,
        readingDays: data.reading_days || 0,
        progress: data.progress || {},
      }
    } catch {
      return { totalBooks: 0, totalNotes: 0, totalConcepts: 0, readingDays: 0, progress: {} }
    }
  },

  async getTimeline(_skip?: number, _limit?: number): Promise<{ total: number; items: any[] }> {
    try {
      const response = await fetch(`${DATA_BASE}data/timeline.json`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      const items = Array.isArray(data) ? data : (data.items || [])
      return { total: items.length, items }
    } catch {
      return { total: 0, items: [] }
    }
  },

  async deleteNote(_noteId: number): Promise<any> {
    return { message: '静态模式不支持删除' }
  },

  async analyzeNote(_noteId: number): Promise<any> {
    return { status: 'error', message: '静态模式不支持 AI 分析' }
  },

  async getModels(): Promise<any[]> {
    try {
      const response = await fetch(`${DATA_BASE}data/models.json`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch {
      return []
    }
  },

  async getKnowledge(): Promise<any[]> {
    try {
      const response = await fetch(`${DATA_BASE}data/knowledge.json`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch {
      return []
    }
  },

  async getDailyInsight(_forceRefresh?: boolean): Promise<any> {
    return { status: 'unavailable', message: '静态模式不支持知识复利播报', insight: '' }
  },
}

/**
 * 后端 API — 全部从数据库获取，失败时 fallback 到 JSON
 */
const backendApi: ApiInterface = {
  async getGraphData(): Promise<GraphData> {
    try {
      // 优先从 /api/reading/graph（新的知识图谱表）
      const response = await fetch(`${API_BASE}/api/reading/graph`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      return {
        nodes: data.nodes.map((n: any) => ({
          id: String(n.id),
          name: n.label || n.name,
          type: n.category || 'concept',
          description: n.description,
          category: n.category,
          importance: n.importance,
          size: n.size,
        })),
        links: data.edges.map((e: any) => ({
          id: `${e.source}-${e.target}`,
          source: String(e.source),
          target: String(e.target),
          type: e.type || 'co_occurs',
          strength: e.strength || 1,
        })),
      }
    } catch (error) {
      console.warn('后端图谱 API 失败，回退到 JSON:', error)
      return jsonFallback.getGraphData()
    }
  },

  async getStatistics(): Promise<Statistics> {
    try {
      const response = await fetch(`${API_BASE}/api/reading/overview`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      return {
        totalBooks: data.books_count || 0,
        totalNotes: data.notes_count ?? data.books_count ?? 0,  // 优先用 notes_count，兼容旧字段
        totalConcepts: data.concepts_count || 0,
        readingDays: data.reading_days || 0,
        progress: data.progress || {},
      }
    } catch (error) {
      console.warn('后端概览 API 失败，回退到 JSON:', error)
      return jsonFallback.getStatistics()
    }
  },

  async getTimeline(skip = 0, limit = 10, sourceType?: string): Promise<{ total: number; items: any[] }> {
    try {
      const extra = sourceType ? `&source_type=${sourceType}` : ''
      const response = await fetch(`${API_BASE}/api/reading/timeline?skip=${skip}&limit=${limit}${extra}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch (error) {
      console.warn('后端时间线 API 失败，回退到 JSON:', error)
      return jsonFallback.getTimeline()
    }
  },

  async getModels(): Promise<any[]> {
    try {
      const response = await fetch(`${API_BASE}/api/reading/models`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch (error) {
      console.warn('后端模型 API 失败，回退到 JSON:', error)
      return jsonFallback.getModels()
    }
  },

  async getKnowledge(): Promise<any[]> {
    try {
      const response = await fetch(`${API_BASE}/api/reading/knowledge`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch (error) {
      console.warn('后端知识分类 API 失败，回退到 JSON:', error)
      return jsonFallback.getKnowledge()
    }
  },

  async getDailyInsight(forceRefresh = false): Promise<any> {
    try {
      const url = `${API_BASE}/api/reading/daily-insight${forceRefresh ? '?force_refresh=true' : ''}`
      const response = await fetch(url)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch (error) {
      console.warn('每日知识复利 API 失败:', error)
      return { status: 'error', message: '网络错误', insight: '' }
    }
  },

  async deleteNote(noteId: number): Promise<any> {
    try {
      const response = await fetch(`${API_BASE}/api/reading/notes/${noteId}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch (error) {
      console.warn('删除笔记失败:', error)
      return { message: '删除失败' }
    }
  },

  async analyzeNote(noteId: number): Promise<any> {
    try {
      const response = await fetch(`${API_BASE}/api/reading/notes/${noteId}/analyze`, {
        method: 'POST',
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    } catch (error) {
      console.warn('AI 分析失败:', error)
      return { status: 'error', message: '分析失败' }
    }
  },
}

/**
 * 检测是否为 file:// 协议（纯静态模式）
 */
const isFileProtocol = (): boolean => {
  return typeof window !== 'undefined' && window.location.protocol === 'file:'
}

/**
 * 根据环境自动选择 API 实现
 * - file:// 协议 → JSON 文件
 * - 其他 → 后端 API（数据库优先，JSON 作为 fallback）
 */
export const api: ApiInterface = (() => {
  if (isFileProtocol()) {
    console.log('📦 使用静态模式（JSON 文件）')
    return jsonFallback
  }
  console.log('🌐 使用数据库 API（fallback JSON）:', API_BASE)
  return backendApi
})()

export { jsonFallback as jsonApi }
