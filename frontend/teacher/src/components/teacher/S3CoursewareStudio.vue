<template>
  <div class="s3-courseware-studio">
    <!-- 顶部状态栏 -->
    <header class="studio-header">
      <div class="studio-header__left">
        <h2 class="studio-header__title">课件生成工作台</h2>
        <span class="studio-header__badge" :class="statusClass">{{ statusLabel }}</span>
      </div>
      <div class="studio-header__right">
        <button
          class="studio-btn studio-btn--primary"
          :disabled="isGenerating"
          @click="handleGenerate"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="btn-icon">
            <path d="M12 2v20M2 12h20" />
          </svg>
          {{ isGenerating ? '生成中…' : '开始生成' }}
        </button>
      </div>
    </header>

    <!-- 生成进度条 -->
    <div v-if="isGenerating" class="studio-progress">
      <div class="studio-progress__bar">
        <div class="studio-progress__fill" :style="{ width: progressPercent + '%' }" />
      </div>
      <div class="studio-progress__info">
        <span class="studio-progress__text">{{ progressText }}</span>
        <span class="studio-progress__pct">{{ Math.round(progressPercent) }}%</span>
      </div>
    </div>

    <!-- 主面板：四宫格布局 -->
    <div class="studio-panels">
      <!-- 左上：OutlineView 节点树 -->
      <section class="studio-panel studio-panel--outline">
        <header class="panel-header">
          <h3 class="panel-title">节点大纲</h3>
          <span class="panel-count">{{ outlineNodes.length }} 个节点</span>
        </header>
        <div class="panel-body">
          <LoadingState v-if="outlineLoading" type="loading" text="加载节点树…" size="sm" />
          <LoadingState
            v-else-if="outlineNodes.length === 0"
            type="empty"
            icon="node"
            text="暂无节点"
            hint="点击「开始生成」创建课件大纲"
            size="sm"
          />
          <div v-else class="outline-tree">
            <div
              v-for="(node, idx) in outlineNodes"
              :key="node.node_id || node.id || idx"
              class="outline-node"
              :class="{
                'outline-node--active': activeNodeId === (node.node_id || node.id),
                'outline-node--completed': node.status === 'completed' || node.completed,
                'outline-node--generating': node.status === 'generating'
              }"
              @click="selectNode(node)"
            >
              <div class="outline-node__index">{{ idx + 1 }}</div>
              <div class="outline-node__content">
                <div class="outline-node__title">{{ node.title || '未命名节点' }}</div>
                <div class="outline-node__summary">{{ node.summary || node.content || '' }}</div>
              </div>
              <div class="outline-node__status">
                <span v-if="node.status === 'completed' || node.completed" class="status-dot status-dot--done" title="已完成">✓</span>
                <span v-else-if="node.status === 'generating'" class="status-dot status-dot--busy" title="生成中">◌</span>
                <span v-else class="status-dot status-dot--pending" title="待生成">○</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 右上：NodeEditorView 节点编辑 -->
      <section class="studio-panel studio-panel--editor">
        <header class="panel-header">
          <h3 class="panel-title">节点编辑</h3>
          <button
            v-if="editingNode"
            class="studio-btn studio-btn--sm"
            @click="saveNodeEdit"
            :disabled="!hasEditChanges"
          >保存修改</button>
        </header>
        <div class="panel-body">
          <LoadingState
            v-if="!editingNode"
            type="empty"
            icon="file"
            text="请选择一个节点"
            hint="点击左侧大纲中的节点进行编辑"
            size="sm"
          />
          <div v-else class="node-editor">
            <div class="node-editor__field">
              <label class="node-editor__label">标题</label>
              <input
                v-model="editForm.title"
                class="node-editor__input"
                placeholder="节点标题"
                @input="markEditChanged"
              />
            </div>
            <div class="node-editor__field">
              <label class="node-editor__label">内容</label>
              <textarea
                v-model="editForm.content"
                class="node-editor__textarea"
                placeholder="节点内容 / 讲稿"
                rows="8"
                @input="markEditChanged"
              />
            </div>
            <div class="node-editor__field">
              <label class="node-editor__label">摘要</label>
              <input
                v-model="editForm.summary"
                class="node-editor__input"
                placeholder="简要摘要"
                @input="markEditChanged"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- 左下：PreviewCanvas 预览 -->
      <section class="studio-panel studio-panel--preview">
        <header class="panel-header">
          <h3 class="panel-title">课件预览</h3>
          <div class="panel-header__right">
            <button
              class="studio-btn studio-btn--sm"
              :disabled="!previewHtml"
              @click="handlePreview"
            >刷新预览</button>
          </div>
        </header>
        <div class="panel-body">
          <LoadingState
            v-if="!previewHtml && !previewLoading"
            type="empty"
            icon="box"
            text="暂无预览"
            hint="生成课件后自动生成预览，或点击「刷新预览」"
            size="sm"
          />
          <LoadingState v-else-if="previewLoading" type="loading" text="加载预览…" size="sm" variant="dots" />
          <div v-else class="preview-canvas" v-html="previewHtml" />
        </div>
      </section>

      <!-- 右下：GenerationLog 生成日志 -->
      <section class="studio-panel studio-panel--log">
        <header class="panel-header">
          <h3 class="panel-title">生成日志</h3>
          <button
            v-if="generationLogs.length > 0"
            class="studio-btn studio-btn--sm"
            @click="clearLogs"
          >清空</button>
        </header>
        <div class="panel-body">
          <LoadingState
            v-if="generationLogs.length === 0"
            type="empty"
            icon="box"
            text="暂无日志"
            hint="生成操作日志将显示在这里"
            size="sm"
          />
          <div v-else class="generation-log">
            <div
              v-for="(log, idx) in generationLogs"
              :key="idx"
              class="log-entry"
              :class="`log-entry--${log.level || 'info'}`"
            >
              <span class="log-entry__time">{{ log.time }}</span>
              <span class="log-entry__msg">{{ log.message }}</span>
            </div>
            <div ref="logEnd" />
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useGenerationStore } from '../../stores/generationStore'
import { useWorkspaceStore } from '../../stores/workspaceStore'
import LoadingState from '../common/LoadingState.vue'

const emit = defineEmits(['generate', 'preview', 'save-nodes', 'sync-nodes'])

const generationStore = useGenerationStore()
const workspaceStore = useWorkspaceStore()

// 状态
const outlineNodes = computed(() => generationStore.currentScriptNodes || [])
const outlineLoading = ref(false)
const activeNodeId = ref('')
const editingNode = ref(null)
const editForm = ref({ title: '', content: '', summary: '' })
const hasEditChanges = ref(false)
const previewHtml = ref('')
const previewLoading = ref(false)
const generationLogs = ref([])
const logEnd = ref(null)

const isGenerating = computed(() => generationStore.isGenerating)
const progressPercent = computed(() => generationStore.generateProgress || 0)
const progressText = computed(() => generationStore.generateStageText || '准备中…')

const statusClass = computed(() => {
  if (generationStore.isGenerating) return 'badge--busy'
  if (outlineNodes.value.length > 0) return 'badge--ready'
  return 'badge--idle'
})
const statusLabel = computed(() => {
  if (generationStore.isGenerating) return '生成中'
  if (outlineNodes.value.length > 0) return '已就绪'
  return '待开始'
})

function addLog(message, level = 'info') {
  const now = new Date()
  const time = now.toLocaleTimeString('zh-CN', { hour12: false })
  generationLogs.value.push({ time, message, level })
  nextTick(() => {
    logEnd.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

function selectNode(node) {
  const nodeId = node.node_id || node.id
  activeNodeId.value = nodeId
  editingNode.value = node
  editForm.value = {
    title: node.title || '',
    content: node.content || node.scriptText || node.script || '',
    summary: node.summary || ''
  }
  hasEditChanges.value = false
}

function markEditChanged() {
  hasEditChanges.value = true
}

function saveNodeEdit() {
  if (!editingNode.value) return
  const nodeId = editingNode.value.node_id || editingNode.value.id
  const idx = generationStore.currentScriptNodes.findIndex(
    n => (n.node_id || n.id) === nodeId
  )
  if (idx >= 0) {
    generationStore.updateNode(idx, {
      title: editForm.value.title,
      content: editForm.value.content,
      summary: editForm.value.summary
    })
    editingNode.value = { ...generationStore.currentScriptNodes[idx] }
    hasEditChanges.value = false
    addLog(`已保存节点「${editForm.value.title}」`, 'success')
    emit('sync-nodes', generationStore.currentScriptNodes)
  }
}

function handleGenerate() {
  addLog('开始生成课件…', 'info')
  generationStore.setGenerating(true)
  generationStore.setGenerateProgress(10, '正在创建大纲…')
  emit('generate')
}

function handlePreview() {
  previewLoading.value = true
  addLog('请求预览…', 'info')
  emit('preview')
}

function clearLogs() {
  generationLogs.value = []
}

// 监听 Store 变化
watch(() => generationStore.currentScriptNodes, (nodes) => {
  if (nodes.length > 0 && !activeNodeId.value) {
    selectNode(nodes[0])
  }
}, { deep: true })

watch(() => generationStore.isGenerating, (v) => {
  if (!v) {
    addLog('生成完成', 'success')
  }
})

// 暴露方法给父组件
function setPreviewHtml(html) {
  previewHtml.value = html
  previewLoading.value = false
  addLog('预览已更新', 'success')
}

function setPreviewError(msg) {
  previewLoading.value = false
  addLog(`预览失败: ${msg}`, 'error')
}

function setOutlineNodes(nodes) {
  outlineLoading.value = false
  if (nodes.length > 0) {
    selectNode(nodes[0])
  }
}

defineExpose({ setPreviewHtml, setPreviewError, setOutlineNodes, addLog })
</script>

<style scoped>
.s3-courseware-studio {
  display: flex; flex-direction: column; gap: 12px;
  height: 100%; padding: 16px;
}

/* 头部 */
.studio-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; background: #fff; border-radius: 12px; border: 1px solid #e2e8f0;
}
.studio-header__left { display: flex; align-items: center; gap: 12px; }
.studio-header__title { margin: 0; font-size: 18px; color: #111827; }
.studio-header__badge {
  padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 500;
}
.badge--idle { background: #f1f5f9; color: #64748b; }
.badge--ready { background: #ecfdf5; color: #065f46; }
.badge--busy { background: #fef3c7; color: #92400e; animation: pulse 1.5s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }

/* 按钮 */
.studio-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border: 1px solid #e2e8f0; border-radius: 8px;
  background: #fff; color: #475569; font-size: 13px; cursor: pointer;
  transition: all 0.15s; white-space: nowrap;
}
.studio-btn:hover { border-color: #2d5f58; color: #2d5f58; }
.studio-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.studio-btn--primary {
  background: #2d5f58; color: #fff; border-color: #2d5f58;
}
.studio-btn--primary:hover { background: #234a44; color: #fff; }
.studio-btn--sm { padding: 4px 12px; font-size: 12px; }
.btn-icon { width: 16px; height: 16px; }

/* 进度条 */
.studio-progress {
  padding: 12px 16px; background: #fff; border-radius: 12px; border: 1px solid #e2e8f0;
}
.studio-progress__bar {
  height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden;
}
.studio-progress__fill {
  height: 100%; background: linear-gradient(90deg, #2d5f58, #4a9e8e);
  border-radius: 3px; transition: width 0.3s ease;
}
.studio-progress__info {
  display: flex; justify-content: space-between; margin-top: 6px;
  font-size: 12px; color: #64748b;
}

/* 面板网格 */
.studio-panels {
  display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr;
  gap: 12px; flex: 1; min-height: 0;
}
.studio-panel {
  display: flex; flex-direction: column;
  background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; border-bottom: 1px solid #f1f5f9; flex-shrink: 0;
}
.panel-title { margin: 0; font-size: 14px; font-weight: 600; color: #1e293b; }
.panel-count { font-size: 12px; color: #94a3b8; }
.panel-header__right { display: flex; gap: 6px; }
.panel-body { flex: 1; overflow-y: auto; min-height: 0; }

/* 节点树 */
.outline-tree { padding: 8px; }
.outline-node {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; border-radius: 8px; cursor: pointer;
  transition: all 0.15s; border: 1px solid transparent; margin-bottom: 4px;
}
.outline-node:hover { background: #f8fafc; border-color: #e2e8f0; }
.outline-node--active { background: #ecfdf5; border-color: #2d5f58; }
.outline-node__index {
  width: 24px; height: 24px; border-radius: 50%;
  background: #f1f5f9; color: #64748b;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600; flex-shrink: 0;
}
.outline-node--active .outline-node__index { background: #2d5f58; color: #fff; }
.outline-node__content { flex: 1; min-width: 0; }
.outline-node__title { font-size: 13px; font-weight: 500; color: #1e293b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.outline-node__summary { font-size: 11px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; }
.outline-node__status { flex-shrink: 0; }
.status-dot { font-size: 14px; }
.status-dot--done { color: #10b981; }
.status-dot--busy { color: #f59e0b; animation: pulse 1s ease-in-out infinite; }
.status-dot--pending { color: #d1d5db; }

/* 节点编辑器 */
.node-editor { padding: 14px; display: flex; flex-direction: column; gap: 12px; }
.node-editor__field { display: flex; flex-direction: column; gap: 4px; }
.node-editor__label { font-size: 12px; font-weight: 500; color: #475569; }
.node-editor__input {
  padding: 8px 10px; border: 1px solid #e2e8f0; border-radius: 6px;
  font-size: 13px; color: #1e293b; outline: none; transition: border-color 0.15s;
}
.node-editor__input:focus { border-color: #2d5f58; }
.node-editor__textarea {
  padding: 8px 10px; border: 1px solid #e2e8f0; border-radius: 6px;
  font-size: 13px; color: #1e293b; outline: none; resize: vertical;
  font-family: inherit; line-height: 1.5; transition: border-color 0.15s;
}
.node-editor__textarea:focus { border-color: #2d5f58; }

/* 预览 */
.preview-canvas { padding: 14px; }
.preview-canvas :deep(h1) { font-size: 20px; color: #111827; margin: 0 0 8px; }
.preview-canvas :deep(h2) { font-size: 16px; color: #1e293b; margin: 12px 0 6px; }
.preview-canvas :deep(p) { font-size: 13px; color: #475569; line-height: 1.6; margin: 0 0 8px; }
.preview-canvas :deep(ul) { margin: 4px 0; padding-left: 20px; }
.preview-canvas :deep(li) { font-size: 13px; color: #475569; line-height: 1.5; }

/* 日志 */
.generation-log { padding: 8px; font-family: 'SF Mono', 'Monaco', monospace; font-size: 12px; }
.log-entry { padding: 4px 8px; display: flex; gap: 8px; line-height: 1.5; }
.log-entry--info { color: #475569; }
.log-entry--success { color: #065f46; }
.log-entry--error { color: #dc2626; }
.log-entry--warn { color: #92400e; }
.log-entry__time { color: #94a3b8; flex-shrink: 0; }
</style>