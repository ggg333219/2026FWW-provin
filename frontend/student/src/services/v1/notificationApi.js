import { requestJson } from './request'

const buildQuery = (params) => {
  return Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&')
}

export const studentNotificationApi = {
  list: ({ studentId, status, page, pageSize }) => {
    const query = buildQuery({ studentId, status, page, pageSize })
    return requestJson(`/api/v1/notifications?${query}`)
  },

  getUnreadCount: (studentId) => requestJson(`/api/v1/notifications/unread-count?studentId=${encodeURIComponent(studentId)}`),

  markAsRead: (notificationId) => requestJson(`/api/v1/notifications/${encodeURIComponent(notificationId)}/read`, {
    method: 'PUT'
  }),

  markAllAsRead: (studentId) => requestJson(`/api/v1/notifications/read-all?studentId=${encodeURIComponent(studentId)}`, {
    method: 'PUT'
  }),

  remove: (notificationId) => requestJson(`/api/v1/notifications/${encodeURIComponent(notificationId)}`, {
    method: 'DELETE'
  }),

  sendImmediate: ({ studentId, title, content, type, channels = ['app'] }) => requestJson('/api/v1/notifications/send-immediate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ studentId, title, content, type, channels })
  })
}
