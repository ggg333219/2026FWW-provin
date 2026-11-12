// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import KnowledgeBasePanel from '../components/teacher/KnowledgeBasePanel.vue'
import { teacherV1Api } from '../services/v1'

let app
let host

beforeEach(() => {
  setActivePinia(createPinia())
  host = document.createElement('div')
  document.body.appendChild(host)
})

afterEach(() => {
  app?.unmount()
  host?.remove()
  app = null
  vi.restoreAllMocks()
})

async function searchFor(query, props = {}) {
  app = createApp({ render: () => h(KnowledgeBasePanel, { autoSearch: false, ...props }) })
  app.use(createPinia())
  app.mount(host)
  const input = host.querySelector('.search-input')
  input.value = query
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
  host.querySelector('.search-row button').click()
  await new Promise(resolve => setTimeout(resolve, 0))
  await nextTick()
}

describe('S2 高级检索状态', () => {
  it('成功返回空列表时提示无命中', async () => {
    vi.spyOn(teacherV1Api.rag, 'search').mockResolvedValue({ data: { results: [], total_results: 0 } })
    await searchFor('无关主题')
    expect(host.textContent).toContain('本次没有命中资料')
    expect(host.textContent).not.toContain('检索服务异常')
  })

  it('请求失败时提示服务异常，不把失败说成无命中', async () => {
    vi.spyOn(teacherV1Api.rag, 'search').mockRejectedValue(new Error('服务不可用'))
    await searchFor('排序算法')
    expect(host.textContent).toContain('检索服务异常')
    expect(host.textContent).not.toContain('本次没有命中资料')
  })

  it('手选片段形成参考内容后通知 S2 主界面保存本次选择', async () => {
    const packet = {
      relevant_chunks: [{ chunk_id: 'source-1', content: '分治法将问题分成较小的子问题' }],
      citations: [{ chunk_id: 'source-1', text_snippet: '分治法将问题分成较小的子问题', source_ref: '算法讲义.pdf' }]
    }
    vi.spyOn(teacherV1Api.rag, 'search').mockResolvedValue({
      data: { results: [{ chunk_id: 'source-1', content: packet.relevant_chunks[0].content, score: 0.9, source: { file_name: '算法讲义.pdf', page: 3 } }], total_results: 1 }
    })
    const fuse = vi.spyOn(teacherV1Api.rag, 'evidence').mockResolvedValue({ data: { evidence_packet: packet } })
    const onBindEvidence = vi.fn()
    await searchFor('分治法', { onBindEvidence })
    host.querySelector('.result-item input[type="checkbox"]').click()
    await nextTick()
    ;[...host.querySelectorAll('button')].find(button => button.textContent.includes('形成参考内容')).click()
    await new Promise(resolve => setTimeout(resolve, 0))
    await nextTick()
    expect(fuse).toHaveBeenCalledWith(expect.objectContaining({ selectedChunkIds: ['source-1'] }))
    expect(onBindEvidence).toHaveBeenCalledWith(expect.objectContaining({ packet }))
  })
})
