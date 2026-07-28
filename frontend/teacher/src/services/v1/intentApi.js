import { AI_API_BASE } from '../../config/api'
import { requestJson } from './request'

/**
 * S1 意图理解 API
 *
 * 负责教学意图的捕获、解析与结构化输出。
 */
export const teacherIntentApi = {
  /**
   * 解析教学意图（流式或非流式）
   * @param {Object} params
   * @param {string} params.input - 教师原始输入文本
   * @param {boolean} params.stream - 是否使用流式响应
   * @returns {Promise<Response|Object>} 流式模式返回 Response，非流式返回解析结果
   */
  parseIntent: (params = {}) => {
    const { input, stream = false } = params
    if (stream) {
      // 流式接口：返回原始 Response 供前端 ReadableStream 消费
      return fetch(`${AI_API_BASE}/api/v1/teacher/intent/parse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input, stream: true })
      })
    }
    return requestJson('/api/v1/teacher/intent/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input, stream: false })
    })
  },

  /**
   * 获取意图解析历史
   * @param {string} courseId - 课件ID
   * @returns {Promise<Object>}
   */
  getHistory: (courseId) =>
    requestJson(`/api/v1/teacher/intent/history/${encodeURIComponent(courseId)}`)
}