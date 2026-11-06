import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { intentStorageKey, useIntentStore } from './intentStore'
import { useLlmConfigStore } from './llmConfigStore'
import { teacherIntentApi } from '../services/v1/intentApi'

function createStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key)
  }
}

const okResult = () => ({
  intent_summary: { topic: '排序算法', duration_minutes: 45, knowledge_points: ['冒泡排序'] },
  session_status: 'collecting',
  completion_pct: 100,
  turn_count: 1,
  max_turns: 8,
  can_confirm: true,
  response: '好的',
  followup_questions: [],
  human_summary: '',
  engine: 'LLMIntentEngine',
  used_fallback: false,
  fallback_reason: null,
  model_source: 'real_model',
  normalization_notes: []
})

beforeEach(() => {
  globalThis.window = { localStorage: createStorage() }
  globalThis.fetch = () => Promise.reject(new Error('backend unreachable'))
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('S1 请求携带使用者自带模型配置', () => {
  it('未配置时不下发任何额外字段（旧请求体形状不变）', async () => {
    const spy = vi.spyOn(teacherIntentApi, 'extract').mockResolvedValueOnce(okResult())
    const store = useIntentStore()
    store.initialize()

    await store.sendMessage('请做一节排序课件')

    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy.mock.calls[0][0].llmConfig).toEqual({})
  })

  it('已配置时随请求下发三项白名单字段', async () => {
    const llm = useLlmConfigStore()
    llm.save({
      baseUrl: 'https://api.example.com/v1',
      apiKey: 'unit-test-key-abcdef',
      model: 'unit-model'
    })
    const spy = vi.spyOn(teacherIntentApi, 'extract').mockResolvedValueOnce(okResult())
    const store = useIntentStore()
    store.initialize()

    await store.sendMessage('请做一节排序课件')

    expect(spy.mock.calls[0][0].llmConfig).toEqual({
      api_key: 'unit-test-key-abcdef',
      base_url: 'https://api.example.com/v1',
      model: 'unit-model'
    })
  })

  it('密钥不会被写进 S1 会话的持久化状态', async () => {
    const llm = useLlmConfigStore()
    llm.save({
      baseUrl: 'https://api.example.com/v1',
      apiKey: 'unit-test-key-abcdef',
      model: 'unit-model'
    })
    vi.spyOn(teacherIntentApi, 'extract').mockResolvedValueOnce(okResult())
    const store = useIntentStore()
    store.initialize()

    await store.sendMessage('请做一节排序课件')

    const saved = window.localStorage.getItem(intentStorageKey('fuww_s1_conversation', store.projectId))
    expect(saved || '').not.toContain('unit-test-key-abcdef')
  })
})
