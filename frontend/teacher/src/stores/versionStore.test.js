import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useVersionStore } from './versionStore'
import { teacherV1Api } from '../services/v1'
import { projectModifyApi } from '../services/v1/projectModifyApi'

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
  vi.restoreAllMocks()
  const localStorage = createStorage()
  globalThis.window = { localStorage }
  // 后端不可达 → requestJson 回退 Mock（契约路径 /api/v1/exp）
  globalThis.fetch = () => Promise.reject(new Error('backend unreachable'))
  setActivePinia(createPinia())
})

describe('versionStore S4 导出闭环（Mock）', () => {
  it('项目版本可查看并按版本 ID 克隆分叉，保留旧历史', async () => {
    const outline = {
      outline_id: 'outline_tcp',
      outline_version: 2,
      status: 'confirmed',
      nodes: [{ node_id: 'outline_1', title: 'TCP 连接建立' }],
    }
    const versions = [
      { version_id: 'ver_2', version_no: 2, version_summary: '第二版', created_at: '2026-09-23' },
      { version_id: 'ver_1', version_no: 1, version_summary: '首版', created_at: '2026-09-22' },
    ]
    vi.spyOn(projectModifyApi, 'versions').mockResolvedValue({ data: { items: versions } })
    vi.spyOn(projectModifyApi, 'versionDetail').mockImplementation(async (_projectId, versionId) => ({ data: {
      version_id: versionId,
      version_no: versionId === 'ver_1' ? 1 : 2,
      change_note: versionId === 'ver_1' ? '首版' : '第二版',
      snapshot: {
        content: [{ node_id: 'tcp', title: versionId === 'ver_1' ? '握手' : 'TCP 三次握手' }],
        outline,
      },
    } }))
    const rollback = vi.spyOn(projectModifyApi, 'rollback').mockResolvedValue({ data: { base_version_no: 1, new_draft_version_no: 3 } })

    const store = useVersionStore()
    await store.loadProjectVersions('proj_tcp')
    const detail = await store.loadProjectVersion('proj_tcp', 1)
    expect(detail.nodes[0].title).toBe('握手')
    expect(detail.outline).toEqual(outline)
    await store.rollbackProject('proj_tcp', 1)
    expect(rollback).toHaveBeenCalledWith('proj_tcp', 'ver_1')
    expect(store.versions).toHaveLength(2)
  })

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
    store.exportQualityReport = { status: 'passed' }

    store.resetExport()
    expect(store.exportJobId).toBe('')
    expect(store.exportStatus).toBe('idle')
    expect(store.exportDownloadUrl).toBe('')
    expect(store.exportFiles).toEqual({})
    expect(store.exportError).toBe('')
    expect(store.exportQualityReport).toBeNull()
  })

  it('polling stores the PPTX quality report returned with export status', async () => {
    const store = useVersionStore()
    vi.spyOn(teacherV1Api.version, 'exportCreate').mockResolvedValue({
      job_id: 'exp_quality', status: 'pending'
    })
    vi.spyOn(teacherV1Api.version, 'exportStatus').mockResolvedValue({
      job_id: 'exp_quality',
      status: 'done',
      download_url: '/download/exp_quality.pptx',
      files: { pptx: '/download/exp_quality.pptx', docx: '/download/exp_quality.docx' },
      quality_report: {
        status: 'passed_with_warnings',
        slide_count: 3,
        findings: [{
          code: 'text_may_overflow', severity: 'warning',
          message: '文本可能超出文本框容量。', slide_number: 2
        }]
      }
    })

    await store.startExport('generation-quality', 'pptx')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(store.exportStatus).toBe('done')
    expect(store.exportQualityReport.status).toBe('passed_with_warnings')
    expect(store.exportQualityReport.findings[0].slide_number).toBe(2)
    expect(store.exportFiles.docx).toContain('/download/exp_quality.docx')
  })
})
