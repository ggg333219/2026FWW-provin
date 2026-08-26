import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useVersionStore } from './versionStore'

function createStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key)
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

beforeEach(() => {
  const localStorage = createStorage()
  globalThis.window = { localStorage }
  // 后端不可达 → requestJson 回退 Mock（/api/v1/export + /api/v1/export/status）
  globalThis.fetch = () => Promise.reject(new Error('backend unreachable'))
  setActivePinia(createPinia())
})

describe('versionStore S4 导出闭环（Mock）', () => {
  it('startExport：正确读取 job_id 并轮询到 done（回归：信封解包 bug）', async () => {
    const store = useVersionStore()

    // 回归点：旧实现未解包 response.data，exportJobId 恒为 ''，永不进入轮询，
    // 界面停留在「导出中...」。此处断言 job_id 被真实读到。
    await store.startExport('gen_export_test', 'pptx')
    expect(store.exportJobId).toBeTruthy()
    expect(store.exportStatus).toBe('pending')
    expect(store.exportError).toBe('')

    // Mock 异步 2s 完成 + 下一轮轮询 → 终态 done，下载地址可用
    await sleep(2700)
    expect(store.exportStatus).toBe('done')
    expect(store.exportDownloadUrl).toBeTruthy()
  })

  it('Mock 完成时生成真实可下载文件（Blob URL，而非死链）', async () => {
    const store = useVersionStore()
    await store.startExport('gen_export_url', 'pptx')
    await sleep(2700)

    expect(store.exportStatus).toBe('done')
    // Mock 用版本快照节点生成最小 PPTX 并以 Blob URL 返回，保证「下载文件」可点开
    expect(store.exportDownloadUrl.startsWith('blob:')).toBe(true)
  })

  it('resetExport 清空导出状态', async () => {
    const store = useVersionStore()
    store.exportJobId = 'exp_x'
    store.exportStatus = 'done'
    store.exportDownloadUrl = '/download/exp_x.pptx'
    store.exportError = ''

    store.resetExport()
    expect(store.exportJobId).toBe('')
    expect(store.exportStatus).toBe('idle')
    expect(store.exportDownloadUrl).toBe('')
    expect(store.exportError).toBe('')
  })
})
