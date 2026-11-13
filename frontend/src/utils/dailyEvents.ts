/** 跨页面刷新用的轻量事件，避免列表/顶栏各拉各的。 */

export const DIARY_CHANGED = 'daily:diary-changed'
export const QUESTIONS_CHANGED = 'daily:questions-changed'

export function emitDiaryChanged() {
  window.dispatchEvent(new CustomEvent(DIARY_CHANGED))
}

export function emitQuestionsChanged() {
  window.dispatchEvent(new CustomEvent(QUESTIONS_CHANGED))
}
