import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { projectModifyApi } from '../services/v1/projectModifyApi'
import { useModifyStore } from './modifyStore'

function createStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  }
}

beforeEach(() => {
  globalThis.window = { localStorage: createStorage() }
  setActivePinia(createPinia())
  vi.restoreAllMocks()
})

describe('modifyStore C6/C7 对话迭代', () => {
  it('把教师对追问的回答与原指令合并后再次解析', async () => {
    const modify = vi.spyOn(projectModifyApi, 'modify')
      .mockResolvedValueOnce({ data: { clarification: '要修改哪一页？', intent: { action: 'simplify' } } })
      .mockResolvedValueOnce({ data: {
        intent: { action: 'simplify', target_ids: ['node_3'] },
        modified_nodes: [{ node_id: 'node_3', title: '案例' }],
        all_nodes: [{ node_id: 'node_3', title: '案例' }],
        previous_version_no: 1,
        new_version_no: 2,
      } })
    vi.spyOn(projectModifyApi, 'versions').mockResolvedValue({ data: { items: [{ version_no: 2 }] } })
    const store = useModifyStore()
    store.bindProject('project_1')
    store.inputText = '精简一下'
    await store.sendModify([], () => {})
    store.inputText = '第三页'
    await store.sendModify([], () => {})

    expect(modify).toHaveBeenCalledTimes(2)
    expect(modify.mock.calls[1][1]).toContain('精简一下')
    expect(modify.mock.calls[1][1]).toContain('补充说明：第三页')
    expect(store.pendingClarification).toBeNull()
    expect(store.versionLabel).toBe('当前 v2 · 基于 v1 修改')
  })

  it('使用实际修改节点生成摘要和高亮集合', async () => {
    vi.spyOn(projectModifyApi, 'modify').mockResolvedValue({ data: {
      intent: { action: 'rewrite', target_ids: ['node_2'] },
      modified_nodes: [{ node_id: 'node_2', title: '排序案例' }],
      all_nodes: [{ node_id: 'node_2', title: '排序案例' }],
      new_version_no: 1,
    } })
    vi.spyOn(projectModifyApi, 'versions').mockResolvedValue({ data: { items: [{ version_no: 1 }] } })
    const store = useModifyStore()
    store.bindProject('project_1')
    store.inputText = '重写第二页'
    await store.sendModify([], () => {})

    expect(store.recentlyModifiedIds).toEqual(['node_2'])
    expect(store.messages.some((message) => message.text === '已更新：排序案例')).toBe(true)
  })

  it('限制超长输入并支持失败后重新填写', async () => {
    vi.spyOn(projectModifyApi, 'modify').mockRejectedValue(new Error('服务暂不可用'))
    const store = useModifyStore()
    store.bindProject('project_1')
    store.inputText = 'x'.repeat(501)
    expect(store.canSend).toBe(false)

    store.inputText = '精简第三页'
    await store.sendModify([], () => {})
    expect(store.lastFailedInstruction).toBe('精简第三页')
    store.retryLast()
    expect(store.inputText).toBe('精简第三页')
    expect(store.error).toBe('')
  })

  /**
   * 契约 v1.0 §3.2：切 PPT / 新建课件后必须清空"上一个课件"的 AI 对话气泡，
   * 否则切回会看到之前残留。之前的 bindProject 只在 !projectId 时清，导致
   * A→B 切换时 messages 保留了 A 的内容。修复后 projectId 变化必清空。
   */
  it('切 PPT 时清空上一个项目的 AI 对话气泡', async () => {
    vi.spyOn(projectModifyApi, 'modify').mockResolvedValue({
      data: {
        intent: { action: 'simplify', target_ids: ['node_3'] },
        modified_nodes: [{ node_id: 'node_3', title: '案例' }],
        all_nodes: [{ node_id: 'node_3', title: '案例' }],
        previous_version_no: 1,
        new_version_no: 2,
      },
    })
    vi.spyOn(projectModifyApi, 'versions').mockResolvedValue({ data: { items: [{ version_no: 2 }] } })
    const store = useModifyStore()
    store.bindProject('project_A')
    store.inputText = '精简 A 课件第三页'
    await store.sendModify([], () => {})
    expect(store.messages.length).toBeGreaterThan(0)
    expect(store.currentVersionNo).toBeGreaterThan(0)

    // 切到 B（不带 localStorage 缓存）
    store.bindProject('project_B')
    expect(store.projectId).toBe('project_B')
    expect(store.messages).toEqual([])
    expect(store.currentVersionNo).toBe(0)
    expect(store.basedOnVersionNo).toBe(0)
    expect(store.lastIntent).toBeNull()
    expect(store.undoStack).toEqual([])
    expect(store.redoStack).toEqual([])
    expect(store.recentlyModifiedIds).toEqual([])
  })

  /**
   * 契约 v1.0 §3.2：进入 S3 时按 project_id 拉 /latest-generation-context
   * 作为权威读源——version_no / pageBindings 来自后端最新 CoursewareVersion，
   * AI 对话气泡后端不存所以重置为空。
   */
  it('loadLatestContext 用后端权威读源重置对话与版本号', async () => {
    vi.spyOn(projectModifyApi, 'latestGenerationContext').mockResolvedValue({
      data: {
        project_id: 'project_X',
        version_no: 3,
        latest_version: {
          version_id: 'v_3',
          version_no: 3,
          modify_instruction: '把第三页改成生活案例',
          version_summary: '已更新第三页',
          created_at: '2026-09-23T10:00:00Z',
        },
        page_bindings: [
          { page_id: 'page_003', evidence_refs: ['chunk_001', 'chunk_005'] },
        ],
      },
    })
    const store = useModifyStore()
    // 先模拟 A 留下的对话残留
    store.bindProject('project_A')
    store.inputText = '把 A 课件的封面换掉'
    await store.sendModify([], () => {})
    expect(store.messages.length).toBeGreaterThan(0)

    const data = await store.loadLatestContext('project_X')
    expect(projectModifyApi.latestGenerationContext).toHaveBeenCalledWith('project_X')
    expect(data.version_no).toBe(3)
    expect(store.projectId).toBe('project_X')
    expect(store.messages).toEqual([])
    expect(store.currentVersionNo).toBe(3)
    expect(store.basedOnVersionNo).toBe(2)
    expect(store.versionHistory).toEqual([
      expect.objectContaining({ version_no: 3, modify_instruction: '把第三页改成生活案例' }),
    ])
    expect(store.pageBindings).toEqual([
      { page_id: 'page_003', evidence_refs: ['chunk_001', 'chunk_005'] },
    ])
  })

  /**
   * 后端不可用（500 / 网络中断）时 loadLatestContext 必须降级而非抛错——
   * S3 不应被后端抖动打断进入流程。
   */
  it('loadLatestContext 在后端不可用时降级而不抛错', async () => {
    vi.spyOn(projectModifyApi, 'latestGenerationContext').mockRejectedValue(new Error('network down'))
    const store = useModifyStore()
    store.bindProject('project_Y')
    store.inputText = 'A 的修改'
    await store.sendModify([], () => {})

    const data = await store.loadLatestContext('project_Y')
    expect(data).toBeNull()
    // 即便后端挂了，projectId 仍按请求切换，messages 走 bindProject 重置分支
    expect(store.projectId).toBe('project_Y')
    expect(store.messages).toEqual([])
  })
})
