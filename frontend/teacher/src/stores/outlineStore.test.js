import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useOutlineStore } from './outlineStore'

describe('outlineStore 大纲拖拽排序', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.stubGlobal('window', { localStorage: { setItem: vi.fn(), getItem: vi.fn(), removeItem: vi.fn() } })
  })
  afterEach(() => vi.unstubAllGlobals())

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
})
