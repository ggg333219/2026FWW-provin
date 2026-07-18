<template>
  <section class="composer">
    <div class="composer-input">
      <el-textarea
        v-model="messageContent"
        :rows="rows"
        placeholder="输入你的问题..."
        @change="handleInputChange"
        @keydown.enter.exclusive="handleSend"
        @keydown.shift.enter="handleNewLine"
        @focus="handleFocus"
        @blur="handleBlur"
      />
    </div>

    <div class="composer-actions">
      <span class="compose-tip">{{ askLoading || streamTypingActive ? 'AI 正在回答中' : 'Enter 发送，Shift + Enter 换行' }}</span>
      <el-button
        type="primary"
        class="send-btn"
        :disabled="sendDisabled"
        :loading="askLoading"
        @click="handleSend"
      >
        发送
      </el-button>
    </div>
  </section>
</template>

<script setup>
/* eslint-disable no-undef */
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  askLoading: {
    type: Boolean,
    default: false
  },
  streamTypingActive: {
    type: Boolean,
    default: false
  },
  sendDisabled: {
    type: Boolean,
    default: false
  },
  handleSend: {
    type: Function,
    required: true
  },
  handleNewLine: {
    type: Function,
    required: true
  },
  handleInputChange: {
    type: Function,
    required: true
  },
  handleFocus: {
    type: Function,
    required: true
  },
  handleBlur: {
    type: Function,
    required: true
  }
})

const messageContent = ref('')
const rows = computed(() => {
  return messageContent.value.length > 0 ? 4 : 2
})
</script>

<style scoped>
.composer {
  margin-top: 16px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(226, 232, 240, 0.8);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.composer-input {
  flex: 1;
}

.composer-input :deep(.el-textarea__inner) {
  border-radius: 12px;
  border-color: rgba(148, 163, 184, 0.5);
  line-height: 1.65;
  resize: none;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.compose-tip {
  font-size: 12px;
  color: #64748b;
}

.send-btn {
  min-width: 96px;
  border-radius: 12px;
  font-weight: 700;
  font-size: 14px;
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.send-btn:disabled:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(148, 163, 184, 0.5);
  cursor: not-allowed;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: rgba(16, 185, 129, 0.1);
  border-color: rgba(16, 185, 129, 0.8);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.15);
}
</style>