import { AI_API_BASE } from '../../config/api'
import { requestJson } from './request'

/**
 * S3 讲稿生成 API (Studio)
 *
 * 负责讲稿的生成、节点树管理、分段与音频生成。
 *
 * 注意：S2 讲稿/节点 CRUD 方法在 coursewareApi.js 中，
 * 本文件仅包含 S3 gen API（生成 + 修改 + 预览）。
 */
export const teacherGenerationApi = {
  // ================================================================
  // gen API（S3 生成 + 修改 + 预览）
  // ================================================================

  /** 创建生成任务 (gen/create) */
  createGeneration: ({ session_id, course_id, title, markdown, evidence_packet, template_id } = {}) =>
    requestJson('/api/v1/gen/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: session_id || '',
        course_id,
        title: title || '',
        markdown: markdown || '',
        evidence_packet: evidence_packet || null,
        template_id: template_id || 'default'
      })
    }),

  /** 查询生成任务状态 (gen/status) */
  getGenerationStatus: (taskId) =>
    requestJson(`/api/v1/gen/status/${encodeURIComponent(taskId)}`),

  /** 提交修改命令 (gen/modify) */
  modifyNodes: ({ generation_id, commands, nodes } = {}) =>
    requestJson('/api/v1/gen/modify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        generation_id,
        commands: commands || [],
        nodes: nodes || []
      })
    }),

  /** 获取预览 (gen/preview) */
  preview: ({ nodes, course_name } = {}) =>
    requestJson('/api/v1/gen/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nodes: nodes || [],
        course_name: course_name || '课件预览'
      })
    }),

  /** 获取增强讲稿（AI API 模式，已废弃，保留兼容） */
  getEnhancedScript: (params = {}) => {
    return fetch(`${AI_API_BASE}/generate-enhanced`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        markdown: params.markdown,
        course_name: params.courseName || '未命名课程',
        mode: params.mode || 'llm'
      })
    }).then(r => r.json())
  }
}
