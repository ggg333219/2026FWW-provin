import { AI_API_BASE } from '../../config/api'
import { requestJson } from './request'

function toFiniteNumber(value, fallback) {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function normalizeRecommendResponse(payload, page, pageSize) {
  const source = payload && typeof payload === 'object' ? (payload.data || payload) : {}
  const list = Array.isArray(source.recommended_resources)
    ? source.recommended_resources
    : (Array.isArray(source.resources)
      ? source.resources
      : (Array.isArray(source.list) ? source.list : []))

  const total = Number(source.total || list.length || 0)
  const safePage = Number(source.page || page || 1)
  const safePageSize = Number(source.pageSize || pageSize || 10)
  const hasMore = typeof source.hasMore === 'boolean' ? source.hasMore : (safePage * safePageSize < total)

  return {
    list,
    total,
    page: safePage,
    pageSize: safePageSize,
    hasMore
  }
}

async function fetchRecommendedResources(params = {}) {
  const page = Number(params.page || 1)
  const pageSize = Number(params.pageSize || 10)
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
    body.stage = stage
  }

  const subject = String(params.subject || '').trim()
  if (subject) {
    body.subject = subject
  }

  let payload = null
  let gatewayError = null

  try {
    payload = await requestJson('/api/v1/teacher/recommend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
  } catch (error) {
    gatewayError = error
  }

  if (!payload) {
    const response = await fetch(`${AI_API_BASE}/api/v1/teacher/recommend`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })

    payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      const detail = Array.isArray(payload?.detail)
        ? payload.detail.map((item) => item?.msg).filter(Boolean).join('; ')
        : (payload?.detail || payload?.message)
      throw new Error(detail || gatewayError?.message || `请求失败: ${response.status}`)
    }
  }

  return normalizeRecommendResponse(payload, page, pageSize)
}

export const teacherAnalyticsApi = {
  getStats: (courseId) => requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/stats`),
  getCardData: (courseId) => requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/card-data`),
  getQuestionRecords: (courseId, page = 1, pageSize = 100) => requestJson(`/api/v1/teacher/coursewares/${encodeURIComponent(courseId)}/questions?page=${page}&pageSize=${pageSize}`),
  fetchRecommendedResources
}
