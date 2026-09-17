<template>
  <div class="modify-panel" v-if="modifyStore.projectId">
    <div class="panel-header">
      <span class="panel-title">🤖 AI 修改</span>
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

    <!-- 版本时间线（C7，展开后显示） -->
    <details v-if="modifyStore.versionHistory.length > 0" class="version-timeline">
      <summary>📜 修改历史（{{ modifyStore.versionHistory.length }} 条）</summary>
      <div v-for="v in modifyStore.versionHistory" :key="v.version_no" class="timeline-item">
        <span class="tl-version">v{{ v.version_no }}</span>
        <span class="tl-instr">{{ v.modify_instruction || '(初始版本)' }}</span>
        <span class="tl-time">{{ v.created_at }}</span>
      </div>
    </details>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useModifyStore } from '../../stores/modifyStore'
import { useOutlineStore } from '../../stores/outlineStore'

const modifyStore = useModifyStore()
const outlineStore = useOutlineStore()
const messagesEl = ref(null)

// 节点转 TeachingNodeItem 格式（outlineStore.nodes → Go TeachingNodeItem JSON）
function nodesForApi() {
  return (outlineStore.nodes || []).map((n) => ({
    node_id: n.node_id,
    title: n.title,
    summary: n.summary,
    node_type: n.node_type,
    key_points: n.key_points || [],
    core_points: n.key_points || [],
    script: n.script || '',
    segments: n.segments || [],
    estimated_duration_minutes: n.estimated_duration_minutes || 5,
    citation_refs: n.citation_refs || [],
    source_chunk_ids: n.source_chunk_ids || [],
  }))
}

// 修改结果写回 outlineStore
function applyResult(allNodes) {
  if (!Array.isArray(allNodes)) return
  outlineStore.nodes = allNodes.map((n) => ({
    node_id: n.node_id,
    title: n.title,
    summary: n.summary,
    node_type: n.node_type || 'content',
    key_points: n.key_points || [],
    estimated_duration_minutes: n.estimated_duration_minutes || 5,
    script: n.script || '',
    segments: n.segments || [],
    citation_refs: n.citation_refs || [],
    source_chunk_ids: n.source_chunk_ids || [],
    interactive_plan: n.interactive_plan || null,
  }))
  outlineStore._reorder()
  outlineStore._persist()
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
  display: flex;
  gap: 8px;
  font-size: 11px;
  padding: 3px 0;
  align-items: center;
}
.tl-version { font-weight: 600; color: #4a90d9; min-width: 30px; }
.tl-instr { flex: 1; color: #555; }
.tl-time { color: #aaa; white-space: nowrap; }
</style>
