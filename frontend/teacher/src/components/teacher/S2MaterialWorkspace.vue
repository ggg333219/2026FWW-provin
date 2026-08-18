<template>
  <div class="s2-workspace">
    <!-- 证据预渲染区：已绑定证据包预览 -->
    <section v-if="boundEvidenceList.length > 0" class="evidence-strip">
      <div class="strip-head">
        <h4>证据预渲染</h4>
        <span class="strip-hint">已绑定 {{ boundEvidenceList.length }} 个证据包，将随会话传递给 S3 生成环节</span>
        <button class="ghost-link" @click="clearEvidence">清空</button>
      </div>
      <div class="strip-list">
        <div v-for="(ev, i) in boundEvidenceList" :key="ev.id" class="strip-item">
          <span class="strip-idx">{{ i + 1 }}</span>
          <div class="strip-body">
            <p class="strip-query">{{ ev.query }}</p>
            <p class="strip-meta">
              {{ ev.packet?.relevant_chunks?.length || 0 }} 个相关切片
              <template v-if="ev.nodeRef"> · 绑定节点 {{ ev.nodeRef }}</template>
            </p>
          </div>
          <button class="strip-del" title="取消绑定" @click="unbindEvidence(ev.id)">×</button>
        </div>
      </div>
    </section>

    <div class="s2-layout">
      <!-- 左侧：资料上传 + 解析 + 素材与切片 -->
      <div class="s2-col">
        <S2MaterialHub
          :session-id="sessionId"
          @toast="handleToast"
          @task-finished="handleTaskFinished"
        />
      </div>

      <!-- 右侧：知识库 RAG 检索 + 证据融合 -->
      <div class="s2-col">
        <!-- 当前绑定节点指示器 -->
        <div class="node-ref-bar">
          <span class="node-ref-label">绑定到当前节点：</span>
          <template v-if="editingNodeRef">
            <input
              v-model="nodeRefInput"
              class="node-ref-input"
              placeholder="输入节点 ID，如 p1_n2"
              @keyup.enter="confirmNodeRef"
              @keyup.escape="cancelEditNodeRef"
            />
            <button class="node-ref-confirm" @click="confirmNodeRef">确定</button>
            <button class="node-ref-cancel" @click="cancelEditNodeRef">取消</button>
          </template>
          <template v-else>
            <span class="node-ref-value" :class="{ empty: !currentNodeRef }">
              {{ currentNodeRef || '未指定（将绑定到空节点）' }}
            </span>
            <button class="node-ref-edit" @click="startEditNodeRef" title="编辑节点引用">✎</button>
            <span class="node-ref-hint">由 S3 传入，也可手动指定</span>
          </template>
        </div>

        <KnowledgeBasePanel
          :session-id="sessionId"
          :bound-node-ref="currentNodeRef"
          @toast="handleToast"
          @bind-evidence="handleBindEvidence"
        />
      </div>
    </div>

    <!-- 全局 Toast -->
    <teleport to="body">
      <div v-if="toastVisible" class="inline-toast" role="status">{{ toastMessage }}</div>
    </teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMaterialStore } from '../../stores/materialStore'
import S2MaterialHub from './S2MaterialHub.vue'
import KnowledgeBasePanel from './KnowledgeBasePanel.vue'

const materialStore = useMaterialStore()
const route = useRoute()
const router = useRouter()

const EVIDENCE_KEY = 'fuww_s2_bound_evidence'
const SELECTION_KEY = 'fuww_s2_selected_materials'
const SESSION_KEY = 'fuww_s2_session_id'
const NODE_REF_KEY = 'fuww_s2_current_node_ref'

/** 会话ID：同一浏览器会话内保持稳定，供 S2 → KB → S3 串联 */
const sessionId = computed(() => {
  if (typeof window === 'undefined') return 's2_demo'
  let id = window.localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = `sess_s2_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
    window.localStorage.setItem(SESSION_KEY, id)
  }
  return id
})

/**
 * 当前绑定节点引用。
 *
 * 来源优先级（逐级回退）：
 * 1. 路由 query ?nodeRef=p1_n2（S3 跳转时传入，如 "绑定到当前节点"）
 * 2. localStorage 持久化（刷新不丢失）
 * 3. 空字符串（用户手动输入）
 */
const currentNodeRef = ref('')

// 是否正在编辑节点引用
const editingNodeRef = ref(false)
const nodeRefInput = ref('')

/** 已绑定证据包（跨刷新持久化） */
const boundEvidenceList = ref([])

const persistEvidence = () => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(EVIDENCE_KEY, JSON.stringify(boundEvidenceList.value))
}

const handleBindEvidence = (payload) => {
  const existing = boundEvidenceList.value.find((ev) => ev.query === payload.query)
  if (existing) {
    existing.packet = payload.packet
    existing.createdAt = payload.createdAt
    existing.nodeRef = payload.nodeRef || existing.nodeRef
  } else {
    boundEvidenceList.value.push({
      id: `ev_${Date.now()}`,
      query: payload.query,
      packet: payload.packet,
      createdAt: payload.createdAt,
      nodeRef: payload.nodeRef
    })
  }
  persistEvidence()
}

const unbindEvidence = (id) => {
  boundEvidenceList.value = boundEvidenceList.value.filter((ev) => ev.id !== id)
  persistEvidence()
}

const clearEvidence = () => {
  boundEvidenceList.value = []
  persistEvidence()
}

const handleToast = (message) => {
  showInlineToast(String(message || ''))
}

/** 节点引用编辑 */
const startEditNodeRef = () => {
  nodeRefInput.value = currentNodeRef.value
  editingNodeRef.value = true
}

const confirmNodeRef = () => {
  currentNodeRef.value = nodeRefInput.value.trim()
  editingNodeRef.value = false
  persistNodeRef()
  showInlineToast(currentNodeRef.value
    ? `当前绑定节点设为 ${currentNodeRef.value}`
    : '已清除绑定节点引用')
}

const cancelEditNodeRef = () => {
  editingNodeRef.value = false
  nodeRefInput.value = ''
}

const persistNodeRef = () => {
  if (typeof window === 'undefined') return
  if (currentNodeRef.value) {
    window.localStorage.setItem(NODE_REF_KEY, currentNodeRef.value)
  } else {
    window.localStorage.removeItem(NODE_REF_KEY)
  }
}

const toastVisible = ref(false)
const toastMessage = ref('')
let toastTimer = null
const showInlineToast = (message) => {
  toastMessage.value = message
  toastVisible.value = true
  if (toastTimer) window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toastVisible.value = false
  }, 2800)
}

const handleTaskFinished = (payload) => {
  // 解析完成后，自动把新素材同步为选中，便于立即查看切片
  if (payload?.status === 'done' && payload.chunkCount > 0) {
    const fresh = materialStore.materials[0]
    if (fresh && !materialStore.selectedMaterials.includes(fresh.id)) {
      materialStore.selectMaterial(fresh.id)
      persistSelection()
    }
  }
}

const persistSelection = () => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(SELECTION_KEY, JSON.stringify(materialStore.selectedMaterials))
}

onMounted(async () => {
  await materialStore.loadMaterials()

  // 恢复当前节点引用（优先级：路由 query > localStorage）
  if (typeof window !== 'undefined') {
    // 路由 query 传入（如 S3 跳转时传入 ?nodeRef=p1_n2）
    const queryRef = route.query.nodeRef
    if (typeof queryRef === 'string' && queryRef.trim()) {
      currentNodeRef.value = queryRef.trim()
      // 消费后清除 query，避免刷新后残留
      router.replace({ query: { ...route.query, nodeRef: undefined } })
    } else {
      // 从 localStorage 恢复
      const saved = window.localStorage.getItem(NODE_REF_KEY)
      if (saved) currentNodeRef.value = saved
    }
    persistNodeRef()

    // 恢复选中状态（刷新不丢失）
    try {
      const raw = window.localStorage.getItem(SELECTION_KEY)
      if (raw) {
        const ids = JSON.parse(raw)
        if (Array.isArray(ids)) materialStore.restoreSelection(ids)
      }
      const evRaw = window.localStorage.getItem(EVIDENCE_KEY)
      if (evRaw) {
        const parsed = JSON.parse(evRaw)
        if (Array.isArray(parsed)) boundEvidenceList.value = parsed
      }
    } catch {
      // noop
    }
  }
})

// 选中变化时持久化
watch(
  () => materialStore.selectedMaterials.join(','),
  () => persistSelection()
)

// ---- 跨 Store 编排：供 WorkspacePage 调用 ----
const searchQuery = ref('')

function setSearchQuery(keywords) {
  searchQuery.value = String(keywords || '').trim()
}

defineExpose({ setSearchQuery })
</script>

<style scoped>
.s2-workspace {
  padding: 20px;
  min-height: calc(100vh - 140px);
}

/* ---------- 证据预渲染 ---------- */
.evidence-strip {
  background: linear-gradient(180deg, #f2faf6, #eef8f3);
  border: 1px solid #d9ece3;
  border-radius: 16px;
  padding: 14px 18px;
  margin-bottom: 16px;
}

.strip-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.strip-head h4 {
  margin: 0;
  font-size: 14px;
  color: #2f605a;
}

.strip-hint {
  flex: 1;
  font-size: 12px;
  color: #7a8a9a;
}

.strip-list {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.strip-item {
  flex: 0 0 auto;
  width: 240px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background: #fff;
  border: 1px solid #e4ede8;
  border-radius: 12px;
  padding: 10px 12px;
}

.strip-idx {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  background: #5ca68f;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.strip-body {
  flex: 1;
  min-width: 0;
}

.strip-query {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #1f2a37;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.strip-meta {
  margin: 4px 0 0;
  font-size: 11px;
  color: #7a8a9a;
}

.strip-del {
  flex-shrink: 0;
  border: 0;
  background: transparent;
  color: #94a3b8;
  font-size: 15px;
  cursor: pointer;
  line-height: 1;
}

.strip-del:hover {
  color: #b91c1c;
}

/* ---------- 布局 ---------- */
.s2-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.s2-col {
  min-width: 0;
}

/* ---------- 节点引用栏 ---------- */
.node-ref-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
  margin-bottom: 12px;
  font-size: 13px;
  flex-wrap: wrap;
}

.node-ref-label {
  font-weight: 600;
  color: #2f605a;
  flex-shrink: 0;
}

.node-ref-value {
  color: #1f2a37;
  font-family: monospace;
  font-weight: 600;
}

.node-ref-value.empty {
  color: #94a3b8;
  font-weight: 400;
  font-style: italic;
}

.node-ref-edit {
  border: 0;
  background: transparent;
  color: #5ca68f;
  cursor: pointer;
  font-size: 14px;
  padding: 0 4px;
}

.node-ref-edit:hover {
  color: #2f605a;
}

.node-ref-hint {
  font-size: 11px;
  color: #94a3b8;
}

.node-ref-input {
  padding: 4px 10px;
  border: 1px solid #5ca68f;
  border-radius: 8px;
  font-size: 13px;
  font-family: monospace;
  width: 120px;
  outline: none;
  box-shadow: 0 0 0 3px rgba(92, 166, 143, 0.12);
}

.node-ref-confirm {
  padding: 4px 12px;
  border: 0;
  background: #2f605a;
  color: #fff;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  font-weight: 600;
}

.node-ref-cancel {
  padding: 4px 10px;
  border: 1px solid #d5e3dc;
  background: #fff;
  color: #64748b;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
}

/* ---------- Toast ---------- */
.inline-toast {
  position: fixed;
  left: 50%;
  bottom: 32px;
  transform: translateX(-50%);
  z-index: 99999;
  max-width: min(92vw, 460px);
  padding: 12px 18px;
  border-radius: 10px;
  background: rgba(17, 24, 39, 0.92);
  color: #f8fafc;
  font-size: 14px;
  line-height: 1.45;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.25);
  pointer-events: none;
}

.ghost-link {
  border: 0;
  background: transparent;
  color: #5ca68f;
  font-size: 12px;
  cursor: pointer;
  font-weight: 600;
}

@media (max-width: 1200px) {
  .s2-layout {
    grid-template-columns: 1fr;
  }
}
</style>