<template>
  <section class="intent-workspace">

    <div class="conversation-card">
      <header class="card-header">
        <div class="agent-identity">
          <div class="agent-avatar">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.2l1.35 4.1a5 5 0 003.15 3.15l4.1 1.35-4.1 1.35a5 5 0 00-3.15 3.15L12 20.4l-1.35-4.1a5 5 0 00-3.15-3.15L3.4 11.8l4.1-1.35a5 5 0 003.15-3.15L12 3.2z"/></svg>
          </div>
          <div>
            <div class="agent-name">教学设计智能体 <span class="online-dot"></span></div>
            <div class="agent-meta">正在理解你的课堂意图</div>
          </div>
        </div>
        <div class="header-actions">
          <span class="turn-badge">{{ store.turnCount }} / {{ store.maxTurns }} 轮</span>
          <button class="icon-button" title="重新开始" @click="handleReset">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4v6h6M20 20v-6h-6M5.5 15A7 7 0 0018 17M18.5 9A7 7 0 006 7"/></svg>
          </button>
        </div>
      </header>

      <div ref="messageList" class="message-list" aria-live="polite">
        <div class="conversation-date"><span>本次共创</span></div>
        <div
          v-for="(message, index) in store.messages"
          :key="`${index}-${message.role}`"
          class="message-row"
          :class="message.role"
        >
          <div v-if="message.role === 'assistant'" class="message-avatar ai">
            <svg viewBox="0 0 24 24"><path d="M12 4l1.1 3.4a4.2 4.2 0 002.7 2.7l3.4 1.1-3.4 1.1a4.2 4.2 0 00-2.7 2.7L12 18.4 10.9 15a4.2 4.2 0 00-2.7-2.7l-3.4-1.1 3.4-1.1a4.2 4.2 0 002.7-2.7L12 4z"/></svg>
          </div>
          <div class="message-block">
            <span class="message-author">{{ message.role === 'teacher' ? '你' : '教学设计智能体' }}</span>
            <div class="message-bubble">{{ message.content }}</div>
          </div>
          <div v-if="message.role === 'teacher'" class="message-avatar teacher">师</div>
        </div>

        <div v-if="store.isAnalyzing" class="message-row assistant">
          <div class="message-avatar ai">
            <svg viewBox="0 0 24 24"><path d="M12 4l1.1 3.4a4.2 4.2 0 002.7 2.7l3.4 1.1-3.4 1.1a4.2 4.2 0 00-2.7 2.7L12 18.4 10.9 15a4.2 4.2 0 00-2.7-2.7l-3.4-1.1 3.4-1.1a4.2 4.2 0 002.7-2.7L12 4z"/></svg>
          </div>
          <div class="message-block">
            <span class="message-author">教学设计智能体</span>
            <div class="message-bubble typing"><i></i><i></i><i></i><span>正在分析并更新方案</span></div>
          </div>
        </div>
      </div>

      <div v-if="!store.hasStarted" class="starter-prompts">
        <button v-for="item in starters" :key="item.title" @click="useStarter(item.prompt)">
          <span class="starter-icon" v-html="item.icon"></span>
          <span><b>{{ item.title }}</b><small>{{ item.description }}</small></span>
          <svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6"/></svg>
        </button>
      </div>

      <div v-else-if="store.followupQuestions.length && !store.isConfirmed" class="smart-replies">
        <span>建议补充</span>
        <button v-for="question in store.followupQuestions" :key="question" @click="useFollowup(question)">
          {{ shortQuestion(question) }}
        </button>
      </div>

      <div v-if="store.error" class="error-banner">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.1"/></svg>
        <span>{{ store.error }}</span>
      </div>

      <form class="composer" :class="{ disabled: store.isConfirmed }" @submit.prevent="send">
        <textarea
          ref="composerInput"
          v-model="draft"
          :disabled="store.isAnalyzing || store.isConfirmed"
          :placeholder="store.isConfirmed ? '方案已确认，如需修改请重新开始' : '描述课程主题、学生情况、时长或希望达到的效果…'"
          rows="2"
          @keydown.enter.exact.prevent="send"
          @keydown.enter.shift.exact.stop
        ></textarea>
        <div class="composer-footer">
          <div class="input-hints">
            <span><kbd>Enter</kbd> 发送</span>
            <span><kbd>Shift</kbd> + <kbd>Enter</kbd> 换行</span>
          </div>
          <div class="composer-actions">
            <VoiceInputButton
              :disabled="store.isAnalyzing || store.isConfirmed"
              @transcript="appendTranscript"
            />
            <button class="send-button" type="submit" :disabled="!draft.trim() || store.isAnalyzing || store.isConfirmed">
              <span>{{ store.isAnalyzing ? '理解中' : '发送' }}</span>
              <svg viewBox="0 0 24 24"><path d="M5 12h13M13 6l6 6-6 6"/></svg>
            </button>
          </div>
        </div>
      </form>
    </div>

    <aside class="intent-card">
      <header class="intent-header">
        <div>
          <span class="panel-kicker">LIVE INTENT MAP</span>
          <h2>教学意图画像</h2>
        </div>
        <div class="intent-header-actions">
          <button
            v-if="store.intentSummary && !store.isConfirmed"
            class="adjust-button"
            type="button"
            :aria-expanded="isEditing"
            @click="toggleEditor"
          >
            <svg viewBox="0 0 24 24"><path d="M4 20h4l11-11-4-4L4 16v4zM13.5 6.5l4 4"/></svg>
            {{ isEditing ? '收起调整' : '调整画像' }}
          </button>
          <span class="status-pill" :class="statusClass"><i></i>{{ statusText }}</span>
        </div>
      </header>

      <div class="readiness-card">
        <div class="readiness-ring" :style="ringStyle">
          <div><strong>{{ store.completionPct }}</strong><small>%</small></div>
        </div>
        <div class="readiness-copy">
          <span>方案完整度</span>
          <strong>{{ readinessTitle }}</strong>
          <p>{{ readinessDescription }}</p>
        </div>
      </div>

      <form v-if="isEditing" class="intent-editor" @submit.prevent="saveRevision">
        <div class="editor-heading">
          <div>
            <strong>确认前校正</strong>
            <span>调整后会重新交给智能体理解，并同步后端意图档案</span>
          </div>
          <span class="editor-badge">可撤回</span>
        </div>
        <div class="editor-grid">
          <label>
            <span>课程主题 <i>必填</i></span>
            <input v-model.trim="editForm.topic" aria-label="编辑课程主题" placeholder="例如：快速排序" />
          </label>
          <label>
            <span>授课时长 <i>必填</i></span>
            <div class="duration-input">
              <input v-model="editForm.duration_minutes" aria-label="编辑授课时长" type="number" min="5" max="300" />
              <b>分钟</b>
            </div>
          </label>
          <label>
            <span>授课对象</span>
            <input v-model.trim="editForm.target_student" aria-label="编辑授课对象" placeholder="例如：大一计算机专业学生" />
          </label>
          <label>
            <span>教学风格</span>
            <input v-model.trim="editForm.style" aria-label="编辑教学风格" placeholder="可自由填写，如：活泼、有故事感" />
          </label>
          <label class="editor-wide">
            <span>核心知识点</span>
            <input v-model.trim="editForm.knowledge_points" aria-label="编辑核心知识点" placeholder="用顿号或逗号分隔，例如：分治思想、枢轴选择、分区过程" />
          </label>
        </div>
        <label class="interaction-toggle">
          <input v-model="editForm.with_interactive" type="checkbox" />
          <span class="toggle-track"><i></i></span>
          <span><b>加入互动设计</b><small>课堂测验或知识翻卡</small></span>
        </label>
        <p v-if="editError" class="editor-error">{{ editError }}</p>
        <div class="editor-actions">
          <button type="button" class="editor-cancel" @click="closeEditor">取消</button>
          <button type="submit" class="editor-save" :disabled="store.isAnalyzing">
            {{ store.isAnalyzing ? '正在更新画像…' : '保存并重新分析' }}
          </button>
        </div>
      </form>

      <div class="field-grid">
        <article v-for="field in coreFields" :key="field.key" class="intent-field" :class="{ filled: field.filled }">
          <div class="field-icon" v-html="field.icon"></div>
          <div class="field-copy">
            <span>{{ field.label }} <i v-if="field.required">必填</i></span>
            <strong :class="{ placeholder: !field.filled }">{{ field.value || field.placeholder }}</strong>
          </div>
          <svg v-if="field.filled" class="field-check" viewBox="0 0 24 24"><path d="M5 12.5l4 4L19 7"/></svg>
        </article>
      </div>

      <section class="knowledge-section">
        <div class="section-title">
          <span>核心知识点</span>
          <small>{{ knowledgePoints.length ? `${knowledgePoints.length} 项` : '等待识别' }}</small>
        </div>
        <div v-if="knowledgePoints.length" class="knowledge-chips">
          <span v-for="point in knowledgePoints" :key="point">{{ point }}</span>
        </div>
        <div v-else class="knowledge-empty">
          <span>与 AI 对话后，知识点会自动汇聚到这里</span>
        </div>
      </section>

      <section v-if="store.intentSummary" class="preference-row">
        <div>
          <span class="preference-icon"><svg viewBox="0 0 24 24"><path d="M4 7h10M18 7h2M4 17h3M11 17h9M14 4v6M7 14v6"/></svg></span>
          <span><small>输出载体</small><b>{{ outputLabel }}</b></span>
        </div>
        <div>
          <span class="preference-icon"><svg viewBox="0 0 24 24"><path d="M8 12l2.5 2.5L16 9M12 3a9 9 0 100 18 9 9 0 000-18z"/></svg></span>
          <span><small>互动设计</small><b>{{ store.intentSummary.with_interactive ? '已开启' : '按需生成' }}</b></span>
        </div>
      </section>

      <div v-if="engineNoteVisible" class="engine-note" role="status">
        {{ engineNoteText }}
      </div>

      <footer class="intent-footer">
        <template v-if="!store.isConfirmed">
          <button class="confirm-button" :disabled="!store.canConfirm || store.isAnalyzing || store.isConfirming || isEditing" @click="confirm">
            <svg viewBox="0 0 24 24"><path d="M5 12.5l4 4L19 7"/></svg>
            <span>{{ store.isConfirming ? '正在建立意图档案…' : '确认教学意图' }}</span>
          </button>
          <p v-if="!store.canConfirm"><span></span>补齐课程主题与授课时长后即可确认</p>
          <p v-else><span class="ready"></span>核心信息已齐全，可确认或继续完善</p>
        </template>
        <template v-else>
          <div class="confirmed-banner">
            <svg viewBox="0 0 24 24"><path d="M5 12.5l4 4L19 7"/></svg>
            <span><b>教学意图已确认</b><small>{{ store.intentId }}</small></span>
          </div>
          <button class="next-button" @click="goNext">
            <span>进入 S3 · 自动检索并生成</span>
            <svg viewBox="0 0 24 24"><path d="M5 12h13M13 6l6 6-6 6"/></svg>
          </button>
        </template>
      </footer>
    </aside>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useIntentStore } from '../../stores/intentStore'
import { useCoursewareProjectStore } from '../../stores/coursewareProjectStore'
import VoiceInputButton from '../voice/VoiceInputButton.vue'

const props = defineProps({ deferInitialize: { type: Boolean, default: false } })
const store = useIntentStore()
const projectStore = useCoursewareProjectStore()
const router = useRouter()
const route = useRoute()
const draft = ref('')
const messageList = ref(null)
const composerInput = ref(null)
const isEditing = ref(false)
const editError = ref('')
const editForm = ref({
  topic: '',
  duration_minutes: '',
  target_student: '',
  style: '',
  knowledge_points: '',
  with_interactive: false
})

const svg = (path) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`
const starters = [
  {
    title: '从课程主题开始',
    description: '适合已有明确授课方向',
    prompt: '我想做一节关于排序算法的课，面向大一计算机专业学生。',
    icon: svg('M4 5h16v14H4zM8 9h8M8 13h5')
  },
  {
    title: '从课堂痛点开始',
    description: '让 AI 帮你反推教学设计',
    prompt: '学生总是混淆冒泡排序和快速排序，我想设计一节能真正讲清差异的课。',
    icon: svg('M12 3a7 7 0 00-4 12.7V19h8v-3.3A7 7 0 0012 3zM9 22h6')
  },
  {
    title: '体验完整示例',
    description: '一键填入高质量需求',
    prompt: '请设计一节45分钟的排序算法课，面向大一计算机专业学生，采用讲练结合的方式，重点包括冒泡排序、快速排序和复杂度对比，并加入课堂小测。',
    icon: svg('M4 12l5 5L20 6M4 6h5M15 17h5')
  }
]

const fieldIcons = {
  topic: svg('M4 5h16v14H4zM8 9h8M8 13h5'),
  duration_minutes: svg('M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v5l3 2'),
  target_student: svg('M16 19v-1.5a4 4 0 00-4-4H7a4 4 0 00-4 4V19M9.5 10a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM16 6h5M18.5 3.5v5'),
  style: svg('M5 4h14v16H5zM8 8h8M8 12h8M8 16h5')
}

const valueFor = (key) => store.intentSummary?.[key]
const coreFields = computed(() => [
  { key: 'topic', label: '课程主题', value: valueFor('topic'), placeholder: '等待对话提取', required: true, icon: fieldIcons.topic, filled: Boolean(valueFor('topic')) },
  { key: 'duration_minutes', label: '授课时长', value: valueFor('duration_minutes') ? `${valueFor('duration_minutes')} 分钟` : '', placeholder: '等待确认', required: true, icon: fieldIcons.duration_minutes, filled: Boolean(valueFor('duration_minutes')) },
  { key: 'target_student', label: '授课对象', value: valueFor('target_student'), placeholder: '可继续补充', icon: fieldIcons.target_student, filled: Boolean(valueFor('target_student')) },
  { key: 'style', label: '教学风格', value: valueFor('style'), placeholder: '可继续补充', icon: fieldIcons.style, filled: Boolean(valueFor('style')) }
])

const knowledgePoints = computed(() => store.intentSummary?.knowledge_points || [])
const fallbackReasonLabel = computed(() => ({
  timeout: 'AI 请求超时',
  engine_unavailable: 'AI 服务暂不可用',
  model_error: 'AI 服务返回异常',
  invalid_model_response: 'AI 返回内容无法校验',
  mock_mode: '本地模拟模式',
  missing_api_key_mock: '未配置 API Key'
}[store.fallbackReason] || '解析服务异常'))
// 结果来源判定（V04）：必须让"真实模型生成""规则兜底""未接入真实模型"在界面上可区分，
// 不能把一次 HTTP 200 当成真实模型已经跑通。
//   real_model   → 真实模型直出，不提示
//   rule_fallback→ 模型失败已回退规则引擎，提示具体降级原因
//   mock         → 压根没调用真实模型（mock 模式 / 未配置 API Key）
//   rule_engine  → 规则引擎直接产出（显式规则模式）
// 空串表示来源未知（旧数据），此时按旧逻辑只依据 usedFallback 提示，避免误报。
const isRealModelSource = computed(() => store.modelSource === 'real_model')
const isMockSource = computed(() => store.modelSource === 'mock' || store.modelSource === 'rule_engine')
const engineNoteVisible = computed(() => {
  if (store.modelSource) return !isRealModelSource.value
  return store.usedFallback
})
const engineNoteText = computed(() => {
  if (isMockSource.value) {
    return '当前未接入真实模型（本地模拟/规则模式），识别结果仅供参考，请核对并补充。'
  }
  // 注意：这里是 JS 模板字符串，必须用 ${} 插值；
  // 若误写成 Vue 的 {{ }}，界面上会原样显示 "{{ fallbackReasonLabel.value }}"。
  return `当前使用本地规则提取（${fallbackReasonLabel.value}），请核对并补充识别结果。`
})
const ringStyle = computed(() => ({ background: `conic-gradient(#4f8f7b ${store.completionPct}%, #e7efeb 0)` }))
const statusClass = computed(() => store.isConfirmed ? 'confirmed' : store.canConfirm ? 'confirming' : 'collecting')
const statusText = computed(() => store.isConfirmed ? '已确认' : store.canConfirm ? '待确认' : '持续理解中')
const readinessTitle = computed(() => {
  if (store.isConfirmed) return '方案已锁定'
  if (store.completionPct >= 80) return '信息很完整'
  if (store.canConfirm) return '核心信息齐全'
  if (store.completionPct >= 40) return '轮廓正在形成'
  return '等待你的想法'
})
const readinessDescription = computed(() => {
  if (store.isConfirmed) return '意图档案已准备好传递给下游 Skill。'
  if (store.canConfirm) return '现在即可确认，也可以继续补充细节。'
  return '每次对话都会实时更新右侧结构化画像。'
})
const outputLabel = computed(() => {
  const formats = store.intentSummary?.output_format || []
  if (formats.includes('ppt') && formats.includes('doc')) return 'PPT + Word'
  if (formats.includes('doc')) return 'Word 教案'
  return 'PPT 课件'
})

const fillEditor = () => {
  const summary = store.intentSummary || {}
  editForm.value = {
    topic: summary.topic || '',
    duration_minutes: summary.duration_minutes || '',
    target_student: summary.target_student || '',
    style: summary.style || '',
    knowledge_points: (summary.knowledge_points || []).join('、'),
    with_interactive: Boolean(summary.with_interactive)
  }
  editError.value = ''
}

const toggleEditor = () => {
  if (isEditing.value) closeEditor()
  else {
    fillEditor()
    isEditing.value = true
  }
}
const closeEditor = () => {
  isEditing.value = false
  editError.value = ''
}
const saveRevision = async () => {
  const duration = Number.parseInt(editForm.value.duration_minutes, 10)
  if (!editForm.value.topic.trim()) {
    editError.value = '请填写课程主题。'
    return
  }
  if (!Number.isFinite(duration) || duration < 5 || duration > 300) {
    editError.value = '授课时长请填写 5–300 分钟。'
    return
  }
  editError.value = ''
  const updated = await store.correctIntent({ ...editForm.value, duration_minutes: duration })
  if (updated) closeEditor()
  await scrollToLatest()
}

const scrollToLatest = async () => {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

const send = async () => {
  const content = draft.value.trim()
  if (!content) return
  draft.value = ''
  const sent = await store.sendMessage(content)
  if (!sent) draft.value = content
  await scrollToLatest()
  if (sent) composerInput.value?.focus()
}

// 语音输入：把 VoiceInputButton 识别出的最终文本片段追加进输入框。
// 中间结果只在按钮气泡里预览，只有 isFinal 的片段才会进入草稿，避免反复回改。
const appendTranscript = (text) => {
  if (!text) return
  draft.value = draft.value ? `${draft.value}${text}` : text
}

const useStarter = (prompt) => {
  draft.value = prompt
  composerInput.value?.focus()
}
const useFollowup = (question) => {
  if (question.includes('多少分钟')) draft.value = '45分钟'
  else if (question.includes('教学风格') || question.includes('案例驱动')) draft.value = '采用讲练结合和案例驱动的方式'
  else if (question.includes('年级') || question.includes('学生')) draft.value = '面向大一计算机专业、具备基础编程经验的学生'
  else if (question.includes('知识点')) draft.value = '重点包括概念原理、典型案例、方法对比和课堂练习'
  else if (question.includes('主题')) draft.value = '这节课的主题是排序算法'
  else draft.value = ''
  composerInput.value?.focus()
}
const shortQuestion = (question) => question.replace(/[？?]/g, '').replace(/^你?更?/, '').slice(0, 22)
const confirm = async () => {
  const confirmed = await store.confirmIntent()
  await scrollToLatest()
  if (confirmed) await goNext()
}
const handleReset = () => {
  if (store.hasStarted && !window.confirm('重新开始会清空当前 S1 对话与意图摘要，是否继续？')) return
  store.reset()
  closeEditor()
  draft.value = ''
  nextTick(() => composerInput.value?.focus())
}
const goNext = () => router.push({
  name: 'S3Studio',
  query: {
    project_id: route.query.project_id,
    sessionId: store.sessionId,
    intentId: store.intentId,
    auto_evidence: '1',
  },
})

onMounted(() => {
  if (!props.deferInitialize) store.initialize(String(route.query.project_id || projectStore.restoreActiveId() || ''))
  scrollToLatest()
})
watch(() => store.messages.length, scrollToLatest)
</script>

<style scoped>
* { box-sizing: border-box; }
button, textarea { font: inherit; }
button { -webkit-tap-highlight-color: transparent; }

/* 主工作区 / 侧栏：统一栅格，1280 以下双列、768 以下单列 */
.intent-workspace {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(340px, .82fr);
  gap: var(--space-4);
  width: 100%;
  margin: 0 auto;
}

.conversation-card,
.intent-card {
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.conversation-card {
  display: flex;
  flex-direction: column;
  min-height: 620px;
}

.card-header,
.intent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border-subtle);
}
.agent-identity { display: flex; align-items: center; gap: var(--space-3); min-width: 0; }
.agent-avatar {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: var(--radius-control);
  color: var(--color-on-primary);
  background: var(--color-primary);
}
.agent-avatar svg { width: 20px; fill: none; stroke: currentColor; stroke-width: 1.5; }
.agent-name { color: var(--text-primary); font-size: var(--text-sm); font-weight: var(--weight-semibold); }
.online-dot { display: inline-block; width: 6px; height: 6px; margin-left: var(--space-1); border-radius: 50%; background: var(--brand-400); box-shadow: 0 0 0 3px var(--color-primary-soft); }
.agent-meta { margin-top: 2px; color: var(--text-tertiary); font-size: var(--text-2xs); }
.header-actions { display: flex; align-items: center; gap: var(--space-2); flex-shrink: 0; }
.turn-badge {
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--bg-subtle);
  color: var(--text-secondary);
  font-size: var(--text-2xs);
  font-weight: var(--weight-medium);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.icon-button {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  color: var(--text-secondary);
  background: var(--bg-surface);
  cursor: pointer;
  transition: color var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}
.icon-button:hover { color: var(--color-primary); border-color: var(--color-primary-border); background: var(--color-primary-soft); }
.icon-button svg { width: 16px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }

/* 对话区 */
.message-list {
  flex: 1;
  min-height: 320px;
  max-height: 460px;
  padding: var(--space-5);
  overflow-y: auto;
}
.conversation-date {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin: 0 0 var(--space-5);
  color: var(--text-tertiary);
  font-size: var(--text-2xs);
  font-weight: var(--weight-medium);
  letter-spacing: 0.04em;
}
.conversation-date::before,
.conversation-date::after { content: ''; flex: 1; height: 1px; background: var(--border-subtle); }
.message-row { display: flex; align-items: flex-end; gap: var(--space-2); margin: 0 0 var(--space-4); }
.message-row.teacher { justify-content: flex-end; }
.message-avatar {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--radius-control);
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
}
.message-avatar.ai { color: var(--color-primary); background: var(--color-primary-soft); }
.message-avatar.ai svg { width: 16px; fill: none; stroke: currentColor; stroke-width: 1.6; }
.message-avatar.teacher { color: var(--color-on-primary); background: var(--neutral-500); }
.message-block { max-width: min(78%, 600px); min-width: 0; }
.message-row.teacher .message-block { text-align: right; }
.message-author { display: block; margin: 0 var(--space-1) var(--space-1); color: var(--text-tertiary); font-size: var(--text-2xs); font-weight: var(--weight-medium); }
.message-bubble {
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-control) var(--radius-md) var(--radius-md) var(--radius-md);
  color: var(--text-primary);
  background: var(--bg-subtle);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  text-align: left;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.teacher .message-bubble {
  border-color: transparent;
  border-radius: var(--radius-md) var(--radius-control) var(--radius-md) var(--radius-md);
  color: var(--color-on-primary);
  background: var(--color-primary);
}
.message-bubble.typing { display: flex; align-items: center; gap: var(--space-1); width: max-content; color: var(--text-tertiary); }
.message-bubble.typing i { width: 5px; height: 5px; border-radius: 50%; background: var(--brand-400); animation: tip-bounce 1.1s infinite; }
.message-bubble.typing i:nth-child(2) { animation-delay: .13s; }
.message-bubble.typing i:nth-child(3) { animation-delay: .26s; }
.message-bubble.typing span { margin-left: var(--space-1); font-size: var(--text-2xs); }

/* 引导语 / 建议补充 */
.starter-prompts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-2); padding: 0 var(--space-5) var(--space-4); }
.starter-prompts button {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  padding: var(--space-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  background: var(--bg-surface);
  text-align: left;
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}
.starter-prompts button:hover { border-color: var(--color-primary-border); background: var(--color-primary-soft); }
.starter-icon { display: grid; flex: 0 0 auto; place-items: center; width: 28px; height: 28px; border-radius: var(--radius-control); color: var(--color-primary); background: var(--color-primary-soft); }
.starter-icon :deep(svg) { width: 15px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.starter-prompts button > span:nth-child(2) { min-width: 0; flex: 1; }
.starter-prompts b, .starter-prompts small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.starter-prompts b { font-size: var(--text-2xs); font-weight: var(--weight-semibold); }
.starter-prompts small { margin-top: 2px; color: var(--text-tertiary); font-size: var(--text-2xs); }
.starter-prompts button > svg { width: 13px; flex-shrink: 0; fill: none; stroke: var(--text-tertiary); stroke-width: 1.7; }

.smart-replies { display: flex; align-items: center; gap: var(--space-2); padding: 0 var(--space-5) var(--space-3); overflow-x: auto; }
.smart-replies > span { flex: 0 0 auto; color: var(--text-tertiary); font-size: var(--text-2xs); font-weight: var(--weight-semibold); }
.smart-replies button {
  flex: 0 0 auto;
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-pill);
  color: var(--color-primary);
  background: var(--bg-surface);
  font-size: var(--text-2xs);
  cursor: pointer;
}
.smart-replies button:hover { border-color: var(--color-primary-border); background: var(--color-primary-soft); }

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin: 0 var(--space-5) var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-control);
  color: var(--color-danger);
  background: var(--color-danger-soft);
  font-size: var(--text-2xs);
  line-height: var(--leading-normal);
}
.error-banner svg { width: 15px; flex-shrink: 0; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; }

/* 输入区 */
.composer {
  margin: 0 var(--space-5) var(--space-5);
  padding: var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  transition: border-color var(--duration-fast) var(--ease-standard),
              box-shadow var(--duration-fast) var(--ease-standard);
}
.composer:focus-within { border-color: var(--color-primary); box-shadow: var(--shadow-focus); }
.composer.disabled { background: var(--bg-subtle); box-shadow: none; }
.composer textarea {
  width: 100%;
  min-height: 56px;
  padding: 0;
  border: 0;
  outline: 0;
  resize: vertical;
  color: var(--text-primary);
  background: transparent;
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
}
.composer textarea::placeholder { color: var(--text-disabled); }
.composer-footer { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.composer-actions { display: flex; align-items: center; gap: var(--space-2); }
.input-hints { display: flex; gap: var(--space-3); color: var(--text-tertiary); font-size: var(--text-2xs); }
.input-hints kbd { padding: 1px var(--space-1); border: 1px solid var(--border-default); border-radius: 4px; color: var(--text-secondary); background: var(--bg-subtle); font-size: var(--text-2xs); }
.send-button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 36px;
  padding: 0 var(--space-4);
  border: 0;
  border-radius: var(--radius-control);
  color: var(--color-on-primary);
  background: var(--color-primary);
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard);
}
.send-button:hover:not(:disabled) { background: var(--color-primary-hover); }
.send-button:disabled { opacity: 0.48; cursor: not-allowed; }
.send-button svg { width: 14px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }

/* 意图画像侧栏 */
.intent-card { min-height: 620px; padding-bottom: var(--space-4); }
.intent-header { padding: var(--space-4) var(--space-5); }
.panel-kicker { display: block; margin-bottom: var(--space-1); color: var(--color-primary); font-size: var(--text-2xs); font-weight: var(--weight-semibold); letter-spacing: 0.08em; }
.intent-header h2 { margin: 0; color: var(--text-primary); font-size: var(--text-lg); font-weight: var(--weight-semibold); }
.intent-header-actions { display: flex; align-items: center; gap: var(--space-2); flex-shrink: 0; }
.adjust-button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-height: 30px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  color: var(--color-primary);
  background: var(--bg-surface);
  font-size: var(--text-2xs);
  font-weight: var(--weight-medium);
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}
.adjust-button:hover { border-color: var(--color-primary-border); background: var(--color-primary-soft); }
.adjust-button svg { width: 12px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-pill);
  background: var(--bg-subtle);
  color: var(--text-secondary);
  font-size: var(--text-2xs);
  font-weight: var(--weight-medium);
  white-space: nowrap;
}
.status-pill i { width: 6px; height: 6px; border-radius: 50%; background: var(--text-disabled); }
.status-pill.confirming { color: var(--color-warning); background: var(--color-warning-soft); }
.status-pill.confirming i { background: var(--color-warning); }
.status-pill.confirmed { color: var(--color-success); background: var(--color-success-soft); }
.status-pill.confirmed i { background: var(--color-success); }

.readiness-card {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin: var(--space-4) var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
}
.readiness-ring { position: relative; display: grid; flex: 0 0 auto; place-items: center; width: 64px; height: 64px; border-radius: 50%; }
.readiness-ring::after { content: ''; position: absolute; inset: 6px; border-radius: 50%; background: var(--bg-surface); }
.readiness-ring > div { position: relative; z-index: 1; color: var(--color-primary); }
.readiness-ring strong { font-size: var(--text-xl); font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
.readiness-ring small { font-size: var(--text-2xs); }
.readiness-copy { min-width: 0; }
.readiness-copy > span { color: var(--text-tertiary); font-size: var(--text-2xs); font-weight: var(--weight-medium); }
.readiness-copy strong { display: block; margin-top: 2px; color: var(--text-primary); font-size: var(--text-sm); }
.readiness-copy p { margin: var(--space-1) 0 0; color: var(--text-tertiary); font-size: var(--text-2xs); line-height: var(--leading-relaxed); }

/* 画像编辑器 */
.intent-editor {
  margin: 0 var(--space-5) var(--space-4);
  padding: var(--space-4);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
}
.editor-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-3); margin-bottom: var(--space-3); }
.editor-heading strong, .editor-heading div > span { display: block; }
.editor-heading strong { color: var(--text-primary); font-size: var(--text-xs); }
.editor-heading div > span { margin-top: 2px; color: var(--text-secondary); font-size: var(--text-2xs); line-height: var(--leading-relaxed); }
.editor-heading .editor-badge { flex: 0 0 auto; padding: 2px var(--space-2); border-radius: var(--radius-pill); color: var(--color-primary); background: var(--bg-surface); font-size: var(--text-2xs); font-weight: var(--weight-medium); }
.editor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
.editor-grid label { min-width: 0; }
.editor-grid label > span { display: block; margin-bottom: var(--space-1); color: var(--text-secondary); font-size: var(--text-2xs); font-weight: var(--weight-medium); }
.editor-grid label > span i { margin-left: var(--space-1); color: var(--color-danger); font-style: normal; font-size: var(--text-2xs); }
.editor-grid input {
  width: 100%;
  min-height: 36px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  outline: 0;
  color: var(--text-primary);
  background: var(--bg-surface);
  font-size: var(--text-2xs);
  transition: border-color var(--duration-fast) var(--ease-standard),
              box-shadow var(--duration-fast) var(--ease-standard);
}
.editor-grid input:focus { border-color: var(--color-primary); box-shadow: var(--shadow-focus); }
.editor-wide { grid-column: 1 / -1; }
.duration-input { position: relative; }
.duration-input input { padding-right: 44px; }
.duration-input b { position: absolute; top: 50%; right: var(--space-3); color: var(--text-tertiary); font-size: var(--text-2xs); font-weight: var(--weight-regular); transform: translateY(-50%); }
.interaction-toggle { display: flex; align-items: center; gap: var(--space-2); margin-top: var(--space-3); padding: var(--space-2) var(--space-3); border-radius: var(--radius-control); background: var(--bg-surface); cursor: pointer; }
.interaction-toggle > input { position: absolute; opacity: 0; pointer-events: none; }
.toggle-track { position: relative; flex: 0 0 auto; width: 30px; height: 18px; border-radius: var(--radius-pill); background: var(--neutral-300); transition: background var(--duration-fast) var(--ease-standard); }
.toggle-track i { position: absolute; top: 3px; left: 3px; width: 12px; height: 12px; border-radius: 50%; background: var(--bg-surface); box-shadow: var(--shadow-xs); transition: transform var(--duration-fast) var(--ease-standard); }
.interaction-toggle > input:checked + .toggle-track { background: var(--color-primary); }
.interaction-toggle > input:checked + .toggle-track i { transform: translateX(12px); }
.interaction-toggle b, .interaction-toggle small { display: block; }
.interaction-toggle b { color: var(--text-primary); font-size: var(--text-2xs); font-weight: var(--weight-medium); }
.interaction-toggle small { margin-top: 2px; color: var(--text-tertiary); font-size: var(--text-2xs); }
.editor-error { margin: var(--space-2) 0 0; color: var(--color-danger); font-size: var(--text-2xs); }
.editor-actions { display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-3); }
.editor-actions button { min-height: 32px; padding: 0 var(--space-3); border-radius: var(--radius-control); font-size: var(--text-2xs); font-weight: var(--weight-semibold); cursor: pointer; }
.editor-cancel { border: 1px solid var(--border-default); color: var(--text-secondary); background: var(--bg-surface); }
.editor-save { border: 1px solid var(--color-primary); color: var(--color-on-primary); background: var(--color-primary); }
.editor-save:disabled { opacity: 0.48; cursor: not-allowed; }

/* 字段网格 */
.field-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-2); padding: 0 var(--space-5); }
.intent-field { position: relative; display: flex; align-items: center; gap: var(--space-2); min-width: 0; padding: var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--bg-surface); }
.intent-field.filled { border-color: var(--color-primary-border); background: var(--color-primary-soft); }
.field-icon { display: grid; flex: 0 0 auto; place-items: center; width: 28px; height: 28px; border-radius: var(--radius-control); color: var(--text-tertiary); background: var(--bg-subtle); }
.filled .field-icon { color: var(--color-primary); background: var(--bg-surface); }
.field-icon :deep(svg) { width: 15px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.field-copy { min-width: 0; }
.field-copy span, .field-copy strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.field-copy span { color: var(--text-tertiary); font-size: var(--text-2xs); }
.field-copy span i { margin-left: var(--space-1); color: var(--color-danger); font-style: normal; font-size: var(--text-2xs); }
.field-copy strong { margin-top: 2px; color: var(--text-primary); font-size: var(--text-xs); font-weight: var(--weight-medium); }
.field-copy strong.placeholder { color: var(--text-disabled); font-weight: var(--weight-regular); }
.field-check { position: absolute; top: var(--space-2); right: var(--space-2); width: 12px; fill: none; stroke: var(--color-success); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

.knowledge-section { margin: var(--space-4) var(--space-5) 0; padding: var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--bg-surface); }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
.section-title span { color: var(--text-primary); font-size: var(--text-xs); font-weight: var(--weight-semibold); }
.section-title small { color: var(--text-tertiary); font-size: var(--text-2xs); }
.knowledge-chips { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: var(--space-3); }
.knowledge-chips span { padding: var(--space-1) var(--space-2); border: 1px solid var(--color-primary-border); border-radius: var(--radius-control); color: var(--color-primary); background: var(--color-primary-soft); font-size: var(--text-2xs); }
.knowledge-empty { margin-top: var(--space-2); padding: var(--space-3); border: 1px dashed var(--border-default); border-radius: var(--radius-control); color: var(--text-tertiary); background: var(--bg-subtle); font-size: var(--text-2xs); text-align: center; }

.preference-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2); margin: var(--space-3) var(--space-5) 0; }
.preference-row > div { display: flex; align-items: center; gap: var(--space-2); min-width: 0; padding: var(--space-3); border-radius: var(--radius-sm); background: var(--bg-subtle); }
.preference-icon { display: grid; flex: 0 0 auto; place-items: center; width: 26px; height: 26px; border-radius: var(--radius-control); color: var(--color-primary); background: var(--bg-surface); }
.preference-icon svg { width: 14px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.preference-row small, .preference-row b { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.preference-row small { color: var(--text-tertiary); font-size: var(--text-2xs); }
.preference-row b { margin-top: 2px; color: var(--text-primary); font-size: var(--text-2xs); font-weight: var(--weight-medium); }

/* V04 结果来源提示：与全站反馈条一致，不再是一行 8px 灰字 */
.engine-note {
  margin: var(--space-3) var(--space-5) 0;
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-warning-border);
  border-left: 3px solid var(--color-warning);
  border-radius: var(--radius-control);
  background: var(--color-warning-soft);
  color: var(--color-warning);
  font-size: var(--text-2xs);
  line-height: var(--leading-relaxed);
}

.intent-footer { margin: var(--space-4) var(--space-5) 0; padding-top: var(--space-4); border-top: 1px solid var(--border-subtle); }
.confirm-button,
.next-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  min-height: 42px;
  padding: 0 var(--space-4);
  border: 0;
  border-radius: var(--radius-control);
  color: var(--color-on-primary);
  background: var(--color-primary);
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard);
}
.confirm-button:hover:not(:disabled), .next-button:hover { background: var(--color-primary-hover); }
.confirm-button:active:not(:disabled), .next-button:active { transform: translateY(1px); }
.confirm-button:disabled { opacity: 0.48; cursor: not-allowed; }
.confirm-button svg, .next-button svg { width: 15px; fill: none; stroke: currentColor; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
.intent-footer > p { display: flex; align-items: center; justify-content: center; gap: var(--space-2); margin: var(--space-2) 0 0; color: var(--text-tertiary); font-size: var(--text-2xs); }
.intent-footer > p span { width: 6px; height: 6px; border-radius: 50%; background: var(--text-disabled); }
.intent-footer > p span.ready { background: var(--color-success); box-shadow: 0 0 0 3px var(--color-success-soft); }
.confirmed-banner { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); padding: var(--space-3); border: 1px solid var(--color-primary-border); border-radius: var(--radius-control); color: var(--color-primary); background: var(--color-primary-soft); }
.confirmed-banner > svg { width: 18px; flex-shrink: 0; fill: none; stroke: currentColor; stroke-width: 2; }
.confirmed-banner b, .confirmed-banner small { display: block; }
.confirmed-banner b { font-size: var(--text-2xs); }
.confirmed-banner small { margin-top: 2px; color: var(--text-secondary); font-family: var(--font-mono); font-size: var(--text-2xs); overflow-wrap: anywhere; }

@keyframes tip-bounce { 0%, 60%, 100% { transform: translateY(0); opacity: .5; } 30% { transform: translateY(-3px); opacity: 1; } }

@media (max-width: 1279px) {
  .intent-workspace { grid-template-columns: minmax(0, 1.2fr) minmax(320px, .9fr); }
}
@media (max-width: 1023px) {
  .intent-workspace { grid-template-columns: 1fr; }
  .intent-card { min-height: auto; }
  .conversation-card { min-height: 560px; }
}
@media (max-width: 767px) {
  .card-header, .intent-header { padding: var(--space-3) var(--space-4); }
  .intent-header { align-items: flex-start; flex-wrap: wrap; }
  .intent-header-actions { align-items: flex-end; }
  .conversation-card { min-height: 520px; }
  .message-list { padding: var(--space-4); }
  .message-block { max-width: 86%; }
  .starter-prompts { grid-template-columns: 1fr; padding: 0 var(--space-4) var(--space-3); }
  .smart-replies { padding: 0 var(--space-4) var(--space-3); }
  .composer { margin: 0 var(--space-4) var(--space-4); }
  .input-hints span:nth-child(2) { display: none; }
  .readiness-card { margin: var(--space-3) var(--space-4); }
  .intent-editor { margin: 0 var(--space-4) var(--space-3); }
  .editor-grid { grid-template-columns: 1fr; }
  .editor-wide { grid-column: auto; }
  .field-grid { grid-template-columns: 1fr; padding: 0 var(--space-4); }
  .knowledge-section, .preference-row, .engine-note, .intent-footer { margin-left: var(--space-4); margin-right: var(--space-4); }
  .preference-row { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .message-bubble.typing i { animation-duration: 0.01ms; }
}
</style>
