<template>
  <div class="aqp-container">
    <!-- 学情总览卡片 -->
    <section class="aqp-overview">
      <div class="aqp-card stat-card">
        <span class="stat-value">{{ studentStats.totalQuestions }}</span>
        <span class="stat-label">总提问量</span>
      </div>
      <div class="aqp-card stat-card">
        <span class="stat-value">{{ studentStats.activeSessions }}</span>
        <span class="stat-label">活跃会话</span>
      </div>
      <div class="aqp-card stat-card">
        <span class="stat-value">{{ studentStats.avgTurnsPerSession }}</span>
        <span class="stat-label">平均轮次</span>
      </div>
      <div class="aqp-card stat-card">
        <span class="stat-value">{{ studentStats.masteryRadar?.avgMastery || 0 }}%</span>
        <span class="stat-label">平均掌握度</span>
      </div>
    </section>

    <!-- 掌握度 + 难点 -->
    <section class="aqp-detail-row">
      <div class="aqp-card aqp-half">
        <h4>知识点掌握度</h4>
        <div v-if="!nodeStats.length" class="empty-tip">暂无数据</div>
        <div v-else class="mastery-list">
          <div v-for="node in topNodes" :key="node.nodeId" class="mastery-row">
            <span class="mastery-title">{{ node.title || node.nodeId }}</span>
            <div class="mastery-bar-track">
              <div
                class="mastery-bar-fill"
                :style="{ width: (node.masteryScore || 0) + '%' }"
                :class="masteryLevel(node.masteryScore)"
              ></div>
            </div>
            <span class="mastery-pct">{{ node.masteryScore || 0 }}%</span>
          </div>
        </div>
      </div>

      <div class="aqp-card aqp-half">
        <h4>教学难点 &amp; 建议</h4>
        <div v-if="!insights" class="empty-tip">暂无数据</div>
        <div v-else class="insights-content">
          <p class="insight-summary">{{ insights.summary }}</p>
          <div v-if="insights.reteachNodes?.length" class="insight-group">
            <strong>需重讲节点:</strong>
            <span
              v-for="n in insights.reteachNodes.slice(0, 5)"
              :key="n.nodeId"
              class="insight-tag tag-warn"
            >{{ n.title || n.nodeId }}</span>
          </div>
          <div v-if="insights.prerequisiteGaps?.length" class="insight-group">
            <strong>前置知识缺口:</strong>
            <span
              v-for="g in insights.prerequisiteGaps.slice(0, 5)"
              :key="g.nodeId"
              class="insight-tag tag-info"
            >{{ g.title }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 提问记录 -->
    <section class="aqp-card aqp-questions">
      <div class="questions-header">
        <h4>提问记录 ({{ totalQuestions }})</h4>
        <div class="questions-filter">
          <label>筛选页码:</label>
          <select v-model="localFilterPage" class="filter-select">
            <option value="">全部</option>
            <option v-for="p in availablePages" :key="p" :value="p">第 {{ p }} 页</option>
          </select>
        </div>
      </div>

      <div v-if="!filteredList.length" class="empty-tip">暂无提问记录</div>
      <div v-else class="questions-table-wrap">
        <table class="questions-table">
          <thead>
            <tr>
              <th>学生</th>
              <th>页码</th>
              <th>节点</th>
              <th>问题</th>
              <th>回答</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in pagedQuestions" :key="q.id">
              <td class="td-student">{{ q.studentId }}</td>
              <td class="td-page">{{ q.page }}</td>
              <td class="td-node">{{ q.nodeTitle || q.nodeId || '-' }}</td>
              <td class="td-question">{{ q.content }}</td>
              <td class="td-answer">{{ q.answer?.slice(0, 60) }}{{ (q.answer?.length || 0) > 60 ? '...' : '' }}</td>
              <td class="td-time">{{ q.time }}</td>
            </tr>
          </tbody>
        </table>

        <!-- 分页 -->
        <div v-if="totalPages > 1" class="pagination">
          <button :disabled="currPage <= 1" @click="currPage--">← 上一页</button>
          <span>{{ currPage }} / {{ totalPages }}</span>
          <button :disabled="currPage >= totalPages" @click="currPage++">下一页 →</button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  studentStats: { type: Object, default: () => ({}) },
  cardData: { type: Array, default: () => [] },
  questionRecords: { type: Array, default: () => [] }
})

defineEmits(['update:filterPage'])

const localFilterPage = ref('')
const currPage = ref(1)
const pageSize = 20

const filteredList = computed(() => {
  if (!localFilterPage.value) return props.questionRecords
  const p = Number(localFilterPage.value)
  return props.questionRecords.filter(q => q.page === p)
})

const totalQuestions = computed(() => props.questionRecords.length)
const totalPages = computed(() => Math.max(1, Math.ceil(filteredList.value.length / pageSize)))
const pagedQuestions = computed(() => {
  const start = (currPage.value - 1) * pageSize
  return filteredList.value.slice(start, start + pageSize)
})

const nodeStats = computed(() => props.studentStats?.nodeStats || [])
const topNodes = computed(() =>
  [...nodeStats.value].sort((a, b) => (a.masteryScore || 0) - (b.masteryScore || 0)).slice(0, 8)
)

const insights = computed(() => props.studentStats?.learningInsights || null)

const availablePages = computed(() => {
  const pages = new Set(props.questionRecords.map(q => q.page).filter(Boolean))
  return [...pages].sort((a, b) => a - b)
})

watch(localFilterPage, (val) => {
  currPage.value = 1
  // 通知父组件
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('analytics:filterPage', { detail: val }))
  }
})

function masteryLevel(score) {
  const s = score || 0
  if (s >= 80) return 'bar-high'
  if (s >= 50) return 'bar-mid'
  return 'bar-low'
}
</script>

<style scoped>
.aqp-container { display: flex; flex-direction: column; gap: 16px; }

/* 总览卡片 */
.aqp-overview { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
@media (max-width: 900px) { .aqp-overview { grid-template-columns: repeat(2, 1fr); } }

.aqp-card {
  background: #fff; border: 1px solid #dbe6df; border-radius: 14px;
  padding: 16px; box-shadow: 0 2px 8px rgba(15,23,42,0.03);
}
.aqp-card h4 { margin: 0 0 10px; font-size: 15px; color: #2d5f58; }

.stat-card { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 20px 12px; }
.stat-value { font-size: 28px; font-weight: 700; color: #5ca68f; }
.stat-label { font-size: 13px; color: #607a71; }

/* 掌握度 + 难点双栏 */
.aqp-detail-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 900px) { .aqp-detail-row { grid-template-columns: 1fr; } }

.mastery-list { display: flex; flex-direction: column; gap: 8px; }
.mastery-row { display: flex; align-items: center; gap: 8px; }
.mastery-title { font-size: 13px; color: #334155; min-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mastery-bar-track { flex: 1; height: 8px; background: #f1f5f9; border-radius: 4px; overflow: hidden; }
.mastery-bar-fill { height: 100%; border-radius: 4px; transition: width 0.5s; }
.bar-high { background: #5ca68f; }
.bar-mid { background: #f59e0b; }
.bar-low { background: #ef4444; }
.mastery-pct { font-size: 12px; color: #94a3b8; min-width: 36px; text-align: right; }

/* 难点 & 建议 */
.insights-content { font-size: 13px; color: #334155; }
.insight-summary { margin: 0 0 10px; line-height: 1.5; color: #607a71; }
.insight-group { margin-bottom: 8px; }
.insight-group strong { display: block; font-size: 12px; color: #607a71; margin-bottom: 4px; }
.insight-tag { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 999px; margin: 2px 4px 2px 0; }
.tag-warn { background: #fef3c7; color: #92400e; }
.tag-info { background: #e0f2fe; color: #0369a1; }

/* 提问记录表 */
.questions-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.questions-filter { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #607a71; }
.filter-select { padding: 4px 8px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; background: #fff; }

.empty-tip { color: #94a3b8; text-align: center; padding: 30px 0; font-size: 14px; }

.questions-table-wrap { overflow-x: auto; }
.questions-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.questions-table th {
  background: #f8fafc; color: #607a71; font-weight: 600; text-align: left;
  padding: 8px 10px; border-bottom: 1px solid #e2e8f0; white-space: nowrap;
}
.questions-table td { padding: 8px 10px; border-bottom: 1px solid #f1f5f9; color: #334155; }
.questions-table tr:hover td { background: #f8fafc; }
.td-student { min-width: 80px; }
.td-page { min-width: 50px; text-align: center; }
.td-node { min-width: 80px; }
.td-question { min-width: 140px; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.td-answer { min-width: 100px; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #607a71; }
.td-time { min-width: 110px; font-size: 12px; color: #94a3b8; white-space: nowrap; }

.pagination { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 12px; }
.pagination button {
  padding: 4px 12px; border: 1px solid #cbd5e1; border-radius: 6px;
  background: #fff; cursor: pointer; font-size: 13px; color: #334155;
}
.pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.pagination span { font-size: 13px; color: #607a71; }
</style>
