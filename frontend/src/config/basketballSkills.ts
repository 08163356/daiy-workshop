/**
 * 篮球反思模块 — 20 个固定技术维度词表
 * 用于：前端筛选 / 进化史时间轴 / 颜色映射 / 与后端 SKILL_DIMENSIONS 严格一致
 */

export const SKILL_DIMENSIONS = [
  '投篮', '三分', '中投', '罚球', '上篮', '突破', '低位', '面框',
  '防守', '横移', '协防', '篮板', '传球', '控球', '挡拆', '无球跑动',
  '对抗', '体能', '心态', '阅读比赛',
] as const

export type SkillDimension = typeof SKILL_DIMENSIONS[number]

/** 维度大类映射（用于颜色分组） */
export const DIMENSION_GROUP: Record<SkillDimension, string> = {
  '投篮': 'shooting', '三分': 'shooting', '中投': 'shooting', '罚球': 'shooting',
  '上篮': 'finishing', '突破': 'finishing', '低位': 'finishing', '面框': 'finishing',
  '防守': 'defense', '横移': 'defense', '协防': 'defense', '篮板': 'defense',
  '传球': 'playmaking', '控球': 'playmaking', '挡拆': 'playmaking', '无球跑动': 'playmaking',
  '对抗': 'physical', '体能': 'physical', '心态': 'mind', '阅读比赛': 'mind',
}

/** 焦点领域（用于阶段目标） */
export const FOCUS_AREAS = ['投篮', '防守', '脚步', '体能', '心态', '对抗', '其他'] as const
