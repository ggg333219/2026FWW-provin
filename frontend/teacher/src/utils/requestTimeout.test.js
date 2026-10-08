// 回归：requestJson 超时必须抛出可读的 TimeoutError，而不是裸 AbortError。
//
// 背景：S3 大纲创建/修订内部要等 LLM，实测耗时 9.4s~15.4s，而 requestJson 默认
// 超时只有 10s。中止后抛出的 AbortError 自带 message 不含可读信息（浏览器只给
// "The operation was aborted"），调用方兜底成空串，前端表现为「点了没反应」。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { requestJson } from '../services/v1/request'
import { teacherOutlineApi } from '../services/v1/outlineApi'

function createStorage() {
  const map = new Map()
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => { map.set(k, String(v)) },
    removeItem: (k) => { map.delete(k) },
    clear: () => { map.clear() }
  }
}

// 永不 resolve 的 fetch：只在 signal 中止时以 AbortError 拒绝，模拟超时。
function stallingFetch() {
  return (url, opts) =>
    new Promise((_, reject) => {
      opts.signal.addEventListener('abort', () => {
        const err = new Error('The operation was aborted')
        err.name = 'AbortError'
        reject(err)
      })
    })
}

beforeEach(() => {
  vi.restoreAllMocks()
  const storage = createStorage()
  globalThis.window = { localStorage: storage, setTimeout, clearTimeout }
  globalThis.localStorage = storage
})

describe('requestJson 超时错误', () => {
  it('中止后抛出 TimeoutError 并带可读��案与路径', async () => {
    globalThis.fetch = stallingFetch()

    const err = await requestJson('/api/v1/outlines', {
      method: 'POST',
      timeoutMs: 20
    }).catch((e) => e)

    expect(err.name).toBe('TimeoutError')
    expect(err.isTimeout).toBe(true)
    expect(err.message).toContain('超时')
    expect(err.message).toContain('/api/v1/outlines')
  })

  it('超时文案不夹带原始 AbortError 的英文 message', async () => {
    globalThis.fetch = stallingFetch()

    const err = await requestJson('/api/v1/ping', { timeoutMs: 20 }).catch((e) => e)

    expect(err.message).not.toContain('The operation was aborted')
  })
})

describe('大纲接口超时配置', () => {
  // 记录 requestJson 实际传给 setTimeout 的延时，确认走的是长超时而非默认 10s。
  function captureTimeoutDelays() {
    const delays = []
    const realSetTimeout = globalThis.setTimeout
    globalThis.setTimeout = (fn, ms, ...rest) => {
      delays.push(ms)
      return realSetTimeout(fn, 0, ...rest)
    }
    return delays
  }

  it('create 使用 150s 超时，长于 Go 大纲等待上限', async () => {
    const delays = captureTimeoutDelays()
    globalThis.fetch = stallingFetch()

    await teacherOutlineApi.create({ session_id: 's1' }).catch(() => {})

    expect(delays).toContain(180000)
  })

  it('revise 同样使用 150s 超时，长于 Go 大纲等待上限', async () => {
    const delays = captureTimeoutDelays()
    globalThis.fetch = stallingFetch()

    await teacherOutlineApi.revise('outline_1', { message: '删掉总结节点' }).catch(() => {})

    expect(delays).toContain(180000)
  })
})
