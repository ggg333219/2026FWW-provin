import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useGenerationStore } from './generationStore'

function createStorage() {
  const values = new Map()
  const storage = {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => {
      values.set(key, String(value))
      Object.defineProperty(storage, key, { value: String(value), enumerable: true, configurable: true, writable: true })
    },
    removeItem: (key) => {
      values.delete(key)
      delete storage[key]
    }
  }
  return storage
}

beforeEach(() => {
  const localStorage = createStorage()
  globalThis.window = { localStorage }
  globalThis.fetch = () => Promise.reject(new Error('backend unreachable'))
  setActivePinia(createPinia())
})

describe('generationStore S3 到 S4 generation_id 透传', () => {
  it('保存生成 ID 到 Store 和统一的 localStorage key', () => {
    const store = useGenerationStore()

    expect(store.setLastGenId(' gen_abc123 ')).toBe('gen_abc123')
    expect(store.lastGenId).toBe('gen_abc123')
    expect(window.localStorage.getItem('fuww_last_gen_id')).toBe('gen_abc123')
  })

  it('保存生成任务 task_id 供状态接口查询', () => {
    const store = useGenerationStore()

    expect(store.setLastTaskId(' task_abc123 ')).toBe('task_abc123')
    expect(store.lastTaskId).toBe('task_abc123')
    expect(window.localStorage.getItem('fuww_last_task_id')).toBe('task_abc123')
  })

  it('新 Store 可在刷新后从 localStorage 恢复生成 ID', () => {
    window.localStorage.setItem('fuww_last_gen_id', 'gen_restored')
    const store = useGenerationStore()

    expect(store.restoreLastGenId()).toBe('gen_restored')
    expect(store.lastGenId).toBe('gen_restored')
  })

  it('空生成 ID 不覆盖已有的可用状态', () => {
    const store = useGenerationStore()
    store.setLastGenId('gen_kept')

    expect(store.setLastGenId('')).toBe('')
    expect(store.lastGenId).toBe('gen_kept')
    expect(window.localStorage.getItem('fuww_last_gen_id')).toBe('gen_kept')
  })

  it('reset 清空 S3 状态、生成 ID 和所有预览缓存', () => {
    const store = useGenerationStore()
    store.setNodes([{ node_id: 'n1', title: '旧课件' }])
    store.setLastGenId('gen_old')
    store.previewHtml = '<html>旧预览</html>'
    window.localStorage.setItem('fuww_preview_cache:draft', 'draft-cache')
    window.localStorage.setItem('fuww_preview_cache:gen_old', 'gen-cache')

    store.reset()

    expect(store.currentScriptNodes).toEqual([])
    expect(store.lastGenId).toBe('')
    expect(store.lastTaskId).toBe('')
    expect(store.previewHtml).toBe('')
    expect(window.localStorage.getItem('fuww_last_gen_id')).toBeNull()
    expect(window.localStorage.getItem('fuww_last_task_id')).toBeNull()
    expect(window.localStorage.getItem('fuww_preview_cache:draft')).toBeNull()
    expect(window.localStorage.getItem('fuww_preview_cache:gen_old')).toBeNull()
  })

  it('全流程生成任务返回真实 ID，并在完成后回填节点', async () => {
    const store = useGenerationStore()
    const task = await store.createCoursewareGeneration({
      course_id: 'course_handoff_test',
      title: '排序算法',
      evidence_packet: { query: '排序算法', relevant_chunks: [] }
    })

    expect(task.task_id).toBeTruthy()
    expect(store.lastGenId).toBeTruthy()
    expect(window.localStorage.getItem('fuww_last_gen_id')).toBe(store.lastGenId)

    await store.waitForCoursewareGeneration(task.task_id, { intervalMs: 50, maxAttempts: 100 })
    expect(store.currentScriptNodes.length).toBeGreaterThan(0)
    expect(store.currentScript).toContain('核心')
  })
})

describe('预览持久化与版本快照恢复', () => {
  it('inline 渲染当前节点并写入 previewHtml 与草稿缓存', async () => {
    const store = useGenerationStore()
    store.setNodes([
      { nodeId: 'n1', title: '封面', node_type: 'cover', subtitle: '测试课件' },
      { nodeId: 'n2', title: '正文', node_type: 'slide', scriptText: '正文脚本内容' }
    ])

    const html = await store.renderCoursewarePreview('测试课件')
    expect(html).toContain('class="slide')
    expect(store.previewHtml).toBe(html)
    expect(store.previewLoading).toBe(false)

    const cache = JSON.parse(window.localStorage.getItem('fuww_preview_cache:draft'))
    expect(cache).toBeTruthy()
    expect(cache.html).toContain('slide')
    expect(cache.nodes.length).toBe(2)
  })

  it('按 gen_id 渲染版本快照并记录版本号', async () => {
    const store = useGenerationStore()
    const task = await store.createCoursewareGeneration({
      course_id: 'course_snapshot_test',
      title: '快照课件',
      evidence_packet: { query: '快照课件', relevant_chunks: [] }
    })
    await store.waitForCoursewareGeneration(task.task_id, { intervalMs: 50, maxAttempts: 100 })
    expect(store.lastGenId).toBeTruthy()

    const html = await store.renderCoursewarePreview('课件预览', { genId: store.lastGenId })
    expect(html).toContain('class="slide')
    expect(store.previewGenId).toBe(store.lastGenId)
    expect(store.previewVersion).toBeGreaterThan(0)
  })

  it('restorePreview：后端无该 gen_id 快照时保留本地缓存预览', async () => {
    const store = useGenerationStore()
    store.setNodes([{ nodeId: 'n1', title: '缓存页', content: '缓存内容' }])
    await store.renderCoursewarePreview('课件')
    expect(store.previewHtml).toContain('slide')

    // 该 gen_id 在 mock 中无快照：应回退到草稿缓存，而不是空态覆盖
    const html = await store.restorePreview('gen_no_snapshot')
    expect(html).toContain('slide')
    expect(store.previewHtml).toContain('slide')
  })

  it('restorePreview：按 gen_id 从版本快照恢复完整预览', async () => {
    const store = useGenerationStore()
    const task = await store.createCoursewareGeneration({
      course_id: 'course_restore_test',
      title: '恢复课件',
      evidence_packet: { query: '恢复课件', relevant_chunks: [] }
    })
    await store.waitForCoursewareGeneration(task.task_id, { intervalMs: 50, maxAttempts: 100 })

    store.clearPreview()
    const html = await store.restorePreview(store.lastGenId)
    expect(html).toContain('class="slide')
    expect(store.previewVersion).toBeGreaterThan(0)
  })

  it('clearPreview 清空状态与本地缓存', async () => {
    const store = useGenerationStore()
    store.setNodes([{ nodeId: 'n1', title: 'x', content: 'y' }])
    await store.renderCoursewarePreview('课件')
    expect(window.localStorage.getItem('fuww_preview_cache:draft')).toBeTruthy()

    store.clearPreview()
    expect(store.previewHtml).toBe('')
    expect(store.previewLoading).toBe(false)
    expect(store.previewGenId).toBe('')
    expect(window.localStorage.getItem('fuww_preview_cache:draft')).toBeNull()
  })

  it('新链路：intent/evidence 透传 → 版本快照 → 全链路预览', async () => {
    const store = useGenerationStore()
    const task = await store.createCoursewareGeneration({
      course_id: 'course_chain_intent',
      title: '排序算法',
      intent: { topic: '排序算法', duration_minutes: 45, style: '案例驱动', target_student: '大一' },
      evidence_packet: { query: '排序算法', relevant_chunks: [{ chunk_id: 'c1', content: '冒泡排序步骤' }] }
    })
    expect(task.task_id).toBeTruthy()

    const status = await store.waitForCoursewareGeneration(task.task_id, { intervalMs: 50, maxAttempts: 100 })
    // Mock 回显 S1 意图 / S2 证据，断言 S1→S4 链路透传未被丢弃
    expect(status.intent).toMatchObject({ topic: '排序算法' })
    expect(status.evidence_packet?.query).toBe('排序算法')
    expect(store.currentScriptNodes.length).toBeGreaterThan(0)
    expect(store.lastGenId).toBeTruthy()

    // 生成完成 → 按 gen_id 从版本快照恢复整棵树预览（刷新/回看不丢失）
    const html = await store.renderCoursewarePreview('排序算法', { genId: store.lastGenId })
    expect(html).toContain('class="slide')
    expect(store.previewGenId).toBe(store.lastGenId)
    expect(store.previewVersion).toBeGreaterThan(0)
  })
})
