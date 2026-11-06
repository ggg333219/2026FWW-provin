import { defineStore } from 'pinia'

// 使用者自带的第三方模型配置。
// 本产品不提供模型服务，因此这里**不预置任何厂商地址、模型名或密钥**。
// 配置只保存在当前浏览器的 localStorage，随每次 S1 请求发给服务端用于本次调用；
// 服务端仅在单次请求的内存中使用，不写入代码仓库、不写入任何配置文件。
const LLM_CONFIG_KEY = 'fuww_llm_config'
const CONFIG_FIELDS = ['baseUrl', 'apiKey', 'model']

const normalizeText = (value) => String(value ?? '').trim()

const readStorage = () => {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(LLM_CONFIG_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

const writeStorage = (value) => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(LLM_CONFIG_KEY, JSON.stringify(value))
  } catch {
    // 隐私模式 / 配额不足时保留内存态即可，不阻断本次会话使用。
  }
}

const removeStorage = () => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(LLM_CONFIG_KEY)
  } catch {
    // noop
  }
}

export const useLlmConfigStore = defineStore('llmConfig', {
  state: () => ({
    baseUrl: '',
    apiKey: '',
    model: '',
    loaded: false
  }),

  getters: {
    // 三项齐全才算"已接入"：缺 base_url 或 model 时不下发，避免拿默认端点误调用。
    isConfigured: (state) => Boolean(
      state.baseUrl.trim() && state.apiKey.trim() && state.model.trim()
    ),
    // 只展示掩码，避免设置页把完整密钥渲染到界面上。
    maskedKey: (state) => {
      const key = state.apiKey.trim()
      if (!key) return ''
      if (key.length <= 8) return '••••••••'
      return `${key.slice(0, 3)}••••${key.slice(-4)}`
    }
  },

  actions: {
    load() {
      if (this.loaded) return
      const saved = readStorage()
      if (saved) {
        for (const field of CONFIG_FIELDS) {
          this[field] = normalizeText(saved[field])
        }
      }
      this.loaded = true
    },

    save({ baseUrl = '', apiKey = '', model = '' } = {}) {
      this.baseUrl = normalizeText(baseUrl)
      this.apiKey = normalizeText(apiKey)
      this.model = normalizeText(model)
      this.loaded = true
      writeStorage({
        baseUrl: this.baseUrl,
        apiKey: this.apiKey,
        model: this.model
      })
    },

    clear() {
      for (const field of CONFIG_FIELDS) this[field] = ''
      this.loaded = true
      removeStorage()
    },

    // 只返回白名单字段；未配置时返回空对象，旧请求体形状完全不变。
    // 绝不把整个 store（含 loaded 等内部字段）拼进请求。
    requestConfig() {
      if (!this.isConfigured) return {}
      return {
        api_key: this.apiKey.trim(),
        base_url: this.baseUrl.trim().replace(/\/+$/, ''),
        model: this.model.trim()
      }
    }
  }
})
