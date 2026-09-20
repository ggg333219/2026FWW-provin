import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useVersionStore } from './versionStore'
import { teacherV1Api } from '../services/v1'

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
  // 后端不可达 → requestJson 回退 Mock（契约路径 /api/v1/exp）
  globalThis.fetch = () => Promise.reject(new Error('backend unreachable'))
  setActivePinia(createPinia())
})

describe('versionStore S4 导出闭环（Mock）', () => {
  it('版本加载与回滚保留页面证据绑定和呈现样式', async () => {
    const pageBindings = [{ page_id: 'page_1', evidence_refs: ['chunk_tcp_1'] }]
    const presentation = { template_id: 'deck-swiss-edu', palette: 'forest' }
    await teacherV1Api.generation.finalize({
      generation_id: 'gen_version_binding',
      nodes: [{ node_id: 'page_1', title: 'TCP 三次握手' }],
      page_bindings: pageBindings,
      presentation,
    })
    const store = useVersionStore()
    const detail = await store.loadVersion('gen_version_binding', 1)

    expect(detail.pageBindings).toEqual(pageBindings)
    expect(detail.presentation).toEqual(presentation)

    const rollback = await store.rollbackTo('gen_version_binding', 1)
    expect(rollback.data.page_bindings).toEqual(pageBindings)
    expect(rollback.data.presentation).toEqual(presentation)
  })

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

  it('导出创建响应符合契约：文件名、标题和版本号完整', async () => {
    const response = await teacherV1Api.version.exportCreate('gen_contract', 'pptx', 3, 'TCP三次握手课件')
    expect(response.ok).toBe(true)
    expect(response.data.filename).toBe('TCP三次握手课件_v3.pptx')
    expect(response.data.courseware_title).toBe('TCP三次握手课件')
    expect(response.data.version_no).toBe(3)
  })

  it('同时导出返回 PPTX、DOCX、HTML5 三个独立下载入口', async () => {
    const store = useVersionStore()
    await store.startExport('gen_export_bundle', 'both', 2, '网络基础')
    await sleep(2700)

    expect(store.exportStatus).toBe('done')
    expect(Object.keys(store.exportFiles).sort()).toEqual(['docx', 'html', 'pptx'])
    expect(Object.values(store.exportFiles).every((url) => url.startsWith('blob:'))).toBe(true)
  })

  it('resetExport 清空导出状态', async () => {
    const store = useVersionStore()
    store.exportJobId = 'exp_x'
    store.exportStatus = 'done'
    store.exportDownloadUrl = '/download/exp_x.pptx'
    store.exportFiles = { pptx: '/download/exp_x.pptx' }
    store.exportError = ''

    store.resetExport()
    expect(store.exportJobId).toBe('')
    expect(store.exportStatus).toBe('idle')
    expect(store.exportDownloadUrl).toBe('')
    expect(store.exportFiles).toEqual({})
    expect(store.exportError).toBe('')
  })
})
