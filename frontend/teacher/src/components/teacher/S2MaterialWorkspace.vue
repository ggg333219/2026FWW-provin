<template>
  <div class="s2-workspace">
    <section class="auto-evidence-card" aria-live="polite">
      <div>
        <span class="auto-badge">自动证据</span>
        <strong>依据 S1 教学意图检索并绑定整份 PPT 草稿</strong>
        <p>{{ automaticQuery || '等待 S1 教学意图' }}</p>
      </div>
      <button :disabled="autoEvidenceLoading || !automaticQuery" @click="refreshAutomaticEvidence({ indexMaterials: true, force: true })">
        {{ autoEvidenceLoading ? '正在自动检索…' : '重新自动检索' }}
      </button>
      <span v-if="autoEvidenceError" class="auto-error">{{ autoEvidenceError }}</span>
    </section>
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
          :auto-load="false"
          @toast="handleToast"
          @task-finished="handleTaskFinished"
        />
      </div>

      <!-- 右侧：知识库 RAG 检索 + 证据融合 -->
      <div class="s2-col">
        <div class="auto-result-panel">
          <h4>全局证据包</h4>
          <p>上传资料解析完成后会自动重新索引，并按照 S1 意图更新整份课件的证据包，无需逐节点检索。</p>
          <div v-if="boundEvidenceList.length" class="auto-result-ok">已绑定 {{ boundEvidenceList.at(-1)?.packet?.relevant_chunks?.length || 0 }} 个相关切片</div>
          <div v-else class="auto-result-empty">暂无可用证据，仍可继续上传资料；S3 会保留无证据生成兜底。</div>
        </div>
        <details class="advanced-search">
          <summary>高级：手动检索与核对</summary>
          <KnowledgeBasePanel
            :session-id="sessionId"
            bound-node-ref="draft"
            @toast="handleToast"
            @bind-evidence="handleBindEvidence"
          />
        </details>
      </div>
    </div>

    <!-- 全局 Toast -->
    <teleport to="body">
      <div v-if="toastVisible" class="inline-toast" role="status">{{ toastMessage }}</div>
    </teleport>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMaterialStore, isEvidencePacketUsable } from '../../stores/materialStore'
import { intentStorageKey, useIntentStore } from '../../stores/intentStore'
import { useCoursewareProjectStore } from '../../stores/coursewareProjectStore'
import S2MaterialHub from './S2MaterialHub.vue'
import KnowledgeBasePanel from './KnowledgeBasePanel.vue'
import { buildIntentEvidenceQuery } from '../../utils/intentEvidence'

const materialStore = useMaterialStore()
const intentStore = useIntentStore()
const projectStore = useCoursewareProjectStore()
const route = useRoute()
const router = useRouter()

const EVIDENCE_KEY = 'fuww_s2_bound_evidence'
const SELECTION_KEY = 'fuww_s2_selected_materials'
const NODE_REF_KEY = 'fuww_s2_current_node_ref'
intentStore.initialize(String(route.query.project_id || projectStore.projectId || projectStore.restoreActiveId() || ''))

const scopedKey = (base) => `${base}:${sessionId.value}`

/** 会话ID：同一浏览器会话内保持稳定，供 S2 → KB → S3 串联 */
const sessionId = computed(() => {
  if (typeof window === 'undefined') return 's2_demo'
  let id = intentStore.sessionId || window.localStorage.getItem(intentStorageKey('fuww_workflow_session_id', projectStore.projectId || route.query.project_id || ''))
  if (!id) {
    id = `sess_s1_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
    window.localStorage.setItem(intentStorageKey('fuww_workflow_session_id', projectStore.projectId || route.query.project_id || ''), id)
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
const autoEvidenceLoading = ref(false)
const autoEvidenceError = ref('')
const automaticQuery = computed(() => buildIntentEvidenceQuery(intentStore.intentSummary || {}))

const persistEvidence = () => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(scopedKey(EVIDENCE_KEY), JSON.stringify(boundEvidenceList.value))
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
  if (boundEvidenceList.value.length === 0) materialStore.clearEvidencePackets()
  persistEvidence()
}

const clearEvidence = () => {
  boundEvidenceList.value = []
  materialStore.clearEvidencePackets()
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
    window.localStorage.setItem(scopedKey(NODE_REF_KEY), currentNodeRef.value)
  } else {
    window.localStorage.removeItem(scopedKey(NODE_REF_KEY))
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

const handleTaskFinished = async (payload) => {
  // 解析完成后，自动把新素材同步为选中，便于立即查看切片
  if (payload?.status === 'done' && payload.chunkCount > 0) {
    const fresh = materialStore.materials[0]
    if (fresh && !materialStore.selectedMaterials.includes(fresh.id)) {
      materialStore.selectMaterial(fresh.id)
      persistSelection()
    }
    await nextTick()
    await refreshAutomaticEvidence({ indexMaterials: true, force: true })
  }
}

async function refreshAutomaticEvidence({ indexMaterials = false, force = false } = {}) {
  const query = automaticQuery.value
  if (!query || autoEvidenceLoading.value) return null
  const latest = boundEvidenceList.value.at(-1)
  if (!force && latest?.query === query && isEvidencePacketUsable(latest.packet)) return latest.packet
  autoEvidenceLoading.value = true
  autoEvidenceError.value = ''
  try {
    if (indexMaterials && materialStore.allChunks.length) {
      await materialStore.indexKnowledgeBase({ sessionId: sessionId.value })
    }
    const packet = await materialStore.generateEvidence({
      query,
      context: { intent: intentStore.intentSummary || {}, binding_scope: 'draft', auto_bind: true },
    })
    if (!isEvidencePacketUsable(packet)) {
      autoEvidenceError.value = materialStore.error || '知识库暂未返回可用证据'
      return null
    }
    boundEvidenceList.value = [{
      id: `ev_auto_${Date.now()}`,
      query,
      packet,
      createdAt: new Date().toISOString(),
      nodeRef: '整份PPT草稿',
    }]
    persistEvidence()
    showInlineToast('已依据 S1 意图自动更新整份 PPT 的证据包')
    return packet
  } finally {
    autoEvidenceLoading.value = false
  }
}

const persistSelection = () => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(scopedKey(SELECTION_KEY), JSON.stringify(materialStore.selectedMaterials))
}

onMounted(async () => {
  await materialStore.loadMaterials({ sessionId: sessionId.value })

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
      const saved = window.localStorage.getItem(scopedKey(NODE_REF_KEY))
      if (saved) currentNodeRef.value = saved
    }
    persistNodeRef()

    // 恢复选中状态（刷新不丢失）
    try {
      const raw = window.localStorage.getItem(scopedKey(SELECTION_KEY))
      if (raw) {
        const ids = JSON.parse(raw)
        if (Array.isArray(ids)) materialStore.restoreSelection(ids)
      }
      const evRaw = window.localStorage.getItem(scopedKey(EVIDENCE_KEY))
      if (evRaw) {
        const parsed = JSON.parse(evRaw)
        if (Array.isArray(parsed)) {
          boundEvidenceList.value = parsed
          const latest = parsed[parsed.length - 1]?.packet
          if (latest) window.localStorage.setItem(`fuww_s2_evidence_packet:${sessionId.value}`, JSON.stringify(latest))
        }
      }
    } catch {
      // noop
    }
  }
  await refreshAutomaticEvidence({ indexMaterials: materialStore.allChunks.length > 0 })
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

.auto-evidence-card { display:flex; align-items:center; gap:16px; margin-bottom:16px; padding:14px 18px; border:1px solid #bcded1; border-radius:16px; background:linear-gradient(135deg,#edf9f4,#f9fcfb); color:#244f49; }
.auto-evidence-card>div { flex:1; min-width:0; }
.auto-evidence-card strong { display:block; margin-top:5px; font-size:14px; }
.auto-evidence-card p { margin:5px 0 0; color:#668078; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.auto-evidence-card button { padding:8px 14px; border:1px solid #72ad98; border-radius:9px; background:#fff; color:#2f6658; font:600 12px/1.2 inherit; cursor:pointer; }
.auto-evidence-card button:disabled { opacity:.55; cursor:not-allowed; }
.auto-badge { display:inline-flex; padding:3px 8px; border-radius:999px; background:#2f8069; color:#fff; font-size:10px; font-weight:700; }
.auto-error { max-width:240px; color:#a54b36; font-size:11px; }
.auto-result-panel { padding:18px; border:1px solid #dceae4; border-radius:14px; background:#fff; }
.auto-result-panel h4 { margin:0 0 7px; color:#2f605a; }
.auto-result-panel p { margin:0; color:#6d8179; font-size:12px; line-height:1.6; }
.auto-result-ok,.auto-result-empty { margin-top:12px; padding:10px 12px; border-radius:10px; font-size:12px; }
.auto-result-ok { background:#eaf8f1; color:#276a55; }
.auto-result-empty { background:#f7f8f8; color:#7b8984; }
.advanced-search { margin-top:12px; border:1px solid #e1e9e5; border-radius:12px; background:#fff; }
.advanced-search>summary { padding:12px 14px; color:#61756d; font-size:12px; cursor:pointer; }

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
