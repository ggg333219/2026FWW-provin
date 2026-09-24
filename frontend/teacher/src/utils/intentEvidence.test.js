import { describe, expect, it } from 'vitest'
import { buildIntentEvidenceQuery, evidenceIds } from './intentEvidence'

describe('S1 意图驱动的自动证据检索', () => {
  it('用主题、知识点、难点和对象组成稳定查询并去重', () => {
    expect(buildIntentEvidenceQuery({
      topic: 'TCP 三次握手',
      knowledge_points: ['SYN 与 ACK', 'TCP 三次握手'],
      key_difficulties: ['为什么不能两次握手'],
      target_student: '大一学生',
    })).toBe('TCP 三次握手；SYN 与 ACK；为什么不能两次握手；大一学生')
  })

  it('合并引用和检索块 ID，供整份草稿自动绑定', () => {
    expect(evidenceIds({
      citations: [{ chunk_id: 'a' }],
      relevant_chunks: [{ chunk_id: 'a' }, { chunk_id: 'b' }],
    })).toEqual(['a', 'b'])
  })
})
