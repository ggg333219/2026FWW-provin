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

  it('把选中页随请求发出，供引擎解析「这页」', async () => {
    const modify = vi.spyOn(projectModifyApi, 'modify').mockResolvedValue({ data: {
      intent: { action: 'expand', target_ids: ['node_3'] },
      modified_nodes: [{ node_id: 'node_3', title: '空间复杂度' }],
      all_nodes: [{ node_id: 'node_3', title: '空间复杂度' }],
      new_version_no: 1,
    } })
    vi.spyOn(projectModifyApi, 'versions').mockResolvedValue({ data: { items: [{ version_no: 1 }] } })
    const store = useModifyStore()
    store.bindProject('project_1')
    store.setActiveNode('node_3')
    store.inputText = '这页加个生活案例'
    await store.sendModify([], () => {})

    expect(modify.mock.calls[0][3].activeNodeId).toBe('node_3')
    // 改完选中页跟到刚改的那页，「再改改刚才那页」不必重新点
    expect(store.activeNodeId).toBe('node_3')
  })

  it('换项目时清空选中页（上一份课件的选中页在这里没有意义）', () => {
    const store = useModifyStore()
    store.bindProject('project_1')
    store.setActiveNode('node_2')
    store.bindProject('project_2')
    expect(store.activeNodeId).toBe('')
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

  /**
   * 契约 v1.0 §3.2：AI 对话气泡切 PPT / 刷新后从后端权威读源恢复。
   * 每次 sendModify 都把推送的气泡批量 upsert 到 courseware_ai_messages；
   * loadAIMessages 再把后端存的列表覆盖回本地 messages。
   */
  it('sendModify 把 AI 对话气泡批量 upsert 到后端', async () => {
    const upsertSpy = vi.spyOn(projectModifyApi, 'upsertAIMessages').mockResolvedValue({ data: { upserted: 2 } })
    vi.spyOn(projectModifyApi, 'modify').mockResolvedValue({
      data: {
        intent: { action: 'rewrite', target_ids: ['node_2'] },
        modified_nodes: [{ node_id: 'node_2', title: '排序案例' }],
        all_nodes: [{ node_id: 'node_2', title: '排序案例' }],
        new_version_no: 1,
      },
    })
    vi.spyOn(projectModifyApi, 'versions').mockResolvedValue({ data: { items: [{ version_no: 1 }] } })
    const store = useModifyStore()
    store.bindProject('project_P')
    store.inputText = '把第二页改成生活案例'
    await store.sendModify([], () => {})
    expect(upsertSpy).toHaveBeenCalled()
    const [calledProjectId, calledMsgs] = upsertSpy.mock.calls[0]
    expect(calledProjectId).toBe('project_P')
    expect(Array.isArray(calledMsgs)).toBe(true)
    // teacher 1 + ai 执行结果 1 + ai 摘要 1 = 至少 3 条
    expect(calledMsgs.length).toBeGreaterThanOrEqual(3)
    // 字段归一：message_id / role / is_summary 等后端字段名都对得上
    expect(calledMsgs[0]).toMatchObject({ role: 'teacher', text: '把第二页改成生活案例' })
    // "已执行" 那条带 is_summary:false + version_no:new_version_no，"已更新" 那条带 is_summary:true
    // 总之应当存在一条带 version_no>=1 的 AI 摘要气泡
    expect(calledMsgs.some((m) => m.role === 'ai' && m.version_no >= 1)).toBe(true)
    expect(calledMsgs.some((m) => m.is_summary === true)).toBe(true)
  })

  /**
   * loadAIMessages：拉后端存的消息列表，覆盖本地 messages。
   * 关键场景：刷新页面 / 切回旧项目时，对话气泡应该从后端拉回来而不是丢。
   */
  it('loadAIMessages 用后端存的气泡覆盖本地', async () => {
    vi.spyOn(projectModifyApi, 'listAIMessages').mockResolvedValue({
      data: {
        messages: [
          { message_id: 'msg_seed_1', role: 'teacher', text: '把第三页案例改掉', created_at: '2026-09-23T08:00:00Z' },
          { message_id: 'msg_seed_2', role: 'ai', text: '已更新：第三页', is_summary: true, version_no: 2, created_at: '2026-09-23T08:00:01Z' },
        ],
      },
    })
    const store = useModifyStore()
    store.bindProject('project_P') // 先触发 init，清空 messages
    // 用 setMessages 直接注入脏数据，模拟"上次没清干净"
    store.messages = [{ id: 'stale', role: 'teacher', text: '残留消息', created_at: '2026-09-23T07:00:00Z' }]
    const msgs = await store.loadAIMessages('project_P')
    expect(msgs.length).toBe(2)
    expect(store.messages[0]).toMatchObject({ id: 'msg_seed_1', role: 'teacher', text: '把第三页案例改掉' })
    expect(store.messages[1]).toMatchObject({ id: 'msg_seed_2', isSummary: true, versionNo: 2 })
    // 来自后端的视为已落库，pending 队列应空
    expect(store._pendingPersist).toEqual([])
  })

  /**
   * loadLatestContext 必须并发拉最新上下文 + AI 消息——S3 进入时一次性把版本链
   * 和对话气泡都恢复成权威读源。
   */
  it('loadLatestContext 顺手拉取 AI 对话气泡（合并 latest + messages）', async () => {
    vi.spyOn(projectModifyApi, 'latestGenerationContext').mockResolvedValue({
      data: { project_id: 'project_Z', version_no: 2, page_bindings: [] },
    })
    vi.spyOn(projectModifyApi, 'listAIMessages').mockResolvedValue({
      data: { messages: [{ message_id: 'msg_z_1', role: 'teacher', text: '旧的对话', created_at: '2026-09-23T09:00:00Z' }] },
    })
    const store = useModifyStore()
    await store.loadLatestContext('project_Z')
    expect(store.projectId).toBe('project_Z')
    expect(store.currentVersionNo).toBe(2)
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].id).toBe('msg_z_1')
  })

  /**
   * _flushPendingMessages 失败时回退到 pending 队列，下次再试，避免丢消息。
   */
  it('_flushPendingMessages 失败时把消息还回队列', async () => {
    vi.spyOn(projectModifyApi, 'upsertAIMessages').mockRejectedValueOnce(new Error('network'))
    const store = useModifyStore()
    store.bindProject('project_Q')
    // 直接调内部 API 推一条消息
    const m = store._pushMessage('teacher', '测试消息')
    expect(store._pendingPersist).toHaveLength(1)
    await store._flushPendingMessages()
    // 失败 → 消息回到 pending；Pinia 会再包一层 reactive，引用会变，比内容即可
    expect(store._pendingPersist).toHaveLength(1)
    expect(store._pendingPersist[0]).toMatchObject({ id: m.id, role: 'teacher', text: '测试消息' })
  })

  it('高风险元素修改先等待确认，确认后才发送 confirmed', async () => {
    const modify = vi.spyOn(projectModifyApi, 'modify')
      .mockResolvedValueOnce({ data: {
        requires_confirmation: true,
        candidates: [{ page_number: 2, role: 'chart' }],
      } })
      .mockResolvedValueOnce({ data: {
        intent: { action: 'restyle', target_element_ids: ['el_node_2_chart'] },
        all_nodes: [{ node_id: 'node_2', title: '图表' }],
        modified_nodes: [{ node_id: 'node_2', title: '图表' }],
        new_version_no: 1,
      } })
    vi.spyOn(projectModifyApi, 'versions').mockResolvedValue({ data: { items: [{ version_no: 1 }] } })
    const store = useModifyStore()
    store.bindProject('project_1')
    store.inputText = '把第二页图表改成柱状图'
    await store.sendModify([], () => {})

    expect(store.pendingConfirmation).not.toBeNull()
    await store.confirmPending()
    expect(modify.mock.calls[1][3]).toMatchObject({ confirmed: true })
    expect(store.pendingConfirmation).toBeNull()
  })
})
