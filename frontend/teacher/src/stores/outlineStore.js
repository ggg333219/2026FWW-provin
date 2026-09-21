import { defineStore } from 'pinia'
import { teacherV1Api } from '../services/v1'

/**
 * S3 大纲状态管理 — Outline Store
 *
 * 对应 S3 数据规范第1章 ID 体系：
 *   session_id → intent_id → outline_id + outline_version
 *
 * 大纲状态机（规范 2.3）：
 *   draft → confirming → confirmed → superseded
 *
 * 核心职责：
 *   - 大纲节点 CRUD（大纲可视化编辑器）
 *   - AI 修订（revise → 待确认 → apply/放弃）
 *   - 大纲确认（confirm → 进入内容生成）
 *   - 大纲持久化（localStorage 刷新恢复）
 */

function makeNodeId() {
  return `node_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
}

/**
 * 归一 node_type 到前端大纲编辑器的枚举（content/section/quiz/interactive/summary）。
 * 引擎侧（Python normalize_stage2_nodes）产出 slide/cover/divider 等渲染枚举，
 * 编辑器 <select> 无这些选项会显示空白，故在此收敛。
 */
function normalizeOutlineNodeType(raw) {
  const v = String(raw || '').trim()
  switch (v) {
    case 'content':
    case 'section':
    case 'quiz':
    case 'interactive':
    case 'summary':
      return v
    case 'slide':
    case 'cover':
      return 'content'
    case 'divider':
      return 'section'
    default:
      return 'content'
  }
}

/** 前端内部大纲节点（前端编辑用，不含完整讲稿） */
function createOutlineNode(overrides = {}) {  return {
    node_id: makeNodeId(),
    order: 1,
    title: '',
    summary: '',
    node_type: 'content', // content | section | quiz | interactive | summary
    key_points: [],
    estimated_duration_minutes: 5,
    source_chunk_ids: [],
    interactive_plan: null,
    ...overrides
  }
}

/** localStorage key */
const STORAGE_KEY = 'fuww_outline_cache'

export const useOutlineStore = defineStore('outline', {
  state: () => ({
    /** 当前大纲 */
    outline_id: '',
    outline_version: 0,
    status: 'draft', // draft | confirming | confirmed | superseded
    title: '',
    confirmed_at: null,

    /** 节点树 */
    nodes: [],

    /** 所属上下文 */
    session_id: '',
    intent_id: '',

    /** AI 修订待确认状态 */
    reviseLoading: false,
    reviseError: '',
    pendingRevision: null, // { outline_version, nodes, change_summary }

    /** 加载状态 */
    loading: false,
    error: '',

    /** 确认校验错误 */
    confirmError: ''
  }),

  getters: {
    /** 是否可以编辑大纲（仅草稿状态可编辑） */
    canEdit: (state) => state.status === 'draft' || state.status === 'confirming',

    /**
     * 节点顺序在已确认后仍允许调整。
     * S3 的“已确认”代表内容可以开始生成，不应把教师的排序操作一并锁死。
     */
    canReorder: (state) => ['draft', 'confirming', 'confirmed'].includes(state.status),

    /** 是否已确认（可进入内容生成） */
    isConfirmed: (state) => state.status === 'confirmed',

    /** 总课时（分钟） */
    totalDuration: (state) =>
      state.nodes.reduce((sum, n) => sum + Number(n.estimated_duration_minutes || 0), 0),

    /** 节点数 */
    nodeCount: (state) => state.nodes.length,

    /** 是否有互动节点 */
    hasInteractive: (state) =>
      state.nodes.some((n) => n.node_type === 'interactive' || n.interactive_plan?.enabled),

    /** 获取指定节点 */
    getNode: (state) => (nodeId) => state.nodes.find((n) => n.node_id === nodeId),

    /** 变更摘要（供确认对话框显示） */
    changeSummary: (state) => {
      if (!state.pendingRevision?.change_summary) return []
      return Array.isArray(state.pendingRevision.change_summary)
        ? state.pendingRevision.change_summary
        : [state.pendingRevision.change_summary]
    }
  },

  actions: {
    // ------------------------------------------------------------------
    // 大纲创建 / 加载
    // ------------------------------------------------------------------

    /**
     * 创建新大纲（调用 AI 生成初始节点树）
     * 对应规范 3.1 POST /api/v1/outlines
     */
    async createOutline({ session_id, intent_id, intent, evidence_packet, markdown }) {
      this.loading = true
      this.error = ''
      try {
        const resp = await teacherV1Api.outline.create({
          session_id,
          intent_id,
          intent,
          evidence_packet,
          markdown
        })
        const data = resp?.data || resp || {}
        this._applyOutlineData(data)
        this._persist()
        return data
      } catch (err) {
        this.error = err?.message || '创建大纲失败'
        throw err
      } finally {
        this.loading = false
      }
    },

    /**
     * 加载已有大纲（从后端拉取）
     * 对应规范 3.2 GET /api/v1/outlines/{id}
     */
    async loadOutline(outlineId, { version } = {}) {
      this.loading = true
      this.error = ''
      try {
        const resp = await teacherV1Api.outline.get(outlineId, { version })
        const data = resp?.data || resp || {}
        this._applyOutlineData(data)
        return data
      } catch (err) {
        this.error = err?.message || '加载大纲失败'
        throw err
      } finally {
        this.loading = false
      }
    },

    /**
     * 从 localStorage 恢复最近的大纲（刷新恢复）
     */
    restore() {
      try {
        const raw = window.localStorage.getItem(STORAGE_KEY)
        if (!raw) return false
        const cache = JSON.parse(raw)
        if (!cache?.outline_id) return false
        this.outline_id = cache.outline_id
        this.outline_version = cache.outline_version || 0
        this.status = cache.status || 'draft'
        this.title = cache.title || ''
        this.confirmed_at = cache.confirmed_at || null
        this.nodes = Array.isArray(cache.nodes) ? cache.nodes : []
        this.session_id = cache.session_id || ''
        this.intent_id = cache.intent_id || ''
        return true
      } catch {
        return false
      }
    },

    // ------------------------------------------------------------------
    // 节点编辑（仅 draft 状态可调用）
    // ------------------------------------------------------------------

    /** 添加节点（追加到末尾） */
    addNode(afterNodeId = null) {
      if (!this.canEdit) return null
      const newNode = createOutlineNode({
        order: afterNodeId ? this._nextOrderAfter(afterNodeId) : this.nodes.length + 1
      })
      if (afterNodeId) {
        const idx = this.nodes.findIndex((n) => n.node_id === afterNodeId)
        if (idx >= 0) {
          this.nodes.splice(idx + 1, 0, newNode)
          this._reorder()
        } else {
          this.nodes.push(newNode)
        }
      } else {
        this.nodes.push(newNode)
      }
      this._persist()
      return newNode
    },

    /** 删除节点 */
    removeNode(nodeId) {
      if (!this.canEdit) return
      this.nodes = this.nodes.filter((n) => n.node_id !== nodeId)
      this._reorder()
      this._persist()
    },

    /** 更新节点字段 */
    updateNode(nodeId, patch) {
      if (!this.canEdit) return
      const idx = this.nodes.findIndex((n) => n.node_id === nodeId)
      if (idx < 0) return
      // 禁止覆盖 node_id 和 order
      const { node_id: _nid, order: _ord, ...safe } = patch
      this.nodes[idx] = { ...this.nodes[idx], ...safe }
      this._persist()
    },

    /** 交换两个节点的顺序（真换数组位置，再重排 order） */
    swapNodes(nodeIdA, nodeIdB) {
      if (!this.canReorder) return
      const idxA = this.nodes.findIndex((n) => n.node_id === nodeIdA)
      const idxB = this.nodes.findIndex((n) => n.node_id === nodeIdB)
      if (idxA < 0 || idxB < 0 || idxA === idxB) return
      // 交换数组元素位置（此前只换 order 字段值，随即被 _reorder() 抹掉，导致排序无效）
      const tmp = this.nodes[idxA]
      this.nodes[idxA] = this.nodes[idxB]
      this.nodes[idxB] = tmp
      this._reorder()
      this._persist()
    },

    /** 向上/下移动节点 */
    moveNode(nodeId, direction) {
      const idx = this.nodes.findIndex((n) => n.node_id === nodeId)
      if (idx < 0) return
      const newIdx = direction === 'up' ? idx - 1 : idx + 1
      if (newIdx < 0 || newIdx >= this.nodes.length) return
      this.swapNodes(this.nodes[idx].node_id, this.nodes[newIdx].node_id)
    },

    /** 拖拽到指定位置，保持数组顺序与 order 字段一致 */
    moveNodeToIndex(nodeId, targetIndex) {
      if (!this.canReorder) return
      const sourceIndex = this.nodes.findIndex((n) => n.node_id === nodeId)
      const boundedTarget = Math.max(0, Math.min(Number(targetIndex), this.nodes.length - 1))
      if (sourceIndex < 0 || sourceIndex === boundedTarget) return
      const [node] = this.nodes.splice(sourceIndex, 1)
      this.nodes.splice(boundedTarget, 0, node)
      this._reorder()
      this._persist()
    },

    // ------------------------------------------------------------------
    // 保存 & AI 修订
    // ------------------------------------------------------------------

    /**
     * 保存大纲版本（手动编辑后持久化）
     * 对应规范 3.4 PUT /api/v1/outlines/{id}
     *
     * 后端校验：base_version 必须等于当前版本（409冲突检测）
     */
    async saveVersion() {
      if (!this.outline_id) return
      this.loading = true
      this.error = ''
      try {
        const resp = await teacherV1Api.outline.save(this.outline_id, {
          base_version: this.outline_version,
          nodes: this.nodes
        })
        const data = resp?.data || resp || {}
        this.outline_version = data.outline_version || this.outline_version + 1
        this._persist()
        return data
      } catch (err) {
        // 409 版本冲突
        if (err?.code === 409 || err?.status === 409) {
          this.error = '大纲版本冲突，请刷新后重试'
        } else {
          this.error = err?.message || '保存大纲失败'
        }
        throw err
      } finally {
        this.loading = false
      }
    },

    /**
     * AI 修改大纲（发送自然语言指令）
     * 对应规范 3.3 POST /api/v1/outlines/{id}/revise
     *
     * auto_apply=false（默认）：返回待确认修订结果
     */
    async reviseOutline(message) {
      if (!this.outline_id) return
      this.reviseLoading = true
      this.reviseError = ''
      this.pendingRevision = null
      try {
        const resp = await teacherV1Api.outline.revise(this.outline_id, {
          message,
          base_version: this.outline_version,
          auto_apply: false
        })
        const data = resp?.data || resp || {}
        this.pendingRevision = {
          outline_version: data.outline_version || this.outline_version + 1,
          nodes: data.nodes || [],
          change_summary: data.change_summary || []
        }
        return data
      } catch (err) {
        this.reviseError = err?.message || 'AI 修订失败'
        throw err
      } finally {
        this.reviseLoading = false
      }
    },

    /** 接受 AI 修订结果（写入当前节点） */
    applyRevision() {
      if (!this.pendingRevision) return
      this.nodes = this.pendingRevision.nodes.map((n) => ({
        ...n,
        node_id: n.node_id || makeNodeId(),
        node_type: normalizeOutlineNodeType(n.node_type),
        key_points: Array.isArray(n.key_points) ? n.key_points : [],
        estimated_duration_minutes: Number(n.estimated_duration_minutes) || 5,
        source_chunk_ids: Array.isArray(n.source_chunk_ids) ? n.source_chunk_ids : [],
        interactive_plan: n.interactive_plan || null
      }))
      this.outline_version = this.pendingRevision.outline_version
      this.pendingRevision = null
      this._reorder()
      this._persist()
    },

    /** 放弃 AI 修订结果 */
    discardRevision() {
      this.pendingRevision = null
    },

    // ------------------------------------------------------------------
    // 大纲确认
    // ------------------------------------------------------------------

    /**
     * 确认大纲（校验 → confirmed → 可进入内容生成）
     * 对应规范 3.5 POST /api/v1/outlines/{id}/confirm
     *
     * 前端预校验：
     *   - 节点数量 > 0
     *   - node_id 不重复
     *   - order 连续不重复
     *   - title / summary 非空
     *   - estimated_duration_minutes > 0
     */
    validateForConfirm() {
      const errors = []
      if (this.nodes.length === 0) errors.push('节点数量为 0')
      const nodeIds = this.nodes.map((n) => n.node_id)
      if (new Set(nodeIds).size !== nodeIds.length) errors.push('node_id 重复')
      const orders = this.nodes.map((n) => n.order)
      if (new Set(orders).size !== orders.length) errors.push('order 重复')
      const missingTitle = this.nodes.some((n) => !n.title?.trim())
      if (missingTitle) errors.push('存在空标题节点')
      const missingSummary = this.nodes.some((n) => !n.summary?.trim())
      if (missingSummary) errors.push('存在空摘要节点')
      const invalidDuration = this.nodes.some((n) => Number(n.estimated_duration_minutes) <= 0)
      if (invalidDuration) errors.push('存在时长 ≤ 0 的节点')
      return errors
    },

    async confirmOutline() {
      const errors = this.validateForConfirm()
      if (errors.length > 0) {
        this.confirmError = errors.join('；')
        throw new Error(this.confirmError)
      }
      this.loading = true
      this.confirmError = ''
      try {
        const resp = await teacherV1Api.outline.confirm(this.outline_id, {
          outline_version: this.outline_version
        })
        const data = resp?.data || resp || {}
        this.status = data.status || 'confirmed'
        this.confirmed_at = data.confirmed_at || new Date().toISOString()
        this._persist()
        return data
      } catch (err) {
        this.confirmError = err?.message || '确认大纲失败'
        throw err
      } finally {
        this.loading = false
      }
    },

    // ------------------------------------------------------------------
    // 内部工具
    // ------------------------------------------------------------------

    /** 将后端返回数据写入 state（_applyOutlineData） */
    _applyOutlineData(data) {
      this.outline_id = data.outline_id || ''
      this.outline_version = data.outline_version || data.outline_version || 0
      this.status = data.status || 'draft'
      this.title = data.title || ''
      this.confirmed_at = data.confirmed_at || null
      this.nodes = (data.nodes || []).map((n) => ({
        node_id: n.node_id || makeNodeId(),
        order: Number(n.order) || 1,
        title: n.title || '',
        summary: n.summary || '',
        // 兼容引擎枚举（slide/cover/divider）→ 大纲编辑器的前端枚举
        node_type: normalizeOutlineNodeType(n.node_type),
        key_points: Array.isArray(n.key_points) ? n.key_points : [],
        estimated_duration_minutes: Number(n.estimated_duration_minutes) || 5,
        source_chunk_ids: Array.isArray(n.source_chunk_ids) ? n.source_chunk_ids : [],
        interactive_plan: n.interactive_plan || null
      }))
      this.session_id = data.session_id || ''
      this.intent_id = data.intent_id || ''
    },

    /** 重新编号 order（1 开始连续） */
    _reorder() {
      this.nodes.forEach((n, i) => {
        n.order = i + 1
      })
    },

    /** 计算插入位置之后的 order */
    _nextOrderAfter(nodeId) {
      const idx = this.nodes.findIndex((n) => n.node_id === nodeId)
      if (idx < 0) return this.nodes.length + 1
      return (this.nodes[idx].order || idx + 1) + 0.5
    },

    /** 持久化到 localStorage */
    _persist() {
      try {
        window.localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            outline_id: this.outline_id,
            outline_version: this.outline_version,
            status: this.status,
            title: this.title,
            confirmed_at: this.confirmed_at,
            nodes: this.nodes,
            session_id: this.session_id,
            intent_id: this.intent_id
          })
        )
      } catch (e) {
        console.warn('[outlineStore] 持久化大纲失败', e)
      }
    },

    /** 清理状态 */
    reset() {
      this.outline_id = ''
      this.outline_version = 0
      this.status = 'draft'
      this.title = ''
      this.confirmed_at = null
      this.nodes = []
      this.session_id = ''
      this.intent_id = ''
      this.loading = false
      this.error = ''
      this.reviseLoading = false
      this.reviseError = ''
      this.pendingRevision = null
      this.confirmError = ''
      try {
        window.localStorage.removeItem(STORAGE_KEY)
      } catch {}
    }
  }
})
