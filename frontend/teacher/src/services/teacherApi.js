import { API_BASE } from '../config/api'

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || (typeof payload.code !== 'undefined' && payload.code !== 200)) {
    throw new Error(payload.message || `请求失败: ${response.status}`)
  }
  return payload
}

export const teacherApi = {
  checkHealth: () => fetch(`${API_BASE}/health`, { cache: 'no-store' }),
  getCoursewareList: () => requestJson('/api/v1/teacher/coursewares'),
  deleteCourseware: (courseId) => requestJson(`/api/v1/teacher/coursewares/${courseId}`, { method: 'DELETE' }),
  getScript: (courseId, page) => requestJson(`/api/v1/teacher/coursewares/${courseId}/scripts/${page}`),
  saveScript: (body) => requestJson(`/api/v1/teacher/coursewares/${body.courseId}/scripts/${body.page}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: body.content })
  }),
  generateScript: (body) => requestJson(`/api/v1/teacher/coursewares/${body.courseId}/scripts/ai-generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pageNum: body.page, mode: body.mode || 'llm' })
  }),
  uploadCourseware: (formData) => requestJson('/api/v1/teacher/coursewares/upload', {
    method: 'POST',
    body: formData
  }),
  publishCourseware: (body) => requestJson(`/api/v1/teacher/coursewares/${body.courseId}/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scope: body.scope })
  }),
  getStudentStats: (courseId) => requestJson(`/api/v1/teacher/coursewares/${courseId}/stats`),
  getCardData: (courseId) => requestJson(`/api/v1/teacher/coursewares/${courseId}/card-data`),
  getQuestionRecords: (courseId, page = 1, pageSize = 100) => requestJson(`/api/v1/teacher/coursewares/${courseId}/questions?page=${page}&pageSize=${pageSize}`)
}
