import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { projectModifyApi } from '../services/v1/projectModifyApi'
import { useCoursewareProjectStore } from './coursewareProjectStore'

function createStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  }
}

describe('courseware project draft isolation', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    globalThis.window = { localStorage: createStorage() }
    setActivePinia(createPinia())
  })

  it('clears the previous project draft and pending autosave when switching projects', () => {
    const store = useCoursewareProjectStore()
    store.setActive('project-a')
    store.draft = { title: 'A draft' }
    store._lastDraft = store.draft
    store._timer = setTimeout(() => {}, 60_000)

    store.setActive('project-b')

    expect(store.projectId).toBe('project-b')
    expect(store.draft).toBeNull()
    expect(store._lastDraft).toBeNull()
    expect(store._timer).toBe(0)
    expect(store.saveState).toBe('idle')
  })

  it('does not attach a late save response to the newly active project', async () => {
    let resolveSave
    vi.spyOn(projectModifyApi, 'saveDraft').mockImplementation(() => new Promise((resolve) => {
      resolveSave = resolve
    }))
    const store = useCoursewareProjectStore()
    store.setActive('project-a')

    const pendingSave = store.saveNow({ title: 'A draft' })
    store.setActive('project-b')
    await new Promise((resolve) => setTimeout(resolve, 0))
    resolveSave({ data: { saved_at: '2026-10-07T00:00:00Z' } })
    await pendingSave

    expect(projectModifyApi.saveDraft).toHaveBeenCalledWith('project-a', { title: 'A draft' })
    expect(store.projectId).toBe('project-b')
    expect(store.draft).toBeNull()
    expect(store.savedAt).toBe('')
  })

  it('does not activate a project when its resume response is stale', async () => {
    let resolveContext
    vi.spyOn(projectModifyApi, 'context').mockImplementation(() => new Promise((resolve) => {
      resolveContext = resolve
    }))
    const store = useCoursewareProjectStore()
    store.setActive('project-c')

    const pendingResume = store.resume('project-b', () => false)
    resolveContext({ data: { project: { id: 'project-b' }, draft: { title: 'stale B' } } })
    await pendingResume

    expect(store.projectId).toBe('project-c')
    expect(store.draft).toBeNull()
  })

  it('queues saves with the project ID captured before a project switch', async () => {
    const calls = []
    vi.spyOn(projectModifyApi, 'saveDraft').mockImplementation((projectId, draft) => new Promise((resolve) => {
      calls.push({ projectId, draft, resolve })
    }))
    const store = useCoursewareProjectStore()
    store.setActive('project-a')
    const first = store.saveNow({ title: 'A1' })
    const second = store.saveNow({ title: 'A2' })
    store.setActive('project-b')
    await new Promise((resolve) => setTimeout(resolve, 0))
    calls[0].resolve({ data: {} })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(calls[1].projectId).toBe('project-a')
    calls[1].resolve({ data: {} })
    await Promise.all([first, second])
    expect(store.projectId).toBe('project-b')
    expect(store.draft).toBeNull()
  })
})
