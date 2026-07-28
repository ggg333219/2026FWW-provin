import { AI_API_BASE } from '../../config/api'
import { requestJson } from './request'

/**
 * S3 讲稿生成 API (Studio)
 *
 * 负责讲稿的生成、节点树管理、分段与音频生成。
 */
export const teacherGenerationApi = {
  /**
   * AI 生成讲稿
   * @param {Object} params
   * @param {string} params.courseId - 课件ID
   * @param {number} params.pageNum - 页码
   * @param {string} params.mode - 生成模式 ('llm' | 'template')
   * @returns {Promise<Object>}
   */
  generateScript: ({ courseId, pageNum, mode = 'llm' }) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/scripts/ai-generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pageNum, mode })
    }),

  /**
   * 获取讲稿内容
   * @param {string} courseId - 课件ID
   * @param {number} pageNum - 页码
   * @returns {Promise<Object>}
   */
  getScript: (courseId, pageNum) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/scripts/${pageNum}`),

  /**
   * 保存讲稿内容
   * @param {Object} params
   * @param {string} params.courseId
   * @param {number} params.pageNum
   * @param {string} params.content
   * @returns {Promise<Object>}
   */
  saveScript: ({ courseId, pageNum, content }) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/scripts/${pageNum}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content })
    }),

  /**
   * 获取节点树
   * @param {string} courseId - 课件ID
   * @param {number} pageNum - 页码
   * @returns {Promise<Object>}
   */
  getNodes: (courseId, pageNum) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/pages/${pageNum}/nodes`),

  /**
   * 保存节点树
   * @param {Object} params
   * @param {string} params.courseId
   * @param {number} params.pageNum
   * @param {Array} params.nodes
   * @returns {Promise<Object>}
   */
  saveNodes: ({ courseId, pageNum, nodes }) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/pages/${pageNum}/nodes`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodes })
    }),

  /**
   * 生成页面音频
   * @param {Object} params
   * @param {string} params.courseId
   * @param {number} params.pageNum
   * @returns {Promise<Object>}
   */
  generateAudio: ({ courseId, pageNum }) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/pages/${pageNum}/audio`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    }),

  /**
   * 获取增强讲稿（AI API 模式）
   * @param {Object} params
   * @param {string} params.markdown - 课件markdown
   * @param {string} params.courseName
   * @param {string} params.mode
   * @returns {Promise<Object>}
   */
  getEnhancedScript: (params = {}) => {
    return fetch(`${AI_API_BASE}/generate-enhanced`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        markdown: params.markdown,
        course_name: params.courseName || '未命名课程',
        mode: params.mode || 'llm'
      })
    }).then(r => r.json())
  }
}