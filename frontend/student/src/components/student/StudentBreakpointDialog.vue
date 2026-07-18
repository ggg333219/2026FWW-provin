<template>
  <el-dialog
    :model-value="modelValue"
    title="断点续播"
    width="30%"
    :close-on-click-modal="false"
    :show-close="false"
  >
    <p>检测到你上次学习到第 {{ breakpointPage }} 页，是否继续学习？</p>
    <template #footer>
      <el-button @click="$emit('restart-study')">重新开始</el-button>
      <el-button type="primary" @click="$emit('continue-study')">继续学习</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
/* eslint-disable no-undef */
defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  breakpointPage: {
    type: Number,
    default: 1
  }
})

defineEmits(['restart-study', 'continue-study'])
</script>