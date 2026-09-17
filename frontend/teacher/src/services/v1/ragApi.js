import { requestJson } from './request'

/**
 * KB 知识库 RAG API — 走 Go Backend（cmd/teacher，端口 8082）
 *
 * 对齐后端路由（backend/internal/router/teacher.go → RegisterNewSkillRoutes）：
 *   POST /api/v1/rag/search       → RAG 检索（向量 + BM25 混合）
 *   POST /api/v1/rag/evidence     → 证据融合（生成 EvidencePacket 供 S3 消费）
 *   POST /api/v1/knowledge/upload → 文档上传/索引（进入向量存储）
 *
 * 返回统一 envelope { code, message, data }，与 materialStore 的 resp.data 解包一致。
 * 注意：不要用原生 fetch 直连 AI Engine（8000）——那返回的是 FastAPI 原始 response_model，
 * 没有 data 包裹，会导致 materialStore 读 resp.data 恒为 undefined，索引/检索被误判失败。
 */
export const teacherRagApi = {
  /**
   * RAG 检索
   * @param {Object} params
   * @param {string} params.query - 检索关键词
   * @param {string[]} params.knowledgeBaseIds - 限定知识库（可选）
   * @param {number} params.topK - 返回结果数
   * @param {number} params.minScore - 相似度阈值
   * @returns {Promise<Object>} { code, data: { results, total_chunks } }
   */
  search: (params = {}) =>
    requestJson('/api/v1/rag/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: params.query || '',
        knowledge_base_ids: params.knowledgeBaseIds || [],
        top_k: params.topK || 10,
        min_score: params.minScore ?? 0.6
      })
    }),

  /**
   * 证据融合（KB → S3 交接产物）
   * @param {Object} params
   * @param {string} params.query - 查询文本
   * @param {Object} params.context - 附加上下文（如当前意图摘要）
   * @param {string[]} params.knowledgeBaseIds - 限定知识库（可选）
   * @returns {Promise<Object>} { code, data: { evidence_packet: {...} } }
   */
  evidence: (params = {}) =>
    requestJson('/api/v1/rag/evidence', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 证据融合包含一次 LLM 摘要，真实环境通常会超过通用的 10 秒请求上限。
      // 与后端 AI Client 的长任务窗口保持一致，避免后端成功但前端提前 Abort。
      timeoutMs: 120000,
      body: JSON.stringify({
        query: params.query || '',
        context: params.context || {},
        knowledge_base_ids: params.knowledgeBaseIds || []
      })
    }),

  /**
   * 知识库上传/索引
   * @param {Object} params
   * @param {string} params.sessionId - 会话ID（关联 S2 已解析资料）
   * @param {string[]} params.files - 文件路径列表（minio:// 或本地路径，可选）
   * @param {string[]} params.texts - 直接上传的文本片段（可选）
   * @param {string} params.knowledgeBaseId - 目标知识库ID（可选）
   * @returns {Promise<Object>} { code, data: { task_id, status, chunk_count, document_id } }
   */
  knowledgeUpload: (params = {}) =>
    requestJson('/api/v1/knowledge/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: params.sessionId || '',
        knowledge_base_id: params.knowledgeBaseId || '',
        files: params.files || [],
        texts: params.texts || []
      })
    })
}
