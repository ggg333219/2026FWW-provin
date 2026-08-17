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
 *
 * 注意：轮询逻辑在 S3StudioPage.vue 中实现，不在此处。
 */
export const useGenerationStore = defineStore('generation', {
  state: () => ({
    /** 当前页讲稿文本（S2 兼容） */
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

    /** 最近一次 S3 全流程生成的 generation_id，供 S4 版本管理读取。 */
    lastGenId: '',

    /** 当前页音频（S2 兼容） */
    currentPageAudio: null,
    audioGenerating: false,

    /** AI 生成状态 */
    isGenerating: false,
    scriptSaving: false,
    generateProgress: 0,
    generateStageText: '',

    /** 迭代同步通知（S2 兼容） */
    iterationSyncNotice: ''
  }),

  getters: {
    /** S2 兼容：音频是否正在生成 */
    isGeneratingAudio: (state) => state.audioGenerating,
    /** S2 兼容：讲稿是否正在保存 */
    isSaving: (state) => state.scriptSaving,
    /** S2 兼容：是否有节点 */
    hasNodes: (state) => state.currentScriptNodes.length > 0
  },

  actions: {
    setScript(script) {
      this.currentScript = script
    },

    setNodes(nodes) {
      this.currentScriptNodes = nodes
    },

    /** 记录可被 S4 使用的生成 ID，并支持刷新后的工作流续接。 */
    setLastGenId(genId) {
      const normalized = String(genId || '').trim()
      if (!normalized) return ''
      this.lastGenId = normalized
      try {
        window.localStorage.setItem('fuww_last_gen_id', normalized)
      } catch (error) {
        console.warn('[generationStore] 持久化 generation_id 失败', error)
      }
      return normalized
    },

    /** 从 localStorage 恢复最近一次成功生成的 ID。 */
    restoreLastGenId() {
      if (this.lastGenId) return this.lastGenId
      try {
        const cached = window.localStorage.getItem('fuww_last_gen_id')
        if (cached) this.lastGenId = cached
      } catch (error) {
        console.warn('[generationStore] 恢复 generation_id 失败', error)
      }
      return this.lastGenId
    },

    /**
     * 创建 S3 全流程生成任务。响应统一兼容 Go 网关、Python 服务与 Mock 形态。
     */
    async createCoursewareGeneration(request) {
      const response = await teacherV1Api.generation.createGeneration(request)
      const task = response?.data || response || {}
      const generationId = task.generation_id || task.gen_id || task.generationId || task.genId
      if (generationId) this.setLastGenId(generationId)
      return task
    },

    /** 查询生成任务状态，并统一兼容 progress / progress_pct。 */
    async getCoursewareGenerationStatus(taskId) {
      const response = await teacherV1Api.generation.getGenerationStatus(taskId)
      return response?.data || response || {}
    },

    /**
     * 轮询全流程生成任务，并把完成后的节点树回填到 S3 编辑状态。
     */
    async waitForCoursewareGeneration(taskId, { intervalMs = 500, maxAttempts = 240 } = {}) {
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        const status = await this.getCoursewareGenerationStatus(taskId)
        const progress = Number(status.progress_pct ?? (Number(status.progress || 0) * 100))
        this.setGenerateProgress(Number.isFinite(progress) ? progress : 0, status.stage_text || '正在生成课件')

        if (['done', 'completed', 'success'].includes(status.status)) {
          const nodes = Array.isArray(status.nodes) ? status.nodes : []
          this.setNodes(nodes)
          this.setScript(nodes.map((node) => node.script || node.content || node.summary || '').filter(Boolean).join('\n\n'))
          this.setGenerateProgress(100, '生成完成')
          return status
        }
        if (['failed', 'error'].includes(status.status)) {
          throw new Error(status.error || '课件生成失败')
        }
        await new Promise((resolve) => setTimeout(resolve, intervalMs))
      }
      throw new Error('课件生成超时，请稍后在版本管理中查看任务结果')
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
    }
  }
})
