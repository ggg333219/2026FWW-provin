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
    resolveSave({ data: { saved_at: '2026-10-07T00:00:00Z' } })
    await pendingSave

    expect(projectModifyApi.saveDraft).toHaveBeenCalledWith('project-a', { title: 'A draft' })
    expect(store.projectId).toBe('project-b')
    expect(store.draft).toBeNull()
    expect(store.savedAt).toBe('')
  })
})
