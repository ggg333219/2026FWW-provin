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
})
