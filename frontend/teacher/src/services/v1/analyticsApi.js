import { AI_API_BASE } from '../../config/api'
import { requestJson } from './request'

/**
 * 学情统计 API
 *
 * 对接后端 AI Engine 端点，mockBackend 提供离线回退。
 */
export const teacherAnalyticsApi = {
  /**
   * 学情总览统计
   * GET /api/v1/teacher/coursewares/{courseId}/stats
   */
  getStats: (courseId) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/stats`),

  /**
   * 卡片数据（页面级统计）
   * GET /api/v1/teacher/coursewares/{courseId}/card-data
   */
  getCardData: (courseId) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/card-data`),

  /**
   * 提问记录
   * GET /api/v1/teacher/coursewares/{courseId}/questions?page=1&pageSize=100
   */
  getQuestionRecords: (courseId, page = 1, pageSize = 100) =>
    requestJson(
      `/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/questions?page=${page}&pageSize=${pageSize}`
    )
}
