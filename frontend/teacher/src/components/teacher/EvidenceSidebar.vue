<template>
  <aside class="evidence-sidebar">
    <header>
      <div><strong>资料与证据</strong><small>已选 {{ selectedIds.size }}/{{ citationCount }} 条可追溯引用</small></div>
      <router-link :to="{ name: 'S2Material' }">管理资料</router-link>
    </header>

    <div class="search-row">
      <input v-model="query" placeholder="检索当前课件所需证据" @keyup.enter="runSearch" />
      <button :disabled="searching || !query.trim()" @click="runSearch">{{ searching ? '检索中' : '检索' }}</button>
    </div>

    <div class="scope-card">
      <label>应用范围</label>
      <select v-model="scope">
        <option value="node">当前节点</option>
        <option value="page">当前页面</option>
        <option value="draft">整个草稿</option>
        <option value="none">暂不使用</option>
      </select>
      <select v-if="scope === 'node' || scope === 'page'" v-model="targetNodeId">
        <option value="" disabled>选择目标节点</option>
        <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">{{ node.title || node.node_id }}</option>
      </select>
      <button class="apply" :disabled="!packet || (!selectedIds.size && scope !== 'none') || ((scope === 'node' || scope === 'page') && !targetNodeId)" @click="$emit('apply', { scope, nodeId: targetNodeId, selectedIds: [...selectedIds] })">应用所选证据</button>
    </div>

    <div v-if="!packet" class="empty">尚无证据包。可在这里检索，或前往资料中心上传并建立索引。</div>
    <div v-else class="evidence-list">
      <div class="select-tools"><button type="button" @click="selectAll">全选</button><button type="button" @click="clearSelection">取消全选</button></div>
      <article v-for="(item, index) in evidenceItems" :key="evidenceId(item, index)" :class="{ selected: selectedIds.has(evidenceId(item, index)) }">
        <label class="evidence-check"><input type="checkbox" :checked="selectedIds.has(evidenceId(item, index))" @change="toggleEvidence(evidenceId(item, index))" /><span class="evidence-meta"><span>#{{ index + 1 }}</span><b>{{ item.source_ref || '知识库资料' }}</b></span></label>
        <p>{{ item.text_snippet || item.content || '已关联证据切片' }}</p>
        <small v-if="item.score != null">相关度 {{ Math.round(Number(item.score) * 100) }}%</small>
      </article>
    </div>
    <div v-if="searching" class="search-mask" role="status"><span class="spinner"></span><strong>正在检索并融合证据</strong><small>AI 正在阅读资料，通常需要几秒钟…</small></div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  packet: { type: Object, default: null },
  nodes: { type: Array, default: () => [] },
  searching: { type: Boolean, default: false },
  defaultQuery: { type: String, default: '' },
  selectedEvidenceIds: { type: Array, default: () => [] },
  selectionInitialized: { type: Boolean, default: false },
})
const emit = defineEmits(['search', 'apply', 'selection-change'])
const query = ref(props.defaultQuery)
const scope = ref('draft')
const targetNodeId = ref('')
const selectedIds = ref(new Set())
const evidenceItems = computed(() => {
  const citations = Array.isArray(props.packet?.citations) ? props.packet.citations : []
  if (citations.length) return citations
  return Array.isArray(props.packet?.relevant_chunks) ? props.packet.relevant_chunks : []
})
const citationCount = computed(() => evidenceItems.value.length)
const evidenceId = (item, index) => String(item?.chunk_id || item?.id || `evidence-${index}`)
watch(
  [evidenceItems, () => props.selectedEvidenceIds, () => props.selectionInitialized],
  ([items, externalIds, initialized]) => {
    const available = new Set(items.map(evidenceId))
    const nextIds = initialized
      ? externalIds.map(String).filter((id) => available.has(id))
      : [...available]
    const unchanged = nextIds.length === selectedIds.value.size && nextIds.every((id) => selectedIds.value.has(id))
    if (unchanged) return
    selectedIds.value = new Set(nextIds)
    if (!initialized) emitSelection()
  },
  { immediate: true },
)
watch(() => props.nodes, (nodes) => {
  if (!targetNodeId.value && nodes?.length) targetNodeId.value = nodes[0].node_id || ''
}, { immediate: true })
function runSearch() { if (query.value.trim()) emit('search', query.value.trim()) }
function emitSelection() { emit('selection-change', [...selectedIds.value]) }
function toggleEvidence(id) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id); else next.add(id)
  selectedIds.value = next
  emitSelection()
}
function selectAll() { selectedIds.value = new Set(evidenceItems.value.map(evidenceId)); emitSelection() }
function clearSelection() { selectedIds.value = new Set(); emitSelection() }
</script>

<style scoped>
.evidence-sidebar{position:fixed;top:118px;left:20px;bottom:20px;width:300px;z-index:11;display:flex;flex-direction:column;gap:12px;padding:14px;border:1px solid #dce9e3;border-radius:14px;background:#fff;box-shadow:0 12px 34px rgba(30,72,60,.1);overflow:auto}.evidence-sidebar header{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.evidence-sidebar header div{display:grid;gap:3px}.evidence-sidebar strong{color:#24483e}.evidence-sidebar small{font-size:11px;color:#7b8d86}.evidence-sidebar a{font-size:12px;color:#28735f;text-decoration:none}.search-row{display:flex;gap:6px}.search-row input{min-width:0;flex:1;padding:8px;border:1px solid #cbded6;border-radius:8px}.search-row button,.scope-card button{border:1px solid #297761;border-radius:8px;background:#297761;color:#fff;padding:7px 10px;cursor:pointer}.search-row button:disabled,.scope-card button:disabled{opacity:.45;cursor:not-allowed}.scope-card{display:grid;gap:7px;padding:10px;border-radius:10px;background:#f3f8f6}.scope-card label{font-size:12px;font-weight:700;color:#42675d}.scope-card select{padding:7px;border:1px solid #cbddd6;border-radius:7px;background:#fff}.empty{padding:18px 8px;text-align:center;color:#82928c;font-size:12px;line-height:1.6}.evidence-list{display:grid;gap:8px}.select-tools{display:flex;justify-content:flex-end;gap:6px}.select-tools button{border:0;background:transparent;color:#28735f;font-size:11px;cursor:pointer}.evidence-list article{padding:10px;border:1px solid #e0ebe6;border-radius:10px;background:#fcfefd;transition:.16s}.evidence-list article.selected{border-color:#72ad9b;background:#f1faf6;box-shadow:inset 3px 0 #28735f}.evidence-check{display:flex;align-items:center;gap:7px;cursor:pointer}.evidence-check input{accent-color:#28735f}.evidence-list p{margin:7px 0;font-size:12px;line-height:1.55;color:#4c625b}.evidence-meta{display:flex;gap:6px;align-items:center;min-width:0;font-size:11px;color:#26715f}.evidence-meta b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.search-mask{position:absolute;inset:0;z-index:2;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:24px;text-align:center;border-radius:14px;background:rgba(255,255,255,.94);color:#31594d}.search-mask small{color:#7b8d86}.spinner{width:28px;height:28px;border:3px solid #d9ebe4;border-top-color:#28735f;border-radius:50%;animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1400px){.evidence-sidebar{position:static;width:auto;max-height:430px;margin-bottom:14px}}
</style>
