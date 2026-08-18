import { API_BASE } from '../../config/api'
import { handleMockRequest } from './mockBackend'

const MOCK_FLAG_KEY = 'fuww_mock_mode'

// JSON 请求超时（multipart 上传不设超时，避免大文件被误中止）。
// 真实解析/RAG 涉及 LLM 调用，可能超过数秒；超时不再切换全局 mock，
// 而是如实抛错，由调用方优雅降级（重试轮询 / 空态提示）。
const REQUEST_TIMEOUT_MS = 10000

// Mock 模式下探测后端健康检查的节流窗口：探测失败后 8s 内不再重复探测。
const PROBE_TTL_MS = 8000

let lastProbeFailedAt = 0

function isMockMode() {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(MOCK_FLAG_KEY) === 'true'
}

function setMockMode() {
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(MOCK_FLAG_KEY, 'true')
    } catch {
      // noop
    }
  }
}

function clearMockMode() {
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.removeItem(MOCK_FLAG_KEY)
    } catch {
      // noop
    }
  }
}

/**
 * 探测后端是否已恢复可用。
 * 仅当处于 Mock 模式时调用：后端重启/恢复后，清除 mock 标志，重新走真实链路。
 */
async function isBackendReachable() {
  if (typeof fetch === 'undefined') return false
  const now = Date.now()
  if (lastProbeFailedAt && now - lastProbeFailedAt < PROBE_TTL_MS) return false
  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 1500)
    const resp = await fetch(`${API_BASE}/api/health`, {
      method: 'GET',
      signal: controller.signal,
      cache: 'no-store'
    })
    clearTimeout(timer)
    if (resp.ok) {
      lastProbeFailedAt = 0
      return true
    }
    lastProbeFailedAt = now
    return false
  } catch {
    lastProbeFailedAt = now
    return false
  }
}

export async function requestJson(path, options = {}) {
  // 若已确认是 Mock 模式：先探测后端是否恢复；恢复则清除标志并继续走真实请求。
  // 否则直接返回 Mock（离线演示保持快速响应，不重复等待超时）。
  if (isMockMode()) {
    if (await isBackendReachable()) {
      clearMockMode()
    } else {
      const mockPayload = handleMockRequest(path, options, new Error('mock mode'))
      if (mockPayload) return mockPayload
      throw new Error(`[Mock] 未匹配路由: ${options?.method || 'GET'} ${path}`)
    }
  }

  try {
    const { timeoutMs = REQUEST_TIMEOUT_MS, ...fetchOptions } = options
    const isMultipart = typeof FormData !== 'undefined' && fetchOptions.body instanceof FormData
    const controller = new AbortController()
    const timer = isMultipart
      ? 0
      : setTimeout(() => controller.abort(), timeoutMs)
    const response = await fetch(`${API_BASE}${path}`, { ...fetchOptions, signal: controller.signal })
    if (timer) clearTimeout(timer)
    const payload = await response.json().catch(() => ({}))
    if (!response.ok || (typeof payload.code !== 'undefined' && payload.code !== 200)) {
      // 标记 HTTP 级错误（后端可达但路由缺失/业务错误），区别于网络不可达
      const err = new Error(payload.message || `请求失败: ${response.status}`)
      err.httpStatus = response.status
      throw err
    }
    return payload
  } catch (error) {
    // 超时（AbortError）：后端可能仍在慢速处理（如 RAG 嵌入/生成）。
    // 不切换全局 mock、也不回退 Mock，避免“真实数据 → 假数据”跳变；
    // 交由调用方优雅降级（空态提示 / 轮询重试）。
    if (error && error.name === 'AbortError') {
      throw error
    }
    // 尝试 Mock 回退
    const mockPayload = handleMockRequest(path, options, error)
    if (mockPayload) {
      // 仅网络层不可达（连接拒绝/断开，无 httpStatus 的 TypeError）才全局切换 Mock；
      // HTTP 级错误（路由缺失）仅对当前请求回退 Mock，其余请求继续走真实后端。
      if (!error.httpStatus) {
        setMockMode()
      }
      if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function' && typeof CustomEvent === 'function') {
        window.dispatchEvent(new CustomEvent('fuww:mock-fallback', {
          detail: { path, reason: error?.message || '网络不可达' }
        }))
      }
      return mockPayload
    }
    throw error
  }
}
