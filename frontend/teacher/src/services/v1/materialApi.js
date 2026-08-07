import { requestJson } from './request'

/**
 * S2 多模态资料中心 API
 *
 * 负责资料上传、解析任务（S2 状态机）、素材与 ChunkSchema 管理。
 * 真实后端路由参见 backend/internal/router/teacher.go：
 *   POST /api/v1/parse/process          → 创建解析任务（file_paths）
 *   GET  /api/v1/parse/status/:task_id  → 查询解析状态 + chunks
 *   POST /api/v1/parse/video            → 视频专用解析
 *   POST /api/v1/teacher/coursewares/upload → multipart 上传（PPT/PDF）
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
   * 删除素材
   * @param {string} materialId - 素材ID
   * @returns {Promise<Object>}
   */
  delete: (materialId) =>
    requestJson(`/api/v1/teacher/materials/${encodeURIComponent(materialId)}`, {
      method: 'DELETE'
    }),

  /**
   * 上传课件文件（multipart，PPT/PDF）
   * @param {Object} params
   * @param {File} params.file - 文件对象
   * @param {string} params.title - 课件标题
   * @returns {Promise<Object>}
   */
  uploadCourseware: ({ file, title }) => {
    const form = new FormData()
    form.append('file', file)
    if (title) form.append('title', title)
    return requestJson('/api/v1/teacher/coursewares/upload', {
      method: 'POST',
      body: form
    })
  },

  /**
   * S2 专用上传：文件落盘到引擎可读目录，返回本地路径供 parse/process 使用
   * @param {Object} params
   * @param {File} params.file - 文件对象
   * @param {string} params.sessionId - 会话ID（用于分目录）
   * @returns {Promise<Object>} { file_path, file_name, file_size, source_type }
   */
  uploadParseFile: ({ file, sessionId = '' }) => {
    const form = new FormData()
    form.append('file', file)
    form.append('session_id', sessionId || '')
    return requestJson('/api/v1/parse/upload', {
      method: 'POST',
      body: form
    })
  },

  /**
   * 创建解析任务（S2）
   * @param {Object} params
   * @param {string} params.sessionId - 会话ID
   * @param {string[]} params.filePaths - 待解析文件路径列表
   * @param {Object} [params.fileContents] - { [path]: text }，仅 Mock 端用于生成真实切片；
   *                                         真实后端自行解析磁盘文件，pydantic 会忽略多余字段
   * @returns {Promise<Object>} { task_id, status, assets }
   */
  parseProcess: ({ sessionId, filePaths = [], fileContents } = {}) => {
    const body = { session_id: sessionId || '', file_paths: filePaths }
    if (fileContents && typeof fileContents === 'object' && Object.keys(fileContents).length > 0) {
      body.file_contents = fileContents
    }
    return requestJson('/api/v1/parse/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
  },

  /**
   * 查询解析状态
   * @param {string} taskId - 解析任务ID
   * @returns {Promise<Object>} { task_id, status, chunks, error }
   */
  parseStatus: (taskId) =>
    requestJson(`/api/v1/parse/status/${encodeURIComponent(taskId)}`),

  /**
   * 视频专用解析
   * @param {Object} params
   * @param {string} params.sessionId - 会话ID
   * @param {string} params.filePath - 视频文件路径
   * @param {string} params.language - ASR 语言（'zh' | 'en'，空则自动检测）
   * @returns {Promise<Object>} { task_id, status, assets }
   */
  parseVideo: ({ sessionId, filePath, language = '' }) =>
    requestJson('/api/v1/parse/video', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId || '',
        file_path: filePath,
        language
      })
    })
}
