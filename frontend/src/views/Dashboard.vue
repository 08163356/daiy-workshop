<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'
import { useGraphStore } from '@/stores'
import { api } from '@/api'
import { timeCapsuleApi } from '@/api/timeCapsule'
import { wereadApi, type WeReadStats } from '@/api/weread'
import { wishlistApi, type WishDashboard } from '@/api/wishlist'
import type { DashboardData } from '@/api/timeCapsule'
import {
  LayoutDashboard, BookOpen, Lightbulb, FileText,
  Sparkles, RotateCcw, Package, BookMarked,
  Hourglass, CalendarDays, Tag,
} from '@lucide/vue'

marked.setOptions({ breaks: true, gfm: true })

const router = useRouter()
const graphStore = useGraphStore()

const loading = ref(true)
const timelineData = ref<any[]>([])
const categories = ref<{ title: string; count: number }[]>([])

// 知识复利播报
const insightLoading = ref(false)
const insightData = ref<{ status: string; insight: string; cached?: boolean; note_count?: number; message?: string }>({ status: '', insight: '' })

// 获取统计数据
const stats = computed(() => graphStore.statistics)

// 渲染 markdown
const renderMarkdown = (md: string): string => {
  if (!md) return ''
  try {
    return marked.parse(md) as string
  } catch {
    return md.replace(/\n/g, '<br>')
  }
}

// 格式化日期
const formatDate = (dateStr: string): string => {
  // 支持 "2026.03.04" 格式
  const normalized = dateStr.replace(/\./g, '-')
  const date = new Date(normalized)
  if (isNaN(date.getTime())) return dateStr
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// 跳转
const goToTimeline = () => router.push('/timeline')
const goToNotes = () => router.push('/timeline')
const goToConcepts = () => router.push('/knowledge')

// 从 knowledge.json 获取分类数据（快速、数据准确）
const fetchCategories = async () => {
  try {
    const knowledgeData = await api.getKnowledge()
    categories.value = knowledgeData.map((cat: any) => ({
      title: cat.title || '未分类',
      count: cat.items?.length || 0,
    }))
  } catch (e) {
    console.error('获取分类失败:', e)
  }
}

// 获取知识复利播报
const fetchDailyInsight = async (forceRefresh = false) => {
  insightLoading.value = true
  try {
    insightData.value = await api.getDailyInsight(forceRefresh)
  } catch (e) {
    console.error('获取知识复利播报失败:', e)
    insightData.value = { status: 'error', insight: '', message: '加载失败' }
  }
  insightLoading.value = false
}

// 时光胶囊倒计时
const capsuleData = ref<DashboardData | null>(null)
const fetchCapsuleData = async () => {
  try {
    capsuleData.value = await timeCapsuleApi.getDashboard()
  } catch (e) {
    console.warn('时光胶囊数据加载失败:', e)
  }
}
const goToCapsule = () => router.push('/time-capsule')

// 微信读书统计
const wereadStats = ref<WeReadStats | null>(null)
const fetchWeReadStats = async () => {
  try {
    wereadStats.value = await wereadApi.getStats()
  } catch {
    // 静默失败（未配置时正常）
  }
}
const goToWeRead = () => router.push('/weread')

// 心愿墙统计
const wishData = ref<WishDashboard | null>(null)
const fetchWishData = async () => {
  try {
    wishData.value = await wishlistApi.getDashboard()
  } catch (e) {
    console.warn('心愿墙数据加载失败:', e)
  }
}
const goToWishlist = () => router.push('/wishlist')

onMounted(async () => {
  loading.value = true
  await Promise.all([
    graphStore.loadStatistics(),
    api.getTimeline(0, 5).then(data => { timelineData.value = data.items || [] }),
    fetchCategories(),
  ])
  loading.value = false
  
  // 知识复利播报异步加载（不阻塞主页面）
  fetchDailyInsight()
  // 时光胶囊倒计时
  fetchCapsuleData()
  // 微信读书统计（后台静默加载）
  fetchWeReadStats()
  // 心愿墙统计（后台静默加载）
  fetchWishData()
})
</script>

<template>
  <div class="dashboard">
    <!-- 页面标题 -->
    <header class="dashboard__header animate-slideUp">
      <h1 class="dashboard__title">
        <LayoutDashboard :size="26" :stroke-width="1.75" class="dashboard__title-icon" />
        仪表盘
      </h1>
      <p class="dashboard__subtitle">欢迎回来，这是你的阅读概览</p>
    </header>
    
    <!-- 加载状态 -->
    <div v-if="loading" class="dashboard__loading">
      <div class="loading-spinner"></div>
      <span>加载中...</span>
    </div>
    
    <template v-else-if="stats">
      <!-- 统计卡片 -->
      <section class="dashboard__stats">
        <div class="stat-card stat-card--clickable animate-slideUp" style="animation-delay: 0.1s" @click="goToTimeline">
          <div class="stat-card__icon stat-card__icon--blue"><BookOpen :size="24" :stroke-width="1.75" /></div>
          <div class="stat-card__content">
            <div class="stat-card__value">{{ stats.totalBooks }}</div>
            <div class="stat-card__label">已读书籍</div>
          </div>
          <span class="stat-card__arrow">→</span>
        </div>
        
        <div class="stat-card stat-card--clickable animate-slideUp" style="animation-delay: 0.15s" @click="goToConcepts">
          <div class="stat-card__icon stat-card__icon--purple"><Lightbulb :size="24" :stroke-width="1.75" /></div>
          <div class="stat-card__content">
            <div class="stat-card__value">{{ stats.totalConcepts }}</div>
            <div class="stat-card__label">核心概念</div>
          </div>
          <span class="stat-card__arrow">→</span>
        </div>
        
        <div class="stat-card stat-card--clickable animate-slideUp" style="animation-delay: 0.2s" @click="goToNotes">
          <div class="stat-card__icon stat-card__icon--green"><FileText :size="24" :stroke-width="1.75" /></div>
          <div class="stat-card__content">
            <div class="stat-card__value">{{ stats.totalNotes }}</div>
            <div class="stat-card__label">读书笔记</div>
          </div>
          <span class="stat-card__arrow">→</span>
        </div>
      </section>

      <section class="dashboard__insight card animate-slideUp" style="animation-delay: 0.25s">
        <div class="card-header">
          <h3><Sparkles :size="16" :stroke-width="1.75" style="margin-right:6px;vertical-align:middle;" />今日知识复利</h3>
          <button
            v-if="insightData.status === 'success'" 
            class="btn btn-ghost btn-sm" 
            @click="fetchDailyInsight(true)"
            :disabled="insightLoading"
          >
            <RotateCcw v-if="!insightLoading" :size="13" style="margin-right:4px;vertical-align:middle;" />
            {{ insightLoading ? '生成中...' : '换一个' }}
          </button>
        </div>
        <div class="card-body">
          <div v-if="insightLoading && !insightData.insight" class="insight-loading">
            <div class="insight-loading__dots">
              <span></span><span></span><span></span>
            </div>
            <span class="insight-loading__text">正在从你的知识库中发现深层连接...</span>
          </div>
          
          <div v-else-if="insightData.status === 'success' && insightData.insight" class="insight-content">
            <div class="insight-content__body" v-html="renderMarkdown(insightData.insight)"></div>
            <div class="insight-content__meta">
              <span v-if="insightData.cached" class="insight-meta-tag"><Package :size="12" style="margin-right:3px;vertical-align:middle;" />今日缓存</span>
              <span v-if="insightData.note_count" class="insight-meta-tag"><BookOpen :size="12" style="margin-right:3px;vertical-align:middle;" />基于 {{ insightData.note_count }} 篇笔记</span>
            </div>
          </div>
          
          <div v-else-if="insightData.status === 'insufficient_data'" class="insight-empty">
            <BookOpen :size="32" :stroke-width="1.5" class="insight-empty__icon" />
            <p>{{ insightData.message }}</p>
          </div>
          
          <div v-else-if="insightData.status === 'no_ai_config'" class="insight-empty">
            <Sparkles :size="32" :stroke-width="1.5" class="insight-empty__icon" />
            <p>{{ insightData.message }}</p>
          </div>
          
          <div v-else-if="insightData.status === 'error'" class="insight-empty">
            <RotateCcw :size="32" :stroke-width="1.5" class="insight-empty__icon" />
            <p>{{ insightData.message || '加载失败，点击重试' }}</p>
            <button class="btn btn-sm btn-primary" @click="fetchDailyInsight(true)">重试</button>
          </div>
          
          <div v-else class="insight-empty">
            <Sparkles :size="32" :stroke-width="1.5" class="insight-empty__icon" />
            <p>知识复利播报加载中...</p>
          </div>
        </div>
      </section>

      <section
        v-if="wereadStats && (wereadStats.today_minutes || wereadStats.week_minutes || wereadStats.total_minutes)"
        class="dashboard__weread card animate-slideUp"
        style="animation-delay: 0.27s"
        @click="goToWeRead"
      >
        <div class="card-body weread-mini">
          <BookMarked :size="28" :stroke-width="1.5" class="weread-mini__icon" />
          <div class="weread-mini__content">
            <h4>微信读书</h4>
            <div class="weread-mini__stats">
              <span v-if="wereadStats.today_minutes">今日<strong>{{ wereadStats.today_minutes }}分钟</strong></span>
              <span v-if="wereadStats.week_minutes">本周 <strong>{{ wereadStats.week_minutes }}分钟</strong></span>
              <span v-if="wereadStats.total_minutes">总计 <strong>{{ Math.round(wereadStats.total_minutes / 60) }}小时</strong></span>
            </div>
          </div>
          <span class="weread-mini__arrow">→</span>
        </div>
      </section>

      <!-- 时光胶囊倒计时卡片 -->
      <section v-if="capsuleData && capsuleData.nearest_letter" class="dashboard__capsule card animate-slideUp" style="animation-delay: 0.28s" @click="goToCapsule">
        <div class="card-body capsule-countdown">
          <Hourglass :size="28" :stroke-width="1.5" class="capsule-countdown__icon" />
          <div class="capsule-countdown__content">
            <h4 v-if="capsuleData.nearest_letter.days_until > 0">
              距下一封信开封还有 <strong>{{ capsuleData.nearest_letter.days_until }}</strong> 天
            </h4>
            <h4 v-else-if="capsuleData.nearest_letter.days_until === 0">
              今天有一封信可以开封！
            </h4>
            <h4 v-else>
              有一封信已到开封日！
            </h4>
            <p>{{ capsuleData.nearest_letter.title }} ·写给{{ capsuleData.nearest_letter.recipient }}</p>
          </div>
          <div class="capsule-countdown__stats">
            <span>{{ capsuleData.sealed_count }} 封待开封</span>
            <span>{{ capsuleData.opened_count }} 封已读</span>
          </div>
          <span class="capsule-countdown__arrow">→</span>
        </div>
      </section>

      <!-- 心愿墙卡片 -->
      <section v-if="wishData && wishData.total > 0" class="dashboard__wishlist card animate-slideUp" style="animation-delay: 0.29s" @click="goToWishlist">
        <div class="card-body wish-mini">
          <Sparkles :size="28" :stroke-width="1.5" class="wish-mini__icon" />
          <div class="wish-mini__content">
            <h4>心愿墙</h4>
            <div class="wish-mini__stats">
              <span>进行中 <strong>{{ wishData.active_count }}</strong></span>
              <span>已实现 <strong>{{ wishData.achieved_count }}</strong></span>
              <span v-if="wishData.pending_candidates > 0" class="wish-mini__pending">✨ {{ wishData.pending_candidates }} 条待审核</span>
            </div>
          </div>
          <span class="wish-mini__arrow">→</span>
        </div>
      </section>
      
      <!-- 主要内容区 -->
      <section class="dashboard__main">
        <!-- 左侧：最近阅读（使用时间线数据） -->
        <div class="dashboard__recent card animate-slideUp" style="animation-delay: 0.3s">
          <div class="card-header">
            <h3><CalendarDays :size="16" :stroke-width="1.75" style="margin-right:6px;vertical-align:middle;" />最近阅读</h3>
            <button class="btn btn-ghost btn-sm" @click="goToTimeline">查看全部</button>
          </div>
          <div class="card-body">
            <div v-if="timelineData.length === 0" class="activity-empty">
              暂无阅读记录
            </div>
            <div class="activity-list" v-else>
              <div
                v-for="(item, index) in timelineData"
                :key="index"
                class="activity-item"
                @click="goToTimeline"
              >
                <div class="activity-item__date">{{ formatDate(item.date) }}</div>
                <div class="activity-item__content">
                  <div class="activity-item__book">{{ item.title }}</div>
                  <div class="activity-item__meta">
                    <span v-if="item.key_points && item.key_points.length">
                      <Lightbulb :size="12" style="vertical-align:middle;margin-right:2px;" />{{ item.key_points.length }} 个要点
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 右侧：热门标签（使用概念分类数据） -->
        <div class="dashboard__tags card animate-slideUp" style="animation-delay: 0.35s">
          <div class="card-header">
            <h3><Tag :size="16" :stroke-width="1.75" style="margin-right:6px;vertical-align:middle;" />知识分类</h3>
          </div>
          <div class="card-body">
            <div v-if="categories.length === 0" class="activity-empty">
              暂无分类数据
            </div>
            <div class="tag-list" v-else>
              <div
                v-for="cat in categories"
                :key="cat.title"
                class="tag-item"
                @click="goToConcepts"
              >
                <span class="tag-item__name">{{ cat.title }}</span>
                <span class="tag-item__count">{{ cat.count }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>
      
      <!-- 快捷入口 -->
      <section class="dashboard__shortcuts animate-slideUp" style="animation-delay: 0.4s">
        <div class="shortcut-card" @click="goToTimeline">
          <div class="shortcut-card__icon">📅</div>
          <div class="shortcut-card__content">
            <h4>阅读时间线</h4>
            <p>回顾你的阅读历程</p>
          </div>
          <div class="shortcut-card__arrow">→</div>
        </div>
        
        <div class="shortcut-card" @click="goToConcepts">
          <div class="shortcut-card__icon">📚</div>
          <div class="shortcut-card__content">
            <h4>知识分类</h4>
            <p>浏览你积累的知识体系</p>
          </div>
          <div class="shortcut-card__arrow">→</div>
        </div>
      </section>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.dashboard {
  &__header {
    margin-bottom: $spacing-xl;
  }
  
  &__title {
    font-size: $font-size-xxl;
    font-weight: 700;
    color: $text-primary;
    display: flex;
    align-items: center;
    gap: $spacing-sm;
    
    @media (max-width: $breakpoint-sm) {
      font-size: $font-size-xl;
    }
    
    &-icon {
      display: flex;
      align-items: center;
      flex-shrink: 0;
      color: $primary-color;
    }
  }
  
  &__subtitle {
    color: $text-secondary;
    margin-top: $spacing-xs;
  }
  
  &__loading {
    @include flex-center;
    flex-direction: column;
    gap: $spacing-md;
    padding: $spacing-xxl;
    color: $text-secondary;
    
    .loading-spinner {
      width: 40px;
      height: 40px;
      border: 3px solid rgba($primary-color, 0.2);
      border-top-color: $primary-color;
      border-radius: 50%;
      animation: spin 1s linear infinite;
    }
  }
  
  &__stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: $spacing-lg;
    margin-bottom: $spacing-xl;
    
    @media (max-width: $breakpoint-lg) {
      grid-template-columns: repeat(2, 1fr);
    }
    
    @media (max-width: $breakpoint-sm) {
      grid-template-columns: 1fr;
    }
  }
  
  &__main {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: $spacing-lg;
    margin-bottom: $spacing-xl;
    
    @media (max-width: $breakpoint-lg) {
      grid-template-columns: 1fr;
    }
  }
  
  &__shortcuts {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: $spacing-lg;
    
    @media (max-width: $breakpoint-md) {
      grid-template-columns: 1fr;
    }

    @media (max-width: $breakpoint-sm) {
      gap: $spacing-md;
    }
  }
}

// 统计卡片
.stat-card {
  @include glass-card;
  padding: $spacing-lg;
  display: flex;
  align-items: center;
  gap: $spacing-md;
  @include hover-lift;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    border-radius: $border-radius-md;
  }
  
  &--clickable {
    cursor: pointer;
    
    &:hover {
      border-color: rgba($primary-color, 0.3);
      
      .stat-card__arrow {
        transform: translateX(4px);
        color: $primary-color;
      }
    }
  }
  
  &__icon {
    width: 56px;
    height: 56px;
    border-radius: $border-radius-md;
    @include flex-center;

    @media (max-width: $breakpoint-sm) {
      width: 44px;
      height: 44px;
      font-size: 22px;
    }
    
    &--blue { background: rgba($primary-color, 0.15); }
    &--purple { background: rgba($accent-color, 0.15); }
    &--green { background: rgba($success-color, 0.15); }
  }
  
  &__content {
    flex: 1;
  }
  
  &__value {
    font-size: $font-size-xl;
    font-weight: 700;
    color: $text-primary;
  }
  
  &__label {
    font-size: $font-size-sm;
    color: $text-secondary;
    margin-top: $spacing-xs;
  }
  
  &__arrow {
    font-size: $font-size-lg;
    color: $text-muted;
    transition: all $transition-fast;
  }
}

// 活动列表
.activity-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-md;
}

.activity-item {
  display: flex;
  gap: $spacing-md;
  padding: $spacing-md;
  background: rgba($primary-color, 0.03);
  border-radius: $border-radius-md;
  transition: background $transition-fast;
  cursor: pointer;
  
  &:hover {
    background: rgba($primary-color, 0.08);
  }
  
  &__date {
    min-width: 60px;
    font-size: $font-size-sm;
    color: $text-muted;
    font-weight: 500;
  }
  
  &__content {
    flex: 1;
  }
  
  &__book {
    font-weight: 600;
    color: $text-primary;
    margin-bottom: $spacing-xs;
  }
  
  &__meta {
    display: flex;
    gap: $spacing-md;
    font-size: $font-size-xs;
    color: $text-secondary;
  }
}

// 标签列表
.tag-list {
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;
}

.tag-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: $spacing-sm $spacing-md;
  background: rgba($accent-color, 0.05);
  border-radius: $border-radius-sm;
  transition: all $transition-fast;
  cursor: pointer;
  
  &:hover {
    background: rgba($accent-color, 0.1);
    transform: translateX(4px);
  }
  
  &__name {
    font-weight: 500;
    color: $text-primary;
  }
  
  &__count {
    font-size: $font-size-sm;
    color: $accent-color;
    font-weight: 600;
  }
}

// 快捷入口卡片
.shortcut-card {
  @include glass-card;
  padding: $spacing-lg;
  display: flex;
  align-items: center;
  gap: $spacing-md;
  cursor: pointer;
  @include hover-lift;

  @media (max-width: $breakpoint-sm) {
    padding: $spacing-md;
    border-radius: $border-radius-md;
  }
  
  &__icon {
    width: 56px;
    height: 56px;
    @include gradient-bg;
    border-radius: $border-radius-md;
    @include flex-center;
    font-size: 28px;
  }
  
  &__content {
    flex: 1;
    
    h4 {
      font-size: $font-size-lg;
      font-weight: 600;
      color: $text-primary;
      margin-bottom: $spacing-xs;
    }
    
    p {
      font-size: $font-size-sm;
      color: $text-secondary;
    }
  }
  
  &__arrow {
    font-size: $font-size-xl;
    color: $text-muted;
    transition: transform $transition-fast;
  }
  
  &:hover &__arrow {
    transform: translateX(4px);
    color: $primary-color;
  }
}

.activity-empty {
  text-align: center;
  padding: $spacing-xl;
  color: $text-muted;
  font-size: $font-size-sm;
}

// 知识复利播报
.dashboard__insight {
  margin-bottom: $spacing-xl;
}

// 微信读书统计卡片
.dashboard__weread {
  margin-bottom: $spacing-md;
  cursor: pointer;
  @include hover-lift;
  border-left: 4px solid #07C160;
}

.weread-mini {
  display: flex;
  align-items: center;
  gap: $spacing-md;

  &__icon { display: flex; align-items: center; flex-shrink: 0; color: #07C160; }
  &__content {
    flex: 1;
    h4 { font-size: $font-size-sm; font-weight: 600; color: $text-primary; margin-bottom: 4px; }
  }
  &__stats {
    display: flex;
    gap: $spacing-md;
    font-size: $font-size-xs;
    color: $text-secondary;
    flex-wrap: wrap;
    strong { color: #07C160; font-weight: 600; margin-left: 2px; }
  }
  &__arrow { color: $text-muted; font-size: 18px; }
}

// 时光胶囊倒计时
.dashboard__capsule {
  margin-bottom: $spacing-xl;
  cursor: pointer;
  @include hover-lift;
  border-left: 4px solid #8b5cf6;
}

.capsule-countdown {
  display: flex;
  align-items: center;
  gap: $spacing-md;

  &__icon { display: flex; align-items: center; flex-shrink: 0; color: #8b5cf6; }
  &__content {
    flex: 1;
    h4 {
      font-size: $font-size-md;
      color: $text-primary;
      margin-bottom: 4px;
      strong { color: #8b5cf6; font-size: $font-size-lg; }
    }
    p {
      font-size: $font-size-sm;
      color: $text-secondary;
    }
  }
  &__stats {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: $font-size-xs;
    color: $text-muted;
    text-align: right;
  }
  &__arrow {
    font-size: $font-size-lg;
    color: $text-muted;
    transition: transform $transition-fast;
  }

  &:hover &__arrow {
    transform: translateX(4px);
    color: #8b5cf6;
  }
}

// 心愿墙卡片
.dashboard__wishlist {
  margin-bottom: $spacing-xl;
  cursor: pointer;
  @include hover-lift;
  border-left: 4px solid #F43F5E;
}

.wish-mini {
  display: flex;
  align-items: center;
  gap: $spacing-md;

  &__icon { display: flex; align-items: center; flex-shrink: 0; color: #F43F5E; }
  &__content {
    flex: 1;
    h4 { font-size: $font-size-sm; font-weight: 600; color: $text-primary; margin-bottom: 4px; }
  }
  &__stats {
    display: flex;
    gap: $spacing-md;
    font-size: $font-size-xs;
    color: $text-secondary;
    flex-wrap: wrap;
    strong { color: #F43F5E; font-weight: 600; margin-left: 2px; }
  }
  &__pending {
    color: #F59E0B;
    font-weight: 600;
  }
  &__arrow { color: $text-muted; font-size: 18px; }
}

.insight-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $spacing-md;
  padding: $spacing-xl;
  
  &__dots {
    display: flex;
    gap: 6px;
    
    span {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: linear-gradient(135deg, $primary-color, $accent-color);
      animation: insightBounce 1.4s ease-in-out infinite;
      
      &:nth-child(1) { animation-delay: 0s; }
      &:nth-child(2) { animation-delay: 0.2s; }
      &:nth-child(3) { animation-delay: 0.4s; }
    }
  }
  
  &__text {
    font-size: $font-size-sm;
    color: $text-muted;
    font-style: italic;
  }
}

.insight-content {
  &__body {
    font-size: $font-size-sm;
    line-height: 1.9;
    color: $text-secondary;
    padding: $spacing-sm 0;
    
    :deep(strong) {
      color: $text-primary;
      font-weight: 600;
    }
    
    :deep(em) {
      color: $primary-color;
      font-style: normal;
      padding: 0 2px;
    }
    
    :deep(p) {
      margin: $spacing-sm 0;
    }
    
    :deep(blockquote) {
      border-left: 3px solid $primary-color;
      padding: $spacing-xs $spacing-md;
      color: $text-secondary;
      margin: $spacing-sm 0;
      background: rgba($primary-color, 0.03);
      border-radius: 0 $border-radius-sm $border-radius-sm 0;
    }
    
    :deep(ul), :deep(ol) {
      padding-left: $spacing-lg;
      margin: $spacing-xs 0;
    }
    
    :deep(li) {
      margin-bottom: $spacing-xs;
    }
    
    :deep(code) {
      background: rgba($primary-color, 0.1);
      padding: 1px 4px;
      border-radius: 3px;
      font-size: 0.9em;
    }
  }
  
  &__meta {
    display: flex;
    gap: $spacing-sm;
    margin-top: $spacing-md;
    padding-top: $spacing-sm;
    border-top: 1px solid rgba($primary-color, 0.06);
  }
}

.insight-meta-tag {
  font-size: 11px;
  color: $text-muted;
  background: rgba($primary-color, 0.05);
  padding: 2px 8px;
  border-radius: 99px;
}

.insight-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: $spacing-sm;
  padding: $spacing-lg;
  color: $text-muted;
  
  &__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    color: $text-muted;
    opacity: 0.6;
  }
  
  p {
    font-size: $font-size-sm;
    text-align: center;
  }
}

@keyframes insightBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
