<template>
  <div class="top-nav">
    <div class="nav-left">
      <span class="app-icon">🎓</span>
      <span class="app-title">智能互动教学平台 · 教师端</span>
    </div>
    <div class="nav-right">
      <div class="backend-status" :class="backendStatusClass">
        <span class="status-dot"></span>
        {{ backendStatusText }}
      </div>
      <div class="platform-status" :class="platformStatusClass">
        <span class="status-dot"></span>
        {{ platformStatusText }}
      </div>
      <div class="teacher-info">
        <div class="avatar">
          <span>{{ (username || '教').slice(0, 1) }}</span>
        </div>
        <div class="account-actions">
          <span class="teacher-name">{{ username }}</span>
          <button class="logout-btn" @click="$emit('logout')">退出登录</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  backendStatusClass: {
    type: String,
    default: 'checking'
  },
  backendStatusText: {
    type: String,
    default: '检测中'
  },
  platformStatusClass: {
    type: String,
    default: 'checking'
  },
  platformStatusText: {
    type: String,
    default: '泛雅开放平台已接通'
  },
  username: {
    type: String,
    default: '教师'
  }
})

defineEmits(['logout'])
</script>

<style scoped>
.top-nav {
  --tb-bg: rgba(255, 255, 255, 0.86);
  --tb-border: rgba(120, 156, 140, 0.22);
  --tb-text: #111827;
  --tb-muted: #5f7467;
  --tb-accent: #5ca68f;

  height: 62px;
  margin: 0;
  border-radius: 0;
  background: var(--tb-bg);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 0;
  border-bottom: 1px solid var(--tb-border);
  box-shadow: none;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
  color: var(--tb-text);
  flex-shrink: 0;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.app-icon {
  width: 28px;
  height: 28px;
  border-radius: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  background: linear-gradient(180deg, #ecf8f3 0%, #ddf1e8 100%);
  color: #2f6052;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.app-title {
  font-size: 15px;
  font-weight: 650;
  letter-spacing: 0.01em;
  color: #111827;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.backend-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(248, 250, 252, 0.88);
  border: 0;
}

.platform-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(236, 248, 243, 0.95);
  border: 0;
  color: #2f6052;
}

.platform-status .status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #14b8a6;
  animation: pulse-platform 2.2s ease-in-out infinite;
}

@keyframes pulse-platform {
  0%, 100% { box-shadow: 0 0 0 0 rgba(20, 184, 166, 0.38); }
  50% { box-shadow: 0 0 0 5px rgba(20, 184, 166, 0); }
}

.platform-status.checking {
  color: #2f6052;
}

.platform-status.checking .status-dot {
  background: #5ca68f;
  animation: blink 1.4s ease-in-out infinite;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.backend-status.online {
  color: #047857;
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
  color: #b91c1c;
}

.backend-status.offline .status-dot {
  background: #ef4444;
}

.backend-status.checking {
  color: #2f6052;
}

.backend-status.checking .status-dot {
  background: var(--tb-accent);
  animation: blink 1.4s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.25; }
}

.teacher-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.96);
  border: 0;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(180deg, #ecf8f3 0%, #dfeee7 100%);
  color: #334155;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
}

.account-actions {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
}

.teacher-name {
  font-size: 13px;
  font-weight: 650;
  color: #1f2937;
}

.logout-btn {
  background: transparent;
  border: none;
  padding: 0;
  margin-top: 2px;
  font-size: 11px;
  color: var(--tb-muted);
  cursor: pointer;
  transition: color 0.2s;
}

.logout-btn:hover {
  color: var(--tb-accent);
  text-decoration: underline;
}
</style>