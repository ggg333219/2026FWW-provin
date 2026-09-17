<template>
  <section class="intent-workspace">
    <div class="workspace-glow"></div>

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
          <span><b>加入互动设计</b><small>课堂游戏、投票、讨论或随堂测验</small></span>
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

      <div v-if="store.usedFallback" class="engine-note">当前由本地规则引擎稳定接管，链路仍保持可用。</div>

      <footer class="intent-footer">
        <template v-if="!store.isConfirmed">
          <button class="confirm-button" :disabled="!store.canConfirm || store.isConfirming || isEditing" @click="confirm">
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
            <span>进入 S2 · 融合教学资料</span>
            <svg viewBox="0 0 24 24"><path d="M5 12h13M13 6l6 6-6 6"/></svg>
          </button>
        </template>
      </footer>
    </aside>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useIntentStore } from '../../stores/intentStore'
import VoiceInputButton from '../voice/VoiceInputButton.vue'

const store = useIntentStore()
const router = useRouter()
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
  await store.sendMessage(content)
  await scrollToLatest()
  composerInput.value?.focus()
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
  await store.confirmIntent()
  await scrollToLatest()
}
const handleReset = () => {
  if (store.hasStarted && !window.confirm('重新开始会清空当前 S1 对话与意图摘要，是否继续？')) return
  store.reset()
  closeEditor()
  draft.value = ''
  nextTick(() => composerInput.value?.focus())
}
const goNext = () => router.push({ name: 'S2Material', query: { sessionId: store.sessionId, intentId: store.intentId } })

onMounted(() => {
  store.initialize()
  scrollToLatest()
})
watch(() => store.messages.length, scrollToLatest)
</script>

<style scoped>
* { box-sizing: border-box; }
button, textarea { font: inherit; }
button { -webkit-tap-highlight-color: transparent; }

.intent-workspace {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(380px, .82fr);
  gap: 18px;
  max-width: 1500px;
  margin: 0 auto;
  isolation: isolate;
}
.workspace-glow {
  position: absolute;
  z-index: -1;
  right: 4%;
  bottom: -20px;
  width: 330px;
  height: 180px;
  border-radius: 50%;
  background: rgba(120, 190, 163, .16);
  filter: blur(70px);
}

.conversation-card, .intent-card {
  border: 1px solid rgba(45, 81, 70, .11);
  border-radius: 24px;
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 22px 55px rgba(29, 55, 46, .07), 0 2px 5px rgba(29, 55, 46, .03);
  overflow: hidden;
}
.conversation-card {
  display: flex;
  flex-direction: column;
  min-height: 650px;
}
.card-header, .intent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 22px;
  border-bottom: 1px solid #edf2ef;
}
.agent-identity { display: flex; align-items: center; gap: 12px; }
.agent-avatar {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 13px;
  color: #fff;
  background: linear-gradient(145deg, #305f56, #1f433e);
  box-shadow: 0 8px 18px rgba(33, 73, 66, .2);
}
.agent-avatar svg { width: 21px; fill: none; stroke: currentColor; stroke-width: 1.5; }
.agent-name { color: #1d2b26; font-size: 14px; font-weight: 750; }
.online-dot { display: inline-block; width: 6px; height: 6px; margin-left: 5px; border-radius: 50%; background: #55b384; box-shadow: 0 0 0 3px #e1f4e9; }
.agent-meta { margin-top: 4px; color: #8a9690; font-size: 11px; }
.header-actions { display: flex; align-items: center; gap: 9px; }
.turn-badge { padding: 6px 10px; border-radius: 999px; background: #f1f6f3; color: #698078; font-size: 10px; font-weight: 700; }
.icon-button {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid #e4ebe7;
  border-radius: 10px;
  color: #7f8d86;
  background: #fff;
  cursor: pointer;
}
.icon-button:hover { color: #315e54; border-color: #bfd3ca; background: #f5faf7; }
.icon-button svg { width: 16px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }

.message-list {
  flex: 1;
  min-height: 300px;
  max-height: 430px;
  padding: 20px 24px 10px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #cedbd5 transparent;
}
.conversation-date { display: flex; align-items: center; gap: 12px; margin: 0 0 22px; color: #a1aba6; font-size: 9px; font-weight: 700; letter-spacing: .12em; }
.conversation-date::before, .conversation-date::after { content: ''; flex: 1; height: 1px; background: #eef2f0; }
.message-row { display: flex; align-items: flex-end; gap: 10px; margin: 0 0 18px; }
.message-row.teacher { justify-content: flex-end; }
.message-avatar {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  font-size: 10px;
  font-weight: 800;
}
.message-avatar.ai { color: #315d53; background: #e8f2ed; }
.message-avatar.ai svg { width: 15px; fill: none; stroke: currentColor; stroke-width: 1.6; }
.message-avatar.teacher { color: #fff; background: #80958c; }
.message-block { max-width: min(78%, 600px); }
.message-row.teacher .message-block { text-align: right; }
.message-author { display: block; margin: 0 4px 5px; color: #909b95; font-size: 9px; font-weight: 650; }
.message-bubble {
  padding: 11px 14px;
  border: 1px solid #e5ece8;
  border-radius: 7px 16px 16px 16px;
  color: #31413a;
  background: #f7faf8;
  font-size: 13px;
  line-height: 1.7;
  text-align: left;
  white-space: pre-wrap;
}
.teacher .message-bubble { border: 0; border-radius: 16px 7px 16px 16px; color: #fff; background: linear-gradient(145deg, #315f56, #274e47); box-shadow: 0 8px 20px rgba(39, 78, 71, .12); }
.message-bubble.typing { display: flex; align-items: center; gap: 4px; width: max-content; color: #7b8983; }
.message-bubble.typing i { width: 5px; height: 5px; border-radius: 50%; background: #5d9b84; animation: bounce 1.1s infinite; }
.message-bubble.typing i:nth-child(2) { animation-delay: .13s; }
.message-bubble.typing i:nth-child(3) { animation-delay: .26s; }
.message-bubble.typing span { margin-left: 5px; font-size: 10px; }

.starter-prompts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; padding: 0 22px 14px; }
.starter-prompts button {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  padding: 10px;
  border: 1px solid #e5ece8;
  border-radius: 13px;
  color: #43544d;
  background: #fbfdfc;
  text-align: left;
  cursor: pointer;
  transition: .2s ease;
}
.starter-prompts button:hover { transform: translateY(-2px); border-color: #bcd3c9; box-shadow: 0 8px 18px rgba(42, 78, 66, .07); }
.starter-icon { display: grid; flex: 0 0 auto; place-items: center; width: 28px; height: 28px; border-radius: 9px; color: #477565; background: #eaf3ee; }
.starter-icon :deep(svg) { width: 15px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.starter-prompts button > span:nth-child(2) { min-width: 0; flex: 1; }
.starter-prompts b, .starter-prompts small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.starter-prompts b { font-size: 10px; }
.starter-prompts small { margin-top: 3px; color: #98a29d; font-size: 8px; }
.starter-prompts button > svg { width: 13px; fill: none; stroke: #a3afa9; stroke-width: 1.7; }

.smart-replies { display: flex; align-items: center; gap: 7px; padding: 0 22px 12px; overflow-x: auto; }
.smart-replies > span { flex: 0 0 auto; color: #8b9791; font-size: 9px; font-weight: 700; }
.smart-replies button { flex: 0 0 auto; padding: 6px 10px; border: 1px solid #dbe8e2; border-radius: 999px; color: #4d7466; background: #f4f9f6; font-size: 9px; cursor: pointer; }
.smart-replies button:hover { border-color: #80aa9b; background: #e9f4ee; }
.error-banner { display: flex; align-items: center; gap: 8px; margin: 0 22px 10px; padding: 9px 11px; border: 1px solid #f1d4d1; border-radius: 11px; color: #a0443f; background: #fff8f7; font-size: 10px; }
.error-banner svg { width: 15px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; }

.composer { margin: 0 18px 18px; padding: 11px 12px 9px; border: 1px solid #cfdcd6; border-radius: 17px; background: #fff; box-shadow: 0 8px 24px rgba(33, 62, 52, .06); transition: .2s ease; }
.composer:focus-within { border-color: #73a491; box-shadow: 0 0 0 4px rgba(90, 151, 127, .09), 0 10px 28px rgba(33, 62, 52, .07); }
.composer.disabled { background: #f7f9f8; box-shadow: none; }
.composer textarea { width: 100%; min-height: 48px; padding: 2px 3px; border: 0; outline: 0; resize: none; color: #27372f; background: transparent; font-size: 12px; line-height: 1.6; }
.composer textarea::placeholder { color: #a2ada7; }
.composer-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.composer-actions { display: flex; align-items: center; gap: 8px; }
.input-hints { display: flex; gap: 11px; color: #a2aca7; font-size: 8px; }
.input-hints kbd { padding: 1px 4px; border: 1px solid #e0e6e3; border-radius: 4px; color: #7f8c86; background: #f7f9f8; font-size: 8px; }
.send-button { display: flex; align-items: center; gap: 6px; padding: 8px 13px; border: 0; border-radius: 11px; color: #fff; background: #2c5b52; font-size: 10px; font-weight: 700; cursor: pointer; box-shadow: 0 6px 14px rgba(44, 91, 82, .18); }
.send-button:hover:not(:disabled) { background: #214a43; transform: translateY(-1px); }
.send-button:disabled { opacity: .38; cursor: not-allowed; box-shadow: none; }
.send-button svg { width: 14px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }

.intent-card { min-height: 650px; padding-bottom: 18px; background: linear-gradient(180deg, #fff, #fbfdfc); }
.intent-header { padding: 20px 20px 17px; }
.panel-kicker { display: block; margin-bottom: 5px; color: #739487; font-size: 8px; font-weight: 800; letter-spacing: .17em; }
.intent-header h2 { margin: 0; color: #1e2d27; font-size: 17px; letter-spacing: -.02em; }
.intent-header-actions { display: flex; align-items: center; gap: 7px; }
.adjust-button { display: inline-flex; align-items: center; gap: 5px; padding: 6px 9px; border: 1px solid #d9e7e0; border-radius: 999px; color: #436d5f; background: #f8fbf9; font-size: 9px; font-weight: 750; cursor: pointer; transition: .18s ease; }
.adjust-button:hover { border-color: #a9c9bb; background: #eef7f2; transform: translateY(-1px); }
.adjust-button svg { width: 11px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.status-pill { display: inline-flex; align-items: center; gap: 5px; padding: 6px 9px; border-radius: 999px; color: #6f7e77; background: #f0f4f2; font-size: 9px; font-weight: 700; }
.status-pill i { width: 5px; height: 5px; border-radius: 50%; background: #9eaaa4; }
.status-pill.confirming { color: #8a681c; background: #fff7df; }
.status-pill.confirming i { background: #d8a936; }
.status-pill.confirmed { color: #2c6a52; background: #e8f5ed; }
.status-pill.confirmed i { background: #4ca879; }

.readiness-card { display: flex; align-items: center; gap: 14px; margin: 16px 18px 13px; padding: 14px; border: 1px solid #e3ece7; border-radius: 17px; background: linear-gradient(135deg, #f4f9f6, #fbfdfc); }
.readiness-ring { position: relative; display: grid; flex: 0 0 auto; place-items: center; width: 64px; height: 64px; border-radius: 50%; }
.readiness-ring::after { content: ''; position: absolute; inset: 6px; border-radius: 50%; background: #fff; }
.readiness-ring > div { position: relative; z-index: 1; color: #2d5c52; }
.readiness-ring strong { font-size: 19px; letter-spacing: -.04em; }
.readiness-ring small { font-size: 8px; }
.readiness-copy > span { color: #8b9892; font-size: 8px; font-weight: 700; letter-spacing: .08em; }
.readiness-copy strong { display: block; margin-top: 3px; color: #25362f; font-size: 12px; }
.readiness-copy p { margin: 4px 0 0; color: #89958f; font-size: 9px; line-height: 1.45; }

.intent-editor { margin: 0 18px 14px; padding: 14px; border: 1px solid #cfe2d9; border-radius: 17px; background: linear-gradient(145deg, #f8fcfa, #f1f8f4); box-shadow: inset 0 1px 0 #fff, 0 10px 25px rgba(42, 86, 70, .06); }
.editor-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.editor-heading strong, .editor-heading span { display: block; }
.editor-heading strong { color: #25483d; font-size: 11px; }
.editor-heading div > span { margin-top: 3px; color: #819189; font-size: 8px; line-height: 1.5; }
.editor-heading .editor-badge { flex: 0 0 auto; padding: 4px 7px; border-radius: 999px; color: #4e806e; background: #e4f2eb; font-size: 7px; font-weight: 750; }
.editor-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
.editor-grid label { min-width: 0; }
.editor-grid label > span { display: block; margin-bottom: 5px; color: #60756b; font-size: 8px; font-weight: 700; }
.editor-grid label > span i { color: #a66d4f; font-style: normal; font-size: 7px; }
.editor-grid input { width: 100%; height: 34px; padding: 0 10px; border: 1px solid #d8e4de; border-radius: 9px; outline: 0; color: #263c33; background: rgba(255,255,255,.9); font-size: 9px; transition: .18s ease; }
.editor-grid input:focus { border-color: #73a691; box-shadow: 0 0 0 3px rgba(92, 159, 132, .1); }
.editor-wide { grid-column: 1 / -1; }
.duration-input { position: relative; }
.duration-input input { padding-right: 39px; }
.duration-input b { position: absolute; top: 50%; right: 10px; color: #899890; font-size: 8px; transform: translateY(-50%); }
.interaction-toggle { display: flex; align-items: center; gap: 8px; margin-top: 11px; padding: 9px 10px; border-radius: 11px; background: rgba(255,255,255,.72); cursor: pointer; }
.interaction-toggle > input { position: absolute; opacity: 0; pointer-events: none; }
.toggle-track { position: relative; flex: 0 0 auto; width: 28px; height: 17px; border-radius: 999px; background: #cdd9d3; transition: .2s ease; }
.toggle-track i { position: absolute; top: 3px; left: 3px; width: 11px; height: 11px; border-radius: 50%; background: #fff; box-shadow: 0 2px 4px rgba(36, 68, 56, .18); transition: .2s ease; }
.interaction-toggle > input:checked + .toggle-track { background: #4f947b; }
.interaction-toggle > input:checked + .toggle-track i { transform: translateX(11px); }
.interaction-toggle b, .interaction-toggle small { display: block; }
.interaction-toggle b { color: #38574b; font-size: 9px; }
.interaction-toggle small { margin-top: 2px; color: #8c9993; font-size: 7px; }
.editor-error { margin: 8px 0 0; color: #a0443f; font-size: 8px; }
.editor-actions { display: flex; justify-content: flex-end; gap: 7px; margin-top: 12px; }
.editor-actions button { padding: 7px 10px; border-radius: 9px; font-size: 8px; font-weight: 750; cursor: pointer; }
.editor-cancel { border: 1px solid #dbe5e0; color: #718078; background: #fff; }
.editor-save { border: 1px solid #315f56; color: #fff; background: #315f56; box-shadow: 0 5px 12px rgba(49, 95, 86, .16); }
.editor-save:disabled { opacity: .45; cursor: not-allowed; }

.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 0 18px; }
.intent-field { position: relative; display: flex; align-items: center; gap: 9px; min-width: 0; padding: 11px; border: 1px solid #e8eeeb; border-radius: 14px; background: #fff; }
.intent-field.filled { border-color: #d8e8e0; background: #fbfefc; }
.field-icon { display: grid; flex: 0 0 auto; place-items: center; width: 28px; height: 28px; border-radius: 9px; color: #7c8f86; background: #f0f4f2; }
.filled .field-icon { color: #477665; background: #e8f2ed; }
.field-icon :deep(svg) { width: 15px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.field-copy { min-width: 0; }
.field-copy span, .field-copy strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.field-copy span { color: #8e9a94; font-size: 8px; }
.field-copy span i { margin-left: 3px; color: #a66d4f; font-style: normal; font-size: 7px; }
.field-copy strong { margin-top: 4px; color: #293932; font-size: 10px; }
.field-copy strong.placeholder { color: #b0b8b4; font-weight: 500; }
.field-check { position: absolute; top: 8px; right: 8px; width: 11px; fill: none; stroke: #54a078; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

.knowledge-section { margin: 14px 18px 0; padding: 13px; border: 1px solid #e7eeea; border-radius: 15px; background: #fff; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.section-title span { color: #46574f; font-size: 10px; font-weight: 750; }
.section-title small { color: #9aa49f; font-size: 8px; }
.knowledge-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 10px; }
.knowledge-chips span { padding: 5px 8px; border: 1px solid #dce9e3; border-radius: 7px; color: #477263; background: #f1f7f4; font-size: 8px; }
.knowledge-empty { margin-top: 9px; padding: 10px; border: 1px dashed #dfe8e3; border-radius: 10px; color: #a1aba6; background: #fafcfb; font-size: 8px; text-align: center; }

.preference-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 10px 18px 0; }
.preference-row > div { display: flex; align-items: center; gap: 8px; padding: 10px; border-radius: 12px; background: #f5f8f6; }
.preference-icon { display: grid; place-items: center; width: 25px; height: 25px; border-radius: 8px; color: #53776a; background: #fff; }
.preference-icon svg { width: 14px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.preference-row small, .preference-row b { display: block; }
.preference-row small { color: #99a39e; font-size: 7px; }
.preference-row b { margin-top: 3px; color: #43544c; font-size: 9px; }
.engine-note { margin: 9px 18px 0; color: #8b7951; font-size: 8px; line-height: 1.5; }

.intent-footer { margin: 16px 18px 0; padding-top: 14px; border-top: 1px solid #ebf0ed; }
.confirm-button, .next-button { display: flex; align-items: center; justify-content: center; gap: 7px; width: 100%; padding: 11px; border: 0; border-radius: 12px; color: #fff; background: linear-gradient(135deg, #315f56, #244b44); font-size: 10px; font-weight: 750; cursor: pointer; box-shadow: 0 8px 18px rgba(36, 75, 68, .17); transition: .2s ease; }
.confirm-button:hover:not(:disabled), .next-button:hover { transform: translateY(-1px); box-shadow: 0 10px 22px rgba(36, 75, 68, .23); }
.confirm-button:disabled { color: #9ca8a2; background: #edf1ef; cursor: not-allowed; box-shadow: none; }
.confirm-button svg, .next-button svg { width: 14px; fill: none; stroke: currentColor; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
.intent-footer > p { display: flex; align-items: center; justify-content: center; gap: 5px; margin: 8px 0 0; color: #9ba6a0; font-size: 8px; }
.intent-footer > p span { width: 5px; height: 5px; border-radius: 50%; background: #c7cfcb; }
.intent-footer > p span.ready { background: #55a47a; box-shadow: 0 0 0 3px #e7f3ec; }
.confirmed-banner { display: flex; align-items: center; gap: 9px; margin-bottom: 8px; padding: 10px; border: 1px solid #d5eadf; border-radius: 12px; color: #377159; background: #f0faf4; }
.confirmed-banner > svg { width: 19px; fill: none; stroke: currentColor; stroke-width: 2; }
.confirmed-banner b, .confirmed-banner small { display: block; }
.confirmed-banner b { font-size: 10px; }
.confirmed-banner small { margin-top: 2px; color: #78a18e; font-family: monospace; font-size: 7px; }

@keyframes bounce { 0%, 60%, 100% { transform: translateY(0); opacity: .5; } 30% { transform: translateY(-3px); opacity: 1; } }

@media (max-width: 1050px) {
  .intent-workspace { grid-template-columns: 1fr; }
  .intent-card { min-height: auto; }
}
@media (max-width: 700px) {
  .conversation-card { min-height: 600px; }
  .starter-prompts { grid-template-columns: 1fr; }
  .starter-prompts button:nth-child(2) { display: none; }
  .field-grid { grid-template-columns: 1fr; }
  .intent-header { align-items: flex-start; gap: 10px; }
  .intent-header-actions { align-items: flex-end; flex-direction: column-reverse; }
  .editor-grid { grid-template-columns: 1fr; }
  .editor-wide { grid-column: auto; }
  .message-block { max-width: 86%; }
  .input-hints span:nth-child(2) { display: none; }
}
</style>
