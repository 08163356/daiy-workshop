<script setup lang="ts">
defineProps<{
  work: boolean
  markDone: boolean
  aiEval: boolean
}>()

const emit = defineEmits<{
  'update:work': [value: boolean]
  'update:markDone': [value: boolean]
  'update:aiEval': [value: boolean]
}>()
</script>

<template>
  <div class="task-extras">
    <label class="task-extra">
      <input
        type="checkbox"
        :checked="work"
        @change="emit('update:work', ($event.target as HTMLInputElement).checked)"
      />
      <span>工作任务</span>
    </label>
    <label class="task-extra">
      <input
        type="checkbox"
        :checked="markDone"
        @change="emit('update:markDone', ($event.target as HTMLInputElement).checked)"
      />
      <span>创建后标记完成</span>
    </label>
    <label class="task-extra">
      <input
        type="checkbox"
        :checked="aiEval"
        @change="emit('update:aiEval', ($event.target as HTMLInputElement).checked)"
      />
      <span>创建后进行 AI 评估</span>
    </label>
  </div>
</template>

<style scoped>
.task-extras {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
}

.task-extra {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #475569;
  font-size: 13px;
  cursor: pointer;
  user-select: none;
}

.task-extra input {
  width: 15px;
  height: 15px;
  accent-color: #6366f1;
}
</style>
