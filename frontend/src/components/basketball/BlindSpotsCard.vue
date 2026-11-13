<script setup lang="ts">
/**
 * 盲区警告卡：警示红，列表式展示重复模式
 */
defineProps<{
  blindSpots?: { title: string; evidence?: string; repeat_count: number }[] | null
}>()
</script>

<template>
  <div v-if="blindSpots && blindSpots.length" class="blind-spots">
    <div class="blind-spots__head">
      <span class="blind-spots__icon">⚠️</span>
      <span class="blind-spots__title">教练发现的盲区</span>
    </div>
    <div class="blind-spots__list">
      <div
        v-for="(bs, idx) in blindSpots"
        :key="idx"
        class="blind-spot"
      >
        <div class="blind-spot__head">
          <span class="blind-spot__title">{{ bs.title }}</span>
          <span class="blind-spot__count" v-if="bs.repeat_count > 1">第 {{ bs.repeat_count }} 次</span>
        </div>
        <div v-if="bs.evidence" class="blind-spot__evidence">
          <span class="blind-spot__evidence-label">证据：</span>{{ bs.evidence }}
        </div>
      </div>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.blind-spots {
  background: linear-gradient(135deg, rgba(220, 38, 38, 0.04), rgba(220, 38, 38, 0.08));
  border: 1px solid rgba(220, 38, 38, 0.2);
  border-radius: 12px;
  padding: 16px 20px;
  animation: bs-fade-in 0.5s ease-out 0.15s backwards;

  &__head {
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px dashed rgba(220, 38, 38, 0.25);
  }

  &__icon {
    font-size: 18px;
  }

  &__title {
    font-size: 14px;
    font-weight: 700;
    color: #DC2626;
    letter-spacing: 0.3px;
  }

  &__list {
    display: flex; flex-direction: column; gap: 12px;
  }
}

.blind-spot {
  &__head {
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px;
    margin-bottom: 4px;
  }

  &__title {
    font-size: 14px;
    font-weight: 600;
    color: #1F2937;
  }

  &__count {
    flex-shrink: 0;
    padding: 2px 8px;
    background: #DC2626;
    color: white;
    font-size: 11px;
    font-weight: 600;
    border-radius: 4px;
  }

  &__evidence {
    font-size: 12px;
    color: #64748B;
    line-height: 1.6;
    padding-left: 4px;
    border-left: 2px solid rgba(220, 38, 38, 0.3);
    padding-left: 10px;

    &-label {
      color: #94A3B8;
      font-weight: 500;
    }
  }
}

@keyframes bs-fade-in {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
