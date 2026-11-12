<template>
  <div class="s2-workspace">
    <section class="ds-card preparation-status" aria-live="polite">
      <div class="section-heading">
        <div>
          <h2>本次依据准备</h2>
          <p>系统依据教学意图查找相关内容。资料列表中的勾选只用于查看片段，不限定自动检索范围。</p>
        </div>
        <button class="ds-btn ds-btn--secondary ds-btn--sm" type="button" :disabled="autoEvidenceLoading || !automaticQuery" @click="refreshAutomaticEvidence({ force: true })">
          {{ autoEvidenceLoading ? '处理中…' : '重新检索' }}
        </button>
      </div>
      <ol class="process-list">
        <li><strong>资料解析</strong><span>逐份查看下方状态与解析片段</span></li>
        <li><strong>索引请求</strong><span>{{ indexStatusText }}</span></li>
        <li><strong>检索结果</strong><span>{{ searchStatusText }}</span></li>
        <li><strong>页面关联</strong><span>进入 S3 后可为草稿或页面关联引用；此处不代表页面内容已核实</span></li>
      </ol>
      <ErrorState v-if="autoEvidenceState === 'error'" title="资料检索未完成" :description="autoEvidenceError" retry-text="重试检索" inline @retry="refreshAutomaticEvidence({ force: true })" />
      <div v-else-if="autoEvidenceState === 'empty'" class="ds-notice ds-notice--warning">本次检索没有返回可用参考内容。可调整资料或检索词，也可在下方选择仅按教学意图生成。</div>
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
        <section class="ds-card actual-evidence">
          <div class="section-heading">
            <div><h2>当前采用的参考内容</h2><p>以下片段来自实际返回的证据包，进入 S3 前可核对来源。</p></div>
            <button v-if="activeEvidence" class="ds-btn ds-btn--ghost ds-btn--sm" type="button" @click="clearEvidence">清除本次依据</button>
          </div>
          <p v-if="activeEvidence" class="evidence-query">{{ autoEvidenceState === 'error' ? '上次成功检索的主题' : '检索主题' }}：{{ activeEvidence.query }}</p>
          <p v-if="activeEvidence && ['empty', 'error'].includes(autoEvidenceState)" class="reference-note">最近一次检索未取得新内容；下列上次采用的片段仍会带入生成。如需仅按教学意图生成，请先清除本次依据。</p>
          <ul v-if="referenceItems.length" class="reference-list">
            <li v-for="(item, index) in referenceItems" :key="item.chunk_id || index" class="reference-item">
              <strong>{{ referenceSource(item) }}</strong>
              <span v-if="referenceLocation(item)">{{ referenceLocation(item) }}</span>
              <p>{{ item.text_snippet || item.content }}</p>
            </li>
          </ul>
          <EmptyState v-else title="暂无可核对的参考片段" description="上传资料后可重新检索；若仍无命中，可以明确选择仅按教学意图生成。" icon="search" inline />
          <p v-if="activeEvidence" class="reference-note">当前片段可供生成参考；它们不是对最终课件内容的逐句核验。</p>
          <details v-if="boundEvidenceList.length > 1" class="evidence-history">
            <summary>查看 {{ boundEvidenceList.length }} 次参考内容记录</summary>
            <ul>
              <li v-for="ev in boundEvidenceList" :key="ev.id">
                <span>{{ ev.query }}<template v-if="ev.nodeRef"> · {{ ev.nodeRef }}</template></span>
                <button class="ds-btn ds-btn--ghost ds-btn--sm" type="button" :aria-label="`移除 ${ev.query} 的参考内容`" @click="unbindEvidence(ev.id)">移除</button>
              </li>
            </ul>
          </details>
        </section>
        <details class="advanced-search">
          <summary>高级：手动检索、选择片段与证据融合</summary>
          <KnowledgeBasePanel
            :session-id="sessionId"
            bound-node-ref="draft"
            :auto-search="false"
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
import EmptyState from '../common/EmptyState.vue'
import ErrorState from '../common/ErrorState.vue'
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
const autoEvidenceState = ref('idle')
const lastIndexResponse = ref(null)
const indexRequestNote = ref('')
const automaticQuery = computed(() => buildIntentEvidenceQuery(intentStore.intentSummary || {}))
const activeEvidence = computed(() => [...boundEvidenceList.value].reverse().find(ev => isEvidencePacketUsable(ev.packet)) || null)
const referenceItems = computed(() => {
  const packet = activeEvidence.value?.packet
  const chunks = Array.isArray(packet?.relevant_chunks) ? packet.relevant_chunks : []
  const citations = Array.isArray(packet?.citations)
    ? packet.citations.filter(item => String(item.text_snippet || item.content || '').trim()) : []
  if (!citations.length) return chunks
  const chunksById = new Map(chunks.map(item => [item.chunk_id, item]))
  return citations.map(item => ({ ...(chunksById.get(item.chunk_id) || {}), ...item }))
})
const referenceSource = item => item.source_ref || item.source?.file_name || item.metadata?.file_name || '来源未标注'
const referenceLocation = item => {
  const page = item.page_ref ?? item.source?.page ?? item.metadata?.page
  if (page != null && Number(page) > 0) return `第 ${page} 页`
  const start = item.time_start ?? item.metadata?.time_start
  const end = item.time_end ?? item.metadata?.time_end
  return start != null ? `${start}–${end ?? start} 秒` : ''
}
const indexStatusText = computed(() => {
  const result = lastIndexResponse.value
  if (materialStore.indexing) return '正在发送索引请求'
  if (indexRequestNote.value) return indexRequestNote.value
  if (!result) return '尚无本次索引结果；解析完成不代表已索引'
  return `本次请求返回 ${result.chunk_count} 个片段（${result.status || '状态未提供'}）；能否检索到内容请看下步`
})
const searchStatusText = computed(() => {
  if (autoEvidenceLoading.value && !materialStore.indexing) return '正在按教学意图检索'
  if (autoEvidenceState.value === 'matched') return `当前采用 ${referenceItems.value.length} 条实际返回的参考片段`
  if (autoEvidenceState.value === 'empty') return '本次未返回可用片段'
  if (autoEvidenceState.value === 'error') return '检索或索引服务异常'
  return automaticQuery.value ? '尚未得到本次检索结果' : '请先完成教学意图'
})

const persistEvidence = () => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(scopedKey(EVIDENCE_KEY), JSON.stringify(boundEvidenceList.value))
}

const handleBindEvidence = (payload) => {
  const existingIndex = boundEvidenceList.value.findIndex((ev) => ev.query === payload.query)
  const existing = existingIndex >= 0 ? boundEvidenceList.value.splice(existingIndex, 1)[0] : null
  if (existing) {
    existing.packet = payload.packet
    existing.createdAt = payload.createdAt
    existing.nodeRef = payload.nodeRef || existing.nodeRef
    boundEvidenceList.value.push(existing)
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
  autoEvidenceState.value = 'matched'
  autoEvidenceError.value = ''
}

const unbindEvidence = (id) => {
  boundEvidenceList.value = boundEvidenceList.value.filter((ev) => ev.id !== id)
  materialStore.clearEvidencePackets()
  const latest = activeEvidence.value
  if (latest) materialStore.addEvidencePacket(latest.query, latest.packet)
  persistEvidence()
  autoEvidenceState.value = latest ? 'matched' : 'idle'
}

const clearEvidence = () => {
  boundEvidenceList.value = []
  materialStore.clearEvidencePackets()
  persistEvidence()
  autoEvidenceState.value = 'idle'
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
  // 教师已手动挑选片段时，重进页面不自动覆盖其选择；显式点击重试才重新检索。
  if (!force && activeEvidence.value) {
    autoEvidenceState.value = 'matched'
    return activeEvidence.value.packet
  }
  autoEvidenceLoading.value = true
  autoEvidenceError.value = ''
  autoEvidenceState.value = 'loading'
  try {
    if (indexMaterials && materialStore.allChunks.length) {
      lastIndexResponse.value = null
      indexRequestNote.value = ''
      const indexed = await materialStore.indexKnowledgeBase({ sessionId: sessionId.value })
      if (!indexed) {
        if (materialStore.error === '知识库索引未写入任何切片') {
          // 重复索引可能没有新增片段；是否有内容可用以随后真实检索为准。
          indexRequestNote.value = '本次未新增片段；继续检索已有内容'
        } else {
          autoEvidenceError.value = materialStore.error || '知识库索引失败'
          autoEvidenceState.value = 'error'
          return null
        }
      } else {
        lastIndexResponse.value = indexed
        indexRequestNote.value = ''
      }
    }
    const packet = await materialStore.generateEvidence({
      query,
      context: { intent: intentStore.intentSummary || {}, binding_scope: 'draft', auto_bind: true },
    })
    if (!isEvidencePacketUsable(packet)) {
      autoEvidenceError.value = materialStore.error || '知识库暂未返回可用证据'
      autoEvidenceState.value = materialStore.error?.startsWith('RAG 未检索到') ? 'empty' : 'error'
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
    autoEvidenceState.value = 'matched'
    showInlineToast('已找到可供课件生成参考的资料片段')
    return packet
  } catch (error) {
    autoEvidenceState.value = 'error'
    autoEvidenceError.value = String(error?.message || error)
    return null
  } finally {
    autoEvidenceLoading.value = false
  }
}

const persistSelection = () => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(scopedKey(SELECTION_KEY), JSON.stringify(materialStore.selectedMaterials))
}

onMounted(async () => {
  await materialStore.loadMaterials({
    sessionId: sessionId.value,
    preserveSessionMaterials: true
  })

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
          const latest = activeEvidence.value?.packet
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
  display: grid;
  gap: var(--space-5);
  min-height: calc(100dvh - 140px);
}

.preparation-status, .actual-evidence { padding: var(--space-5); }
.section-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-4); }
.section-heading h2 { margin: 0; color: var(--text-primary); font-size: var(--text-md); }
.section-heading p { margin: var(--space-1) 0 0; color: var(--text-secondary); font-size: var(--text-xs); line-height: var(--leading-relaxed); }
.process-list { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--space-3); margin: var(--space-5) 0 0; padding: 0; list-style: none; }
.process-list li { display: grid; align-content: start; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--bg-page); }
.process-list strong { color: var(--text-primary); font-size: var(--text-xs); }
.process-list span { color: var(--text-secondary); font-size: var(--text-2xs); line-height: var(--leading-relaxed); overflow-wrap: anywhere; }
.preparation-status :deep(.loading-state), .preparation-status .ds-notice { margin-top: var(--space-4); }
.reference-list { display: grid; gap: var(--space-3); padding: 0; margin: var(--space-4) 0; list-style: none; max-height: 420px; overflow: auto; }
.reference-item { padding: var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); }
.reference-item strong { display: block; color: var(--text-primary); font-size: var(--text-xs); overflow-wrap: anywhere; }
.reference-item span { display: block; margin-top: var(--space-1); color: var(--text-secondary); font-size: var(--text-2xs); }
.reference-item p { margin: var(--space-2) 0 0; color: var(--text-primary); font-size: var(--text-xs); line-height: var(--leading-relaxed); white-space: pre-wrap; overflow-wrap: anywhere; }
.evidence-query, .reference-note { color: var(--text-secondary); font-size: var(--text-2xs); line-height: var(--leading-relaxed); }
.evidence-history { margin-top: var(--space-3); color: var(--text-secondary); font-size: var(--text-2xs); }
.evidence-history summary { cursor: pointer; }
.evidence-history ul { padding: 0; margin: var(--space-2) 0 0; list-style: none; }
.evidence-history li { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); padding: var(--space-1) 0; border-top: 1px solid var(--border-subtle); }
.evidence-history li span { overflow-wrap: anywhere; }
.advanced-search { overflow: hidden; }
.advanced-search > summary { font-size: var(--text-xs); font-weight: var(--weight-medium); }
@media (max-width: 1023px) { .process-list { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 767px) {
  .section-heading { flex-direction: column; }
  .process-list, .s2-layout { grid-template-columns: minmax(0, 1fr); }
  .preparation-status, .actual-evidence { padding: var(--space-4); }
}

.auto-evidence-card { display:flex; align-items:center; gap:16px; margin-bottom:16px; padding:14px 18px; border:1px solid #bcded1; border-radius:16px; background:linear-gradient(135deg,#edf9f4,#f9fcfb); color:#244f49; }
.auto-evidence-card>div { flex:1; min-width:0; }
.auto-evidence-card strong { display:block; margin-top:5px; font-size:14px; }
.auto-evidence-card p { margin:5px 0 0; color:#668078; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.auto-evidence-card button { padding:8px 14px; border:1px solid #72ad98; border-radius:9px; background:#fff; color:#2f6658; font:600 12px/1.2 inherit; cursor:pointer; }
.auto-evidence-card button:disabled { opacity:.55; cursor:not-allowed; }
.auto-badge { display:inline-flex; padding:3px 8px; border-radius:999px; background:#2f8069; color:#fff; font-size: 12px; font-weight:700; }
.auto-error { max-width:240px; color:#a54b36; font-size: 12px; }
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
  font-size: 12px;
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
  font-size: 12px;
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
  font-size: 12px;
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
