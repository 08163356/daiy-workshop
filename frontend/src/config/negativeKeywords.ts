/**
 * 负面情绪关键词词典
 *
 * 用于在日记编辑器中实时检测用户文本，触发「焦虑模式」安抚浮层。
 * 命中规则：检测到 high 级别关键词 1 次或 medium 级别关键词 2 次即触发。
 */

interface KeywordSet {
  high: string[]
  medium: string[]
  low: string[]
}

const KEYWORDS: KeywordSet = {
  // 高强度：单次命中即触发
  high: [
    '焦虑', '不配', '没用', '失败', '崩溃', '绝望', '完蛋', '废物',
    '活不下去', '撑不住', '撑不下去', '没希望', '一无是处',
    '配不上', '不值得', '羞耻', '自我厌恶', '想放弃',
  ],
  // 中强度：累计 2 次触发
  medium: [
    '累', '迷茫', '孤独', '难过', '无力', '空虚', '害怕',
    '比不过', '比不上', '差距', '后悔', '沮丧', '心累',
    '内耗', '压抑', '怀疑自己', '没意义', '没动力', '提不起',
    '羡慕别人', '别人都', '我怎么', '又失败', '又错了',
  ],
  // 低强度：仅作记录，不触发
  low: [
    '叹气', '一般般', '凑合', '随便',
  ],
}

export type NegativeLevel = 'none' | 'low' | 'medium' | 'high'

export interface DetectionResult {
  hit: boolean
  level: NegativeLevel
  keywords: string[]
}

export function detectNegativeEmotion(text: string): DetectionResult {
  if (!text || text.length < 5) {
    return { hit: false, level: 'none', keywords: [] }
  }

  const matched: { word: string; level: 'high' | 'medium' | 'low' }[] = []

  for (const w of KEYWORDS.high) {
    if (text.includes(w)) matched.push({ word: w, level: 'high' })
  }
  for (const w of KEYWORDS.medium) {
    if (text.includes(w)) matched.push({ word: w, level: 'medium' })
  }
  for (const w of KEYWORDS.low) {
    if (text.includes(w)) matched.push({ word: w, level: 'low' })
  }

  const highCount = matched.filter(m => m.level === 'high').length
  const mediumCount = matched.filter(m => m.level === 'medium').length

  let level: NegativeLevel = 'none'
  let hit = false

  if (highCount >= 1) {
    level = 'high'
    hit = true
  } else if (mediumCount >= 2) {
    level = 'medium'
    hit = true
  } else if (mediumCount === 1 || matched.some(m => m.level === 'low')) {
    level = 'low'
    hit = false
  }

  return {
    hit,
    level,
    keywords: matched.map(m => m.word),
  }
}

/**
 * 防抖封装：300ms 内的多次输入只检测一次
 */
export function createDebouncedDetector(
  callback: (result: DetectionResult) => void,
  wait = 300,
) {
  let timer: ReturnType<typeof setTimeout> | null = null
  return (text: string) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      callback(detectNegativeEmotion(text))
    }, wait)
  }
}
