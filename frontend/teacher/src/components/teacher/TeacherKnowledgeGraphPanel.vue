<template>
  <div class="kb-page">
    <header class="kb-page-head">
      <div>
        <h2>教学资源中枢 - 个人知识库</h2>
        <p class="kb-lead">
          沉淀个人教学资源，备课时一键引用；智能推荐与学生高频收藏自动汇入，支撑「资源 → 课堂 → 再沉淀」闭环。
        </p>
      </div>
    </header>

    <nav class="kb-tabs" role="tablist">
      <button
        v-for="tab in kbTabs"
        :key="tab.id"
        type="button"
        role="tab"
        :class="['kb-tab', { active: activeKbTab === tab.id }]"
        @click="activeKbTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </nav>

    <section v-show="activeKbTab === 'mine'" class="kb-panel">
      <p class="kb-hint">按课程 / 知识点管理的个人资源；与「编辑讲稿」侧栏互通，可拖拽或一键引用。</p>
      <div class="res-grid">
        <article v-for="item in myTeachingResources" :key="item.id" class="res-card">
          <div class="res-card-head">
            <span class="res-type">{{ item.type }}</span>
            <strong>{{ item.title }}</strong>
          </div>
          <p class="res-meta">{{ item.course }} · {{ item.node }}</p>
          <p class="res-desc">{{ item.desc }}</p>
          <div class="res-actions">
            <button type="button" class="btn-main" @click="emitCite({ ...item, sourceTab: 'mine' })">一键引用到我的讲稿</button>
            <button type="button" class="btn-sub" @click="hintEdit">编辑标签</button>
          </div>
        </article>
      </div>
    </section>

    <section v-show="activeKbTab === 'students'" class="kb-panel">
      <p class="kb-hint">同步学生端高频收藏/访问资源，按热度排序，便于教师反向优化讲义与拓展材料。</p>
      <div class="res-grid">
        <article v-for="item in studentHotList" :key="item.id" class="res-card">
          <div class="res-card-head">
            <span class="hot-tag">热度 {{ item.hot }}</span>
            <strong>{{ item.title }}</strong>
          </div>
          <p class="res-meta">知识点：{{ item.node }} · 收藏人数 {{ item.favorites }}</p>
          <div class="res-actions">
            <button type="button" class="btn-main" @click="emitCite({ ...item, sourceTab: 'students' })">一键引用到我的讲稿</button>
            <button type="button" class="btn-sub" @click="hintSave">保存到我的资源</button>
          </div>
        </article>
      </div>
    </section>

    <section v-show="activeKbTab === 'public'" class="kb-panel">
      <p class="kb-hint">平台精选与合规外链资源池；可按知识点筛选后保存到个人库。</p>
      <div class="filter-row">
        <label>知识点 <input v-model.trim="publicFilter" placeholder="如：递归与分治" /></label>
        <button type="button" class="btn-main" @click="hintSave">保存筛选条件</button>
      </div>
      <div class="res-grid">
        <article v-for="item in publicFiltered" :key="item.id" class="res-card">
          <div class="res-card-head">
            <span class="res-type">{{ item.type }}</span>
            <strong>{{ item.title }}</strong>
          </div>
          <p class="res-meta">{{ item.source }}</p>
          <div class="res-actions">
            <button type="button" class="btn-main" @click="emitCite({ ...item, sourceTab: 'public' })">一键引用到我的讲稿</button>
            <button type="button" class="btn-sub" @click="hintSave">保存到我的资源</button>
          </div>
        </article>
      </div>
    </section>

    <section v-show="activeKbTab === 'graph'" class="kb-panel graph-embed">
      <div class="graph-panel-shell">
        <div class="graph-panel-head">
          <div>
            <h4>知识图谱维护</h4>
            <p>同步关系边、扫描引用健康、一键修复孤儿节点引用（高级能力，置于独立标签）。</p>
          </div>
        </div>

        <div class="action-row">
          <button type="button" class="action-btn primary" :disabled="syncLoading" @click="handleSync">
            {{ syncLoading ? '同步中...' : '同步图谱' }}
          </button>
          <button type="button" class="action-btn" :disabled="scanLoading" @click="handleScan">
            {{ scanLoading ? '扫描中...' : '扫描健康' }}
          </button>
          <button type="button" class="action-btn warn" :disabled="repairLoading || !scanReport?.hasOrphans" @click="handleRepair">
            {{ repairLoading ? '修复中...' : '修复引用' }}
          </button>
        </div>

        <transition name="fade-slide">
          <div v-if="summaryVisible" class="summary-grid">
            <div class="metric-card">
              <span>当前课件</span>
              <strong :title="courseName">{{ courseName || '未命名课件' }}</strong>
            </div>
            <div class="metric-card">
              <span>图谱关系边</span>
              <strong>{{ edgeCount }}</strong>
            </div>
            <div class="metric-card" :class="{ danger: orphanCount > 0 }">
              <span>孤儿节点引用</span>
              <strong>{{ orphanCount }}</strong>
            </div>
            <div class="metric-card">
              <span>涉及来源表</span>
              <strong>{{ bucketCount }}</strong>
            </div>
          </div>
        </transition>

        <transition-group name="chip-pop" tag="div" class="orphan-chip-list" v-if="scanReport?.unionOrphanNodeIds?.length">
          <span v-for="id in scanReport.unionOrphanNodeIds" :key="id" class="orphan-chip">{{ id }}</span>
        </transition-group>

        <div class="result-box" v-if="lastMessage">
          {{ lastMessage }}
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { teacherCoursewareApi } from '../../services/v1/coursewareApi'

const props = defineProps({
  courseId: {
    type: String,
    required: true
  },
  courseName: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['cite-resource'])

const kbTabs = [
  { id: 'mine', label: '我的教学资源' },
  { id: 'students', label: '学生高频收藏' },
  { id: 'public', label: '公共资源库' },
  { id: 'graph', label: '知识图谱维护' }
]

const activeKbTab = ref('mine')
const publicFilter = ref('')

const myTeachingResources = computed(() => [
  {
    id: 'mr1',
    type: '教案',
    title: `${props.courseName || '本课'} · 分治策略简案`,
    course: props.courseName || '当前课程',
    node: '算法思想 / 分治',
    desc: '与当前课件节点对齐的简案骨架，可直接插入讲稿后微调。'
  },
  {
    id: 'mr2',
    type: '视频',
    title: '递归可视化 12′ 补充讲解',
    course: props.courseName || '当前课程',
    node: '递归基础',
    desc: '用于突破「递归基础」卡点的课堂穿插视频（演示数据）。'
  },
  {
    id: 'mr3',
    type: '习题',
    title: '随堂小测 · 主定理判定 6 题',
    course: props.courseName || '当前课程',
    node: '复杂度分析',
    desc: '与学情错误率联动的随堂测（前端占位，可对接题库）。'
  }
])

const studentHotList = computed(() => [
  { id: 'sh1', title: '学生反复拖拽的「快排动画」微课', node: '排序 / 快排', hot: 96, favorites: 28 },
  { id: 'sh2', title: '主定理一页纸速记', node: '复杂度', hot: 88, favorites: 21 }
])

const publicPool = ref([
  {
    id: 'pb1',
    type: '慕课',
    title: '分治与递归 · 名校公开课节选',
    source: '高校慕课联盟',
    url: 'https://example.edu/open-course/divide-conquer-demo',
    node: '分治与递归'
  },
  {
    id: 'pb2',
    type: '题库',
    title: '算法分析基础 · 50 题',
    source: '平台合规题库',
    url: 'https://example.edu/question-bank/algo-analysis-50',
    node: '复杂度分析'
  }
])

const publicFiltered = computed(() => {
  const q = publicFilter.value.trim()
  if (!q) return publicPool.value
  return publicPool.value.filter((i) => `${i.title} ${i.source}`.includes(q))
})

const hintEdit = () => {
  window.alert('演示环境：标签编辑可对接资源元数据接口。')
}

const hintSave = () => {
  window.alert('演示环境：已记入「保存到我的资源」动作（可对接收藏 API）。')
}

const emitCite = (item) => {
  emit('cite-resource', {
    ...item,
    courseName: props.courseName
  })
}

const syncLoading = ref(false)
const scanLoading = ref(false)
const repairLoading = ref(false)

const syncPayload = ref(null)
const scanReport = ref(null)
const lastMessage = ref('')

const summaryVisible = computed(() => Boolean(syncPayload.value || scanReport.value))
const edgeCount = computed(() => Number(syncPayload.value?.edgeCount || 0))
const orphanCount = computed(() => Number(scanReport.value?.unionOrphanNodeIds?.length || 0))
const bucketCount = computed(() => Number(scanReport.value?.buckets?.length || 0))

const handleSync = async () => {
  if (!props.courseId || syncLoading.value) return
  syncLoading.value = true
  lastMessage.value = ''
  try {
    const resp = await teacherCoursewareApi.syncKnowledgeGraph(props.courseId)
    syncPayload.value = resp?.data || {}
    lastMessage.value = `同步完成：共 ${edgeCount.value} 条关系边。`
  } catch (err) {
    lastMessage.value = `同步失败：${err.message || err}`
  } finally {
    syncLoading.value = false
  }
}

const handleScan = async () => {
  if (!props.courseId || scanLoading.value) return
  scanLoading.value = true
  lastMessage.value = ''
  try {
    const resp = await teacherCoursewareApi.getKnowledgeGraphReferenceHealth(props.courseId)
    scanReport.value = resp?.data || null
    if (scanReport.value?.hasOrphans) {
      lastMessage.value = `发现 ${orphanCount.value} 个孤儿引用，建议修复。`
    } else {
      lastMessage.value = '扫描完成：未发现孤儿引用。'
    }
  } catch (err) {
    lastMessage.value = `扫描失败：${err.message || err}`
  } finally {
    scanLoading.value = false
  }
}

const handleRepair = async () => {
  if (!props.courseId || repairLoading.value || !scanReport.value?.hasOrphans) return
  repairLoading.value = true
  lastMessage.value = ''
  try {
    await teacherCoursewareApi.repairKnowledgeGraphReferences(props.courseId, {
      confirm: true,
      nodeIds: scanReport.value.unionOrphanNodeIds || []
    })
    lastMessage.value = '修复完成，正在自动重新扫描...'
    await handleScan()
  } catch (err) {
    lastMessage.value = `修复失败：${err.message || err}`
  } finally {
    repairLoading.value = false
  }
}
</script>

<style scoped>
.kb-page {
  padding: 16px 24px 24px;
  min-height: 520px;
  box-sizing: border-box;
}

.kb-page-head h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333333;
}

.kb-lead {
  margin: 8px 0 0;
  font-size: 14px;
  color: #666666;
  line-height: 1.55;
  max-width: 72ch;
}

.kb-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 16px 0;
}

.kb-tab {
  border: 1px solid #d0d7de;
  background: #fff;
  color: #666666;
  font-size: 14px;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: transform 0.15s ease;
}

.kb-tab.active {
  background: #2d8cf0;
  border-color: #2d8cf0;
  color: #fff;
}

.kb-tab:active {
  transform: scale(0.96);
}

.kb-panel {
  border-radius: 8px;
  padding: 16px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border: 1px solid #e8e8e8;
  min-height: 360px;
}

.kb-hint {
  margin: 0 0 14px;
  font-size: 12px;
  color: #999999;
  line-height: 1.5;
}

.res-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.res-card {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #fafafa;
}

.res-card-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.res-card-head strong {
  font-size: 14px;
  color: #333333;
}

.res-type,
.hot-tag {
  font-size: 12px;
  color: #2d8cf0;
  font-weight: 600;
}

.res-meta {
  margin: 0;
  font-size: 12px;
  color: #999999;
}

.res-desc {
  margin: 0;
  font-size: 13px;
  color: #666666;
  line-height: 1.45;
  flex: 1;
}

.res-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

.btn-main {
  border: none;
  background: #2d8cf0;
  color: #fff;
  font-size: 14px;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
}

.btn-main:hover {
  filter: brightness(0.97);
}

.btn-main:active {
  transform: scale(0.96);
}

.btn-sub {
  border: 1px solid #2d8cf0;
  background: #fff;
  color: #2d8cf0;
  font-size: 14px;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  margin-bottom: 14px;
}

.filter-row label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
  color: #666666;
}

.filter-row input {
  min-width: 220px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid #d0d7de;
}

.graph-embed .graph-panel-shell {
  margin: 0;
  box-shadow: none;
  border: none;
  padding: 0;
  background: transparent;
}

.graph-panel-shell {
  border-radius: 8px;
  padding: 12px 0;
}

.graph-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.graph-panel-head h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
  color: #333333;
}

.graph-panel-head p {
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: #666666;
}

.action-row {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.action-btn {
  border: 1px solid #b9d7ca;
  border-radius: 8px;
  padding: 8px 10px;
  background: #ffffff;
  color: #2f605a;
  font-size: 12px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.action-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 16px rgba(46, 89, 74, 0.12);
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn.primary {
  background: linear-gradient(180deg, #7dc3ad 0%, #5ca68f 100%);
  color: #ffffff;
  border-color: transparent;
}

.action-btn.warn {
  background: linear-gradient(180deg, #fff8ef 0%, #fff0dc 100%);
  border-color: #f5d5a5;
  color: #925900;
}

.summary-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.metric-card {
  border: 1px solid rgba(92, 166, 143, 0.2);
  border-radius: 10px;
  background: #ffffff;
  padding: 8px;
  min-width: 0;
}

.metric-card span {
  font-size: 11px;
  color: #6a847a;
}

.metric-card strong {
  margin-top: 4px;
  display: block;
  font-size: 14px;
  color: #21483e;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-card.danger {
  border-color: rgba(228, 92, 92, 0.28);
  background: linear-gradient(180deg, #fffaf9 0%, #fff1f0 100%);
}

.orphan-chip-list {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 96px;
  overflow: auto;
}

.orphan-chip {
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid rgba(228, 92, 92, 0.3);
  background: #fff5f4;
  color: #b14a4a;
  font-size: 11px;
}

.result-box {
  margin-top: 10px;
  border-radius: 9px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: #365b52;
  border: 1px solid #d2e5dc;
  background: #ffffff;
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.24s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(5px);
}

.chip-pop-enter-active,
.chip-pop-leave-active {
  transition: all 0.22s ease;
}

.chip-pop-enter-from,
.chip-pop-leave-to {
  opacity: 0;
  transform: scale(0.92);
}
</style>
