import { describe, it, expect } from 'vitest'
import { registerLocalUser, authenticateLocalUser, getLocalAuthStore } from './authFallback'

const STORAGE_KEY = 'teacher-local-auth-users'

/** 模拟 localStorage：只提供 getItem/setItem，便于验证持久化行为 */
function createStorage() {
  const data = {}
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v) },
    removeItem: (k) => { delete data[k] }
  }
}

describe('authFallback 本地认证', () => {
  it('registerLocalUser 写入统一 storage key，用户名小写化', () => {
    const storage = createStorage()
    const user = registerLocalUser('Demo', '1234', storage)

    expect(user.username).toBe('demo')
    expect(user.role).toBe('teacher')

    const store = getLocalAuthStore(storage)
    expect(store.demo.password).toBe('1234')
    expect(store.demo.role).toBe('teacher')
  })

  it('authenticateLocalUser 可用已注册账号登录', () => {
    const storage = createStorage()
    registerLocalUser('demo', '1234', storage)
    const result = authenticateLocalUser('demo', '1234', storage)

    expect(result).toEqual({ username: 'demo', role: 'teacher' })
  })

  it('旧学生账号不能通过教师端本地兜底登录', () => {
    const storage = createStorage()
    storage.setItem(STORAGE_KEY, JSON.stringify({
      demo: { username: 'demo', password: '1234', role: 'student' }
    }))
    expect(() => authenticateLocalUser('demo', '1234', storage)).toThrow('账号或密码错误')
  })

  it('密码错误时抛出异常', () => {
    const storage = createStorage()
    registerLocalUser('demo', '1234', storage)
    expect(() => authenticateLocalUser('demo', 'wrong', storage)).toThrow('账号或密码错误')
  })

  it('未注册账号登录时抛出异常', () => {
    const storage = createStorage()
    expect(() => authenticateLocalUser('nobody', '1234', storage)).toThrow('账号或密码错误')
  })

  it('空用户名或空密码注册时抛出异常', () => {
    const storage = createStorage()
    expect(() => registerLocalUser('', '1234', storage)).toThrow('用户名和密码不能为空')
    expect(() => registerLocalUser('demo', '', storage)).toThrow('用户名和密码不能为空')
  })
})
