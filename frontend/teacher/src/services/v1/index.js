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
  health: async () => {
    let lastError = null
    for (const path of ['/api/health', '/health']) {
      try {
        const response = await fetch(`${API_BASE}${path}`, { cache: 'no-store' })
        if (response.ok) return response
        lastError = new Error(`健康检查失败: ${response.status}`)
      } catch (error) {
        lastError = error
      }
    }
    throw lastError || new Error('后端健康检查失败')
  },
  coursewares: teacherCoursewareApi,
  analytics: teacherAnalyticsApi,
  platform: teacherPlatformApi,
  intent: teacherIntentApi,
  material: teacherMaterialApi,
  generation: teacherGenerationApi,
  version: teacherVersionApi,
  rag: teacherRagApi
}
