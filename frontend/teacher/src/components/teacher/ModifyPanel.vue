<template>
  <div class="modify-panel" v-if="modifyStore.projectId">
    <div class="panel-header">
      <span class="panel-title">🤖 AI 修改 PPT</span>
      <span class="version-badge">{{ modifyStore.versionLabel }}</span>
      <div class="undo-redo">
        <button class="icon-btn" :disabled="!modifyStore.canUndo || modifyStore.modifying"
          @click="handleUndo" title="撤销">↩️</button>
        <button class="icon-btn" :disabled="!modifyStore.canRedo || modifyStore.modifying"
          @click="handleRedo" title="重做">↪️</button>
      </div>
    </div>

    <!--
      当前页 —— 对话里说「这页 / 本页 / 当前页」时的所指。
      不选就退回「按指令里的页号或标题定位」，与加这条之前完全一致。
    -->
    <div v-if="liveNodes.length" class="active-page-bar">
      <span class="apb-label">当前页</span>
      <select
        class="apb-select"
        :value="modifyStore.activeNodeId"
        :disabled="modifyStore.modifying"
        aria-label="选择当前页"
        @change="modifyStore.setActiveNode($event.target.value)"
      >
        <option value="">未指定（按指令里的页号定位）</option>
        <option
          v-for="(node, index) in liveNodes"
          :key="node.node_id || index"
          :value="node.node_id"
        >
          第 {{ index + 1 }} 页 · {{ node.title || '未命名节点' }}
        </option>
      </select>
    </div>

    <!-- 快捷指令 -->
    <div class="quick-chips">
      <button v-for="chip in modifyStore.quickChips" :key="chip.label"
        class="chip-btn" :disabled="modifyStore.modifying"
        @click="modifyStore.applyQuickChip(chip)">
        {{ chip.label }}
      </button>
    </div>

    <!-- 对话区 -->
    <div class="messages-area" ref="messagesEl" aria-live="polite" aria-label="AI 修改对话记录">
      <div v-if="modifyStore.messages.length === 0" class="empty-hint">
        输入修改意见，AI 会理解意图并局部修改课件。
      </div>
      <div v-for="msg in modifyStore.messages" :key="msg.id"
        :class="['message', msg.role === 'teacher' ? 'msg-right' : 'msg-left', { 'msg-error': msg.isError }]">
        <span class="msg-text">{{ msg.text }}</span>
        <span v-if="msg.versionNo" class="msg-version">v{{ msg.versionNo }}</span>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="modifyStore.error" class="error-bar" role="alert">
      <span>{{ modifyStore.error }}</span>
      <button v-if="modifyStore.lastFailedInstruction" type="button" @click="modifyStore.retryLast">重新填写</button>
    </div>

    <div v-if="modifyStore.modifying" class="ai-working" role="status" aria-live="polite">
      <span class="ai-working-spinner"></span>
      <div><strong>AI 正在修改课件</strong><p>正在理解指令并更新相关页面，请稍候…</p></div>
    </div>

    <div v-if="modifyStore.pendingClarification" class="clarification-context" role="status">
      <strong>AI 正在等你补充</strong>
      <span>{{ modifyStore.pendingClarification.question }}</span>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <textarea v-model="modifyStore.inputText" rows="2" maxlength="500"
        :placeholder="inputPlaceholder"
        :disabled="modifyStore.modifying"
        @keydown.enter.exact.prevent="handleSend"
        class="modify-input"></textarea>
      <button class="send-btn" :disabled="!modifyStore.canSend"
        @click="handleSend">
        {{ modifyStore.modifying ? '⏳' : '发送' }}
      </button>
    </div>

    <section v-if="liveNodes.length" class="live-preview" aria-label="页面列表">
      <div class="preview-head">
        <strong>页面</strong>
        <span>点一行即选中，对话里就能说「这页」</span>
      </div>
      <article v-for="(node, index) in liveNodes" :key="node.node_id || index"
        :class="['preview-node', { modified: isRecentlyModified(node), active: isActiveNode(node) }]"
        role="button" tabindex="0"
        :aria-pressed="isActiveNode(node)"
        @click="toggleActiveNode(node)"
        @keydown.enter.prevent="toggleActiveNode(node)"
        @keydown.space.prevent="toggleActiveNode(node)">
        <div class="preview-node-head">
          <span>第 {{ index + 1 }} 页 · {{ node.title || '未命名节点' }}</span>
          <span v-if="isActiveNode(node)" class="active-badge">当前页</span>
          <span v-else-if="isRecentlyModified(node)" class="modified-badge">已修改</span>
        </div>
        <p>{{ node.summary || node.content || node.script || '暂无内容' }}</p>
      </article>
    </section>

    <!-- 版本时间线（C7，展开后显示） -->
    <details v-if="modifyStore.versionHistory.length > 0" class="version-timeline">
      <summary>📜 修改历史（{{ modifyStore.versionHistory.length }} 条）</summary>
      <button v-for="v in modifyStore.versionHistory" :key="v.version_no" type="button"
        class="timeline-item" @click="previewVersion(v)">
        <span class="tl-version">v{{ v.version_no }}</span>
        <span :class="['change-kind', changeKind(v)]">{{ changeKind(v) === 'style' ? '样式' : '内容' }}</span>
        <span class="tl-instr">{{ v.modify_instruction || '(初始版本)' }}</span>
        <span class="tl-time">{{ v.created_at }}</span>
      </button>
      <span class="char-count" :class="{ limit: modifyStore.inputText.length >= 480 }">{{ modifyStore.inputText.length }}/500</span>
    </details>

    <div v-if="selectedVersion" class="history-preview" role="dialog" aria-modal="true" aria-label="历史版本只读预览" @click.self="selectedVersion = null">
      <div class="history-card">
        <div class="history-head">
          <div><strong>v{{ selectedVersion.version_no }} 只读预览</strong><p>{{ selectedVersion.modify_instruction || '初始版本' }}</p></div>
          <button type="button" class="icon-btn" @click="selectedVersion = null" aria-label="关闭">✕</button>
        </div>
        <div class="history-nodes">
          <article v-for="(node, index) in selectedVersion.nodes || []" :key="node.node_id || index">
            <strong>第 {{ index + 1 }} 页 · {{ node.title || '未命名节点' }}</strong>
            <p>{{ node.summary || node.content || node.script || '暂无内容' }}</p>
          </article>
          <p v-if="!selectedVersion.nodes?.length" class="empty-hint">该历史记录暂无可预览的节点快照。</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { useModifyStore } from '../../stores/modifyStore'
import { useOutlineStore } from '../../stores/outlineStore'
import { useGenerationStore } from '../../stores/generationStore'

const modifyStore = useModifyStore()
const outlineStore = useOutlineStore()
const generationStore = useGenerationStore()
const messagesEl = ref(null)
const selectedVersion = ref(null)
const emit = defineEmits(['style-request', 'applied'])
const liveNodes = computed(() => generationStore.currentScriptNodes?.length
  ? generationStore.currentScriptNodes
  : outlineStore.nodes)
const isRecentlyModified = (node) => modifyStore.recentlyModifiedIds.includes(node.node_id)
// 选中页时直接教老师说「这页」—— 这是最短的一句指令
const inputPlaceholder = computed(() => modifyStore.activeNodeId
  ? '例如：这页减少文字，加一个生活案例'
  : '例如：第三页减少文字，增加一个生活案例')
const isActiveNode = (node) => !!node?.node_id && node.node_id === modifyStore.activeNodeId
const toggleActiveNode = (node) => {
  // 再点一次取消选中，回到「按指令里的页号定位」
  modifyStore.setActiveNode(isActiveNode(node) ? '' : node.node_id)
}
const previewVersion = (version) => { selectedVersion.value = version }
const changeKind = (version) => /风格|样式|模板|配色|字体|版式|style|template/i.test(version?.modify_instruction || '') ? 'style' : 'content'
const handleGlobalKeydown = (event) => { if (event.key === 'Escape') selectedVersion.value = null }
onMounted(() => window.addEventListener('keydown', handleGlobalKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', handleGlobalKeydown))

// 节点转 TeachingNodeItem 格式（outlineStore.nodes → Go TeachingNodeItem JSON）
//
// 整节点透传（`...n`）而不是手工列字段：幻灯片真正画的是 point_details / figure /
// key_conclusion / teaching_plan，漏掉任何一个，都等于在这一跳把引擎的修改丢掉 ——
// 对话里报「已更新」，页面上却是「改了看不见」。引擎侧每加一个节点字段，
// 手工白名单就得同步一次，这条链路上没有谁会记得。
function nodesForApi() {
  const source = generationStore.currentScriptNodes?.length
    ? generationStore.currentScriptNodes
    : outlineStore.nodes
  return (source || []).map((n) => ({
    ...n,
    node_id: n.node_id,
    title: n.title,
    summary: n.summary,
    node_type: n.node_type,
    key_points: n.key_points || [],
    core_points: n.core_points || n.key_points || [],
    script: n.script || '',
    segments: n.segments || [],
    estimated_duration_minutes: n.estimated_duration_minutes || 5,
    citation_refs: n.citation_refs || [],
    source_chunk_ids: n.source_chunk_ids || [],
    metadata: n.metadata || {},
  }))
}

// 生成后优先写回 PPT 节点并用 inline 节点刷新预览；生成前才回写大纲。
async function applyResult({ allNodes, modifiedNodes, intent, instruction, presentation }) {
  if (!Array.isArray(allNodes)) return
  if (intent?.action === 'restyle' || intent?.target_type === 'style') {
    emit('style-request', { instruction, intent, presentation })
    return
  }
  const current = liveNodes.value || []
  const currentById = new Map(current.map((node) => [node.node_id, node]))
  const hasField = (node, field) => Object.prototype.hasOwnProperty.call(node || {}, field)
  const normalize = (n) => ({
    ...(currentById.get(n.node_id) || {}),
    ...n,
    node_id: n.node_id,
    title: n.title,
    summary: n.summary,
    node_type: n.node_type || 'content',
    key_points: n.key_points || n.core_points || [],
    core_points: n.core_points || n.key_points || [],
    estimated_duration_minutes: n.estimated_duration_minutes || 5,
    // AI 局部结果可能只返回变更字段；缺失字段必须保留当前 PPT 内容。
    script: hasField(n, 'script') ? (n.script || '') : (n.content || currentById.get(n.node_id)?.script || currentById.get(n.node_id)?.content || ''),
    segments: hasField(n, 'segments') ? (n.segments || []) : (currentById.get(n.node_id)?.segments || []),
    citation_refs: n.citation_refs || currentById.get(n.node_id)?.citation_refs || [],
    source_chunk_ids: n.source_chunk_ids || currentById.get(n.node_id)?.source_chunk_ids || [],
    interactive_plan: n.interactive_plan || currentById.get(n.node_id)?.interactive_plan || null,
  })
  const normalized = allNodes.map(normalize)
  if (generationStore.currentScriptNodes?.length || generationStore.lastGenId) {
    // all_nodes 才是后端修改后的完整权威结果，不能依赖 modified_nodes 是否完整。
    generationStore.setNodes(normalized)
    generationStore.setScript(
      normalized.map((node) => node.script || node.content || node.summary || '').filter(Boolean).join('\n\n'),
    )
  } else {
    outlineStore.nodes = normalized
    outlineStore._reorder()
    outlineStore._persist()
  }

  // 页面负责重新渲染预览并持久化草稿，修改面板只应用结构化结果。
  emit('applied', { allNodes: normalized, modifiedNodes, intent, instruction, presentation })
}

async function handleSend() {
  await modifyStore.sendModify(nodesForApi(), applyResult)
  scrollToBottom()
}

async function handleUndo() {
  await modifyStore.undo(nodesForApi(), applyResult)
}

async function handleRedo() {
  await modifyStore.redo(applyResult)
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

// 修改执行后滚动到底部
watch(() => modifyStore.messages.length, scrollToBottom)
</script>

<style scoped>
.modify-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-left: 1px solid var(--border, #e0e0e0);
  background: var(--panel-bg, #fafafa);
  min-width: 320px;
  max-width: 400px;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border, #e0e0e0);
}

.panel-title { font-weight: 600; font-size: 14px; }

.version-badge {
  font-size: 12px;
  color: #666;
  background: #eef;
  border-radius: 4px;
  padding: 2px 6px;
}

.undo-redo { margin-left: auto; }

.icon-btn {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 16px;
  padding: 2px 4px;
  border-radius: 4px;
}
.icon-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.icon-btn:hover:not(:disabled) { background: #eee; }

.active-page-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #eee;
  background: #f6f9ff;
}
.apb-label { font-size: 12px; color: #4a5b70; white-space: nowrap; }
.apb-select {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  padding: 3px 6px;
  border: 1px solid #ccd8e6;
  border-radius: 6px;
  background: #fff;
  color: #33443e;
  cursor: pointer;
}
.apb-select:disabled { opacity: 0.5; cursor: not-allowed; }

.quick-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid #eee;
}

.chip-btn {
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid #d0d0d0;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  transition: background 0.15s;
}
.chip-btn:hover:not(:disabled) { background: #f0f4ff; }
.chip-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty-hint {
  color: #999;
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

.message {
  max-width: 85%;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.4;
  display: flex;
  align-items: center;
  gap: 6px;
}

.msg-right {
  align-self: flex-end;
  background: #4a90d9;
  color: #fff;
}

.msg-left {
  align-self: flex-start;
  background: #fff;
  border: 1px solid #e0e0e0;
}

.msg-error {
  background: #fee;
  color: #c33;
  border-color: #fcc;
}

.msg-version {
  font-size: 10px;
  opacity: 0.7;
  white-space: nowrap;
}

.error-bar {
  padding: 6px 12px;
  background: #fee;
  color: #c33;
  font-size: 12px;
  border-top: 1px solid #fcc;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.ai-working{display:flex;align-items:center;gap:11px;margin:10px 12px 0;padding:12px;border:1px solid #cde2da;border-radius:11px;background:linear-gradient(110deg,#eff9f5,#fff);color:#28594c}.ai-working strong{font-size:13px}.ai-working p{margin:3px 0 0;color:#789087;font-size:11px}.ai-working-spinner{width:22px;height:22px;flex:0 0 auto;border:3px solid #d6e9e1;border-top-color:#28735f;border-radius:50%;animation:ai-spin .75s linear infinite}@keyframes ai-spin{to{transform:rotate(360deg)}}
.error-bar button { border:0; background:transparent; color:#9f2525; text-decoration:underline; cursor:pointer; }
.clarification-context { display:grid; gap:3px; margin:8px 12px 0; padding:8px 10px; border:1px solid #ead8a3; border-radius:8px; background:#fff9e8; color:#795a12; font-size:11px; }

.input-area {
  position: relative;
  display: flex;
  gap: 6px;
  padding: 10px 12px;
  border-top: 1px solid #e0e0e0;
}

.modify-input {
  flex: 1;
  border: 1px solid #d0d0d0;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
  outline: none;
  resize: vertical;
  min-height: 34px;
  max-height: 110px;
  font-family: inherit;
}
.modify-input:focus { border-color: #4a90d9; }

.send-btn {
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  background: #4a90d9;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.char-count { position:absolute; right:72px; bottom:12px; color:#98a19d; font-size:9px; pointer-events:none; }
.char-count.limit { color:#b45a21; }

.version-timeline {
  border-top: 1px solid #e0e0e0;
  padding: 8px 12px;
  max-height: 150px;
  overflow-y: auto;
}
.version-timeline summary {
  font-size: 12px;
  cursor: pointer;
  color: #666;
}

.timeline-item {
  width: 100%;
  border: 0;
  background: transparent;
  cursor: pointer;
  display: flex;
  gap: 8px;
  font-size: 11px;
  padding: 3px 0;
  align-items: center;
}
.timeline-item:hover { background: #f2f6ff; }
.tl-version { font-weight: 600; color: #4a90d9; min-width: 30px; }
.change-kind { padding:1px 5px; border-radius:999px; font-size:10px; background:#eaf6f0; color:#26715f; }
.change-kind.style { background:#f1edff; color:#6845aa; }
.tl-instr { flex: 1; color: #555; }
.tl-time { color: #aaa; white-space: nowrap; }
.live-preview { border-top: 1px solid #e0e0e0; padding: 10px 12px; max-height: 250px; overflow-y: auto; }
.preview-head,.preview-node-head,.history-head { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.preview-head { margin-bottom:8px; font-size:12px; }
.preview-head span { color:#78828c; font-size:11px; }
.preview-node { margin:6px 0; padding:8px; border:1px solid #e0e7e4; border-radius:8px; background:#fff; cursor:pointer; transition:border-color .25s,box-shadow .25s,background .25s; }
.preview-node:hover { background:#f7faf9; }
.preview-node:focus-visible { outline:2px solid #4a90d9; outline-offset:2px; }
.preview-node.active { border-color:#4a90d9; background:#f4f8ff; box-shadow:inset 3px 0 0 #4a90d9; }
.preview-node.modified { border-color:#24a36f; background:#edfff7; box-shadow:0 0 0 3px rgba(36,163,111,.14); animation:modifiedPulse 2s ease-out; }
.active-badge { padding:2px 6px; border-radius:999px; background:#4a90d9; color:#fff; font-size:10px; white-space:nowrap; }
.preview-node-head { color:#33443e; font-size:12px; font-weight:650; }
.preview-node p,.history-nodes p { margin:5px 0 0; color:#66736f; font-size:11px; line-height:1.45; white-space:pre-wrap; }
.preview-node p { display:-webkit-box; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:3; }
.modified-badge { padding:2px 6px; border-radius:999px; background:#24a36f; color:#fff; font-size:10px; }
.history-preview { position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:20px; background:rgba(17,31,27,.42); }
.history-card { width:min(720px,calc(100vw - 40px)); max-height:80vh; overflow:hidden; border-radius:14px; background:#fff; box-shadow:0 24px 80px rgba(0,0,0,.2); }
.history-head { padding:16px 18px; border-bottom:1px solid #e5ebe8; }
.history-head p { margin:4px 0 0; color:#68746f; font-size:12px; }
.history-nodes { max-height:60vh; overflow-y:auto; padding:14px 18px; }
.history-nodes article { padding:10px 0; border-bottom:1px solid #edf1ef; }
@keyframes modifiedPulse { 0% { transform:scale(.99); } 25% { transform:scale(1); } 100% { box-shadow:none; } }
@media (max-width:680px) {
  .modify-panel { min-width:0; max-width:none; }
  .panel-header { align-items:flex-start; flex-wrap:wrap; }
  .version-badge { order:3; width:100%; box-sizing:border-box; }
  .live-preview { max-height:210px; }
  .tl-time { display:none; }
}
</style>
