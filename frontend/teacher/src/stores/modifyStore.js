import { defineStore } from 'pinia'
import { projectModifyApi } from '../services/v1/projectModifyApi'

/**
 * AI 修改对话 Store（C6/C7）
 *
 * 职责：
 *  - 管理修改对话气泡（教师指令 / AI 解析结果 / 追问）
 *  - 调用 A6 modify 编排（意图解析 → 局部重生成 → 版本快照）
 *  - 版本标签（当前 vN · 基于 vN-1 修改）与撤销/重做（基于版本链）
 *  - 修改高亮节点集合（C7：局部刷新 + 高亮 2s 渐隐）
 *
 * 不重复管理节点数据本身——节点以 outlineStore 为准，
 * 修改成功后由调用方（S3StudioPage）把 all_nodes 写回 outlineStore。
 */

const STORAGE_KEY = 'fuww_modify_panel_state'

export const useModifyStore = defineStore('modifyPanel', {
  state: () => ({
    /** 当前课件项目 ID（S3 进入时设置；为空则面板禁用） */
    projectId: '',
    /** 对话气泡 [{ id, role: 'teacher'|'ai', text, intent?, versionNo? }] */
    messages: [],
    /** 输入框内容 */
    inputText: '',
    /** 修改执行中 */
    modifying: false,
    /** 最近一次修改返回的完整意图（供追问上下文） */
    lastIntent: null,
    /** 低置信度追问上下文；下一条教师回复会和原指令合并后再次解析。 */
    pendingClarification: null,
    /** 当前版本号（每次成功修改自增） */
    currentVersionNo: 0,
    /** 当前版本由哪个版本修改而来。 */
    basedOnVersionNo: 0,
    /** 版本历史 [{ version_no, modify_instruction, created_at }] */
    versionHistory: [],
    /** 本次修改的节点（C7 高亮用；2s 后清除） */
    recentlyModifiedIds: [],
    /** 撤销栈：可回滚的版本号 */
    undoStack: [],
    /** 重做栈 */
    redoStack: [],
    /** 错误提示 */
    error: '',
    /** 最近一次失败的教师输入，供一键重试。 */
    lastFailedInstruction: '',
    /** 后端 /latest-generation-context 拉来的当前项目所有页的证据绑定
     * （契约 v1.0 §3.2）：切 PPT / 新建课件进入 S3 时由 loadLatestContext 写入，
     * 证据侧栏直接读取，避免打开 PPT 后还要等"生成"才显示绑定关系。 */
    pageBindings: [],
    /** 自上次 _flushPendingMessages 以来新增的、待 upsert 到 courseware_ai_messages
     * 的对话气泡。在 sendModify / undo / redo / clarification 等业务动作末尾批量发送。*/
    _pendingPersist: [],
  }),

  getters: {
    canSend: (state) => !!state.projectId && !!state.inputText.trim() && state.inputText.length <= 500 && !state.modifying,
    canUndo: (state) => state.undoStack.length > 0,
    canRedo: (state) => state.redoStack.length > 0,
    /** 版本标签文案 */
    versionLabel: (state) => {
      if (state.currentVersionNo <= 0) return '尚未生成版本'
      return state.basedOnVersionNo > 0
        ? `当前 v${state.currentVersionNo} · 基于 v${state.basedOnVersionNo} 修改`
        : `当前 v${state.currentVersionNo}`
    },
    /** 快捷指令 chips（C6） */
    quickChips: () => [
      { label: '精简这页', text: '精简当前选中页面的内容，减少文字量' },
      { label: '增加案例', text: '为当前内容增加一个生活案例' },
      { label: '换个风格', text: '整体风格换成更简洁的商务风' },
      { label: '调整顺序', text: '把当前页面和下一页交换顺序' },
    ],
  },

  actions: {
    /**
     * 设置项目上下文（S3 进入时调用）
     *
     * 关键修复：无论 projectId 是否变化，都必须把"上一个课件"的对话气泡、
     * 待追问上下文等清空，避免切 PPT 时显示之前的 AI 对话残留。
     * 之前实现只在 !projectId 时清，导致 A→B 切换时 messages 保留了 A 的内容。
     *
     * 再按 projectId 从 localStorage 恢复该项目的最后状态（messages 等）。
     */
    bindProject(projectId) {
      const newId = projectId || ''
      const projectChanged = this.projectId !== newId
      this.projectId = newId
      // 1) projectId 变化或为空 → 必清空内存里的对话与版本栈
      if (projectChanged || !this.projectId) {
        this.messages = []
        this.inputText = ''
        this.lastIntent = null
        this.pendingClarification = null
        this.currentVersionNo = 0
        this.basedOnVersionNo = 0
        this.versionHistory = []
        this.recentlyModifiedIds = []
        this.undoStack = []
        this.redoStack = []
        this.error = ''
        this.lastFailedInstruction = ''
      }
      if (!this.projectId) {
        this._persist()
        return
      }
      // 2) localStorage 命中同项目 → 恢复该项目的最后状态
      try {
        const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || 'null')
        if (saved?.projectId === this.projectId) {
          this.messages = Array.isArray(saved.messages) ? saved.messages : []
          this.currentVersionNo = Number(saved.currentVersionNo || 0)
          this.basedOnVersionNo = Number(saved.basedOnVersionNo || 0)
          this.pendingClarification = saved.pendingClarification || null
        }
      } catch {
        // 本地缓存损坏不影响服务端版本链恢复。
      }
      this._persist()
    },

    /**
     * 按 projectId 拉后端 /latest-generation-context 作为权威读源
     * （契约 v1.0 §3.2），用响应重置本 store：对话气泡清空（后端不存对话历史）、
     * version_no / version_history 来自最新 CoursewareVersion、pageBindings 来自
     * 当前所有页的绑定。让"切 PPT 不重置 AI 对话"和"左侧资料绑定打开 PPT 不显示"
     * 这两类前端问题都有权威读源。
     *
     * @returns {Promise<{version_no:number, page_bindings:Array}|null>} 后端响应
     */
    async loadLatestContext(projectId) {
      const targetId = String(projectId || this.projectId || '')
      if (!targetId) return null
      // 先用 bindProject 把内存里的对话清掉，再发请求
      this.bindProject(targetId)
      // 并发拉权威读源（版本/绑定）与 AI 对话气泡；任一失败都不阻断对方降级。
      const [ctxResult, msgResult] = await Promise.allSettled([
        projectModifyApi.latestGenerationContext(targetId),
        this.loadAIMessages(targetId),
      ])
      if (ctxResult.status === 'fulfilled') {
        const data = ctxResult.value?.data || ctxResult.value || {}
        // 当前项目已存在的版本号 → 同步版本链
        const versionNo = Number(data.version_no || 0)
        if (versionNo > 0) {
          this.currentVersionNo = versionNo
          this.basedOnVersionNo = Math.max(versionNo - 1, 0)
        }
        // 最新版本摘要作为 versionHistory 第一项（保持原有时间线组件不空）
        const latestVersion = data.latest_version
        if (latestVersion) {
          const summary = {
            version_no: Number(latestVersion.version_no || versionNo || 0),
            version_id: latestVersion.version_id || '',
            version_summary: latestVersion.version_summary || latestVersion.change_note || '',
            modify_instruction: latestVersion.modify_instruction || latestVersion.change_note || '',
            created_at: latestVersion.created_at || '',
          }
          this.versionHistory = [
            summary,
            ...this.versionHistory.filter((item) => Number(item.version_no) !== summary.version_no),
          ]
        }
        // 把后端 page_bindings 暴露给证据侧栏读取
        this.pageBindings = Array.isArray(data.page_bindings) ? data.page_bindings : []
        this._persist()
        return data
      }
      // 后端不可用时回退到 bindProject 结果，不阻断 S3 进入
      console.warn('[modifyStore] latest-generation-context 拉取失败，使用本地状态', ctxResult.reason)
      return null
    },

    /** 重置（新建课件/切换项目时）。
     *
     * 关键：保留 _pendingPersist 给 flush 调用处理；如果当前 projectId 还有未
     * 落库的气泡，先尝试发出去再清，避免 create project 时丢掉旧项目的对话。
     * 然后把 projectId / messages / 各版本栈清空，等待下一个 bindProject 接管。
     */
    async reset() {
      const prevProjectId = this.projectId
      // 先把旧项目的待落库气泡发出去（如果有）；失败不影响重置。
      if (prevProjectId && this._pendingPersist.length) {
        try { await this._flushPendingMessages() } catch {}
      }
      this.projectId = ''
      this.messages = []
      this.inputText = ''
      this.modifying = false
      this.lastIntent = null
      this.pendingClarification = null
      this.currentVersionNo = 0
      this.basedOnVersionNo = 0
      this.versionHistory = []
      this.recentlyModifiedIds = []
      this.undoStack = []
      this.redoStack = []
      this.error = ''
      this.lastFailedInstruction = ''
      this.pageBindings = []
      this._pendingPersist = []
      this._persist()
      // 注意：不主动 DELETE 后端对话；后端按 project_id 隔离，留着让用户切回时能恢复。
      // 若业务上要求"新建课件丢弃全部历史"，由调用方在 createProject 前显式
      // projectModifyApi.clearAIMessages(oldProjectId) 处理。
    },

    _pushMessage(role, text, extra = {}) {
      const message = {
        id: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        role,
        text,
        created_at: new Date().toISOString(),
        ...extra,
      }
      this.messages.push(message)
      if (this.messages.length > 100) this.messages.splice(0, this.messages.length - 100)
      // 标记为待落库，由 sendModify / clarification / undo / redo 等业务动作完成后
      // 一次性 _flushPendingMessages 批量 upsert，避免每条消息都发一次 HTTP。
      this._pendingPersist.push(message)
      return message
    },

    /**
     * 把自上次 flush 以来 _pushMessage 标记的全部气泡一次性 upsert 到后端。
     * 契约 v1.0 §3.2：按 (project_id, message_id) 幂等，同一会话重发不会产生重复。
     * 失败时仅 warn，不阻断本地流程；下次成功的 sendModify 会再带上未落库的部分。
     */
    async _flushPendingMessages() {
      if (!this.projectId || this._pendingPersist.length === 0) return
      const batch = this._pendingPersist.splice(0, this._pendingPersist.length)
      const payload = batch.map((m) => this._toBackendMessage(m))
      try {
        await projectModifyApi.upsertAIMessages(this.projectId, payload)
      } catch (error) {
        // 失败时把 message 还回去，下一次 flush 再尝试
        this._pendingPersist = [...batch, ...this._pendingPersist]
        console.warn('[modifyStore] AI 消息批量落库失败', error)
      }
    },

    /**
     * 把前端的 message shape 转成后端 AIMessageItem：
     * id/message_id、isClarification/is_clarification 等字段名差异在这里归一。
     */
    _toBackendMessage(m) {
      return {
        message_id: m.id,
        role: m.role,
        text: m.text,
        intent: m.intent || undefined,
        is_clarification: !!m.isClarification,
        is_summary: !!m.isSummary,
        is_error: !!m.isError,
        version_no: Number(m.versionNo || 0),
        created_at: m.created_at || new Date().toISOString(),
      }
    },

    /**
     * 契约 v1.0 §3.2：拉后端权威 AI 对话气泡，覆盖本地 messages。
     * 切 PPT / 刷新后用这一份作为权威读源，避免 localStorage 残留。
     */
    async loadAIMessages(projectId) {
      const targetId = String(projectId || this.projectId || '')
      if (!targetId) return []
      try {
        const resp = await projectModifyApi.listAIMessages(targetId)
        const msgs = (resp?.data || resp || {}).messages || []
        this.messages = Array.isArray(msgs)
          ? msgs.map((m) => ({
              id: m.message_id || m.id,
              role: m.role,
              text: m.text,
              intent: m.intent,
              isClarification: !!m.is_clarification,
              isSummary: !!m.is_summary,
              isError: !!m.is_error,
              versionNo: Number(m.version_no || 0),
              created_at: m.created_at,
            }))
          : []
        // 从后端拉来的消息视为已落库，避免启动时无脑重发
        this._pendingPersist = []
        this._persist()
        return this.messages
      } catch (error) {
        console.warn('[modifyStore] 拉 AI 消息失败，使用本地缓存', error)
        return this.messages
      }
    },

    /**
     * C6 核心：发送修改指令
     * @param {Array} nodes 当前大纲节点（来自 outlineStore.nodes，含内容）
     * @param {Function} onApplied 修改应用回调（all_nodes 写回 outlineStore）
     */
    async sendModify(nodes, onApplied) {
      const teacherReply = this.inputText.trim()
      if (!this.projectId || !teacherReply || this.modifying) return

      const clarificationContext = this.pendingClarification
      const instruction = clarificationContext
        ? `${clarificationContext.originalInstruction}\n补充说明：${teacherReply}\n请结合以上两轮信息完成修改。`
        : teacherReply

      this.modifying = true
      this.error = ''
      this.lastFailedInstruction = ''
      this._pushMessage('teacher', teacherReply)
      this.inputText = ''

      try {
        const resp = await projectModifyApi.modify(this.projectId, instruction, nodes)
        const data = resp.data || resp

        // 追问分支：AI 置信度低，返回澄清问题，不执行修改
        if (data.clarification) {
          this.lastIntent = data.intent || null
          this.pendingClarification = {
            originalInstruction: clarificationContext?.originalInstruction || teacherReply,
            intent: data.intent || clarificationContext?.intent || null,
            question: data.clarification,
          }
          this._pushMessage('ai', `❓ ${data.clarification}`, { isClarification: true })
          this._persist()
          await this._flushPendingMessages()
          return
        }

        this.pendingClarification = null

        // 成功分支：解析结果 + 修改摘要 + 版本标签
        const intent = data.intent || {}
        const actionLabel = {
          simplify: '精简内容', expand: '扩充内容', delete: '删除节点',
          add: '新增节点', reorder: '调整顺序', restyle: '调整样式', rewrite: '重写内容',
        }[intent.action] || intent.action
        const targetDesc = (intent.target_ids || []).length
          ? `目标：${intent.target_ids.join('、')}`
          : '目标：整个课件'
        this._pushMessage('ai', `✅ 已执行：${actionLabel} · ${targetDesc}`, {
          intent,
          versionNo: data.new_version_no,
        })

        const modifiedNodes = Array.isArray(data.modified_nodes) ? data.modified_nodes : []
        const modifiedTitles = modifiedNodes
          .map((node) => node.title || node.node_title || node.node_id)
          .filter(Boolean)
        const summary = modifiedTitles.length
          ? `已更新：${modifiedTitles.join('、')}`
          : (intent.action === 'restyle' ? '已更新 PPT 呈现样式，正文与引用保持不变' : '本次未改动正文节点')
        this._pushMessage('ai', summary, { isSummary: true })

        // 版本推进 + 撤销栈
        if (data.new_version_no > this.currentVersionNo) {
          this.undoStack.push(this.currentVersionNo || 0)
          this.redoStack = []
          this.basedOnVersionNo = Math.max(Number(data.new_version_no || 0) - 1, 0)
          this.currentVersionNo = data.new_version_no
        }

        // C7 高亮集合
        this.recentlyModifiedIds = modifiedNodes
          .map((node) => node.node_id)
          .filter(Boolean)
        if (!this.recentlyModifiedIds.length) {
          this.recentlyModifiedIds = (intent.target_ids || []).slice()
        }
        if (this.recentlyModifiedIds.length) {
          setTimeout(() => { this.recentlyModifiedIds = [] }, 2000)
        }

        // 应用修改结果
        if (typeof onApplied === 'function' && Array.isArray(data.all_nodes)) {
          await Promise.resolve(onApplied({
            allNodes: data.all_nodes,
            modifiedNodes,
            intent,
            instruction,
            previousVersionNo: data.previous_version_no,
            newVersionNo: data.new_version_no,
            presentation: data.presentation || intent.presentation || null,
          }))
        }

        await this.loadVersionHistory()
        this._persist()
        // 把刚才推送的全部气泡（teacher + ai 已执行 + ai summary）批量落库
        await this._flushPendingMessages()
      } catch (e) {
        this.error = e?.message || '修改失败，请重试'
        this.lastFailedInstruction = teacherReply
        this._pushMessage('ai', `⚠️ ${this.error}`, { isError: true })
        await this._flushPendingMessages()
      } finally {
        this.modifying = false
      }
    },

    /** 快捷指令 */
    applyQuickChip(chip) {
      this.inputText = chip.text
    },

    retryLast() {
      if (this.lastFailedInstruction) this.inputText = this.lastFailedInstruction
      this.error = ''
    },

    /** 撤销 = 回滚到上一个版本（克隆式，产生新版本号） */
    async undo(nodes, onApplied) {
      if (!this.canUndo) return
      const targetNo = this.undoStack.pop()
      if (targetNo == null) return
      try {
        this.modifying = true
        // 回滚到 targetNo（0 = 初始状态，回滚到 v1 的修改前——用 v1 快照）
        const rollbackTo = targetNo > 0 ? targetNo : 1
        const target = this.versionHistory.find((item) => Number(item.version_no) === rollbackTo)
        if (!target?.version_id) throw new Error('目标版本标识缺失，请刷新版本历史后重试')
        const resp = await projectModifyApi.rollback(this.projectId, target.version_id)
        const data = resp.data || resp
        this.redoStack.push(this.currentVersionNo)
        this.basedOnVersionNo = rollbackTo
        this.currentVersionNo = data.new_version_no || this.currentVersionNo
        this._pushMessage('ai', `↩️ 已回滚到 v${rollbackTo} 的内容（新版本 v${this.currentVersionNo}）`, {
          versionNo: this.currentVersionNo,
        })
        if (typeof onApplied === 'function' && Array.isArray(data.nodes)) {
          await Promise.resolve(onApplied({ allNodes: data.nodes, modifiedNodes: data.nodes, intent: { action: 'rollback', target_ids: [] } }))
        }
        this._persist()
        await this._flushPendingMessages()
      } catch (e) {
        this.error = e?.message || '撤销失败'
        this._pushMessage('ai', `⚠️ ${this.error}`, { isError: true })
        await this._flushPendingMessages()
      } finally {
        this.modifying = false
      }
    },

    /** 重做 = 回滚到撤销前的版本 */
    async redo(onApplied) {
      if (!this.canRedo) return
      const targetNo = this.redoStack.pop()
      if (targetNo == null) return
      try {
        this.modifying = true
        const target = this.versionHistory.find((item) => Number(item.version_no) === targetNo)
        if (!target?.version_id) throw new Error('目标版本标识缺失，请刷新版本历史后重试')
        const resp = await projectModifyApi.rollback(this.projectId, target.version_id)
        const data = resp.data || resp
        this.undoStack.push(this.currentVersionNo)
        this.basedOnVersionNo = targetNo
        this.currentVersionNo = data.new_version_no || this.currentVersionNo
        this._pushMessage('ai', `↪️ 已恢复到 v${targetNo} 的内容（新版本 v${this.currentVersionNo}）`, {
          versionNo: this.currentVersionNo,
        })
        if (typeof onApplied === 'function' && Array.isArray(data.nodes)) {
          await Promise.resolve(onApplied({ allNodes: data.nodes, modifiedNodes: data.nodes, intent: { action: 'rollback', target_ids: [] } }))
        }
        this._persist()
        await this._flushPendingMessages()
      } catch (e) {
        this.error = e?.message || '重做失败'
        this._pushMessage('ai', `⚠️ ${this.error}`, { isError: true })
        await this._flushPendingMessages()
      } finally {
        this.modifying = false
      }
    },

    /** 拉取版本历史（C7 时间线） */
    async loadVersionHistory() {
      if (!this.projectId) return
      try {
        const resp = await projectModifyApi.versions(this.projectId)
        const data = resp.data || resp
        this.versionHistory = data.items || []
        const latest = this.versionHistory.reduce((max, item) => Math.max(max, Number(item.version_no || 0)), 0)
        if (latest > this.currentVersionNo) {
          this.currentVersionNo = latest
          this.basedOnVersionNo = Math.max(latest - 1, 0)
        }
      } catch {
        this.versionHistory = []
      }
    },

    _persist() {
      try {
        if (typeof window !== 'undefined' && this.projectId) {
          window.localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify({
              projectId: this.projectId,
              currentVersionNo: this.currentVersionNo,
              basedOnVersionNo: this.basedOnVersionNo,
              pendingClarification: this.pendingClarification,
              messages: this.messages.slice(-30),
            }),
          )
        }
      } catch { /* localStorage 不可用时静默 */ }
    },
  },
})
