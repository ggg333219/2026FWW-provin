<template>
  <main ref="threadRef" class="message-thread" aria-live="polite">
    <div v-if="!activeMessages.length" class="thread-empty">
      <p>开始你的第一条提问，例如：这一步推导为什么成立？</p>
    </div>

    <article
      v-for="message in activeMessages"
      :key="message.id"
      class="message-row"
      :class="message.role"
    >
      <div class="message-avatar" :class="message.role === 'assistant' ? 'assistant-avatar' : 'user-avatar'">
        {{ message.role === 'assistant' ? 'AI' : '我' }}
      </div>

      <div class="message-bubble" :class="{ streaming: isStreamingMessage(message), system: message.system }">
        <div class="message-meta-row">
          <span class="message-role">{{ messageRoleLabel(message) }}</span>
          <div class="message-tools">
            <button
              v-if="message.role === 'assistant' && !message.system && message.content"
              class="inline-copy-btn"
              type="button"
              @click="copyText(message.content, '消息已复制')"
            >
              复制
            </button>
            <span class="message-time">{{ formatDateTime(message.createdAt) }}</span>
          </div>
        </div>

        <div v-if="message.role === 'assistant'" class="assistant-body" :class="{ system: message.system }" @click="handleMarkdownAction">
          <div
            v-if="message.content"
            class="markdown-content"
            v-html="renderAssistantMessage(message.content)"
          ></div>
          <div v-else class="thinking-inline">
            <span>正在思考...</span>
            <i></i><i></i><i></i>
          </div>
          <div v-if="isStreamingMessage(message) && !message.system" class="streaming-state">
            <span class="typing-dot"></span>
            正在思考...
          </div>
        </div>
      </div>
    </article>
  </main>
</template>

<script setup>
/* eslint-disable no-undef */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  activeMessages: {
    type: Array,
    required: true
  },
  isStreamingMessage: {
    type: Function,
    required: true
  },
  handleMarkdownAction: {
    type: Function,
    required: true
  },
  copyText: {
    type: Function,
    required: true
  },
  formatDateTime: {
    type: Function,
    required: true
  },
  renderAssistantMessage: {
    type: Function,
    required: true
  }
})

function messageRoleLabel(message) {
  if (message.system) return '系统'
  return message.role === 'assistant' ? 'AI' : '我'
}
</script>

<style scoped>
.message-thread {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 12px;
  border: 1px solid rgba(226, 232, 240, 0.8);
  min-height: 0;
}

.thread-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px;
  text-align: center;
  color: #94a3b8;
}

.thread-empty p {
  font-size: 16px;
  line-height: 1.6;
  max-width: 400px;
  margin: 0 auto;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
  transition: all 0.3s ease;
}

.message-row:hover {
  background: rgba(241, 245, 249, 0.5);
  border-radius: 12px;
  padding: 8px;
}

.message-avatar {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-weight: 600;
  font-size: 14px;
  color: #fff;
  flex-shrink: 0;
}

.user-avatar {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
}

.assistant-avatar {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
}

.message-bubble {
  flex: 1;
  position: relative;
  border-radius: 16px;
  padding: 16px;
  max-width: 600px;
  min-width: 200px;
  background: #fff;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
  transition: all 0.3s ease;
}

.message-bubble:hover {
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.1);
}

.message-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  color: #94a3b8;
}

.message-role {
  font-weight: 600;
  color: #64748b;
}

.message-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}

.inline-copy-btn {
  border: 1px solid rgba(148, 163, 184, 0.5);
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(12px);
  border-radius: 999px;
  padding: 4px 10px;
  color: #64748b;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.inline-copy-btn:hover {
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(192, 228, 212, 0.8);
}

.message-time {
  color: #94a3b8;
}

.assistant-body {
  color: #1e293b;
  font-size: 14px;
  line-height: 1.6;
}

.thinking-inline {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #64748b;
}

.thinking-inline span {
  font-size: 14px;
}

.thinking-inline i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
  animation: dot-jump 1s ease-in-out infinite;
}

.thinking-inline i:nth-child(2) {
  animation-delay: 0.2s;
}

.thinking-inline i:nth-child(3) {
  animation-delay: 0.4s;
}

.streaming-state {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(226, 232, 240, 0.5);
  font-size: 12px;
  color: #64748b;
}

.typing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #10b981;
  animation: pulse 1.1s ease-in-out infinite;
}

.markdown-content {
  color: #1e293b;
  font-size: 14px;
  line-height: 1.6;
}

.markdown-content :deep(p) {
  margin: 0.28em 0;
}

.markdown-content :deep(pre) {
  margin: 0.55em 0;
  padding: 0;
  border-radius: 12px;
  border: 1px solid #c5dacc;
  background: #12271f;
  overflow: hidden;
}

.markdown-content :deep(code) {
  font-family: Consolas, 'Courier New', monospace;
  color: #d3ebdf;
}

.markdown-content :deep(.code-shell-head) {
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  background: linear-gradient(180deg, #1f3e33 0%, #1a332b 100%);
  border-bottom: 1px solid rgba(156, 199, 181, 0.2);
}

.markdown-content :deep(.code-lang) {
  font-size: 11px;
  color: #c2e2d4;
  text-transform: uppercase;
}

.markdown-content :deep(.code-copy-btn) {
  border: 1px solid rgba(161, 199, 182, 0.38);
  background: rgba(255, 255, 255, 0.06);
  color: #d9f0e5;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
}

.markdown-content :deep(.code-copy-btn:hover) {
  background: rgba(255, 255, 255, 0.15);
}

.markdown-content :deep(.hl-code) {
  display: block;
  padding: 10px 12px;
  overflow: auto;
  color: #d3ebdf;
}

.markdown-content :deep(.tok-key) {
  color: #8bd8b9;
}

.markdown-content :deep(.tok-string) {
  color: #f6cf9a;
}

.markdown-content :deep(.tok-comment) {
  color: #8eb1a2;
}

.markdown-content :deep(.tok-num) {
  color: #b5f0ce;
}

.markdown-content :deep(.tok-bool) {
  color: #d9f0e5;
}

/* 滚动条样式 */
.message-thread::-webkit-scrollbar {
  width: 8px;
}

.message-thread::-webkit-scrollbar-track {
  background: transparent;
}

.message-thread::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.3);
  border-radius: 999px;
}

.message-thread::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.5);
}
</style>