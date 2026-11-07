<template>
  <LoadingState
    type="error"
    :text="title"
    :hint="description"
    :action-text="retryText"
    :size="size"
    :inline="inline"
    @action="$emit('retry')"
  />
</template>

<script setup>
import LoadingState from './LoadingState.vue'

/** 错误状态语义封装。就近展示可恢复动作，不用原生 alert。 */
defineProps({
  title: { type: String, default: '加载失败' },
  description: { type: String, default: '' },
  retryText: { type: String, default: '重试' },
  size: { type: String, default: 'md' },
  inline: { type: Boolean, default: false }
})

defineEmits(['retry'])
</script>
