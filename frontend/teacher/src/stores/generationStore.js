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