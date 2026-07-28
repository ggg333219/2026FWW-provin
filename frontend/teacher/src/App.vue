<template>
  <router-view />
</template>

<script setup>
import { onMounted } from 'vue'
import { useAuthStore } from './stores/authStore'

const authStore = useAuthStore()

onMounted(() => {
  // 尝试恢复登录会话（URL 参数优先，其次 localStorage）
  authStore.hydrate()
})
</script>