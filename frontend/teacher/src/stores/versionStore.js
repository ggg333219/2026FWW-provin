import { defineStore } from 'pinia'
import { teacherV1Api } from '../services/v1'

/**
 * S4 版本管理 + 导出 Store
 */
export const useVersionStore = defineStore('version', {
  state: () => ({
    /** 版本列表 */
    versions: [],
    /** 当前加载的版本详情（含 nodes_snapshot） */
    currentVersionDetail: null,
    /** 当前 generation_id */
    genId: '',
    /** 修改指令列表 */
    pendingChanges: [],
    /** 发布/锁定状态 */
    publishState: {
      isPublishing: false,
      lastPublishedAt: null
    },

    // ---- 导出 ----
    /** 导出任务 ID */
    exportJobId: '',
    /** 导出状态: idle | pending | exporting | done | failed */
    exportStatus: 'idle',
    /** 导出格式 */
    exportFormat: 'pptx',
    /** 导出下载地址 */
    exportDownloadUrl: '',
    /** 导出错误 */
    exportError: '',

    loading: false,
    error: ''
  }),

  getters: {
    versionCount: (state) => state.versions.length,
    hasPendingChanges: (state) => state.pendingChanges.some(c => c.status === 'pending'),
    latestVersion: (state) => state.versions.length > 0 ? state.versions[0] : null,
    isExportDone: (state) => state.exportStatus === 'done',
    exportIsActive: (state) => ['pending', 'exporting'].includes(state.exportStatus)
  },

  actions: {
    // ================================================================
    // 版本历史
    // ================================================================
    async loadVersions(genId) {
      if (!genId) return
      this.genId = genId
      this.loading = true
      this.error = ''
      try {
        const data = await teacherV1Api.version.history(genId)
        this.versions = (data?.versions || []).map(v => ({
          id: v.id,
          version: v.version_number,
          title: v.summary || `版本 ${v.version_number}`,
          summary: v.summary || '',
          locked: v.locked || false,
          createdAt: v.created_at || '',
          createdBy: ''
        }))
      } catch (err) {
        this.error = err.message || '加载版本历史失败'
        console.warn('[versionStore] 加载版本失败', err)
      } finally {
        this.loading = false
      }
    },

    async loadVersion(genId, versionNumber = null) {
      if (!genId) return
      this.loading = true
      try {
        const data = await teacherV1Api.version.load(genId, versionNumber)
        this.currentVersionDetail = {
          version: data.version_number,
          id: data.id,
          nodes: data.nodes_snapshot || [],
          summary: data.summary || '',
          locked: data.locked || false,
          createdAt: data.created_at || ''
        }
      } catch (err) {
        console.warn('[versionStore] 加载版本详情失败', err)
        this.currentVersionDetail = null
      } finally {
        this.loading = false
      }
    },

    // ================================================================
    // 回滚
    // ================================================================
    async rollbackTo(genId, targetVersion) {
      if (!genId) return
      this.loading = true
      this.error = ''
      try {
        const result = await teacherV1Api.version.rollback(genId, targetVersion)
        // 回滚后刷新列表
        await this.loadVersions(genId)
        return result
      } catch (err) {
        this.error = err.message || '回滚失败'
        throw err
      } finally {
        this.loading = false
      }
    },

    // ================================================================
    // 锁定
    // ================================================================
    async lockVersion(genId) {
      if (!genId) return
      this.loading = true
      this.error = ''
      try {
        const result = await teacherV1Api.version.lock(genId)
        await this.loadVersions(genId)
        return result
      } catch (err) {
        this.error = err.message || '锁定失败'
        throw err
      } finally {
        this.loading = false
      }
    },

    // ================================================================
    // 修改指令
    // ================================================================
    addChange(change) {
      this.pendingChanges.push({
        id: change.id || `change_${Date.now()}`,
        type: change.type || 'update_node',
        target: change.target || '',
        before: change.before || null,
        after: change.after || null,
        status: 'pending',
        appliedAt: null
      })
    },

    applyChange(changeId) {
      const change = this.pendingChanges.find(c => c.id === changeId)
      if (change) {
        change.status = 'applied'
        change.appliedAt = new Date().toISOString()
      }
    },

    /** 提交所有 pending 修改到后端 */
    async submitModify(genId) {
      if (!genId || !this.currentVersionDetail?.nodes) {
        this.error = '无可用节点，无法提交修改'
        return
      }
      const pending = this.pendingChanges.filter(c => c.status === 'pending')
      if (!pending.length) {
        this.error = '无待处理的修改指令'
        return
      }
      this.loading = true
      this.error = ''
      try {
        // 构建后端 ModifyRequest 格式
        const nodes = this.currentVersionDetail.nodes.map(n => ({
          node_id: n.node_id,
          title: n.title || '',
          content: n.content || '',
          summary: n.summary || '',
          node_type: n.node_type || 'slide'
        }))
        const commands = pending.map(c => ({
          type: c.type,
          node_id: c.target,
          content: c.after || ''
        }))
        await teacherV1Api.version.modify(nodes, commands)
        // 全部标记为已应用
        pending.forEach(c => {
          c.status = 'applied'
          c.appliedAt = new Date().toISOString()
        })
        // 刷新版本列表
        await this.loadVersions(genId)
      } catch (err) {
        this.error = err.message || '修改提交失败'
        throw err
      } finally {
        this.loading = false
      }
    },

    rejectChange(changeId) {
      const change = this.pendingChanges.find(c => c.id === changeId)
      if (change) {
        change.status = 'rejected'
      }
    },

    clearPending() {
      this.pendingChanges = []
    },

    // ================================================================
    // 导出
    // ================================================================
    async startExport(genId, format = 'pptx') {
      if (!genId) return
      this.exportStatus = 'pending'
      this.exportFormat = format
      this.exportError = ''
      try {
        const result = await teacherV1Api.version.exportCreate(genId, format)
        this.exportJobId = result.job_id || ''
        this.exportStatus = result.status === 'done' ? 'done' : 'pending'
        this.exportDownloadUrl = result.download_url || ''
        // 如果不是立即完成，启动轮询
        if (this.exportStatus !== 'done' && this.exportJobId) {
          this._pollExport()
        }
      } catch (err) {
        this.exportStatus = 'failed'
        this.exportError = err.message || '导出任务创建失败'
      }
    },

    async _pollExport() {
      const maxPolls = 30  // 最多轮询 30 次（约 60 秒）
      let polls = 0
      const poll = async () => {
        if (polls >= maxPolls || !this.exportJobId) {
          if (this.exportStatus === 'pending') {
            this.exportStatus = 'failed'
            this.exportError = '导出超时'
          }
          return
        }
        polls++
        try {
          const result = await teacherV1Api.version.exportStatus(this.exportJobId)
          this.exportStatus = result.status || 'pending'
          this.exportDownloadUrl = result.download_url || ''
          this.exportError = result.error || ''
          if (this.exportStatus === 'done' || this.exportStatus === 'failed') {
            return
          }
          // 继续轮询
          setTimeout(poll, 2000)
        } catch (err) {
          if (polls >= maxPolls) {
            this.exportStatus = 'failed'
            this.exportError = err.message || '导出状态查询失败'
          } else {
            setTimeout(poll, 2000)
          }
        }
      }
      poll()
    },

    resetExport() {
      this.exportJobId = ''
      this.exportStatus = 'idle'
      this.exportFormat = 'pptx'
      this.exportDownloadUrl = ''
      this.exportError = ''
    },

    // ================================================================
    // 清理
    // ================================================================
    reset() {
      this.versions = []
      this.currentVersionDetail = null
      this.genId = ''
      this.pendingChanges = []
      this.error = ''
      this.resetExport()
    }
  }
})
