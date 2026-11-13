import { createRouter, createWebHashHistory, RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  // ==================== 首页 → 日历规划 ====================
  {
    path: '/',
    name: 'Home',
    redirect: '/todo/calendar',
  },

  // ==================== 读书模块 ====================
  {
    path: '/reading',
    name: 'Dashboard',
    component: () => import('./views/Dashboard.vue'),
    meta: { title: '总览', system: 'reading' }
  },
  {
    path: '/timeline',
    name: 'TimelineView',
    component: () => import('./views/TimelineView.vue'),
    meta: { title: '阅读时间线', system: 'reading' }
  },
  {
    path: '/models',
    name: 'ModelsView',
    component: () => import('./views/ModelsView.vue'),
    meta: { title: '思维模型', system: 'reading' }
  },
  {
    path: '/knowledge',
    name: 'KnowledgeView',
    component: () => import('./views/KnowledgeView.vue'),
    meta: { title: '知识分类', system: 'reading' }
  },
  
  // ==================== 投资模块 ====================
  {
    path: '/investment',
    name: 'InvestmentDashboard',
    component: () => import('./views/investment/InvestDashboard.vue'),
    meta: { title: '投资总览', system: 'investment' }
  },
  {
    path: '/investment/principles',
    name: 'InvestmentPrinciples',
    component: () => import('./views/investment/PrinciplesView.vue'),
    meta: { title: '投资原则', system: 'investment' }
  },
  {
    path: '/investment/cognitions',
    name: 'InvestmentCognitions',
    component: () => import('./views/investment/CognitionsView.vue'),
    meta: { title: '认知迭代', system: 'investment' }
  },
  {
    path: '/investment/decisions',
    name: 'InvestmentDecisions',
    component: () => import('./views/investment/DecisionsView.vue'),
    meta: { title: '决策日志', system: 'investment' }
  },
  {
    path: '/investment/emotions',
    name: 'InvestmentEmotions',
    component: () => import('./views/investment/EmotionsView.vue'),
    meta: { title: '情绪复盘', system: 'investment' }
  },
  {
    path: '/investment/knowledge',
    name: 'InvestmentKnowledge',
    component: () => import('./views/investment/KnowledgeView.vue'),
    meta: { title: '投资知识', system: 'investment' }
  },
  {
    path: '/investment/qa',
    name: 'InvestmentQA',
    component: () => import('./views/investment/QAView.vue'),
    meta: { title: 'Q&A 问答', system: 'investment' }
  },

  // ==================== 日记模块 ====================
  {
    path: '/diary',
    name: 'DiaryDashboard',
    component: () => import('./views/diary/DiaryDashboard.vue'),
    meta: { title: '日记总览', system: 'diary' }
  },
  {
    path: '/diary/list',
    name: 'DiaryList',
    component: () => import('./views/diary/DiaryList.vue'),
    meta: { title: '日记列表', system: 'diary' }
  },
  {
    path: '/diary/:id',
    name: 'DiaryDetail',
    component: () => import('./views/diary/DiaryDetail.vue'),
    meta: { title: '日记详情', system: 'diary' }
  },

  // ==================== 娱乐模块 ====================
  {
    path: '/entertainment',
    name: 'Entertainment',
    component: () => import('./views/EntertainmentView.vue'),
    meta: { title: '娱乐', system: 'entertainment' }
  },

  // ==================== 待办模块 ====================
  {
    path: '/todo',
    name: 'TodoDashboard',
    component: () => import('./views/todo/TodoDashboard.vue'),
    meta: { title: '待办总览', system: 'todo' }
  },
  {
    path: '/todo/inbox',
    redirect: { path: '/assistant', query: { prefill: '/任务单 ' } },
  },
  {
    path: '/todo/list',
    name: 'TodoList',
    component: () => import('./views/todo/TodoList.vue'),
    meta: { title: '全部待办', system: 'todo' }
  },
  {
    path: '/todo/review',
    name: 'TodoReview',
    component: () => import('./views/todo/TodoReview.vue'),
    meta: { title: '总结报告', system: 'todo' }
  },
  {
    path: '/todo/calendar',
    name: 'TodoCalendar',
    component: () => import('./views/todo/TodoCalendar.vue'),
    meta: { title: '日历规划', system: 'todo' }
  },
  {
    path: '/todo/habits',
    name: 'TodoHabits',
    component: () => import('./views/todo/TodoHabits.vue'),
    meta: { title: '习惯追踪', system: 'todo' }
  },

  // ==================== 知识库模块 ====================
  {
    path: '/kb',
    name: 'KBDashboard',
    component: () => import('./views/kb/KBDashboard.vue'),
    meta: { title: '知识库总览', system: 'kb' }
  },
  {
    path: '/kb/list',
    name: 'KBList',
    component: () => import('./views/kb/KBList.vue'),
    meta: { title: '知识库列表', system: 'kb' }
  },
  {
    path: '/kb/:id',
    name: 'KBDetail',
    component: () => import('./views/kb/KBDetail.vue'),
    meta: { title: '知识详情', system: 'kb' }
  },

  // ==================== AI 对话 ====================
  {
    path: '/assistant',
    name: 'Assistant',
    component: () => import('./views/chat/AgentChatView.vue'),
    meta: { title: 'AI 助手', system: 'chat' }
  },
  {
    // 旧分析页已并入统一 AI 助手页，所有 /chat 访问重定向（保留 query 如 prompt/prefill）
    path: '/chat',
    redirect: (to) => ({ path: '/assistant', query: to.query }),
  },

  // ==================== 心力模块（成就 + 感恩） ====================
  {
    path: '/wellbeing',
    name: 'WellbeingDashboard',
    component: () => import('./views/wellbeing/WellbeingDashboard.vue'),
    meta: { title: '心力总览', system: 'wellbeing' }
  },
  {
    path: '/wellbeing/list',
    name: 'WellbeingList',
    component: () => import('./views/wellbeing/WellbeingList.vue'),
    meta: { title: '心力列表', system: 'wellbeing' }
  },
  {
    path: '/wellbeing/candidates',
    name: 'WellbeingCandidates',
    component: () => import('./views/wellbeing/WellbeingCandidates.vue'),
    meta: { title: '候选审核', system: 'wellbeing' }
  },
  {
    path: '/wellbeing/reports',
    name: 'WellbeingReports',
    component: () => import('./views/wellbeing/WellbeingReports.vue'),
    meta: { title: '周月报', system: 'wellbeing' }
  },
  {
    path: '/wellbeing/anxiety',
    name: 'AnxietyMode',
    component: () => import('./views/wellbeing/AnxietyMode.vue'),
    meta: { title: '焦虑模式', system: 'wellbeing' }
  },

  // ==================== 篮球反思模块 ====================
  {
    path: '/basketball',
    name: 'BasketballDashboard',
    component: () => import('./views/basketball/BasketballDashboard.vue'),
    meta: { title: '篮球反思总览', system: 'basketball' }
  },
  {
    path: '/basketball/new',
    name: 'BasketballNew',
    component: () => import('./views/basketball/BasketballNew.vue'),
    meta: { title: '新建复盘', system: 'basketball' }
  },
  {
    path: '/basketball/list',
    name: 'BasketballList',
    component: () => import('./views/basketball/BasketballList.vue'),
    meta: { title: '复盘列表', system: 'basketball' }
  },
  {
    path: '/basketball/goals',
    name: 'BasketballGoals',
    component: () => import('./views/basketball/BasketballGoals.vue'),
    meta: { title: '阶段目标', system: 'basketball' }
  },
  {
    path: '/basketball/:id',
    name: 'BasketballDetail',
    component: () => import('./views/basketball/BasketballDetail.vue'),
    meta: { title: '复盘详情', system: 'basketball' }
  },

  // ==================== AI 设置 ====================
  {
    path: '/settings',
    name: 'SettingsView',
    component: () => import('./views/settings/SettingsView.vue'),
    meta: { title: '系统设置', system: 'settings' }
  },

  // ==================== 时光胶囊模块 ====================
  {
    path: '/time-capsule',
    name: 'TimeCapsuleList',
    component: () => import('./views/timeCapsule/CapsuleList.vue'),
    meta: { title: '时光胶囊', system: 'timeCapsule' }
  },
  {
    path: '/time-capsule/write',
    name: 'TimeCapsuleWrite',
    component: () => import('./views/timeCapsule/CapsuleWrite.vue'),
    meta: { title: '写信', system: 'timeCapsule' }
  },
  {
    path: '/time-capsule/:id',
    name: 'TimeCapsuleDetail',
    component: () => import('./views/timeCapsule/CapsuleDetail.vue'),
    meta: { title: '信件详情', system: 'timeCapsule' }
  },

  // ==================== 微信读书模块 ====================
  {
    path: '/weread',
    name: 'WeRead',
    component: () => import('./views/weread/WeReadSync.vue'),
    meta: { title: '微信读书', system: 'reading' }
  },

  // ==================== 审批中心模块 ====================
  {
    path: '/review',
    name: 'ReviewDashboard',
    component: () => import('./views/review/ReviewDashboard.vue'),
    meta: { title: '审批中心', system: 'review' }
  },

  // ==================== 心愿清单模块 ====================
  {
    path: '/wishlist',
    name: 'WishlistView',
    component: () => import('./views/wishlist/WishlistView.vue'),
    meta: { title: '心愿清单', system: 'wishlist' }
  },
  {
    path: '/wishlist/:id',
    name: 'WishDetail',
    component: () => import('./views/wishlist/WishDetail.vue'),
    meta: { title: '心愿详情', system: 'wishlist' }
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach((to, _from, next) => {
  const systemNames: Record<string, string> = {
    reading: '读书',
    investment: '投资',
    diary: '日记',
    entertainment: '娱乐',
    todo: '待办',
    kb: '知识库',
    wellbeing: '心力',
    basketball: '篮球反思',
    chat: 'AI 对话',
    settings: '设置',
    timeCapsule: '时光胶囊',
    weread: '微信读书',
    wishlist: '心愿清单',
    review: '审批中心',
  }
  const system = systemNames[to.meta.system as string] || 'Daily'
  document.title = `${to.meta.title || '总览'} - Daily ${system}`
  next()
})

export default router
