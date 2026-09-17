import { requestJson } from './request'

/**
 * S3 大纲 API — 对接 Go 后端 /api/v1/outlines/*
 *
 * 接口规范：文档/S3数据与接口规范.md 第3章
 *
 * ID 体系：
 *   session_id → intent_id → outline_id + outline_version → generation_id
 *
 * 大纲状态机：
 *   draft → confirming → confirmed → superseded（确认后不得原地覆盖）
 */
export const teacherOutlineApi = {
  /**
   * POST /api/v1/outlines
   * 生成大纲（AI 生成大纲节点树，仅结构描述，不含完整讲稿）
   */
  create: ({ session_id, intent_id, intent, evidence_packet, markdown } = {}) =>
    requestJson('/api/v1/outlines', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // S2 -> S3 的初始大纲生成会调用真实大模型，不能使用通用 10 秒超时。
      timeoutMs: 120000,
      body: JSON.stringify({
        session_id: session_id || '',
        intent_id: intent_id || '',
        intent: intent || {},
        evidence_packet: evidence_packet || null,
        markdown: markdown || ''
      })
    }),

  /**
   * GET /api/v1/outlines/{outline_id}?version=N
   * 获取指定版本大纲，version 可选，缺省返回最新版本
   */
  get: (outlineId, { version } = {}) => {
    const query = version != null ? `?version=${version}` : ''
    return requestJson(`/api/v1/outlines/${encodeURIComponent(outlineId)}${query}`)
  },

  /**
   * PUT /api/v1/outlines/{outline_id}
   * 保存大纲版本（手动编辑节点后保存，base_version 不匹配返回 409）
   *
   * 校验规则（规范 3.4）：
   *   - base_version 必须等于当前版本
   *   - node_id 不得重复
   *   - order 必须从 1 连续编号
   *   - 必须保留原节点 node_id
   */
  save: (outlineId, { base_version, nodes } = {}) =>
    requestJson(`/api/v1/outlines/${encodeURIComponent(outlineId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_version,
        nodes: nodes || []
      })
    }),

  /**
   * POST /api/v1/outlines/{outline_id}/revise
   * AI 修改大纲（发送教师自然语言指令，返回待确认的修订结果）
   *
   * auto_apply=false 时返回待确认修改结果，不得直接进入正式生成
   * （规范 3.3）
   */
  revise: (outlineId, { message, base_version, auto_apply = false } = {}) =>
    requestJson(`/api/v1/outlines/${encodeURIComponent(outlineId)}/revise`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 真实大模型修订可能超过通用 10 秒请求超时。
      timeoutMs: 120000,
      body: JSON.stringify({
        message: message || '',
        base_version: base_version != null ? base_version : 1,
        auto_apply
      })
    }),

  /**
   * POST /api/v1/outlines/{outline_id}/confirm
   * 确认大纲（校验节点结构，校验通过后 status → confirmed）
   *
   * 校验规则（规范 3.5）：
   *   - 节点数量 > 0
   *   - node_id 不重复，order 连续不重复
   *   - title / summary 非空
   *   - estimated_duration_minutes > 0
   *   - interactive_plan 格式正确
   *   - 总时长符合教学意图约束
   */
  confirm: (outlineId, { outline_version } = {}) =>
    requestJson(`/api/v1/outlines/${encodeURIComponent(outlineId)}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        outline_version: outline_version != null ? outline_version : 1
      })
    })
}
