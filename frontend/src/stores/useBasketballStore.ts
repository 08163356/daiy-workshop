/**
 * 篮球反思模块 Pinia store
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '@/api/basketball'

export const useBasketballStore = defineStore('basketball', () => {
  const sessions = ref<api.BasketballSessionListItem[]>([])
  const currentSession = ref<api.BasketballSession | null>(null)
  const dashboard = ref<api.DashboardOverview | null>(null)
  const skillHistory = ref<api.SkillHistoryResponse | null>(null)
  const activeGoal = ref<api.BasketballGoal | null>(null)
  const goals = ref<api.BasketballGoal[]>([])
  const loading = ref(false)

  async function fetchSessions(params?: Parameters<typeof api.listSessions>[0]) {
    loading.value = true
    sessions.value = await api.listSessions(params)
    loading.value = false
  }

  async function fetchSession(id: number) {
    currentSession.value = await api.getSession(id)
    return currentSession.value
  }

  async function saveSession(data: Partial<api.BasketballSession>) {
    const created = await api.createSession(data)
    currentSession.value = created
    return created
  }

  async function regenerateCoach(id: number) {
    currentSession.value = await api.regenerateCoach(id)
    return currentSession.value
  }

  async function fetchDashboard() {
    dashboard.value = await api.getDashboard()
  }

  async function fetchSkillHistory(days = 90) {
    skillHistory.value = await api.getSkillHistory(days)
  }

  async function fetchActiveGoal() {
    activeGoal.value = await api.getActiveGoal()
  }

  async function fetchGoals(status?: string) {
    goals.value = await api.listGoals(status)
  }

  async function generateNextGoal(weeks = 2, create_todos = true) {
    const result = await api.generateGoal(weeks, create_todos)
    activeGoal.value = result.goal
    return result
  }

  async function evaluateGoal(id: number) {
    return api.evaluateGoal(id)
  }

  return {
    sessions, currentSession, dashboard, skillHistory, activeGoal, goals, loading,
    fetchSessions, fetchSession, saveSession, regenerateCoach,
    fetchDashboard, fetchSkillHistory,
    fetchActiveGoal, fetchGoals, generateNextGoal, evaluateGoal,
  }
})
