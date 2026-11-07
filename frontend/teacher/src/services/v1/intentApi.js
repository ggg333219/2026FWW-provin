import { requestJson } from './request'

const unwrap = (payload) => payload?.data ?? payload

/** S1 意图理解 API：教师端只访问 Go Backend，由 Go 转发 AI Engine。 */
export const teacherIntentApi = {
  extract: async ({ sessionId, messages, llmConfig = {} }) => {
    // 只取白名单字段：使用者自带模型配置由 llmConfigStore.requestConfig() 提供，
    // 未配置时为空对象，请求体形状与旧版完全一致。
    const { api_key: apiKey, base_url: baseUrl, model } = llmConfig || {}
    const llmFields = {
      ...(apiKey ? { api_key: apiKey } : {}),
      ...(baseUrl ? { base_url: baseUrl } : {}),
      ...(model ? { model } : {})
    }
    const payload = await requestJson('/api/v1/intent/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, messages, ...llmFields }),
      // H1 三层超时统一：前端 90s ≥ Go 网关 90s ≥ 引擎 LLM 60s×2，
      // 保证引擎的一次重试周期不被前端先切断。
      timeoutMs: 90000
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
