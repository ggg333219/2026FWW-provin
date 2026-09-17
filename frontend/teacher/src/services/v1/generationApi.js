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
  createGeneration: ({
    session_id,
    course_id,
    title,
    markdown,
    intent,
    evidence_packet,
    template_id,
    // S3 规范 3.6 参数
    outline_id,
    outline_version,
    outline_confirmed,
    generate_mode,
    project_id
  } = {}) =>
    requestJson('/api/v1/gen/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: session_id || '',
        course_id,
        title: title || '',
        markdown: markdown || '',
        intent: intent || undefined,
        evidence_packet: evidence_packet || null,
        project_id: project_id || '',
        template_id: template_id || 'default',
        // 规范 3.6：确认大纲后必须传递完整 outline 上下文
        ...(outline_id ? { outline_id, outline_version, outline_confirmed: !!outline_confirmed, generate_mode: generate_mode || 'page_incremental' } : {})
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

  /** 将当前内容、样式和证据引用固化为新的正式版本快照 */
  finalize: ({ generation_id, nodes, course_name, summary, outline_id, outline_version } = {}) =>
    requestJson('/api/v1/gen/finalize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        generation_id: generation_id || '',
        nodes: nodes || [],
        course_name: course_name || '未命名课件',
        summary: summary || '教师保存的新版本',
        outline_id: outline_id || '',
        outline_version: outline_version || 0
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

  // ================================================================
  // page API（S3 单页操作，规范 3.7~3.10）
  // ================================================================

  /** GET /api/v1/generations/{generation_id} 查询生成任务状态（规范 3.7） */
  getGeneration: (generationId) =>
    requestJson(`/api/v1/generations/${encodeURIComponent(generationId)}`),

  /** GET /api/v1/generations/{generation_id}/pages/{page_id} 查询单页（规范 3.8） */
  getPage: (generationId, pageId) =>
    requestJson(
      `/api/v1/generations/${encodeURIComponent(generationId)}/pages/${encodeURIComponent(pageId)}`
    ),

  /** POST /api/v1/generations/{generation_id}/pages/{page_id}/regenerate 单页重生成（规范 3.9） */
  regeneratePage: (generationId, pageId, { reason, mode = 'ai' } = {}) =>
    requestJson(
      `/api/v1/generations/${encodeURIComponent(generationId)}/pages/${encodeURIComponent(pageId)}/regenerate`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: reason || '', mode })
      }
    ),

  /** POST /api/v1/generations/{generation_id}/pages/{page_id}/revise AI修改页面（规范 3.10） */
  revisePage: (generationId, pageId, { message, base_version, auto_apply = false } = {}) =>
    requestJson(
      `/api/v1/generations/${encodeURIComponent(generationId)}/pages/${encodeURIComponent(pageId)}/revise`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message || '',
          base_version: base_version != null ? base_version : 1,
          auto_apply
        })
      }
    ),

  // ================================================================
  // 兼容旧接口（保留，Phase 4 清理）
  // ================================================================

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
