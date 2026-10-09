import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useContentStore } from './contentStore'
import { teacherV1Api } from '../services/v1'

vi.mock('../services/v1', () => ({
  teacherV1Api: { generation: { modifyContent: vi.fn(), getContentStatus: vi.fn() } },
}))

beforeEach(() => {
  setActivePinia(createPinia())
  const values = new Map()
  globalThis.window = {
    localStorage: {
      getItem: (key) => values.get(key) || null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    },
  }
  vi.clearAllMocks()
})

describe('contentStore script editing', () => {
  it('saves a manual edit and clears stale segments', () => {
    const store = useContentStore()
    store.nodesContent.n1 = { node_id: 'n1', script: '原稿', segments: [{ text: '旧分段' }] }
    store.saveNodeScript('n1', '新稿')
    expect(store.nodesContent.n1).toMatchObject({ script: '新稿', lecture_script: '新稿', segments: [] })
    expect(JSON.parse(window.localStorage.getItem('fuww_content_cache')).nodesContent.n1.script).toBe('新稿')
  })

  it('uses the current script for AI revision and rejects fallback', async () => {
    const store = useContentStore()
    store.nodesContent.n1 = { node_id: 'n1', script: '原稿' }
    teacherV1Api.generation.modifyContent.mockResolvedValueOnce({ data: {
      node_id: 'n1', script: '改后讲稿', used_fallback: false,
    } })
    const result = await store.modifyNode({ node_id: 'n1', title: '排序', message: '精简', course_name: '算法' })
    expect(teacherV1Api.generation.modifyContent).toHaveBeenCalledWith({
      node_id: 'n1', title: '排序', script: '原稿', message: '精简', course_name: '算法',
    })
    expect(result.script).toBe('改后讲稿')
    expect(store.nodesContent.n1.script).toBe('原稿')

    teacherV1Api.generation.modifyContent.mockResolvedValueOnce({ data: {
      node_id: 'n1', script: '占位', used_fallback: true,
    } })
    await expect(store.modifyNode({ node_id: 'n1', message: '再改' })).rejects.toThrow('原稿未修改')
    expect(store.nodesContent.n1.script).toBe('原稿')
  })

  it('keeps an edited node when background generation reports an older script', async () => {
    const store = useContentStore()
    store.content_id = 'content-1'
    store.status = 'generating'
    store.nodesContent.n1 = { node_id: 'n1', script: '初稿' }
    store.saveNodeScript('n1', '教师改稿')
    teacherV1Api.generation.getContentStatus.mockResolvedValue({ data: {
      status: 'generating', nodes: [
        { node_id: 'n1', script: '旧生成稿' },
        { node_id: 'n2', script: '第二节点初稿' },
      ],
    } })
    await store.pollStatus()
    expect(store.nodesContent.n1.script).toBe('教师改稿')
    expect(store.nodesContent.n2.script).toBe('第二节点初稿')
  })
})
