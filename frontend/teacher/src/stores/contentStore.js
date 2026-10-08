import { defineStore } from 'pinia'
import { teacherV1Api } from '../services/v1'

/**
 * P1 内容生成状态管理 — Content Store
 *
 * 职责：
 *   - 管理 content generation 任务（outline → nodes content）
 *   - 提供 progress 轮询、modify、状态持久化
 *   - 将生成的 content 存入 outlineStore.nodes（内容合并）
 *
 * 状态机：idle → generating → done | error
 */

const STORAGE_KEY = 'fuww_content_cache'

export const useContentStore = defineStore('content', {
  state: () => ({
    /** 当前 content 任务 ID */
    content_id: '',

    /** 内容生成状态 */
    status: 'idle', // idle | pending | generating | done | error
    progress_pct: 0,
    current_node_id: '',
    total_nodes: 0,
    completed_nodes: 0,

    /** 节点讲稿内容 key=node_id, value={script, key_points, ...} */
    nodesContent: {},

    /** 轮询定时器 ID */
    pollTimer: null,

    /** 错误 */
    error: '',

    /** 是否正在修改 */
    modifying: false,
    modifyError: ''
  }),

  getters: {
    /** 是否正在生成中 */
    isGenerating: (state) => state.status === 'generating' || state.status === 'pending',

    /** 内容生成进度文字 */
    progressText: (state) => {
      if (state.status === 'idle') return '未开始'
      if (state.status === 'error') return state.error || '生成失败'
      if (state.total_nodes === 0) return '准备中...'
      return `正在生成第 ${state.completed_nodes + 1}/${state.total_nodes} 个节点`
    },

    /** 是否有内容 */
    hasContent: (state) => Object.keys(state.nodesContent).length > 0,

    /** 获取某个节点的内容 */
    getNodeContent: (state) => (nodeId) => state.nodesContent[nodeId] || null,

    /** 未完成的节点（用于展示待生成） */
    pendingNodes: (state) => (allNodes) => {
      if (!Array.isArray(allNodes)) return []
      return allNodes.filter(n => !state.nodesContent[n.node_id])
    }
  },

  actions: {
    // ------------------------------------------------------------------
    // 内容生成
    // ------------------------------------------------------------------

    /**
     * 启动内容生成（创建任务并开始轮询）
     * 对应后端 POST /api/v1/gen/content
     */
    async startGeneration({ nodes, context_markdown, course_name, mode, enhanced, outline_id, outline_version, generation_instruction_set }) {
      this.error = ''
      this.status = 'pending'
      this.progress_pct = 0
      this.completed_nodes = 0
      this.total_nodes = nodes?.length || 0
      this.current_node_id = ''

      try {
        const resp = await teacherV1Api.generation.generateContent({
          nodes: nodes || [],
          context_markdown: context_markdown || '',
          course_name: course_name || '课件',
          mode: mode || 'llm',
          enhanced: enhanced || false,
          outline_id: outline_id || '',
          outline_version: outline_version || 0,
          generation_instruction_set: generation_instruction_set || {},
        })

        const data = resp?.data || resp || {}
        const contentId = data.content_id
        if (!contentId) {
          throw new Error('未返回 content_id')
        }

        this.content_id = contentId
        this.status = 'generating'
        this._persist()

        // 开始轮询
        this._startPolling()
        return contentId
      } catch (err) {
        this.status = 'error'
        this.error = err?.message || '启动内容生成失败'
        this._persist()
        throw err
      }
    },

    /**
     * 轮询内容生成状态
     * 对应后端 GET /api/v1/gen/content/status/:content_id
     */
    async pollStatus() {
      if (!this.content_id) return null

      try {
        const resp = await teacherV1Api.generation.getContentStatus(this.content_id)
        const data = resp?.data || resp || {}

        // 更新状态
        this.status = data.status || this.status
        this.progress_pct = Number(data.progress_pct) || this.progress_pct
        this.current_node_id = data.current_node_id || ''
        this.total_nodes = data.total_nodes || this.total_nodes
        this.completed_nodes = data.completed_nodes || this.completed_nodes
        this.error = data.error || ''

        // 合并节点内容
        if (Array.isArray(data.nodes)) {
          for (const node of data.nodes) {
            if (node.node_id) {
              this.nodesContent[node.node_id] = node
            }
          }
        }

        this._persist()

        // 如果完成或失败，停止轮询
        if (this.status === 'done' || this.status === 'error') {
          this._stopPolling()
        }

        return data
      } catch (err) {
        this.error = err?.message || '查询内容状态失败'
        return null
      }
    },

    /**
     * AI 修改节点内容（自然语言指令）
     * 对应后端 POST /api/v1/gen/content/modify
     *
     * nodes 是必带的改写基础：引擎只重生成 target 节点，其余原样返回，
     * 所以这里回写的其实是「整棵树里被换掉的那一节」。
     */
    async modifyNode({ content_id, node_id, message, nodes = [], action = '',
      course_name = '', context_markdown = '', outline_id = '', outline_version = 0,
      intent = undefined } = {}) {
      this.modifying = true
      this.modifyError = ''
      try {
        const resp = await teacherV1Api.generation.modifyContent({
          content_id: content_id || this.content_id,
          node_id,
          message,
          nodes,
          action,
          course_name,
          context_markdown,
          outline_id,
          outline_version,
          intent
        })
        const data = resp?.data || resp || {}
        const returned = Array.isArray(data.nodes) ? data.nodes : []

        if (returned.length) {
          for (const node of returned) {
            if (node.node_id) {
              this.nodesContent[node.node_id] = node
            }
          }
          this._persist()
        }

        return { ...data, nodes: returned }
      } catch (err) {
        this.modifyError = err?.message || '修改内容失败'
        throw err
      } finally {
        this.modifying = false
      }
    },

    /**
     * 手动编辑节点内容并落缓存。
     *
     * 与 modifyNode 的区别：这一条不经过大模型，教师改什么就是什么。
     * script 与 lecture_script 写同一份 —— 预览读前者、讲稿区读后者，
     * 只写一个会让「页面上改了、讲稿区没动」。
     */
    saveManualEdit({ node_id, summary, script, key_points } = {}) {
      if (!node_id) return null
      const current = this.nodesContent[node_id] || {}
      const next = { ...current, node_id }
      if (summary != null) next.summary = summary
      if (script != null) {
        next.script = script
        next.lecture_script = script
      }
      if (key_points != null) next.key_points = key_points
      this.nodesContent[node_id] = next
      this._persist()
      return next
    },

    /**
     * 将内容合并到 outlineStore 的节点中
     * 每个节点的讲稿内容写入 nodesContent，不影响节点结构
     */
    mergeContentToOutline(outlineNodes) {
      if (!Array.isArray(outlineNodes)) return outlineNodes
      return outlineNodes.map(n => {
        const content = this.nodesContent[n.node_id]
        if (content) {
          return {
            ...n,
            script: content.script || content.lecture_script || '',
            key_points: content.key_points || n.key_points || [],
            summary: content.summary || n.summary || ''
          }
        }
        return n
      })
    },

    // ------------------------------------------------------------------
    // 轮询控制
    // ------------------------------------------------------------------

    /** 开始轮询（每 800ms） */
    _startPolling() {
      this._stopPolling()
      this.pollTimer = setInterval(() => {
        this.pollStatus()
      }, 800)
    },

    /** 停止轮询 */
    _stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer)
        this.pollTimer = null
      }
    },

    // ------------------------------------------------------------------
    // 持久化 & 恢复
    // ------------------------------------------------------------------

    /** 持久化到 localStorage */
    _persist() {
      try {
        window.localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            content_id: this.content_id,
            status: this.status,
            progress_pct: this.progress_pct,
            current_node_id: this.current_node_id,
            total_nodes: this.total_nodes,
            completed_nodes: this.completed_nodes,
            nodesContent: this.nodesContent,
            error: this.error
          })
        )
      } catch (e) {
        console.warn('[contentStore] 持久化内容状态失败', e)
      }
    },

    /** 从 localStorage 恢复 */
    restore() {
      try {
        const raw = window.localStorage.getItem(STORAGE_KEY)
        if (!raw) return false
        const cache = JSON.parse(raw)
        if (!cache?.content_id) return false

        this.content_id = cache.content_id || ''
        this.status = cache.status || 'idle'
        this.progress_pct = Number(cache.progress_pct) || 0
        this.current_node_id = cache.current_node_id || ''
        this.total_nodes = cache.total_nodes || 0
        this.completed_nodes = cache.completed_nodes || 0
        this.nodesContent = cache.nodesContent || {}
        this.error = cache.error || ''

        // 如果之前未完成，恢复轮询
        if (this.status === 'generating' || this.status === 'pending') {
          this.status = 'generating'
          this._startPolling()
        }

        return true
      } catch {
        return false
      }
    },

    // ------------------------------------------------------------------
    // 清理
    // ------------------------------------------------------------------

    /** 重置状态 */
    reset() {
      this._stopPolling()
      this.content_id = ''
      this.status = 'idle'
      this.progress_pct = 0
      this.current_node_id = ''
      this.total_nodes = 0
      this.completed_nodes = 0
      this.nodesContent = {}
      this.error = ''
      this.modifying = false
      this.modifyError = ''

      try {
        window.localStorage.removeItem(STORAGE_KEY)
      } catch {}
    }
  }
})
