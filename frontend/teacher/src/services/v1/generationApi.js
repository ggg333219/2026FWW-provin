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
  createGeneration: ({ session_id, course_id, title, markdown, intent, evidence_packet, template_id } = {}) =>
    requestJson('/api/v1/gen/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: session_id || '',
        course_id,
        title: title || '',
        markdown: markdown || '',
        // S1 确认后的结构化意图直接透传（未确认时省略，后端以 title 构建默认意图）
        intent: intent || undefined,
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

  /** 获取预览 (gen/preview)
   *  支持两种调用：
   *    - inline nodes：直接渲染当前节点树
   *    - 版本快照：传 gen_id（可选 version），后端按版本恢复节点渲染
   */
  preview: ({ nodes, course_name, gen_id, version } = {}) =>
    requestJson('/api/v1/gen/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nodes: nodes || [],
        course_name: course_name || '课件预览',
        gen_id: gen_id || '',
        version: version || null
      })
    }),

  /** 生成 HTML 课件预览（deck-skill，直连 AI Engine） */
  skillDeckPreview: (params = {}) => {
    const { intent = {}, evidence_packet = null, nodes = null, template_id = 'deck-swiss-edu', palette = 'klein-blue' } = params || {}
    return fetch(`${AI_API_BASE}/api/v1/skill/deck`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intent, evidence_packet, nodes, template_id, palette })
    }).then(r => r.json())
  },

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
