import { requestJson } from './request'

export const studentSessionApi = {
  start: ({ userId, courseId }) => requestJson('/api/v1/student/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, courseId })
  }),
  updateProgress: ({ sessionId, userId, courseId, currentPage, currentNodeId, currentTimeSec = 0 }) => requestJson('/api/v1/student/sessions/progress', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sessionId, userId, courseId, currentPage, currentNodeId, currentTimeSec })
  })
}
