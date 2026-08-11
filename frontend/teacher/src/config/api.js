// API_BASE：教师端 Go 后端（cmd/teacher，端口 8082）。
// 优先级：window.__API_BASE__（构建期注入）> VITE_API_BASE（.env）> 默认 localhost:8082。
export const API_BASE = (typeof window !== 'undefined' && window.__API_BASE__) || import.meta.env.VITE_API_BASE || 'http://localhost:8082'
// AI_API_BASE：AI 引擎直连地址（S1 意图面板等仍直连引擎）。
export const AI_API_BASE = import.meta.env.VITE_AI_API_BASE || 'http://localhost:8000'
