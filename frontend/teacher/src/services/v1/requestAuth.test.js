import { beforeEach, describe, expect, it, vi } from 'vitest'
import { requestJson } from './request'

function createStorage() {
  const data = new Map()
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key),
  }
}

beforeEach(() => {
  vi.restoreAllMocks()
  const localStorage = createStorage()
  localStorage.setItem('fuww_teacher_logged_in', '1')
  localStorage.setItem('fuww_teacher_username', 'teacher')
  localStorage.setItem('fuww_teacher_role', 'teacher')
  localStorage.setItem('fuww_teacher_auth_token', 'old-token')
  localStorage.setItem('fuww_project_draft', 'keep-this')
  globalThis.window = {
    localStorage,
    location: {
      pathname: '/courseware/create/s4-version',
      search: '?project_id=p1',
      hash: '',
      replace: vi.fn(),
    },
  }
})

describe('认证失败时保留项目并引导重新登录', () => {
  it('401 清除旧登录态并带原地址跳转', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ message: '无效或过期的令牌' }),
    })

    await expect(requestJson('/api/v1/exports/status/job-1')).rejects.toMatchObject({
      message: '登录已过期，请重新登录后重试',
      httpStatus: 401,
    })

    expect(window.localStorage.getItem('fuww_teacher_auth_token')).toBe(null)
    expect(window.localStorage.getItem('fuww_teacher_logged_in')).toBe(null)
    expect(window.localStorage.getItem('fuww_project_draft')).toBe('keep-this')
    expect(window.location.replace).toHaveBeenCalledWith(
      '/login?redirect=%2Fcourseware%2Fcreate%2Fs4-version%3Fproject_id%3Dp1&reason=session_expired',
    )
  })

  it('403 不会误删登录态', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ message: '权限不足' }),
    })

    await expect(requestJson('/api/v1/exports/status/job-1')).rejects.toMatchObject({
      message: '权限不足',
      httpStatus: 403,
    })
    expect(window.localStorage.getItem('fuww_teacher_auth_token')).toBe('old-token')
    expect(window.location.replace).not.toHaveBeenCalled()
  })
})
