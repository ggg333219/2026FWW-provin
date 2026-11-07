<template>
  <teleport to="body">
    <transition name="toast">
      <div
        v-if="visible && message"
        class="app-toast"
        :class="`app-toast--${type}`"
        :role="type === 'error' ? 'alert' : 'status'"
        aria-live="polite"
      >
        <span class="app-toast__icon" aria-hidden="true">
          <svg v-if="type === 'success'" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="m4 10.5 4 4 8-9" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <svg v-else-if="type === 'error'" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="10" cy="10" r="7.5" /><path d="M10 6.5v4.2M10 13.6h.01" stroke-linecap="round" />
          </svg>
          <svg v-else-if="type === 'warning'" viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M10 2.8 18 17H2L10 2.8Z" stroke-linejoin="round" /><path d="M10 8v3.6M10 14h.01" stroke-linecap="round" />
          </svg>
          <svg v-else viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="10" cy="10" r="7.5" /><path d="M10 9v4.5M10 6.6h.01" stroke-linecap="round" />
          </svg>
        </span>
        <span class="app-toast__message">{{ message }}</span>
        <button
          v-if="dismissible"
          class="app-toast__close"
          type="button"
          aria-label="关闭提示"
          @click="$emit('dismiss')"
        >
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <path d="m4 4 8 8M12 4l-8 8" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
/** 全局唯一 Toast。AppShell 负责计时与分发，本组件只负责渲染与无障碍语义。 */
defineProps({
  visible: { type: Boolean, default: false },
  message: { type: String, default: '' },
  type: {
    type: String,
    default: 'success',
    validator: v => ['success', 'error', 'warning', 'info'].includes(v)
  },
  dismissible: { type: Boolean, default: true }
})

defineEmits(['dismiss'])
</script>

<style scoped>
.app-toast {
  position: fixed;
  left: 50%;
  bottom: var(--space-8);
  transform: translateX(-50%);
  z-index: var(--z-toast);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: max-content;
  max-width: min(92vw, 480px);
  min-height: 40px;
  padding: var(--space-2) var(--space-3) var(--space-2) var(--space-4);
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--color-primary);
  border-radius: var(--radius-control);
  background: var(--bg-surface);
  color: var(--text-primary);
  box-shadow: var(--shadow-lg);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
}

.app-toast__icon {
  display: inline-flex;
  align-items: center;
  color: var(--color-primary);
  flex-shrink: 0;
}

.app-toast--success { border-left-color: var(--color-success); }
.app-toast--error { border-left-color: var(--color-danger); }
.app-toast--error .app-toast__icon { color: var(--color-danger); }
.app-toast--warning { border-left-color: var(--color-warning); }
.app-toast--warning .app-toast__icon { color: var(--color-warning); }
.app-toast--info { border-left-color: var(--color-info); }
.app-toast--info .app-toast__icon { color: var(--color-info); }

.app-toast__message {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}

.app-toast__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--text-tertiary);
}

.app-toast__close:hover {
  background: var(--bg-subtle);
  color: var(--text-primary);
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity var(--duration-base) var(--ease-standard),
              transform var(--duration-base) var(--ease-standard);
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 8px);
}

@media (max-width: 767px) {
  .app-toast { bottom: var(--space-4); max-width: calc(100vw - 32px); }
}
</style>
