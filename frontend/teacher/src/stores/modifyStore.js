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
    /** 当前版本号（每次成功修改自增） */
    currentVersionNo: 0,
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
  }),

  getters: {
    canSend: (state) => !!state.projectId && !!state.inputText.trim() && !state.modifying,
    canUndo: (state) => state.undoStack.length > 0,
    canRedo: (state) => state.redoStack.length > 0,
    /** 版本标签文案 */
    versionLabel: (state) =>
      state.currentVersionNo > 0 ? `当前 v${state.currentVersionNo}` : '尚未生成版本',
    /** 快捷指令 chips（C6） */
    quickChips: () => [
      { label: '精简这页', text: '精简当前选中页面的内容，减少文字量' },
      { label: '增加案例', text: '为当前内容增加一个生活案例' },
      { label: '换个风格', text: '整体风格换成更简洁的商务风' },
      { label: '调整顺序', text: '把当前页面和下一页交换顺序' },
    ],
  },

  actions: {
    /** 设置项目上下文（S3 进入时调用） */
    bindProject(projectId) {
      this.projectId = projectId || ''
      if (!this.projectId) {
        this.messages = []
        this.currentVersionNo = 0
        this.versionHistory = []
      }
    },

    /** 重置（新建课件/切换项目时） */
    reset() {
      this.projectId = ''
      this.messages = []
      this.inputText = ''
      this.modifying = false
      this.lastIntent = null
      this.currentVersionNo = 0
      this.versionHistory = []
      this.recentlyModifiedIds = []
      this.undoStack = []
      this.redoStack = []
      this.error = ''
      this._persist()
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
      const instruction = this.inputText.trim()
      if (!this.projectId || !instruction || this.modifying) return

      this.modifying = true
      this.error = ''
      this._pushMessage('teacher', instruction)
      this.inputText = ''

      try {
        const resp = await projectModifyApi.modify(this.projectId, instruction, nodes)
        const data = resp.data || resp

        // 追问分支：AI 置信度低，返回澄清问题，不执行修改
        if (data.clarification) {
          this.lastIntent = data.intent || null
          this._pushMessage('ai', `❓ ${data.clarification}`, { isClarification: true })
          return
        }

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

        const modifiedCount = (data.modified_nodes || []).length
        this._pushMessage('ai', `本次修改了 ${modifiedCount} 个节点`, { isSummary: true })

        // 版本推进 + 撤销栈
        if (data.new_version_no > this.currentVersionNo) {
          this.undoStack.push(this.currentVersionNo || 0)
          this.redoStack = []
          this.currentVersionNo = data.new_version_no
        }

        // C7 高亮集合
        this.recentlyModifiedIds = (intent.target_ids || []).slice()
        if (this.recentlyModifiedIds.length) {
          setTimeout(() => { this.recentlyModifiedIds = [] }, 2000)
        }

        // 应用修改结果
        if (typeof onApplied === 'function' && Array.isArray(data.all_nodes)) {
          await Promise.resolve(onApplied(data.all_nodes))
        }

        this._persist()
      } catch (e) {
        this.error = e?.message || '修改失败，请重试'
        this._pushMessage('ai', `⚠️ ${this.error}`, { isError: true })
      } finally {
        this.modifying = false
      }
    },

    /** 快捷指令 */
    applyQuickChip(chip) {
      this.inputText = chip.text
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
        const resp = await projectModifyApi.rollback(this.projectId, rollbackTo)
        const data = resp.data || resp
        this.redoStack.push(this.currentVersionNo)
        this.currentVersionNo = data.new_version_no || this.currentVersionNo
        this._pushMessage('ai', `↩️ 已回滚到 v${rollbackTo} 的内容（新版本 v${this.currentVersionNo}）`, {
          versionNo: this.currentVersionNo,
        })
        if (typeof onApplied === 'function' && Array.isArray(data.nodes)) {
          await Promise.resolve(onApplied(data.nodes))
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
        const resp = await projectModifyApi.rollback(this.projectId, targetNo)
        const data = resp.data || resp
        this.undoStack.push(this.currentVersionNo)
        this.currentVersionNo = data.new_version_no || this.currentVersionNo
        this._pushMessage('ai', `↪️ 已恢复到 v${targetNo} 的内容（新版本 v${this.currentVersionNo}）`, {
          versionNo: this.currentVersionNo,
        })
        if (typeof onApplied === 'function' && Array.isArray(data.nodes)) {
          await Promise.resolve(onApplied(data.nodes))
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
              messages: this.messages.slice(-30),
            }),
          )
        }
      } catch { /* localStorage 不可用时静默 */ }
    },
  },
})
