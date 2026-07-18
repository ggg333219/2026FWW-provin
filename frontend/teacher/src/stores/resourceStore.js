import { defineStore } from 'pinia'

const STORAGE_KEYS = {
  search: 'teacher:resource:lastSearchConfig',
  cache: 'teacher:resource:recommendationCache'
}

const DEFAULT_SEARCH_CONFIG = {
  keyword: '',
  stage: '',
  subject: '',
  type: '',
  difficulty: '',
  duration: '',
  lang: '',
  budget: '',
  source: ''
}

function safeParse(raw, fallback) {
  if (!raw) return fallback
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : fallback
  } catch {
    return fallback
  }
}

export const useResourceStore = defineStore('resource', {
  state: () => ({
    lastSearchConfig: { ...DEFAULT_SEARCH_CONFIG },
    recommendationCache: {
      key: '',
      items: [],
      total: 0,
      page: 1,
      pageSize: 10,
      hasMore: false,
      updatedAt: 0
    },
    initialized: false
  }),
  actions: {
    hydrate() {
      if (this.initialized) return

      const savedSearch = safeParse(window.localStorage.getItem(STORAGE_KEYS.search), DEFAULT_SEARCH_CONFIG)
      const savedCache = safeParse(window.localStorage.getItem(STORAGE_KEYS.cache), null)

      this.lastSearchConfig = { ...DEFAULT_SEARCH_CONFIG, ...savedSearch }
      if (savedCache && typeof savedCache === 'object') {
        this.recommendationCache = {
          key: String(savedCache.key || ''),
          items: Array.isArray(savedCache.items) ? savedCache.items : [],
          total: Number(savedCache.total || 0),
          page: Number(savedCache.page || 1),
          pageSize: Number(savedCache.pageSize || 10),
          hasMore: Boolean(savedCache.hasMore),
          updatedAt: Number(savedCache.updatedAt || 0)
        }
      }
      this.initialized = true
    },

    setLastSearchConfig(config) {
      this.lastSearchConfig = { ...DEFAULT_SEARCH_CONFIG, ...(config || {}) }
      window.localStorage.setItem(STORAGE_KEYS.search, JSON.stringify(this.lastSearchConfig))
    },

    setRecommendationCache(payload) {
      this.recommendationCache = {
        key: String(payload?.key || ''),
        items: Array.isArray(payload?.items) ? payload.items : [],
        total: Number(payload?.total || 0),
        page: Number(payload?.page || 1),
        pageSize: Number(payload?.pageSize || 10),
        hasMore: Boolean(payload?.hasMore),
        updatedAt: Date.now()
      }
      window.localStorage.setItem(STORAGE_KEYS.cache, JSON.stringify(this.recommendationCache))
    },

    clearRecommendationCache() {
      this.recommendationCache = {
        key: '',
        items: [],
        total: 0,
        page: 1,
        pageSize: 10,
        hasMore: false,
        updatedAt: 0
      }
      window.localStorage.removeItem(STORAGE_KEYS.cache)
    },

    buildCacheKey(config) {
      const normalized = { ...DEFAULT_SEARCH_CONFIG, ...(config || {}) }
      return JSON.stringify(normalized)
    }
  }
})
