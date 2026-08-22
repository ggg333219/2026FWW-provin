import { defineStore } from 'pinia'
import { teacherV1Api } from '../services/v1'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    isLoggedIn: false,
    username: '',
    userId: '',
    role: '',
    token: '',
    backendStatus: 'checking' // 'online' | 'offline' | 'demo' | 'checking'
  }),

  getters: {
    isTeacher: (state) => state.role === 'teacher',
    isAuthenticated: (state) => state.isLoggedIn && !!state.token
  },

  actions: {
    async login(user) {
      this.isLoggedIn = true
      this.username = user.username || ''
      this.userId = user.userId || ''
      this.role = user.role || 'teacher'
      this.token = user.token || `local_${Date.now()}`

      if (typeof window !== 'undefined') {
        localStorage.setItem('fuww_teacher_logged_in', '1')
        localStorage.setItem('fuww_teacher_username', this.username)
        localStorage.setItem('fuww_teacher_role', this.role)
      }
    },

    logout() {
      this.isLoggedIn = false
      this.username = ''
      this.userId = ''
      this.role = ''
      this.token = ''

      if (typeof window !== 'undefined') {
        localStorage.removeItem('fuww_teacher_logged_in')
        localStorage.removeItem('fuww_teacher_username')
        localStorage.removeItem('fuww_teacher_role')
      }
    },

    async checkHealth() {
      this.backendStatus = 'checking'
      try {
        const res = await teacherV1Api.health()
        this.backendStatus = res.ok ? 'online' : 'offline'
        if (res.ok && typeof window !== 'undefined') {
          window.localStorage.removeItem('fuww_mock_mode')
        }
      } catch {
        const inDemoMode = typeof window !== 'undefined' && window.localStorage.getItem('fuww_mock_mode') === 'true'
        this.backendStatus = inDemoMode ? 'demo' : 'offline'
      }
    },

    restoreSession() {
      if (typeof window === 'undefined') return false
      const loggedIn = localStorage.getItem('fuww_teacher_logged_in')
      const username = localStorage.getItem('fuww_teacher_username')
      const role = localStorage.getItem('fuww_teacher_role')
      if (loggedIn && username) {
        this.isLoggedIn = true
        this.username = username
        this.role = role || 'teacher'
        this.token = `local_${Date.now()}`
        return true
      }
      return false
    },

    hydrate() {
      const params = new URLSearchParams(typeof window !== 'undefined' ? window.location.search : '')
      const role = String(params.get('role') || '').trim().toLowerCase()
      const username = String(params.get('username') || '').trim().toLowerCase()

      if (role === 'student') {
        // 学生跳转到学生端
        const studentOrigin = typeof window !== 'undefined'
          ? (localStorage.getItem('fuww_student_origin') || 'http://localhost:8081')
          : 'http://localhost:8081'
        window.location.replace(`${studentOrigin}/?studentId=${encodeURIComponent(username)}&role=student&username=${encodeURIComponent(username)}`)
        return true
      }

      if (role && username) {
        this.login({ username, role })
        if (typeof window !== 'undefined') {
          window.history.replaceState({}, document.title, window.location.pathname)
        }
        return true
      }

      return this.restoreSession()
    }
  }
})
