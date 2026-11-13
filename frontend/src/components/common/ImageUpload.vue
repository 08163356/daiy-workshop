<script setup lang="ts">
/**
 * 通用图片上传组件
 * - 支持点击上传、拖拽上传
 * - 手机端支持拍照/相册
 * - 预览已上传图片，支持删除
 * - 最多9张
 */
import { ref, computed } from 'vue'
import { API_BASE } from '@/config'

const props = defineProps<{
  modelValue: string[]  // 已上传的图片URL列表
  max?: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void
}>()

const maxCount = computed(() => props.max || 9)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement>()

const canAdd = computed(() => props.modelValue.length < maxCount.value && !uploading.value)

const triggerUpload = () => {
  fileInput.value?.click()
}

const handleFiles = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return

  const files = Array.from(input.files).slice(0, maxCount.value - props.modelValue.length)
  if (!files.length) return

  uploading.value = true
  try {
    const formData = new FormData()
    files.forEach(f => formData.append('files', f))

    const res = await fetch(`${API_BASE}/api/uploads/images`, {
      method: 'POST',
      body: formData,
    })

    if (res.ok) {
      const data = await res.json()
      const newUrls = (data.images || []).map((img: any) => img.url)
      emit('update:modelValue', [...props.modelValue, ...newUrls])
    }
  } catch (e) {
    console.error('图片上传失败:', e)
  } finally {
    uploading.value = false
    // 清空 input 以允许重复选择同一文件
    if (input) input.value = ''
  }
}

const removeImage = (index: number) => {
  const updated = [...props.modelValue]
  updated.splice(index, 1)
  emit('update:modelValue', updated)
}

const getFullUrl = (url: string) => {
  if (url.startsWith('http')) return url
  return `${API_BASE}${url}`
}

// 预览大图
const previewUrl = ref('')
const showPreview = ref(false)
const openPreview = (url: string) => {
  previewUrl.value = getFullUrl(url)
  showPreview.value = true
}
</script>

<template>
  <div class="img-upload">
    <!-- 已上传图片列表 -->
    <div class="img-upload__list">
      <div
        v-for="(url, idx) in modelValue"
        :key="url"
        class="img-upload__item"
      >
        <img :src="getFullUrl(url)" alt="" @click="openPreview(url)" />
        <button class="img-upload__remove" @click.stop="removeImage(idx)">×</button>
      </div>

      <!-- 上传按钮 -->
      <div
        v-if="canAdd"
        class="img-upload__add"
        @click="triggerUpload"
      >
        <span v-if="uploading" class="img-upload__spinner"></span>
        <template v-else>
          <span class="img-upload__plus">+</span>
          <span class="img-upload__label">上传图片</span>
        </template>
      </div>
    </div>

    <!-- 隐藏的 file input -->
    <input
      ref="fileInput"
      type="file"
      accept="image/*"
      multiple
      capture="environment"
      class="img-upload__input"
      @change="handleFiles"
    />

    <!-- 图片预览弹窗 -->
    <Teleport to="body">
      <div v-if="showPreview" class="img-preview-overlay" @click="showPreview = false">
        <img :src="previewUrl" class="img-preview-overlay__img" @click.stop />
      </div>
    </Teleport>
  </div>
</template>

<style lang="scss" scoped>
.img-upload {
  &__list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  &__item {
    position: relative;
    width: 80px;
    height: 80px;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid rgba(0, 0, 0, 0.08);

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      cursor: pointer;
    }
  }

  &__remove {
    position: absolute;
    top: 2px;
    right: 2px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.6);
    color: white;
    border: none;
    font-size: 14px;
    line-height: 1;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;

    &:hover {
      background: rgba(239, 68, 68, 0.9);
    }
  }

  &__add {
    width: 80px;
    height: 80px;
    border-radius: 8px;
    border: 2px dashed rgba(0, 0, 0, 0.15);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s;
    background: rgba(0, 0, 0, 0.02);

    &:hover {
      border-color: #EC4899;
      background: rgba(236, 72, 153, 0.04);
    }
  }

  &__plus {
    font-size: 24px;
    color: #94A3B8;
    line-height: 1;
  }

  &__label {
    font-size: 10px;
    color: #94A3B8;
    margin-top: 2px;
  }

  &__spinner {
    width: 20px;
    height: 20px;
    border: 2px solid #e2e8f0;
    border-top-color: #EC4899;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  &__input {
    display: none;
  }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

// 预览弹窗
.img-preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  cursor: pointer;

  &__img {
    max-width: 90vw;
    max-height: 90vh;
    object-fit: contain;
    border-radius: 4px;
    cursor: default;
  }
}

// 移动端放大触控区域
@media (max-width: 768px) {
  .img-upload {
    &__item, &__add {
      width: 72px;
      height: 72px;
    }
    &__remove {
      width: 24px;
      height: 24px;
      font-size: 16px;
    }
  }
}
</style>
