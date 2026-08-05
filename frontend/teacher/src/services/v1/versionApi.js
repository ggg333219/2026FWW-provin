import { requestJson } from './request'

/**
 * S4 版本管理 API — 对接 Python 后端 /api/v1/version/{gen_id}/...
 */
export const teacherVersionApi = {
  /**
   * 版本历史列表
   * GET /api/v1/version/{genId}/history
   */
  history: (genId) =>
    requestJson(`/api/v1/version/${encodeURIComponent(genId)}/history`),

  /**
   * 加载指定版本
   * GET /api/v1/version/{genId}?v={versionNumber}
   */
  load: (genId, versionNumber = null) => {
    const query = versionNumber != null ? `?v=${versionNumber}` : ''
    return requestJson(`/api/v1/version/${encodeURIComponent(genId)}${query}`)
  },

  /**
   * 对比两个版本
   * GET /api/v1/version/{genId}/diff?v1=1&v2=2
   */
  diff: (genId, v1, v2) =>
    requestJson(`/api/v1/version/${encodeURIComponent(genId)}/diff?v1=${v1}&v2=${v2}`),

  /**
   * 回滚到指定版本
   * POST /api/v1/version/{genId}/rollback
   */
  rollback: (genId, targetVersion) =>
    requestJson(`/api/v1/version/${encodeURIComponent(genId)}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_version: targetVersion })
    }),

  /**
   * 锁定当前版本
   * POST /api/v1/version/{genId}/lock
   */
  lock: (genId) =>
    requestJson(`/api/v1/version/${encodeURIComponent(genId)}/lock`, {
      method: 'POST'
    }),

  /**
   * 创建导出任务
   * POST /api/v1/export/{genId}
   */
  exportCreate: (genId, format = 'pptx', version = null) =>
    requestJson(`/api/v1/export/${encodeURIComponent(genId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        format,
        version: version || null
      })
    }),

  /**
   * 查询导出任务状态
   * GET /api/v1/export/status/{jobId}
   */
  exportStatus: (jobId) =>
    requestJson(`/api/v1/export/status/${encodeURIComponent(jobId)}`),

  /**
   * 提交修改命令
   * POST /gen/modify
   * @param {Array} nodes - 当前节点列表
   * @param {Array} commands - 修改命令列表 [{type, node_id, content, ...}]
   */
  modify: (nodes, commands) =>
    requestJson('/gen/modify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodes, commands, regenerate: false })
    })
}
