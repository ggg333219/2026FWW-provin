import { requestJson } from './request'

const unwrap = (payload) => payload?.data ?? payload

/** S1 意图理解 API：教师端只访问 Go Backend，由 Go 转发 AI Engine。 */
export const teacherIntentApi = {
  extract: async ({ sessionId, messages }) => {
    const payload = await requestJson('/api/v1/intent/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, messages }),
      timeoutMs: 45000
    })
    return unwrap(payload)
  },

  confirm: async (sessionId) => {
    const payload = await requestJson('/api/v1/intent/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
      timeoutMs: 20000
    })
    return unwrap(payload)
  },

  // 兼容旧调用方；新 S1 工作台使用 extract。
  parseIntent: ({ input }) => teacherIntentApi.extract({
    sessionId: `sess_s1_${Date.now().toString(36)}`,
    messages: [{ role: 'teacher', content: input }]
  })
}
