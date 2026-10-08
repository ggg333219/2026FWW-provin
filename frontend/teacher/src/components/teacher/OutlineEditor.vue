<template>
  <div class="outline-editor">
    <!-- 大纲头部信息 -->
    <div class="outline-header">
      <div class="outline-meta">
        <span class="outline-id" v-if="outlineStore.outline_id">
          大纲 ID：{{ outlineStore.outline_id }}
        </span>
        <span class="outline-version" v-if="outlineStore.outline_version">
          v{{ outlineStore.outline_version }}
        </span>
        <span class="outline-status" :class="`status-${outlineStore.status}`">
          {{ statusLabel }}
        </span>
        <span class="outline-duration">
          ⏱ 总计 {{ outlineStore.totalDuration }} 分钟 · {{ outlineStore.nodeCount }} 个节点
        </span>
      </div>
      <div class="outline-actions">
        <button
          v-if="outlineStore.canEdit"
          class="btn btn-sm"
          :disabled="outlineStore.reviseLoading"
          @click="showReviseInput = true"
          title="发送指令让 AI 修改大纲"
        >
          {{ outlineStore.reviseLoading ? 'AI 修订中...' : '🤖 AI 修订' }}
        </button>
        <button
          v-if="outlineStore.canEdit"
          class="btn btn-sm"
          :disabled="outlineStore.loading"
          @click="handleSave"
        >
          保存大纲
        </button>
        <button
          v-if="outlineStore.isConfirmed"
          class="btn btn-sm btn-primary"
          @click="$emit('confirm-complete')"
        >
          进入内容生成 →
        </button>
        <button
          v-else-if="outlineStore.canEdit && outlineStore.nodeCount > 0"
          class="btn btn-sm btn-primary"
          :disabled="outlineStore.loading"
          @click="handleConfirm"
        >
          {{ outlineStore.loading ? '确认中...' : '确认大纲' }}
        </button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="outlineStore.error || outlineStore.confirmError || outlineStore.reviseError" class="error-bar" role="alert">
      {{ outlineStore.confirmError || outlineStore.reviseError || outlineStore.error }}
    </div>

    <div v-if="outlineStore.fallbackNotice" class="fallback-notice" role="status" aria-live="polite">
      {{ outlineStore.fallbackNotice }}
    </div>

    <!-- 节点编辑器 -->
    <div class="nodes-list">
      <TransitionGroup name="node-list">
        <div
          v-for="(node, idx) in outlineStore.nodes"
          :key="node.node_id"
          class="outline-node-card"
          :class="[`node-type-${node.node_type}`, { dragging: draggedNodeId === node.node_id, 'drag-over': dragOverIndex === idx }]"
          @dragover.prevent="handleDragOver($event, idx)"
          @dragenter.prevent="handleDragOver($event, idx)"
          @drop.prevent="handleDrop($event, idx)"
          @dragend="handleDragEnd"
        >
          <!-- 节点序号 & 移动按钮 -->
          <div
            class="node-drag-handle"
            :draggable="outlineStore.canReorder"
            :title="outlineStore.canReorder ? '按住拖动排序' : ''"
            :aria-label="outlineStore.canReorder ? `拖动第 ${idx + 1} 个节点排序` : undefined"
            @dragstart="handleDragStart($event, node.node_id)"
          >
            <span v-if="outlineStore.canReorder" class="drag-grip" aria-hidden="true">⠿</span>
            <span class="node-order">{{ idx + 1 }}</span>
            <div class="node-move-btns" v-if="outlineStore.canReorder">
              <button
                class="move-btn"
                :disabled="idx === 0"
                @click="outlineStore.moveNode(node.node_id, 'up')"
                title="上移"
              >↑</button>
              <button
                class="move-btn"
                :disabled="idx === outlineStore.nodes.length - 1"
                @click="outlineStore.moveNode(node.node_id, 'down')"
                title="下移"
              >↓</button>
            </div>
          </div>

          <!-- 节点内容 -->
          <div class="node-content">
            <div class="node-top-row">
              <!-- 节点类型选择 -->
              <select
                v-if="outlineStore.canEdit"
                v-model="node.node_type"
                class="node-type-select"
                @change="outlineStore.updateNode(node.node_id, { node_type: node.node_type })"
              >
                <option value="content">📖 知识讲解</option>
                <option value="section">📂 章节标题</option>
                <option value="quiz">❓ 随堂测验</option>
                <option value="interactive">🎮 互动环节</option>
                <option value="summary">📋 总结回顾</option>
              </select>
              <span v-else class="node-type-badge">{{ node.node_type }}</span>

              <!-- 标题 -->
              <input
                v-if="outlineStore.canEdit"
                v-model="node.title"
                class="node-title-input"
                placeholder="节点标题"
                @input="outlineStore.updateNode(node.node_id, { title: node.title })"
              />
              <div v-else class="node-title">{{ node.title }}</div>
            </div>

            <!-- 摘要 -->
            <textarea
              v-if="outlineStore.canEdit"
              v-model="node.summary"
              class="node-summary-input"
              placeholder="节点摘要（简述本节点教学内容）"
              rows="2"
              @input="outlineStore.updateNode(node.node_id, { summary: node.summary })"
            ></textarea>
            <p v-else class="node-summary">{{ node.summary }}</p>

            <!-- 核心知识点标签 -->
            <div class="node-key-points">
              <span class="kp-label">核心知识点：</span>
              <template v-if="outlineStore.canEdit">
                <div class="kp-tags">
                  <span
                    v-for="(kp, ki) in node.key_points"
                    :key="ki"
                    class="kp-tag"
                  >
                    {{ kp }}
                    <button class="kp-remove" @click="removeKeyPoint(node, ki)">×</button>
                  </span>
                  <input
                    v-model="newKeyPoints[node.node_id]"
                    class="kp-add-input"
                    placeholder="+ 添加知识点"
                    @keyup.enter="addKeyPoint(node)"
                  />
                </div>
              </template>
              <template v-else>
                <span v-for="(kp, ki) in node.key_points" :key="ki" class="kp-tag-static">
                  {{ kp }}
                </span>
              </template>
            </div>

            <!-- 互动规划（仅 interactive / quiz 类型且有 plan 时显示）
                 注意：必须判 interactive_plan 非空——后端/LLM 产出的交互节点该字段常为 null，
                 直接访问 interactive_plan.x 会抛错并中断整个节点列表渲染。 -->
            <div
              v-if="(node.node_type === 'interactive' || node.node_type === 'quiz') && node.interactive_plan && outlineStore.canEdit"
              class="node-interactive-plan"
            >
              <details>
                <summary class="plan-toggle">🎯 互动规划</summary>
                <div class="plan-fields">
                  <label>
                    时长（分钟）
                    <input
                      type="number"
                      v-model.number="node.interactive_plan.duration_minutes"
                      min="1"
                      max="60"
                      @change="outlineStore.updateNode(node.node_id, { interactive_plan: { ...node.interactive_plan } })"
                    />
                  </label>
                  <label>
                    题目数量
                    <input
                      type="number"
                      v-model.number="node.interactive_plan.question_count"
                      min="1"
                      max="20"
                      @change="outlineStore.updateNode(node.node_id, { interactive_plan: { ...node.interactive_plan } })"
                    />
                  </label>
                  <label>
                    自动判分
                    <input
                      type="checkbox"
                      v-model="node.interactive_plan.auto_grading"
                      @change="outlineStore.updateNode(node.node_id, { interactive_plan: { ...node.interactive_plan } })"
                    />
                  </label>
                  <label>
                    产出方式
                    <select v-model="node.interactive_plan.delivery">
                      <option value="html5_link">HTML5 链接</option>
                      <option value="ppt_native">PPT 内嵌</option>
                      <option value="standalone_html">独立 HTML</option>
                    </select>
                  </label>
                </div>
              </details>
            </div>

            <!-- 时长 -->
            <div class="node-footer">
              <label class="duration-label">
                时长
                <input
                  type="number"
                  v-model.number="node.estimated_duration_minutes"
                  min="1"
                  max="180"
                  :disabled="!outlineStore.canEdit"
                  class="duration-input"
                  @change="outlineStore.updateNode(node.node_id, { estimated_duration_minutes: node.estimated_duration_minutes })"
                />
                分钟
              </label>

              <!-- 删除按钮 -->
              <button
                v-if="outlineStore.canEdit"
                class="node-delete-btn"
                @click="handleDeleteNode(node.node_id)"
                title="删除节点"
              >🗑</button>
            </div>
          </div>
        </div>
      </TransitionGroup>

      <!-- 添加节点按钮 -->
      <div v-if="outlineStore.canEdit" class="add-node-row">
        <button class="btn btn-outline add-node-btn" @click="handleAddNode">
          ＋ 添加节点
        </button>
        <button
          v-if="outlineStore.nodes.length === 0"
          class="btn btn-primary"
          @click="handleGenerateOutline"
          :disabled="outlineStore.loading"
        >
          {{ outlineStore.loading ? 'AI 生成中...' : '🤖 AI 生成大纲' }}
        </button>
      </div>

      <div v-if="outlineStore.loading" class="operation-status" role="status" aria-live="polite">
        正在根据教学意图生成大纲，请稍候…
      </div>
    </div>

    <!-- AI 修订对话框 -->
    <OutlineRevisionDialog
      :visible="showReviseDialog"
      :loading="revisingDialogLoading"
      :change-summary="outlineStore.changeSummary"
      :pending-nodes="outlineStore.pendingRevision?.nodes || []"
      :error-message="outlineStore.reviseError"
      @apply="handleApplyRevision"
      @cancel="handleCancelRevision"
    />

    <!-- AI 修订输入弹窗 -->
    <div v-if="showReviseDialog" class="dialog-overlay" style="display:none"><!-- 利用 OutlineRevisionDialog --></div>

    <!-- 修订指令输入（集成在 OutlineRevisionDialog 之前） -->
    <div v-if="showReviseInput" class="revise-input-bar">
      <input
        v-model="reviseMessage"
        class="revise-text-input"
        placeholder="例如：增加一个生活案例，把课堂练习放到快速排序之后"
        @keyup.enter="handleSendRevise"
        autofocus
      />
      <button class="btn btn-primary" @click="handleSendRevise" :disabled="!reviseMessage.trim()">
        发送修订
      </button>
      <button class="btn btn-outline" @click="showReviseInput = false">取消</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useOutlineStore } from '../../stores/outlineStore'
import OutlineRevisionDialog from './OutlineRevisionDialog.vue'

const props = defineProps({
  /** 所属 session_id（从 S1 透传） */
  sessionId: { type: String, default: '' },
  /** 所属 intent_id（从 S1 透传） */
  intentId: { type: String, default: '' },
  /** 教学意图摘要（用于创建大纲） */
  intentSummary: { type: Object, default: null },
  /** 是否自动尝试从 localStorage 恢复大纲 */
  autoRestore: { type: Boolean, default: true },
  /** S1 意图自动检索形成的整份课件证据包 */
  evidencePacket: { type: Object, default: null },
  /** 等待父级完成自动检索后再创建大纲，避免先生成后补证据 */
  ready: { type: Boolean, default: true },
  presentation: { type: Object, default: () => ({}) },
  generationMode: { type: String, default: 'full_pipeline' },
  pageGenerationMode: { type: String, default: 'page_incremental' }
})

const emit = defineEmits(['confirm-complete', 'outline-created', 'error'])

const outlineStore = useOutlineStore()
const route = useRoute()

const showReviseDialog = ref(false)
const showReviseInput = ref(false)
const reviseMessage = ref('')
const revisingDialogLoading = ref(false) // 对话框内 AI 正在生成修订
const newKeyPoints = ref({}) // { [node_id]: input value }
const draggedNodeId = ref('')
const dragOverIndex = ref(-1)

const statusLabel = computed(() => ({
  draft: '草稿',
  confirming: '确认中',
  confirmed: '已确认',
  superseded: '已替代'
}[outlineStore.status] || outlineStore.status))

// 自动恢复
if (props.autoRestore) {
  outlineStore.restore()
}

// localStorage 里的版本可能落后于后端（例如后端重启后重新保存、
// 多标签页编辑或其他操作已经创建了新版本）。进入 S3 后先同步一次，
// 避免第一次 AI 修订直接因为过期 base_version 返回 409。
onMounted(async () => {
  // 基于历史版本创建的新分支已经由 S3 页面恢复为本地 draft。
  // 此时不能再次从后端读取原 outline，否则会把 draft 覆盖回 confirmed，
  // 编辑器就会重新变成只读。
  const isEditableFork = Boolean(
    route.query.from_rollback_version || route.query.editable_outline || outlineStore.forked_from_version > 0,
  )
  if (!outlineStore.outline_id || isEditableFork) return
  try {
    await outlineStore.loadOutline(outlineStore.outline_id)
    outlineStore._persist()
  } catch {
    // 后端暂不可用时保留已恢复的本地大纲，交由后续请求显示真实错误。
  }
})

// 若无大纲且有 intent，自动创建
watch(
  () => [outlineStore.outline_id, outlineStore.nodes.length, props.ready],
  ([oid, nc, ready]) => {
    if (ready && !oid && nc === 0 && props.intentSummary) {
      handleGenerateOutline()
    }
  },
  { immediate: true }
)

async function handleGenerateOutline() {
  if (!props.sessionId) {
    const message = '缺少 session_id，请先完成 S1 意图理解'
    outlineStore.error = message
    emit('error', message)
    return
  }
  try {
    // 优先使用父级按 S1 意图自动检索的证据包，兼容旧版 S2 localStorage 交接。
    let evidence = props.evidencePacket || null
    try {
      if (!evidence) {
        const raw = window.localStorage.getItem(`fuww_s2_evidence_packet:${props.sessionId}`)
        if (raw) evidence = JSON.parse(raw)
      }
    } catch {}
    // S1→S3 新主流程必须以结构化意图为主。旧版全局 Markdown 缓存可能属于
    // 另一份课件，或只有“未提供正文”的占位文本；仅在完全没有 S1 意图时兼容读取。
    let markdown = ''
    try {
      const intent = props.intentSummary || {}
      const hasIntent = Boolean(
        String(intent.topic || intent.title || '').trim()
        || (Array.isArray(intent.knowledge_points) && intent.knowledge_points.length)
        || (Array.isArray(intent.key_points) && intent.key_points.length)
      )
      if (!hasIntent) {
        const m = window.localStorage.getItem('fuww_s2_markdown')
        if (m) markdown = m
      }
    } catch {}

    await outlineStore.createOutline({
      session_id: props.sessionId,
      intent_id: props.intentId,
      intent: props.intentSummary || {},
      evidence_packet: evidence,
      generation_instruction_set: {
        schema_version: 1,
        intent: props.intentSummary || {},
        reference_materials: (evidence?.relevant_chunks || []).map((chunk) => ({
          chunk_id: chunk.chunk_id,
          source_ref: chunk.source_ref || chunk.source?.file_name || '',
          page_ref: chunk.page_ref || chunk.source?.page || null
        })),
        confirmed_evidence: evidence,
        output_requirements: {
          formats: props.intentSummary?.output_format || ['ppt'],
          with_interactive: Boolean(props.intentSummary?.with_interactive)
        },
        presentation: props.presentation || {},
        generation_mode: props.generationMode || 'full_pipeline',
        page_generation_mode: props.pageGenerationMode || 'page_incremental'
      },
      markdown
    })
    emit('outline-created', {
      outline_id: outlineStore.outline_id,
      outline_version: outlineStore.outline_version
    })
  } catch (err) {
    const message = err?.message || '创建大纲失败'
    outlineStore.error = message
    emit('error', message)
  }
}

function handleAddNode() {
  const lastNodeId = outlineStore.nodes.at(-1)?.node_id || null
  outlineStore.addNode(lastNodeId)
}

function handleDeleteNode(nodeId) {
  if (outlineStore.nodes.length <= 1) {
    emit('error', '大纲至少需要一个节点')
    return
  }
  outlineStore.removeNode(nodeId)
}

function handleDragStart(event, nodeId) {
  if (!outlineStore.canReorder) {
    event.preventDefault()
    return
  }
  draggedNodeId.value = nodeId
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', nodeId)
}

function handleDragOver(event, index) {
  if (!draggedNodeId.value) return
  event.dataTransfer.dropEffect = 'move'
  dragOverIndex.value = index
}

function handleDrop(event, index) {
  const nodeId = draggedNodeId.value || event.dataTransfer.getData('text/plain')
  if (nodeId) outlineStore.moveNodeToIndex(nodeId, index)
  handleDragEnd()
}

function handleDragEnd() {
  draggedNodeId.value = ''
  dragOverIndex.value = -1
}

function addKeyPoint(node) {
  const val = (newKeyPoints.value[node.node_id] || '').trim()
  if (!val) return
  const kps = [...(node.key_points || []), val]
  outlineStore.updateNode(node.node_id, { key_points: kps })
  newKeyPoints.value[node.node_id] = ''
}

function removeKeyPoint(node, index) {
  const kps = [...(node.key_points || [])]
  kps.splice(index, 1)
  outlineStore.updateNode(node.node_id, { key_points: kps })
}

async function handleSave() {
  try {
    await outlineStore.saveVersion()
  } catch (err) {
    emit('error', err?.message || '保存大纲失败')
  }
}

async function handleConfirm() {
  try {
    await outlineStore.confirmOutline()
  } catch (err) {
    emit('error', err?.message || '确认大纲失败')
  }
}

async function handleSendRevise() {
  const msg = reviseMessage.value.trim()
  if (!msg) return
  showReviseInput.value = false
  showReviseDialog.value = true
  revisingDialogLoading.value = true
  try {
    await outlineStore.reviseOutline(msg)
  } catch (err) {
    emit('error', err?.message || 'AI 修订失败')
  } finally {
    revisingDialogLoading.value = false
  }
}

async function handleApplyRevision() {
  try {
    await outlineStore.applyRevision()
    showReviseDialog.value = false
    reviseMessage.value = ''
  } catch (err) {
    emit('error', err?.message || '保存 AI 修订失败')
  }
}

function handleCancelRevision() {
  outlineStore.discardRevision()
  showReviseDialog.value = false
  reviseMessage.value = ''
}
</script>

<style scoped>
.outline-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 头部 */
.outline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 16px;
  background: #f8fbf9;
  border: 1px solid #e2ece6;
  border-radius: 12px;
}
.outline-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #607a71;
  flex-wrap: wrap;
}
.outline-status {
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
}
.status-draft { background: #f0f5f2; color: #2f605a; }
.status-confirming { background: #fff8e6; color: #7c4a15; }
.status-confirmed { background: #d1fae5; color: #065f46; }
.status-superseded { background: #f3f4f6; color: #6b7280; }
.outline-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 错误条 */
.error-bar {
  padding: 10px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #dc2626;
  font-size: 13px;
}

.operation-status {
  margin-top: 10px;
  padding: 10px 14px;
  border: 1px solid #c6ded6;
  border-radius: 8px;
  background: #f0f5f2;
  color: #2f605a;
  font-size: 13px;
}

/* 节点列表 */
.nodes-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.outline-node-card {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  background: #fff;
  border: 1.5px solid #e2ece6;
  border-radius: 14px;
  transition: border-color 0.15s;
}
.outline-node-card:hover {
  border-color: #5ca68f;
}
.outline-node-card.dragging { opacity: .45; cursor: grabbing; }
.outline-node-card.drag-over { border-color: #28735f; box-shadow: 0 0 0 3px rgba(40,115,95,.14); transform: translateY(2px); }
.outline-node-card.node-type-section {
  border-left: 4px solid #2f605a;
  background: #f8fbf9;
}
.outline-node-card.node-type-quiz {
  border-left: 4px solid #7c3aed;
}
.outline-node-card.node-type-interactive {
  border-left: 4px solid #ea580c;
}
.outline-node-card.node-type-summary {
  border-left: 4px solid #ca8a04;
}

/* 序号 */
.node-drag-handle {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 28px;
  cursor: grab;
  user-select: none;
}
.node-drag-handle:active { cursor: grabbing; }
.drag-grip { color:#7da596; font-size:18px; line-height:1; pointer-events:none; }
.node-order {
  font-size: 16px;
  font-weight: 700;
  color: #5ca68f;
  line-height: 1;
}
.node-move-btns {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.move-btn {
  background: none;
  border: 1px solid #c6ded6;
  border-radius: 4px;
  font-size: 10px;
  color: #5ca68f;
  cursor: pointer;
  padding: 1px 4px;
  line-height: 1;
}
.move-btn:disabled { opacity: 0.35; cursor: not-allowed; }

/* 节点内容 */
.node-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.node-top-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.node-type-select {
  font-size: 12px;
  border: 1px solid #c6ded6;
  border-radius: 6px;
  padding: 3px 6px;
  color: #2f605a;
  background: #f0f5f2;
  cursor: pointer;
}
.node-type-badge {
  font-size: 11px;
  background: #e2ece6;
  color: #5ca68f;
  padding: 2px 8px;
  border-radius: 999px;
}
.node-title-input {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  border: none;
  border-bottom: 1.5px solid #c6ded6;
  padding: 2px 4px;
  outline: none;
  color: #1e293b;
  background: transparent;
  min-width: 0;
}
.node-title-input:focus { border-bottom-color: #5ca68f; }
.node-title { font-size: 14px; font-weight: 600; color: #1e293b; }
.node-summary-input {
  width: 100%;
  font-size: 12px;
  color: #475569;
  border: 1px solid #c6ded6;
  border-radius: 8px;
  padding: 6px 8px;
  resize: vertical;
  outline: none;
  font-family: inherit;
  box-sizing: border-box;
  background: #fafcfa;
}
.node-summary-input:focus { border-color: #5ca68f; }
.node-summary { font-size: 12px; color: #475569; margin: 0; line-height: 1.5; }

/* 知识点 */
.node-key-points {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  flex-wrap: wrap;
}
.kp-label { font-size: 11px; color: #94a3b8; white-space: nowrap; line-height: 22px; }
.kp-tags { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.kp-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  background: #e8f5f0;
  color: #2f605a;
  padding: 2px 8px;
  border-radius: 999px;
}
.kp-remove {
  background: none;
  border: none;
  color: #2f605a;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
  line-height: 1;
  opacity: 0.6;
}
.kp-remove:hover { opacity: 1; }
.kp-add-input {
  font-size: 11px;
  border: none;
  background: transparent;
  outline: none;
  color: #2f605a;
  width: 100px;
  padding: 2px 4px;
}
.kp-tag-static {
  font-size: 11px;
  background: #e8f5f0;
  color: #2f605a;
  padding: 2px 8px;
  border-radius: 999px;
}

/* 互动规划 */
.node-interactive-plan {
  border-top: 1px dashed #c6ded6;
  padding-top: 8px;
}
.plan-toggle {
  font-size: 12px;
  color: #5ca68f;
  cursor: pointer;
  user-select: none;
  list-style: none;
}
.plan-toggle::-webkit-details-marker { display: none; }
.plan-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 8px;
}
.plan-fields label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #64748b;
}
.plan-fields input[type="number"] {
  width: 54px;
  padding: 2px 5px;
  border: 1px solid #c6ded6;
  border-radius: 5px;
  font-size: 11px;
  outline: none;
}
.plan-fields select {
  font-size: 11px;
  border: 1px solid #c6ded6;
  border-radius: 5px;
  padding: 2px 4px;
  outline: none;
}
.plan-fields input[type="checkbox"] { width: 14px; height: 14px; }

/* 底部：时长 & 删除 */
.node-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.duration-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #64748b;
}
.duration-input {
  width: 48px;
  padding: 2px 6px;
  border: 1px solid #c6ded6;
  border-radius: 5px;
  font-size: 11px;
  text-align: center;
  outline: none;
}
.duration-input:disabled { background: #f8fbf9; }
.fallback-notice {
  margin: 10px 0;
  padding: 10px 12px;
  color: #704b0b;
  background: #fff8e7;
  border: 1px solid #e8c978;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
}
.node-delete-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  opacity: 0.4;
  transition: opacity 0.15s;
}
.node-delete-btn:hover { opacity: 1; }

/* 添加节点 */
.add-node-row {
  display: flex;
  gap: 10px;
  justify-content: center;
  padding: 10px 0;
}
.add-node-btn {
  font-size: 13px;
}
.btn {
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
  border: 1px solid transparent;
}
.btn-sm { padding: 5px 12px; font-size: 12px; }
.btn-outline {
  background: #fff;
  border-color: #c6ded6;
  color: #2f605a;
}
.btn-outline:hover { background: #f0f5f2; }
.btn-primary {
  background: #2f605a;
  color: #fff;
  border-color: #2f605a;
}
.btn-primary:hover:not(:disabled) { background: #1e4a44; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* 修订输入条 */
.revise-input-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 14px;
  background: #f0f5f2;
  border: 1px solid #c6ded6;
  border-radius: 10px;
}
.revise-text-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #c6ded6;
  border-radius: 8px;
  font-size: 13px;
  outline: none;
}
.revise-text-input:focus { border-color: #5ca68f; }

/* 过渡动画 */
.node-list-enter-active,
.node-list-leave-active { transition: all 0.25s ease; }
.node-list-enter-from { opacity: 0; transform: translateY(-8px); }
.node-list-leave-to { opacity: 0; transform: translateX(-8px); }
</style>
