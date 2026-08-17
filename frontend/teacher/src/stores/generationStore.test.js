import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useGenerationStore } from './generationStore'

function createStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key)
  }
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
