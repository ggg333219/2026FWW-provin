import { requestJson } from './request'

export const studentWeakPointApi = {
  explain: (weakPointId, weakPointName) => requestJson(`/api/v1/student/weak-points/${encodeURIComponent(weakPointId)}/explain?name=${encodeURIComponent(weakPointName || '')}`),
  generateTest: ({ weakPointId, ...body }) => requestJson(`/api/v1/student/weak-points/${encodeURIComponent(weakPointId)}/generate-test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  checkAnswer: ({ questionId, ...body }) => requestJson(`/api/v1/student/tests/${encodeURIComponent(questionId)}/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
}
