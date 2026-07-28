import { requestJson } from './request'

/**
 * 知识库 RAG API
 *
 * 负责知识库检索、向量搜索与证据引用。
 */
export const teacherRagApi = {
  /**
   * 检索知识库
   * @param {Object} params
   * @param {string} params.courseId - 课件ID
   * @param {string} params.query - 检索关键词
   * @param {number} params.topK - 返回结果数
   * @returns {Promise<Object>}
   */
  search: (params = {}) => {
    const query = new URLSearchParams()
    if (params.query) query.set('query', params.query)
    if (params.topK) query.set('top_k', params.topK)
    return requestJson(`/api/v1/teacher/knowledge-graph/${encodeURIComponent(params.courseId)}/search?${query.toString()}`)
  },

  /**
   * 向量检索（RAG 核心）
   * @param {Object} params
   * @param {string} params.courseId
   * @param {string} params.query - 查询文本
   * @param {number} params.topK - 返回切片数
   * @param {number} params.threshold - 相似度阈值
   * @returns {Promise<Object>}
   */
  vectorSearch: (params = {}) =>
    requestJson(`/api/v1/teacher/knowledge-graph/${encodeURIComponent(params.courseId)}/vector-search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: params.query,
        top_k: params.topK || 10,
        threshold: params.threshold || 0.6
      })
    }),

  /**
   * 获取知识图谱同步状态
   * @param {string} courseId
   * @returns {Promise<Object>}
   */
  getSyncStatus: (courseId) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/knowledge-graph/sync`, {
      method: 'POST'
    }),

  /**
   * 获取知识图谱引用健康度
   * @param {string} courseId
   * @returns {Promise<Object>}
   */
  getReferenceHealth: (courseId) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/knowledge-graph/reference-health`),

  /**
   * 修复知识图谱引用
   * @param {string} courseId
   * @param {Object} body
   * @returns {Promise<Object>}
   */
  repairReferences: (courseId, body = {}) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/knowledge-graph/reference-health/repair`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
}