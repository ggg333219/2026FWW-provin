import { defineStore } from 'pinia'
import { teacherV1Api } from '../services/v1'

/**
 * S3 互动资源状态管理 — Interactive Store
 *
 * 对应规范：
 *   2.7 InteractiveAsset
 *   3.11 POST /api/v1/generations/{gen_id}/nodes/{node_id}/interactive
 *   3.12 GET /api/v1/interactive/assets/{asset_id}
 *   3.13 POST /api/v1/generations/{gen_id}/pages/{page_id}/interactive-link
 */

/** 资源状态轮询 */
const POLL_INTERVAL_MS = 1500
const MAX_POLL_ATTEMPTS = 80

export const useInteractiveStore = defineStore('interactive', {
  state: () => ({
    /** 当前 generation 上下文 */
    generation_id: '',
    /** 已生成的资源映射：node_id → asset */
    assets: {}, // { [node_id]: InteractiveAsset }

    /** 当前轮询状态 */
    pollingTaskId: null,
    pollingAttempts: 0,

    /** 全局加载/错误状态 */
    loading: false,
    error: ''
  }),

  getters: {
    /** 获取某节点的互动资源 */
    getAsset: (state) => (nodeId) => state.assets[nodeId] || null,

    /** 是否存在某节点的有效资源 */
    hasAsset: (state) => (nodeId) => {
      const a = state.assets[nodeId]
      return a && a.status === 'done'
    },

    /** 获取所有已完成的资源列表 */
    doneAssets: (state) =>
      Object.values(state.assets).filter((a) => a.status === 'done')
  },

  actions: {
    setGenerationId(genId) {
      this.generation_id = String(genId || '')
    },

    /**
     * 生成互动资源（对应规范 3.11）
     */
    async generateInteractive({ generation_id, node_id, node, interactive_plan }) {
      const genId = generation_id || this.generation_id
      if (!genId || !node_id) return
      this.loading = true
      this.error = ''
      try {
        const resp = await teacherV1Api.interactive.generate({
          generation_id: genId,
          node_id,
          node,
          interactive_plan
        })
        const data = resp?.data || resp || {}
        const asset = {
          interactive_asset_id: data.interactive_asset_id || '',
          generation_id: genId,
          node_id,
          asset_type: data.asset_type || 'html5',
          status: data.status || 'processing',
          file_url: data.file_url || '',
          entry_url: data.entry_url || '',
          file_size: data.file_size || 0,
          items: Array.isArray(data.items) ? data.items : [],
          error: data.error || null
        }
        this.assets[node_id] = asset
        return asset
      } catch (err) {
        this.error = err?.message || '生成互动资源失败'
        throw err
      } finally {
        this.loading = false
      }
    },

    /**
     * 轮询资源状态直到完成或失败（规范 3.12）
     */
    async pollAssetStatus(nodeId, { intervalMs = POLL_INTERVAL_MS, maxAttempts = MAX_POLL_ATTEMPTS } = {}) {
      if (!nodeId) return
      const asset = this.assets[nodeId]
      if (!asset?.interactive_asset_id) return

      this.pollingTaskId = nodeId
      this.pollingAttempts = 0

      for (let i = 0; i < maxAttempts; i++) {
        if (this.pollingTaskId !== nodeId) return // 被取消
        this.pollingAttempts = i + 1

        try {
          const resp = await teacherV1Api.interactive.getAsset(asset.interactive_asset_id)
          const data = resp?.data || resp || {}
          this.assets[nodeId] = {
            ...this.assets[nodeId],
            status: data.status || this.assets[nodeId].status,
            file_url: data.file_url || this.assets[nodeId].file_url,
            entry_url: data.entry_url || this.assets[nodeId].entry_url,
            file_size: data.file_size || this.assets[nodeId].file_size,
            items: Array.isArray(data.items) ? data.items : (this.assets[nodeId].items || []),
            error: data.error || null
          }
          if (data.status === 'done' || data.status === 'failed') {
            this.pollingTaskId = null
            return this.assets[nodeId]
          }
        } catch (err) {
          console.warn(`[interactiveStore] 轮询资源状态失败（尝试 ${i + 1}）:`, err)
        }

        await new Promise((resolve) => setTimeout(resolve, intervalMs))
      }

      this.pollingTaskId = null
      this.assets[nodeId] = {
        ...this.assets[nodeId],
        status: 'failed',
        error: '轮询超时'
      }
      return this.assets[nodeId]
    },

    /** 取消轮询 */
    cancelPolling() {
      this.pollingTaskId = null
    },

    /**
     * 建立页面与互动资源的关联（规范 3.13）
     */
    async linkToPage({ generation_id, page_id, interactive_asset_id, label }) {
      const genId = generation_id || this.generation_id
      try {
        const resp = await teacherV1Api.interactive.linkToPage({
          generation_id: genId,
          page_id,
          interactive_asset_id,
          label
        })
        return resp?.data || resp || {}
      } catch (err) {
        this.error = err?.message || '关联互动资源失败'
        throw err
      }
    },

    /** 清理 */
    reset() {
      this.generation_id = ''
      this.assets = {}
      this.pollingTaskId = null
      this.pollingAttempts = 0
      this.loading = false
      this.error = ''
    }
  }
})
