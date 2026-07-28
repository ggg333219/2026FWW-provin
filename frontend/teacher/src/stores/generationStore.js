import { defineStore } from 'pinia'

/**
 * S3 讲稿生成 Store (Studio)
 *
 * 对应讲稿生成与节点编辑模块的状态管理，包括：
 * - 讲稿内容与结构化节点树
 * - 节点编辑与版本
 * - AI 生成状态
 * - 音频生成状态
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
    //   scriptText: string,
    //   reteachScript: string,
    //   transitionText: string,
    //   estimatedDuration: number,
    //   sortOrder: number,
    //   segments: [              // 分段结构（AI 生成时填充）
    //     { segment_type, text, estimated_seconds }
    //   ],
    //   prerequisites: []
    // }

    /** 当前页音频 */
    currentPageAudio: null,
    audioGenerating: false,

    /** AI 生成状态 */
    isGenerating: false,
    scriptSaving: false,
    generateProgress: 0,
    generateStageText: '',

    /** 迭代同步通知 */
    iterationSyncNotice: '',

    /** 本地讲稿缓存 */
    localScriptCache: {},

    /** 学情洞察（节点级别） */
    nodeInsights: {}
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

    reset() {
      this.currentScript = ''
      this.currentScriptNodes = []
      this.currentPageAudio = null
      this.audioGenerating = false
      this.isGenerating = false
      this.generateProgress = 0
      this.generateStageText = ''
    }
  }
})
