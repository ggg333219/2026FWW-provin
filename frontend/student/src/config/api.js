export const API_BASE = (typeof window !== 'undefined' && window.__API_BASE__) || process.env.VUE_APP_API_BASE || 'http://172.22.160.1:8081'
export const AI_API_BASE = process.env.VUE_APP_AI_API_BASE || 'http://localhost:8000'
