<template>
  <div class="top-nav">
    <div class="nav-left">
      <span class="app-icon">🎓</span>
      <span class="app-title">智能互动教学平台 · 学生端</span>
    </div>
    <div class="nav-right">
      <div class="backend-status" :class="backendStatusClass">
        <span class="status-dot"></span>
        {{ backendStatusText }}
      </div>
      <div class="student-info">
        <div class="avatar">
          <span>{{ (username || '学').slice(0, 1) }}</span>
        </div>
        <div class="account-actions">
          <span class="student-name">{{ username }}</span>
          <button class="logout-btn" @click="$emit('logout')">退出登录</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
/* eslint-disable no-undef */
defineProps({
  backendStatusClass: {
    type: String,
    default: 'checking'
  },
  backendStatusText: {
    type: String,
    default: '检测中'
  },
  username: {
    type: String,
    default: '学生'
  }
})

defineEmits(['logout'])
</script>

<style scoped>
.top-nav {
  height: 56px;
  background: #f7f9f8;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 22px;
  color: #1e293b;
  border-bottom: 1px solid #dee8e1;
  flex-shrink: 0;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-icon {
  font-size: 16px;
}

.app-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: #30443f;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.backend-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 999px;
  background: #e9f4eb;
  border: 1px solid #d5e6d9;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.backend-status.online {
  color: #5f7f67;
}

.backend-status.online .status-dot {
  background: #22c55e;
  animation: pulse-green 2s ease-in-out infinite;
}

@keyframes pulse-green {
  0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(34, 197, 94, 0); }
}

.backend-status.offline {
  color: #991b1b;
}

.backend-status.offline .status-dot {
  background: #ef4444;
}

.backend-status.checking {
  color: #854d0e;
}

.backend-status.checking .status-dot {
  background: #eab308;
  animation: blink 1.4s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}

.student-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #d8e4dc;
  color: #445a52;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
}

.account-actions {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
}

.student-name {
  font-size: 13px;
  font-weight: 600;
  color: #324740;
}

.logout-btn {
  background: transparent;
  border: none;
  padding: 0;
  margin-top: 2px;
  font-size: 11px;
  color: #80938b;
  cursor: pointer;
  transition: color 0.2s;
}

.logout-btn:hover {
  color: #ef4444;
  text-decoration: underline;
}
</style>