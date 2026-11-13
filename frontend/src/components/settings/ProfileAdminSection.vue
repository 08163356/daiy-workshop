<script setup lang="ts">
/**
 * 用户画像管理（分层架构的画像层操作台）
 * - 画像层：查看/编辑/删除条目（蒸馏后的当前理解）
 * - 快照层：手动快照、整理前自动快照、一键回滚
 * - 整理提案：AI 出方案 → 用户审阅 → 确认才执行（consent-first）
 */
import { ref, onMounted } from 'vue'
import { API_BASE } from '@/config'

const API = `${API_BASE}/api/profile-admin`

interface Entry { id: number; key: string; value: string; confidence: number; source_count: number; last_evidence: string | null; updated_at: string | null }
interface Group { category: string; items: Entry[] }
interface Snapshot { id: number; reason: string; entry_count: number; created_at: string }
interface Proposal {
  id: number; status: string; summary: string; stats: any; created_at: string
  plan: { dedup_delete_ids: number[]; category_changes: { id: number; from: string; to: string }[]; merges: { keep_key: string; merge_keys: string[]; merged_value: string }[] } | null
}

const loading = ref(true)
const total = ref(0)
const totalChars = ref(0)
const groups = ref<Group[]>([])
const snapshots = ref<Snapshot[]>([])
const proposals = ref<Proposal[]>([])
const collapsedCats = ref<Set<string>>(new Set())
const editingId = ref<number | null>(null)
const editKey = ref('')
const editValue = ref('')
const editCategory = ref('')
const proposing = ref(false)
const applying = ref(false)
const error = ref('')
const notice = ref('')

const flash = (msg: string) => { notice.value = msg; setTimeout(() => { notice.value = '' }, 3000) }

const loadAll = async () => {
  loading.value = true
  error.value = ''
  try {
    const [p, s, pr] = await Promise.all([
      fetch(`${API}`).then(r => r.json()),
      fetch(`${API}/snapshots`).then(r => r.json()),
      fetch(`${API}/proposals`).then(r => r.json()),
    ])
    total.value = p.total
    totalChars.value = p.total_chars
    groups.value = p.groups
    snapshots.value = s
    proposals.value = pr
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

const toggleCat = (c: string) => {
  collapsedCats.value.has(c) ? collapsedCats.value.delete(c) : collapsedCats.value.add(c)
  collapsedCats.value = new Set(collapsedCats.value)
}

const startEdit = (e: Entry) => {
  editingId.value = e.id
  editKey.value = e.key
  editValue.value = e.value
  editCategory.value = groups.value.find(g => g.items.includes(e))?.category || ''
}

const saveEdit = async (id: number) => {
  try {
    const res = await fetch(`${API}/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: editKey.value, value: editValue.value, category: editCategory.value }),
    })
    if (!res.ok) throw new Error((await res.json()).detail || '保存失败')
    editingId.value = null
    flash('已保存')
    loadAll()
  } catch (e: any) { error.value = e.message }
}

const removeEntry = async (e: Entry) => {
  if (!confirm(`确定删除「${e.key}」这条画像吗？`)) return
  try {
    const res = await fetch(`${API}/${e.id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error('删除失败')
    flash('已删除')
    loadAll()
  } catch (e: any) { error.value = e.message }
}

const takeSnapshot = async () => {
  try {
    const res = await fetch(`${API}/snapshots?reason=${encodeURIComponent('手动快照')}`, { method: 'POST' })
    if (!res.ok) throw new Error('快照失败')
    flash('快照已保存')
    loadAll()
  } catch (e: any) { error.value = e.message }
}

const rollback = async (s: Snapshot) => {
  if (!confirm(`回滚到 ${s.created_at.slice(0, 16).replace('T', ' ')} 的快照（${s.entry_count} 条）？\n当前状态会先自动备份。`)) return
  try {
    const res = await fetch(`${API}/snapshots/${s.id}/rollback`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '回滚失败')
    flash(data.message)
    loadAll()
  } catch (e: any) { error.value = e.message }
}

const propose = async () => {
  proposing.value = true
  error.value = ''
  try {
    const res = await fetch(`${API}/proposals`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '生成提案失败')
    flash('提案已生成，请审阅后确认')
    loadAll()
  } catch (e: any) { error.value = e.message } finally { proposing.value = false }
}

const applyProposal = async (id: number) => {
  if (!confirm('确认执行整理？执行前会自动快照，可随时回滚。')) return
  applying.value = true
  try {
    const res = await fetch(`${API}/proposals/${id}/apply`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '执行失败')
    flash(`整理完成，剩余 ${data.remaining} 条（快照 #${data.snapshot_id}）`)
    loadAll()
  } catch (e: any) { error.value = e.message } finally { applying.value = false }
}

const rejectProposal = async (id: number) => {
  try {
    const res = await fetch(`${API}/proposals/${id}/reject`, { method: 'POST' })
    if (!res.ok) throw new Error('操作失败')
    flash('已拒绝该提案')
    loadAll()
  } catch (e: any) { error.value = e.message }
}

const pendingProposal = () => proposals.value.find(p => p.status === 'pending')

onMounted(loadAll)
</script>

<template>
  <div class="profile-admin">
    <p class="profile-admin__desc">AI 对你的长期理解（蒸馏层）。原始日记/问答永不删除；整理前自动快照，可回滚</p>

    <div v-if="notice" class="profile-admin__notice">{{ notice }}</div>
    <div v-if="error" class="profile-admin__error">{{ error }}</div>

    <div v-if="loading" class="profile-admin__loading">加载中…</div>
    <template v-else>
      <!-- 概览 + 操作 -->
      <div class="profile-admin__bar">
        <span class="profile-admin__stat">{{ total }} 条 · {{ totalChars }} 字 · {{ groups.length }} 个分类</span>
        <div class="profile-admin__actions">
          <button class="btn btn--ghost" @click="takeSnapshot">📸 手动快照</button>
          <button class="btn btn--primary" :disabled="proposing || !!pendingProposal()" @click="propose">
            {{ proposing ? 'AI 分析中（约1分钟）…' : pendingProposal() ? '有待审提案' : '🧹 生成整理提案' }}
          </button>
        </div>
      </div>

      <!-- 待审提案 -->
      <div v-if="pendingProposal()" class="proposal-card">
        <div class="proposal-card__title">🧹 整理提案（确认后才执行，执行前自动快照）</div>
        <div class="proposal-card__summary">{{ pendingProposal()!.summary }}</div>
        <div class="proposal-card__detail">
          <div v-if="pendingProposal()!.plan!.category_changes.length" class="proposal-card__block">
            <strong>分类归一（{{ pendingProposal()!.plan!.category_changes.length }} 条）：</strong>
            <span v-for="c in pendingProposal()!.plan!.category_changes.slice(0, 12)" :key="c.id" class="proposal-card__tag">{{ c.from }}→{{ c.to }}</span>
            <span v-if="pendingProposal()!.plan!.category_changes.length > 12" class="proposal-card__more">等…</span>
          </div>
          <div v-if="pendingProposal()!.plan!.merges.length" class="proposal-card__block">
            <strong>同义合并（{{ pendingProposal()!.plan!.merges.length }} 组）：</strong>
            <div v-for="(m, i) in pendingProposal()!.plan!.merges.slice(0, 8)" :key="i" class="proposal-card__merge">
              「{{ m.merge_keys.join('」「') }}」→「{{ m.keep_key }}」
            </div>
            <span v-if="pendingProposal()!.plan!.merges.length > 8" class="proposal-card__more">等…</span>
          </div>
        </div>
        <div class="proposal-card__ops">
          <button class="btn btn--primary" :disabled="applying" @click="applyProposal(pendingProposal()!.id)">
            {{ applying ? '执行中…' : '✓ 确认执行' }}
          </button>
          <button class="btn btn--ghost" @click="rejectProposal(pendingProposal()!.id)">拒绝</button>
        </div>
      </div>

      <!-- 画像条目（按分类分组，可折叠） -->
      <div v-for="g in groups" :key="g.category" class="profile-group">
        <button class="profile-group__header" @click="toggleCat(g.category)">
          <span>{{ collapsedCats.has(g.category) ? '▶' : '▼' }} {{ g.category }}</span>
          <span class="profile-group__count">{{ g.items.length }}</span>
        </button>
        <div v-if="!collapsedCats.has(g.category)" class="profile-group__items">
          <div v-for="e in g.items" :key="e.id" class="profile-entry">
            <template v-if="editingId === e.id">
              <div class="profile-entry__edit">
                <div class="profile-entry__edit-row">
                  <input v-model="editCategory" class="profile-entry__input profile-entry__input--cat" placeholder="分类" />
                  <input v-model="editKey" class="profile-entry__input" placeholder="特征名" />
                </div>
                <textarea v-model="editValue" class="profile-entry__textarea" rows="2"></textarea>
                <div class="profile-entry__edit-ops">
                  <button class="btn btn--primary btn--sm" @click="saveEdit(e.id)">保存</button>
                  <button class="btn btn--ghost btn--sm" @click="editingId = null">取消</button>
                </div>
              </div>
            </template>
            <template v-else>
              <div class="profile-entry__body">
                <span class="profile-entry__key">{{ e.key }}</span>
                <span class="profile-entry__value">{{ e.value }}</span>
                <span class="profile-entry__conf" :title="`置信度 ${e.confidence}`">{{ Math.round(e.confidence * 100) }}%</span>
              </div>
              <div class="profile-entry__ops">
                <button class="profile-entry__op" title="编辑" @click="startEdit(e)">✏️</button>
                <button class="profile-entry__op profile-entry__op--danger" title="删除" @click="removeEntry(e)">🗑</button>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- 快照列表 -->
      <div v-if="snapshots.length" class="snapshot-list">
        <div class="snapshot-list__title">📸 快照（{{ snapshots.length }}）</div>
        <div v-for="s in snapshots" :key="s.id" class="snapshot-list__item">
          <span class="snapshot-list__meta">{{ s.created_at.slice(0, 16).replace('T', ' ') }} · {{ s.entry_count }} 条 · {{ s.reason }}</span>
          <button class="btn btn--ghost btn--sm" @click="rollback(s)">回滚到此</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.profile-admin {
  &__desc { font-size: 12px; color: $text-muted; margin: 0 0 $spacing-md; }
  &__bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: $spacing-md;
    flex-wrap: wrap;
    margin-bottom: $spacing-md;
  }
  &__stat { font-size: 13px; color: $text-muted; }
  &__actions { display: flex; gap: 8px; }
  &__notice {
    padding: 8px 12px; margin-bottom: $spacing-sm;
    background: rgba(#10B981, 0.1); color: #059669;
    border-radius: 8px; font-size: 13px;
  }
  &__error {
    padding: 8px 12px; margin-bottom: $spacing-sm;
    background: rgba(#EF4444, 0.08); color: #DC2626;
    border-radius: 8px; font-size: 13px;
  }
  &__loading { color: $text-muted; font-size: 13px; padding: $spacing-md 0; }
}

.proposal-card {
  border: 1px solid rgba(#F59E0B, 0.4);
  background: rgba(#F59E0B, 0.04);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: $spacing-md;

  &__title { font-size: 13px; font-weight: 600; color: #B45309; margin-bottom: 6px; }
  &__summary { font-size: 13px; color: $text-primary; margin-bottom: 8px; }
  &__block { font-size: 12px; color: $text-secondary; margin-bottom: 6px; }
  &__tag {
    display: inline-block; padding: 1px 8px; margin: 2px 4px 2px 0;
    background: rgba(#3B82F6, 0.08); color: #2563EB;
    border-radius: 6px; font-size: 11px;
  }
  &__merge { color: $text-secondary; margin: 2px 0; }
  &__more { color: $text-muted; }
  &__ops { display: flex; gap: 8px; margin-top: 8px; }
}

.profile-group {
  margin-bottom: 6px;

  &__header {
    display: flex; align-items: center; justify-content: space-between;
    width: 100%; padding: 8px 10px;
    border: none; background: rgba(0, 0, 0, 0.03);
    border-radius: 8px; font-size: 13px; font-weight: 600;
    color: $text-primary; cursor: pointer;
    &:hover { background: rgba(0, 0, 0, 0.06); }
  }
  &__count { font-size: 11px; color: $text-muted; font-weight: 400; }
  &__items { padding: 6px 0 0 8px; }
}

.profile-entry {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 7px 8px; border-radius: 8px;
  &:hover { background: rgba(0, 0, 0, 0.02); }
  &:hover .profile-entry__ops { opacity: 1; }

  &__body { flex: 1; min-width: 0; display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
  &__key { font-size: 13px; font-weight: 600; color: $text-primary; flex-shrink: 0; }
  &__value { font-size: 13px; color: $text-secondary; line-height: 1.5; }
  &__conf { font-size: 10px; color: $text-muted; flex-shrink: 0; }
  &__ops { display: flex; gap: 4px; opacity: 0; transition: opacity 0.15s; flex-shrink: 0; }
  &__op {
    border: none; background: transparent; cursor: pointer; font-size: 13px; padding: 2px 4px;
    border-radius: 4px;
    &:hover { background: rgba(0, 0, 0, 0.06); }
  }
  &__edit { flex: 1; }
  &__edit-row { display: flex; gap: 6px; margin-bottom: 6px; }
  &__input {
    flex: 1; padding: 5px 8px; font-size: 13px;
    border: 1px solid $border-color; border-radius: 6px;
    &:focus { outline: none; border-color: $primary-color; }
    &--cat { flex: 0 0 120px; }
  }
  &__textarea {
    width: 100%; padding: 6px 8px; font-size: 13px; font-family: inherit;
    border: 1px solid $border-color; border-radius: 6px; resize: vertical;
    &:focus { outline: none; border-color: $primary-color; }
  }
  &__edit-ops { display: flex; gap: 6px; margin-top: 6px; }
}

.snapshot-list {
  margin-top: $spacing-md;
  border-top: 1px solid $border-color;
  padding-top: $spacing-sm;

  &__title { font-size: 12px; font-weight: 600; color: $text-muted; margin-bottom: 6px; }
  &__item {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    padding: 6px 0; font-size: 12px;
  }
  &__meta { color: $text-secondary; }
}

.btn--sm { padding: 3px 10px; font-size: 12px; }
</style>
