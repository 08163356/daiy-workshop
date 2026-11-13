/**
 * 应用配置 - 自动检测环境
 */

/**
 * 获取API基础URL
 * 优先级：环境变量 > 自动检测（同域名）> 默认localhost
 */
export const getApiBase = (): string => {
  // 1. 优先使用环境变量
  if (import.meta.env.VITE_API_BASE) {
    return import.meta.env.VITE_API_BASE
  }

  // 2. 生产环境默认使用同源 API；反向代理把 /api 转到后端。
  if (typeof window !== 'undefined' && window.location.hostname !== 'localhost') {
    return window.location.origin
  }

  // 3. 本地开发默认
  return 'http://localhost:8088'
}

/**
 * API 基础 URL
 */
export const API_BASE = getApiBase()

/**
 * 投资模块 API 基础 URL
 */
export const INVESTMENT_API_BASE = `${API_BASE}/api/investment`

/**
 * 日记模块 API 基础 URL
 */
export const DIARY_API_BASE = `${API_BASE}/api/diary`

/**
 * 统一对话 API 基础 URL
 */
export const CHAT_API_BASE = `${API_BASE}/api/chat`

/**
 * 待办模块 API 基础 URL
 */
export const TODO_API_BASE = `${API_BASE}/api/todo`

/**
 * 时间记录模块 API 基础 URL
 */
export const TIME_API_BASE = `${API_BASE}/api/time`

/**
 * 知识库模块 API 基础 URL
 */
export const KB_API_BASE = `${API_BASE}/api/kb`

/**
 * 心力模块（成就 + 感恩）API 基础 URL
 */
export const WELLBEING_API_BASE = `${API_BASE}/api/wellbeing`

/**
 * 篮球反思模块 API 基础 URL
 */
export const BASKETBALL_API_BASE = `${API_BASE}/api/basketball`

/**
 * 时光胶囊模块 API 基础 URL
 */
export const TIME_CAPSULE_API_BASE = `${API_BASE}/api/time-capsule`

/**
 * 微信读书模块 API 基础 URL
 */
export const WEREAD_API_BASE = `${API_BASE}/api/weread`

/**
 * 心愿清单模块 API 基础 URL
 */
export const WISHLIST_API_BASE = `${API_BASE}/api/wishlist`

/**
 * 审批中心模块 API 基础 URL
 */
export const REVIEW_API_BASE = `${API_BASE}/api/review`

/**
 * 数据文件基础路径
 */
export const DATA_BASE = import.meta.env.BASE_URL || '/'

console.log('🔧 API配置:', { API_BASE, INVESTMENT_API_BASE, DIARY_API_BASE, CHAT_API_BASE, TODO_API_BASE, TIME_API_BASE, KB_API_BASE, WELLBEING_API_BASE, BASKETBALL_API_BASE, TIME_CAPSULE_API_BASE, WEREAD_API_BASE, WISHLIST_API_BASE })
