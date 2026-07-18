import { API_BASE } from '../config/api'

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || (typeof payload.code !== 'undefined' && payload.code !== 200)) {
    throw new Error(payload.message || `请求失败: ${response.status}`)
  }
  return payload
}

async function requestSSE(path, body, handlers = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })

  if (!response.ok || !response.body) {
    throw new Error(`请求失败: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let currentEvent = 'message'

  const emitFrame = (frame) => {
    const lines = frame.split('\n').map(line => line.trim()).filter(Boolean)
    let dataLine = ''
    currentEvent = 'message'
    lines.forEach((line) => {
      if (line.startsWith('event:')) currentEvent = line.slice(6).trim()
      if (line.startsWith('data:')) dataLine += line.slice(5).trim()
    })
    if (!dataLine) return
    let payload = {}
    try {
      payload = JSON.parse(dataLine)
    } catch (error) {
      payload = { text: dataLine }
    }
    const handler = handlers[currentEvent]
    if (typeof handler === 'function') handler(payload)
  }

  let doneReading = false
  while (!doneReading) {
    const { value, done } = await reader.read()
    doneReading = done
    if (doneReading) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''
    frames.forEach(emitFrame)
  }

  if (buffer.trim()) emitFrame(buffer)
}

export const studentApi = {
  checkHealth: () => fetch(`${API_BASE}/health`, { cache: 'no-store' }),
  getCoursewareList: () => requestJson('/api/student/courseware-list'),
  getScript: (courseId, page) => requestJson(`/api/student/script/${encodeURIComponent(courseId)}/${page}`),
  startSession: (body) => requestJson('/api/student/session/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  updateProgress: (body) => requestJson('/api/student/progress/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  askQuestion: (body) => requestJson(`/api/v1/ai/coursewares/${encodeURIComponent(body.courseId)}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  streamQuestion: (body, handlers) => requestSSE('/api/student/qa/stream', body, handlers),
  getBreakpoint: (studentId, courseId) => requestJson(`/api/v1/student/coursewares/${encodeURIComponent(courseId)}/breakpoint?studentId=${encodeURIComponent(studentId)}`),
  saveBreakpoint: (body) => requestJson(`/api/v1/student/coursewares/${encodeURIComponent(body.courseId)}/breakpoint`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ studentId: body.studentId, pageNum: body.lastPage || body.pageNum || 1 })
  }),
  getStudyData: (studentId, courseId) => requestJson(`/api/v1/student/coursewares/${encodeURIComponent(courseId)}/stats?studentId=${encodeURIComponent(studentId)}`),
  getWeakPointList: (studentId, courseId) => requestJson(`/api/v1/student/coursewares/${encodeURIComponent(courseId)}/weak-points?studentId=${encodeURIComponent(studentId)}`),
  parseKnowledge: (body) => requestJson('/api/ai/parseKnowledge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  getWeakPointExplain: (weakPointId, weakPointName) => requestJson(`/api/v1/student/weak-points/${encodeURIComponent(weakPointId)}/explain?name=${encodeURIComponent(weakPointName || '')}`),
  getWeakPointTest: (body) => requestJson(`/api/v1/student/weak-points/${encodeURIComponent(body.weakPointId)}/generate-test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  checkAnswer: (body) => requestJson(`/api/v1/student/tests/${encodeURIComponent(body.questionId)}/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
}
