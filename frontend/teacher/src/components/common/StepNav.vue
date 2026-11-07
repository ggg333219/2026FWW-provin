<template>
  <nav class="step-nav" aria-label="课件生成流程">
    <ol class="step-nav__rail">
      <li
        v-for="(step, index) in mainSteps"
        :key="step.key"
        class="step-nav__item"
        :class="{
          'is-current': step.key === current,
          'is-done': index < currentIndex,
          'is-disabled': !canNavigate(step.key)
        }"
        :aria-current="step.key === current ? 'step' : undefined"
      >
        <button
          v-if="actionKeys.includes(step.key)"
          class="step-nav__link step-nav__link--button"
          type="button"
          @click="$emit('step-action', step.key)"
        >
          <span class="step-nav__index">{{ pad(index + 1) }}</span>
          <span class="step-nav__label">{{ step.label }}</span>
        </button>
        <span v-else-if="!canNavigate(step.key) && step.key !== current" class="step-nav__link is-disabled" aria-disabled="true">
          <span class="step-nav__index">{{ pad(index + 1) }}</span>
          <span class="step-nav__label">{{ step.label }}</span>
        </span>
        <router-link
          v-else
          class="step-nav__link"
          :to="toFor(step)"
          @click="$emit('step-click', step.key)"
        >
          <span class="step-nav__index">{{ pad(index + 1) }}</span>
          <span class="step-nav__label">{{ step.label }}</span>
        </router-link>
      </li>
    </ol>

    <div class="step-nav__extras">
      <span v-if="!ready && current !== 's2'" class="step-nav__optional is-disabled" aria-disabled="true">
        补充资料（可选）
      </span>
      <router-link
        v-else-if="current !== 's2'"
        class="step-nav__optional"
        :to="toFor(optionalStep)"
        @click="$emit('step-click', 's2')"
      >
        <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <path d="M8 3v10M3 8h10" stroke-linecap="round" />
        </svg>
        补充资料（可选）
      </router-link>
      <span v-else class="step-nav__optional is-current" aria-current="step">当前：资料补充（可选）</span>

      <span class="step-nav__divider" aria-hidden="true"></span>
      <router-link class="step-nav__back" :to="{ name: 'Middle' }">
        <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
          <path d="M10 3 5 8l5 5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        返回中间页
      </router-link>
    </div>
  </nav>
</template>

<script setup>
import { computed } from 'vue'

/**
 * 统一流程导航。
 *
 * 业务事实：主流程是 S1 意图理解 → S3 课件生成 → S4 版本管理，
 * S2 资料上传是可选补充入口，不能画成线性四步。
 * 页面若需要在跳转前执行业务动作（例如先保存版本、先做「无资料生成」确认），
 * 把对应 key 放进 ``actionKeys`` 并监听 ``step-action``；该步会渲染为按钮而不是
 * RouterLink，从根上避免「监听顺序导致拦截失效、直接跳走」的问题。
 */
const props = defineProps({
  current: {
    type: String,
    required: true,
    validator: v => ['s1', 's2', 's3', 's4'].includes(v)
  },
  projectId: { type: [String, Number], default: '' },
  ready: { type: Boolean, default: true },
  overrides: { type: Object, default: () => ({}) },
  actionKeys: { type: Array, default: () => [] }
})

const withProject = name => ({
  name,
  ...(props.projectId ? { query: { project_id: props.projectId } } : {})
})

const mainSteps = [
  { key: 's1', label: '意图理解', to: computed(() => withProject('S1Intent')) },
  { key: 's3', label: '课件生成', to: computed(() => withProject('S3Studio')) },
  { key: 's4', label: '版本与导出', to: computed(() => withProject('S4Version')) }
]

const optionalStep = { key: 's2', label: '补充资料（可选）', to: computed(() => withProject('S2Material')) }

const currentIndex = computed(() => mainSteps.findIndex(step => step.key === props.current))

const canNavigate = key => props.ready || key === props.current

const toFor = step => props.overrides[step.key] || step.to.value

const pad = n => String(n).padStart(2, '0')
</script>

<style scoped>
.step-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5);
  padding: var(--space-3) var(--space-5);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-xs);
}

.step-nav__rail {
  display: flex;
  align-items: center;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.step-nav__item {
  display: flex;
  align-items: center;
}

.step-nav__item + .step-nav__item::before {
  content: '';
  width: 28px;
  height: 1px;
  margin: 0 var(--space-2);
  background: var(--border-default);
  flex-shrink: 0;
}

.step-nav__item.is-done + .step-nav__item::before {
  background: var(--brand-300);
}

.step-nav__link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--text-tertiary);
  font-size: var(--text-xs);
  font-weight: var(--weight-medium);
  white-space: nowrap;
  transition: color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}
.step-nav__link--button { font-family: var(--font-sans); cursor: pointer; }

.step-nav__link:hover:not(.is-disabled) {
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.step-nav__link.is-disabled {
  opacity: 0.48;
  cursor: not-allowed;
}

.step-nav__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 1px solid var(--border-default);
  border-radius: 50%;
  background: var(--bg-surface);
  color: var(--text-tertiary);
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.step-nav__item.is-current .step-nav__link {
  color: var(--color-primary);
  font-weight: var(--weight-semibold);
}

.step-nav__item.is-current .step-nav__index {
  border-color: var(--color-primary);
  background: var(--color-primary);
  color: var(--color-on-primary);
}

.step-nav__item.is-done .step-nav__index {
  border-color: var(--brand-300);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.step-nav__extras {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
}

.step-nav__optional,
.step-nav__back {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-weight: var(--weight-medium);
  color: var(--text-secondary);
  white-space: nowrap;
  border-radius: var(--radius-control);
  padding: var(--space-1) var(--space-2);
  transition: color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}

.step-nav__optional:hover:not(.is-disabled):not(.is-current),
.step-nav__back:hover {
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.step-nav__optional.is-current {
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.step-nav__optional.is-disabled {
  opacity: 0.48;
  cursor: not-allowed;
}

.step-nav__divider {
  width: 1px;
  height: 16px;
  background: var(--border-subtle);
}

@media (max-width: 1023px) {
  .step-nav {
    flex-wrap: wrap;
    gap: var(--space-3);
  }
  .step-nav__extras { width: 100%; justify-content: flex-start; }
}

@media (max-width: 767px) {
  .step-nav { padding: var(--space-3); }
  /* 三步必须完整可见：收紧间距而不是靠 overflow-x 隐藏内容 */
  .step-nav__rail { width: 100%; overflow: visible; }
  .step-nav__item + .step-nav__item::before { width: 10px; margin: 0 2px; }
  .step-nav__link { gap: var(--space-1); padding: 2px; }
  .step-nav__index { width: 18px; height: 18px; }
  .step-nav__label { font-size: var(--text-2xs); }
  .step-nav__extras { flex-wrap: wrap; gap: var(--space-2); }
  .step-nav__divider { display: none; }
}
</style>
