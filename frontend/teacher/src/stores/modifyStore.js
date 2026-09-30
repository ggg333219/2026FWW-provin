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
    pendingConfirmation: null,
    confirmationReady: false,
    /** 当前版本号（每次成功修改自增） */
    currentVersionNo: 0,
    /** 当前版本由哪个版本修改而来。 */
    basedOnVersionNo: 0,
    /** 版本历史 [{ version_no, modify_instruction, created_at }] */
    versionHistory: [],
    /** 本次修改的节点（C7 高亮用；2s 后清除） */
    recentlyModifiedIds: [],
    /**
     * 教师当前选中的页面（node_id）。
     * 对话里说「这页」时靠它定位 —— 模型只看到标题和摘要，猜不出「这页」是哪页。
     * 为空表示未选中，此时完全按指令里的页号/标题定位（与加这个字段之前一致）。
     */
    activeNodeId: '',
    /** 撤销栈：可回滚的版本号 */
    undoStack: [],
    /** 重做栈 */
    redoStack: [],
    /** 错误提示 */
    error: '',
    /** 最近一次失败的教师输入，供一键重试。 */
    lastFailedInstruction: '',
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
    /**
     * 快捷指令 chips（C6）。
     *
     * 前两条说的是「这页」，与选中页配套：指令里带指示代词，引擎才会用界面选中页
     * 覆盖模型的猜测（见 ai_engine/gen/modify_intent.py 的 _resolve_active_target）。
     * 「调整顺序」不在此列 —— 交换位置要两个页号，套用一个选中页只会改错。
     */
    quickChips: () => [
      { label: '精简这页', text: '精简这页的内容，减少文字量' },
      { label: '增加案例', text: '为这页增加一个生活案例' },
      { label: '换个风格', text: '整体风格换成更简洁的商务风' },
      { label: '调整顺序', text: '把当前页面和下一页交换顺序' },
    ],
  },

  actions: {
    /** 设置项目上下文（S3 进入时调用） */
    bindProject(projectId) {
      if ((projectId || '') !== this.projectId) {
        // 换项目 → 上一份课件的选中页在这里没有意义
        this.activeNodeId = ''
      }
      this.projectId = projectId || ''
      if (!this.projectId) {
        this.messages = []
        this.currentVersionNo = 0
        this.versionHistory = []
        return
      }
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
    },

    /** 重置（新建课件/切换项目时） */
    reset() {
      this.projectId = ''
      this.messages = []
      this.inputText = ''
      this.modifying = false
      this.lastIntent = null
      this.pendingClarification = null
      this.pendingConfirmation = null
      this.confirmationReady = false
      this.currentVersionNo = 0
      this.basedOnVersionNo = 0
      this.versionHistory = []
      this.recentlyModifiedIds = []
      this.activeNodeId = ''
      this.undoStack = []
      this.redoStack = []
      this.error = ''
      this.lastFailedInstruction = ''
      this._persist()
    },

    /** 选中某一页（预览页列表 / 面板下拉都可改它）。 */
    setActiveNode(nodeId) {
      this.activeNodeId = nodeId || ''
    },

    _pushMessage(role, text, extra = {}) {
      this.messages.push({
        id: `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        role,
        text,
        ...extra,
      })
      if (this.messages.length > 100) this.messages.splice(0, this.messages.length - 100)
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

      const confirmed = this.confirmationReady
      this.confirmationReady = false
      try {
        const resp = await projectModifyApi.modify(this.projectId, instruction, nodes, {
          activeNodeId: this.activeNodeId,
          confirmed,
        })
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
          return
        }

        if (data.requires_confirmation) {
          this.pendingConfirmation = {
            instruction,
            candidates: Array.isArray(data.candidates) ? data.candidates : [],
            intent: data.intent || null,
          }
          this._pushMessage('ai', '⚠️ 这次修改会影响高风险元素，请确认后继续。', { isConfirmation: true })
          this._persist()
          return
        }

        this.pendingClarification = null
        this.pendingConfirmation = null

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
          // 改完把选中页跟到刚改的那页：「再改改刚才那页」不必重新点一次。
          this.activeNodeId = this.recentlyModifiedIds[0]
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
      } catch (e) {
        this.error = e?.message || '修改失败，请重试'
        this.lastFailedInstruction = teacherReply
        this._pushMessage('ai', `⚠️ ${this.error}`, { isError: true })
      } finally {
        this.modifying = false
      }
    },

    /** 快捷指令 */
    applyQuickChip(chip) {
      this.inputText = chip.text
    },

    confirmPending(nodes = [], onApplied) {
      if (!this.pendingConfirmation || this.modifying) return
      this.inputText = this.pendingConfirmation.instruction
      this.confirmationReady = true
      return this.sendModify(nodes, onApplied)
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
      } catch (e) {
        this.error = e?.message || '撤销失败'
        this._pushMessage('ai', `⚠️ ${this.error}`, { isError: true })
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
      } catch (e) {
        this.error = e?.message || '重做失败'
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
