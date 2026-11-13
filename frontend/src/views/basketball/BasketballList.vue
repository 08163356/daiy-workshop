<script setup lang="ts">
/**
 * 复盘列表流
 */
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useBasketballStore } from '@/stores/useBasketballStore'
import { SKILL_DIMENSIONS } from '@/config/basketballSkills'

const router = useRouter()
const store = useBasketballStore()

const filters = ref({
  type: '',
  skill: '',
  keyword: '',
})

async function reload() {
  await store.fetchSessions({
    type: filters.value.type || undefined,
    skill: filters.value.skill || undefined,
    keyword: filters.value.keyword || undefined,
    limit: 100,
  })
}

watch(() => [filters.value.type, filters.value.skill], reload)

let kwTimer: any = null
watch(() => filters.value.keyword, () => {
  if (kwTimer) clearTimeout(kwTimer)
  kwTimer = setTimeout(reload, 500)
})

onMounted(reload)

function fmtType(t: string) { return t === 'match' ? '比赛' : '散场' }
</script>

<template>
  <div class="bb-list">
    <header class="bb-list__head">
      <h1 class="bb-list__title">📋 复盘历史</h1>
      <button class="bb-list__write" @click="router.push('/basketball/new')">+ 写新复盘</button>
    </header>

    <!-- 筛选条 -->
    <div class="bb-list__filters">
      <div class="bb-list__tabs">
        <button class="bb-list__tab" :class="{ 'bb-list__tab--active': filters.type === '' }" @click="filters.type = ''">全部</button>
        <button class="bb-list__tab" :class="{ 'bb-list__tab--active': filters.type === 'pickup' }" @click="filters.type = 'pickup'">🏃 散场</button>
        <button class="bb-list__tab" :class="{ 'bb-list__tab--active': filters.type === 'match' }" @click="filters.type = 'match'">🏆 比赛</button>
      </div>
      <select v-model="filters.skill" class="bb-list__select">
        <option value="">所有技术维度</option>
        <option v-for="d in SKILL_DIMENSIONS" :key="d" :value="d">{{ d }}</option>
      </select>
      <input
        v-model="filters.keyword"
        type="text"
        class="bb-list__search"
        placeholder="搜索一句话总结/亮点/问题/对手..."
      />
    </div>

    <!-- 列表 -->
    <div v-if="store.loading" class="bb-list__loading">加载中…</div>
    <div v-else-if="!store.sessions.length" class="bb-list__empty">
      <span class="bb-list__empty-icon">🏀</span>
      <p>还没有复盘记录</p>
      <button class="bb-list__write" @click="router.push('/basketball/new')">写第一篇 →</button>
    </div>
    <div v-else class="bb-list__items">
      <div
        v-for="s in store.sessions"
        :key="s.id"
        class="bb-list__card"
        @click="router.push(`/basketball/${s.id}`)"
      >
        <div class="bb-list__card-head">
          <span class="bb-list__card-date">{{ s.date }}</span>
          <span class="bb-list__card-type" :class="{ 'bb-list__card-type--match': s.type === 'match' }">{{ fmtType(s.type) }}</span>
          <span v-if="s.duration_min" class="bb-list__card-meta">⏱ {{ s.duration_min }}min</span>
          <span v-if="s.shots_attempted" class="bb-list__card-meta">🎯 {{ s.shots_made }}/{{ s.shots_attempted }}</span>
          <span class="bb-list__card-meta bb-list__card-meta--int">{{ '★'.repeat(s.intensity) }}</span>
        </div>
        <div class="bb-list__card-line">{{ s.one_line_summary }}</div>
        <div v-if="s.coach_review" class="bb-list__card-coach">
          <span class="bb-list__card-coach-tag">教练点评</span>
          <span>{{ s.coach_review.split('\n')[0].slice(0, 80) }}…</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.bb-list {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px;
  display: flex; flex-direction: column; gap: 18px;
  background: linear-gradient(180deg, #FAF7F2 0%, #FFFFFF 200px);
  min-height: 100%;
}

.bb-list__head {
  display: flex; justify-content: space-between; align-items: center;
}

.bb-list__title {
  font-size: 22px; font-weight: 700; color: #1F2937; margin: 0;
}

.bb-list__write {
  background: linear-gradient(135deg, #D97706, #B45309);
  color: white;
  border: none;
  border-radius: 8px;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  &:hover { transform: translateY(-1px); }
}

.bb-list__filters {
  display: flex; gap: 12px; flex-wrap: wrap;
  background: white;
  padding: 14px 18px;
  border-radius: 12px;
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.bb-list__tabs {
  display: flex; gap: 4px;
  background: #F8FAFC;
  border-radius: 8px;
  padding: 4px;
}

.bb-list__tab {
  background: transparent;
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 13px;
  color: #64748B;
  cursor: pointer;
  font-family: inherit;

  &--active {
    background: white;
    color: #D97706;
    font-weight: 600;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }
}

.bb-list__select,
.bb-list__search {
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
  background: white;
  outline: none;
  font-family: inherit;
  color: #1F2937;

  &:focus { border-color: #D97706; }
}

.bb-list__search { flex: 1; min-width: 200px; }

.bb-list__items {
  display: flex; flex-direction: column; gap: 10px;
}

.bb-list__card {
  background: white;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 12px;
  padding: 14px 18px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    transform: translateX(4px);
    border-color: rgba(217, 119, 6, 0.3);
    box-shadow: 0 8px 20px rgba(217, 119, 6, 0.06);
  }

  &-head {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }

  &-date {
    font-family: ui-monospace, monospace;
    font-size: 13px;
    color: #1F2937;
    font-weight: 600;
  }

  &-type {
    padding: 2px 8px;
    background: #D97706;
    color: white;
    font-size: 11px;
    font-weight: 600;
    border-radius: 4px;

    &--match { background: #DC2626; }
  }

  &-meta {
    font-size: 11px;
    color: #94A3B8;

    &--int { color: #D97706; }
  }

  &-line {
    font-size: 14px;
    color: #1F2937;
    line-height: 1.6;
  }

  &-coach {
    margin-top: 8px;
    padding: 8px 12px;
    background: rgba(30, 64, 175, 0.04);
    border-left: 2px solid #1E40AF;
    border-radius: 4px;
    font-size: 12px;
    color: #475569;
    line-height: 1.5;
    display: flex; gap: 8px; align-items: baseline;

    &-tag {
      flex-shrink: 0;
      padding: 1px 6px;
      background: #1E40AF;
      color: white;
      font-size: 10px;
      border-radius: 3px;
      font-weight: 600;
    }
  }
}

.bb-list__loading,
.bb-list__empty {
  text-align: center;
  padding: 50px 20px;
  color: #94A3B8;
}

.bb-list__empty-icon {
  font-size: 48px;
  display: block;
  margin-bottom: 12px;
}

.bb-list__empty p {
  margin: 0 0 16px 0;
}
</style>
