// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, h, nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import S2MaterialWorkspace from '../components/teacher/S2MaterialWorkspace.vue'
import { useMaterialStore } from '../stores/materialStore'
import { intentStorageKey } from '../stores/intentStore'
import { buildIntentEvidenceQuery } from './intentEvidence'

let app
let host
let router

const packet = (id, text = '可追溯的资料片段') => ({
  relevant_chunks: [{ chunk_id: id, content: text }],
  citations: []
})

function storage(values = {}) {
  const map = new Map(Object.entries(values))
  return {
    getItem: (key) => map.get(key) || null,
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
    clear: () => map.clear()
  }
}

async function mountWorkspace({ intent, evidence = [], materials = [], setupStore = null } = {}) {
  const sessionId = 'sess_workspace'
  const projectId = 'unscoped'
  window.localStorage.setItem(intentStorageKey('fuww_workflow_session_id', projectId), sessionId)
  window.localStorage.setItem(intentStorageKey('fuww_s1_conversation', projectId), JSON.stringify({
    sessionId,
    messages: [],
    intentSummary: intent,
    sessionStatus: 'confirmed',
    intentId: 'intent_test'
  }))
  window.localStorage.setItem(`fuww_s2_bound_evidence:${sessionId}`, JSON.stringify(evidence))

  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useMaterialStore()
  store.materials = materials
  store.loadMaterials = vi.fn().mockResolvedValue(undefined)
  setupStore?.(store)

  router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/s2', component: S2MaterialWorkspace }] })
  await router.push('/s2')
  await router.isReady()
  host = document.createElement('div')
  document.body.appendChild(host)
  app = createApp({ render: () => h(S2MaterialWorkspace) })
  app.use(pinia)
  app.use(router)
  app.mount(host)
  await new Promise(resolve => setTimeout(resolve, 0))
  await nextTick()
  return store
}

beforeEach(() => {
  Object.defineProperty(window, 'localStorage', { value: storage(), configurable: true })
})

afterEach(() => {
  app?.unmount()
  host?.remove()
  app = null
  host = null
  router = null
  vi.restoreAllMocks()
})

describe('S2MaterialWorkspace 自动检索编排', () => {
  it('相同 query 只复用当前 session 的自动证据，不重复检索', async () => {
    const intent = { topic: '快速排序', knowledge_points: ['复杂度'] }
    const query = buildIntentEvidenceQuery(intent)
    const store = await mountWorkspace({
      intent,
      evidence: [{ id: 'auto-old', query, sourceType: 'automatic', sessionId: 'sess_workspace', nodeRef: '整份PPT草稿', packet: packet('same') }],
      setupStore: (store) => { store.generateEvidence = vi.fn() }
    })

    expect(store.generateEvidence).not.toHaveBeenCalled()
    expect(host.textContent).toContain('当前采用')
    expect(host.textContent).not.toContain('检索服务异常')
  })

  it('S1 query 变化后不复用旧自动证据，并用新 query 发起检索', async () => {
    const intent = { topic: '归并排序', knowledge_points: ['稳定性'] }
    const calls = []
    const store = await mountWorkspace({
      intent,
      evidence: [{ id: 'auto-old', query: '旧主题', sourceType: 'automatic', sessionId: 'sess_workspace', nodeRef: '整份PPT草稿', packet: packet('old') }],
      setupStore: (store) => {
        store.generateEvidence = vi.fn(async (params) => {
          calls.push(params)
          return packet('new')
        })
      }
    })
    await nextTick()
    expect(buildIntentEvidenceQuery(intent)).not.toBe('旧主题')
    expect(calls).toHaveLength(1)
    expect(calls[0]).toEqual(expect.objectContaining({ query: buildIntentEvidenceQuery(intent), sourceType: 'automatic' }))
    expect(host.textContent).not.toContain('旧主题')
  })

  it('相同 query 但不同 session 不复用另一教学任务的自动证据', async () => {
    const intent = { topic: '动态规划' }
    const calls = []
    const store = await mountWorkspace({
      intent,
      evidence: [{ id: 'auto-other-session', query: buildIntentEvidenceQuery(intent), sourceType: 'automatic', sessionId: 'sess_other', nodeRef: '整份PPT草稿', packet: packet('other') }],
      setupStore: (store) => {
        store.generateEvidence = vi.fn(async (params) => {
          calls.push(params)
          return packet('current')
        })
      }
    })

    expect(calls).toHaveLength(1)
    expect(calls[0].query).toBe(buildIntentEvidenceQuery(intent))
    expect(store.evidencePackets).not.toContainEqual(expect.objectContaining({ query: buildIntentEvidenceQuery(intent), sourceType: 'automatic' }))
  })

  it('手动重新检索按索引后检索的顺序执行，并传递当前 session', async () => {
    const intent = { topic: '二叉树', knowledge_points: ['遍历'] }
    const order = []
    const store = await mountWorkspace({
      intent,
      materials: [{ id: 'm1', chunks: [{ chunkId: 'chunk-1', content: '树的遍历', sessionRegistered: true }] }],
      setupStore: (store) => {
        store.indexKnowledgeBase = vi.fn(async (params) => {
          order.push(['index', params])
          return { status: 'done', chunk_count: 1 }
        })
        store.generateEvidence = vi.fn(async (params) => {
          order.push(['evidence', params])
          return packet('indexed')
        })
      }
    })

    const retry = [...host.querySelectorAll('button')].find(button => button.textContent.includes('重新检索'))
    expect(retry).toBeTruthy()
    order.length = 0
    retry.click()
    await new Promise(resolve => setTimeout(resolve, 0))
    await nextTick()

    expect(order.map(item => item[0])).toEqual(['index', 'evidence'])
    expect(order[0][1]).toEqual({ sessionId: 'sess_workspace' })
    expect(order[1][1]).toEqual(expect.objectContaining({ sourceType: 'automatic' }))
  })

  it('索引失败时不继续检索，也不把旧自动证据当作当前成功结果', async () => {
    const intent = { topic: '图搜索' }
    const store = await mountWorkspace({
      intent,
      evidence: [{ id: 'auto-old', query: '旧主题', sourceType: 'automatic', sessionId: 'sess_workspace', nodeRef: '整份PPT草稿', packet: packet('old') }],
      materials: [{ id: 'm1', chunks: [{ chunkId: 'chunk-1', content: '图搜索', sessionRegistered: true }] }],
      setupStore: (store) => {
        store.indexKnowledgeBase = vi.fn().mockImplementation(async () => {
          store.error = '知识库索引服务异常'
          return null
        })
        store.generateEvidence = vi.fn()
      }
    })

    expect(store.generateEvidence).not.toHaveBeenCalled()
    expect(host.textContent).toContain('知识库索引服务异常')
    expect(store.evidencePackets).toHaveLength(0)
  })

  it('RAG 无命中时不恢复旧自动交接，也不显示检索成功', async () => {
    const store = await mountWorkspace({
      intent: { topic: '没有命中的主题' },
      evidence: [{ id: 'auto-old', query: '旧主题', sourceType: 'automatic', sessionId: 'sess_workspace', nodeRef: '整份PPT草稿', packet: packet('old') }],
      setupStore: (store) => {
        store.generateEvidence = vi.fn().mockImplementation(async () => {
          store.error = 'RAG 未检索到可用证据，请调整关键词或先索引资料'
          return null
        })
      }
    })

    expect(store.evidencePackets).toHaveLength(0)
    expect(host.textContent).toContain('本次检索没有返回可用参考内容')
    expect(host.textContent).not.toContain('当前采用 1 条实际返回的参考片段')
  })

  it('手动证据在 query 变化后仍保留，并作为明确确认的 S3 交接', async () => {
    const intent = { topic: '哈希表' }
    const manual = { id: 'manual-1', query: '旧手动检索', sourceType: 'manual', sessionId: 'sess_workspace', nodeRef: 'draft', packet: packet('manual') }
    const store = await mountWorkspace({ intent, evidence: [manual] })

    store.generateEvidence = vi.fn()
    expect(store.generateEvidence).not.toHaveBeenCalled()
    expect(store.evidencePackets.at(-1)).toEqual(expect.objectContaining({ query: '旧手动检索', sourceType: 'manual' }))
    expect(JSON.parse(window.localStorage.getItem('fuww_s2_evidence_packet:sess_workspace')).relevant_chunks[0].chunk_id).toBe('manual')
  })
})
