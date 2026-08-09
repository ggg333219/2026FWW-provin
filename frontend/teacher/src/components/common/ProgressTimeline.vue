<template>
  <div class="progress-timeline">
    <div
      v-for="(step, idx) in steps"
      :key="idx"
      class="timeline-step"
      :class="{
        'timeline-step--done': step.status === 'done',
        'timeline-step--active': step.status === 'active',
        'timeline-step--pending': step.status === 'pending',
        'timeline-step--error': step.status === 'error'
      }"
    >
      <div class="timeline-step__dot">
        <span v-if="step.status === 'done'" class="timeline-step__icon">✓</span>
        <span v-else-if="step.status === 'error'" class="timeline-step__icon">✗</span>
        <span v-else-if="step.status === 'active'" class="timeline-step__icon">◌</span>
        <span v-else class="timeline-step__icon">○</span>
      </div>
      <div class="timeline-step__content">
        <span class="timeline-step__label">{{ step.label }}</span>
        <span v-if="step.detail" class="timeline-step__detail">{{ step.detail }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  steps: {
    type: Array,
    default: () => []
    // [{ label: '大纲构建', status: 'done', detail: '3 个节点' }, ...]
  }
})
</script>

<style scoped>
.progress-timeline {
  display: flex; flex-direction: column; gap: 0;
  padding: 8px 0;
}
.timeline-step {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 8px 12px; position: relative;
}
.timeline-step::before {
  content: ''; position: absolute; left: 20px; top: 28px;
  width: 1px; height: calc(100% - 28px); background: #e2e8f0;
}
.timeline-step:last-child::before { display: none; }
.timeline-step__dot {
  width: 20px; height: 20px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; font-size: 10px; font-weight: 600;
  border: 2px solid #e2e8f0; background: #fff; color: #94a3b8;
  margin-top: 2px; position: relative; z-index: 1;
}
.timeline-step--done .timeline-step__dot {
  background: #2d5f58; border-color: #2d5f58; color: #fff;
}
.timeline-step--active .timeline-step__dot {
  border-color: #2d5f58; color: #2d5f58;
  animation: pulse 1.5s ease-in-out infinite;
}
.timeline-step--error .timeline-step__dot {
  border-color: #dc2626; color: #dc2626;
}
.timeline-step__content {
  display: flex; flex-direction: column; gap: 2px;
}
.timeline-step__label { font-size: 13px; font-weight: 500; color: #1e293b; }
.timeline-step__detail { font-size: 11px; color: #94a3b8; }
.timeline-step--done .timeline-step__label { color: #065f46; }
.timeline-step--active .timeline-step__label { color: #2d5f58; font-weight: 600; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
</style>