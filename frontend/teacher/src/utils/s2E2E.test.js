// S2 前端全链路仿真（mock 模式）：真实 store + api + mockBackend 协同
// 通过 stub window.localStorage + 抛错的 fetch 强制走 mock 回退路径
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useMaterialStore } from '../stores/materialStore'
import { teacherV1Api } from '../services/v1'
import { handleMockRequest } from '../services/v1/mockBackend'
import { requestJson } from '../services/v1/request'

// ---- 浏览器环境 stub ----
function createStorage() {
  const map = new Map()
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => { map.set(k, String(v)) },
    removeItem: (k) => { map.delete(k) },
    clear: () => { map.clear() }
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

beforeEach(() => {
  vi.restoreAllMocks()
  const storage = createStorage()
  globalThis.window = { localStorage: storage, setTimeout, clearTimeout }
  globalThis.localStorage = storage
  // 强制 fetch 抛错 → requestJson 走 mock 回退并设置 mock 模式
  globalThis.fetch = () => Promise.reject(new Error('backend unreachable'))
  setActivePinia(createPinia())
})

describe('S2 前端链路（mock）', () => {
  it('loadMaterials 加载 3 份默认素材', async () => {
    const store = useMaterialStore()
    await store.loadMaterials()
    expect(store.materials.length).toBe(3)
    expect(store.chunks.length).toBeGreaterThan(0)
  })

  it('RAG 检索返回结果且来源有文件名', async () => {
    const store = useMaterialStore()
    await store.loadMaterials()
    await store.searchRag({ query: '函数', topK: 5, minScore: 0.6 })
    expect(store.ragResults.length).toBeGreaterThan(0)
    expect(store.ragResults[0].source?.file_name).toBeTruthy()
  })

  it('Mock RAG 对无关关键词返回 0 命中，不伪造高相关结果', async () => {
    const store = useMaterialStore()
    await store.loadMaterials()

    const results = await store.searchRag({ query: '不存在的量子海绵课程资料XYZ', topK: 5, minScore: 0.6 })

    expect(results).toHaveLength(0)
    expect(store.ragResults).toHaveLength(0)
  })

  it('KB 文档来源显示真实文件名而非“素材”', async () => {
    const store = useMaterialStore()
    await store.loadMaterials()
    // 索引一个唯一命名的 PDF 文档
    const up = await teacherV1Api.rag.knowledgeUpload({
      sessionId: 'sess_kb_src',
      files: ['minio://courses/cw_x/函数讲义.pdf'],
      texts: []
    })
    expect(up.data.chunk_count).toBeGreaterThan(0)
    // 检索关键词应命中该 KB 文档，且 source.file_name 为其文件名
    await store.searchRag({ query: '函数讲义', topK: 10, minScore: 0.5 })
    const hit = store.ragResults.find((r) => r.source?.file_name === '函数讲义.pdf')
    expect(hit).toBeTruthy()
  })

  it('KB 重复索引幂等：再次点击不新增文档/切片', async () => {
    const store = useMaterialStore()
    await store.loadMaterials()
    const sessionId = 'sess_kb_dedupe'
    const first = await teacherV1Api.rag.knowledgeUpload({ sessionId, files: [], texts: [] })
    expect(first.data.chunk_count).toBeGreaterThan(0)
    // 再次索引同一会话：无新增切片（幂等）
    const second = await teacherV1Api.rag.knowledgeUpload({ sessionId, files: [], texts: [] })
    expect(second.data.chunk_count).toBe(0)
  })

  it('证据融合生成 evidence_packet 并入 store', async () => {
    const store = useMaterialStore()
    await store.loadMaterials()
    const packet = await store.generateEvidence({ query: '函数的定义域' })
    expect(packet).toBeTruthy()
    expect(packet.relevant_chunks).toBeTruthy()
    expect(store.evidencePackets.length).toBe(1)
  })

  it('空证据包不会被当作成功结果持久化', async () => {
    vi.spyOn(teacherV1Api.rag, 'evidence').mockResolvedValueOnce({
      data: {
        evidence_packet: {
          relevant_chunks: [],
          synthesized_context: '',
          citations: []
        }
      }
    })
    const store = useMaterialStore()
    store.activeSessionId = 's_test'
    const packet = await store.generateEvidence({ query: '完全不存在的内容' })

    expect(packet).toBe(null)
    expect(store.evidencePackets).toHaveLength(0)
    expect(window.localStorage.getItem('fuww_s2_evidence_packet:s_test')).toBe(null)
    expect(store.error).toContain('未检索到可用证据')
  })

  it('清空证据历史时同时移除 S3 交接缓存', () => {
    const store = useMaterialStore()
    store.activeSessionId = 's_test'
    store.addEvidencePacket('快速排序', {
      relevant_chunks: [{ chunk_id: 'chunk_1', content: '分治思想' }],
      synthesized_context: '快速排序使用分治思想。',
      citations: []
    })
    expect(window.localStorage.getItem('fuww_s2_evidence_packet:s_test')).toBeTruthy()

    store.clearEvidencePackets()

    expect(store.evidencePackets).toHaveLength(0)
    expect(window.localStorage.getItem('fuww_s2_evidence_packet:s_test')).toBe(null)
  })

  it('parseProcess → 轮询到 done 且 chunks 含 materialId', async () => {
    const store = useMaterialStore()
    await store.loadMaterials()

    const txt = '函数的定义域。自变量 x 的取值范围称为函数的定义域。值域是函数值 y 的取值范围。求定义域时需注意分母不为零。'
    const filePath = '测试材料.txt'
    const resp = await teacherV1Api.material.parseProcess({
      sessionId: 'sess_test',
      filePaths: [filePath],
      fileContents: { [filePath]: txt }
    })
    const taskId = resp.data.task_id
    expect(taskId).toBeTruthy()

    let status
    let chunks = []
    for (let i = 0; i < 15; i += 1) {
      await sleep(400)
      const st = await teacherV1Api.material.parseStatus(taskId)
      status = st.data.status
      chunks = st.data.chunks || []
      if (status === 'done' || status === 'failed') break
    }
    expect(status).toBe('done')
    expect(chunks.length).toBeGreaterThan(0)
    expect(chunks[0].materialId).toBeTruthy()
  })

  it('带 sessionId 加载时只返回当前教学任务上传的素材', async () => {
    const store = useMaterialStore()
    await store.loadMaterials({ sessionId: 'sess_isolated_a' })
    expect(store.materials).toHaveLength(0)

    const resp = await teacherV1Api.material.parseProcess({
      sessionId: 'sess_isolated_a',
      filePaths: ['会话A讲义.txt'],
      fileContents: { '会话A讲义.txt': '会话 A 的函数教学资料。' }
    })

    for (let i = 0; i < 15; i += 1) {
      await sleep(400)
      const status = await teacherV1Api.material.parseStatus(resp.data.task_id)
      if (status.data.status === 'done') break
    }

    await store.loadMaterials({ sessionId: 'sess_isolated_a' })
    expect(store.materials.map((item) => item.title)).toContain('会话A讲义.txt')

    await store.loadMaterials({ sessionId: 'sess_isolated_b' })
    expect(store.materials).toHaveLength(0)
  })

  it('真实后端暂未持久化会话素材时，刷新解析状态不会清掉同会话本地结果', async () => {
    vi.spyOn(teacherV1Api.material, 'search').mockResolvedValue({ data: [] })
    const store = useMaterialStore()
    store.activeSessionId = 'sess_preserve'
    store.addMaterial({
      id: 'mat_local_a',
      sessionId: 'sess_preserve',
      title: '本地解析结果.txt',
      chunks: [{ chunkId: 'chunk_local_a', content: '本次会话内容' }]
    })

    await store.loadMaterials({ sessionId: 'sess_preserve', preserveSessionMaterials: true })

    expect(store.materials.map((item) => item.id)).toEqual(['mat_local_a'])
    expect(store.chunks).toHaveLength(1)
  })

  it('PDF/二进制文件不产生乱码切片（%PDF 应回退为种子内容）', async () => {
    const store = useMaterialStore()
    await store.loadMaterials()

    // 模拟旧版前端把 PDF 二进制按 UTF-8 解码后传给 file_contents 的场景
    const pdfHead = '%PDF-1.7 \n 1 0 obj <</Type/Catalog/Pages 2 0 R>> endobj 2 0 obj <</Type/Pages/Count 41>> endobj %%%EOF'
    const filePath = '讲义.pdf'
    const resp = await teacherV1Api.material.parseProcess({
      sessionId: 'sess_test',
      filePaths: [filePath],
      fileContents: { [filePath]: pdfHead }
    })
    const taskId = resp.data.task_id

    let status
    let chunks = []
    for (let i = 0; i < 15; i += 1) {
      await sleep(400)
      const st = await teacherV1Api.material.parseStatus(taskId)
      status = st.data.status
      chunks = st.data.chunks || []
      if (status === 'done' || status === 'failed') break
    }
    expect(status).toBe('done')
    expect(chunks.length).toBeGreaterThan(0)
    chunks.forEach((c) => {
      expect(c.content.includes('%PDF-')).toBe(false)
      expect(c.content.replace(/\s/g, '').length).toBeGreaterThan(5)
    })
  })

  it('二进制签名文本被 chunkRealText 识别为乱码并回退种子内容', async () => {
    const store = useMaterialStore()
    await store.loadMaterials()

    // 无 file_contents：二进制文件直接交给种子切片（等价于前端不再对二进制读文本）
    const resp = await teacherV1Api.material.parseProcess({
      sessionId: 'sess_test',
      filePaths: ['视频讲解.mp4']
    })
    const taskId = resp.data.task_id
    let status
    let chunks = []
    for (let i = 0; i < 15; i += 1) {
      await sleep(400)
      const st = await teacherV1Api.material.parseStatus(taskId)
      status = st.data.status
      chunks = st.data.chunks || []
      if (status === 'done' || status === 'failed') break
    }
    expect(status).toBe('done')
    expect(chunks.length).toBeGreaterThan(0)
    expect(chunks[0].content).toContain('视频讲解')
    expect(chunks[0].content.includes('%PDF')).toBe(false)
  })

  it('上传占位 → 解析完成 → 素材去重替换（模拟 S2MaterialHub.pollParseTask 流程）', async () => {
    const store = useMaterialStore()
    await store.loadMaterials()
    const before = store.materials.length

    // 占位素材
    const placeholderId = `placeholder_${Date.now()}`
    store.addMaterial({ id: placeholderId, title: 'x.txt', type: 'document', parseStatus: 'parsing', chunks: [] })
    store.selectMaterial(placeholderId)

    const txt = '排序算法。冒泡排序重复遍历序列比较相邻元素。快速排序通过分治思想划分序列。'
    const filePath = '排序算法.txt'
    const resp = await teacherV1Api.material.parseProcess({
      sessionId: 'sess_test',
      filePaths: [filePath],
      fileContents: { [filePath]: txt }
    })
    const taskId = resp.data.task_id

    let status
    for (let i = 0; i < 15; i += 1) {
      await sleep(400)
      const st = await teacherV1Api.material.parseStatus(taskId)
      status = st.data.status
      if (status === 'done' || status === 'failed') break
    }
    expect(status).toBe('done')

    // 移除占位后，用与组件相同的方式刷新并匹配（不再手动新建 fake ID 素材）
    store.removeMaterial(placeholderId)
    await store.loadMaterials()
    const matched = [...store.materials].find(
      (m) => m.title === '排序算法.txt' && m.parseStatus === 'done' && (m.chunks || []).length > 0
    )
    expect(matched).toBeTruthy()
    store.selectMaterial(matched.id)

    // 同名素材只存在一份（不因前端 + Mock 双重登记而重复）
    const sameName = store.materials.filter((m) => m.title === '排序算法.txt')
    expect(sameName.length).toBe(1)
    expect(sameName[0].chunks.length).toBeGreaterThan(0)
    // 解析任务新增的素材恰好只有 1 份（占位被替换，Mock 已入库，前端不再新增）
    expect(store.materials.length).toBe(before + 1)
  })

  it('requestJson 首次失败后进入 mock 模式', async () => {
    const payload = await requestJson('/api/v1/teacher/materials/search')
    expect(payload.code).toBe(200)
    expect(window.localStorage.getItem('fuww_mock_mode')).toBe('true')
  })

  it('真实链路：后端 404 直接抛出真实错误，不回退 Mock', async () => {
    // 模拟真实后端：materials 列表路由缺失(404)，但 rag 等路由真实存在(200)
    const seen = []
    globalThis.fetch = (url, opts = {}) => {
      seen.push(url)
      if (String(url).includes('/teacher/materials/search')) {
        return Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ code: 404, message: 'route not found' })
        })
      }
      if (String(url).includes('/rag/search')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ code: 200, data: { results: [], total_chunks: 0 } })
        })
      }
      return Promise.reject(new TypeError('Failed to fetch'))
    }

    // materials 404 → 保留真实 HTTP 错误，避免导出等失败请求返回假数据
    const error = await requestJson('/api/v1/teacher/materials/search').catch((err) => err)
    expect(error.httpStatus).toBe(404)
    expect(window.localStorage.getItem('fuww_mock_mode')).toBe(null)

    // rag/search 继续走真实 fetch（真实后端 200），而非 Mock
    const rag = await requestJson('/api/v1/rag/search', { method: 'POST', body: '{}' })
    expect(seen.some((u) => String(u).includes('/rag/search'))).toBe(true)
    expect(rag.data.results).toBeTruthy()
  })

  it('handleMockRequest 未知路由返回 null（不假报成功）', () => {
    const resp = handleMockRequest('/api/v1/does-not-exist', { method: 'GET' }, new Error('x'))
    expect(resp).toBe(null)
  })
})
