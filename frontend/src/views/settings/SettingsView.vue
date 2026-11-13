<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { CHAT_API_BASE, KB_API_BASE, API_BASE } from '@/config'
import { wereadApi, type WeReadStatus } from '@/api/weread'
import NewSkillForm from '@/components/settings/NewSkillForm.vue'
import ProfileAdminSection from '@/components/settings/ProfileAdminSection.vue'

interface AIConfig {
  id: number
  name: string
  provider: string
  model: string
  api_base: string | null
  temperature: number
  max_tokens: number
  is_active: boolean
  api_key_masked: string
  created_at: string
  updated_at: string
}

interface UserProfile {
  id: number
  category: string
  key: string
  value: string
  confidence: number
  source_count: number
  created_at: string
}

const configs = ref<AIConfig[]>([])
const profiles = ref<UserProfile[]>([])
const loading = ref(false)
const error = ref('')
const showForm = ref(false)
const editingId = ref<number | null>(null)

const form = ref({
  name: '',
  provider: 'deepseek',
  api_key: '',
  api_base: '',
  model: '',
  temperature: 0.7,
  max_tokens: 4096,
  is_active: true,
})

const providers = [
  { value: 'deepseek', label: 'DeepSeek', models: ['deepseek-chat', 'deepseek-reasoner'], defaultBase: 'https://api.deepseek.com' },
  { value: 'openai', label: 'OpenAI', models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'], defaultBase: 'https://api.openai.com/v1' },
  { value: 'moonshot', label: 'Moonshot (月之暗面)', models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'], defaultBase: 'https://api.moonshot.cn/v1' },
  { value: 'zhipu', label: '智谱 AI', models: ['glm-4-flash', 'glm-4-air', 'glm-4-airx', 'glm-4-plus', 'glm-4v', 'glm-4-long', 'glm-4v-plus', 'glm-4'], defaultBase: 'https://open.bigmodel.cn/api/paas/v4' },
  { value: 'qwen', label: '通义千问', models: ['qwen-max', 'qwen-plus', 'qwen-turbo'], defaultBase: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { value: 'custom', label: '自定义 (OpenAI兼容)', models: [], defaultBase: '' },
]

const currentProvider = () => providers.find(p => p.value === form.value.provider)

const onProviderChange = () => {
  const p = currentProvider()
  if (p && p.models.length > 0) {
    form.value.model = p.models[0]
  }
  if (p && p.defaultBase && !form.value.api_base) {
    form.value.api_base = p.defaultBase
  }
}

const fetchConfigs = async () => {
  try {
    const res = await fetch(`${CHAT_API_BASE}/ai-config`)
    configs.value = await res.json()
  } catch (e) {
    console.error('获取配置失败:', e)
  }
}

const fetchProfiles = async () => {
  try {
    const res = await fetch(`${CHAT_API_BASE}/profile`)
    profiles.value = await res.json()
  } catch (e) {
    console.error('获取画像失败:', e)
  }
}

const saveConfig = async () => {
  loading.value = true
  error.value = ''
  try {
    const url = editingId.value
      ? `${CHAT_API_BASE}/ai-config/${editingId.value}`
      : `${CHAT_API_BASE}/ai-config`
    const method = editingId.value ? 'PUT' : 'POST'
    
    const body: any = { ...form.value }
    if (!body.api_base) delete body.api_base
    
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    
    if (!res.ok) {
      const data = await res.json()
      throw new Error(data.detail || '保存失败')
    }
    
    showForm.value = false
    editingId.value = null
    resetForm()
    await fetchConfigs()
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  form.value = {
    name: '', provider: 'deepseek', api_key: '', api_base: '',
    model: 'deepseek-chat', temperature: 0.7, max_tokens: 4096, is_active: true,
  }
}

// ==================== Skill 管理（prompt_skills 体系） ====================
interface SkillInfo {
  id: number
  name: string
  title: string
  description: string
  content: string
  when_to_use: string | null
  user_invocable: boolean
  model_invocable: boolean
  bind_pipeline: string | null
  is_persona: boolean
  is_builtin: boolean
  enabled: boolean
  revision: number
  use_count: number
  updated_at: string | null
}

interface SkillCandidate {
  id: number
  name: string
  title: string
  description: string
  content: string
  reason: string | null
  action: string
  target_name: string | null
  created_at: string | null
}

const skills = ref<SkillInfo[]>([])
const skillLoading = ref(false)
const candidates = ref<SkillCandidate[]>([])
const editingSkill = ref<SkillInfo | null>(null)
const showSkillEditor = ref(false)
const skillSaving = ref(false)
const expandedCandidate = ref<number | null>(null)

const fetchSkills = async () => {
  skillLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/api/prompt-skills`)
    if (res.ok) skills.value = (await res.json()).items || []
  } catch (e) {
    console.error('获取 Skill 列表失败:', e)
  } finally {
    skillLoading.value = false
  }
}

const fetchCandidates = async () => {
  try {
    const res = await fetch(`${API_BASE}/api/prompt-skills/candidates`)
    if (res.ok) candidates.value = (await res.json()).items || []
  } catch { /* 静默 */ }
}

const toggleSkill = async (skill: SkillInfo) => {
  await fetch(`${API_BASE}/api/prompt-skills/${skill.name}/toggle`, { method: 'POST' })
  fetchSkills()
}

const openSkillEditor = (skill: SkillInfo | null) => {
  editingSkill.value = skill ? { ...skill } : null
  showSkillEditor.value = true
}

const saveSkill = async (payload: Partial<SkillInfo> & { name?: string }) => {
  skillSaving.value = true
  try {
    const isNew = !editingSkill.value?.name
    const res = await fetch(
      isNew ? `${API_BASE}/api/prompt-skills` : `${API_BASE}/api/prompt-skills/${editingSkill.value!.name}`,
      {
        method: isNew ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
    if (!res.ok) {
      const d = await res.json()
      alert(d.detail || '保存失败')
      return
    }
    showSkillEditor.value = false
    fetchSkills()
  } finally {
    skillSaving.value = false
  }
}

const resetSkill = async (skill: SkillInfo) => {
  if (!confirm(`把「${skill.title}」恢复为内置默认内容？你的修改会丢失。`)) return
  await fetch(`${API_BASE}/api/prompt-skills/${skill.name}/reset`, { method: 'POST' })
  fetchSkills()
}

const deleteSkill = async (skill: SkillInfo) => {
  if (!confirm(`删除自定义 skill「${skill.title}」？`)) return
  const res = await fetch(`${API_BASE}/api/prompt-skills/${skill.name}`, { method: 'DELETE' })
  if (!res.ok) alert((await res.json()).detail || '删除失败')
  fetchSkills()
}

const reviewCandidate = async (id: number, approve: boolean) => {
  const res = await fetch(`${API_BASE}/api/prompt-skills/candidates/${id}/${approve ? 'approve' : 'reject'}`, { method: 'POST' })
  if (!res.ok) alert((await res.json()).detail || '操作失败')
  fetchCandidates()
  fetchSkills()
}

// ==================== 模块模型配置 ====================
interface ModuleConfigItem {
  module_name: string
  ai_config_id: number | null
  ai_config_name: string | null
  model_name: string | null
  provider: string | null
}

interface AvailableModel {
  id: number
  name: string
  model: string
  provider: string
}

const MODULE_LABELS: Record<string, { label: string; icon: string; color: string }> = {
  agent: { label: 'AI 助手对话', icon: '💬', color: '#EC4899' },
  diary: { label: '日记分析', icon: '📔', color: '#F59E0B' },
  reading: { label: '读书笔记', icon: '📚', color: '#3B82F6' },
  investment: { label: '投资分析', icon: '📈', color: '#10B981' },
  todo: { label: '待办评估', icon: '✅', color: '#EC4899' },
  kb: { label: '知识库', icon: '📖', color: '#6366F1' },
  note: { label: '随笔分析', icon: '✍️', color: '#8B5CF6' },
  auto_classify: { label: '智能分类', icon: '🤖', color: '#0EA5E9' },
  wellbeing: { label: '心力分析', icon: '💚', color: '#14B8A6' },
  coaching: { label: '教练对话', icon: '🎯', color: '#F97316' },
}

const moduleConfigs = ref<ModuleConfigItem[]>([])
const availableModels = ref<AvailableModel[]>([])
const moduleConfigLoading = ref(false)
const moduleConfigSaving = ref<string | null>(null) // 正在保存的模块名

const fetchModuleConfigs = async () => {
  moduleConfigLoading.value = true
  try {
    const res = await fetch(`${KB_API_BASE}/module-configs`)
    if (res.ok) {
      const data = await res.json()
      moduleConfigs.value = data.modules || []
      availableModels.value = data.available_models || []
    }
  } catch (e) {
    console.error('获取模块配置失败:', e)
  } finally {
    moduleConfigLoading.value = false
  }
}

const setModuleConfig = async (moduleName: string, aiConfigId: number) => {
  moduleConfigSaving.value = moduleName
  try {
    const res = await fetch(`${KB_API_BASE}/module-configs/${moduleName}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ai_config_id: aiConfigId }),
    })
    if (res.ok) {
      await fetchModuleConfigs()
    } else {
      const data = await res.json()
      alert(data.detail || '设置失败')
    }
  } catch (e) {
    console.error('设置模块模型失败:', e)
  } finally {
    moduleConfigSaving.value = null
  }
}

const clearModuleConfig = async (moduleName: string) => {
  moduleConfigSaving.value = moduleName
  try {
    const res = await fetch(`${KB_API_BASE}/module-configs/${moduleName}`, {
      method: 'DELETE',
    })
    if (res.ok) {
      await fetchModuleConfigs()
    }
  } catch (e) {
    console.error('清除模块绑定失败:', e)
  } finally {
    moduleConfigSaving.value = null
  }
}

const onModuleModelChange = async (moduleName: string, value: string) => {
  if (value === '' || value === 'default') {
    await clearModuleConfig(moduleName)
  } else {
    await setModuleConfig(moduleName, Number(value))
  }
}

const getModuleMeta = (name: string) => MODULE_LABELS[name] || { label: name, icon: '⚙️', color: '#64748B' }

// ==================== 安全设置 ====================
const showChangePwd = ref(false)
const oldPwd = ref('')
const newPwd = ref('')
const pwdMsg = ref('')
const pwdLoading = ref(false)

const changePassword = async () => {
  if (!oldPwd.value || !newPwd.value) return
  pwdLoading.value = true
  pwdMsg.value = ''
  try {
    const res = await fetch(`${CHAT_API_BASE.replace('/chat', '/auth')}/change-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_password: oldPwd.value, new_password: newPwd.value }),
    })
    if (res.ok) {
      pwdMsg.value = '密码修改成功'
      oldPwd.value = ''
      newPwd.value = ''
      setTimeout(() => { showChangePwd.value = false; pwdMsg.value = '' }, 1500)
    } else {
      const err = await res.json()
      pwdMsg.value = err.detail || '修改失败'
    }
  } catch { pwdMsg.value = '网络错误' }
  finally { pwdLoading.value = false }
}

const logout = async () => {
  const token = localStorage.getItem('daily_auth_token')
  if (token) {
    try {
      await fetch(`${CHAT_API_BASE.replace('/chat', '/auth')}/logout`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      })
    } catch { /* */ }
  }
  localStorage.removeItem('daily_auth_token')
  window.location.reload()
}

//==================== 微信读书配置 ====================
const wereadStatus = ref<WeReadStatus | null>(null)
const wereadApiKey = ref('')
const wereadShowKey = ref(false)
const wereadSaving = ref(false)
const wereadMsg = ref('')
const wereadMsgType = ref<'success' | 'error'>('success')

const fetchWeReadStatus = async () => {
  try {
    wereadStatus.value = await wereadApi.getStatus()
  } catch { /* 静默 */ }
}

const saveWeReadConfig = async () => {
  const key = wereadApiKey.value.trim()
  if (!key) return
  wereadSaving.value = true
  wereadMsg.value = ''
  try {
    const result = await wereadApi.saveConfig(key)
    wereadMsg.value = result.message
    wereadMsgType.value = 'success'
    wereadApiKey.value = ''
    await fetchWeReadStatus()
  } catch (e: any) {
    wereadMsg.value = e.message || '保存失败'
    wereadMsgType.value = 'error'
  } finally {
    wereadSaving.value = false
  }
}

const deleteWeReadConfig = async () => {
  if (!confirm('确定删除微信读书 API Key？')) return
  try {
    await wereadApi.deleteConfig()
    wereadStatus.value = null
    wereadMsg.value = '配置已删除'
    wereadMsgType.value = 'success'
  } catch (e: any) {
    wereadMsg.value = e.message || '删除失败'
    wereadMsgType.value = 'error'
  }
}

// ==================== 画像周期性蒸馏（最小实现） ====================
interface DistillStatus {
  last_run_at: string | null
  days_since: number | null
  last_summary: string | null
  sources_summary?: Record<string, number>
}
interface DistillResult {
  summary: string
  updated: { action: string }[]
  sources_summary: Record<string, number>
}

const distillStatus = ref<DistillStatus>({ last_run_at: null, days_since: null, last_summary: null })
const distilling = ref(false)
const distillResult = ref<DistillResult | null>(null)
const distillError = ref('')

const fetchDistillStatus = async () => {
  try {
    const res = await fetch(`${CHAT_API_BASE}/profile/distill/status`)
    if (res.ok) distillStatus.value = await res.json()
  } catch (e) {
    console.error('获取画像蒸馏状态失败:', e)
  }
}

const distillCounts = computed(() => {
  const counts: Record<string, number> = { created: 0, updated: 0, merged: 0, deleted: 0 }
  for (const u of distillResult.value?.updated || []) {
    counts[u.action] = (counts[u.action] || 0) + 1
  }
  return counts
})

const runDistill = async () => {
  distilling.value = true
  distillError.value = ''
  distillResult.value = null
  try {
    const res = await fetch(`${CHAT_API_BASE}/profile/distill`, { method: 'POST' })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '画像蒸馏失败')
    distillResult.value = data
    await Promise.all([fetchProfiles(), fetchDistillStatus()])
  } catch (e: any) {
    distillError.value = e.message || '画像蒸馏失败'
  } finally {
    distilling.value = false
  }
}

onMounted(() => {
  fetchConfigs()
  fetchProfiles()
  fetchSkills()
  fetchCandidates()
  fetchModuleConfigs()
  fetchWeReadStatus()
  fetchDistillStatus()
})
</script>

<template>
  <div class="settings">
    <h1 class="settings__title">⚙️ 系统设置</h1>

    <!-- AI 模型配置（已移至 AI 聊天页面） -->
    <section class="settings__section">
      <div class="settings__section-header">
        <h2>🤖 AI 模型配置</h2>
        <router-link to="/" class="btn btn--primary">前往 AI 聊天页配置 →</router-link>
      </div>
      <p class="settings__hint" style="margin: 0;">模型配置和 Skill 管理已移至 AI 聊天页面，方便随时切换</p>
    </section>

    <!-- 模块模型配置 -->
    <section class="settings__section module-config-section">
      <div class="settings__section-header">
        <h2>🎛️ 模块模型配置</h2>
        <span class="settings__hint">为不同功能模块指定 AI 模型，未配置的模块使用全局默认</span>
      </div>

      <div v-if="moduleConfigLoading" class="module-config-loading">
        <span class="module-config-loading__spinner"></span>
        <span>加载中...</span>
      </div>

      <div v-else-if="moduleConfigs.length === 0 && availableModels.length === 0" class="config-empty">
        <span class="config-empty__icon">🎛️</span>
        <p>暂无可用模型</p>
        <p class="config-empty__hint">请先在 AI 聊天页面添加模型配置</p>
      </div>

      <div v-else class="module-config-grid">
        <div
          v-for="mod in moduleConfigs"
          :key="mod.module_name"
          class="module-config-card"
          :class="{ 'module-config-card--bound': mod.ai_config_id }"
        >
          <div class="module-config-card__header">
            <span
              class="module-config-card__icon"
              :style="{ background: `linear-gradient(135deg, ${getModuleMeta(mod.module_name).color}20, ${getModuleMeta(mod.module_name).color}10)` }"
            >
              {{ getModuleMeta(mod.module_name).icon }}
            </span>
            <div class="module-config-card__info">
              <span class="module-config-card__name">{{ getModuleMeta(mod.module_name).label }}</span>
              <span v-if="mod.ai_config_name" class="module-config-card__model">
                {{ mod.ai_config_name }} · {{ mod.model_name }}
              </span>
              <span v-else class="module-config-card__default">使用全局默认模型</span>
            </div>
          </div>

          <div class="module-config-card__actions">
            <select
              class="module-config-card__select"
              :value="mod.ai_config_id || 'default'"
              :disabled="moduleConfigSaving === mod.module_name"
              @change="onModuleModelChange(mod.module_name, ($event.target as HTMLSelectElement).value)"
            >
              <option value="default">🔄 使用默认模型</option>
              <option
                v-for="m in availableModels"
                :key="m.id"
                :value="m.id"
              >
                {{ m.name }} ({{ m.model }})
              </option>
            </select>
            <span
              v-if="moduleConfigSaving === mod.module_name"
              class="module-config-card__saving"
            >保存中...</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 用户画像 -->
    <section class="settings__section">
      <div class="settings__section-header">
        <h2>👤 用户画像</h2>
        <span class="settings__hint">AI 分析时会自动完善，你也可以手动调整</span>
      </div>

      <!-- 画像周期性蒸馏 -->
      <div class="distill-block">
        <div class="distill-block__info">
          <span v-if="distillStatus.last_run_at">
            上次回顾：{{ distillStatus.days_since === 0 ? '今天' : `${distillStatus.days_since} 天前` }}
          </span>
          <span v-else class="distill-block__never">还没有做过画像回顾，整合近14天的日记/待办/心力/心愿记录，让AI帮你发现被忽略的模式</span>
          <p v-if="distillStatus.last_summary" class="distill-block__summary">上次发现：{{ distillStatus.last_summary }}</p>
        </div>
        <button class="btn btn--primary" :disabled="distilling" @click="runDistill">
          {{ distilling ? '正在回顾...' : '✨ 立即回顾画像' }}
        </button>
      </div>
      <div v-if="distillError" class="distill-block__error">{{ distillError }}</div>
      <div v-if="distillResult" class="distill-result">
        <p class="distill-result__summary">{{ distillResult.summary }}</p>
        <div class="distill-result__stats">
          <span>创建 {{ distillCounts.created }}</span>
          <span>更新 {{ distillCounts.updated }}</span>
          <span>合并 {{ distillCounts.merged }}</span>
          <span>删除 {{ distillCounts.deleted }}</span>
        </div>
      </div>

      <!-- 画像分层管理：条目编辑/删除 + 快照回滚 + 整理提案（consent-first） -->
      <ProfileAdminSection />
    </section>

    <!-- Skill 管理（prompt_skills 体系：报告模板/教练/人格/自定义） -->
    <section class="settings__section">
      <div class="settings__section-header">
        <h2>🧩 Skill 管理</h2>
        <button class="btn btn--primary btn--sm" @click="openSkillEditor(null)">+ 新建 Skill</button>
      </div>
      <p class="settings__hint">报告模板、教练、人格都在这里。改动保存后下次对话立即生效；AI 会根据描述自动判断何时调用。</p>

      <!-- 候选 skill（自进化产出，待确认） -->
      <div v-if="candidates.length" class="skill-candidates">
        <div class="skill-candidates__title">🌱 候选技能（AI 从对话经验中沉淀的，确认后转正）</div>
        <div v-for="c in candidates" :key="c.id" class="skill-candidate-card">
          <div class="skill-candidate-card__head" @click="expandedCandidate = expandedCandidate === c.id ? null : c.id">
            <span class="skill-candidate-card__name">{{ c.title }}</span>
            <span class="skill-candidate-card__action">{{ c.action === 'patch' ? `改进 ${c.target_name}` : '新技能' }}</span>
            <span class="skill-candidate-card__toggle">{{ expandedCandidate === c.id ? '▼' : '▶' }}</span>
          </div>
          <div v-if="expandedCandidate === c.id" class="skill-candidate-card__body">
            <p v-if="c.reason" class="skill-candidate-card__reason">来源：{{ c.reason }}</p>
            <p class="skill-candidate-card__desc">{{ c.description }}</p>
            <pre class="skill-candidate-card__content">{{ c.content }}</pre>
            <div class="skill-candidate-card__ops">
              <button class="btn btn--primary btn--sm" @click="reviewCandidate(c.id, true)">✓ 转正为正式 Skill</button>
              <button class="btn btn--ghost btn--sm" @click="reviewCandidate(c.id, false)">✗ 拒绝</button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="skillLoading" class="settings__hint">加载中...</div>
      <div v-else class="skill-grid">
        <div
          v-for="skill in skills" :key="skill.name"
          class="skill-card"
          :class="{ 'skill-card--disabled': !skill.enabled }"
        >
          <div class="skill-card__head">
            <span class="skill-card__title">{{ skill.title }}</span>
            <span class="skill-card__badges">
              <span v-if="skill.bind_pipeline" class="skill-card__badge skill-card__badge--pipeline">管线</span>
              <span v-if="skill.is_persona" class="skill-card__badge skill-card__badge--persona">人格</span>
              <span v-if="skill.is_builtin" class="skill-card__badge">内置</span>
            </span>
          </div>
          <p class="skill-card__desc">{{ skill.description }}</p>
          <p class="skill-card__meta">
            <code>/{{ skill.name }}</code>
            <span v-if="skill.use_count"> · 用过 {{ skill.use_count }} 次</span>
            <span> · v{{ skill.revision }}</span>
          </p>
          <div class="skill-card__ops">
            <button class="btn btn--sm btn--ghost" @click="openSkillEditor(skill)">编辑</button>
            <button class="btn btn--sm btn--ghost" @click="toggleSkill(skill)">{{ skill.enabled ? '禁用' : '启用' }}</button>
            <button v-if="skill.is_builtin" class="btn btn--sm btn--ghost" title="恢复内置默认内容" @click="resetSkill(skill)">恢复默认</button>
            <button v-else class="btn btn--sm btn--danger" @click="deleteSkill(skill)">删除</button>
          </div>
        </div>
      </div>
    </section>

    <!-- Skill 编辑弹窗 -->
    <div v-if="showSkillEditor" class="skill-editor-mask" @click.self="showSkillEditor = false">
      <div class="skill-editor">
        <h3>{{ editingSkill?.name ? `编辑「${editingSkill.title}」` : '新建 Skill' }}</h3>
        <template v-if="editingSkill">
          <!-- 编辑已有 -->
          <label class="skill-editor__label">标题</label>
          <input v-model="editingSkill.title" class="settings-input" />
          <label class="skill-editor__label">描述（前 57 字符决定 AI 何时想到它，写触发语）</label>
          <input v-model="editingSkill.description" class="settings-input" />
          <label class="skill-editor__label">内容（支持 {user_profile} {today} 等占位符）</label>
          <textarea v-model="editingSkill.content" class="skill-editor__textarea" rows="12"></textarea>
          <div class="skill-editor__actions">
            <button class="btn btn--primary" :disabled="skillSaving" @click="saveSkill({ title: editingSkill.title, description: editingSkill.description, content: editingSkill.content, when_to_use: editingSkill.when_to_use })">保存</button>
            <button class="btn btn--ghost" @click="showSkillEditor = false">取消</button>
          </div>
        </template>
        <template v-else>
          <!-- 新建 -->
          <NewSkillForm :saving="skillSaving" @save="saveSkill" @cancel="showSkillEditor = false" />
        </template>
      </div>
    </div>

    <!-- 安全设置 -->
    <section class="settings__section">
      <div class="settings__section-header">
        <h2>🔐 安全设置</h2>
      </div>
      <div class="security-actions">
        <button class="btn btn--ghost" @click="showChangePwd = !showChangePwd">
          {{ showChangePwd ? '取消' : '修改访问密码' }}
        </button>
        <button class="btn btn--danger" @click="logout">退出登录</button>
      </div>
      <div v-if="showChangePwd" class="change-pwd-form">
        <input v-model="oldPwd" type="password" placeholder="当前密码" class="settings-input" />
        <input v-model="newPwd" type="password" placeholder="新密码" class="settings-input" />
        <button class="btn btn--primary" @click="changePassword" :disabled="pwdLoading">
          {{ pwdLoading ? '修改中...' : '确认修改' }}
        </button>
        <span v-if="pwdMsg" class="pwd-msg" :class="{ 'pwd-msg--ok': pwdMsg.includes('成功') }">{{ pwdMsg }}</span>
      </div>
    </section>

    <!-- 微信读书配置 -->
    <section class="settings__section">
      <div class="settings__section-header">
        <h2>📚 微信读书</h2>
        <p>配置 WeRead Skill API Key，同步书架和划线笔记到知识系统</p>
      </div>

      <div class="weread-config">
        <!-- 已配置状态 -->
        <div v-if="wereadStatus?.configured" class="weread-config__status">
          <span class="status-dot status-dot--ok"></span>
          <span>已配置</span>
          <span v-if="wereadStatus.last_sync_at" class="status-hint">
            · 上次同步 {{ new Date(wereadStatus.last_sync_at).toLocaleDateString('zh-CN') }}
            · {{ wereadStatus.total_books }} 本书· {{ wereadStatus.total_notes_synced }} 条笔记
          </span>
          <button class="btn-text btn-danger" @click="deleteWeReadConfig">删除</button>
        </div>
        <div v-else class="weread-config__status">
          <span class="status-dot status-dot--off"></span>
          <span class="status-hint">未配置</span>
        </div>

        <!-- Key 输入 -->
        <div class="weread-config__input-row">
          <div class="input-wrap">
            <input
              v-model="wereadApiKey"
              :type="wereadShowKey ? 'text' : 'password'"
              placeholder="wrk-xxxxxxxxxxxxxxxx"
              class="settings-input"
            />
            <button class="show-btn" @click="wereadShowKey = !wereadShowKey">
              {{ wereadShowKey ? '隐藏' : '显示' }}
            </button>
          </div>
          <button
            class="btn btn--primary"
            :disabled="!wereadApiKey.trim() || wereadSaving"
            @click="saveWeReadConfig"
          >
            {{ wereadSaving ? '验证中...' : '保存' }}
          </button>
        </div>
        <p v-if="wereadMsg" class="weread-msg" :class="`weread-msg--${wereadMsgType}`">{{ wereadMsg }}</p>
        <p class="weread-hint">
          在微信读书App 中获取 Skill API Key（设置 → 实验室 → Skill），格式为 <code>wrk-xxx</code>
        </p>
      </div>
    </section>

    <!-- 配置表单弹窗 - 放在最外层避免被父容器层叠上下文遮挡 -->
    <Teleport to="body">
      <div v-if="showForm" class="modal-overlay" @click.self="showForm = false">
        <div class="modal">
          <h3 class="modal__title">{{ editingId ? '编辑' : '新增' }} AI 配置</h3>
          
          <div class="form-group">
            <label>配置名称</label>
            <input v-model="form.name" placeholder="如：DeepSeek 主力模型" />
          </div>

          <div class="form-group">
            <label>AI 提供商</label>
            <select v-model="form.provider" @change="onProviderChange">
              <option v-for="p in providers" :key="p.value" :value="p.value">{{ p.label }}</option>
            </select>
          </div>

          <div class="form-group">
            <label>API Key</label>
            <input v-model="form.api_key" type="password" placeholder="sk-..." />
            <small v-if="editingId">留空表示不修改</small>
          </div>

          <div class="form-group">
            <label>API 地址 (可选)</label>
            <input v-model="form.api_base" :placeholder="currentProvider()?.defaultBase || 'https://api.xxx.com/v1'" />
          </div>

          <div class="form-group">
            <label>模型名称</label>
            <select v-if="currentProvider()?.models.length" v-model="form.model">
              <option v-for="m in currentProvider()?.models" :key="m" :value="m">{{ m }}</option>
            </select>
            <input v-else v-model="form.model" placeholder="模型名称" />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>温度 ({{ form.temperature }})</label>
              <input v-model.number="form.temperature" type="range" min="0" max="2" step="0.1" />
            </div>
            <div class="form-group">
              <label>最大 Token</label>
              <input v-model.number="form.max_tokens" type="number" min="256" max="32768" />
            </div>
          </div>

          <div class="form-group">
            <label>
              <input v-model="form.is_active" type="checkbox" /> 设为当前使用的配置
            </label>
          </div>

          <div v-if="error" class="form-error">{{ error }}</div>

          <div class="modal__actions">
            <button class="btn btn--ghost" @click="showForm = false">取消</button>
            <button class="btn btn--primary" :disabled="loading" @click="saveConfig">
              {{ loading ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style lang="scss" scoped>
.settings {
  &__title {
    font-size: $font-size-xl;
    margin-bottom: $spacing-lg;

    @media (max-width: $breakpoint-sm) {
      font-size: $font-size-lg;
    }
  }

  &__section {
    @include glass-card;
    padding: $spacing-lg;
    margin-bottom: $spacing-lg;

    @media (max-width: $breakpoint-sm) {
      padding: $spacing-md;
      border-radius: $border-radius-md;
    }
  }

  &__section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: $spacing-lg;

    h2 {
      font-size: $font-size-lg;

      @media (max-width: $breakpoint-sm) {
        font-size: $font-size-md;
      }
    }

    @media (max-width: $breakpoint-sm) {
      flex-direction: column;
      align-items: flex-start;
      gap: $spacing-xs;
      margin-bottom: $spacing-md;
    }
  }

  &__hint {
    font-size: $font-size-sm;
    color: $text-secondary;

    @media (max-width: $breakpoint-sm) {
      font-size: $font-size-xs;
    }
  }
}

.config-list {
  display: grid;
  gap: $spacing-md;
}

.config-card {
  padding: $spacing-md;
  border-radius: $border-radius-md;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid $border-color;
  transition: all $transition-fast;

  &--active {
    border-color: $primary-color;
    background: rgba($primary-color, 0.05);
  }

  &__header {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    margin-bottom: $spacing-sm;
  }

  &__name { font-weight: 600; font-size: $font-size-md; }

  &__badge {
    font-size: $font-size-xs;
    padding: 2px 8px;
    border-radius: 99px;
    background: $primary-color;
    color: white;
  }

  &__info {
    display: flex;
    gap: $spacing-md;
    font-size: $font-size-sm;
    color: $text-secondary;
    margin-bottom: $spacing-sm;
  }

  &__model { font-weight: 500; color: $accent-color; }

  &__meta {
    display: flex;
    gap: $spacing-md;
    font-size: $font-size-xs;
    color: $text-muted;
    margin-bottom: $spacing-sm;
    flex-wrap: wrap;
  }

  &__actions {
    display: flex;
    gap: $spacing-sm;
    justify-content: flex-end;
  }
}

.config-empty {
  text-align: center;
  padding: $spacing-xl;
  color: $text-secondary;

  &__icon { font-size: 48px; display: block; margin-bottom: $spacing-md; }
  &__hint { font-size: $font-size-sm; color: $text-muted; margin-top: $spacing-xs; }
}

// 模块模型配置
.module-config-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: $spacing-sm;
  padding: $spacing-xl;
  color: $text-secondary;
  font-size: $font-size-sm;

  &__spinner {
    width: 20px;
    height: 20px;
    border: 2px solid rgba(99, 102, 241, 0.2);
    border-top-color: #6366F1;
    border-radius: 50%;
    animation: module-spin 0.8s linear infinite;
  }
}

@keyframes module-spin {
  to { transform: rotate(360deg); }
}

.module-config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: $spacing-md;

  @media (max-width: $breakpoint-sm) {
    grid-template-columns: 1fr;
  }
}

.module-config-card {
  padding: $spacing-md;
  border-radius: $border-radius-md;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid $border-color;
  transition: all 0.3s ease;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
    border-color: rgba(99, 102, 241, 0.2);
  }

  &--bound {
    border-color: rgba(99, 102, 241, 0.3);
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.03), rgba(139, 92, 246, 0.03));
  }

  &__header {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    margin-bottom: $spacing-md;
  }

  &__icon {
    width: 40px;
    height: 40px;
    border-radius: $border-radius-sm;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
  }

  &__info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    flex: 1;
  }

  &__name {
    font-weight: 600;
    font-size: $font-size-md;
    color: $text-primary;
  }

  &__model {
    font-size: $font-size-xs;
    color: $accent-color;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__default {
    font-size: $font-size-xs;
    color: $text-muted;
    font-style: italic;
  }

  &__actions {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
  }

  &__select {
    flex: 1;
    padding: 6px 10px;
    border: 1px solid $border-color;
    border-radius: $border-radius-sm;
    font-size: $font-size-sm;
    color: $text-primary;
    background: rgba(255, 255, 255, 0.8);
    cursor: pointer;
    transition: border-color 0.2s;
    appearance: auto;

    &:hover {
      border-color: rgba(99, 102, 241, 0.4);
    }

    &:focus {
      outline: none;
      border-color: #6366F1;
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
    }

    &:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
  }

  &__saving {
    font-size: $font-size-xs;
    color: #6366F1;
    white-space: nowrap;
    animation: module-pulse 1.5s ease-in-out infinite;
  }
}

@keyframes module-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}



.btn {
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-sm;
  font-size: $font-size-sm;
  font-weight: 500;
  cursor: pointer;
  transition: all $transition-fast;
  border: none;

  &--primary {
    background: linear-gradient(135deg, $primary-color, $accent-color);
    color: white;
    &:hover { opacity: 0.9; transform: translateY(-1px); }
  }

  &--success {
    background: $success-color;
    color: white;
    &:hover { opacity: 0.9; }
  }

  &--danger {
    background: transparent;
    color: $danger-color;
    &:hover { background: rgba($danger-color, 0.1); }
  }

  &--ghost {
    background: transparent;
    color: $text-secondary;
    &:hover { background: rgba($primary-color, 0.1); }
  }

  &--sm {
    padding: 4px 12px;
    font-size: $font-size-xs;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.distill-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: $spacing-md;
  padding: $spacing-md;
  border-radius: $border-radius-md;
  background: linear-gradient(135deg, rgba(#F43F5E, 0.06), rgba(#FBBF24, 0.06));
  margin-bottom: $spacing-md;
  flex-wrap: wrap;

  &__info {
    flex: 1;
    min-width: 200px;
    font-size: 13px;
    color: $text-secondary;
  }

  &__never {
    color: $text-muted;
    font-size: 12px;
    line-height: 1.6;
  }

  &__summary {
    margin: 4px 0 0;
    font-size: 12px;
    color: $text-primary;
  }

  &__error {
    color: $danger-color;
    font-size: 12px;
    margin-bottom: $spacing-sm;
  }
}

.distill-result {
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-md;
  background: rgba(16, 185, 129, 0.08);
  margin-bottom: $spacing-md;

  &__summary {
    margin: 0 0 6px;
    font-size: 13px;
    color: $text-primary;
  }

  &__stats {
    display: flex;
    gap: $spacing-md;
    font-size: 12px;
    color: $text-secondary;
  }
}

.profile-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: $spacing-md;
}

.profile-filter-btn {
  padding: 4px 12px;
  border-radius: 16px;
  border: 1px solid $border-color;
  background: rgba(255, 255, 255, 0.6);
  font-size: $font-size-xs;
  cursor: pointer;
  transition: all 0.15s;
  color: $text-secondary;

  &:hover {
    border-color: $primary-color;
    color: $primary-color;
  }

  &--active {
    background: rgba($primary-color, 0.1);
    border-color: $primary-color;
    color: $primary-color;
    font-weight: 600;
  }
}

.profile-group {
  margin-bottom: $spacing-lg;

  &__title {
    font-size: $font-size-md;
    font-weight: 600;
    margin-bottom: $spacing-sm;
    padding-bottom: $spacing-xs;
    border-bottom: 1px solid $border-color;
  }
}

.profile-list {
  display: grid;
  gap: $spacing-sm;
}

.profile-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: $spacing-sm $spacing-md;
  border-radius: $border-radius-sm;
  background: rgba(255, 255, 255, 0.5);

  @media (max-width: $breakpoint-sm) {
    flex-direction: column;
    align-items: flex-start;
    gap: $spacing-sm;
  }

  &__content {
    display: flex;
    gap: $spacing-md;
    flex: 1;
  }

  &__key {
    font-weight: 500;
    min-width: 120px;
    color: $text-secondary;
  }

  &__value { color: $text-primary; }

  &__meta {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
  }

  &__confidence {
    height: 4px;
    min-width: 40px;
    background: $primary-color;
    border-radius: 2px;
  }

  &__count {
    font-size: $font-size-xs;
    color: $text-muted;
    white-space: nowrap;
  }
}

// Skill 管理（prompt_skills 体系）
.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: $spacing-md;
}

.skill-card {
  border-radius: $border-radius-md;
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid $border-color;
  padding: $spacing-md;
  transition: all $transition-fast;

  &:hover { box-shadow: 0 4px 16px rgba(236, 72, 153, 0.08); }
  &--disabled { opacity: 0.5; }

  &__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: $spacing-sm;
  }

  &__title { font-weight: 600; font-size: $font-size-sm; }

  &__badges { display: flex; gap: 4px; flex-shrink: 0; }

  &__badge {
    font-size: 10px;
    padding: 1px 8px;
    border-radius: 99px;
    background: rgba(0, 0, 0, 0.05);
    color: $text-muted;

    &--pipeline { background: rgba(#3B82F6, 0.12); color: #1D4ED8; }
    &--persona { background: rgba(#8B5CF6, 0.12); color: #6D28D9; }
  }

  &__desc {
    font-size: $font-size-xs;
    color: $text-secondary;
    margin: $spacing-xs 0;
    line-height: 1.5;
  }

  &__meta {
    font-size: 10px;
    color: $text-muted;
    margin-bottom: $spacing-sm;
    code { background: rgba(0,0,0,0.05); padding: 1px 6px; border-radius: 4px; }
  }

  &__ops { display: flex; gap: 6px; flex-wrap: wrap; }
}

// 候选技能
.skill-candidates {
  margin-bottom: $spacing-lg;
  border: 1px dashed rgba(#10B981, 0.4);
  border-radius: $border-radius-md;
  padding: $spacing-md;
  background: rgba(#10B981, 0.03);

  &__title { font-size: $font-size-xs; font-weight: 600; color: #059669; margin-bottom: $spacing-sm; }
}

.skill-candidate-card {
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid $border-color;
  border-radius: $border-radius-sm;
  margin-bottom: $spacing-xs;

  &__head {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    padding: $spacing-sm $spacing-md;
    cursor: pointer;
    &:hover { background: rgba(0,0,0,0.02); }
  }

  &__name { font-weight: 600; font-size: $font-size-sm; flex: 1; }
  &__action { font-size: 10px; color: $text-muted; }
  &__toggle { font-size: 10px; color: $text-muted; }

  &__body { padding: 0 $spacing-md $spacing-md; }
  &__reason { font-size: $font-size-xs; color: $text-secondary; font-style: italic; }
  &__desc { font-size: $font-size-xs; color: $text-secondary; }
  &__content {
    font-size: $font-size-xs; white-space: pre-wrap; word-break: break-word;
    background: rgba(0,0,0,0.03); padding: $spacing-sm; border-radius: $border-radius-sm;
    max-height: 240px; overflow-y: auto; font-family: ui-monospace, monospace;
  }
  &__ops { display: flex; gap: $spacing-sm; margin-top: $spacing-sm; }
}

// Skill 编辑弹窗
.skill-editor-mask {
  position: fixed; inset: 0; z-index: 500;
  background: rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center;
  padding: $spacing-md;
}

.skill-editor {
  background: #fff; border-radius: $border-radius-lg;
  width: 100%; max-width: 720px; max-height: 85vh; overflow-y: auto;
  padding: $spacing-lg;

  h3 { margin-bottom: $spacing-md; }

  &__label { display: block; font-size: $font-size-xs; font-weight: 600; color: $text-secondary; margin: $spacing-sm 0 4px; }

  &__textarea {
    width: 100%; padding: $spacing-sm $spacing-md; border: 1px solid $border-color; border-radius: $border-radius-sm;
    font-size: $font-size-sm; font-family: ui-monospace, monospace; resize: vertical; box-sizing: border-box;
    background: rgba(255,255,255,0.8);
    &:focus { outline: none; border-color: $primary-color; }
  }

  &__actions { display: flex; gap: $spacing-sm; margin-top: $spacing-md; }
}

.security-actions {
  display: flex; gap: $spacing-sm; margin-bottom: $spacing-md;
}

.change-pwd-form {
  display: flex; gap: $spacing-sm; align-items: center; flex-wrap: wrap;
}

.settings-input {
  padding: 8px 14px; border: 1px solid $border-color; border-radius: 8px;
  font-size: 14px; outline: none; background: rgba(255,255,255,0.8);
  &:focus { border-color: $primary-color; box-shadow: 0 0 0 2px rgba($primary-color, 0.1); }
}

.pwd-msg {
  font-size: 13px; color: $danger-color;
  &--ok { color: $success-color; }
}

.btn--danger {
  background: rgba(239, 68, 68, 0.1); color: #EF4444; border: 1px solid rgba(239, 68, 68, 0.2);
  &:hover { background: rgba(239, 68, 68, 0.2); }
}

// 微信读书配置
.weread-config {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;

  &__status {
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    font-size: $font-size-sm;
    color: $text-primary;
  }

  &__input-row {
    display: flex;
    gap: $spacing-sm;
    align-items: center;
    .input-wrap { flex: 1; display: flex; position: relative; }
    .settings-input { flex: 1; padding-right: 60px; }
    .show-btn {
      position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
      font-size: 12px; color: $text-muted; background: none; border: none; cursor: pointer;
      &:hover { color: $primary-color; }
    }
  }
}

.status-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  &--ok { background: #10b981; }
  &--off { background: #94a3b8; }
}

.status-hint { color: $text-muted; font-size: $font-size-xs; }

.btn-text { background: none; border: none; cursor: pointer; font-size: $font-size-xs; padding: 04px; }
.btn-danger { color: #ef4444; &:hover { text-decoration: underline; } }

.weread-msg {
  font-size: $font-size-xs;
  &--success { color: #10b981; }
  &--error { color: #ef4444; }
}

.weread-hint {
  font-size: $font-size-xs;
  color: $text-muted;
  line-height: 1.6;
  code { background: rgba($primary-color, 0.08); padding: 1px 4px; border-radius: 3px; }
}
</style>

<style>
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.modal {
  background: white;
  padding: 24px;
  width: 100%;
  max-width: 560px;
  max-height: 90vh;
  overflow-y: auto;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  -webkit-overflow-scrolling: touch;
}

.modal__title { font-size: 18px; margin-bottom: 20px; font-weight: 600; }

.modal__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}

.modal .form-group {
  margin-bottom: 16px;
}

.modal .form-group label {
  display: block;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 6px;
  color: #1a1a2e;
}

.modal .form-group input,
.modal .form-group select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  font-size: 14px;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.modal .form-group input:focus,
.modal .form-group select:focus {
  outline: none;
  border-color: #6366f1;
}

.modal .form-group input[type="range"] {
  padding: 0;
}

.modal .form-group input[type="checkbox"] {
  width: auto;
  margin-right: 6px;
}

.modal .form-group small {
  font-size: 12px;
  color: #999;
}

.modal .form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

@media (max-width: 480px) {
  .modal {
    padding: 16px;
  }

  .modal .form-row {
    grid-template-columns: 1fr;
  }
}

.modal .form-error {
  color: #ef4444;
  font-size: 14px;
  margin-top: 8px;
}

.modal .btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.modal .btn--primary {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
}

.modal .btn--primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

.modal .btn--ghost {
  background: transparent;
  color: #666;
}

.modal .btn--ghost:hover {
  background: rgba(99, 102, 241, 0.1);
}

.modal .btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
