import { requestJson } from './request'

const buildQuery = (params) => {
  return Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&')
}

export const studentTaskApi = {
  listScheduled: ({ studentId, status, page, pageSize }) => {
    const query = buildQuery({ studentId, status, page, pageSize })
    return requestJson(`/api/v1/tasks/scheduled?${query}`)
  },

  listStatuses: ({ studentId, status, page, pageSize }) => {
    const query = buildQuery({ studentId, status, page, pageSize })
    return requestJson(`/api/v1/tasks/statuses?${query}`)
  },

  executeNow: (taskId) => requestJson(`/api/v1/tasks/scheduled/${encodeURIComponent(taskId)}/execute`, {
    method: 'POST'
  }),

  remove: (taskId) => requestJson(`/api/v1/tasks/scheduled/${encodeURIComponent(taskId)}`, {
    method: 'DELETE'
  })
}
