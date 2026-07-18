<template>
  <div class="tab-content teacher-stats-flywheel">
    <div class="stats-header" v-if="currentCourseId">
      <h4>学情诊断中枢 - {{ currentCourseName }}</h4>
      <p>融合卡点、答题与课堂互动数据，输出结论并联动备课 / 资源 / 迭代，形成「数据 → 行动」闭环。</p>
    </div>

    <div v-if="currentCourseId" class="stats-subnav" role="tablist">
      <button
        v-for="tab in statTabs"
        :key="tab.id"
        type="button"
        role="tab"
        :aria-selected="activeStatsTab === tab.id"
        :class="['stats-subnav-btn', { active: activeStatsTab === tab.id }]"
        @click="setActiveStatsTab(tab.id)"
      >
        {{ tab.label }}
      </button>
    </div>

    <div v-if="currentCourseId && activeStatsTab === 'overview'" class="stats-layout">
      <section class="summary-grid">
        <article class="stat-card">
          <div class="stat-value">{{ studentStats.totalQuestions || 0 }}</div>
          <div class="stat-label">总提问数</div>
        </article>
        <article class="stat-card">
          <div class="stat-value">{{ studentStats.activeSessions || 0 }}</div>
          <div class="stat-label">活跃会话数</div>
        </article>
        <article class="stat-card">
          <div class="stat-value">{{ Math.round(Number(studentStats.avgTurnsPerSession || 0) * 10) / 10 }}</div>
          <div class="stat-label">平均追问轮次</div>
        </article>
        <article class="stat-card">
          <div class="stat-value">{{ Math.round(Number(masteryRadar.avgMastery || 0)) }}%</div>
          <div class="stat-label">平均掌握度</div>
        </article>
      </section>

      <section class="decision-board">
        <div class="decision-title">决策建议</div>
        <div class="decision-summary">{{ learningInsights.summary || '暂无建议' }}</div>
        <div class="decision-grid">
          <article class="decision-card">
            <h5>建议重讲节点</h5>
            <ul>
              <li v-for="item in reteachNodes" :key="item.nodeId">
                <strong>{{ item.title }}</strong>
                <span>P{{ item.page }} | 错误率 {{ Math.round((Number(item.errorRate || 0) * 1000)) / 10 }}%</span>
              </li>
              <li v-if="reteachNodes.length === 0" class="empty-row">暂无明显重讲节点</li>
            </ul>
          </article>
          <article class="decision-card">
            <h5>建议补前置知识</h5>
            <ul>
              <li v-for="item in prerequisiteGaps" :key="`${item.nodeId}_${item.suggestedPrereqId}`">
                <strong>{{ item.title }}</strong>
                <span>建议前置：{{ item.suggestedPrereq }} ({{ item.suggestedPrereqId }})</span>
              </li>
              <li v-if="prerequisiteGaps.length === 0" class="empty-row">暂无前置缺口</li>
            </ul>
          </article>
        </div>
        <div class="decision-grid extra">
          <article class="decision-card">
            <h5>薄弱知识点 Top3</h5>
            <ul>
              <li v-for="(item, idx) in weakTop3" :key="item.nodeId || idx">
                <strong>TOP{{ idx + 1 }} · {{ item.title || item.nodeId }}</strong>
                <span>掌握度 {{ Math.round(Number(item.masteryScore || 0)) }}% · 错误率 {{ Math.round(Number(item.errorRate || 0) * 1000) / 10 }}%</span>
              </li>
              <li v-if="weakTop3.length === 0" class="empty-row">暂无薄弱知识点数据</li>
            </ul>
          </article>
          <article class="decision-card">
            <h5>AI 生成教学优化建议</h5>
            <ul>
              <li v-for="tip in aiTeachingSuggestions" :key="tip.id">
                <strong>{{ tip.title }}</strong>
                <span>{{ tip.detail }}</span>
              </li>
              <li v-if="aiTeachingSuggestions.length === 0" class="empty-row">暂无可生成建议</li>
            </ul>
          </article>
        </div>
      </section>

      <section class="chart-grid">
        <article class="chart-card">
          <header>
            <h5>知识点热力图</h5>
            <span>热力 = 提问 + 对话 + 重讲加权</span>
          </header>
          <div class="chart-view" ref="heatmapChartRef"></div>
        </article>

        <article class="chart-card full-width">
          <header>
            <h5>班级学情趋势图</h5>
            <span>按天观察活跃人数、提问与重讲变化</span>
          </header>
          <div class="chart-view trend" ref="trendChartRef"></div>
        </article>
      </section>

      <section class="node-table-card">
        <div class="table-header">
          <h5>节点聚合指标</h5>
          <button
            v-if="hasUncoveredNodes"
            type="button"
            class="tiny-filter-btn"
            @click="onlyUncovered = !onlyUncovered"
          >
            {{ onlyUncovered ? '显示全部节点' : '仅看未覆盖节点' }}
          </button>
        </div>
        <div class="node-table" v-if="filteredNodeStats.length">
          <div class="row head">
            <span>节点</span>
            <span>提问</span>
            <span>停留(秒)</span>
            <span>错误率</span>
            <span>掌握度</span>
          </div>
          <div class="row" v-for="item in filteredNodeStats" :key="item.nodeId">
            <span>{{ item.title || item.nodeId }}</span>
            <span>{{ item.questionCount || item.dialogueCount || 0 }}</span>
            <span>{{ Number(item.stayTime || 0).toFixed(1) }}</span>
            <span>{{ Math.round(Number(item.errorRate || 0) * 1000) / 10 }}%</span>
            <span>{{ Math.round(Number(item.masteryScore || 0)) }}%</span>
          </div>
        </div>
        <div class="empty-tip" v-else>暂无节点聚合数据</div>
      </section>
    </div>

    <section v-if="currentCourseId && activeStatsTab === 'mastery'" class="stats-layout secondary-tab">
      <article class="narrative-card">
        <h5>知识点掌握度</h5>
        <p class="muted">
          雷达维度来自班级在各知识节点的聚合掌握度；数值越高表示该维度整体掌握越好。数据与下方节点表同源，可按页码追溯到讲稿节点。
        </p>
      </article>
      <div class="chart-card full-width">
        <header>
          <h5>掌握度雷达</h5>
          <span>按知识维度聚合</span>
        </header>
        <div class="chart-view" ref="radarChartRef"></div>
      </div>
      <section class="node-table-card">
        <div class="table-header">
          <h5>节点掌握度明细</h5>
        </div>
        <div class="node-table" v-if="filteredNodeStats.length">
          <div class="row head">
            <span>节点</span>
            <span>提问</span>
            <span>停留(秒)</span>
            <span>错误率</span>
            <span>掌握度</span>
          </div>
          <div class="row" v-for="item in filteredNodeStats" :key="item.nodeId + '-m'">
            <span>{{ item.title || item.nodeId }}</span>
            <span>{{ item.questionCount || item.dialogueCount || 0 }}</span>
            <span>{{ Number(item.stayTime || 0).toFixed(1) }}</span>
            <span>{{ Math.round(Number(item.errorRate || 0) * 1000) / 10 }}%</span>
            <span>{{ Math.round(Number(item.masteryScore || 0)) }}%</span>
          </div>
        </div>
        <div class="empty-tip" v-else>暂无节点数据</div>
      </section>
    </section>

    <section v-if="currentCourseId && activeStatsTab === 'bottleneck'" class="stats-layout secondary-tab bottleneck-tab">
      <article class="narrative-card">
        <h5>班级学习卡点可视化分析</h5>
        <p class="muted">
          数据来源：学生课堂学习行为、停留时长、重讲次数、提问与错题表现。下方热力图纵轴为指标，横轴为章节页码/知识节点；色块越深表示该项越高、卡点越突出。
        </p>
        <div class="formula-box">
          <strong>卡点指数（0–10）计算</strong>
          <p>
            对各指标在班级内做 Min-Max 归一化后：
            卡点指数 = 0.4×N(停留时长) + 0.3×N(重讲次数) + 0.2×N(提问量) + 0.1×N(错题率)，再映射到 0–10。数值越高，该节点越值得优先干预。
          </p>
        </div>
      </article>
      <div class="chart-card full-width">
        <header>
          <h5>全章节卡点热力图</h5>
          <span>与学情权重算法联动（演示数据可来自学情聚合接口）</span>
        </header>
        <div class="chart-view bottleneck-heatmap" ref="bottleneckHeatmapRef"></div>
      </div>
      <section class="bottleneck-actions-card">
        <h5>高卡点节点 · 落地操作</h5>
        <p class="muted">每个节点可一键跳转资源推荐或学情迭代队列，与备课工作台联动。</p>
        <div class="bottleneck-node-list">
          <article v-for="row in bottleneckActionRows" :key="row.nodeId" class="bn-row">
            <div>
              <strong>{{ row.title }}</strong>
              <span class="muted">P{{ row.page }} · 卡点指数 {{ row.cardIndex.toFixed(1) }}</span>
            </div>
            <div class="bn-actions">
              <button type="button" class="btn-ghost" @click="emitViewNode(row)">查看详情</button>
              <button type="button" class="btn-primary" @click="emitRecommend(row)">推荐资源</button>
              <button type="button" class="btn-secondary" @click="emitQueueIteration(row)">加入迭代建议</button>
            </div>
          </article>
          <div v-if="!bottleneckActionRows.length" class="empty-tip">暂无可操作卡点节点</div>
        </div>
      </section>
    </section>

    <section v-if="currentCourseId && activeStatsTab === 'mistakes'" class="stats-layout secondary-tab">
      <article class="narrative-card">
        <h5>错题分析</h5>
        <p class="muted">按节点错误率排序，优先处理错误率高且样本量足够的知识点。</p>
      </article>
      <section class="node-table-card">
        <div class="node-table" v-if="mistakeHeavyNodes.length">
          <div class="row head row--four">
            <span>节点</span>
            <span>错误率</span>
            <span>掌握度</span>
            <span>提问</span>
          </div>
          <div class="row row--four" v-for="item in mistakeHeavyNodes" :key="item.nodeId + '-e'">
            <span>{{ item.title || item.nodeId }}</span>
            <span>{{ Math.round(Number(item.errorRate || 0) * 1000) / 10 }}%</span>
            <span>{{ Math.round(Number(item.masteryScore || 0)) }}%</span>
            <span>{{ item.questionCount || 0 }}</span>
          </div>
        </div>
        <div class="empty-tip" v-else>暂无错题聚合数据</div>
      </section>
    </section>

    <section v-if="currentCourseId && activeStatsTab === 'qa'" class="stats-layout secondary-tab">
      <article class="narrative-card">
        <h5>问答详情</h5>
        <p class="muted">
          班级提问与师生问答的明细请在「提问统计」中按页码/节点筛选；此处保留学情总览入口，避免重复造轮子。
        </p>
        <p class="hint-line">提示：从左侧菜单进入「提问统计」可查看全文与导出。</p>
      </article>
    </section>

    <div v-if="!currentCourseId" class="empty-tip">请先选择一个课件查看学情数据</div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  currentCourseId: {
    type: String,
    default: ''
  },
  currentCourseName: {
    type: String,
    default: ''
  },
  studentStats: {
    type: Object,
    default: () => ({
      totalQuestions: 0,
      hotPages: [],
      keyDifficulties: '暂无',
      nodeStats: [],
      mappingCoverage: null,
      nodeHeatmap: [],
      masteryRadar: { indicators: [], values: [], avgMastery: 0 },
      classTrend: [],
      learningInsights: { reteachNodes: [], prerequisiteGaps: [], summary: '' }
    })
  },
  cardData: {
    type: Array,
    default: () => []
  },
  initialStatsTab: {
    type: String,
    default: 'overview'
  }
})

const emit = defineEmits(['update:statsTab', 'open-smart-resource', 'queue-iteration-node'])

const statTabs = [
  { id: 'overview', label: '班级总览' },
  { id: 'mastery', label: '知识点掌握度' },
  { id: 'bottleneck', label: '学习卡点诊断' },
  { id: 'mistakes', label: '错题分析' },
  { id: 'qa', label: '问答详情' }
]

const activeStatsTab = ref('overview')

watch(
  () => props.initialStatsTab,
  (v) => {
    if (v && statTabs.some((t) => t.id === v)) {
      activeStatsTab.value = v
    }
  },
  { immediate: true }
)

const setActiveStatsTab = (id) => {
  activeStatsTab.value = id
  emit('update:statsTab', id)
}

const onlyUncovered = ref(false)
const heatmapChartRef = ref(null)
const radarChartRef = ref(null)
const trendChartRef = ref(null)
const bottleneckHeatmapRef = ref(null)

let heatmapChart = null
let radarChart = null
let trendChart = null
let bottleneckChart = null

const nodeStats = computed(() => (Array.isArray(props.studentStats?.nodeStats) ? props.studentStats.nodeStats : []))
const heatmapData = computed(() => (Array.isArray(props.studentStats?.nodeHeatmap) ? props.studentStats.nodeHeatmap : []))
const masteryRadar = computed(() => props.studentStats?.masteryRadar || { indicators: [], values: [], avgMastery: 0 })
const classTrend = computed(() => (Array.isArray(props.studentStats?.classTrend) ? props.studentStats.classTrend : []))
const learningInsights = computed(() => props.studentStats?.learningInsights || { reteachNodes: [], prerequisiteGaps: [], summary: '' })

const reteachNodes = computed(() => {
  const list = Array.isArray(learningInsights.value?.reteachNodes) ? learningInsights.value.reteachNodes : []
  return list.slice(0, 6)
})

const prerequisiteGaps = computed(() => {
  const list = Array.isArray(learningInsights.value?.prerequisiteGaps) ? learningInsights.value.prerequisiteGaps : []
  return list.slice(0, 6)
})

const uncoveredNodeIdSet = computed(() => {
  const ids = props.studentStats?.mappingCoverage?.uncoveredNodeIds
  if (!Array.isArray(ids) || ids.length === 0) return new Set()
  return new Set(ids.map(item => String(item || '').trim()).filter(Boolean))
})

const hasUncoveredNodes = computed(() => uncoveredNodeIdSet.value.size > 0)

const filteredNodeStats = computed(() => {
  if (!onlyUncovered.value || uncoveredNodeIdSet.value.size === 0) {
    return nodeStats.value
  }
  return nodeStats.value.filter(item => uncoveredNodeIdSet.value.has(String(item?.nodeId || '').trim()))
})

const weakTop3 = computed(() => {
  const list = (nodeStats.value || [])
    .map((item) => ({
      ...item,
      masteryScore: Number(item?.masteryScore || 0),
      errorRate: Number(item?.errorRate || 0),
      questionCount: Number(item?.questionCount || item?.dialogueCount || 0)
    }))
    .sort((a, b) => {
      if (a.masteryScore !== b.masteryScore) return a.masteryScore - b.masteryScore
      if (a.errorRate !== b.errorRate) return b.errorRate - a.errorRate
      return b.questionCount - a.questionCount
    })
  return list.slice(0, 3)
})

const aiTeachingSuggestions = computed(() => {
  const top = weakTop3.value
  if (!top.length) return []

  const first = top[0]
  const second = top[1] || top[0]
  const third = top[2] || top[0]
  return [
    {
      id: 'teacher-opt-1',
      title: `优先重讲「${first.title || first.nodeId}」`,
      detail: `建议先用 8-10 分钟回顾核心概念，再安排 2-3 题当堂检测；当前掌握度 ${Math.round(first.masteryScore)}%。`
    },
    {
      id: 'teacher-opt-2',
      title: `前置补偿「${second.title || second.nodeId}」`,
      detail: `该节点错误率 ${Math.round(second.errorRate * 1000) / 10}%，建议在讲新内容前增加前置知识快问快答。`
    },
    {
      id: 'teacher-opt-3',
      title: `分层练习强化「${third.title || third.nodeId}」`,
      detail: `按基础/提升两层布置练习，结合课堂追问数据（提问 ${third.questionCount} 次）做针对性讲评。`
    }
  ]
})

const enrichedNodes = computed(() => {
  const raw = nodeStats.value || []
  const mapped = raw.map((n) => {
    const page = Number(n.page) || 1
    const matchCard = (props.cardData || []).find((c) => Number(c.page) === page)
    return {
      ...n,
      page,
      stayTime: Number(n.stayTime ?? matchCard?.停留时长 ?? 0),
      reteachCount: Number(n.reteachCount ?? n.reteach ?? matchCard?.需重讲 ?? 0),
      questionCount: Number(n.questionCount ?? n.dialogueCount ?? matchCard?.提问量 ?? 0),
      errorRate: Number(n.errorRate ?? 0)
    }
  })
  if (mapped.length) return mapped
  return [
    { nodeId: 'demo_1', title: '示例节点 A', page: 1, stayTime: 120, reteachCount: 2, questionCount: 6, errorRate: 0.35 },
    { nodeId: 'demo_2', title: '示例节点 B', page: 2, stayTime: 80, reteachCount: 1, questionCount: 4, errorRate: 0.22 }
  ]
})

const minMaxNorm = (arr) => {
  const nums = arr.map((x) => Number(x) || 0)
  const lo = Math.min(...nums)
  const hi = Math.max(...nums)
  const span = hi - lo || 1
  return nums.map((v) => (v - lo) / span)
}

const nodesWithCardIndex = computed(() => {
  const rows = enrichedNodes.value
  const stay = rows.map((r) => r.stayTime)
  const rt = rows.map((r) => r.reteachCount)
  const q = rows.map((r) => r.questionCount)
  const er = rows.map((r) => r.errorRate)
  const ns = minMaxNorm(stay)
  const nr = minMaxNorm(rt)
  const nq = minMaxNorm(q)
  const ne = minMaxNorm(er)
  return rows.map((r, i) => {
    const cardIndex = 10 * (0.4 * ns[i] + 0.3 * nr[i] + 0.2 * nq[i] + 0.1 * ne[i])
    return {
      ...r,
      cardIndex
    }
  })
})

const bottleneckActionRows = computed(() => {
  return [...nodesWithCardIndex.value]
    .sort((a, b) => b.cardIndex - a.cardIndex)
    .slice(0, 8)
})

const mistakeHeavyNodes = computed(() => {
  return [...nodesWithCardIndex.value]
    .sort((a, b) => b.errorRate - a.errorRate)
    .slice(0, 12)
})

const emitRecommend = (row) => {
  const title = String(row.title || row.nodeId || '').trim()
  if (!title) return
  emit('open-smart-resource', {
    keyword: title,
    matchReason: `班级学情：${row.title || title} 卡点指数 ${row.cardIndex.toFixed(1)}，错误率 ${(row.errorRate * 100).toFixed(1)}%`
  })
}

const emitQueueIteration = (row) => {
  emit('queue-iteration-node', {
    title: row.title || row.nodeId,
    nodeId: row.nodeId
  })
}

const emitViewNode = (row) => {
  setActiveStatsTab('overview')
  // eslint-disable-next-line no-console
  console.info('[学情详情]', row)
}

const disposeAllCharts = () => {
  if (heatmapChart) {
    heatmapChart.dispose()
    heatmapChart = null
  }
  if (radarChart) {
    radarChart.dispose()
    radarChart = null
  }
  if (trendChart) {
    trendChart.dispose()
    trendChart = null
  }
  if (bottleneckChart) {
    bottleneckChart.dispose()
    bottleneckChart = null
  }
}

const ensureCharts = () => {
  if (heatmapChartRef.value && !heatmapChart) {
    heatmapChart = echarts.init(heatmapChartRef.value)
  }
  if (radarChartRef.value && !radarChart) {
    radarChart = echarts.init(radarChartRef.value)
  }
  if (trendChartRef.value && !trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }
  if (bottleneckHeatmapRef.value && !bottleneckChart) {
    bottleneckChart = echarts.init(bottleneckHeatmapRef.value)
  }
}

const renderHeatmap = () => {
  if (!heatmapChart) return
  const labels = heatmapData.value.map(item => item.title || item.nodeId || '-')
  const values = heatmapData.value.map(item => Number(item.heat || 0))
  heatmapChart.setOption({
    grid: { left: 70, right: 18, top: 26, bottom: 24 },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#64748b' }
    },
    yAxis: {
      type: 'category',
      data: labels,
      axisLabel: { color: '#334155', width: 150, overflow: 'truncate' }
    },
    series: [{
      type: 'bar',
      data: values,
      itemStyle: {
        color: params => {
          const value = Number(params.value || 0)
          if (value >= 15) return '#dc2626'
          if (value >= 8) return '#f97316'
          return '#0f766e'
        },
        borderRadius: [0, 10, 10, 0]
      },
      label: { show: true, position: 'right', color: '#1e293b' }
    }],
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    }
  }, true)
}

const renderRadar = () => {
  if (!radarChart) return
  const indicators = Array.isArray(masteryRadar.value?.indicators) ? masteryRadar.value.indicators : []
  const values = Array.isArray(masteryRadar.value?.values) ? masteryRadar.value.values : []
  radarChart.setOption({
    radar: {
      indicator: indicators.length ? indicators : [{ name: '暂无数据', max: 100 }],
      radius: '60%',
      splitArea: { areaStyle: { color: ['#f8fafc', '#eef2ff'] } },
      axisName: { color: '#334155' }
    },
    series: [{
      type: 'radar',
      data: [{
        value: values.length ? values : [0],
        name: '掌握度',
        areaStyle: { color: 'rgba(15, 118, 110, 0.25)' },
        lineStyle: { color: '#0f766e' },
        itemStyle: { color: '#0f766e' }
      }]
    }],
    tooltip: {}
  }, true)
}

const renderTrend = () => {
  if (!trendChart) return
  const rows = classTrend.value
  const days = rows.map(item => item.day)
  const question = rows.map(item => Number(item.questionCount || 0))
  const reteach = rows.map(item => Number(item.reteachCount || 0))
  const errorRate = rows.map(item => Math.round(Number(item.errorRate || 0) * 1000) / 10)
  const activeUsers = rows.map((item) => {
    const v = item.activeUsers ?? item.active_sessions ?? item.dailyActiveUsers
    return v === undefined || v === null ? null : Number(v)
  })
  const hasActiveUsers = activeUsers.some((v) => v !== null && !Number.isNaN(v) && v >= 0)

  const series = []
  if (hasActiveUsers) {
    series.push({
      name: '活跃人数',
      type: 'line',
      data: activeUsers.map((v) => (v === null || Number.isNaN(v) ? 0 : v)),
      smooth: true,
      itemStyle: { color: '#6366f1' },
      lineStyle: { width: 2 }
    })
  }
  series.push(
    { name: '提问次数', type: 'line', data: question, smooth: true, itemStyle: { color: '#0f766e' } },
    { name: '重讲次数', type: 'line', data: reteach, smooth: true, itemStyle: { color: '#f97316' } },
    { name: '错误率', type: 'bar', yAxisIndex: 1, data: errorRate, itemStyle: { color: '#dc2626', opacity: 0.6 } }
  )

  trendChart.setOption({
    legend: { top: 4, textStyle: { color: '#475569' } },
    tooltip: { trigger: 'axis' },
    grid: { left: 42, right: 46, top: hasActiveUsers ? 48 : 40, bottom: 30 },
    xAxis: { type: 'category', data: days, axisLabel: { color: '#64748b' } },
    yAxis: [
      { type: 'value', name: '次数 / 人数', axisLabel: { color: '#64748b' }, splitLine: { lineStyle: { color: '#e2e8f0' } } },
      { type: 'value', name: '错误率%', axisLabel: { color: '#64748b' } }
    ],
    series
  }, true)
}

const renderBottleneckHeatmap = () => {
  if (!bottleneckChart) return
  const rows = nodesWithCardIndex.value.slice(0, 14)
  if (!rows.length) {
    bottleneckChart.clear()
    return
  }
  const xCats = rows.map((r) => `P${r.page}·${String(r.title || r.nodeId).slice(0, 8)}`)
  const yCats = ['停留时长', '重讲次数', '提问量', '错题率×10', '卡点指数']
  const data = []
  rows.forEach((r, xi) => {
    data.push([xi, 0, r.stayTime])
    data.push([xi, 1, r.reteachCount])
    data.push([xi, 2, r.questionCount])
    data.push([xi, 3, r.errorRate * 10])
    data.push([xi, 4, r.cardIndex])
  })
  const maxVal = Math.max(...data.map((d) => Number(d[2]) || 0), 1)
  bottleneckChart.setOption({
    tooltip: {
      formatter: (p) => {
        const v = p.data
        const xi = v[0]
        const yi = v[1]
        const val = v[2]
        return `${xCats[xi]}<br/>${yCats[yi]}：${val}`
      }
    },
    grid: { left: 110, right: 24, top: 28, bottom: 72 },
    xAxis: {
      type: 'category',
      data: xCats,
      axisLabel: { color: '#666666', fontSize: 11, rotate: 28 }
    },
    yAxis: {
      type: 'category',
      data: yCats,
      axisLabel: { color: '#666666', fontSize: 12 }
    },
    visualMap: {
      min: 0,
      max: maxVal,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      inRange: { color: ['#f0f9ff', '#2d8cf0', '#7f1d1d'] }
    },
    series: [{
      type: 'heatmap',
      data,
      label: { show: false },
      emphasis: {
        itemStyle: { shadowBlur: 12, shadowColor: 'rgba(0,0,0,0.2)' }
      }
    }]
  }, true)
}

const renderForActiveTab = async () => {
  await nextTick()
  disposeAllCharts()
  if (!props.currentCourseId) return
  const tab = activeStatsTab.value
  if (tab === 'overview') {
    ensureCharts()
    renderHeatmap()
    renderTrend()
  } else if (tab === 'mastery') {
    ensureCharts()
    renderRadar()
  } else if (tab === 'bottleneck') {
    ensureCharts()
    renderBottleneckHeatmap()
  }
}

const handleResize = () => {
  if (heatmapChart) heatmapChart.resize()
  if (radarChart) radarChart.resize()
  if (trendChart) trendChart.resize()
  if (bottleneckChart) bottleneckChart.resize()
}

watch(
  () => activeStatsTab.value,
  () => {
    renderForActiveTab()
  }
)

watch(
  () => [heatmapData.value, masteryRadar.value, classTrend.value, nodesWithCardIndex.value, props.currentCourseId, props.cardData],
  () => {
    renderForActiveTab()
  },
  { deep: true }
)

onMounted(() => {
  renderForActiveTab()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  disposeAllCharts()
})
</script>

<style scoped>
.tab-content {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 14px;
  padding: 18px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
  overflow: auto;
}

.stats-header {
  margin-bottom: 16px;
}

.stats-header h4 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #333333;
}

.stats-header p {
  margin: 6px 0 0;
  color: #666666;
  font-size: 14px;
  line-height: 1.5;
}

.stats-subnav {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.stats-subnav-btn {
  border: 1px solid #d0d7de;
  background: #fff;
  color: #666666;
  font-size: 14px;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}

.stats-subnav-btn:hover {
  border-color: #2d8cf0;
  color: #2d8cf0;
}

.stats-subnav-btn.active {
  background: #2d8cf0;
  border-color: #2d8cf0;
  color: #fff;
  box-shadow: 0 2px 8px rgba(45, 140, 240, 0.25);
}

.stats-subnav-btn:active {
  transform: scale(0.96);
}

.narrative-card {
  border-radius: 8px;
  padding: 16px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border: 1px solid #e8e8e8;
}

.narrative-card h5 {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 500;
  color: #333333;
}

.muted {
  color: #666666;
  font-size: 14px;
  line-height: 1.55;
  margin: 0;
}

.formula-box {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 8px;
  background: #f7f9fc;
  border: 1px dashed #c5d6ee;
  font-size: 12px;
  color: #999999;
  line-height: 1.55;
}

.formula-box strong {
  display: block;
  color: #333333;
  margin-bottom: 6px;
  font-size: 13px;
}

.bottleneck-heatmap {
  height: 420px;
}

.bottleneck-actions-card {
  border-radius: 8px;
  padding: 16px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border: 1px solid #e8e8e8;
}

.bottleneck-actions-card h5 {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 500;
  color: #333333;
}

.bottleneck-node-list {
  display: grid;
  gap: 12px;
  margin-top: 12px;
}

.bn-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  background: #fafafa;
}

.bn-row strong {
  display: block;
  font-size: 14px;
  color: #333333;
}

.bn-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.btn-ghost {
  border: 1px solid #2d8cf0;
  background: #fff;
  color: #2d8cf0;
  font-size: 14px;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: transform 0.15s ease;
}

.btn-primary {
  border: none;
  background: #2d8cf0;
  color: #fff;
  font-size: 14px;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  transition: transform 0.15s ease;
}

.btn-secondary {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #666666;
  font-size: 14px;
  padding: 8px 16px;
  border-radius: 8px;
  cursor: pointer;
}

.btn-ghost:active,
.btn-primary:active,
.btn-secondary:active {
  transform: scale(0.96);
}

.hint-line {
  margin: 10px 0 0;
  font-size: 12px;
  color: #999999;
}

.row--four {
  grid-template-columns: 2fr 0.9fr 0.9fr 0.8fr;
}

.stats-layout {
  display: grid;
  gap: 14px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.stat-card {
  border: 1px solid #dbe5df;
  border-radius: 12px;
  padding: 14px;
  background: linear-gradient(180deg, #fbfdfc 0%, #f4f8f6 100%);
}

.stat-value {
  font-size: 28px;
  color: #0f172a;
  font-weight: 700;
}

.stat-label {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
}

.decision-board {
  border: 1px solid #dbe5df;
  border-radius: 12px;
  padding: 14px;
  background: #f8fbfa;
}

.decision-title {
  font-size: 16px;
  font-weight: 700;
  color: #14532d;
}

.decision-summary {
  margin-top: 6px;
  color: #334155;
  font-size: 13px;
}

.decision-grid {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.decision-grid.extra {
  margin-top: 10px;
}

.decision-card {
  border: 1px solid #cfded5;
  border-radius: 10px;
  background: #ffffff;
  padding: 10px;
}

.decision-card h5 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #0f172a;
}

.decision-card ul {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.decision-card li {
  display: grid;
  gap: 2px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 7px;
  background: #f8fafc;
}

.decision-card strong {
  font-size: 13px;
  color: #1e293b;
}

.decision-card span {
  font-size: 12px;
  color: #64748b;
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.chart-card {
  border: 1px solid #dbe5df;
  border-radius: 12px;
  padding: 10px;
  background: #ffffff;
}

.chart-card.full-width {
  grid-column: span 2;
}

.chart-card header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}

.chart-card h5 {
  margin: 0;
  color: #0f172a;
  font-size: 14px;
}

.chart-card span {
  color: #64748b;
  font-size: 12px;
}

.chart-view {
  margin-top: 8px;
  height: 280px;
}

.chart-view.trend {
  height: 300px;
}

.node-table-card {
  border: 1px solid #dbe5df;
  border-radius: 12px;
  background: #ffffff;
  padding: 12px;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.table-header h5 {
  margin: 0;
  font-size: 14px;
  color: #0f172a;
}

.node-table {
  display: grid;
  gap: 6px;
}

.row {
  display: grid;
  grid-template-columns: 2.3fr 0.8fr 0.9fr 0.8fr 0.8fr;
  gap: 8px;
  align-items: center;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px 10px;
  background: #f8fafc;
  font-size: 12px;
  color: #334155;
}

.row.head {
  background: #eef2f7;
  color: #1e293b;
  font-weight: 700;
}

.tiny-filter-btn {
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  color: #334155;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}

.empty-tip,
.empty-row {
  color: #64748b;
  font-size: 12px;
}

@media (max-width: 1200px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .decision-grid {
    grid-template-columns: 1fr;
  }

  .chart-grid {
    grid-template-columns: 1fr;
  }

  .chart-card.full-width {
    grid-column: span 1;
  }
}
</style>
