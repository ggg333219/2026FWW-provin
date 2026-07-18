import { API_BASE } from '../../config/api'
import { handleMockRequest } from './mockBackend'

export async function requestJson(path, options = {}) {
  try {
    const response = await fetch(`${API_BASE}${path}`, options)
    const payload = await response.json().catch(() => ({}))
    if (!response.ok || (typeof payload.code !== 'undefined' && payload.code !== 200)) {
      throw new Error(payload.message || `请求失败: ${response.status}`)
    }
    return payload
  } catch (error) {
    const mockPayload = handleMockRequest(path, options, error)
    if (mockPayload) {
      return mockPayload
    }
    throw error
  }
}
