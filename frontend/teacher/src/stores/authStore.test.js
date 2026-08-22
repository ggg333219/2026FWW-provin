import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { teacherV1Api } from '../services/v1'
import { useAuthStore } from './authStore'

function createStorage() {
  const data = new Map()
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key)
  }
}

beforeEach(() => {
  vi.restoreAllMocks()
  const localStorage = createStorage()
  globalThis.window = { localStorage }
  globalThis.localStorage = localStorage
  setActivePinia(createPinia())
})

describe('authStore 后端状态', () => {
  it('健康检查失败时如实显示未连接', async () => {
    vi.spyOn(teacherV1Api, 'health').mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const store = useAuthStore()

    await store.checkHealth()

    expect(store.backendStatus).toBe('offline')
  })

  it('Mock 已启用时明确显示本地演示模式', async () => {
    window.localStorage.setItem('fuww_mock_mode', 'true')
    vi.spyOn(teacherV1Api, 'health').mockRejectedValueOnce(new TypeError('Failed to fetch'))
    const store = useAuthStore()

    await store.checkHealth()

    expect(store.backendStatus).toBe('demo')
  })

  it('后端恢复后显示已连接并退出 Mock 模式', async () => {
    window.localStorage.setItem('fuww_mock_mode', 'true')
    vi.spyOn(teacherV1Api, 'health').mockResolvedValueOnce({ ok: true })
    const store = useAuthStore()

    await store.checkHealth()

    expect(store.backendStatus).toBe('online')
    expect(window.localStorage.getItem('fuww_mock_mode')).toBe(null)
  })
})
