<template>
  <div class="app-shell">
    <!-- 顶部导航 -->
    <TeacherTopBar
      :backend-status-class="backendStatusClass"
      :backend-status-text="backendStatusText"
      :platform-status-class="platformConnectionClass"
      :platform-status-text="platformConnectionText"
      :username="authStore.username"
      @logout="handleLogout"
    />

    <!-- 主内容容器 -->
    <div class="app-shell-content">
      <slot />
    </div>

    <!-- 全局 Toast -->
    <teleport to="body">
      <div v-if="toastVisible" class="app-global-toast" role="status">{{ toastMessage }}</div>
    </teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/authStore'
import { useWorkspaceStore } from '../../stores/workspaceStore'
import TeacherTopBar from '../teacher/TeacherTopBar.vue'

const router = useRouter()
const authStore = useAuthStore()
const workspaceStore = useWorkspaceStore()

const toastVisible = ref(false)
const toastMessage = ref('')
let toastTimer = null

const backendStatusClass = computed(() => {
  return ['online', 'offline', 'demo'].includes(authStore.backendStatus) ? authStore.backendStatus : 'checking'
})

const backendStatusText = computed(() => {
  if (authStore.backendStatus === 'online') return '后端已连接'
  if (authStore.backendStatus === 'offline') return '后端未连接'
  if (authStore.backendStatus === 'demo') return '本地演示模式'
  return '正在检测后端'
})

const platformConnectionClass = computed(() => {
  return workspaceStore.platformOverviewLoading ? 'checking' : 'online'
})

const platformConnectionText = computed(() => {
  return workspaceStore.platformConnectionText
})

const handleLogout = () => {
  authStore.logout()
  router.push({ name: 'Login' })
}

const showToast = (message) => {
  const text = String(message || '').trim()
  if (!text) return
  toastMessage.value = text
  toastVisible.value = true
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toastVisible.value = false
  }, 3200)
}

const handleMockFallback = () => {
  authStore.backendStatus = 'demo'
}

defineExpose({ showToast })

onMounted(async () => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('fuww_teacher_origin', window.location.origin)
    window.addEventListener('fuww:mock-fallback', handleMockFallback)
  }
  await authStore.checkHealth()
})

onUnmounted(() => {
  if (toastTimer) window.clearTimeout(toastTimer)
  if (typeof window !== 'undefined') {
    window.removeEventListener('fuww:mock-fallback', handleMockFallback)
  }
})
</script>

<style scoped>
.app-shell {
  width: 100%;
  min-height: 100vh;
  height: auto;
  overflow-y: auto;
  overflow-x: hidden;
  font-family: 'SF Pro Display', 'SF Pro Text', 'PingFang SC', 'Helvetica Neue', 'Microsoft YaHei', sans-serif;
  background: radial-gradient(circle at 45% -12%, #ffffff 0%, #f3f8f5 58%, #e8f3ee 100%);
  padding: 20px;
  box-sizing: border-box;
}

.app-shell-content {
  width: 100%;
  min-height: calc(100vh - 100px);
  height: auto;
  border-radius: 26px;
  overflow: hidden;
  background: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 24px 54px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
}

.app-global-toast {
  position: fixed;
  left: 50%;
  bottom: 32px;
  transform: translateX(-50%);
  z-index: 99999;
  max-width: min(92vw, 480px);
  padding: 12px 18px;
  border-radius: 10px;
  background: rgba(17, 24, 39, 0.92);
  color: #f8fafc;
  font-size: 14px;
  line-height: 1.45;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.25);
  pointer-events: none;
}
</style>
