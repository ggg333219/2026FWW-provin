import { requestJson } from './v1/request'
import { AI_API_BASE } from '../config/api'

async function requestAiJson(path, options = {}, requestError = null) {
  const response = await fetch(`${AI_API_BASE}${path}`, options)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(payload?.detail)
      ? payload.detail.map(item => item?.msg).filter(Boolean).join('; ')
      : (payload?.detail || payload?.message)
    throw new Error(detail || requestError?.message || `请求失败: ${response.status}`)
  }
  return payload
}

function toFiniteNumber(value, fallback) {
  const str = String(value || '').trim()
  if (!str) return fallback
  const n = Number(str)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

function generateTempUuid(prefix = 'tmp') {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  const seed = `${Date.now().toString(16)}_${Math.random().toString(16).slice(2)}`
  return `${prefix}_${seed}`
}

function normalizeItemsWithId(items, prefix) {
  if (!Array.isArray(items)) return []
  return items.map((item, index) => {
    const safeItem = item && typeof item === 'object' ? item : { value: item }
    return {
      ...safeItem,
      id: safeItem.id || generateTempUuid(`${prefix}_${index}`)
    }
  })
}

/**
 * 获取教学迭代概览。
 * @param {string} courseId
 * @returns {Promise<{basicNodeTree: Array, pendingNodes: Array, pendingCases: Array}>}
 */
export async function getIterationOverview(courseId) {
  const normalizedCourseId = encodeURIComponent(String(courseId || '').trim())
  let payload = null
  let requestError = null

  try {
    payload = await requestJson(`/api/v1/teacher/iteration-overview/${normalizedCourseId}`, {
      method: 'GET'
    })
  } catch (error) {
    requestError = error
  }

  if (!payload) {
    payload = await requestAiJson(`/api/v1/teacher/iteration-overview/${normalizedCourseId}`, {
      method: 'GET'
    }, requestError)
  }

  const source = payload && typeof payload === 'object' ? (payload.data || payload) : {}

  return {
    ...source,
    basicNodeTree: normalizeItemsWithId(source.basicNodeTree, 'basic_node'),
    pendingNodes: normalizeItemsWithId(source.pendingNodes, 'pending_node'),
    pendingCases: normalizeItemsWithId(source.pendingCases, 'pending_case')
  }
}

/**
 * 基于教学迭代节点顺序生成讲稿。
 * @param {{ courseId?: string, nodeOrder: string[] }} payload
 * @returns {Promise<{ data: string }>}
 */
export async function generateIterationScript(payload) {
  const body = payload && typeof payload === 'object' ? payload : { nodeOrder: [] }
  let response = null
  let requestError = null

  try {
    response = await requestJson('/api/v1/teacher/iteration/script-generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
  } catch (error) {
    requestError = error
  }

  if (!response) {
    response = await requestAiJson('/api/v1/teacher/iteration/script-generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }, requestError)
  }

  const data = response && typeof response === 'object' ? (response.data || response) : ''
  if (typeof data === 'string') return { data }
  if (data && typeof data === 'object') {
    return { data: String(data.markdown || data.content || '') }
  }
  return { data: '' }
}

/**
 * 保存学情迭代大纲与绑定关系。
 * @param {string} courseId
 * @param {{ nodeTree?: Array, bindingMap?: Record<string, string[]> }} payload
 * @returns {Promise<{ ok: boolean, updatedAt?: string }>}
 */
export async function saveIterationOverview(courseId, payload = {}) {
  const normalizedCourseId = encodeURIComponent(String(courseId || '').trim())
  const body = {
    nodeTree: Array.isArray(payload.nodeTree) ? payload.nodeTree : [],
    bindingMap: payload.bindingMap && typeof payload.bindingMap === 'object' ? payload.bindingMap : {}
  }

  let response = null
  let requestError = null

  try {
    response = await requestJson(`/api/v1/teacher/iteration-overview/${normalizedCourseId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
  } catch (error) {
    requestError = error
  }

  if (!response) {
    response = await requestAiJson(`/api/v1/teacher/iteration-overview/${normalizedCourseId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }, requestError)
  }

  const data = response && typeof response === 'object' ? (response.data || response) : {}
  return {
    ok: Boolean(data.ok ?? true),
    updatedAt: data.updatedAt || ''
  }
}

/**
 * 智能资源推荐（教师端）。
 * @param {{
 *   keyword?: string,
 *   stage?: string,
 *   subject?: string,
 *   type?: string,
 *   difficulty?: string,
 *   duration?: string,
 *   lang?: string,
 *   budget?: string,
 *   source?: string,
 *   page?: number,
 *   pageSize?: number,
 *   sortBy?: string
 * }} params
 * @returns {Promise<{ list: Array, total: number, page: number, pageSize: number, hasMore: boolean }>}
 */
export async function fetchRecommendedResources(params = {}) {
  const normalizedType = String(params.type || '').trim()
  const type = normalizedType === '题库' ? '题库' : '网课'
  const body = {
    keyword: String(params.keyword || '').trim(),
    type,
    difficulty: toFiniteNumber(params.difficulty, 0.5),
    duration: toFiniteNumber(params.duration, 30),
    budget: toFiniteNumber(params.budget, 0),
    source_preference: Array.isArray(params.source_preference)
      ? params.source_preference
      : (String(params.source || '').trim() ? [String(params.source || '').trim()] : [])
  }

  const stage = String(params.stage || '').trim()
  if (stage) {
    // 后端 StageType 是枚举，传空字符串会触发 422
    body.stage = stage
  }

  const subject = String(params.subject || '').trim()
  if (subject) {
    body.subject = subject
  }

  let payload = null
  let requestError = null

  try {
    // 优先走统一网关（与其他教师端接口一致）
    payload = await requestJson('/api/v1/teacher/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
  } catch (error) {
    requestError = error
  }

  if (!payload) {
    // 网关不可用时回退到 AI 服务直连
    const response = await fetch(`${AI_API_BASE}/api/v1/teacher/recommend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })

    payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = Array.isArray(payload?.detail)
        ? payload.detail.map(item => item?.msg).filter(Boolean).join('; ')
        : (payload?.detail || payload?.message)
      throw new Error(detail || requestError?.message || `请求失败: ${response.status}`)
    }
  }

  const source = payload && typeof payload === 'object' ? (payload.data || payload) : {}
  const list = Array.isArray(source.recommended_resources)
    ? source.recommended_resources
    : (Array.isArray(source.resources)
      ? source.resources
      : (Array.isArray(source.list) ? source.list : []))
  const total = Number(source.total || list.length || 0)
  const page = Number(source.page || params.page || 1)
  const pageSize = Number(source.pageSize || params.pageSize || 10)
  const hasMore = typeof source.hasMore === 'boolean' ? source.hasMore : (page * pageSize < total)

  return { list, total, page, pageSize, hasMore }
}

export const teacherV1Service = {
  getIterationOverview,
  generateIterationScript,
  saveIterationOverview,
  fetchRecommendedResources
}
