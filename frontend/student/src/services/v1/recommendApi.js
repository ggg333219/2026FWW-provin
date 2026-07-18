import { requestJson } from './request'
import { AI_API_BASE } from '../../config/api'

const toFiniteNumber = (value, fallback) => {
  const str = String(value || '').trim()
  if (!str) return fallback
  const n = Number(str)
  return Number.isFinite(n) && n > 0 ? n : fallback
}

const requestAiJson = async (path, options = {}, requestError = null) => {
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

export const studentRecommendApi = {
  async fetchRecommendedResources(params = {}) {
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
    if (stage) body.stage = stage

    const subject = String(params.subject || '').trim()
    if (subject) body.subject = subject

    let payload = null
    let requestError = null

    try {
      payload = await requestJson('/api/v1/teacher/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
    } catch (error) {
      requestError = error
    }

    if (!payload) {
      payload = await requestAiJson('/api/v1/teacher/recommend', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      }, requestError)
    }

    const source = payload && typeof payload === 'object' ? (payload.data || payload) : {}
    const list = Array.isArray(source.recommended_resources)
      ? source.recommended_resources
      : (Array.isArray(source.resources)
        ? source.resources
        : (Array.isArray(source.list) ? source.list : []))

    return {
      list,
      total: Number(source.total || list.length || 0),
      page: Number(source.page || params.page || 1),
      pageSize: Number(source.pageSize || params.pageSize || 10),
      hasMore: typeof source.hasMore === 'boolean'
        ? source.hasMore
        : (Number(source.page || params.page || 1) * Number(source.pageSize || params.pageSize || 10) < Number(source.total || list.length || 0))
    }
  }
}
