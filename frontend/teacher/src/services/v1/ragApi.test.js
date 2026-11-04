import { describe, expect, it, vi } from 'vitest'

vi.mock('./request', () => ({
  requestJson: vi.fn(async (_path, options) => JSON.parse(options.body))
}))

import { teacherRagApi } from './ragApi'

describe('knowledgeUpload 请求契约', () => {
  it('区分未提供 chunkIds 和显式空数组', async () => {
    const legacy = await teacherRagApi.knowledgeUpload({ sessionId: 'session-f04', texts: ['手动文本'] })
    expect(legacy).not.toHaveProperty('chunk_ids')
    expect(legacy.texts).toEqual(['手动文本'])

    const empty = await teacherRagApi.knowledgeUpload({ sessionId: 'session-f04', chunkIds: [] })
    expect(empty.chunk_ids).toEqual([])

    const selected = await teacherRagApi.knowledgeUpload({ sessionId: 'session-f04', chunkIds: ['f04-a'] })
    expect(selected.chunk_ids).toEqual(['f04-a'])
  })
})
