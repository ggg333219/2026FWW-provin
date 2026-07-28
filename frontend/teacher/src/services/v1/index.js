import { API_BASE } from '../../config/api'
import { teacherCoursewareApi } from './coursewareApi'
import { teacherAnalyticsApi } from './analyticsApi'
import { teacherPlatformApi } from './platformApi'
import { teacherIntentApi } from './intentApi'
import { teacherMaterialApi } from './materialApi'
import { teacherGenerationApi } from './generationApi'
import { teacherVersionApi } from './versionApi'
import { teacherRagApi } from './ragApi'

export const teacherV1Api = {
  health: () => fetch(`${API_BASE}/health`, { cache: 'no-store' }),
  coursewares: teacherCoursewareApi,
  analytics: teacherAnalyticsApi,
  platform: teacherPlatformApi,
  intent: teacherIntentApi,
  material: teacherMaterialApi,
  generation: teacherGenerationApi,
  version: teacherVersionApi,
  rag: teacherRagApi
}
