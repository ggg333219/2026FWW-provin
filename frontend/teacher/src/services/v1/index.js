import { API_BASE } from '../../config/api'
import { teacherCoursewareApi } from './coursewareApi'
import { teacherAnalyticsApi } from './analyticsApi'
import { teacherPlatformApi } from './platformApi'

export const teacherV1Api = {
  health: () => fetch(`${API_BASE}/health`, { cache: 'no-store' }),
  coursewares: teacherCoursewareApi,
  analytics: teacherAnalyticsApi,
  platform: teacherPlatformApi
}
