import { requestJson, requestSSE } from './request'

export const studentQaApi = {
  ask: ({ courseId, ...body }) => requestJson(`/api/v1/ai/coursewares/${encodeURIComponent(courseId)}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  stream: (body, handlers) => requestSSE('/api/v1/student/qa/stream', body, handlers)
}
