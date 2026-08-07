import { requestJson } from './request'

/**
 * KB 知识库 RAG API
 *
 * 对齐后端 knowledge_handler.go + ai_engine/rag/router.py：
 *   POST /api/v1/rag/search       → RAG 检索（向量 + BM25 混合）
 *   POST /api/v1/rag/evidence     → 证据融合（生成 EvidencePacket 供 S3 消费）
 *   POST /api/v1/knowledge/upload → 文档上传/索引（进入向量存储）
 */
export const teacherRagApi = {
  /**
   * RAG 检索
   * @param {Object} params
   * @param {string} params.query - 检索关键词
   * @param {string[]} params.knowledgeBaseIds - 限定知识库（可选）
   * @param {number} params.topK - 返回结果数
   * @param {number} params.minScore - 相似度阈值
   * @returns {Promise<Object>} { results, total_chunks }
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
   * @returns {Promise<Object>} { evidence_packet: { relevant_chunks, synthesized_context, citations } }
   */
  evidence: (params = {}) =>
    requestJson('/api/v1/rag/evidence', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
   * @returns {Promise<Object>} { task_id, status, chunk_count, document_id }
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
