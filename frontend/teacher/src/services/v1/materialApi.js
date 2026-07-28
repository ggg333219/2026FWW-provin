import { requestJson } from './request'

/**
 * S2 素材管理 API
 *
 * 负责素材检索、切片 (ChunkSchema) 管理与向量检索。
 */
export const teacherMaterialApi = {
  /**
   * 检索素材列表
   * @param {Object} params
   * @param {string} params.keyword - 关键词
   * @param {string} params.type - 素材类型
   * @param {number} params.page - 页码
   * @param {number} params.pageSize - 每页数量
   * @returns {Promise<Object>}
   */
  search: (params = {}) => {
    const query = new URLSearchParams()
    if (params.keyword) query.set('keyword', params.keyword)
    if (params.type) query.set('type', params.type)
    if (params.page) query.set('page', params.page)
    if (params.pageSize) query.set('pageSize', params.pageSize)
    return requestJson(`/api/v1/teacher/materials/search?${query.toString()}`)
  },

  /**
   * 获取素材详情
   * @param {string} materialId - 素材ID
   * @returns {Promise<Object>}
   */
  getDetail: (materialId) =>
    requestJson(`/api/v1/teacher/materials/${encodeURIComponent(materialId)}`),

  /**
   * 获取素材切片列表 (ChunkSchema)
   * @param {string} materialId - 素材ID
   * @returns {Promise<Object>}
   */
  getChunks: (materialId) =>
    requestJson(`/api/v1/teacher/materials/${encodeURIComponent(materialId)}/chunks`),

  /**
   * 向量检索相似切片
   * @param {Object} params
   * @param {string} params.query - 查询文本
   * @param {number} params.topK - 返回切片数量
   * @param {string} params.courseId - 课件ID（可选，限定范围）
   * @returns {Promise<Object>}
   */
  vectorSearch: (params = {}) => {
    return requestJson('/api/v1/teacher/materials/vector-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: params.query,
        top_k: params.topK || 10,
        course_id: params.courseId || ''
      })
    })
  }
}