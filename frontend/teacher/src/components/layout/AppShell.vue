<template>
  <div class="app-shell">
    <!-- 顶部导航：桌面端固定 60px 单行，滚动时吸顶 -->
    <TeacherTopBar
      :backend-status-class="backendStatusClass"
      :backend-status-text="backendStatusText"
      :platform-status-class="platformStatusClass"
      :platform-status-text="platformStatusText"
      :username="authStore.username"
      @logout="handleLogout"
    />

    <!-- 主内容容器 -->
    <div class="app-shell-body">
      <div class="app-shell-content">
        <slot />
      </div>
    </div>

    <!-- 全局唯一 Toast -->
    <AppToast
      :visible="toastVisible"
      :message="toastMessage"
      :type="toastType"
      @dismiss="dismissToast"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/authStore'
import { useWorkspaceStore } from '../../stores/workspaceStore'
import TeacherTopBar from '../teacher/TeacherTopBar.vue'
import AppToast from '../common/AppToast.vue'

const router = useRouter()
const authStore = useAuthStore()
const workspaceStore = useWorkspaceStore()

const toastVisible = ref(false)
const toastMessage = ref('')
const toastType = ref('success')
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

const platformStatusClass = computed(() => {
  return workspaceStore.platformOverviewLoading ? 'checking' : 'online'
})

const platformStatusText = computed(() => workspaceStore.platformConnectionText)

const handleLogout = () => {
  authStore.logout()
  router.push({ name: 'Login' })
}

const dismissToast = () => {
  toastVisible.value = false
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = null
}

const showToast = (message, type = 'success') => {
  const text = String(message || '').trim()
  if (!text) return
  toastMessage.value = text
  toastType.value = ['success', 'error', 'warning', 'info'].includes(type) ? type : 'success'
  toastVisible.value = true
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toastVisible.value = false
    toastTimer = null
  }, 3200)
}

/** 页面无需持有 AppShell 引用也能发全局反馈：
 *  window.dispatchEvent(new CustomEvent('fuww:toast', { detail: { message, type } })) */
const handleGlobalToast = event => {
  const detail = event?.detail || {}
  showToast(typeof detail === 'string' ? detail : detail.message, detail.type)
}

const handleMockFallback = () => {
  authStore.backendStatus = 'demo'
}

defineExpose({ showToast })

onMounted(async () => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('fuww_teacher_origin', window.location.origin)
    window.addEventListener('fuww:mock-fallback', handleMockFallback)
    window.addEventListener('fuww:toast', handleGlobalToast)
  }
  await authStore.checkHealth()
})

onUnmounted(() => {
  if (toastTimer) window.clearTimeout(toastTimer)
  if (typeof window !== 'undefined') {
    window.removeEventListener('fuww:mock-fallback', handleMockFallback)
    window.removeEventListener('fuww:toast', handleGlobalToast)
  }
})
</script>

<style scoped>
.app-shell {
  width: 100%;
  min-height: 100dvh;
  background: var(--bg-page);
  font-family: var(--font-sans);
  color: var(--text-primary);
}

.app-shell-body {
  width: 100%;
  max-width: var(--content-max);
  margin: 0 auto;
  padding: var(--shell-gutter);
}

.app-shell-content {
  width: 100%;
  min-height: calc(100dvh - var(--topbar-height) - var(--shell-gutter) * 2);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
  /* clip 而非 hidden：hidden 会生成滚动容器，导致内部 position:sticky 侧栏失效。 */
  overflow: clip;
  display: flex;
  flex-direction: column;
}

@media (max-width: 767px) {
  .app-shell-body { padding: var(--space-2); }
  .app-shell-content {
    border-radius: var(--radius-sm);
    min-height: calc(100dvh - var(--topbar-height) - var(--space-4));
  }
}
</style>
