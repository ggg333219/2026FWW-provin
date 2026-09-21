import { requestJson } from './request'

/**
 * 课件项目修改对话 API — 对接 Go 后端 /api/v1/coursewares/*（A6/A7 新增）
 *
 * 注意：与 coursewareApi.js（旧版教师素材接口 /teacher/coursewares）是不同的资源——
 * 这里是"课件项目"（courseware_projects），服务于 AI 对话式修改与版本快照。
 *
 * 接口契约：
 *   POST   /coursewares                   新建项目（A1）
 *   GET    /coursewares                    我的课件列表（A1）
 *   PUT    /coursewares/:id/step           持久化步骤（A3）
 *   PUT    /coursewares/:id/draft          保存草稿（A2）
 *   GET    /coursewares/:id/draft          读取草稿（A2）
 *   POST   /coursewares/:id/modify         修改编排（A6：意图解析→局部生成→快照）
 *   GET    /coursewares/:id/modify-history 修改记录（A6）
 *   GET    /coursewares/:id/versions       版本列表（A7）
 *   POST   /coursewares/:id/versions       保存完整版本快照（模块3）
 *   GET    /coursewares/:id/versions/:vid  读取单版本快照（模块3）
 *   POST   /coursewares/:id/rollback       回滚（A7，克隆式）
 */
const MODIFY_LLM_TIMEOUT_MS = 120000 // 修改编排含 LLM 意图解析 + 局部生成，给 2 分钟

export const projectModifyApi = {
  /** 新建课件项目 */
  create: ({ owner_id, title } = {}) =>
    requestJson('/api/v1/coursewares', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner_id: owner_id || 'teacher_demo', title: title || '' }),
    }),

  /** 我的课件列表 */
  list: () =>
    requestJson('/api/v1/coursewares', {
      method: 'GET',
    }),

  /** 删除课件项目 */
  remove: (project_id) =>
    requestJson(`/api/v1/coursewares/${encodeURIComponent(project_id)}`, {
      method: 'DELETE',
    }),

  /** 恢复项目的步骤、草稿和 generation_id。 */
  context: (project_id) =>
    requestJson(`/api/v1/coursewares/${encodeURIComponent(project_id)}/context`, {
      method: 'GET',
    }),

  /** 持久化当前步骤 */
  updateStep: (project_id, step) =>
    requestJson(`/api/v1/coursewares/${project_id}/step`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_step: step }),
    }),

  /** 保存草稿（draft_json 为 JSON 字符串） */
  saveDraft: (project_id, draft_json) =>
    requestJson(`/api/v1/coursewares/${project_id}/draft`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ draft_json }),
    }),

  /** 读取草稿 */
  getDraft: (project_id) =>
    requestJson(`/api/v1/coursewares/${project_id}/draft`, {
      method: 'GET',
    }),

  /**
   * A6 修改编排：自然语言 → 意图解析 → 局部重生成 → 版本快照
   * 响应 data: { modified_nodes, all_nodes, intent, previous_version_no, new_version_no, clarification? }
   */
  modify: (project_id, instruction, nodes) =>
    requestJson(`/api/v1/coursewares/${project_id}/modify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      timeoutMs: MODIFY_LLM_TIMEOUT_MS,
      body: JSON.stringify({ instruction, nodes }),
    }),

  /** 修改记录列表 */
  modifyHistory: (project_id) =>
    requestJson(`/api/v1/coursewares/${project_id}/modify-history`, {
      method: 'GET',
    }),

  /** 版本列表 */
  versions: (project_id) =>
    requestJson(`/api/v1/coursewares/${project_id}/versions`, {
      method: 'GET',
    }),

  /** 保存完整版本快照（节点、呈现样式和页面证据绑定）。 */
  createVersion: (project_id, payload = {}) =>
    requestJson(`/api/v1/coursewares/${encodeURIComponent(project_id)}/versions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  /** 读取指定版本的完整快照。 */
  versionDetail: (project_id, version_id) =>
    requestJson(`/api/v1/coursewares/${encodeURIComponent(project_id)}/versions/${encodeURIComponent(version_id)}`, {
      method: 'GET',
    }),

  /** A7 回滚（按 version_id 克隆，不覆盖历史）。 */
  rollback: (project_id, target_version_id) =>
    requestJson(`/api/v1/coursewares/${project_id}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_version_id }),
    }),
}
