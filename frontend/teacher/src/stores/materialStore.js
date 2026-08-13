import { defineStore } from 'pinia'
import { teacherV1Api } from '../services/v1'

/**
 * S2 多模态资料中心 + KB 知识库 Store
 *
 * 职责：
 * - 资料上传任务与解析状态机（uploaded → parsing → done / failed）
 * - 素材列表、ChunkSchema 切片管理与选中
 * - RAG 检索结果缓存
 * - 证据绑定（供 S3 生成环节消费的 EvidencePacket）
 *
 * 输出给 S3 的数据格式（evidencePackets）：
 * {
 *   evidence_packet: {
 *     query: string,
 *     relevant_chunks: ChunkSchema[],
 *     synthesized_context: string,
 *     citations: [{ chunk_id, text_snippet, source_ref }]
 *   }
 * }
 */
export const useMaterialStore = defineStore('material', {
  state: () => ({
    /** 素材列表 */
    materials: [],
    // materials[i] 结构参考：
    // {
    //   id: string,
    //   title: string,
    //   type: 'video' | 'document' | 'image' | 'audio' | 'link',
    //   fileType: string,          // 原始文件扩展名
    //   fileSize: number,          // 文件大小(字节)
    //   source: string,            // 来源
    //   tags: string[],            // 标签
    //   parseStatus: 'uploaded' | 'parsing' | 'done' | 'failed',
    //   uploadedAt: string,
    //   chunks: [],                // ChunkSchema 切片
    // }

    /** 当前选中的素材 */
    selectedMaterials: [],

    /** 素材切片列表 (ChunkSchema) */
    chunks: [],
    // chunks[i] 结构参考：
    // {
    //   chunkId: string,
    //   materialId: string,
    //   content: string,           // 切片内容/文本
    //   pageStart: number,
    //   pageEnd: number,
    //   timeStart: number,         // 视频起始时间(秒)
    //   timeEnd: number,           // 视频结束时间(秒)
    //   seqIndex: number,          // 文档内顺序索引
    //   embedding: [],             // 向量嵌入（可选）
    //   metadata: {},              // 额外元数据
    //   relevanceScore: number     // 与当前意图的相关性(0-1)
    // }

    /** 上传/解析任务列表 */
    parseTasks: [],
    // parseTasks[i] 结构参考：
    // {
    //   taskId: string,
    //   fileName: string,
    //   fileSize: number,
    //   status: 'processing' | 'done' | 'failed',   // 任务级状态
    //   chunkCount: number,
    //   error: string,
    //   createdAt: string
    // }

    /** RAG 检索结果 */
    ragResults: [],
    // ragResults[i] 结构参考：
    // {
    //   chunk_id: string,
    //   content: string,
    //   score: number,             // 命中分数(0-1)
    //   source: { file_name, page, url },
    //   metadata: { type, node_ref }
    // }

    /** 证据融合包（KB → S3 的交接产物） */
    evidencePackets: [],
    // evidencePackets[i] 结构参考：
    // {
    //   id: string,                // 证据包ID
    //   query: string,             // 触发检索的查询
    //   createdAt: string,
    //   packet: {                  // EvidencePacket（对接后端 /api/v1/rag/evidence）
    //     relevant_chunks: [],
    //     synthesized_context: string,
    //     citations: []
    //   }
    // }

    /** 是否正在上传 */
    uploading: false,

    /** 是否正在加载素材 */
    loading: false,

    /** 检索中标记 */
    searching: false,

    /** 是否正在知识库索引 */
    indexing: false,

    /** 错误信息 */
    error: ''
  }),

  getters: {
    selectedCount: (state) => state.selectedMaterials.length,
    hasSelection: (state) => state.selectedMaterials.length > 0,

    /** 当前选中素材的切片 */
    selectedChunks: (state) =>
      state.chunks.filter(c => state.selectedMaterials.includes(c.materialId)),

    /** 全部素材切片（去重，供检索/证据融合使用） */
    allChunks: (state) => {
      const seen = new Set()
      const list = []
      state.materials.forEach((m) => {
        ;(m.chunks || []).forEach((c) => {
          if (seen.has(c.chunkId)) return
          seen.add(c.chunkId)
          list.push(c)
        })
      })
      return list
    },

    /** 最近一个证据包 */
    latestEvidencePacket: (state) =>
      state.evidencePackets.length > 0
        ? state.evidencePackets[state.evidencePackets.length - 1]
        : null,

    /** 可传给 S3 的 EvidencePacket（后端契约格式） */
    s3EvidencePayload: (state) => {
      const latest = state.evidencePackets.length > 0
        ? state.evidencePackets[state.evidencePackets.length - 1]
        : null
      return latest ? latest.packet : null
    }
  },

  actions: {
    setLoading(loading) {
      this.loading = loading
    },

    setError(error) {
      this.error = error
    },

    /**
     * 加载素材列表
     * 优先使用后端 /api/v1/teacher/materials，失败时回退到 Mock。
     */
    async loadMaterials() {
      this.loading = true
      try {
        const resp = await teacherV1Api.material.search()
        const list = resp?.data
        if (Array.isArray(list)) {
          this.setMaterials(list)
        }
      } catch (err) {
        console.warn('加载素材列表失败', err)
        this.error = String(err?.message || err)
      } finally {
        this.loading = false
      }
    },

    /**
     * 知识库索引：把当前已解析素材送入向量库
     *
     * 数据来源（按优先级）：
     *   1. params.texts / params.files —— 显式传入（调用方指定）
     *   2. allChunks —— 前端 store 中已解析的切片文本（S2 解析产出）
     *
     * 说明：AI 引擎的向量库是进程内存存储，重启后 session 关联的解析 chunks 会
     * 丢失。这里把前端已有切片文本一并上传，保证「索引知识库」不依赖 S2 解析
     * 会话状态，重启后也能重新灌入数据。
     *
     * @returns {Promise<Object|null>} 后端响应 { task_id, status, chunk_count, document_id }
     */
    async indexKnowledgeBase(params = {}) {
      this.indexing = true
      try {
        // 前端已解析切片文本兜底（按顺序截断超长，避免单个 chunk 过大）
        const chunkTexts = this.allChunks
          .map((c) => (typeof c?.content === 'string' ? c.content.trim() : ''))
          .filter((t) => t.length > 0)
          .slice(0, 200)
          .map((t) => t.slice(0, 3000))

        const resp = await teacherV1Api.rag.knowledgeUpload({
          sessionId: params.sessionId || '',
          files: params.files || [],
          texts: [...(params.texts || []), ...chunkTexts]
        })
        return resp?.data || null
      } catch (err) {
        console.warn('知识库索引失败', err)
        this.error = String(err?.message || err)
        return null
      } finally {
        this.indexing = false
      }
    },

    /**
     * RAG 检索
     * @param {Object} params { query, topK, minScore }
     * @returns {Promise<Array>} 检索结果列表
     */
    async searchRag(params = {}) {
      this.searching = true
      this.error = ''
      try {
        const resp = await teacherV1Api.rag.search({
          query: params.query,
          topK: params.topK || 10,
          minScore: params.minScore ?? 0.6
        })
        const results = resp?.data?.results || []
        this.setRagResults(results)
        return results
      } catch (err) {
        console.warn('RAG 检索失败', err)
        this.error = String(err?.message || err)
        this.setRagResults([])
        return []
      } finally {
        this.searching = false
      }
    },

    /**
     * 证据融合（KB → S3 证据包）
     * @param {Object} params { query, context }
     * @returns {Promise<Object|null>} EvidencePacket
     */
    async generateEvidence(params = {}) {
      this.searching = true
      this.error = ''
      try {
        const resp = await teacherV1Api.rag.evidence({
          query: params.query,
          context: params.context || {}
        })
        const packet = resp?.data?.evidence_packet || null
        if (packet) {
          this.addEvidencePacket(params.query, packet)
        }
        return packet
      } catch (err) {
        console.warn('证据融合失败', err)
        this.error = String(err?.message || err)
        return null
      } finally {
        this.searching = false
      }
    },

    setMaterials(list) {
      this.materials = list
      this.chunks = list.flatMap((m) => (m.chunks || []).map((c) => ({
        ...c,
        materialId: c.materialId || m.id
      })))
    },

    setChunks(chunks) {
      this.chunks = chunks
    },

    addMaterial(material) {
      this.materials.unshift(material)
      if (Array.isArray(material.chunks)) {
        this.chunks.push(...material.chunks.map((c) => ({ ...c, materialId: c.materialId || material.id })))
      }
    },

    removeMaterial(id) {
      this.materials = this.materials.filter((item) => item.id !== id)
      this.chunks = this.chunks.filter((item) => item.materialId !== id)
      this.selectedMaterials = this.selectedMaterials.filter((item) => item !== id)
    },

    updateMaterial(id, patch) {
      const material = this.materials.find((item) => item.id === id)
      if (material) {
        Object.assign(material, patch)
        if (patch.chunks) {
          this.chunks = this.chunks.filter((item) => item.materialId !== id)
          this.chunks.push(...patch.chunks.map((c) => ({ ...c, materialId: c.materialId || id })))
        }
      }
    },

    toggleMaterial(id) {
      const idx = this.selectedMaterials.indexOf(id)
      if (idx >= 0) {
        this.selectedMaterials.splice(idx, 1)
      } else {
        this.selectedMaterials.push(id)
      }
    },

    selectMaterial(id) {
      if (!this.selectedMaterials.includes(id)) {
        this.selectedMaterials.push(id)
      }
    },

    deselectMaterial(id) {
      const idx = this.selectedMaterials.indexOf(id)
      if (idx >= 0) {
        this.selectedMaterials.splice(idx, 1)
      }
    },

    clearSelection() {
      this.selectedMaterials = []
    },

    /** 新增一个解析任务（本地乐观状态，等待轮询更新） */
    addParseTask(task) {
      this.parseTasks.unshift(task)
    },

    updateParseTask(taskId, patch) {
      const task = this.parseTasks.find((item) => item.taskId === taskId)
      if (task) {
        Object.assign(task, patch)
      }
    },

    /** 移除已完成/失败的解析任务 */
    removeParseTask(taskId) {
      this.parseTasks = this.parseTasks.filter((item) => item.taskId !== taskId)
    },

    setUploading(uploading) {
      this.uploading = uploading
    },

    setSearching(searching) {
      this.searching = searching
    },

    setIndexing(indexing) {
      this.indexing = indexing
    },

    setRagResults(results) {
      this.ragResults = results
    },

    clearRagResults() {
      this.ragResults = []
    },

    /** 保存一个证据融合包 */
    addEvidencePacket(query, packet) {
      this.evidencePackets.push({
        id: `ev_${Date.now()}`,
        query: String(query || ''),
        createdAt: new Date().toISOString(),
        packet
      })
      // 持久化最新证据包到 localStorage，供 S3 生成环节读取（成员B：S2→S3 证据透传）
      if (packet) {
        try {
          window.localStorage.setItem('fuww_s2_evidence_packet', JSON.stringify(packet))
        } catch (e) {
          console.warn('[materialStore] 持久化证据包失败', e)
        }
      }
    },

    removeEvidencePacket(id) {
      this.evidencePackets = this.evidencePackets.filter((item) => item.id !== id)
    },

    clearEvidencePackets() {
      this.evidencePackets = []
    },

    /** 清除选中素材的持久化（用于刷新后重建） */
    restoreSelection(ids) {
      this.selectedMaterials = (Array.isArray(ids) ? ids : []).filter(
        (id) => this.materials.some((m) => m.id === id)
      )
    },

    reset() {
      this.materials = []
      this.selectedMaterials = []
      this.chunks = []
      this.parseTasks = []
      this.ragResults = []
      this.evidencePackets = []
      this.uploading = false
      this.loading = false
      this.searching = false
      this.indexing = false
      this.error = ''
    }
  }
})
