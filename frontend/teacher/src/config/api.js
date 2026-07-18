export const API_BASE = (typeof window !== 'undefined' && window.__API_BASE__) || import.meta.env.VITE_API_BASE || 'http://172.22.160.1:8082'
export const AI_API_BASE = import.meta.env.VITE_AI_API_BASE || 'http://localhost:8000'
