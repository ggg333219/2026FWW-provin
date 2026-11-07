<template>
  <LoadingState
    type="empty"
    :icon="icon"
    :text="title"
    :hint="description"
    :action-text="actionText"
    :size="size"
    :inline="inline"
    @action="$emit('action')"
  />
</template>

<script setup>
import LoadingState from './LoadingState.vue'

/** 空状态语义封装。统一的「说明 + 如何填充 + 可选动作」结构。 */
defineProps({
  title: { type: String, default: '暂无内容' },
  description: { type: String, default: '' },
  actionText: { type: String, default: '' },
  icon: { type: String, default: 'box' },
  size: { type: String, default: 'md' },
  inline: { type: Boolean, default: false }
})

defineEmits(['action'])
</script>
