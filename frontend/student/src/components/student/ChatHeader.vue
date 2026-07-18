<template>
  <header class="chat-header">
    <div class="chat-header-left">
      <h3>{{ activeSession?.title || '新的聊天' }}</h3>
      <p>共 {{ sessionUserTurnCount(activeSession) }} 条对话</p>
    </div>
    <div class="chat-header-actions">
      <button class="ghost-btn" type="button" @click="$emit('clear-session')" :disabled="disabled || !activeMessages.length">
        清空对话
      </button>
      <button class="ghost-btn" type="button" @click="$emit('regenerate-last')" :disabled="disabled || !hasUserMessage">
        重新生成
      </button>
    </div>
  </header>
</template>

<script setup>
/* eslint-disable no-undef */
const props = defineProps({
  activeSession: {
    type: Object,
    default: null
  },
  disabled: {
    type: Boolean,
    default: false
  },
  hasUserMessage: {
    type: Boolean,
    default: false
  }
})

defineEmits(['clear-session', 'regenerate-last'])

function sessionUserTurnCount(session) {
  if (!session || !Array.isArray(session.messages)) return 0
  return session.messages.filter((item) => item.role === 'user').length
}
</script>

<style scoped>
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.8);
  background: rgba(255, 255, 255, 0.92);
  border-radius: 12px 12px 0 0;
}

.chat-header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.chat-header h3 {
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.chat-header p {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

.chat-header-actions {
  display: flex;
  gap: 8px;
}

.ghost-btn {
  border: 1px solid rgba(148, 163, 184, 0.5);
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(12px);
  border-radius: 12px;
  padding: 8px 16px;
  color: #64748b;
  font-weight: 500;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.ghost-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(192, 228, 212, 0.8);
}

.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ghost-btn:disabled:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(148, 163, 184, 0.5);
  cursor: not-allowed;
}
</style>