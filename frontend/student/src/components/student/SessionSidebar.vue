<template>
  <aside class="session-sidebar">
    <button class="new-session-btn" type="button" @click="$emit('create-new')" :disabled="disabled">
      + 新建对话
    </button>

    <div class="session-list" role="listbox" aria-label="会话列表">
      <div
        v-for="session in sessions"
        :key="session.id"
        class="session-item"
        :class="{ active: session.id === activeSessionId }"
        @click="$emit('switch-session', session.id)"
        @contextmenu.prevent="$emit('delete-session', session.id)"
      >
        <div class="session-item-head">
          <strong class="session-title" :title="session.title">{{ session.title }}</strong>
          <button
            class="session-delete-btn"
            type="button"
            title="删除对话"
            aria-label="删除对话"
            @click.stop="$emit('delete-session', session.id)"
          >
            ×
          </button>
        </div>
        <p class="session-preview" :title="session.preview || '暂无消息'">{{ session.preview || '暂无消息' }}</p>
        <div class="session-meta">
          <span>{{ sessionUserTurnCount(session) }} 条对话</span>
          <span>{{ formatDateTime(session.updatedAt) }}</span>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
/* eslint-disable no-undef */
const props = defineProps({
  sessions: {
    type: Array,
    required: true
  },
  activeSessionId: {
    type: String,
    required: true
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

defineEmits(['create-new', 'switch-session', 'delete-session'])

function sessionUserTurnCount(session) {
  if (!session || !Array.isArray(session.messages)) return 0
  return session.messages.filter((item) => item.role === 'user').length
}

function formatDateTime(timestamp) {
  const time = Number(timestamp) || 0
  const date = new Date(time)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}`
}
</script>

<style scoped>
.session-sidebar {
  width: 280px;
  min-width: 280px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.92);
  padding: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.new-session-btn {
  width: 100%;
  border: 1px solid rgba(157, 208, 188, 0.5);
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(12px);
  border-radius: 12px;
  padding: 12px;
  color: var(--app-brand, #10b981);
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 16px;
}

.new-session-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(192, 228, 212, 0.8);
}

.new-session-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 4px;
}

.session-item {
  border-radius: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(226, 232, 240, 0.8);
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.85);
  border-color: rgba(148, 163, 184, 0.3);
  transform: translateX(2px);
}

.session-item.active {
  background: rgba(255, 255, 255, 0.95);
  border-color: var(--app-brand, #10b981);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.15);
}

.session-item-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 6px;
}

.session-title {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  flex: 1;
  min-width: 0;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.session-delete-btn {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 999px;
  border: none;
  background: rgba(148, 163, 184, 0.2);
  color: #64748b;
  font-size: 16px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.session-delete-btn:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.session-preview {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 32px;
}

.session-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  font-size: 11px;
  color: #94a3b8;
}

.session-meta span {
  background: rgba(241, 245, 249, 0.8);
  padding: 2px 8px;
  border-radius: 999px;
  white-space: nowrap;
}

/* 滚动条样式 */
.session-list::-webkit-scrollbar {
  width: 6px;
}

.session-list::-webkit-scrollbar-track {
  background: transparent;
}

.session-list::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.3);
  border-radius: 999px;
}

.session-list::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.5);
}
</style>