<template>
  <div
    class="loading-state"
    :class="[type, size, { 'loading-state--inline': inline }]"
    :role="type === 'error' ? 'alert' : (type === 'loading' ? 'status' : undefined)"
    :aria-live="type === 'loading' ? 'polite' : undefined"
  >
    <!-- 加载态 -->
    <template v-if="type === 'loading'">
      <div class="loading-state__spinner" :class="`spinner-${variant}`" aria-hidden="true">
        <span v-if="variant === 'dots'">
          <span class="dot" v-for="i in 3" :key="i" :style="{ animationDelay: `${i * 0.15}s` }" />
        </span>
        <svg v-else class="spinner-ring" viewBox="0 0 50 50">
          <circle cx="25" cy="25" r="20" fill="none" stroke="currentColor" stroke-width="4" stroke-dasharray="90 150" stroke-linecap="round" />
        </svg>
      </div>
      <p v-if="text" class="loading-state__text">{{ text }}</p>
      <p v-if="hint" class="loading-state__hint">{{ hint }}</p>
    </template>

    <!-- 空状态 -->
    <template v-else-if="type === 'empty'">
      <div class="loading-state__icon" aria-hidden="true">
        <svg v-if="icon === 'file'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        <svg v-else-if="icon === 'search'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.35-4.35" />
        </svg>
        <svg v-else-if="icon === 'node'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v7M12 15v7M2 12h7M15 12h7" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="2" y="2" width="20" height="20" rx="2" />
          <path d="M8 12h8M12 8v8" />
        </svg>
      </div>
      <p class="loading-state__text">{{ text || '暂无数据' }}</p>
      <p v-if="hint" class="loading-state__hint">{{ hint }}</p>
      <button v-if="actionText" class="ds-btn ds-btn--secondary ds-btn--sm loading-state__action" type="button" @click="$emit('action')">{{ actionText }}</button>
    </template>

    <!-- 错误状态 -->
    <template v-else-if="type === 'error'">
      <div class="loading-state__icon loading-state__icon--error" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4M12 16h.01" />
        </svg>
      </div>
      <p class="loading-state__text">{{ text || '加载失败' }}</p>
      <p v-if="hint" class="loading-state__hint">{{ hint }}</p>
      <button v-if="actionText" class="ds-btn ds-btn--secondary ds-btn--sm loading-state__action" type="button" @click="$emit('action')">{{ actionText }}</button>
    </template>
  </div>
</template>

<script setup>
defineProps({
  type: { type: String, default: 'loading', validator: v => ['loading', 'empty', 'error'].includes(v) },
  size: { type: String, default: 'md', validator: v => ['sm', 'md', 'lg'].includes(v) },
  variant: { type: String, default: 'ring', validator: v => ['ring', 'dots'].includes(v) },
  text: { type: String, default: '' },
  hint: { type: String, default: '' },
  icon: { type: String, default: 'box' },
  actionText: { type: String, default: '' },
  inline: { type: Boolean, default: false }
})
defineEmits(['action'])
</script>

<style scoped>
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-10) var(--space-5);
  text-align: center;
}
.loading-state--inline { padding: var(--space-4); gap: var(--space-2); }
.loading-state.sm { padding: var(--space-5) var(--space-3); }
.loading-state.lg { padding: var(--space-16) var(--space-10); }

.loading-state__spinner { color: var(--color-primary); display: inline-flex; align-items: center; }
.loading-state__icon { width: 48px; height: 48px; color: var(--text-disabled); }
.loading-state__icon--error { color: var(--color-danger); }

.loading-state__text {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  color: var(--text-secondary);
}
.loading-state__hint {
  margin: 0;
  max-width: 42ch;
  font-size: var(--text-2xs);
  line-height: var(--leading-relaxed);
  color: var(--text-tertiary);
}
.loading-state__action { margin-top: var(--space-2); }

.spinner-ring { width: 36px; height: 36px; animation: ls-spin 1s linear infinite; }
@keyframes ls-spin { to { transform: rotate(360deg); } }
.spinner-ring circle { stroke: currentColor; }
.loading-state.sm .spinner-ring { width: 24px; height: 24px; }
.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin: 0 3px;
  border-radius: 50%;
  background: currentColor;
  animation: dot-bounce 1.2s ease-in-out infinite;
}
@keyframes dot-bounce {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1.2); }
}

@media (prefers-reduced-motion: reduce) {
  .spinner-ring, .dot { animation-duration: 0.01ms; animation-iteration-count: 1; }
}
</style>