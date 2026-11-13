/**
 * 心力模块状态管理
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import wellbeingApi, {
  type WellbeingEntry,
  type WellbeingEntryCreate,
  type WellbeingEntryUpdate,
  type WellbeingCandidate,
  type CandidateReviewAction,
  type WellbeingReport,
  type WellbeingOverview,
  type WellbeingInsights,
  type ComfortCardResponse,
} from '@/api/wellbeing'

export const useWellbeingStore = defineStore('wellbeing', () => {
  // 状态
  const overview = ref<WellbeingOverview | null>(null)
  const entries = ref<WellbeingEntry[]>([])
  const entriesTotal = ref(0)
  const candidates = ref<WellbeingCandidate[]>([])
  const currentReport = ref<WellbeingReport | null>(null)
  const reportHistory = ref<WellbeingReport[]>([])
  const comfortCard = ref<ComfortCardResponse | null>(null)
  const insights = ref<WellbeingInsights | null>(null)

  const loading = ref(false)
  const error = ref<string>('')

  // 计算属性
  const pendingCandidatesCount = computed(() =>
    candidates.value.filter(c => c.status === 'pending').length,
  )

  const overviewBadgeCount = computed(() => overview.value?.pending_candidates ?? 0)

  // ==================== Actions ====================

  async function fetchOverview() {
    loading.value = true
    error.value = ''
    try {
      overview.value = await wellbeingApi.getOverview()
    } catch (e: any) {
      error.value = e.message || '加载总览失败'
    } finally {
      loading.value = false
    }
  }

  async function fetchEntries(params: Parameters<typeof wellbeingApi.listEntries>[0] = {}) {
    loading.value = true
    error.value = ''
    try {
      const res = await wellbeingApi.listEntries(params)
      entries.value = res.items
      entriesTotal.value = res.total
    } catch (e: any) {
      error.value = e.message || '加载列表失败'
    } finally {
      loading.value = false
    }
  }

  async function createEntry(data: WellbeingEntryCreate) {
    const e = await wellbeingApi.createEntry(data)
    entries.value.unshift(e)
    return e
  }

  async function updateEntry(id: number, data: WellbeingEntryUpdate) {
    const e = await wellbeingApi.updateEntry(id, data)
    const idx = entries.value.findIndex(x => x.id === id)
    if (idx >= 0) entries.value[idx] = e
    return e
  }

  async function deleteEntry(id: number) {
    await wellbeingApi.deleteEntry(id)
    entries.value = entries.value.filter(x => x.id !== id)
  }

  async function fetchCandidates(status: Parameters<typeof wellbeingApi.listCandidates>[0] = 'pending') {
    candidates.value = await wellbeingApi.listCandidates(status)
  }

  async function reviewCandidate(id: number, action: CandidateReviewAction) {
    const res = await wellbeingApi.reviewCandidate(id, action)
    const idx = candidates.value.findIndex(c => c.id === id)
    if (idx >= 0) {
      candidates.value[idx].status = action.action === 'accept' ? 'accepted' : 'rejected'
    }
    return res
  }

  async function fetchReport(period_type: 'week' | 'month' = 'week', period_key?: string, force = false) {
    loading.value = true
    error.value = ''
    try {
      currentReport.value = await wellbeingApi.getReport(period_type, period_key, force)
    } catch (e: any) {
      error.value = e.message || '加载报告失败'
    } finally {
      loading.value = false
    }
    return currentReport.value
  }

  async function fetchReportHistory(period_type?: 'week' | 'month') {
    reportHistory.value = await wellbeingApi.listReports(period_type)
  }

  async function fetchComfortCard(achievements_n = 3, gratitudes_n = 2) {
    comfortCard.value = await wellbeingApi.getComfortCard(achievements_n, gratitudes_n)
    return comfortCard.value
  }

  async function fetchInsights(days = 90) {
    insights.value = await wellbeingApi.getInsights(days)
    return insights.value
  }

  return {
    // state
    overview,
    entries,
    entriesTotal,
    candidates,
    currentReport,
    reportHistory,
    comfortCard,
    insights,
    loading,
    error,
    // getters
    pendingCandidatesCount,
    overviewBadgeCount,
    // actions
    fetchOverview,
    fetchEntries,
    createEntry,
    updateEntry,
    deleteEntry,
    fetchCandidates,
    reviewCandidate,
    fetchReport,
    fetchReportHistory,
    fetchComfortCard,
    fetchInsights,
  }
})
