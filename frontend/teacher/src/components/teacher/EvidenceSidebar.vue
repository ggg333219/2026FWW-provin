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
        <option v-for="node in nodes" :key="node.node_id" :value="node.node_id">{{ node.title || '未命名章节' }}</option>
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
.evidence-sidebar {
  position: sticky;
  top: calc(var(--topbar-height) + var(--shell-gutter));
  z-index: var(--z-sticky);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
  max-height: calc(100dvh - var(--topbar-height) - var(--space-10));
  overflow: auto;
}
.evidence-sidebar header { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-2); }
.evidence-sidebar header div { display: grid; gap: var(--space-1); }
.evidence-sidebar strong { color: var(--text-primary); font-size: var(--text-sm); }
.evidence-sidebar small { font-size: var(--text-2xs); color: var(--text-tertiary); }
.evidence-sidebar a { font-size: var(--text-2xs); color: var(--color-primary); text-decoration: none; }
.evidence-sidebar a:hover { text-decoration: underline; }
.search-row { display: flex; gap: var(--space-2); }
.search-row input {
  min-width: 0;
  flex: 1;
  min-height: 34px;
  padding: var(--space-2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  background: var(--bg-surface);
  font-size: var(--text-2xs);
}
.search-row input:focus { outline: none; border-color: var(--color-primary); box-shadow: var(--shadow-focus); }
.search-row button,
.scope-card button {
  min-height: 34px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-control);
  background: var(--color-primary);
  color: var(--color-on-primary);
  font-size: var(--text-2xs);
  font-weight: var(--weight-medium);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-standard);
}
.search-row button:hover:not(:disabled),
.scope-card button:hover:not(:disabled) { background: var(--color-primary-hover); }
.search-row button:disabled,
.scope-card button:disabled { opacity: 0.48; cursor: not-allowed; }
.scope-card { display: grid; gap: var(--space-2); padding: var(--space-3); border-radius: var(--radius-sm); background: var(--bg-subtle); }
.scope-card label { font-size: var(--text-2xs); font-weight: var(--weight-semibold); color: var(--text-secondary); }
.scope-card select {
  min-height: 34px;
  padding: var(--space-2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  background: var(--bg-surface);
  font-size: var(--text-2xs);
}
.empty { padding: var(--space-5) var(--space-2); text-align: center; color: var(--text-tertiary); font-size: var(--text-2xs); line-height: var(--leading-relaxed); }
.evidence-list { display: grid; gap: var(--space-2); }
.select-tools { display: flex; justify-content: flex-end; gap: var(--space-2); }
.select-tools button { border: 0; background: transparent; color: var(--color-primary); font-size: var(--text-2xs); cursor: pointer; }
.select-tools button:hover { text-decoration: underline; }
.evidence-list article {
  padding: var(--space-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  transition: border-color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}
.evidence-list article.selected { border-color: var(--color-primary-border); background: var(--color-primary-soft); box-shadow: inset 3px 0 var(--color-primary); }
.evidence-check { display: flex; align-items: center; gap: var(--space-2); cursor: pointer; font-size: var(--text-2xs); }
.evidence-check input { accent-color: var(--color-primary); }
.evidence-list p { margin: var(--space-2) 0; font-size: var(--text-2xs); line-height: var(--leading-relaxed); color: var(--text-secondary); }
.evidence-meta { display: flex; gap: var(--space-2); align-items: center; min-width: 0; font-size: var(--text-2xs); color: var(--color-primary); }
.evidence-meta b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search-mask {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-6);
  text-align: center;
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: var(--text-2xs);
}
.search-mask small { color: var(--text-tertiary); font-size: var(--text-2xs); }
.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--brand-100);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: ev-spin 0.8s linear infinite;
}
@keyframes ev-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 0.01ms; } }
</style>
