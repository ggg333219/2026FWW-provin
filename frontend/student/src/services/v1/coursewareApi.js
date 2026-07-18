import { requestJson } from './request'

const buildQuery = (params) => {
  return Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&')
}

export const studentCoursewareApi = {
  list: (params = {}) => {
    const query = buildQuery(params)
    return requestJson(`/api/v1/student/coursewares${query ? `?${query}` : ''}`)
  },
  getPlaybackScript: (courseId, pageNum) => requestJson(`/api/v1/student/coursewares/${encodeURIComponent(courseId)}/scripts/${pageNum}`),
  getBreakpoint: (studentId, courseId) => requestJson(`/api/v1/student/coursewares/${encodeURIComponent(courseId)}/breakpoint?studentId=${encodeURIComponent(studentId)}`),
  updateBreakpoint: ({ studentId, courseId, pageNum }) => requestJson(`/api/v1/student/coursewares/${encodeURIComponent(courseId)}/breakpoint`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ studentId, pageNum })
  }),
  getStats: (studentId, courseId) => requestJson(`/api/v1/student/coursewares/${encodeURIComponent(courseId)}/stats?studentId=${encodeURIComponent(studentId)}`),
  getWeakPoints: (studentId, courseId) => requestJson(`/api/v1/student/coursewares/${encodeURIComponent(courseId)}/weak-points?studentId=${encodeURIComponent(studentId)}`),
  saveNote: ({ studentId, courseId, pageNum, content, x = 0, y = 0 }) => requestJson(`/api/v1/student/coursewares/${encodeURIComponent(courseId)}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ studentId, pageNum, content, x, y })
  }),

  // 新增接口：分页查笔记
  listNotes: ({ studentId, courseId, pageNum, pageSize }) => {
    const query = buildQuery({ studentId, courseId, pageNum, pageSize })
    return requestJson(`/api/v1/student/notes?${query}`)
  },

  // 新增接口：删除笔记
  deleteNote: (noteId, studentId) => requestJson(`/api/v1/student/notes/${encodeURIComponent(noteId)}?studentId=${encodeURIComponent(studentId)}`, {
    method: 'DELETE'
  }),

  // 新增接口：新增收藏
  addFavorite: ({ studentId, courseId, nodeId, pageNum, title, tags }) => requestJson('/api/v1/student/favorites', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ studentId, courseId, nodeId, pageNum, title, tags })
  }),

  // 新增接口：分页查收藏
  listFavorites: ({ studentId, courseId, page, pageSize }) => {
    const query = buildQuery({ studentId, courseId, page, pageSize })
    return requestJson(`/api/v1/student/favorites?${query}`)
  },

  // 新增接口：删除收藏
  deleteFavorite: (favoriteId) => requestJson(`/api/v1/student/favorites/${encodeURIComponent(favoriteId)}`, {
    method: 'DELETE'
  }),

  // 新增接口：生成练习题
  generatePractice: ({ studentId, courseId, nodeId, pageNum, difficulty, count }) => requestJson('/api/v1/student/practice/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ studentId, courseId, nodeId, pageNum, difficulty, count })
  }),

  // 新增接口：提交练习答案
  submitPractice: ({ taskId, studentId, answers }) => requestJson('/api/v1/student/practice/submit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ taskId, studentId, answers })
  }),

  getPracticeHistory: ({ studentId, courseId, page, pageSize }) => {
    const query = buildQuery({ studentId, courseId, page, pageSize })
    return requestJson(`/api/v1/student/practice/history?${query}`)
  },

  getWrongQuestions: ({ studentId, courseId, page, pageSize }) => {
    const query = buildQuery({ studentId, courseId, page, pageSize })
    return requestJson(`/api/v1/student/practice/wrong-questions?${query}`)
  },

  retryWrongQuestion: ({ questionId, studentId }) => requestJson(`/api/v1/student/practice/wrong-questions/${encodeURIComponent(questionId)}/retry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ studentId })
  }),

  // 新增接口：节点专项讲解
  explainNode: ({ nodeId, courseId, pageNum, question }) => requestJson(`/api/v1/student/nodes/${encodeURIComponent(nodeId)}/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ courseId, pageNum, question })
  }),

  // 图谱维护能力：与教师端保持一致，复用同一后端能力
  syncKnowledgeGraph: (courseId) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/knowledge-graph/sync`, {
      method: 'POST'
    }),
  getKnowledgeGraphReferenceHealth: (courseId) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/knowledge-graph/reference-health`),
  repairKnowledgeGraphReferences: (courseId, body) =>
    requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/knowledge-graph/reference-health/repair`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || { confirm: true })
    }),

  // 复习计划相关接口
  createReviewPlan: ({ studentId, name, description, frequency }) => requestJson('/api/v1/student/review-plans', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ studentId, name, description, frequency })
  }),

  listReviewPlans: (studentId) => requestJson(`/api/v1/student/review-plans?studentId=${encodeURIComponent(studentId)}`),

  updateReviewPlan: (planId, updates) => requestJson(`/api/v1/student/review-plans/${encodeURIComponent(planId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates)
  }),

  deleteReviewPlan: (planId) => requestJson(`/api/v1/student/review-plans/${encodeURIComponent(planId)}`, {
    method: 'DELETE'
  }),

  addReviewPlanItem: ({ reviewPlanId, itemType, itemId, priority }) => requestJson(`/api/v1/student/review-plans/${encodeURIComponent(reviewPlanId)}/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reviewPlanId, itemType, itemId, priority })
  }),

  listReviewPlanItems: (planId) => requestJson(`/api/v1/student/review-plans/${encodeURIComponent(planId)}/items`),

  updateReviewPlanItem: (itemId, updates) => requestJson(`/api/v1/student/review-plan-items/${encodeURIComponent(itemId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates)
  }),

  deleteReviewPlanItem: (itemId) => requestJson(`/api/v1/student/review-plan-items/${encodeURIComponent(itemId)}`, {
    method: 'DELETE'
  })
}
