<template>
  <div class="chat-shell" :class="{ 'sidebar-collapsed': sessionSidebarCollapsed }">
    <aside class="session-sidebar" :class="{ collapsed: sessionSidebarCollapsed }">
      <button
        class="session-toggle-btn"
        :class="{ compact: sessionSidebarCollapsed }"
        type="button"
        @click="toggleSessionSidebar"
        :aria-expanded="sessionSidebarCollapsed ? 'false' : 'true'"
        :title="sessionSidebarCollapsed ? '展开会话列表' : '收起会话列表'"
      >
        <span class="session-toggle-icon" aria-hidden="true">{{ sessionSidebarCollapsed ? '»' : '«' }}</span>
        <span class="session-toggle-text">{{ sessionSidebarCollapsed ? '展开会话' : '收起会话' }}</span>
      </button>

      <template v-if="!sessionSidebarCollapsed">
      <button class="new-session-btn" type="button" @click="createNewSession" :disabled="askLoading">
        + 新建对话
      </button>

      <div class="session-list" role="listbox" aria-label="会话列表">
        <div
          v-for="session in sessions"
          :key="session.id"
          class="session-item"
          :class="{ active: session.id === activeSessionId }"
          @click="switchSession(session.id)"
          @contextmenu.prevent="deleteSession(session.id)"
        >
          <div class="session-item-head">
            <strong class="session-title" :title="session.title">{{ session.title }}</strong>
            <button
              class="session-delete-btn"
              type="button"
              title="删除对话"
              aria-label="删除对话"
              @click.stop="deleteSession(session.id)"
            >
              ×
            </button>
          </div>
          <p class="session-preview" :title="session.preview || '暂无消息'">{{ session.preview || '暂无消息' }}</p>
          <div class="session-meta">
            <span>{{ sessionUserTurnCount(session) }} 条对话</span>
            <span>{{ formatDateTime(session.updatedAt) }}</span>
          </div>
        </div>
      </div>
      </template>

      <button
        v-else
        class="new-session-mini-btn"
        type="button"
        @click="createNewSession"
        :disabled="askLoading"
        title="新建对话"
      >
        +
      </button>
    </aside>

    <section class="chat-main">
      <header class="chat-header">
        <div class="chat-header-left">
          <h3>{{ activeSession?.title || '新的聊天' }}</h3>
          <p>共 {{ sessionUserTurnCount(activeSession) }} 条对话</p>
        </div>
        <div class="chat-header-actions">
          <button class="ghost-btn" type="button" @click="clearActiveSession" :disabled="askLoading || !activeMessages.length">
            清空对话
          </button>
          <button class="ghost-btn" type="button" @click="regenerateLast" :disabled="askLoading || !hasUserMessage">
            重新生成
          </button>
        </div>
      </header>

      <main ref="threadRef" class="message-thread" aria-live="polite">
        <div v-if="!activeMessages.length" class="thread-empty">
          <p>开始你的第一条提问，例如：这一步推导为什么成立？</p>
        </div>

        <article
          v-for="message in activeMessages"
          :key="message.id"
          class="message-row"
          :class="message.role"
        >
          <div class="message-avatar" :class="message.role === 'assistant' ? 'assistant-avatar' : 'user-avatar'">
            {{ message.role === 'assistant' ? 'AI' : '我' }}
          </div>

          <div class="message-bubble" :class="{ streaming: isStreamingMessage(message), system: message.system }">
            <div class="message-meta-row">
              <span class="message-role">{{ messageRoleLabel(message) }}</span>
              <div class="message-tools">
                <template v-if="message.role === 'assistant' && !message.system && latestAnswerMeta.understandingLevel">
                  <span class="understanding-level-tag" :class="'level-' + latestAnswerMeta.understandingLevel">
                    {{ levelLabel(latestAnswerMeta.understandingLevel) }}
                  </span>
                  <span v-if="latestAnswerMeta.resumeSec !== undefined && latestAnswerMeta.resumeSec !== null"
                    class="resume-badge">续接 {{ latestAnswerMeta.resumePage || '?' }}页 {{ latestAnswerMeta.resumeSec }}s</span>
                </template>
                <button
                  v-if="message.role === 'assistant' && !message.system && message.content"
                  class="inline-copy-btn"
                  type="button"
                  @click="copyText(message.content, '消息已复制')"
                >
                  复制
                </button>
                <span class="message-time">{{ formatDateTime(message.createdAt) }}</span>
              </div>
            </div>

            <div
              v-if="message.role === 'assistant'"
              class="assistant-body"
              :class="{ system: message.system, 'has-audio-action': !message.system && message.content }"
              @click="handleMarkdownAction"
            >
              <div
                v-if="message.content"
                class="markdown-content"
                v-html="renderAssistantMessage(message.content)"
              ></div>
              <div v-else class="thinking-inline">
                <span>正在思考...</span>
                <i></i><i></i><i></i>
              </div>
              <div v-if="isStreamingMessage(message) && !message.system" class="streaming-state">
                <span class="typing-dot"></span>
                正在思考...
              </div>
              <div v-if="!message.system && message.content" class="assistant-audio-action">
                <button
                  class="assistant-audio-btn"
                  type="button"
                  :disabled="isStreamingMessage(message)"
                  @click.stop="emitPlayAnswerAudio(message)"
                >
                  🔊 播放语音
                </button>
              </div>
            </div>

            <div v-else class="user-text">{{ message.content }}</div>
          </div>
        </article>
      </main>

      <div class="assistant-tool-row">
        <button
          class="preset-toggle-btn tool-btn"
          type="button"
          :disabled="askLoading"
          :aria-expanded="presetExpanded ? 'true' : 'false'"
          aria-controls="ask-preset-panel"
          @click="togglePresetPanel"
        >
          <span>💡 快捷提问</span>
          <span class="preset-toggle-arrow">{{ presetExpanded ? '▲' : '▼' }}</span>
        </button>

        <button
          class="mode-toggle-btn"
          type="button"
          :class="{ active: contextBinding }"
          :aria-pressed="contextBinding ? 'true' : 'false'"
          :disabled="askLoading"
          @click="toggleContextBinding"
        >
          上下文绑定
        </button>

        <button
          class="mode-toggle-btn"
          type="button"
          :class="{ active: deepReasoning }"
          :aria-pressed="deepReasoning ? 'true' : 'false'"
          :disabled="askLoading"
          @click="toggleDeepReasoning"
        >
          深度推理
        </button>

        <button
          class="mode-toggle-btn"
          type="button"
          :class="{ active: webSearch }"
          :aria-pressed="webSearch ? 'true' : 'false'"
          :disabled="askLoading"
          @click="toggleWebSearch"
        >
          联网搜索
        </button>

        <button
          class="mode-toggle-btn"
          type="button"
          :class="{ active: autoSpeakAnswer }"
          :aria-pressed="autoSpeakAnswer ? 'true' : 'false'"
          :disabled="askLoading"
          @click="toggleAutoSpeakAnswer"
        >
          回答播报
        </button>

        <button
          class="mode-toggle-btn"
          type="button"
          :class="{ active: presetLectureScript }"
          :aria-pressed="presetLectureScript ? 'true' : 'false'"
          :disabled="askLoading"
          @click="togglePresetLectureScript"
        >
          开播讲稿
        </button>
      </div>

      <div class="preset-toggle-shell">
        <div v-if="presetExpanded" id="ask-preset-panel" class="preset-panel">
          <div class="preset-chip-list">
            <button
              v-for="preset in promptPresets"
              :key="preset.id"
              class="preset-chip"
              type="button"
              @click="applyPreset(preset.label)"
              :disabled="askLoading"
              :title="preset.desc"
            >
              {{ preset.label }}
            </button>
          </div>
        </div>
      </div>

      <footer class="composer">
        <el-input
          ref="composerRef"
          :model-value="question"
          class="composer-input"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="输入你的问题，Enter 发送，Shift + Enter 换行"
          @update:model-value="$emit('update:question', $event)"
          @keydown="handleInputKeydown"
        />

        <div class="composer-actions">
          <span class="compose-tip">{{ askLoading || streamTypingActive ? 'AI 正在回答中' : 'Enter 发送，Shift + Enter 换行' }}</span>
          <el-button
            type="primary"
            class="send-btn"
            :disabled="sendDisabled"
            :loading="askLoading"
            @click="handleSend"
          >
            发送
          </el-button>
        </div>

        <div class="explain-profile-row composer-profile-row">
          <div class="profile-group">
            <span class="profile-label">讲解模式</span>
            <div class="profile-options">
              <button
                v-for="option in explainModeOptions"
                :key="option.value"
                class="profile-option-btn"
                type="button"
                :class="{ active: explainMode === option.value }"
                :disabled="askLoading"
                @click="setExplainMode(option.value)"
              >
                {{ option.label }}
              </button>
            </div>
          </div>

          <div class="profile-group">
            <span class="profile-label">标答风格</span>
            <div class="profile-options">
              <button
                v-for="option in explainStyleOptions"
                :key="option.value"
                class="profile-option-btn"
                type="button"
                :class="{ active: explainStyle === option.value }"
                :disabled="askLoading"
                @click="setExplainStyle(option.value)"
              >
                {{ option.label }}
              </button>
            </div>
          </div>
        </div>
      </footer>
    </section>
  </div>
</template>

<script setup>
/* eslint-disable no-undef */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import markdownItKatex from 'markdown-it-katex'

const STORAGE_KEY = 'fuww_student_qa_sessions_v2'
const ACTIVE_STORAGE_KEY = 'fuww_student_qa_active_session_v2'
const SESSION_SIDEBAR_COLLAPSED_KEY = 'fuww_student_qa_session_sidebar_collapsed_v1'
const DEFAULT_SESSION_TITLE = '新的聊天'
const MAX_SESSIONS = 40
const MAX_MESSAGES = 300

const promptPresets = [
  { id: 'explain', label: '📖 解释知识点', desc: '深入理解核心概念' },
  { id: 'practice', label: '📝 3道练习题', desc: '巩固学习成果' },
  { id: 'summary', label: '📋 总结要点', desc: '提炼关键结论' },
  { id: 'example', label: '💡 举例说明', desc: '实例化理解' },
  { id: 'compare', label: '🔍 对比分析', desc: '区分相似概念' }
]

const explainModeOptions = [
  { value: 'deep', label: '深度讲解' },
  { value: 'assist', label: '辅助理解' }
]

const explainStyleOptions = [
  { value: 'gentle', label: '温柔活泼' },
  { value: 'rigorous', label: '客观严谨' }
]

const keywordMap = {
  js: ['const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while', 'new', 'class', 'import', 'from', 'export', 'async', 'await'],
  ts: ['const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while', 'new', 'class', 'import', 'from', 'export', 'type', 'interface', 'extends', 'implements', 'async', 'await'],
  vue: ['const', 'let', 'ref', 'computed', 'watch', 'onMounted', 'defineProps', 'defineEmits', 'return', 'if', 'else'],
  python: ['def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'import', 'from', 'as', 'try', 'except', 'with', 'lambda'],
  go: ['func', 'package', 'import', 'return', 'if', 'else', 'for', 'range', 'type', 'struct', 'interface', 'map', 'var', 'const', 'go', 'defer']
}

const props = defineProps({
  question: {
    type: String,
    default: ''
  },
  askLoading: {
    type: Boolean,
    default: false
  },
  aiReply: {
    type: String,
    default: ''
  },
  streamTypingActive: {
    type: Boolean,
    default: false
  },
  qaHistory: {
    type: Array,
    default: () => []
  },
  latestAnswerMeta: {
    type: Object,
    default: () => ({})
  },
  summaryMode: {
    type: String,
    default: 'quick'
  },
  mergedSummary: {
    type: String,
    default: ''
  },
  contextBinding: {
    type: Boolean,
    default: true
  },
  deepReasoning: {
    type: Boolean,
    default: false
  },
  webSearch: {
    type: Boolean,
    default: false
  },
  explainMode: {
    type: String,
    default: 'deep'
  },
  explainStyle: {
    type: String,
    default: 'rigorous'
  },
  autoSpeakAnswer: {
    type: Boolean,
    default: true
  },
  presetLectureScript: {
    type: Boolean,
    default: true
  },
  canAsk: {
    type: Boolean,
    default: true
  },
  externalAction: {
    type: Object,
    default: null
  }
})

const emit = defineEmits([
  'update:question',
  'open-upload',
  'send-question',
  'update:summaryMode',
  'update:context-binding',
  'update:deep-reasoning',
  'update:web-search',
  'update:explain-mode',
  'update:explain-style',
  'update:auto-speak-answer',
  'update:preset-lecture-script',
  'play-answer-audio',
  'generate-summary',
  'use-summary',
  'clear-draft'
])

const threadRef = ref(null)
const composerRef = ref(null)
const sessions = ref([])
const activeSessionId = ref('')
const pendingSessionId = ref('')
const pendingAssistantMessageId = ref('')
const presetExpanded = ref(false)
const sessionSidebarCollapsed = ref(true)

let persistTimer = null

const markdownEngine = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  highlight: (code, langRaw) => {
    const lang = normalizeLanguage(langRaw)
    const encodedCode = encodeURIComponent(String(code || ''))
    const highlighted = highlightCode(String(code || ''), lang)
    return `<div class="code-shell"><div class="code-shell-head"><span class="code-lang">${escapeHtml(lang || 'text')}</span><button type="button" class="code-copy-btn" data-copy-code="${encodedCode}">复制代码</button></div><pre><code class="hl-code language-${escapeHtml(lang || 'text')}">${highlighted}</code></pre></div>`
  }
})

markdownEngine.use(markdownItKatex, {
  throwOnError: false,
  strict: 'ignore',
  output: 'htmlAndMathml'
})

const activeSession = computed(() => sessions.value.find((item) => item.id === activeSessionId.value) || null)
const activeMessages = computed(() => activeSession.value?.messages || [])

const sendDisabled = computed(() => {
  const hasText = String(props.question || '').trim().length > 0
  return !hasText || props.askLoading || props.streamTypingActive
})

const hasUserMessage = computed(() => activeMessages.value.some((item) => item.role === 'user' && String(item.content || '').trim()))

function nowTs() {
  return Date.now()
}

function createId(prefix = 'id') {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}_${nowTs()}`
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function escapeRegExp(text) {
  return String(text || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function normalizeLanguage(langRaw) {
  const lang = String(langRaw || '').trim().toLowerCase()
  if (!lang) return 'text'
  if (lang.startsWith('javascript')) return 'js'
  if (lang.startsWith('typescript')) return 'ts'
  if (lang.startsWith('py')) return 'python'
  return lang
}

function highlightCode(sourceText, lang) {
  const source = String(sourceText || '')
  if (!source) return ''

  const placeholders = []
  const injectToken = (text, tokenClass) => {
    const token = `__TOK_${placeholders.length}__`
    placeholders.push({ text, tokenClass })
    return token
  }

  let staged = source
  staged = staged.replace(/("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)/g, (match) => injectToken(match, 'tok-string'))
  staged = staged.replace(/(\/\/[^\n]*|\/\*[\s\S]*?\*\/|#[^\n]*)/g, (match) => injectToken(match, 'tok-comment'))

  let escaped = escapeHtml(staged)
  const keywords = keywordMap[lang] || []
  if (keywords.length) {
    const pattern = new RegExp(`\\b(${keywords.map(escapeRegExp).join('|')})\\b`, 'g')
    escaped = escaped.replace(pattern, '<span class="tok-key">$1</span>')
  }

  escaped = escaped.replace(/\b(true|false|null|undefined)\b/g, '<span class="tok-bool">$1</span>')
  escaped = escaped.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="tok-num">$1</span>')
  escaped = escaped.replace(/__TOK_(\d+)__/g, (_, idx) => {
    const token = placeholders[Number(idx)]
    if (!token) return ''
    return `<span class="${token.tokenClass}">${escapeHtml(token.text)}</span>`
  })

  return escaped
}

function normalizeMessage(message, roleFallback = 'assistant') {
  if (!message || typeof message !== 'object') return null
  const role = message.role === 'user' ? 'user' : roleFallback
  return {
    id: String(message.id || createId('msg')),
    role,
    content: String(message.content || ''),
    createdAt: Number(message.createdAt) || nowTs(),
    system: Boolean(message.system)
  }
}

function deriveSessionTitle(messages, fallbackTitle = '') {
  const firstUser = messages.find((item) => item.role === 'user' && String(item.content || '').trim())
  if (firstUser) {
    const source = String(firstUser.content || '').trim()
    return source.length > 18 ? `${source.slice(0, 18)}...` : source
  }
  const fallback = String(fallbackTitle || '').trim()
  return fallback || DEFAULT_SESSION_TITLE
}

function derivePreview(messages) {
  const last = [...messages].reverse().find((item) => String(item.content || '').trim())
  if (!last) return ''
  const text = String(last.content || '').replace(/\s+/g, ' ').trim()
  return text.length > 28 ? `${text.slice(0, 28)}...` : text
}

function createSession() {
  const createdAt = nowTs()
  return {
    id: createId('session'),
    title: DEFAULT_SESSION_TITLE,
    preview: '',
    createdAt,
    updatedAt: createdAt,
    messages: []
  }
}

function normalizeSession(raw) {
  if (!raw || typeof raw !== 'object') return null
  const messages = Array.isArray(raw.messages)
    ? raw.messages.map((item) => normalizeMessage(item, item?.role === 'user' ? 'user' : 'assistant')).filter(Boolean)
    : []
  const createdAt = Number(raw.createdAt) || nowTs()
  const updatedAt = Number(raw.updatedAt) || createdAt
  return {
    id: String(raw.id || createId('session')),
    title: deriveSessionTitle(messages, String(raw.title || '')),
    preview: derivePreview(messages),
    createdAt,
    updatedAt,
    messages: messages.slice(-MAX_MESSAGES)
  }
}

function schedulePersist() {
  if (typeof window === 'undefined') return
  if (persistTimer) {
    window.clearTimeout(persistTimer)
  }
  persistTimer = window.setTimeout(() => {
    persistTimer = null
    persistSessions()
  }, 160)
}

function persistSessions() {
  if (typeof window === 'undefined') return
  try {
    const payload = sessions.value.slice(0, MAX_SESSIONS).map((session) => ({
      id: session.id,
      title: session.title,
      preview: session.preview,
      createdAt: session.createdAt,
      updatedAt: session.updatedAt,
      messages: session.messages.map((msg) => ({
        id: msg.id,
        role: msg.role,
        content: msg.content,
        createdAt: msg.createdAt,
        system: Boolean(msg.system)
      }))
    }))
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    window.localStorage.setItem(ACTIVE_STORAGE_KEY, activeSessionId.value)
  } catch (error) {
    // ignore storage quota or serialization issues
  }
}

function loadSessions() {
  if (typeof window === 'undefined') {
    sessions.value = [createSession()]
    activeSessionId.value = sessions.value[0].id
    return
  }

  let parsed = null
  try {
    parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '[]')
  } catch (error) {
    parsed = []
  }

  const restored = Array.isArray(parsed)
    ? parsed.map((item) => normalizeSession(item)).filter(Boolean)
    : []

  sessions.value = restored
    .sort((a, b) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0))
    .slice(0, MAX_SESSIONS)

  if (!sessions.value.length) {
    sessions.value = [createSession()]
  }

  const storedActive = String(window.localStorage.getItem(ACTIVE_STORAGE_KEY) || '')
  const exists = sessions.value.some((session) => session.id === storedActive)
  activeSessionId.value = exists ? storedActive : sessions.value[0].id
}

function ensureActiveSession() {
  if (sessions.value.length === 0) {
    const session = createSession()
    sessions.value = [session]
    activeSessionId.value = session.id
    return session
  }
  const found = sessions.value.find((item) => item.id === activeSessionId.value)
  if (found) return found
  activeSessionId.value = sessions.value[0].id
  return sessions.value[0]
}

function levelLabel(level) {
  if (level === 'none') return '❌ 未理解'
  if (level === 'partial') return '⚠️ 部分理解'
  if (level === 'full') return '✅ 已理解'
  return level || ''
}

function sessionUserTurnCount(session) {
  if (!session || !Array.isArray(session.messages)) return 0
  return session.messages.filter((item) => item.role === 'user').length
}

function formatDateTime(timestamp) {
  const time = Number(timestamp) || nowTs()
  const date = new Date(time)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}`
}

function moveSessionToTop(sessionId) {
  const idx = sessions.value.findIndex((item) => item.id === sessionId)
  if (idx <= 0) return
  const [target] = sessions.value.splice(idx, 1)
  sessions.value.unshift(target)
}

function syncSessionMeta(session) {
  if (!session) return
  session.updatedAt = nowTs()
  session.title = deriveSessionTitle(session.messages, session.title)
  session.preview = derivePreview(session.messages)
}

function appendMessagePair(sessionId, userText) {
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) return null

  const userMessage = {
    id: createId('msg'),
    role: 'user',
    content: String(userText || ''),
    createdAt: nowTs()
  }
  const assistantMessage = {
    id: createId('msg'),
    role: 'assistant',
    content: '',
    createdAt: nowTs()
  }

  session.messages.push(userMessage, assistantMessage)
  if (session.messages.length > MAX_MESSAGES) {
    session.messages = session.messages.slice(-MAX_MESSAGES)
  }
  syncSessionMeta(session)
  moveSessionToTop(sessionId)
  return assistantMessage.id
}

function updateAssistantMessage(sessionId, messageId, text) {
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) return
  const message = session.messages.find((item) => item.id === messageId)
  if (!message) return

  message.content = String(text || '')
  syncSessionMeta(session)
  moveSessionToTop(sessionId)
}

function appendSystemMessage(text) {
  const content = String(text || '').trim()
  if (!content) return
  const session = ensureActiveSession()
  session.messages.push({
    id: createId('msg'),
    role: 'assistant',
    content: `系统提示：${content}`,
    createdAt: nowTs(),
    system: true
  })
  if (session.messages.length > MAX_MESSAGES) {
    session.messages = session.messages.slice(-MAX_MESSAGES)
  }
  syncSessionMeta(session)
  moveSessionToTop(session.id)
  nextTick(() => scrollToBottom(false))
}

function messageRoleLabel(message) {
  if (message?.system) return '系统'
  return message?.role === 'assistant' ? 'AI 助教' : '学生'
}

function createNewSession() {
  if (props.askLoading) return
  const session = createSession()
  sessions.value.unshift(session)
  activeSessionId.value = session.id
  pendingSessionId.value = ''
  pendingAssistantMessageId.value = ''
  emit('clear-draft')
  emit('update:question', '')
  nextTick(() => {
    scrollToBottom(false)
    focusComposer()
  })
}

function toggleSessionSidebar() {
  sessionSidebarCollapsed.value = !sessionSidebarCollapsed.value
}

function switchSession(sessionId) {
  if (!sessionId || sessionId === activeSessionId.value) return
  const exists = sessions.value.some((item) => item.id === sessionId)
  if (!exists) return
  activeSessionId.value = sessionId
  emit('update:question', '')
  nextTick(() => scrollToBottom(false))
}

function deleteSession(sessionId) {
  if (!sessionId) return
  if (props.askLoading && pendingSessionId.value === sessionId) {
    ElMessage.warning('当前会话正在生成回答，暂时无法删除')
    return
  }
  const idx = sessions.value.findIndex((item) => item.id === sessionId)
  if (idx < 0) return
  sessions.value.splice(idx, 1)
  if (!sessions.value.length) {
    const session = createSession()
    sessions.value = [session]
  }
  if (activeSessionId.value === sessionId) {
    activeSessionId.value = sessions.value[0].id
  }
}

function clearActiveSession() {
  if (props.askLoading) {
    ElMessage.warning('AI 回答中，暂时不能清空')
    return
  }
  const session = ensureActiveSession()
  session.messages = []
  session.title = DEFAULT_SESSION_TITLE
  session.preview = ''
  session.updatedAt = nowTs()
  pendingSessionId.value = ''
  pendingAssistantMessageId.value = ''
  emit('clear-draft')
  emit('update:question', '')
  nextTick(() => scrollToBottom(false))
}

function focusComposer() {
  composerRef.value?.focus?.()
}

function scrollToBottom(smooth = true) {
  const el = threadRef.value
  if (!el) return
  const behavior = smooth ? 'smooth' : 'auto'
  el.scrollTo({ top: el.scrollHeight, behavior })
}

function applyPreset(presetText) {
  if (!presetText) return
  const current = String(props.question || '').trim()
  const nextText = current ? `${current}\n${presetText}` : presetText
  emit('update:question', nextText)
  nextTick(() => focusComposer())
}

function togglePresetPanel() {
  presetExpanded.value = !presetExpanded.value
}

function toggleContextBinding() {
  emit('update:context-binding', !props.contextBinding)
}

function toggleDeepReasoning() {
  emit('update:deep-reasoning', !props.deepReasoning)
}

function toggleWebSearch() {
  emit('update:web-search', !props.webSearch)
}

function setExplainMode(mode) {
  const normalized = String(mode || '').trim()
  if (!['deep', 'assist'].includes(normalized)) return
  emit('update:explain-mode', normalized)
}

function setExplainStyle(style) {
  const normalized = String(style || '').trim()
  if (!['gentle', 'rigorous'].includes(normalized)) return
  emit('update:explain-style', normalized)
}

function toggleAutoSpeakAnswer() {
  emit('update:auto-speak-answer', !props.autoSpeakAnswer)
}

function togglePresetLectureScript() {
  emit('update:preset-lecture-script', !props.presetLectureScript)
}

function sendWithText(rawText) {
  const text = String(rawText || '').trim()
  if (!text) {
    ElMessage.warning('请输入问题后再发送')
    return
  }
  if (props.askLoading || props.streamTypingActive) {
    ElMessage.info('上一条回答仍在生成，请稍后')
    return
  }

  const session = ensureActiveSession()
  const assistantId = appendMessagePair(session.id, text)
  if (!assistantId) return

  pendingSessionId.value = session.id
  pendingAssistantMessageId.value = assistantId
  activeSessionId.value = session.id
  emit('update:question', text)
  emit('send-question')
  nextTick(() => {
    scrollToBottom(false)
    focusComposer()
  })
}

function handleSend() {
  sendWithText(props.question)
}

function regenerateLast() {
  if (props.askLoading || props.streamTypingActive) return
  const session = ensureActiveSession()
  const lastUser = [...session.messages].reverse().find((item) => item.role === 'user' && String(item.content || '').trim())
  if (!lastUser) {
    ElMessage.info('当前会话暂无可重新生成的提问')
    return
  }
  sendWithText(lastUser.content)
}

function isStreamingMessage(message) {
  return Boolean(
    message?.role === 'assistant'
      && message?.id
      && message.id === pendingAssistantMessageId.value
      && pendingSessionId.value === activeSessionId.value
      && (props.askLoading || props.streamTypingActive)
  )
}

function handleInputKeydown(event) {
  if (event.key !== 'Enter') return
  if (event.shiftKey) return
  event.preventDefault()
  handleSend()
}

function renderAssistantMessage(content) {
  const text = String(content || '').trim()
  if (!text) return ''
  try {
    return markdownEngine.render(text)
  } catch (error) {
    return `<pre><code>${escapeHtml(text)}</code></pre>`
  }
}

async function copyText(text, successTip = '已复制') {
  const content = String(text || '')
  if (!content) return
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(content)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = content
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.focus()
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success(successTip)
  } catch (error) {
    ElMessage.error('复制失败，请手动复制')
  }
}

function handleMarkdownAction(event) {
  const target = event.target instanceof HTMLElement ? event.target : null
  if (!target) return
  const button = target.closest('[data-copy-code]')
  if (!button) return
  const encoded = button.getAttribute('data-copy-code') || ''
  const decoded = decodeURIComponent(encoded)
  copyText(decoded, '代码已复制')
}

function emitPlayAnswerAudio(message) {
  const content = String(message?.content || '').trim()
  if (!content) return
  emit('play-answer-audio', {
    messageId: String(message?.id || ''),
    content
  })
}

function finalizePendingAssistantIfIdle() {
  if (!pendingSessionId.value || !pendingAssistantMessageId.value) return
  if (props.askLoading || props.streamTypingActive) return

  const finalText = String(props.aiReply || '').trim()
  if (!finalText) {
    updateAssistantMessage(
      pendingSessionId.value,
      pendingAssistantMessageId.value,
      '这次回答为空，建议点击「重新生成」再试一次。'
    )
  }

  pendingSessionId.value = ''
  pendingAssistantMessageId.value = ''
  nextTick(() => scrollToBottom(false))
}

watch(
  () => props.aiReply,
  (replyText) => {
    if (!pendingSessionId.value || !pendingAssistantMessageId.value) return
    updateAssistantMessage(pendingSessionId.value, pendingAssistantMessageId.value, String(replyText || ''))
    nextTick(() => scrollToBottom(false))
  }
)

watch(
  () => props.askLoading,
  (loading, prev) => {
    if (loading) {
      nextTick(() => scrollToBottom(false))
      return
    }
    if (!prev) return
    finalizePendingAssistantIfIdle()
  }
)

watch(
  () => props.streamTypingActive,
  (active) => {
    if (active) {
      nextTick(() => scrollToBottom(false))
      return
    }
    finalizePendingAssistantIfIdle()
  }
)

watch(
  () => props.externalAction?.id,
  () => {
    const action = props.externalAction || {}
    const mode = String(action.mode || '').trim()
    const text = String(action.text || '').trim()
    if (!mode || !text) return
    if (mode === 'system') {
      appendSystemMessage(text)
      return
    }
    if (mode === 'draft') {
      emit('update:question', text)
      nextTick(() => focusComposer())
      return
    }
    if (mode === 'send') {
      sendWithText(text)
    }
  }
)

watch(sessions, () => schedulePersist(), { deep: true })
watch(activeSessionId, () => schedulePersist())
watch(sessionSidebarCollapsed, (collapsed) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(SESSION_SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0')
})

onMounted(() => {
  if (typeof window !== 'undefined') {
    const raw = String(window.localStorage.getItem(SESSION_SIDEBAR_COLLAPSED_KEY) || '').trim()
    if (raw) {
      sessionSidebarCollapsed.value = ['1', 'true', 'yes', 'on'].includes(raw.toLowerCase())
    }
  }
  loadSessions()
  ensureActiveSession()
  nextTick(() => scrollToBottom(false))
})

onUnmounted(() => {
  if (persistTimer) {
    window.clearTimeout(persistTimer)
    persistTimer = null
  }
  persistSessions()
})
</script>

<style scoped>
.chat-shell {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  gap: 12px;
  border-radius: 14px;
  overflow: hidden;
  background:
    radial-gradient(circle at 4% 6%, rgba(166, 221, 201, 0.26), transparent 34%),
    radial-gradient(circle at 94% 90%, rgba(218, 241, 231, 0.55), transparent 36%),
    linear-gradient(165deg, #f7fcf9 0%, #eef8f3 100%);
  border: 1px solid #d8e9e1;
}

.chat-shell.sidebar-collapsed {
  grid-template-columns: 64px minmax(0, 1fr);
}

.session-sidebar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border-right: 1px solid #d7e7de;
  background:
    linear-gradient(180deg, rgba(31, 83, 69, 0.96) 0%, rgba(35, 103, 82, 0.92) 100%),
    linear-gradient(90deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0));
}

.session-sidebar.collapsed {
  align-items: center;
  padding: 10px 8px;
}

.session-toggle-btn {
  width: 100%;
  border: 1px solid rgba(157, 208, 188, 0.5);
  background: rgba(255, 255, 255, 0.1);
  color: #eaf7f1;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.session-toggle-icon {
  font-size: 14px;
  line-height: 1;
}

.session-toggle-text {
  line-height: 1;
}

.session-toggle-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(192, 228, 212, 0.8);
}

.session-toggle-btn.compact {
  width: 44px;
  min-height: 44px;
  border-radius: 12px;
  padding: 10px 0;
}

.session-toggle-btn.compact .session-toggle-text {
  display: none;
}

.new-session-mini-btn {
  width: 44px;
  height: 44px;
  border: 1px solid rgba(157, 208, 188, 0.5);
  background: rgba(255, 255, 255, 0.1);
  color: #eaf7f1;
  border-radius: 12px;
  font-size: 20px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: all 0.2s ease;
}

.new-session-mini-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(192, 228, 212, 0.8);
}

.new-session-mini-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.new-session-btn {
  width: 100%;
  border: 1px solid rgba(157, 208, 188, 0.5);
  background: rgba(255, 255, 255, 0.1);
  color: #eaf7f1;
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
}

.new-session-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(192, 228, 212, 0.8);
}

.new-session-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: auto;
  min-height: 0;
  padding-right: 2px;
}

.session-item {
  border-radius: 12px;
  border: 1px solid rgba(157, 207, 186, 0.35);
  padding: 10px;
  color: #d9f1e7;
  background: rgba(255, 255, 255, 0.04);
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, background-color 0.2s ease;
}

.session-item:hover {
  transform: translateY(-1px);
  border-color: rgba(173, 223, 201, 0.76);
  background: rgba(255, 255, 255, 0.12);
  box-shadow: 0 8px 18px rgba(16, 43, 36, 0.22);
}

.session-item.active {
  border-color: #76c6a7;
  background: linear-gradient(180deg, rgba(66, 144, 118, 0.34) 0%, rgba(84, 176, 147, 0.2) 100%);
  box-shadow: inset 0 0 0 1px rgba(196, 234, 218, 0.5), 0 10px 20px rgba(12, 46, 34, 0.24);
}

.session-item-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.session-title {
  font-size: 14px;
  line-height: 1.4;
  color: #f0fbf6;
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
}

.session-delete-btn {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  border: 1px solid rgba(183, 220, 204, 0.4);
  background: transparent;
  color: #daf1e7;
  cursor: pointer;
  line-height: 1;
  flex-shrink: 0;
}

.session-delete-btn:hover {
  background: rgba(255, 255, 255, 0.16);
}

.session-preview {
  margin-top: 6px;
  font-size: 12px;
  color: rgba(220, 241, 233, 0.86);
  min-height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  margin-top: 8px;
  font-size: 11px;
  color: rgba(190, 228, 213, 0.86);
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.chat-main {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px;
  gap: 10px;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #deece5;
  padding-bottom: 10px;
}

.chat-header-left h3 {
  margin: 0;
  font-size: 20px;
  color: #1b4d3f;
  line-height: 1.2;
}

.chat-header-left p {
  margin: 4px 0 0;
  color: #5f7f72;
  font-size: 13px;
}

.chat-header-actions {
  display: inline-flex;
  gap: 8px;
}

.ghost-btn {
  border: 1px solid #c4dfd3;
  background: #f7fcf9;
  color: #2a6254;
  border-radius: 999px;
  padding: 7px 12px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.ghost-btn:hover:not(:disabled) {
  background: #edf7f2;
}

.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.message-thread {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.thread-empty {
  min-height: 140px;
  border: 1px dashed #c7dfd4;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.72);
  color: #537668;
  font-size: 13px;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;
  animation: bubble-rise 0.2s ease;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.user .message-avatar {
  order: 2;
}

.message-row.user .message-bubble {
  order: 1;
  background: linear-gradient(180deg, #4a9f7e 0%, #3d8c6d 100%);
  border: 1px solid rgba(58, 127, 102, 0.25);
  color: #ffffff;
}

.message-row.assistant .message-bubble {
  background: #f8fbf8;
  border: 1px solid #d2e2da;
  color: #1f3f35;
}

.message-row.assistant .message-bubble.system {
  background: linear-gradient(180deg, #f7fcfa 0%, #edf7f2 100%);
  border: 1px dashed #9fc9b7;
  color: #2b5c4e;
}

.message-avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.understanding-level-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  margin-right: 4px;
  font-weight: 500;
}
.understanding-level-tag.level-none {
  background: #fee2e2; color: #b91c1c;
}
.understanding-level-tag.level-partial {
  background: #fef3c7; color: #92400e;
}
.understanding-level-tag.level-full {
  background: #d1fae5; color: #065f46;
}
.resume-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  background: #e0e7ff; color: #4338ca;
  margin-right: 4px;
}
.assistant-avatar {
  background: #dfeee7;
  color: #295c4d;
}

.user-avatar {
  background: rgba(255, 255, 255, 0.28);
  color: #ffffff;
}

.message-bubble {
  max-width: min(100%, 78%);
  border-radius: 14px;
  padding: 10px 12px;
  box-shadow: 0 10px 22px rgba(24, 56, 90, 0.08);
}

.message-bubble.streaming {
  border-color: #91c8af;
  box-shadow: 0 10px 24px rgba(47, 127, 102, 0.2);
}

.message-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.message-role {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  opacity: 0.82;
  font-weight: 700;
}

.message-tools {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.message-time {
  font-size: 11px;
  opacity: 0.78;
}

.inline-copy-btn {
  border: 1px solid #c2dbd0;
  background: #fff;
  color: #2e6758;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1;
  padding: 5px 8px;
  cursor: pointer;
}

.inline-copy-btn:hover {
  background: #eef8f3;
}

.user-text {
  white-space: pre-wrap;
  line-height: 1.75;
  color: inherit;
}

.assistant-body {
  position: relative;
  line-height: 1.7;
}

.assistant-body.has-audio-action {
  padding-bottom: 34px;
}

.assistant-body.system {
  color: #2f6454;
}

.thinking-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #3e6a5b;
}

.thinking-inline i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2f7f66;
  animation: dot-jump 1s ease-in-out infinite;
}

.thinking-inline i:nth-child(3) {
  animation-delay: 0.15s;
}

.thinking-inline i:nth-child(4) {
  animation-delay: 0.3s;
}

.streaming-state {
  margin-top: 8px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: #4b7366;
}

.typing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2f7f66;
  animation: pulse 1.1s ease-in-out infinite;
}

.assistant-audio-action {
  position: absolute;
  right: 0;
  bottom: 0;
  display: inline-flex;
}

.assistant-audio-btn {
  border: 1px solid #b8d6ca;
  background: #ffffff;
  color: #25584b;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 6px 10px rgba(36, 84, 69, 0.12);
}

.assistant-audio-btn:hover:not(:disabled) {
  background: #f2faf6;
}

.assistant-audio-btn:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}

.assistant-tool-row {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.explain-profile-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.composer-profile-row {
  margin-top: 10px;
}

.profile-group {
  border: 1px solid #d4e6dc;
  border-radius: 10px;
  background: linear-gradient(180deg, #fbfefc 0%, #f2f9f5 100%);
  padding: 8px;
  display: grid;
  gap: 6px;
}

.profile-label {
  font-size: 11px;
  font-weight: 700;
  color: #57786a;
  letter-spacing: 0.06em;
}

.profile-options {
  display: flex;
  gap: 6px;
}

.profile-option-btn {
  flex: 1;
  border: 1px solid #c8ded3;
  border-radius: 999px;
  background: #f8fcfa;
  color: #2f6758;
  font-size: 12px;
  font-weight: 700;
  padding: 6px 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.profile-option-btn:hover:not(:disabled) {
  border-color: #9cc7b5;
  background: #edf8f2;
}

.profile-option-btn.active {
  background: linear-gradient(180deg, #71b99f 0%, #4f9a7e 100%);
  border-color: #4f9a7e;
  color: #ffffff;
  box-shadow: 0 8px 16px rgba(79, 154, 126, 0.2);
}

.profile-option-btn:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}

.tool-btn {
  flex: 1 1 160px;
  min-width: 142px;
}

.mode-toggle-btn {
  border: 1px solid #c8ded3;
  border-radius: 10px;
  background: #f8fcfa;
  color: #2f6758;
  padding: 8px 10px;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: all 0.2s ease;
}

.mode-toggle-btn:hover:not(:disabled) {
  background: #edf8f2;
  border-color: #9cc7b5;
}

.mode-toggle-btn.active {
  background: linear-gradient(180deg, #71b99f 0%, #4f9a7e 100%);
  border-color: #4f9a7e;
  color: #ffffff;
  box-shadow: 0 8px 16px rgba(79, 154, 126, 0.22);
}

.mode-toggle-btn:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}

.preset-toggle-shell {
  margin-top: 6px;
}

.preset-toggle-btn {
  border: 1px solid #c8ded3;
  border-radius: 10px;
  background: linear-gradient(180deg, #f7fcfa 0%, #eef8f3 100%);
  color: #2c6456;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.preset-toggle-btn:hover:not(:disabled) {
  background: linear-gradient(180deg, #f0faf5 0%, #e7f5ee 100%);
}

.preset-toggle-btn:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}

.preset-toggle-arrow {
  color: #54786b;
  font-size: 11px;
}

.preset-panel {
  margin-top: 8px;
  border: 1px solid #d5e6de;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.9);
  padding: 8px;
}

.preset-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preset-chip {
  border: 1px solid #c6ddd2;
  border-radius: 999px;
  background: #f6fbf8;
  color: #2f6658;
  font-size: 12px;
  line-height: 1;
  padding: 8px 12px;
  cursor: pointer;
  transition: background-color 0.2s ease, border-color 0.2s ease;
}

.preset-chip:hover:not(:disabled) {
  background: #ebf7f1;
  border-color: #9fc8b7;
}

.preset-chip:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.composer {
  border: 1px solid #d7e6df;
  border-radius: 12px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.92);
}

.composer-input :deep(.el-textarea__inner) {
  border-radius: 10px;
  border-color: #c8ddd3;
  line-height: 1.65;
}

.composer-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.compose-tip {
  font-size: 12px;
  color: #607e72;
}

.send-btn {
  min-width: 96px;
  border-radius: 10px;
  font-weight: 700;
}

.markdown-content {
  color: #1f3f35;
}

.markdown-content :deep(p) {
  margin: 0.28em 0;
}

.markdown-content :deep(pre) {
  margin: 0.55em 0;
  padding: 0;
  border-radius: 10px;
  border: 1px solid #c5dacc;
  background: #12271f;
  overflow: hidden;
}

.markdown-content :deep(code) {
  font-family: Consolas, 'Courier New', monospace;
}

.markdown-content :deep(.code-shell-head) {
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  background: linear-gradient(180deg, #1f3e33 0%, #1a332b 100%);
  border-bottom: 1px solid rgba(156, 199, 181, 0.2);
}

.markdown-content :deep(.code-lang) {
  font-size: 11px;
  color: #c2e2d4;
  text-transform: uppercase;
}

.markdown-content :deep(.code-copy-btn) {
  border: 1px solid rgba(161, 199, 182, 0.38);
  background: rgba(255, 255, 255, 0.06);
  color: #d9f0e5;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
}

.markdown-content :deep(.code-copy-btn:hover) {
  background: rgba(255, 255, 255, 0.15);
}

.markdown-content :deep(.hl-code) {
  display: block;
  padding: 10px 12px;
  overflow: auto;
  color: #d3ebdf;
}

.markdown-content :deep(.tok-key) {
  color: #8bd8b9;
}

.markdown-content :deep(.tok-string) {
  color: #f6cf9a;
}

.markdown-content :deep(.tok-comment) {
  color: #8eb1a2;
}

.markdown-content :deep(.tok-num) {
  color: #b5f0ce;
}

.markdown-content :deep(.tok-bool) {
  color: #f8bdbd;
}

@keyframes bubble-rise {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes dot-jump {
  0%,
  80%,
  100% {
    transform: translateY(0);
    opacity: 0.45;
  }
  40% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

@keyframes pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.85;
  }
  50% {
    transform: scale(1.35);
    opacity: 0.5;
  }
}

@media (max-width: 1080px) {
  .chat-shell {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .chat-shell.sidebar-collapsed {
    grid-template-columns: 56px minmax(0, 1fr);
  }

  .message-bubble {
    max-width: min(100%, 86%);
  }
}

@media (max-width: 880px) {
  .chat-shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .chat-shell.sidebar-collapsed {
    grid-template-columns: minmax(0, 1fr);
  }

  .session-sidebar {
    border-right: none;
    border-bottom: 1px solid #d7e7de;
    max-height: 240px;
  }

  .session-sidebar.collapsed {
    max-height: none;
    align-items: flex-start;
  }

  .session-sidebar.collapsed .session-toggle-btn.compact {
    width: auto;
    min-height: 36px;
    writing-mode: horizontal-tb;
    text-orientation: mixed;
    letter-spacing: normal;
    padding: 8px 12px;
  }

  .session-sidebar.collapsed .session-toggle-btn.compact .session-toggle-text {
    display: inline;
  }

  .session-sidebar.collapsed .new-session-mini-btn {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    font-size: 18px;
  }

  .session-list {
    max-height: 170px;
  }

  .chat-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .chat-header-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .tool-btn,
  .mode-toggle-btn {
    flex: 1 1 calc(50% - 4px);
  }

  .explain-profile-row {
    grid-template-columns: 1fr;
  }
}
</style>