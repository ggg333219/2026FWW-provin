import { requestJson } from './request'

function buildQuery(params = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return
    }
    const normalized = typeof value === 'string' ? value.trim() : value
    if (normalized === '' || normalized === false) {
      return
    }
    search.set(key, String(normalized))
  })
  const query = search.toString()
  return query ? `?${query}` : ''
}

export const teacherPlatformApi = {
  getOverview: () => requestJson('/api/v1/platform/overview'),
  syncUser: (body) => requestJson('/api/v1/platform/syncUser', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  syncCourse: (body) => requestJson('/api/v1/platform/syncCourse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  listUsers: (params = {}) => requestJson(`/api/v1/platform/users${buildQuery(params)}`),
  getUserDetail: (userId) => requestJson(`/api/v1/platform/users/${encodeURIComponent(userId)}`),
  listCourses: (params = {}) => requestJson(`/api/v1/platform/courses${buildQuery(params)}`),
  getCourseDetail: (courseId) => requestJson(`/api/v1/platform/courses/${encodeURIComponent(courseId)}`),
  createCourse: (body) => requestJson('/api/v1/platform/courses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  updateCourse: (courseId, body) => requestJson(`/api/v1/platform/courses/${encodeURIComponent(courseId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  deleteCourse: (courseId) => requestJson(`/api/v1/platform/courses/${encodeURIComponent(courseId)}`, {
    method: 'DELETE'
  }),
  listClasses: (params = {}) => requestJson(`/api/v1/platform/classes${buildQuery(params)}`),
  getClassDetail: (classId) => requestJson(`/api/v1/platform/classes/${encodeURIComponent(classId)}`),
  createClass: (body) => requestJson('/api/v1/platform/classes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  updateClass: (classId, body) => requestJson(`/api/v1/platform/classes/${encodeURIComponent(classId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  deleteClass: (classId) => requestJson(`/api/v1/platform/classes/${encodeURIComponent(classId)}`, {
    method: 'DELETE'
  }),
  listEnrollments: (params = {}) => requestJson(`/api/v1/platform/enrollments${buildQuery(params)}`),
  getEnrollmentDetail: (enrollmentId) => requestJson(`/api/v1/platform/enrollments/${encodeURIComponent(enrollmentId)}`),
  createEnrollment: (body) => requestJson('/api/v1/platform/enrollments', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  updateEnrollment: (enrollmentId, body) => requestJson(`/api/v1/platform/enrollments/${encodeURIComponent(enrollmentId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }),
  deleteEnrollment: (enrollmentId) => requestJson(`/api/v1/platform/enrollments/${encodeURIComponent(enrollmentId)}`, {
    method: 'DELETE'
  })
}