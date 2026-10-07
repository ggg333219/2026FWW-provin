// API_BASE：教师端 Go 后端（cmd/teacher）。
// 解析优先级：
//   1. window.__API_BASE__（部署时可在 index.html 注入，可设为 '' 表示同源）
//   2. VITE_API_BASE（构建注入；⚠️ 空字符串是有意为之 = 同源相对路径，生产同源部署常用，
//      不得用 || 真值判断，否则会被 falsy 回退成 localhost——公网部署曾因此全站 API 打到用户本机）
//   3. 默认 http://localhost:8082（本地裸跑 vite dev 场景）
const ENV_API_BASE = import.meta.env.VITE_API_BASE

function resolveApiBase() {
  if (typeof window !== 'undefined' && typeof window.__API_BASE__ === 'string') {
    return window.__API_BASE__
  }
  if (typeof ENV_API_BASE === 'string') {
    return ENV_API_BASE
  }
  return 'http://localhost:8082'
}

export const API_BASE = resolveApiBase()

// AI_API_BASE：AI 引擎直连地址（S1 意图面板等直连引擎）。
// 同样支持空字符串 = 同源（nginx /ai/ 前缀反代）。
const ENV_AI_BASE = import.meta.env.VITE_AI_API_BASE

function resolveAiBase() {
  if (typeof window !== 'undefined' && typeof window.__AI_API_BASE__ === 'string') {
    return window.__AI_API_BASE__
  }
  if (typeof ENV_AI_BASE === 'string') {
    return ENV_AI_BASE
  }
  return 'http://localhost:8000'
}

export const AI_API_BASE = resolveAiBase()
// RAG_API_BASE：知识库 RAG 直连 AI Engine（S2 mock 不走 Go Backend）。
export const RAG_API_BASE = AI_API_BASE
