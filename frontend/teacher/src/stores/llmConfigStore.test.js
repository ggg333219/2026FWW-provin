import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useLlmConfigStore } from './llmConfigStore'

function createStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key)
  }
}

const fullConfig = {
  baseUrl: 'https://api.example.com/v1',
  apiKey: 'unit-test-key-1234567890',
  model: 'unit-model'
}

beforeEach(() => {
  globalThis.window = { localStorage: createStorage() }
  setActivePinia(createPinia())
})

describe('使用者自带模型配置', () => {
  it('默认未接入，且不下发任何配置字段', () => {
    const store = useLlmConfigStore()
    store.load()
    expect(store.isConfigured).toBe(false)
    expect(store.requestConfig()).toEqual({})
    expect(store.maskedKey).toBe('')
  })

  it('保存三项后按白名单下发，并去掉 base_url 末尾斜杠', () => {
    const store = useLlmConfigStore()
    store.save({
      baseUrl: ' https://api.example.com/v1/ ',
      apiKey: ' unit-test-key-1234567890 ',
      model: ' unit-model '
    })
    expect(store.isConfigured).toBe(true)
    expect(store.requestConfig()).toEqual({
      api_key: 'unit-test-key-1234567890',
      base_url: 'https://api.example.com/v1',
      model: 'unit-model'
    })
  })

  it('掩码不暴露完整密钥', () => {
    const store = useLlmConfigStore()
    store.save(fullConfig)
    expect(store.maskedKey).toContain('••••')
    expect(store.maskedKey).not.toContain('1234567890')
    expect(store.maskedKey.length).toBeLessThan(fullConfig.apiKey.length)
  })

  it('缺任一项时视为未接入，不下发配置', () => {
    const store = useLlmConfigStore()
    store.save({ ...fullConfig, model: '' })
    expect(store.isConfigured).toBe(false)
    expect(store.requestConfig()).toEqual({})
  })

  it('清除后内存态与本地存储都被清空', () => {
    const store = useLlmConfigStore()
    store.save(fullConfig)
    expect(window.localStorage.getItem('fuww_llm_config')).not.toBe(null)
    store.clear()
    expect(store.isConfigured).toBe(false)
    expect(store.requestConfig()).toEqual({})
    expect(window.localStorage.getItem('fuww_llm_config')).toBe(null)
  })

  it('新会话能从本地存储恢复配置', () => {
    const first = useLlmConfigStore()
    first.save(fullConfig)
    setActivePinia(createPinia())
    const second = useLlmConfigStore()
    second.load()
    expect(second.isConfigured).toBe(true)
    expect(second.requestConfig()).toEqual({
      api_key: fullConfig.apiKey,
      base_url: fullConfig.baseUrl,
      model: fullConfig.model
    })
  })

  it('本地存储里是脏数据时安全降级为未接入', () => {
    window.localStorage.setItem('fuww_llm_config', '{not-json')
    setActivePinia(createPinia())
    const store = useLlmConfigStore()
    expect(() => store.load()).not.toThrow()
    expect(store.isConfigured).toBe(false)
    expect(store.requestConfig()).toEqual({})
  })
})
