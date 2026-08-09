import { defineStore } from 'pinia'
import { teacherV1Api } from '../services/v1'

/**
 * S3 讲稿生成 Store (Studio)
 *
 * 对应讲稿生成与节点编辑模块的状态管理，包括：
 * - 讲稿内容与结构化节点树
 * - 节点编辑与版本
 * - AI 生成状态
 * - 音频生成状态
 * - gen/create、gen/status、gen/modify、gen/preview
 */
export const useGenerationStore = defineStore('generation', {
  state: () => ({
    /** 当前页讲稿文本 */
    currentScript: '',

    /** 当前页结构化节点树 */
    currentScriptNodes: [],
    // currentScriptNodes[i] 结构参考：
    // {
    //   id: string,
    //   nodeId: string,
    //   title: string,
    //   summary: string,
    //   content: string,
    //   scriptText: string,
    //   status: 'pending' | 'generating' | 'completed'
    // }

    /** 当前页音频 */
    currentPageAudio: null,
    audioGenerating: false,

    /** AI 生成状态 */
    isGenerating: false,
    scriptSaving: false,
    generateProgress: 0,
    generateStageText: '',

    /** 生成任务 ID */
    genTaskId: '',
    /** 当前 generation_id（S3 输出给 S4） */
    generationId: '',

    /** 迭代同步通知 */
    iterationSyncNotice: '',

    /** 本地讲稿缓存 */
    localScriptCache: {},

    /** 学情洞察（节点级别） */
    nodeInsights: {},

    /** 预览 HTML */
    previewHtml: '',

    /** 修改命令（gen/modify 的输入） */
    modifyCommands: [],
    /** 修改后的结果 */
    modifyResult: null
  }),

  getters: {
    isGeneratingAudio: (state) => state.audioGenerating,
    isSaving: (state) => state.scriptSaving,
    hasNodes: (state) => state.currentScriptNodes.length > 0
  },

  actions: {
    setScript(script) {
      this.currentScript = script
    },

    setNodes(nodes) {
      this.currentScriptNodes = nodes
    },

    updateNode(index, patch) {
      if (index >= 0 && index < this.currentScriptNodes.length) {
        this.currentScriptNodes[index] = {
          ...this.currentScriptNodes[index],
          ...patch
        }
      }
    },

    setPageAudio(audio) {
      this.currentPageAudio = audio
    },

    setAudioGenerating(generating) {
      this.audioGenerating = generating
    },

    setGenerating(generating) {
      this.isGenerating = generating
      if (!generating) {
        this.generateProgress = 0
        this.generateStageText = ''
      }
    },

    setSaving(saving) {
      this.scriptSaving = saving
    },

    setGenerateProgress(progress, stageText) {
      this.generateProgress = progress
      if (stageText) this.generateStageText = stageText
    },

    setIterationSyncNotice(notice) {
      this.iterationSyncNotice = notice
    },

    cacheScript(courseId, page, content, nodes) {
      if (!courseId) return
      if (!this.localScriptCache[courseId]) {
        this.localScriptCache[courseId] = {}
      }
      this.localScriptCache[courseId][String(page)] = {
        content: String(content || ''),
        nodes: Array.isArray(nodes) ? nodes : []
      }
    },

    readCache(courseId, page) {
      return this.localScriptCache[courseId]?.[String(page)] || null
    },

    // ================================================================
    // gen API 动作
    // ================================================================

    /**
     * 创建生成任务 (gen/create)
     * 调用后端 outline → nodes 全流程
     */
    async createGeneration(courseId) {
      this.setGenerating(true)
      this.setGenerateProgress(5, '创建生成任务…')
      try {
        const resp = await teacherV1Api.generation.createGeneration({
          course_id: courseId
        })
        const data = resp?.data || resp
        this.genTaskId = data.task_id || ''
        this.generationId = data.generation_id || ''
        this.setGenerateProgress(15, '任务已创建')
        return data
      } catch (err) {
        this.setGenerating(false)
        throw err
      }
    },

    /**
     * 轮询生成状态 (gen/status)
     */
    async pollGenerationStatus(taskId, onProgress) {
      const maxRetries = 30
      const interval = 2000

      for (let i = 0; i < maxRetries; i++) {
        await new Promise(resolve => setTimeout(resolve, interval))

        try {
          const resp = await teacherV1Api.generation.getGenerationStatus(taskId)
          const data = resp?.data || resp
          const status = data.status || ''
          const progress = data.progress || 0
          const stageText = data.stage_text || ''
          const nodes = data.nodes || data.result?.nodes || []

          this.setGenerateProgress(15 + progress * 0.75, stageText)
          if (onProgress) onProgress(progress, stageText)

          if (status === 'completed' || status === 'done') {
            if (nodes.length > 0) {
              this.setNodes(nodes)
            }
            this.setGenerateProgress(100, '生成完成')
            this.setGenerating(false)
            return { status: 'completed', nodes }
          }

          if (status === 'failed' || status === 'error') {
            this.setGenerating(false)
            return { status: 'failed', error: data.error || '生成失败' }
          }
        } catch (err) {
          console.warn('轮询状态失败', err)
        }
      }

      // 超时
      this.setGenerating(false)
      return { status: 'timeout', error: '生成超时' }
    },

    /**
     * 提交修改命令 (gen/modify)
     */
    async submitModify(genId, commands) {
      this.scriptSaving = true
      try {
        const resp = await teacherV1Api.generation.modifyNodes({
          generation_id: genId,
          commands: commands || this.modifyCommands
        })
        const data = resp?.data || resp
        this.modifyResult = data
        if (data.nodes) {
          this.setNodes(data.nodes)
        }
        return data
      } catch (err) {
        console.error('修改失败', err)
        throw err
      } finally {
        this.scriptSaving = false
      }
    },

    /**
     * 获取预览 (gen/preview)
     */
    async fetchPreview(nodes) {
      try {
        const resp = await teacherV1Api.generation.preview({
          nodes: nodes || this.currentScriptNodes
        })
        const data = resp?.data || resp
        this.previewHtml = data.html || ''
        return data
      } catch (err) {
        console.warn('预览接口失败', err)
        throw err
      }
    },

    addModifyCommand(command) {
      this.modifyCommands.push({
        ...command,
        id: Date.now().toString(36)
      })
    },

    removeModifyCommand(id) {
      this.modifyCommands = this.modifyCommands.filter(c => c.id !== id)
    },

    clearModifyCommands() {
      this.modifyCommands = []
    },

    reset() {
      this.currentScript = ''
      this.currentScriptNodes = []
      this.currentPageAudio = null
      this.audioGenerating = false
      this.isGenerating = false
      this.generateProgress = 0
      this.generateStageText = ''
      this.genTaskId = ''
      this.generationId = ''
      this.previewHtml = ''
      this.modifyCommands = []
      this.modifyResult = null
    }
  }
})
