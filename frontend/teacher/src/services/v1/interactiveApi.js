import { requestJson } from './request'

/**
 * S3 互动资源 API — 对接 Go 后端 /api/v1/interactive/* 和
 * /api/v1/generations/{gen_id}/nodes/{node_id}/interactive
 *
 * 接口规范：文档/S3数据与接口规范.md 第3章 3.11~3.13
 */

/** 互动规划数据结构（InteractivePlan） */
export const InteractiveKinds = ['quiz', 'flashcard', 'poll', 'game']
export const InteractiveDeliveries = ['html5_link', 'ppt_native', 'standalone_html']

export const teacherInteractiveApi = {
  /**
   * POST /api/v1/generations/{generation_id}/nodes/{node_id}/interactive
   * 生成 HTML5 互动资源（规范 3.11）
   */
  generate: ({ generation_id, node_id, interactive_plan } = {}) =>
    requestJson(
      `/api/v1/generations/${encodeURIComponent(generation_id)}/nodes/${encodeURIComponent(node_id)}/interactive`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          interactive_plan: interactive_plan || {
            enabled: true,
            kind: 'quiz',
            question_count: 3,
            duration_minutes: 5,
            auto_grading: true,
            delivery: 'html5_link'
          }
        })
      }
    ),

  /**
   * GET /api/v1/interactive/assets/{interactive_asset_id}
   * 查询互动资源状态（规范 3.12）
   */
  getAsset: (assetId) =>
    requestJson(`/api/v1/interactive/assets/${encodeURIComponent(assetId)}`),

  /**
   * POST /api/v1/generations/{generation_id}/pages/{page_id}/interactive-link
   * 建立页面与互动资源的关联（规范 3.13）
   */
  linkToPage: ({ generation_id, page_id, interactive_asset_id, label } = {}) =>
    requestJson(
      `/api/v1/generations/${encodeURIComponent(generation_id)}/pages/${encodeURIComponent(page_id)}/interactive-link`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          interactive_asset_id: interactive_asset_id || '',
          label: label || '开始互动练习'
        })
      }
    )
}
