import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useOutlineStore } from './outlineStore'
import { teacherV1Api } from '../services/v1'

describe('outlineStore 大纲拖拽排序', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('window', { localStorage: { setItem: vi.fn(), getItem: vi.fn(), removeItem: vi.fn() } })
  })

  it('保留 AI 回退状态并将其写入本地恢复快照', () => {
    const setItem = vi.fn()
    vi.stubGlobal('window', { localStorage: { setItem, getItem: vi.fn(), removeItem: vi.fn() } })
    const store = useOutlineStore()

    store._applyOutlineData({
      outline_id: 'outline_fallback',
      used_fallback: true,
      fallback_reason: 'timeout',
      nodes: [{ node_id: 'node_001', title: '本地兜底节点' }],
    })
    store._persist()

    expect(store.usedFallback).toBe(true)
    expect(store.fallbackReason).toBe('timeout')
    expect(store.fallbackNotice).toContain('AI 请求超时')
    expect(store.fallbackNotice).toContain('最初使用本地兜底生成')
    expect(store.fallbackNotice).toContain('继续手动编辑')
    expect(JSON.parse(setItem.mock.calls.at(-1)[1])).toMatchObject({
      used_fallback: true,
      fallback_reason: 'timeout',
    })
  })

  it('AI 成功大纲不显示回退提示，兜底大纲仍可编辑并保存', async () => {
    const save = vi.spyOn(teacherV1Api.outline, 'save').mockResolvedValue({
      data: { outline_version: 2, status: 'draft' },
    })
    const store = useOutlineStore()
    store._applyOutlineData({
      outline_id: 'outline_generated',
      used_fallback: false,
      nodes: [{ node_id: 'node_001', title: 'AI 生成节点', summary: '摘要' }],
    })
    expect(store.fallbackNotice).toBe('')

    store._applyOutlineData({
      outline_id: 'outline_fallback',
      used_fallback: true,
      fallback_reason: 'timeout',
      nodes: [{ node_id: 'node_001', title: '兜底节点', summary: '摘要' }],
    })
    store.updateNode('node_001', { title: '教师已编辑' })
    await store.saveVersion()

    expect(store.nodes[0].title).toBe('教师已编辑')
    expect(store.canEdit).toBe(true)
    expect(save).toHaveBeenCalledWith('outline_fallback', expect.objectContaining({
      nodes: [expect.objectContaining({ title: '教师已编辑' })],
    }))
  })
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('将节点移动到目标位置并连续更新 order', () => {
    const store = useOutlineStore()
    store.nodes = [
      { node_id: 'a', order: 1 },
      { node_id: 'b', order: 2 },
      { node_id: 'c', order: 3 },
    ]

    store.moveNodeToIndex('a', 2)

    expect(store.nodes.map((node) => node.node_id)).toEqual(['b', 'c', 'a'])
    expect(store.nodes.map((node) => node.order)).toEqual([1, 2, 3])
  })

  it('已确认的大纲仍可重新排序', () => {
    const store = useOutlineStore()
    store.status = 'confirmed'
    store.nodes = [
      { node_id: 'a', order: 1 },
      { node_id: 'b', order: 2 },
      { node_id: 'c', order: 3 },
    ]

    store.moveNodeToIndex('c', 0)

    expect(store.canReorder).toBe(true)
    expect(store.nodes.map((node) => node.node_id)).toEqual(['c', 'a', 'b'])
    expect(store.nodes.map((node) => node.order)).toEqual([1, 2, 3])
  })

  it('回滚快照恢复为可编辑分支，首次保存基于服务端最新版本追加', async () => {
    vi.spyOn(teacherV1Api.outline, 'get').mockResolvedValue({ data: { outline_version: 7 } })
    const save = vi.spyOn(teacherV1Api.outline, 'save').mockResolvedValue({ data: { outline_version: 8, status: 'draft' } })
    const store = useOutlineStore()
    store.restoreEditableSnapshot({
      outline_id: 'outline_tcp',
      outline_version: 2,
      status: 'confirmed',
      title: 'TCP',
      nodes: [{ node_id: 'a', order: 1, title: '三次握手', summary: '连接建立', estimated_duration_minutes: 5 }],
    })

    expect(store.canEdit).toBe(true)
    expect(store.forked_from_version).toBe(2)
    store.updateNode('a', { title: 'TCP 三次握手' })
    await store.saveVersion()

    expect(save).toHaveBeenCalledWith('outline_tcp', expect.objectContaining({ base_version: 7 }))
    expect(store.outline_version).toBe(8)
    expect(store.forked_from_version).toBe(0)
  })
})
