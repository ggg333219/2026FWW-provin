<template>
  <aside class="evidence-sidebar">
    <header>
      <div><strong>资料与证据</strong><small>{{ citationCount }} 条可追溯引用</small></div>
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
      <button class="apply" :disabled="!packet || ((scope === 'node' || scope === 'page') && !targetNodeId)" @click="$emit('apply', { scope, nodeId: targetNodeId })">应用证据</button>
    </div>

    <div v-if="!packet" class="empty">尚无证据包。可在这里检索，或前往资料中心上传并建立索引。</div>
    <div v-else class="evidence-list">
      <article v-for="(item, index) in evidenceItems" :key="item.chunk_id || index">
        <div class="evidence-meta"><span>#{{ index + 1 }}</span><b>{{ item.source_ref || '知识库资料' }}</b></div>
        <p>{{ item.text_snippet || item.content || '已关联证据切片' }}</p>
        <small v-if="item.score != null">相关度 {{ Math.round(Number(item.score) * 100) }}%</small>
      </article>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  packet: { type: Object, default: null },
  nodes: { type: Array, default: () => [] },
  searching: { type: Boolean, default: false },
  defaultQuery: { type: String, default: '' },
})
const emit = defineEmits(['search', 'apply'])
const query = ref(props.defaultQuery)
const scope = ref('draft')
const targetNodeId = ref('')
const evidenceItems = computed(() => {
  const citations = Array.isArray(props.packet?.citations) ? props.packet.citations : []
  if (citations.length) return citations
  return Array.isArray(props.packet?.relevant_chunks) ? props.packet.relevant_chunks : []
})
const citationCount = computed(() => evidenceItems.value.length)
watch(() => props.nodes, (nodes) => {
  if (!targetNodeId.value && nodes?.length) targetNodeId.value = nodes[0].node_id || ''
}, { immediate: true })
function runSearch() { if (query.value.trim()) emit('search', query.value.trim()) }
</script>

<style scoped>
.evidence-sidebar{position:fixed;top:118px;left:20px;bottom:20px;width:300px;z-index:11;display:flex;flex-direction:column;gap:12px;padding:14px;border:1px solid #dce9e3;border-radius:14px;background:#fff;box-shadow:0 12px 34px rgba(30,72,60,.1);overflow:auto}.evidence-sidebar header{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.evidence-sidebar header div{display:grid;gap:3px}.evidence-sidebar strong{color:#24483e}.evidence-sidebar small{font-size:11px;color:#7b8d86}.evidence-sidebar a{font-size:12px;color:#28735f;text-decoration:none}.search-row{display:flex;gap:6px}.search-row input{min-width:0;flex:1;padding:8px;border:1px solid #cbded6;border-radius:8px}.search-row button,.scope-card button{border:1px solid #297761;border-radius:8px;background:#297761;color:#fff;padding:7px 10px;cursor:pointer}.search-row button:disabled,.scope-card button:disabled{opacity:.45;cursor:not-allowed}.scope-card{display:grid;gap:7px;padding:10px;border-radius:10px;background:#f3f8f6}.scope-card label{font-size:12px;font-weight:700;color:#42675d}.scope-card select{padding:7px;border:1px solid #cbddd6;border-radius:7px;background:#fff}.empty{padding:18px 8px;text-align:center;color:#82928c;font-size:12px;line-height:1.6}.evidence-list{display:grid;gap:8px}.evidence-list article{padding:10px;border:1px solid #e0ebe6;border-radius:10px;background:#fcfefd}.evidence-list p{margin:7px 0;font-size:12px;line-height:1.55;color:#4c625b}.evidence-meta{display:flex;gap:6px;align-items:center;font-size:11px;color:#26715f}.evidence-meta b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}@media(max-width:1400px){.evidence-sidebar{position:static;width:auto;max-height:430px;margin-bottom:14px}}
</style>
