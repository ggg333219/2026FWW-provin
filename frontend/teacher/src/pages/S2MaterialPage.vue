<template>
  <AppShell>
    <div class="s2-page">
      <div class="page-header">
        <h2>S2 素材管理</h2>
        <p>素材检索、切片 (ChunkSchema) 与向量检索</p>
      </div>
      <div class="page-body">
        <div class="s2-layout">
          <section class="s2-search">
            <div class="section-card">
              <h3>素材搜索</h3>
              <div class="search-row">
                <input
                  v-model="keyword"
                  type="text"
                  placeholder="输入关键词搜索素材..."
                  class="search-input"
                  @keyup.enter="handleSearch"
                />
                <button class="primary-btn" @click="handleSearch">搜索</button>
              </div>
            </div>
          </section>
          <section class="s2-results">
            <div class="section-card">
              <h3>素材列表</h3>
              <div v-if="loading" class="empty-tip">加载中...</div>
              <div v-else-if="materials.length === 0" class="empty-tip">暂无素材，请搜索</div>
              <div v-else class="material-grid">
                <div
                  v-for="item in materials"
                  :key="item.id"
                  class="material-card"
                  :class="{ selected: isSelected(item.id) }"
                  @click="toggleSelect(item.id)"
                >
                  <h4>{{ item.title }}</h4>
                  <span class="material-type">{{ item.type }}</span>
                  <p>{{ item.desc }}</p>
                </div>
              </div>
            </div>
          </section>
          <section class="s2-chunks">
            <div class="section-card">
              <h3>切片预览 (ChunkSchema)</h3>
              <div v-if="selectedChunks.length === 0" class="empty-tip">请选择素材查看切片</div>
              <div v-else class="chunk-list">
                <div v-for="chunk in selectedChunks" :key="chunk.chunkId" class="chunk-item">
                  {{ chunk.content }}
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useMaterialStore } from '../stores/materialStore'
import AppShell from '../components/layout/AppShell.vue'

const materialStore = useMaterialStore()
const keyword = ref('')
const loading = ref(false)
const materials = ref([])

const isSelected = (id) => materialStore.selectedMaterials.includes(id)
const toggleSelect = (id) => materialStore.toggleMaterial(id)

const selectedChunks = computed(() => {
  return materialStore.chunks.filter(c => materialStore.selectedMaterials.includes(c.materialId))
})

const handleSearch = async () => {
  if (!keyword.value.trim()) return
  loading.value = true
  // 模拟搜索，后续对接真实 API
  setTimeout(() => {
    materials.value = [
      { id: 'm1', title: '数学课件-函数篇', type: 'document', desc: '包含函数定义与图像' },
      { id: 'm2', title: '数学视频-导数讲解', type: 'video', desc: '导数概念与计算' }
    ]
    loading.value = false
  }, 300)
}

</script>

<style scoped>
.s2-page { padding: 20px; min-height: calc(100vh - 140px); }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 22px; color: #111827; }
.page-header p { margin: 6px 0 0; font-size: 14px; color: #607a71; }
.page-body { flex: 1; }
.s2-layout { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.section-card { background: #fff; border: 1px solid #dbe6df; border-radius: 16px; padding: 16px; box-shadow: 0 4px 12px rgba(15,23,42,0.04); }
.section-card h3 { margin: 0 0 12px; font-size: 16px; color: #2d5f58; }
.search-row { display: flex; gap: 8px; }
.search-input { flex: 1; padding: 8px 12px; border: 1px solid #d5e3dc; border-radius: 10px; font-size: 14px; }
.search-input:focus { border-color: #8ab8ab; outline: none; }
.primary-btn { padding: 8px 18px; border: 0; background: #5ca68f; color: #fff; border-radius: 10px; cursor: pointer; font-weight: 600; }
.primary-btn:hover { background: #4d9580; }
.empty-tip { color: #94a3b8; text-align: center; padding: 40px 0; font-size: 14px; }
.material-grid { display: flex; flex-direction: column; gap: 8px; }
.material-card { border: 1px solid #e5ede8; border-radius: 12px; padding: 12px; cursor: pointer; transition: all 0.18s ease; }
.material-card:hover { border-color: #8fbcae; }
.material-card.selected { border-color: #5ca68f; background: #f0f9f5; }
.material-card h4 { margin: 0 0 4px; font-size: 14px; color: #284a43; }
.material-type { font-size: 11px; color: #6b887e; background: #edf5f2; padding: 2px 8px; border-radius: 999px; }
.material-card p { margin: 6px 0 0; font-size: 12px; color: #638075; }
.chunk-list { display: flex; flex-direction: column; gap: 8px; }
.chunk-item { padding: 10px; background: #f6faf8; border-radius: 10px; font-size: 13px; color: #334155; line-height: 1.6; }

@media (max-width: 1200px) {
  .s2-layout { grid-template-columns: 1fr; }
}
</style>
