import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/authStore'

const routes = [
  {
    path: '/',
    redirect: '/middle'
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../pages/LoginPage.vue')
  },
  {
    path: '/middle',
    name: 'Middle',
    component: () => import('../pages/MiddlePage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/workspace',
    name: 'Workspace',
    component: () => import('../pages/WorkspacePage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/courseware/create/s1-intent',
    name: 'S1Intent',
    component: () => import('../pages/S1IntentPage.vue'),
    meta: { requiresAuth: true, step: 'intent' }
  },
  {
    path: '/courseware/create/s2-material',
    name: 'S2Material',
    component: () => import('../pages/S2MaterialPage.vue'),
    meta: { requiresAuth: true, step: 'material' }
  },
  {
    path: '/courseware/create/s3-studio',
    name: 'S3Studio',
    component: () => import('../pages/S3StudioPage.vue'),
    meta: { requiresAuth: true, step: 'studio' }
  },
  {
    path: '/courseware/create/s4-version',
    name: 'S4Version',
    component: () => import('../pages/S4VersionPage.vue'),
    meta: { requiresAuth: true, step: 'version' }
  },
  {
    path: '/analytics',
    name: 'Analytics',
    component: () => import('../pages/AnalyticsPage.vue'),
    meta: { requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  // 登录态检查（使用 authStore.isLoggedIn 确保状态一致）
  const authStore = useAuthStore()
  const isLoggedIn = authStore.isLoggedIn || !!(
    typeof window !== 'undefined' && localStorage.getItem('fuww_teacher_logged_in')
  )

  if (to.meta.requiresAuth && !isLoggedIn) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
    return
  }

  next()
})

export default router
