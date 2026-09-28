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
})
