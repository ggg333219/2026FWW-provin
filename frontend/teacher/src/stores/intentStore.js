import { defineStore } from 'pinia'

/**
 * S1 意图理解 Store
 *
 * 对应意图理解模块的状态管理，包括：
 * - 教学意图的捕获与解析
 * - 意图结构化结果
 * - 流式生成状态
 */
export const useIntentStore = defineStore('intent', {
  state: () => ({
    /** 原始输入文本 */
    rawInput: '',

    /** 解析后的结构化意图 */
    parsedIntent: null,
    // parsedIntent 结构参考：
    // {
    //   topic: string,           // 教学主题
    //   grade: string,           // 年级
    //   subject: string,         // 学科
    //   learningObjectives: [],  // 学习目标列表
    //   difficulty: string,      // 难度等级
    //   estimatedDuration: number, // 预估课时
    //   prerequisite: []         // 前置知识
    // }

    /** 流式生成中的中间结果 */
    streamingResult: '',

    /** 是否正在生成 */
    isGenerating: false,

    /** 生成进度 (0-100) */
    progress: 0,

    /** 错误信息 */
    error: '',

    /** 历史记录 */
    history: []
  }),

  getters: {
    hasResult: (state) => !!state.parsedIntent,
    isStreaming: (state) => state.isGenerating && state.progress < 100
  },

  actions: {
    setRawInput(text) {
      this.rawInput = text
    },

    setParsedIntent(intent) {
      this.parsedIntent = intent
      if (intent && this.rawInput) {
        this.history.unshift({
          input: this.rawInput,
          result: intent,
          timestamp: new Date().toISOString()
        })
      }
    },

    updateStreaming(chunk) {
      this.streamingResult += chunk
    },

    setGenerating(generating) {
      this.isGenerating = generating
      if (!generating) {
        this.progress = 0
      }
    },

    setProgress(progress) {
      this.progress = Math.min(100, Math.max(0, progress))
    },

    setError(error) {
      this.error = error
      this.isGenerating = false
    },

    reset() {
      this.rawInput = ''
      this.parsedIntent = null
      this.streamingResult = ''
      this.isGenerating = false
      this.progress = 0
      this.error = ''
    }
  }
})
