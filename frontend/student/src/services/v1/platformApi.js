import { requestJson } from './request'

const buildQuery = (params = {}) => {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) return
    const normalized = typeof value === 'string' ? value.trim() : value
    if (normalized === '') return
    search.set(key, String(normalized))
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

export const studentPlatformApi = {
  listCourses: (params = {}) => requestJson(`/api/v1/platform/courses${buildQuery(params)}`),
  listClasses: (params = {}) => requestJson(`/api/v1/platform/classes${buildQuery(params)}`)
}
