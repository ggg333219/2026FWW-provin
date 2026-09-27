import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearLegacyResumeDraft,
  clearResumeDraft,
  readResumeDraft,
  resumeDraftKey,
  writeResumeDraft,
} from './coursewareDraft'

function createStorage() {
  const values = new Map()
  const storage = {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  }
  return storage
}

let storage

beforeEach(() => {
  storage = createStorage()
  globalThis.window = { localStorage: storage }
})

describe('coursewareDraft 草稿快照按项目归属', () => {
  it('写入后可按同一 projectId 读回，且快照自带归属标记', () => {
    writeResumeDraft('proj_a', { outline: { outline_id: 'o1' } })

    const draft = readResumeDraft('proj_a')
    expect(draft.project_id).toBe('proj_a')
    expect(draft.outline.outline_id).toBe('o1')
  })

  it('读取其他项目不会拿到本项目的快照，也不会清掉它的数据', () => {
    writeResumeDraft('proj_a', { outline: { outline_id: 'o1' } })

    expect(readResumeDraft('proj_b')).toBe(null)
    expect(readResumeDraft('proj_a').outline.outline_id).toBe('o1')
  })

  it('历史遗留的无归属快照（写死全局 key）不再被读取', () => {
    storage.setItem('fuww_courseware_resume_draft', JSON.stringify({ outline: { outline_id: 'legacy' } }))

    expect(readResumeDraft('proj_a')).toBe(null)
  })

  it('归属标记对不上的快照会被清除', () => {
    storage.setItem(resumeDraftKey('proj_a'), JSON.stringify({ project_id: 'proj_b', outline: { outline_id: 'o1' } }))

    expect(readResumeDraft('proj_a')).toBe(null)
    expect(storage.getItem(resumeDraftKey('proj_a'))).toBe(null)
  })

  it('无 projectId 时不读写（避免落入无归属的全局 key）', () => {
    writeResumeDraft('', { outline: { outline_id: 'o1' } })

    expect(storage.getItem('fuww_courseware_resume_draft')).toBe(null)
    expect(readResumeDraft('')).toBe(null)
  })

  it('clearResumeDraft 只清当前项目，clearLegacyResumeDraft 只清历史全局 key', () => {
    writeResumeDraft('proj_a', { outline: { outline_id: 'o1' } })
    writeResumeDraft('proj_b', { outline: { outline_id: 'o2' } })
    storage.setItem('fuww_courseware_resume_draft', JSON.stringify({ outline: { outline_id: 'legacy' } }))

    clearResumeDraft('proj_a')
    expect(readResumeDraft('proj_a')).toBe(null)
    expect(readResumeDraft('proj_b').outline.outline_id).toBe('o2')

    clearLegacyResumeDraft()
    expect(storage.getItem('fuww_courseware_resume_draft')).toBe(null)
    expect(readResumeDraft('proj_b').outline.outline_id).toBe('o2')
  })
})
