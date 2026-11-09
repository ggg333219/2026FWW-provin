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

// 这些路径一旦在断网时返回假数据，教师会以为「版本已保存 / 修改已生效 /
// 文件已导出」。mockBackend 为它们全都实现了假响应，必须在网络层拦住。
const STRICT_PATHS = [
  '/api/v1/gen/create',
  '/api/v1/gen/preview',
  '/api/v1/gen/content',
  '/api/v1/gen/content/status/content_1',
  '/api/v1/gen/status/task_1',
  '/api/v1/gen/finalize',
  '/api/v1/gen/modify',
  '/api/v1/exp/gen_1',
  '/api/v1/exp/status/job_1',
  '/api/v1/export/gen_1',
  '/api/v1/exports/status/job_1',
]

beforeEach(() => {
  vi.restoreAllMocks()
  globalThis.window = { localStorage: createStorage() }
  globalThis.fetch = vi.fn().mockRejectedValue(new Error('network down'))
})

describe('严格链路在后端不可达时拒绝 Mock 伪造', () => {
  it.each(STRICT_PATHS)('首次断网也不返回假响应: %s', async (path) => {
    await expect(requestJson(path, { method: 'POST', body: '{}' }))
      .rejects.toThrow('阻止 Mock 回退')
    // 拦下后不能把整个会话切进 mock 模式，否则后续请求会持续拿到假数据
    expect(window.localStorage.getItem('fuww_mock_mode')).toBe(null)
  })

  it('已进入 mock 模式且后端探测失败时同样拦截', async () => {
    window.localStorage.setItem('fuww_mock_mode', 'true')
    await expect(requestJson('/api/v1/gen/finalize', { method: 'POST' }))
      .rejects.toThrow('阻止 Mock 回退')
  })
})
