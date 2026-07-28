import { requestJson } from './request'

/**
 * S4 版本管理 API
 *
 * 负责课件版本管理与发布。
 */
export const teacherVersionApi = {
  /**
   * 获取版本列表
   * @param {string} courseId - 课件ID
   * @returns {Promise<Object>}
   */
  list: (courseId) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/versions`),

  /**
   * 创建新版本
   * @param {Object} params
   * @param {string} params.courseId
   * @param {string} params.title - 版本标题
   * @param {string} params.description - 版本说明
   * @returns {Promise<Object>}
   */
  create: ({ courseId, title, description }) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/versions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, description })
    }),

  /**
   * 获取版本详情
   * @param {string} courseId
   * @param {string} versionId
   * @returns {Promise<Object>}
   */
  getDetail: (courseId, versionId) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/versions/${encodeURIComponent(versionId)}`),

  /**
   * 发布课件
   * @param {Object} params
   * @param {string} params.courseId
   * @param {string} params.scope - 发布范围
   * @param {string} params.teachingCourseId
   * @param {string} params.teachingCourseTitle
   * @param {string} params.courseClassId
   * @param {string} params.courseClassName
   * @returns {Promise<Object>}
   */
  publish: ({ courseId, scope, teachingCourseId, teachingCourseTitle, courseClassId, courseClassName }) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope,
        teachingCourseId,
        teachingCourseTitle,
        courseClassId,
        courseClassName
      })
    }),

  /**
   * 提交修改指令
   * @param {Object} params
   * @param {string} params.courseId
   * @param {Array} params.changes - 修改指令列表
   * @returns {Promise<Object>}
   */
  submitChanges: ({ courseId, changes }) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/changes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ changes })
    })
}