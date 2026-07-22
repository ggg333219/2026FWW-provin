<template>
  <div class="intent-panel card">
    <div class="panel-header">
      <div>
        <h3>意图理解（S1）</h3>
        <p class="subtitle">把教师需求转成结构化教学意图，支持快速补全与一键提取。</p>
      </div>
      <div class="mode-controls">
        <label class="mode-label">演示模式</label>
        <select v-model="mode">
          <option value="rule">本地规则</option>
          <option value="llm">大模型（LLM mock）</option>
        </select>
        <span class="engine-badge" :class="mode">{{ mode === 'rule' ? '本地规则' : 'LLM 模拟' }}</span>
      </div>
    </div>

    <div class="mode-note">当前模式仅用于演示，后端会根据模式选择本地规则或 mock LLM 输出。</div>
    <div class="divider"></div>

    <div class="body">
      <div class="left">
        <div class="conversation">
          <div v-for="(m, idx) in messages" :key="idx" :class="['turn', m.role]">
            <div class="role">{{ m.role }}</div>
            <div class="content">{{ m.content }}</div>
          </div>
        </div>

        <div class="composer">
          <textarea v-model="inputText" placeholder="输入教师消息...（例如：我要一份35分钟的排序算法讲解，面向高中生，包含互动练习）" rows="3"></textarea>
          <div class="preset-row">
            <button class="chip icon-chip" @click="setFormat('课件')">课件</button>
            <button class="chip icon-chip" @click="setFormat('讲稿')">讲稿</button>
            <button class="chip icon-chip" @click="setFormat('练习')">练习</button>
            <button class="chip icon-chip" @click="setFormat('互动')">互动</button>
            <button class="chip icon-chip" @click="setFormat('测验')">测验</button>
          </div>
          <div class="sample-row">
            <span class="sample-label">快速示例：</span>
            <button v-for="item in sampleCases" :key="item.label" class="chip" @click="chooseSample(item)">{{ item.label }}</button>
          </div>
          <div class="controls">
            <button class="primary" @click="appendMessage">+ 添加</button>
            <button class="muted" @click="insertSample">示例</button>
            <button class="accent" @click="callExtract">提取意图</button>
            <button @click="generateFollowups">生成追问</button>
            <button class="danger" @click="clearAll">清空</button>
          </div>
        </div>
      </div>

      <div class="right">
        <div v-if="result" class="result-card">
          <div class="result-header">
            <h4>提取结果</h4>
            <div class="actions">
              <button @click="copyJSON">复制 JSON</button>
            </div>
          </div>

          <div class="fields-grid">
            <div class="field"><strong>主题</strong><div class="val">{{ result.intent_summary.topic || '-' }}</div></div>
            <div class="field"><strong>时长</strong><div class="val">{{ result.intent_summary.duration_minutes ? result.intent_summary.duration_minutes + ' 分钟' : '-' }}</div></div>
            <div class="field"><strong>风格</strong><div class="val">{{ result.intent_summary.style || '-' }}</div></div>
            <div class="field"><strong>面向</strong><div class="val">{{ result.intent_summary.target_student || '-' }}</div></div>
            <div class="field full"><strong>知识点</strong><div class="val">{{ (result.intent_summary.knowledge_points || []).join('、') || '-' }}</div></div>
            <div class="field full"><strong>输出格式</strong><div class="val">{{ (result.intent_summary.output_format || []).join('、') || '-' }}</div></div>
          </div>

          <div class="followups">
            <h5>缺失字段 / 追问</h5>
            <div class="chips">
              <button v-for="q in localFollowups" :key="q" class="chip" @click="insertFollowup(q)">{{ q }}</button>
            </div>
          </div>

          <h5>原始 JSON</h5>
          <pre class="json">{{ formatJSON(result.intent_summary) }}</pre>
        </div>
        <div v-else class="placeholder">还没有提取结果，点击“提取意图”开始。</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { AI_API_BASE } from '../../config/api'

const messages = ref([])
const inputText = ref('')
const result = ref(null)
const mode = ref('llm')
const sampleCases = ref([
  {
    label: '排序算法讲解',
    prompt: '我要一份35分钟的排序算法讲解，面向高中生，希望包含互动练习和习题',
  },
  {
    label: '函数式编程讲稿',
    prompt: '请帮我生成一份50分钟的函数式编程讲稿，面向大二计算机学生，包含案例分析和讨论环节',
  },
  {
    label: '语文阅读练习',
    prompt: '我需要一份30分钟的语文阅读练习课件，面向初三学生，重点讲解古诗鉴赏，并带小测试',
  },
  {
    label: '物理实验测验',
    prompt: '帮我准备一节40分钟的高中物理实验测验，包含实验原理、练习题和互动问答',
  },
  {
    label: '思维导图课件',
    prompt: '我要一份45分钟的思维导图课件，面向历史老师使用，包含知识点梳理和课堂活动',
  },
])

function appendMessage() {
  if (!inputText.value.trim()) return
  messages.value.push({ role: 'teacher', content: inputText.value.trim() })
  inputText.value = ''
}

function chooseSample(item) {
  inputText.value = item.prompt
}

function insertSample() {
  inputText.value = sampleCases.value[0].prompt
}

function clearAll() {
  messages.value = []
  inputText.value = ''
  result.value = null
}

async function callExtract() {
  const payload = { session_id: `sess_${Date.now()}`, messages: messages.value }
  try {
    const res = await fetch(`${AI_API_BASE}/intent/extract?mode=${mode.value}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      result.value = { intent_summary: {}, human_summary: `请求失败: ${res.status}` }
      return
    }
    const data = await res.json()
    // normalize structure: ensure intent_summary exists
    if (!data.intent_summary) data.intent_summary = data.intent || {}
    result.value = data
  } catch (e) {
    result.value = { intent_summary: {}, human_summary: `请求异常: ${e.message}` }
  }
}

function formatJSON(obj) {
  try { return JSON.stringify(obj, null, 2) } catch { return String(obj) }
}

function copyJSON() {
  if (!result.value) return
  navigator.clipboard?.writeText(formatJSON(result.value.intent_summary))
}

function setFormat(tag) {
  const prefix = inputText.value.trim() ? inputText.value.trim() + '，' : ''
  inputText.value = `${prefix}请生成一份${tag}`
}

// Build followup questions locally from missing fields
const followupMap = {
  topic: '请问本次课程的主题具体是什么？',
  duration_minutes: '预计时长是多少分钟？',
  style: '您希望采用什么教学风格（讲练结合/案例驱动等）？',
  target_student: '本课主要面向哪个年级或什么类型的学生？',
  knowledge_points: '请列出本节课计划覆盖的主要知识点。',
}

function generateFollowups() {
  if (!result.value) return
  const missing = result.value.intent_summary?.missing_fields || []
  const qs = missing.map(f => followupMap[f]).filter(Boolean)
  if (qs.length) {
    // show as chips by setting localFollowups
    localFollowups.splice(0, localFollowups.length, ...qs)
  } else {
    localFollowups.splice(0, localFollowups.length)
  }
}

const localFollowups = ref([])

function insertFollowup(q) {
  inputText.value = q
}

</script>

<style scoped>
.intent-panel { padding: 14px; font-family: Inter, 'PingFang SC', sans-serif; }
.card { background: #ffffff; border-radius: 8px; box-shadow: 0 6px 18px rgba(20,30,40,0.06); }
.panel-header { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid #f1f3f5 }
.panel-header h3 { margin:0; font-size:16px }
.mode-controls { display:flex; align-items:center; gap:8px }
.body { display:flex; gap:16px; padding:16px }
.left { flex:1 }
.right { width:420px }
.conversation { max-height:240px; overflow:auto; background:#fbfdff; padding:12px; border:1px solid #eef2ff; border-radius:6px }
.turn { margin-bottom:10px; animation: fadeIn 0.18s ease both }
.turn .role { font-weight:600; font-size:12px; color:#586674 }
.turn.teacher .content { color:#0f172a; padding:6px 0 }
.composer { margin-top:12px }
.composer textarea { width:100%; border:1px solid #e6eef8; border-radius:6px; padding:8px; min-height:68px }
.preset-row { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px }
.sample-row { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-top:10px }
.sample-label { color:#475569; font-size:13px; }
.chip { background:#eef2ff; color:#1e293b; border:none; border-radius:20px; padding:6px 12px; cursor:pointer; transition: transform .15s ease, background .15s ease }
.chip:hover { transform: translateY(-1px); background:#dbeafe }
.mode-note { padding: 0 16px 8px; color: #475569; font-size: 13px }
.icon-chip::before { content:'★'; margin-right:6px; color:#2563eb }
.controls { display:flex; gap:8px; margin-top:8px; flex-wrap:wrap }
.controls button { border:1px solid #e6eef8; background:#fff; padding:8px 12px; border-radius:8px; cursor:pointer; transition: transform .15s ease, box-shadow .15s ease }
.controls button:hover { transform: translateY(-1px); box-shadow: 0 10px 22px rgba(59,130,246,.12) }
.primary { background:#2b6ef6; color:white; border:none }
.accent { background:#0f172a; color:#fff; border:none }
.muted { background:#f3f6ff }
.danger { background:#fff5f6; border-color:#ffc3c6 }
.engine-badge { padding:4px 10px; border-radius:999px; font-size:12px; color:#1e293b; background:#e2e8f0; }
.engine-badge.rule { background:#dbeafe; color:#1d4ed8 }
.engine-badge.llm { background:#ffe4e6; color:#b91c1c }
.divider { height:1px; background:#eef2f7; margin:0 16px }
.result-card { background:linear-gradient(180deg,#ffffff,#fbfcff); padding:16px; border-radius:12px; border:1px solid #eef6f9; box-shadow: inset 0 0 0 1px rgba(99,102,241,.05); transition: transform .18s ease, box-shadow .18s ease }
.result-card:hover { transform: translateY(-1px); box-shadow: 0 14px 32px rgba(15,23,42,.08) }
.result-header { display:flex; justify-content:space-between; align-items:center }
.actions button { background:#eef2ff; border:1px solid #dbeafe; color:#1d4ed8; border-radius:8px; padding:6px 10px; cursor:pointer; transition: background .15s ease }
.actions button:hover { background:#dbeafe }
.fields-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px }
.field { background:#fff; padding:8px; border-radius:6px; border:1px solid #f0f4f8 }
.field.full { grid-column:1/-1 }
.field strong { display:block; color:#334155; margin-bottom:6px }
.val { color:#0f172a }
.followups { margin-top:10px }
.chips { display:flex; gap:8px; flex-wrap:wrap }
.chip { background:#f3f6ff; border:none; padding:6px 10px; border-radius:20px; cursor:pointer }
.json { background:#0f172a; color:#dbeafe; padding:8px; border-radius:6px; overflow:auto; max-height:220px }
.placeholder { color:#94a3b8; padding:20px; border:1px dashed #e6eef8; border-radius:6px }

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px) }
  to { opacity: 1; transform: translateY(0) }
}

</style>
