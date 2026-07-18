<template>
  <div class="modal-overlay" v-if="visible" @click="$emit('close')">
    <div class="modal-content" @click.stop>
      <div class="modal-header">
        <h3>上传课件（PPT/PDF）</h3>
        <button @click="$emit('close')" class="close-btn">×</button>
      </div>
      <div class="upload-form">
        <input
          type="file"
          ref="innerFileInput"
          accept=".ppt,.pptx,.pdf"
          @change="handleFileChange"
          class="file-input"
        />
        <div class="file-name" v-if="selectedFileName">{{ selectedFileName }}</div>
        <button @click="$emit('submit')" class="upload-submit" :disabled="!selectedFileName || uploadLoading">
          {{ uploadLoading ? '上传中...' : '上传并解析' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  selectedFileName: {
    type: String,
    default: ''
  },
  uploadLoading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close', 'select-file', 'submit', 'file-input-ready'])
const innerFileInput = ref(null)

const handleFileChange = (event) => {
  emit('select-file', event)
}

watch(innerFileInput, (value) => {
  if (value) {
    emit('file-input-ready', value)
  }
}, { immediate: true })

watch(() => props.visible, (value) => {
  if (value && innerFileInput.value) {
    emit('file-input-ready', innerFileInput.value)
  }
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-content {
  width: 420px;
  background: #fff;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 24px 50px rgba(15, 23, 42, 0.18);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 18px;
  border-bottom: 1px solid #e6ecf5;
}
.close-btn {
  border: none;
  background: transparent;
  font-size: 24px;
  cursor: pointer;
}
.upload-form {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.file-name {
  color: #334155;
  font-size: 13px;
}
.upload-submit {
  border: none;
  border-radius: 10px;
  padding: 10px 14px;
  background: #2F605A;
  color: #fff;
  cursor: pointer;
}
.upload-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>