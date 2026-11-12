<template>
  <header class="top-nav">
    <div class="top-nav__inner">
      <div class="nav-left">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 8.5 12 4l9 4.5-9 4.5-9-4.5Z" />
            <path d="M7 10.8v4.4c0 1.4 2.2 2.6 5 2.6s5-1.2 5-2.6v-4.4" />
            <path d="M21 8.5v5.2" />
          </svg>
        </span>
        <span class="app-title">智能互动教学平台</span>
        <span class="nav-divider" aria-hidden="true"></span>
        <span class="nav-context">教师工作台</span>
      </div>

      <div class="nav-right">
        <div v-if="platformStatusText" class="platform-status" :class="platformStatusClass" :title="platformStatusText">
          <span class="status-dot"></span>
          <span class="platform-status__text">{{ platformStatusText }}</span>
        </div>

        <div class="backend-status" :class="backendStatusClass" role="status" :aria-label="backendStatusText">
          <span class="status-dot" aria-hidden="true"></span>
          <span class="backend-status__text">{{ backendStatusText }}</span>
        </div>

        <span class="nav-divider" aria-hidden="true"></span>

        <div class="teacher-info">
          <span class="avatar" aria-hidden="true">{{ (username || '教').slice(0, 1) }}</span>
          <span class="teacher-name">{{ username }}</span>
        </div>

        <button class="logout-btn" type="button" @click="$emit('logout')">退出登录</button>
      </div>
    </div>
  </header>
</template>

<script setup>
defineProps({
  backendStatusClass: { type: String, default: 'checking' },
  backendStatusText: { type: String, default: '检测中' },
  platformStatusClass: { type: String, default: 'checking' },
  platformStatusText: { type: String, default: '' },
  username: { type: String, default: '用户' }
})

defineEmits(['logout'])
</script>

<style scoped>
.top-nav {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  height: var(--topbar-height);
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-xs);
}

.top-nav__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  height: 100%;
  max-width: var(--content-max);
  margin: 0 auto;
  padding: 0 var(--shell-gutter);
}

.nav-left,
.nav-right {
  display: flex;
  align-items: center;
  min-width: 0;
}

.nav-left { gap: var(--space-2); flex-shrink: 0; }
.nav-right { gap: var(--space-3); }

.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: var(--radius-control);
  background: var(--color-primary);
  color: var(--color-on-primary);
  flex-shrink: 0;
}

.app-title {
  font-size: var(--text-md);
  font-weight: var(--weight-semibold);
  letter-spacing: 0.01em;
  color: var(--text-primary);
  white-space: nowrap;
}

.nav-divider {
  width: 1px;
  height: 18px;
  margin: 0 var(--space-1);
  background: var(--border-subtle);
  flex-shrink: 0;
}

.nav-context {
  font-size: var(--text-2xs);
  color: var(--text-tertiary);
  white-space: nowrap;
}

.backend-status,
.platform-status {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 28px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--bg-subtle);
  color: var(--text-secondary);
  font-size: var(--text-2xs);
  font-weight: var(--weight-medium);
  white-space: nowrap;
}

.platform-status {
  max-width: 240px;
  border-color: transparent;
  background: transparent;
  color: var(--text-tertiary);
}
.platform-status__text { overflow: hidden; text-overflow: ellipsis; }

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  background: var(--text-disabled);
}

.backend-status.online { color: var(--color-success); background: var(--color-success-soft); border-color: var(--color-primary-border); }
.backend-status.online .status-dot { background: var(--color-success); }
.backend-status.offline { color: var(--color-danger); background: var(--color-danger-soft); border-color: var(--color-danger-border); }
.backend-status.offline .status-dot { background: var(--color-danger); }
.backend-status.demo { color: var(--color-warning); background: var(--color-warning-soft); border-color: var(--color-warning-border); }
.backend-status.demo .status-dot { background: var(--color-warning); }
.backend-status.checking .status-dot,
.platform-status.checking .status-dot { animation: tb-pulse 1.8s ease-in-out infinite; }
@keyframes tb-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(47, 96, 90, 0.28); }
  50% { box-shadow: 0 0 0 4px rgba(47, 96, 90, 0); }
}
.platform-status.online .status-dot { background: var(--brand-400); }

.teacher-info {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  flex-shrink: 0;
}

.teacher-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--text-xs);
  font-weight: var(--weight-medium);
  color: var(--text-primary);
  white-space: nowrap;
}

.logout-btn {
  min-height: 30px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: var(--text-2xs);
  font-weight: var(--weight-medium);
  white-space: nowrap;
  transition: border-color var(--duration-fast) var(--ease-standard),
              color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}
.logout-btn:hover { border-color: var(--color-primary-border); color: var(--color-primary); background: var(--color-primary-soft); }

@media (max-width: 1279px) {
  .platform-status { display: none; }
}
@media (max-width: 1023px) {
  .nav-context, .nav-left .nav-divider { display: none; }
}
@media (max-width: 767px) {
  .top-nav__inner { padding: 0 var(--space-3); gap: var(--space-2); }
  .app-title { font-size: var(--text-sm); }
  .nav-right { gap: var(--space-2); }
  .teacher-name, .nav-right .nav-divider { display: none; }
  .backend-status__text { display: none; }
  .backend-status { padding: 0 var(--space-2); }
  .logout-btn { padding: 0 var(--space-2); }
}
</style>
