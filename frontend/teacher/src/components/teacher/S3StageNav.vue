<template>
  <nav class="s3-stages" aria-label="课件生成步骤">
    <button v-for="stage in stages" :key="stage.id" type="button" class="s3-stage"
      :class="{ active: phase === stage.id }" :aria-current="phase === stage.id ? 'step' : undefined"
      :disabled="stage.disabled" @click="$emit('select', stage.id)">{{ stage.label }}</button>
  </nav>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ phase: { type: String, required: true }, outlineConfirmed: Boolean, reviewReady: Boolean })
defineEmits(['select'])
const stages = computed(() => [
  { id: 'outline', label: '大纲', disabled: false },
  { id: 'content', label: '内容', disabled: !props.outlineConfirmed },
  { id: 'review', label: '审阅', disabled: !props.reviewReady },
])
</script>

<style scoped>
.s3-stages { display: flex; gap: var(--space-2); padding: var(--space-2); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--bg-surface); }
.s3-stage { flex: 1; min-width: 0; padding: var(--space-3); border: 0; border-radius: var(--radius-sm); background: transparent; color: var(--text-secondary); font: inherit; font-weight: var(--weight-semibold); cursor: pointer; }
.s3-stage.active { background: var(--color-primary-soft); color: var(--color-primary); }
.s3-stage:disabled { opacity: .45; cursor: not-allowed; }
.s3-stage:not(:disabled):hover { background: var(--bg-page); }
</style>
