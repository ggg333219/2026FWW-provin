import { API_BASE } from '../../config/api'
import { studentCoursewareApi } from './coursewareApi'
import { studentSessionApi } from './sessionApi'
import { studentQaApi } from './qaApi'
import { studentWeakPointApi } from './weakPointApi'
import { studentKnowledgeApi } from './knowledgeApi'
import { studentNotificationApi } from './notificationApi'
import { studentTaskApi } from './taskApi'
import { studentPlatformApi } from './platformApi'
import { studentRecommendApi } from './recommendApi'

export const studentV1Api = {
  health: () => fetch(`${API_BASE}/health`, { cache: 'no-store' }),
  coursewares: studentCoursewareApi,
  sessions: studentSessionApi,
  qa: studentQaApi,
  weakPoints: studentWeakPointApi,
  knowledge: studentKnowledgeApi,
  notifications: studentNotificationApi,
  tasks: studentTaskApi,
  platform: studentPlatformApi,
  recommend: studentRecommendApi
}
