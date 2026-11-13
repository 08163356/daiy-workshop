/**
 * 核心任务周期工具
 * 后端按当前周期 key 过滤实现过期自动失效，前端展示核心标识时用同样的 key 判断
 */

/** 当前 ISO 周 key，如 2026-W43（与 Python isocalendar 对齐：周一为一周开始） */
export function currentWeekKey(d: Date = new Date()): string {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNum = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  const weekNo = Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${date.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`
}

/** 当前月 key，如 2026-10 */
export function currentMonthKey(d: Date = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

/** 当前年 key，如 2026 */
export function currentYearKey(d: Date = new Date()): string {
  return String(d.getFullYear())
}

interface CoreLike {
  core_scope?: string | null
  core_period_key?: string | null
}

/** 任务是否是当前周期生效中的核心任务 */
export function isCoreActive(item: CoreLike): boolean {
  if (!item.core_scope || !item.core_period_key) return false
  if (item.core_scope === 'week') return item.core_period_key === currentWeekKey()
  if (item.core_scope === 'month') return item.core_period_key === currentMonthKey()
  if (item.core_scope === 'year') return item.core_period_key === currentYearKey()
  return false
}
