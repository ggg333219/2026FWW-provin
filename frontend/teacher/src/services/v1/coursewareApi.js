import { requestJson } from './request'

export const teacherCoursewareApi = {
  list: () => requestJson('/api/v1/teacher/coursewares'),
  upload: (formData) => requestJson('/api/v1/teacher/coursewares/upload', {
    method: 'POST',
    body: formData
  }),
  remove: (courseId) => requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}`, {
    method: 'DELETE'
  }),
  publish: ({ courseId, scope, teachingCourseId, teachingCourseTitle, courseClassId, courseClassName }) => requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/publish`, {
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
  getScript: (courseId, pageNum) => requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/scripts/${pageNum}`),
  saveScript: ({ courseId, pageNum, content }) => requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/scripts/${pageNum}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  }),
  getNodes: (courseId, pageNum) => requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/pages/${pageNum}/nodes`),
  saveNodes: ({ courseId, pageNum, nodes }) => requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/pages/${pageNum}/nodes`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes })
  }),
  generateScript: ({ courseId, pageNum, mode = 'llm', evidence = null }) => {
    // evidence 为可选参数（S2 证据透传）：有则附加到请求 body，无则行为与原来一致
    const body = { pageNum, mode }
    if (evidence) {
      body.evidence = evidence
    }
    return requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/scripts/ai-generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
  },
  generateAudio: ({ courseId, pageNum }) => requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/pages/${pageNum}/audio`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  }),
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
    })
}
