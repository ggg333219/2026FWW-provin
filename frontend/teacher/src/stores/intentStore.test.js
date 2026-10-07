import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { buildIntentRevisionMessage, intentStorageKey, useIntentStore } from './intentStore'
import { teacherIntentApi } from '../services/v1/intentApi'

function createStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key)
  }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

beforeEach(() => {
  const localStorage = createStorage()
  globalThis.window = { localStorage }
  // 后端不可达 → requestJson 回退 Mock（/api/v1/intent/extract + /confirm）
  globalThis.fetch = () => Promise.reject(new Error('backend unreachable'))
  setActivePinia(createPinia())
})

describe('buildIntentRevisionMessage', () => {
  it('builds an explicit correction message understood by the S1 rule engine', () => {
    expect(buildIntentRevisionMessage({
      topic: '快速排序',
      duration_minutes: '50',
      target_student: '大二软件工程学生',
      style: '沉稳专业',
      knowledge_points: '分治思想、枢轴选择，分区过程',
      with_interactive: true
    })).toBe(
      '请更新教学意图：课程主题：快速排序；授课时长：50分钟；授课对象：大二软件工程学生；教学风格：沉稳专业；知识点：分治思想、枢轴选择、分区过程；互动设计：需要。'
    )
  })

  it('can explicitly turn interaction off without sending empty optional fields', () => {
    expect(buildIntentRevisionMessage({
      topic: '快速排序',
      duration_minutes: 45,
      with_interactive: false
    })).toBe('请更新教学意图：课程主题：快速排序；授课时长：45分钟；互动设计：不需要。')
  })
})

describe('S1 意图理解 Mock 链路（extract / confirm）', () => {
  it('服务失败时保留教师原消息，便于核对和重试', async () => {
    vi.spyOn(teacherIntentApi, 'extract').mockRejectedValueOnce(new Error('AI Engine timeout'))
    const store = useIntentStore()
    store.initialize()

    expect(await store.sendMessage('请设计一节高等数学课')).toBe(false)

    expect(store.messages.some((message) => message.role === 'teacher' && message.content === '请设计一节高等数学课')).toBe(true)
    expect(store.error).toContain('AI Engine timeout')
  })

  it('重试失败的最后一条输入不会在多轮对话中重复插入', async () => {
    vi.spyOn(teacherIntentApi, 'extract')
      .mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce({
        intent_summary: { topic: '排序算法', duration_minutes: null, missing_fields: ['duration_minutes'] },
        session_status: 'collecting',
        completion_pct: 25,
        can_confirm: false,
        followup_questions: ['计划安排多少分钟？'],
        response: '计划安排多少分钟？',
        used_fallback: false
      })
    const store = useIntentStore()
    store.initialize()

    expect(await store.sendMessage('我想讲排序算法')).toBe(false)
    expect(await store.sendMessage('我想讲排序算法')).toBe(true)
    expect(store.teacherMessages.filter((message) => message.content === '我想讲排序算法')).toHaveLength(1)
  })

  it('规则降级状态与安全原因会保留并供界面区分', async () => {
    vi.spyOn(teacherIntentApi, 'extract').mockResolvedValueOnce({
      intent_summary: { topic: '排序算法' },
      session_status: 'collecting',
      used_fallback: true,
      fallback_reason: 'engine_unavailable'
    })
    const store = useIntentStore()
    store.initialize()

    expect(await store.sendMessage('排序算法课')).toBe(true)
    expect(store.usedFallback).toBe(true)
    expect(store.fallbackReason).toBe('engine_unavailable')
  })

  it('sendMessage → extract：提取主题并进入澄清（缺核心字段不能确认）', async () => {
    const store = useIntentStore()
    store.initialize()
    expect(store.sessionId).toBeTruthy()

    const ok = await store.sendMessage('我想讲排序算法')
    expect(ok).toBe(true)
    expect(store.intentSummary?.topic).toBe('排序算法')
    expect(store.completionPct).toBeGreaterThan(0)
    expect(store.canConfirm).toBe(false)
    expect(store.followupQuestions.length).toBeGreaterThan(0)
    expect(store.error).toBe('')
  })

  it('修订契约 message 补全核心字段后可确认，并写入 intent_id 交接 key', async () => {
    const store = useIntentStore()
    store.initialize()
    await store.sendMessage('我想讲快速排序，45分钟')
    await store.sendMessage(buildIntentRevisionMessage({
      topic: '快速排序',
      duration_minutes: 45,
      target_student: '大二软件工程学生',
      style: '案例驱动',
      knowledge_points: '分治思想、枢轴选择，分区过程',
      with_interactive: true
    }))

    expect(store.intentSummary?.topic).toBe('快速排序')
    expect(store.intentSummary?.duration_minutes).toBe(45)
    expect(store.intentSummary?.style).toBe('案例驱动')
    expect(store.intentSummary?.target_student).toContain('大二软件工程')
    expect(store.intentSummary?.knowledge_points.length).toBeGreaterThanOrEqual(2)
    expect(store.canConfirm).toBe(true)

    const confirmed = await store.confirmIntent()
    expect(confirmed).toBe(true)
    expect(store.isConfirmed).toBe(true)
    expect(store.intentId).toBeTruthy()
    expect(store.sessionStatus).toBe('confirmed')
    // S1 → S2 交接 key
    expect(window.localStorage.getItem(intentStorageKey('fuww_workflow_intent_id'))).toBe(store.intentId)
    expect(window.localStorage.getItem(intentStorageKey('fuww_s1_confirmed_intent'))).toBeTruthy()
  })

  it('按项目隔离会话，切换项目后再切回可恢复各自对话', async () => {
    const store = useIntentStore()
    store.initialize('project-a')
    const firstSessionId = store.sessionId
    await store.sendMessage('排序算法，45分钟')

    store.initialize('project-b')
    const secondSessionId = store.sessionId
    expect(secondSessionId).not.toBe(firstSessionId)
    expect(store.messages).toHaveLength(1)

    store.initialize('project-a')
    expect(store.sessionId).toBe(firstSessionId)
    expect(store.messages.some((message) => message.content === '排序算法，45分钟')).toBe(true)
    expect(window.localStorage.getItem('fuww_workflow_session_id')).toBeNull()
  })

  it('切换项目后丢弃在途提取响应，不污染新项目状态与存储', async () => {
    const pending = deferred()
    vi.spyOn(teacherIntentApi, 'extract').mockReturnValueOnce(pending.promise)
    const store = useIntentStore()
    store.initialize('project-a')
    const request = store.sendMessage('A 项目意图')
    store.initialize('project-b')
    const sessionB = store.sessionId

    pending.resolve({ intent_summary: { topic: '错误写入' }, session_status: 'confirming', can_confirm: true })
    expect(await request).toBe(false)
    expect(store.projectId).toBe('project-b')
    expect(store.sessionId).toBe(sessionB)
    expect(store.intentSummary).toBeNull()
    expect(store.messages).toHaveLength(1)
    expect(JSON.parse(window.localStorage.getItem(intentStorageKey('fuww_s1_conversation', 'project-b'))).sessionId).toBe(sessionB)
  })

  it('重置后丢弃旧确认响应且不覆盖新 loading 状态', async () => {
    const pending = deferred()
    vi.spyOn(teacherIntentApi, 'confirm').mockReturnValueOnce(pending.promise)
    const store = useIntentStore()
    store.initialize('project-a')
    store.canConfirm = true
    const request = store.confirmIntent()
    store.reset()
    const resetSession = store.sessionId
    pending.resolve({ confirmed: true, intent_id: 'stale-intent' })

    expect(await request).toBe(false)
    expect(store.sessionId).toBe(resetSession)
    expect(store.intentId).toBe('')
    expect(store.isConfirming).toBe(false)
  })

  it('分析修订期间阻止确认旧意图', async () => {
    const confirm = vi.spyOn(teacherIntentApi, 'confirm')
    confirm.mockClear()
    const store = useIntentStore()
    store.initialize('project-a')
    store.canConfirm = true
    store.isAnalyzing = true

    expect(await store.confirmIntent()).toBe(false)
    expect(confirm).not.toHaveBeenCalled()
  })

  it('确认后的意图可经 buildIntentRevisionMessage 回流到 Mock 提取', async () => {
    const store = useIntentStore()
    store.initialize()
    await store.sendMessage(buildIntentRevisionMessage({
      topic: '排序算法',
      duration_minutes: 45,
      target_student: '大一学生',
      style: '案例驱动',
      knowledge_points: '冒泡排序、快速排序'
    }))
    expect(store.intentSummary?.topic).toBe('排序算法')
    expect(store.intentSummary?.knowledge_points).toContain('快速排序')
    expect(store.completionPct).toBe(100)
  })
})
