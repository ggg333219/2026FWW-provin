<template>
  <div class="intent-panel">
    <!-- 顶部 -->
    <div class="top-bar">
      <div>
        <h3>意图理解 S1</h3>
        <span class="desc">输入教师需求，AI 自动提取结构化教学意图</span>
      </div>
      <div class="top-right">
        <label class="stream-toggle">
          <input type="checkbox" v-model="useStreaming" />
          流式输出
        </label>
        <select v-model="mode" :disabled="useStreaming" class="mode-select">
          <option value="rule">本地规则</option>
          <option value="llm">大模型</option>
        </select>
        <span class="badge" :class="badgeClass">{{ badgeText }}</span>
      </div>
    </div>

    <!-- 主体 -->
    <div class="main-area">
      <!-- 左侧：对话 -->
      <div class="left-panel">
        <div class="chat-box">
          <div v-if="messages.length === 0" class="chat-empty">
            在下方输入框描述你的教学需求，按 <kbd>Ctrl+Enter</kbd> 快捷发送
          </div>
          <div v-for="(m, i) in messages" :key="i" class="chat-msg" :class="m.role">
            <span class="msg-role">{{ m.role === 'teacher' ? '教师' : '助手' }}</span>
            <span class="msg-text">{{ m.content }}</span>
          </div>
        </div>

        <!-- 流式输出 -->
        <div v-if="isStreaming || streamedText" class="stream-box" :class="{ live: isStreaming }">
          <div class="stream-head">
            <span v-if="isStreaming" class="dot green"></span>
            <span v-else class="dot gray"></span>
            <span>{{ isStreaming ? '正在提取...' : '提取完成' }}</span>
          </div>
          <pre class="stream-body">{{ streamedText || '...' }}<i v-if="isStreaming" class="cursor">|</i></pre>
        </div>

        <!-- 输入区 -->
        <div class="input-area">
          <textarea
            v-model="inputText"
            placeholder="例如：帮我做一份45分钟的排序算法课件，面向大一计算机专业，讲练结合。包括冒泡排序、快速排序"
            rows="3"
            @keydown.enter.ctrl="appendMessage"
          ></textarea>
          <div class="tag-row">
            <span class="tag-label">快捷标签：</span>
            <button v-for="t in quickTags" :key="t" class="tag" @click="setFormat(t)">{{ t }}</button>
          </div>
          <div class="example-row">
            <span class="tag-label">示例：</span>
            <button v-for="s in sampleCases" :key="s.label" class="tag outline" @click="chooseSample(s)">{{ s.label }}</button>
          </div>
          <div class="btn-row">
            <button class="btn blue" @click="appendMessage" :disabled="!inputText.trim()">+ 添加消息</button>
            <button v-if="!isStreaming" class="btn dark" @click="callExtract" :disabled="messages.length === 0">提取意图</button>
            <button v-else class="btn red" @click="cancelStream">取消</button>
            <button class="btn" @click="generateFollowups" :disabled="!hasResult">生成追问</button>
            <button class="btn outline-red" @click="clearAll">清空</button>
          </div>
          <div v-if="errorMsg" class="err-msg">{{ errorMsg }}</div>
        </div>
      </div>

      <!-- 右侧：结果 -->
      <div class="right-panel">
        <div v-if="hasResult" class="result-card">
          <div class="result-head">
            <h4>提取结果</h4>
            <button class="btn small" @click="copyJSON">复制 JSON</button>
          </div>

          <!-- 只显示有值的字段 -->
          <div class="field-list">
            <template v-for="field in displayFields" :key="field.key">
              <div v-if="field.value" class="fld" :class="{ highlight: freshFields.has(field.key) }">
                <span class="fld-label">{{ field.label }}</span>
                <span class="fld-val">{{ field.value }}</span>
              </div>
            </template>
            <div v-if="allFieldsEmpty" class="fld-empty">
              未能提取到有效字段，请尝试输入更详细的教师需求。
            </div>
          </div>

          <div v-if="localFollowups.length" class="followups">
            <h5>追问建议</h5>
            <div class="fu-chips">
              <button v-for="q in localFollowups" :key="q" class="tag" @click="insertFollowup(q)">{{ q }}</button>
            </div>
          </div>
        </div>

        <div v-else-if="isStreaming" class="loading-box">
          <div class="dots"><i></i><i></i><i></i></div>
          <p>正在提取意图...</p>
        </div>

        <div v-else class="empty-box">
          输入需求后点击「提取意图」
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { AI_API_BASE } from '../../config/api'

const messages = ref([])
const inputText = ref('')
const result = ref(null)
const mode = ref('llm')
const useStreaming = ref(true)
const isStreaming = ref(false)
const streamedText = ref('')
const errorMsg = ref('')
const freshFields = ref(new Set())
let abortController = null

const quickTags = ['课件', '讲稿', '练习', '互动', '测验']

const sampleCases = ref([
  { label: '排序算法', prompt: '我要一份35分钟的排序算法讲解，面向高中生，希望包含互动练习和习题' },
  { label: '函数式编程', prompt: '请帮我生成一份50分钟的函数式编程讲稿，面向大二计算机学生，包含案例分析和讨论环节' },
  { label: '语文阅读', prompt: '我需要一份30分钟的语文阅读练习课件，面向初三学生，重点讲解古诗鉴赏，并带小测试' },
  { label: '物理实验', prompt: '帮我准备一节40分钟的高中物理实验测验，包含实验原理、练习题和互动问答' },
  { label: '思维导图', prompt: '我要一份45分钟的思维导图课件，面向历史老师使用，包含知识点梳理和课堂活动' },
])

const followupMap = {
  topic: '请问本次课程的主题具体是什么？',
  duration_minutes: '预计时长是多少分钟？',
  style: '您希望采用什么教学风格？',
  target_student: '本课主要面向哪个年级或专业的学生？',
  knowledge_points: '请列出计划覆盖的主要知识点。',
}
const localFollowups = ref([])

// ── 计算属性 ──
const hasResult = computed(() => !!result.value?.intent_summary)

const badgeClass = computed(() => useStreaming.value ? 's' : mode.value)
const badgeText = computed(() => useStreaming.value ? 'LLM 流式' : (mode.value === 'rule' ? '本地规则' : 'LLM'))

const displayFields = computed(() => {
  if (!result.value?.intent_summary) return []
  const s = result.value.intent_summary
  return [
    { key: 'topic', label: '主题', value: s.topic || '' },
    { key: 'duration_minutes', label: '时长', value: s.duration_minutes ? `${s.duration_minutes} 分钟` : '' },
    { key: 'style', label: '风格', value: s.style || '' },
    { key: 'target_student', label: '面向', value: s.target_student || '' },
    { key: 'knowledge_points', label: '知识点', value: (s.knowledge_points || []).join('、') },
    { key: 'output_format', label: '输出格式', value: (s.output_format || []).join('、') },
    { key: 'human_summary', label: '摘要', value: result.value.human_summary || '' },
  ]
})

const allFieldsEmpty = computed(() => {
  return displayFields.value.every(f => !f.value)
})

// ── 方法 ──
function appendMessage() {
  if (!inputText.value.trim()) return
  messages.value.push({ role: 'teacher', content: inputText.value.trim() })
  inputText.value = ''
  errorMsg.value = ''
}

function chooseSample(item) { inputText.value = item.prompt }
function insertSample() { inputText.value = sampleCases.value[0].prompt }
function setFormat(tag) {
  const pre = inputText.value.trim() ? inputText.value.trim() + '，' : ''
  inputText.value = `${pre}请生成一份${tag}`
}

function clearAll() {
  messages.value = []
  inputText.value = ''
  result.value = null
  streamedText.value = ''
  errorMsg.value = ''
  localFollowups.value = []
  freshFields.value = new Set()
}

function cancelStream() {
  abortController?.abort()
  abortController = null
  isStreaming.value = false
}

function formatJSON(obj) {
  try { return JSON.stringify(obj, null, 2) } catch { return String(obj) }
}

function copyJSON() {
  if (!result.value) return
  navigator.clipboard?.writeText(formatJSON(result.value.intent_summary))
}

function generateFollowups() {
  if (!result.value) return
  const missing = result.value.intent_summary?.missing_fields || []
  localFollowups.value = missing.map(f => followupMap[f]).filter(Boolean)
}

function insertFollowup(q) { inputText.value = q }

function markFreshFields(obj) {
  if (!obj) return
  const next = new Set(freshFields.value)
  for (const k of Object.keys(obj)) {
    const v = obj[k]
    if (v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0)) {
      next.add(k)
    }
  }
  freshFields.value = next
  setTimeout(() => {
    const cleared = new Set(freshFields.value)
    for (const k of Object.keys(obj)) cleared.delete(k)
    freshFields.value = cleared
  }, 3000)
}

// ── 普通提取 ──
async function callExtractNormal() {
  const payload = { session_id: `sess_${Date.now()}`, messages: messages.value }
  const res = await fetch(`${AI_API_BASE}/intent/extract?mode=${mode.value}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) { errorMsg.value = `请求失败: ${res.status}`; return }
  const data = await res.json()
  if (!data.intent_summary) data.intent_summary = {}
  result.value = data
}

// ── 流式提取 ──
async function callExtractStream() {
  const payload = { session_id: `sess_${Date.now()}`, messages: messages.value }
  abortController = new AbortController()
  isStreaming.value = true
  streamedText.value = ''
  errorMsg.value = ''
  result.value = null
  freshFields.value = new Set()

  try {
    const res = await fetch(`${AI_API_BASE}/intent/extract-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: abortController.signal,
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const parts = buf.split('\n\n')
      buf = parts.pop() || ''
      for (const part of parts) {
        const lines = part.split('\n')
        const ev = lines.find(l => l.startsWith('event: '))
        const dt = lines.find(l => l.startsWith('data: '))
        if (!ev || !dt) continue
        const event = ev.slice(7).trim()
        let data = {}
        try { data = JSON.parse(dt.slice(6)) } catch { continue }

        if (event === 'extract_token') {
          streamedText.value += data.token
          tryProgressiveParse(data.accumulated)
        } else if (event === 'extract_done') {
          result.value = {
            intent_summary: data.intent_summary || {},
            human_summary: data.human_summary || '',
            need_followup: data.need_followup,
            followup_questions: data.followup_questions || [],
          }
          streamedText.value = formatJSON(data.intent_summary)
          markFreshFields(data.intent_summary)
        } else if (event === 'extract_error') {
          errorMsg.value = data.error || '流式提取失败'
        }
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') errorMsg.value = `请求失败: ${e.message}`
  } finally {
    isStreaming.value = false
    abortController = null
  }
}

function tryProgressiveParse(acc) {
  if (!acc) return
  try {
    let json = acc.trim()
    let braces = 0, brackets = 0, inStr = false
    for (const ch of json) {
      if (ch === '"' && json[json.indexOf(ch) - 1] !== '\\\\') inStr = !inStr
      if (inStr) continue
      if (ch === '{') braces++
      if (ch === '}') braces--
      if (ch === '[') brackets++
      if (ch === ']') brackets--
    }
    json += ']'.repeat(Math.max(0, brackets))
    json += '}'.repeat(Math.max(0, braces))
    const parsed = JSON.parse(json)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      if (!result.value) result.value = { intent_summary: {} }
      Object.assign(result.value.intent_summary, parsed)
      markFreshFields(parsed)
    }
  } catch { /* JSON 未完整，跳过 */ }
}

async function callExtract() {
  if (messages.value.length === 0) return
  errorMsg.value = ''
  useStreaming.value ? await callExtractStream() : await callExtractNormal()
}
</script>

<style scoped>
/* ========== 重置 ========== */
* { box-sizing: border-box; }
.intent-panel { font-family: Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif; color: #1e293b; }

/* ========== 顶部 ========== */
.top-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid #e2e8f0; background: #fff;
}
.top-bar h3 { margin: 0; font-size: 16px; color: #0f172a; }
.desc { font-size: 12px; color: #64748b; margin-left: 8px; }
.top-right { display: flex; align-items: center; gap: 10px; }
.stream-toggle { font-size: 13px; color: #334155; cursor: pointer; display: flex; align-items: center; gap: 4px; }
.stream-toggle input { cursor: pointer; }
.mode-select { padding: 4px 8px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; color: #1e293b; background: #fff; }
.mode-select:disabled { opacity: 0.4; }
.badge { padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 500; }
.badge.rule { background: #dbeafe; color: #1d4ed8; }
.badge.llm { background: #fee2e2; color: #991b1b; }
.badge.s { background: #dcfce7; color: #166534; }

/* ========== 主体 ========== */
.main-area { display: flex; gap: 0; min-height: 500px; }
.left-panel { flex: 1; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.right-panel { width: 360px; padding: 16px; border-left: 1px solid #e2e8f0; background: #f8fafc; }

/* ========== 对话区 ========== */
.chat-box {
  flex: 0 0 auto; max-height: 180px; overflow-y: auto;
  background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px;
}
.chat-empty { color: #94a3b8; text-align: center; padding: 24px 0; font-size: 13px; }
.chat-empty kbd { background: #e2e8f0; padding: 1px 5px; border-radius: 3px; font-size: 11px; }
.chat-msg { margin-bottom: 8px; }
.msg-role { font-weight: 600; font-size: 11px; color: #64748b; margin-right: 6px; }
.msg-text { color: #0f172a; }

/* ========== 流式输出 ========== */
.stream-box {
  background: #0f172a; border-radius: 8px; padding: 10px 14px;
  border: 2px solid transparent; transition: border-color 0.3s;
}
.stream-box.live { border-color: #3b82f6; }
.stream-head { display: flex; align-items: center; gap: 8px; color: #94a3b8; font-size: 12px; margin-bottom: 6px; }
.dot { width: 8px; height: 8px; border-radius: 50%; }
.dot.green { background: #22c55e; animation: pulse 1.2s infinite; }
.dot.gray { background: #64748b; }
.stream-body { color: #e2e8f0; font-family: 'JetBrains Mono', monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; max-height: 140px; overflow-y: auto; margin: 0; }
.cursor { color: #3b82f6; font-style: normal; animation: blink 0.8s step-end infinite; }

/* ========== 输入区 ========== */
.input-area { margin-top: auto; }
.input-area textarea {
  width: 100%; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px;
  font-family: inherit; font-size: 14px; color: #0f172a; resize: vertical;
}
.input-area textarea:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }
.tag-row, .example-row { display: flex; align-items: center; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.tag-label { font-size: 12px; color: #64748b; white-space: nowrap; }
.tag {
  background: #eef2ff; color: #1e293b !important; border: 1px solid #cbd5e1; border-radius: 20px;
  padding: 4px 10px; cursor: pointer; font-size: 12px; transition: background 0.15s;
}
.tag:hover { background: #dbeafe; }
.tag.outline { background: #fff; border-style: dashed; }
.btn-row { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }

/* ========== 按钮 (所有按钮显式设置 color) ========== */
.btn {
  padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 500;
  border: 1px solid #cbd5e1; background: #fff; color: #334155 !important;
  transition: all 0.15s;
}
.btn:hover:not(:disabled) { background: #f1f5f9; border-color: #94a3b8; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn.blue { background: #2563eb; color: #fff !important; border-color: #2563eb; }
.btn.blue:hover:not(:disabled) { background: #1d4ed8; }
.btn.dark { background: #0f172a; color: #fff !important; border-color: #0f172a; }
.btn.dark:hover:not(:disabled) { background: #1e293b; }
.btn.red { background: #dc2626; color: #fff !important; border-color: #dc2626; }
.btn.red:hover:not(:disabled) { background: #b91c1c; }
.btn.outline-red { background: #fff; color: #b91c1c !important; border-color: #fca5a5; }
.btn.outline-red:hover:not(:disabled) { background: #fef2f2; }
.btn.small { padding: 4px 10px; font-size: 12px; }

/* ========== 错误 ========== */
.err-msg { margin-top: 8px; padding: 8px 12px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; color: #991b1b; font-size: 13px; }

/* ========== 右侧结果 ========== */
.result-card {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px;
  animation: fadeIn 0.3s ease;
}
.result-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.result-head h4 { margin: 0; font-size: 15px; color: #0f172a; }
.field-list { display: flex; flex-direction: column; gap: 8px; }
.fld {
  background: #f8fafc; padding: 8px 10px; border-radius: 6px;
  border: 1px solid #e2e8f0; transition: border-color 0.3s, background 0.3s;
}
.fld.highlight { border-color: #3b82f6; background: #eff6ff; }
.fld-label { display: block; font-size: 11px; color: #64748b; margin-bottom: 2px; }
.fld-val { font-size: 14px; color: #0f172a; }
.fld-empty { color: #94a3b8; font-size: 13px; text-align: center; padding: 16px 0; }
.followups { margin-top: 14px; }
.followups h5 { margin: 0 0 8px; font-size: 13px; color: #475569; }
.fu-chips { display: flex; gap: 6px; flex-wrap: wrap; }

/* ========== 占位 ========== */
.loading-box { text-align: center; padding: 40px 0; color: #64748b; }
.loading-box .dots { display: flex; gap: 6px; justify-content: center; margin-bottom: 12px; }
.loading-box .dots i { width: 8px; height: 8px; background: #3b82f6; border-radius: 50%; animation: bounce 1.2s infinite; }
.loading-box .dots i:nth-child(2) { animation-delay: 0.2s; }
.loading-box .dots i:nth-child(3) { animation-delay: 0.4s; }
.empty-box { color: #94a3b8; text-align: center; padding: 60px 0; font-size: 14px; }

/* ========== 动画 ========== */
@keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
@keyframes blink { 50% { opacity: 0; } }
@keyframes pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.3; transform: scale(0.7); } }
@keyframes bounce { 0%,80%,100% { transform: scale(0.6); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }
</style>
