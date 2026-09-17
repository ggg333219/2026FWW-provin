import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { buildIntentRevisionMessage, useIntentStore } from './intentStore'

function createStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key)
  }
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
    expect(window.localStorage.getItem('fuww_workflow_intent_id')).toBe(store.intentId)
    expect(window.localStorage.getItem('fuww_s1_confirmed_intent')).toBeTruthy()
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
