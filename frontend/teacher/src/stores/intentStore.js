import { defineStore } from 'pinia'
import { teacherIntentApi } from '../services/v1/intentApi'

const WORKFLOW_SESSION_KEY = 'fuww_workflow_session_id'
const S1_STATE_KEY = 'fuww_s1_conversation'
const CONFIRMED_INTENT_KEY = 'fuww_s1_confirmed_intent'
const INTENT_ID_KEY = 'fuww_workflow_intent_id'

const welcomeMessage = () => ({
  role: 'assistant',
  content: '你好，我是你的教学设计智能体。告诉我这节课想讲什么、面向谁，我会通过几轮简短对话把想法整理成可执行的教学方案。'
})

const createSessionId = () => `sess_s1_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`

const cleanRevisionValue = (value) => String(value ?? '').trim().replace(/[；;。]+$/g, '')

export const buildIntentRevisionMessage = (revision = {}) => {
  const segments = []
  const topic = cleanRevisionValue(revision.topic)
  const duration = Number.parseInt(revision.duration_minutes, 10)
  const targetStudent = cleanRevisionValue(revision.target_student)
  const style = cleanRevisionValue(revision.style)
  const points = Array.isArray(revision.knowledge_points)
    ? revision.knowledge_points
    : String(revision.knowledge_points || '').split(/[、，,；;\n]/)
  const knowledgePoints = points.map(cleanRevisionValue).filter(Boolean)

  if (topic) segments.push(`课程主题：${topic}`)
  if (Number.isFinite(duration) && duration > 0) segments.push(`授课时长：${duration}分钟`)
  if (targetStudent) segments.push(`授课对象：${targetStudent}`)
  if (style) segments.push(`教学风格：${style}`)
  if (knowledgePoints.length) segments.push(`知识点：${knowledgePoints.join('、')}`)
  segments.push(`互动设计：${revision.with_interactive ? '需要' : '不需要'}`)
  return `请更新教学意图：${segments.join('；')}。`
}

const readStorage = (key, fallback = null) => {
  if (typeof window === 'undefined') return fallback
  try {
    const value = window.localStorage.getItem(key)
    return value ? JSON.parse(value) : fallback
  } catch {
    return fallback
  }
}

export const useIntentStore = defineStore('intent', {
  state: () => ({
    sessionId: '',
    messages: [],
    intentSummary: null,
    sessionStatus: 'collecting',
    completionPct: 0,
    turnCount: 0,
    maxTurns: 8,
    canConfirm: false,
    followupQuestions: [],
    humanSummary: '',
    intentId: '',
    isAnalyzing: false,
    isConfirming: false,
    error: '',
    engine: '',
    usedFallback: false
  }),

  getters: {
    isConfirmed: (state) => state.sessionStatus === 'confirmed' && !!state.intentId,
    teacherMessages: (state) => state.messages.filter((item) => item.role === 'teacher'),
    qualityReady: (state) => state.completionPct >= 80,
    hasStarted: (state) => state.messages.some((item) => item.role === 'teacher')
  },

  actions: {
    initialize() {
      if (this.sessionId) return
      const saved = readStorage(S1_STATE_KEY)
      if (saved?.sessionId && Array.isArray(saved.messages)) {
        Object.assign(this, {
          ...saved,
          isAnalyzing: false,
          isConfirming: false,
          error: ''
        })
        return
      }
      const storedSession = typeof window !== 'undefined'
        ? window.localStorage.getItem(WORKFLOW_SESSION_KEY)
        : ''
      this.sessionId = storedSession || createSessionId()
      this.messages = [welcomeMessage()]
      this.persist()
    },

    async sendMessage(text) {
      const content = String(text || '').trim()
      if (!content || this.isAnalyzing || this.isConfirmed) return false
      this.error = ''
      this.messages.push({ role: 'teacher', content })
      this.isAnalyzing = true
      this.persist()
      try {
        const result = await teacherIntentApi.extract({
          sessionId: this.sessionId,
          messages: this.messages.map(({ role, content: messageContent }) => ({ role, content: messageContent }))
        })
        this.intentSummary = result.intent_summary || null
        this.sessionStatus = result.session_status || 'clarifying'
        this.completionPct = Number(result.completion_pct || 0)
        this.turnCount = Number(result.turn_count || this.teacherMessages.length)
        this.maxTurns = Number(result.max_turns || 8)
        this.canConfirm = Boolean(result.can_confirm)
        this.followupQuestions = result.followup_questions || []
        this.humanSummary = result.human_summary || ''
        this.engine = result.engine || ''
        this.usedFallback = Boolean(result.used_fallback)
        this.messages.push({
          role: 'assistant',
          content: result.response || this.followupQuestions[0] || '我已经更新了教学意图，请检查右侧方案卡。'
        })
        this.persist()
        return true
      } catch (error) {
        this.error = error?.name === 'AbortError'
          ? '分析超时，AI Engine 可能仍在处理，请稍后重试。'
          : (error?.message || '暂时无法连接意图理解服务，请检查 Go Backend 与 AI Engine。')
        this.messages.pop()
        this.persist()
        return false
      } finally {
        this.isAnalyzing = false
      }
    },

    async correctIntent(revision) {
      return this.sendMessage(buildIntentRevisionMessage(revision))
    },

    async confirmIntent() {
      if (!this.canConfirm || this.isConfirming) return false
      this.isConfirming = true
      this.error = ''
      try {
        const result = await teacherIntentApi.confirm(this.sessionId)
        this.sessionStatus = result.session_status || 'confirmed'
        this.intentSummary = result.intent_summary || this.intentSummary
        this.intentId = result.intent_id || ''
        this.completionPct = Number(result.completion_pct || this.completionPct)
        this.messages.push({
          role: 'assistant',
          content: '方案已确认并建立意图档案。下一步可以上传教材、课件、图片或视频，我会把资料与这份教学意图自动对齐。'
        })
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(CONFIRMED_INTENT_KEY, JSON.stringify(this.intentSummary))
          window.localStorage.setItem(INTENT_ID_KEY, this.intentId)
        }
        this.persist()
        return true
      } catch (error) {
        this.error = error?.message || '确认失败，请补充核心信息后重试。'
        return false
      } finally {
        this.isConfirming = false
      }
    },

    reset() {
      this.sessionId = createSessionId()
      this.messages = [welcomeMessage()]
      this.intentSummary = null
      this.sessionStatus = 'collecting'
      this.completionPct = 0
      this.turnCount = 0
      this.maxTurns = 8
      this.canConfirm = false
      this.followupQuestions = []
      this.humanSummary = ''
      this.intentId = ''
      this.isAnalyzing = false
      this.isConfirming = false
      this.error = ''
      this.engine = ''
      this.usedFallback = false
      if (typeof window !== 'undefined') {
        window.localStorage.removeItem(CONFIRMED_INTENT_KEY)
        window.localStorage.removeItem(INTENT_ID_KEY)
      }
      this.persist()
    },

    persist() {
      if (typeof window === 'undefined' || !this.sessionId) return
      window.localStorage.setItem(WORKFLOW_SESSION_KEY, this.sessionId)
      window.localStorage.setItem(S1_STATE_KEY, JSON.stringify({
        sessionId: this.sessionId,
        messages: this.messages,
        intentSummary: this.intentSummary,
        sessionStatus: this.sessionStatus,
        completionPct: this.completionPct,
        turnCount: this.turnCount,
        maxTurns: this.maxTurns,
        canConfirm: this.canConfirm,
        followupQuestions: this.followupQuestions,
        humanSummary: this.humanSummary,
        intentId: this.intentId,
        engine: this.engine,
        usedFallback: this.usedFallback
      }))
    }
  }
})
