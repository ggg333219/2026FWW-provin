import { defineStore } from 'pinia'

/**
 * S4 版本管理 Store
 *
 * 对应课件版本管理与发布模块的状态管理，包括：
 * - 版本列表与历史
 * - 修改指令(Diff)管理
 * - 发布状态
 */
export const useVersionStore = defineStore('version', {
  state: () => ({
    /** 版本列表 */
    versions: [],
    // versions[i] 结构参考：
    // {
    //   id: string,
    //   courseId: string,
    //   version: number,         // 版本号
    //   title: string,           // 版本标题
    //   description: string,     // 版本说明
    //   changes: [],             // 修改指令列表
    //   createdBy: string,       // 创建者
    //   createdAt: string,       // ISO 时间
    //   published: boolean       // 是否已发布
    // }

    /** 当前版本 */
    currentVersion: null,

    /** 待处理的修改指令 */
    pendingChanges: [],
    // pendingChanges[i] 结构参考：
    // {
    //   id: string,
    //   type: 'update' | 'insert' | 'delete' | 'reorder',
    //   target: string,          // 修改目标（节点ID或页面）
    //   before: any,             // 修改前内容
    //   after: any,              // 修改后内容
    //   status: 'pending' | 'applied' | 'rejected',
    //   appliedAt: string
    // }

    /** 发布状态 */
    publishState: {
      isPublishing: false,
      lastPublishedAt: null,
      publishScope: 'all',
      publishTarget: '',
      publishSuccess: null
    },

    loading: false,
    error: ''
  }),

  getters: {
    versionCount: (state) => state.versions.length,
    hasPendingChanges: (state) => state.pendingChanges.some(c => c.status === 'pending'),
    publishedVersions: (state) => state.versions.filter(v => v.published)
  },

  actions: {
    setVersions(versions) {
      this.versions = versions
    },

    addVersion(version) {
      this.versions.unshift(version)
    },

    setCurrentVersion(version) {
      this.currentVersion = version
    },

    addChange(change) {
      this.pendingChanges.push({
        id: change.id || `change_${Date.now()}`,
        type: change.type,
        target: change.target,
        before: change.before,
        after: change.after,
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

    rejectChange(changeId) {
      const change = this.pendingChanges.find(c => c.id === changeId)
      if (change) {
        change.status = 'rejected'
      }
    },

    clearPending() {
      this.pendingChanges = []
    },

    setPublishing(publishing) {
      this.publishState.isPublishing = publishing
    },

    setPublishSuccess(info) {
      this.publishState.lastPublishedAt = new Date().toISOString()
      this.publishState.publishSuccess = info
    },

    reset() {
      this.versions = []
      this.currentVersion = null
      this.pendingChanges = []
      this.error = ''
    }
  }
})
