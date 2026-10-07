<template>
  <div class="kb-panel">
    <!-- ============ 检索区 ============ -->
    <section class="kb-card">
      <div class="card-head">
        <div>
          <h3>知识库 RAG 检索</h3>
          <span class="card-desc">向量 + BM25 混合检索，返回切片与命中分数</span>
        </div>
        <button
          class="primary-btn ghost"
          :disabled="materialStore.indexing"
          @click="handleIndexKnowledge"
        >
          {{ materialStore.indexing ? '索引中…' : '索引知识库' }}
        </button>
      </div>

      <div class="search-row">
        <input
          v-model="query"
          type="text"
          placeholder="输入检索关键词，如：函数的定义域、快速排序的复杂度…"
          class="search-input"
          @keyup.enter="handleSearch"
        />
        <select v-model.number="topK" class="topk-select" title="每页结果数" @change="handlePageSizeChange">
          <option :value="5">Top 5</option>
          <option :value="10">Top 10</option>
          <option :value="20">Top 20</option>
        </select>
        <button class="primary-btn" :disabled="!query.trim() || materialStore.searching" @click="handleSearch">
          {{ materialStore.searching ? '检索中…' : '检索' }}
        </button>
      </div>
      <p v-if="materialStore.error && materialStore.error.startsWith('RAG')" class="inline-error">
        {{ materialStore.error }}
      </p>
    </section>

    <!-- ============ 检索结果 ============ -->
    <section class="kb-card">
      <div class="card-head">
        <div>
          <h3>检索结果</h3>
          <span class="card-desc">共 {{ totalResults }} 条命中，按相似度降序</span>
        </div>
        <span v-if="totalChunks > 0" class="stat-badge">知识库 {{ totalChunks }} chunks</span>
      </div>

      <div v-if="materialStore.searching" class="state-block">
        <div class="inline-spinner"></div>
        <p>正在检索知识库…</p>
      </div>
      <div v-else-if="results.length === 0" class="state-block">
        {{ searched ? '未检索到相关内容，试试调整关键词或先索引知识库' : '输入关键词开始检索' }}
      </div>
      <div v-else class="result-list">
        <div v-for="(item, idx) in results" :key="item.chunk_id" class="result-item">
          <div class="result-head">
            <label class="select-evidence">
              <input
                type="checkbox"
                :checked="selectedChunkIds.has(item.chunk_id)"
                @change="toggleEvidence(item, $event.target.checked)"
              />
              采用
            </label>
            <span class="rank">{{ pageOffset + idx + 1 }}</span>
            <span class="score" :class="{ high: item.score >= 0.85, mid: item.score >= 0.7 && item.score < 0.85 }">
              {{ (item.score * 100).toFixed(1) }}%
            </span>
            <span class="source">{{ item.source?.file_name || item.metadata?.type || '知识库' }}</span>
            <span v-if="item.source?.page" class="source-page">P{{ item.source.page }}</span>
          </div>
          <p class="result-content">{{ item.content }}</p>
        </div>
      </div>
      <div v-if="totalResults > topK" class="pagination-row">
        <span>第 {{ currentPage }} / {{ pageCount }} 页</span>
        <div class="pagination-actions">
          <button class="page-btn" :disabled="currentPage <= 1 || materialStore.searching" @click="changePage(-1)">上一页</button>
          <button class="page-btn" :disabled="currentPage >= pageCount || materialStore.searching" @click="changePage(1)">下一页</button>
        </div>
      </div>
    </section>

    <!-- ============ 证据融合区 ============ -->
    <section class="kb-card">
      <div class="card-head">
        <div>
          <h3>证据融合</h3>
          <span class="card-desc">已确认 {{ selectedChunkIds.size }} 条；仅将已选片段作为课件依据</span>
        </div>
        <button
          class="primary-btn"
          :disabled="!query.trim() || materialStore.searching || hasConfirmedEmptySearch || selectedChunkIds.size === 0"
          @click="handleFuseEvidence"
        >
          {{ hasConfirmedEmptySearch ? '暂无证据可融合' : '生成证据包' }}
        </button>
      </div>

      <div v-if="hasConfirmedEmptySearch" class="evidence-warning" role="status">
        <strong>本次检索没有命中资料</strong>
        <span>系统不会生成空证据包。请调整关键词、上传资料或先完成知识库索引。</span>
      </div>

      <div v-if="materialStore.searching" class="state-block">
        <div class="inline-spinner"></div>
        <p>正在融合证据…</p>
      </div>

      <template v-else-if="latestPacket">
        <div class="evidence-box">
          <div class="evidence-query">
            <span class="label">检索问题</span>
            <span class="value">{{ latestPacket.query }}</span>
            <button class="bind-btn" @click="handleBind">
              {{ boundNodeRef ? `已绑定：${boundNodeRef}` : '绑定到当前内容' }}
            </button>
          </div>
          <div class="synth-context">
            <span class="label">合成上下文</span>
            <p>{{ latestPacket.packet?.synthesized_context || '（无合成上下文）' }}</p>
          </div>
          <div v-if="citations.length > 0" class="citation-list">
            <span class="label">引用来源</span>
            <div v-for="(cit, i) in citations" :key="i" class="citation-row">
              <span class="cit-ref">{{ cit.source_ref || '未知来源' }}</span>
              <span class="cit-snippet">{{ cit.text_snippet }}</span>
            </div>
          </div>
        </div>
      </template>
      <div v-else class="state-block">输入关键词并点击「生成证据包」，将检索结果融合为可引用的证据</div>
    </section>

    <!-- ============ 证据包历史 ============ -->
    <section v-if="materialStore.evidencePackets.length > 0" class="kb-card">
      <div class="card-head">
        <div>
          <h3>证据包历史</h3>
          <span class="card-desc">已生成 {{ materialStore.evidencePackets.length }} 个证据包</span>
        </div>
        <button class="ghost-link" @click="materialStore.clearEvidencePackets()">清空</button>
      </div>
      <div class="packet-list">
        <div
          v-for="p in materialStore.evidencePackets.slice().reverse()"
          :key="p.id"
          class="packet-row"
        >
          <span class="packet-query">{{ p.query }}</span>
          <span class="packet-meta">
            {{ p.packet?.relevant_chunks?.length || 0 }} chunks · {{ p.packet?.citations?.length || 0 }} 引用
          </span>
          <span class="packet-time">{{ fmtTime(p.createdAt) }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useMaterialStore } from '../../stores/materialStore'
import { intentStorageKey } from '../../stores/intentStore'
import { useCoursewareProjectStore } from '../../stores/coursewareProjectStore'


const props = defineProps({
  /** 会话ID，传递给知识库索引 */
  sessionId: {
    type: String,
    default: ''
  },
  /** 绑定到的节点引用（如 p1_n2），由外层传入 */
  boundNodeRef: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['toast', 'bind-evidence'])

const materialStore = useMaterialStore()
const projectStore = useCoursewareProjectStore()
const query = ref('')
const topK = ref(10)
const searched = ref(false)
const currentPage = ref(1)
const selectedChunkIds = ref(new Set())
const pageOffset = computed(() => (currentPage.value - 1) * topK.value)
const pageCount = computed(() => Math.max(1, Math.ceil(totalResults.value / topK.value)))

const results = computed(() => materialStore.ragResults)
const totalResults = computed(() => materialStore.ragTotalResults)
const totalChunks = computed(() => {
  const list = materialStore.materials
  return list.reduce((sum, m) => sum + ((m.chunks || []).length), 0)
})

const latestPacket = computed(() => {
  const latest = materialStore.latestEvidencePacket
  if (!latest) return null
  return String(latest.query || '').trim() === query.value.trim() ? latest : null
})
const citations = computed(() => latestPacket.value?.packet?.citations || [])
const hasConfirmedEmptySearch = computed(() => searched.value && !materialStore.searching && results.value.length === 0)

const fmtTime = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const handleIndexKnowledge = async () => {
  const result = await materialStore.indexKnowledgeBase({ sessionId: props.sessionId })
  if (result) {
    emit('toast', `知识库索引完成，入库 ${result.chunk_count} 个切片`)
  } else {
    emit('toast', '知识库索引失败，请检查后端服务')
  }
}

const handleSearch = async () => {
  if (!query.value.trim()) return
  searched.value = true
  currentPage.value = 1
  selectedChunkIds.value = new Set()
  await runSearch()
}

const handlePageSizeChange = () => {
  if (searched.value) void handleSearch()
}

const runSearch = () => materialStore.searchRag({
  query: query.value,
  topK: topK.value,
  offset: pageOffset.value
})

const changePage = async (delta) => {
  const target = currentPage.value + delta
  if (target < 1 || target > pageCount.value || materialStore.searching) return
  currentPage.value = target
  await runSearch()
}

const toggleEvidence = (item, selected) => {
  const ids = new Set(selectedChunkIds.value)
  if (selected) {
    ids.add(item.chunk_id)
  } else {
    ids.delete(item.chunk_id)
  }
  selectedChunkIds.value = ids
}

/**
 * 独立 S2 页面与 Workspace 内嵌 S2 都复用本组件，因此在这里消费交接数据。
 * 只填充空输入框，确保父层预设值或教师手动输入始终具有更高优先级。
 */
onMounted(() => {
  if (typeof window === 'undefined' || query.value.trim()) return

  try {
    const raw = window.localStorage.getItem(intentStorageKey('fuww_intent_parsed', projectStore.projectId || ''))
    if (!raw) return

    const intent = JSON.parse(raw)
    if (!intent || typeof intent !== 'object' || Array.isArray(intent)) return

    const topic = String(intent.topic || '').trim()
    const subject = String(intent.subject || intent.discipline || '').trim()
    const keywords = String(intent.search_query || [topic, subject].filter(Boolean).join(' ')).trim()
    if (!topic || !keywords || query.value.trim()) return

    query.value = keywords
    void handleSearch()
  } catch {
    // 非法/过期缓存应被忽略，S2 仍保持可手动输入的正常空状态。
  }
})

const handleFuseEvidence = async () => {
  if (!query.value.trim() || selectedChunkIds.value.size === 0) return
  const packet = await materialStore.generateEvidence({
    query: query.value,
    selectedChunkIds: [...selectedChunkIds.value]
  })
  if (packet) {
    emit('toast', '证据包已生成，可绑定到当前内容')
  } else {
    emit('toast', materialStore.error || '证据融合失败，请先索引知识库')
  }
}

const handleBind = () => {
  const packet = latestPacket.value
  if (!packet) return
  emit('bind-evidence', {
    query: packet.query,
    packet: packet.packet,
    createdAt: packet.createdAt,
    nodeRef: props.boundNodeRef || ''
  })
  emit('toast', props.boundNodeRef
    ? `证据已绑定到 ${props.boundNodeRef}`
    : '证据包已输出，可传递给 S3 生成环节')
}
</script>

<style scoped>
.kb-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.kb-card {
  background: #fff;
  border: 1px solid #e4ede8;
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.card-head h3 {
  margin: 0;
  font-size: 16px;
  color: #1f2a37;
}

.card-desc {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #7a8a9a;
}

.stat-badge {
  flex-shrink: 0;
  font-size: 12px;
  color: #2f605a;
  background: #e8f0ef;
  border-radius: 999px;
  padding: 4px 12px;
  font-weight: 600;
}

/* ---------- 检索 ---------- */
.search-row {
  display: flex;
  gap: 8px;
}

.search-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid #d5e3dc;
  border-radius: 10px;
  font-size: 13px;
  color: #1f2a37;
}

.search-input:focus {
  border-color: #5ca68f;
  outline: none;
  box-shadow: 0 0 0 3px rgba(92, 166, 143, 0.12);
}

.topk-select {
  padding: 8px 10px;
  border: 1px solid #d5e3dc;
  border-radius: 10px;
  font-size: 13px;
  color: #334155;
  background: #fff;
}

.primary-btn {
  padding: 9px 18px;
  border: 0;
  background: #2f605a;
  color: #fff;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
}

.primary-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.primary-btn.ghost {
  background: #e8f0ef;
  color: #2f605a;
}

.primary-btn.ghost:disabled {
  opacity: 0.6;
}

.inline-error {
  margin: 10px 0 0;
  color: #b91c1c;
  font-size: 13px;
}

.evidence-warning {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin: -2px 0 14px;
  padding: 11px 13px;
  border: 1px solid #f0d8a8;
  border-radius: 11px;
  color: #805d1e;
  background: #fffbeb;
  font-size: 12px;
  line-height: 1.55;
}

.evidence-warning strong { flex: 0 0 auto; }
.evidence-warning span { color: #92713b; }

/* ---------- 结果 ---------- */
.result-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 380px;
  overflow-y: auto;
  padding-right: 4px;
}

.result-item {
  border: 1px solid #e7efeb;
  border-radius: 12px;
  padding: 12px 14px;
  background: #fafcfa;
}

.result-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.rank {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: #e8f0ef;
  color: #2f605a;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.score {
  font-size: 12px;
  font-weight: 700;
  border-radius: 999px;
  padding: 2px 9px;
}

.score.high { color: #166534; background: #dcfce7; }
.score.mid { color: #1d4ed8; background: #dbeafe; }
.score:not(.high):not(.mid) { color: #92400e; background: #fef3c7; }

.source {
  font-size: 12px;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-page {
  margin-left: auto;
  font-size: 11px;
  color: #64748b;
  background: #f1f5f9;
  border-radius: 6px;
  padding: 2px 8px;
}

.result-content {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: #334155;
}

.select-evidence {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #2f605a;
  font-size: 11px;
  white-space: nowrap;
}

.pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
  color: #64748b;
  font-size: 12px;
}

.pagination-actions { display: flex; gap: 8px; }

.page-btn {
  padding: 6px 12px;
  border: 1px solid #d5e3dc;
  border-radius: 8px;
  background: #fff;
  color: #2f605a;
  cursor: pointer;
}

.page-btn:disabled { opacity: 0.45; cursor: not-allowed; }

/* ---------- 证据融合 ---------- */
.evidence-box {
  border: 1px solid #d9ece3;
  background: linear-gradient(180deg, #f6fbf8, #f2f8f5);
  border-radius: 12px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.evidence-query {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.label {
  font-size: 12px;
  font-weight: 700;
  color: #2f605a;
  flex-shrink: 0;
}

.value {
  font-size: 13px;
  color: #334155;
}

.bind-btn {
  margin-left: auto;
  padding: 7px 16px;
  border: 0;
  background: #5ca68f;
  color: #fff;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.bind-btn:hover {
  background: #4d9580;
}

.synth-context p {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: #334155;
  background: #fff;
  border: 1px solid #e4ede8;
  border-radius: 10px;
  padding: 10px 12px;
}

.citation-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.citation-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 12px;
}

.cit-ref {
  flex-shrink: 0;
  color: #5ca68f;
  font-weight: 600;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cit-snippet {
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ---------- 历史 ---------- */
.packet-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.packet-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid #e7efeb;
  border-radius: 10px;
  background: #fafcfa;
  font-size: 13px;
}

.packet-query {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #1f2a37;
}

.packet-meta {
  font-size: 12px;
  color: #64748b;
}

.packet-time {
  font-size: 12px;
  color: #94a3b8;
}

.ghost-link {
  border: 0;
  background: transparent;
  color: #5ca68f;
  font-size: 12px;
  cursor: pointer;
  font-weight: 600;
}

/* ---------- 状态 ---------- */
.state-block {
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  padding: 40px 16px;
}

.state-block p {
  margin: 10px 0 0;
}

.inline-spinner {
  width: 22px;
  height: 22px;
  margin: 0 auto;
  border: 3px solid #d7e6e0;
  border-top-color: #5ca68f;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }
</style>
