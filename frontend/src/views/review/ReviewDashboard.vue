<template>
  <div class="review-page">
    <header class="review-header">
      <h1>📋 审批中心</h1>
      <p class="subtitle">AI 自动化产出审核 — 简历 / 博客 / GBrain / 部署</p>
      <div class="header-actions">
        <button class="btn btn-sm" :class="{ active: statusFilter === '' }" @click="statusFilter = ''">
          全部 ({{ stats.total }})
        </button>
        <button class="btn btn-sm btn-warning" :class="{ active: statusFilter === 'pending' }" @click="statusFilter = 'pending'">
          ⏳ 待审批 ({{ stats.pending }})
        </button>
        <button class="btn btn-sm btn-success" :class="{ active: statusFilter === 'approved' }" @click="statusFilter = 'approved'">
          ✅ 已通过 ({{ stats.approved }})
        </button>
        <button class="btn btn-sm btn-danger" :class="{ active: statusFilter === 'rejected' }" @click="statusFilter = 'rejected'">
          ❌ 已拒绝 ({{ stats.rejected }})
        </button>
        <button class="btn btn-sm btn-outline" @click="exportAll" title="导出 JSON（迁移用）">
          📦 导出
        </button>
      </div>
    </header>

    <!-- 空状态 -->
    <div v-if="!loading && items.length === 0" class="empty-state">
      <div class="empty-icon">📭</div>
      <p>暂无{{ statusFilter === 'pending' ? '待审批' : '' }}条目</p>
      <p class="empty-hint">AI 自动化脚本完成任务后，会在这里生成待审批内容</p>
    </div>

    <!-- 列表 -->
    <div v-else class="review-list">
      <div
        v-for="item in items"
        :key="item.id"
        class="review-card"
        :class="[`status-${item.status}`, { expanded: expandedId === item.id }]"
        @click="toggleExpand(item.id)"
      >
        <div class="card-header">
          <span class="type-badge" :class="`type-${item.type}`">{{ typeLabel(item.type) }}</span>
          <span class="card-title">{{ item.title }}</span>
          <span class="card-source">{{ item.source }}</span>
          <span class="card-time">{{ formatTime(item.createdAt) }}</span>
          <span class="status-badge" :class="`status-${item.status}`">{{ statusLabel(item.status) }}</span>
        </div>

        <div class="card-summary" v-if="item.summary">{{ item.summary }}</div>

        <!-- 展开详情 -->
        <div v-if="expandedId === item.id" class="card-detail" @click.stop>
          <div class="detail-content">
            <h4>📄 内容预览</h4>
            <pre class="content-preview">{{ item.content || '（无内容）' }}</pre>
          </div>

          <div v-if="item.metadata && Object.keys(item.metadata).length" class="detail-meta">
            <h4>📎 附加信息</h4>
            <pre class="meta-preview">{{ JSON.stringify(item.metadata, null, 2) }}</pre>
          </div>

          <div v-if="item.syncCommand" class="detail-sync">
            <h4>🔧 同步命令</h4>
            <code class="sync-cmd">{{ item.syncCommand }}</code>
          </div>

          <div v-if="item.reviewerNote" class="detail-note">
            <h4>💬 审批备注</h4>
            <p>{{ item.reviewerNote }}</p>
          </div>

          <!-- 操作按钮（仅 pending） -->
          <div v-if="item.status === 'pending'" class="action-bar">
            <input
              v-model="reviewNote"
              class="note-input"
              placeholder="批注（可选）"
              @click.stop
            />
            <button class="btn btn-success" @click.stop="approve(item.id)">✅ 通过</button>
            <button class="btn btn-danger" @click.stop="reject(item.id)">❌ 拒绝</button>
            <button class="btn btn-outline btn-sm" @click.stop="deleteItem(item.id)">🗑️ 删除</button>
          </div>

          <!-- 已审批显示结果 -->
          <div v-if="item.status === 'approved' && item.syncCommand" class="action-bar">
            <span class="sync-hint">✅ 已通过，同步命令如上。可复制手动执行或由自动化脚本处理。</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { API_BASE } from '../../config'

const REVIEW_API = `${API_BASE}/api/review`

interface ReviewItemData {
  id: number
  type: string
  title: string
  summary: string
  content: string
  status: string
  source: string
  metadata: Record<string, any>
  syncCommand: string
  createdAt: string
  updatedAt: string
  reviewedAt: string | null
  reviewerNote: string
}

interface Stats {
  pending: number
  approved: number
  rejected: number
  expired: number
  total: number
}

const items = ref<ReviewItemData[]>([])
const stats = ref<Stats>({ pending: 0, approved: 0, rejected: 0, expired: 0, total: 0 })
const loading = ref(false)
const statusFilter = ref('pending')
const expandedId = ref<number | null>(null)
const reviewNote = ref('')

const typeLabels: Record<string, string> = {
  resume: '📝 简历',
  blog: '✍️ 博客',
  gbrain: '🧠 GBrain',
  deploy: '🚀 部署',
  general: '📌 通用',
}

const statusLabels: Record<string, string> = {
  pending: '⏳ 待审批',
  approved: '✅ 已通过',
  rejected: '❌ 已拒绝',
  expired: '⌛ 已过期',
}

const typeLabel = (t: string) => typeLabels[t] || t
const statusLabel = (s: string) => statusLabels[s] || s

function formatTime(iso: string) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function fetchStats() {
  try {
    const res = await fetch(`${REVIEW_API}/stats`)
    if (res.ok) stats.value = await res.json()
  } catch (e) { console.error('stats error', e) }
}

async function fetchItems() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (statusFilter.value) params.set('status', statusFilter.value)
    const res = await fetch(`${REVIEW_API}/items?${params}`)
    if (res.ok) {
      const data = await res.json()
      items.value = data.items
    }
  } catch (e) {
    console.error('fetch error', e)
  } finally {
    loading.value = false
  }
}

function toggleExpand(id: number) {
  expandedId.value = expandedId.value === id ? null : id
  reviewNote.value = ''
}

async function approve(id: number) {
  try {
    const res = await fetch(`${REVIEW_API}/items/${id}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: reviewNote.value }),
    })
    if (res.ok) {
      await fetchItems()
      await fetchStats()
      expandedId.value = null
    }
  } catch (e) { console.error('approve error', e) }
}

async function reject(id: number) {
  try {
    const res = await fetch(`${REVIEW_API}/items/${id}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: reviewNote.value }),
    })
    if (res.ok) {
      await fetchItems()
      await fetchStats()
      expandedId.value = null
    }
  } catch (e) { console.error('reject error', e) }
}

async function deleteItem(id: number) {
  if (!confirm('确定删除？')) return
  try {
    await fetch(`${REVIEW_API}/items/${id}`, { method: 'DELETE' })
    await fetchItems()
    await fetchStats()
    expandedId.value = null
  } catch (e) { console.error('delete error', e) }
}

async function exportAll() {
  try {
    const res = await fetch(`${REVIEW_API}/export`)
    if (res.ok) {
      const data = await res.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `review-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    }
  } catch (e) { console.error('export error', e) }
}

watch(statusFilter, () => fetchItems())

onMounted(() => {
  fetchStats()
  fetchItems()
})
</script>

<style scoped>
.review-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.review-header { margin-bottom: 24px; }
.review-header h1 { margin: 0 0 4px; font-size: 1.5rem; }
.subtitle { color: #888; font-size: 0.85rem; margin: 0 0 12px; }
.header-actions { display: flex; gap: 8px; flex-wrap: wrap; }

.btn {
  padding: 6px 14px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 0.82rem;
  transition: all 0.2s;
}
.btn:hover { background: #f5f5f5; }
.btn.active { background: #e8f0fe; border-color: #4285f4; color: #1967d2; font-weight: 600; }
.btn-sm { padding: 4px 10px; font-size: 0.78rem; }
.btn-success { border-color: #34a853; color: #137333; }
.btn-success:hover { background: #e6f4ea; }
.btn-danger { border-color: #ea4335; color: #c5221f; }
.btn-danger:hover { background: #fce8e6; }
.btn-warning { border-color: #fbbc04; color: #b06000; }
.btn-outline { border-color: #ccc; color: #666; }

.empty-state { text-align: center; padding: 60px 0; color: #999; }
.empty-icon { font-size: 3rem; margin-bottom: 12px; }
.empty-hint { font-size: 0.8rem; color: #bbb; }

.review-list { display: flex; flex-direction: column; gap: 10px; }

.review-card {
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: all 0.2s;
  background: #fff;
}
.review-card:hover { border-color: #c0c0c0; box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
.review-card.expanded { border-color: #4285f4; box-shadow: 0 2px 12px rgba(66,133,244,0.12); }
.review-card.status-approved { border-left: 3px solid #34a853; }
.review-card.status-rejected { border-left: 3px solid #ea4335; }
.review-card.status-pending { border-left: 3px solid #fbbc04; }

.card-header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.type-badge {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f0f0f0;
  white-space: nowrap;
}
.type-resume { background: #e8f0fe; }
.type-blog { background: #fef7e0; }
.type-gbrain { background: #e6f4ea; }
.type-deploy { background: #fce8e6; }

.card-title { font-weight: 600; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-source { font-size: 0.75rem; color: #999; }
.card-time { font-size: 0.75rem; color: #999; }
.status-badge { font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; }
.status-badge.status-pending { background: #fff3cd; color: #856404; }
.status-badge.status-approved { background: #d4edda; color: #155724; }
.status-badge.status-rejected { background: #f8d7da; color: #721c24; }

.card-summary { font-size: 0.85rem; color: #666; margin-top: 6px; line-height: 1.4; }

.card-detail { margin-top: 14px; border-top: 1px solid #eee; padding-top: 14px; }
.card-detail h4 { font-size: 0.85rem; margin: 12px 0 6px; color: #555; }
.card-detail h4:first-child { margin-top: 0; }

.content-preview, .meta-preview {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  padding: 12px;
  font-size: 0.8rem;
  line-height: 1.5;
  max-height: 400px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.sync-cmd {
  display: block;
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 0.8rem;
  word-break: break-all;
}
.detail-note p { font-size: 0.85rem; color: #555; font-style: italic; }

.action-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px dashed #ddd;
}
.note-input {
  flex: 1;
  padding: 6px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 0.85rem;
}
.sync-hint { font-size: 0.82rem; color: #34a853; }

.loading { text-align: center; padding: 40px; color: #999; }
</style>
