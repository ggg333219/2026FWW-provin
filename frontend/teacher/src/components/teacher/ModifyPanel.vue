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

    <!-- 快捷指令 -->
    <div class="quick-chips">
      <button v-for="chip in modifyStore.quickChips" :key="chip.label"
        class="chip-btn" :disabled="modifyStore.modifying"
        @click="modifyStore.applyQuickChip(chip)">
        {{ chip.label }}
      </button>
    </div>

    <!-- 对话区 -->
    <div class="messages-area" ref="messagesEl">
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
    <div v-if="modifyStore.error" class="error-bar">{{ modifyStore.error }}</div>

    <!-- 输入区 -->
    <div class="input-area">
      <input type="text" v-model="modifyStore.inputText"
        placeholder="例如：第三页减少文字，增加一个生活案例"
        :disabled="modifyStore.modifying"
        @keydown.enter="handleSend"
        class="modify-input" />
      <button class="send-btn" :disabled="!modifyStore.canSend"
        @click="handleSend">
        {{ modifyStore.modifying ? '⏳' : '发送' }}
      </button>
    </div>

    <section v-if="liveNodes.length" class="live-preview" aria-label="节点局部预览">
      <div class="preview-head">
        <strong>局部预览</strong>
        <span>仅更新发生变化的节点</span>
      </div>
      <article v-for="(node, index) in liveNodes" :key="node.node_id || index"
        :class="['preview-node', { modified: isRecentlyModified(node) }]">
        <div class="preview-node-head">
          <span>第 {{ index + 1 }} 页 · {{ node.title || '未命名节点' }}</span>
          <span v-if="isRecentlyModified(node)" class="modified-badge">已修改</span>
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
    </details>

    <div v-if="selectedVersion" class="history-preview" role="dialog" aria-modal="true" aria-label="历史版本只读预览">
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
import { computed, ref, watch, nextTick } from 'vue'
import { useModifyStore } from '../../stores/modifyStore'
import { useOutlineStore } from '../../stores/outlineStore'
import { useGenerationStore } from '../../stores/generationStore'

const modifyStore = useModifyStore()
const outlineStore = useOutlineStore()
const generationStore = useGenerationStore()
const messagesEl = ref(null)
const selectedVersion = ref(null)
const emit = defineEmits(['style-request'])
const liveNodes = computed(() => generationStore.currentScriptNodes?.length
  ? generationStore.currentScriptNodes
  : outlineStore.nodes)
const isRecentlyModified = (node) => modifyStore.recentlyModifiedIds.includes(node.node_id)
const previewVersion = (version) => { selectedVersion.value = version }
const changeKind = (version) => /风格|样式|模板|配色|字体|版式|style|template/i.test(version?.modify_instruction || '') ? 'style' : 'content'

// 节点转 TeachingNodeItem 格式（outlineStore.nodes → Go TeachingNodeItem JSON）
function nodesForApi() {
  const source = generationStore.currentScriptNodes?.length
    ? generationStore.currentScriptNodes
    : outlineStore.nodes
  return (source || []).map((n) => ({
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
    script: n.script || '',
    segments: n.segments || [],
    citation_refs: n.citation_refs || [],
    source_chunk_ids: n.source_chunk_ids || [],
    interactive_plan: n.interactive_plan || null,
  })
  const normalized = allNodes.map(normalize)
  if (generationStore.currentScriptNodes?.length || generationStore.lastGenId) {
    const changedById = new Map((modifiedNodes || []).map((node) => [node.node_id, normalize(node)]))
    const structuralChange = normalized.length !== generationStore.currentScriptNodes.length
      || normalized.some((node, index) => generationStore.currentScriptNodes[index]?.node_id !== node.node_id)
    if (structuralChange) {
      generationStore.setNodes(normalized)
    } else {
      generationStore.currentScriptNodes.forEach((node, index) => {
        const changed = changedById.get(node.node_id)
        if (changed) generationStore.updateNode(index, changed)
      })
    }
    generationStore.setScript(
      normalized.map((node) => node.script || node.content || node.summary || '').filter(Boolean).join('\n\n'),
    )
  } else {
    outlineStore.nodes = normalized
    outlineStore._reorder()
    outlineStore._persist()
  }
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
}

.input-area {
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
.preview-node { margin:6px 0; padding:8px; border:1px solid #e0e7e4; border-radius:8px; background:#fff; transition:border-color .25s,box-shadow .25s,background .25s; }
.preview-node.modified { border-color:#24a36f; background:#edfff7; box-shadow:0 0 0 3px rgba(36,163,111,.14); animation:modifiedPulse 2s ease-out; }
.preview-node-head { color:#33443e; font-size:12px; font-weight:650; }
.preview-node p,.history-nodes p { margin:5px 0 0; color:#66736f; font-size:11px; line-height:1.45; white-space:pre-wrap; }
.modified-badge { padding:2px 6px; border-radius:999px; background:#24a36f; color:#fff; font-size:10px; }
.history-preview { position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:20px; background:rgba(17,31,27,.42); }
.history-card { width:min(720px,calc(100vw - 40px)); max-height:80vh; overflow:hidden; border-radius:14px; background:#fff; box-shadow:0 24px 80px rgba(0,0,0,.2); }
.history-head { padding:16px 18px; border-bottom:1px solid #e5ebe8; }
.history-head p { margin:4px 0 0; color:#68746f; font-size:12px; }
.history-nodes { max-height:60vh; overflow-y:auto; padding:14px 18px; }
.history-nodes article { padding:10px 0; border-bottom:1px solid #edf1ef; }
@keyframes modifiedPulse { 0% { transform:scale(.99); } 25% { transform:scale(1); } 100% { box-shadow:none; } }
</style>
