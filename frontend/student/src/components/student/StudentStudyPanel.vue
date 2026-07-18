<template>
  <div class="study-analytics-page">
    <header class="analysis-header">
      <div class="analysis-header-main">
        <p class="header-kicker">Learning Analytics</p>
        <h3>AI学情诊断·精准学习指引</h3>
        <div class="flow-strip">
          <span class="flow-label">数据链路</span>
          <span class="flow-node">课堂行为采集</span>
          <span class="flow-arrow">→</span>
          <span class="flow-node">AI算法计算</span>
          <span class="flow-arrow">→</span>
          <span class="flow-node">学习行动推荐</span>
        </div>
      </div>

      <div class="analysis-header-controls">
        <el-select v-model="selectedCourse" size="small" style="width: 160px">
          <el-option label="本课程数据" value="current" />
          <el-option label="全课程数据" value="all" />
        </el-select>
        <el-select v-model="selectedTimeRange" size="small" style="width: 140px">
          <el-option label="本周" value="week" />
          <el-option label="本月" value="month" />
          <el-option label="本学期" value="term" />
        </el-select>
        <el-button size="small" @click="refreshData">刷新数据</el-button>
        <el-button size="small" type="primary" plain @click="exportReport">导出报告</el-button>
      </div>

      <p class="data-source-tip">
        数据更新时间：{{ dataUpdatedAt }} | 数据来源：课堂学习、随堂练习、问答互动、学习行为
      </p>
    </header>

    <section class="health-overview">
      <article class="health-radar-panel">
        <div class="panel-head">
          <div>
            <h4>学习健康度总览</h4>
            <p>用五维指标展示整体状态，并和上周做趋势对比</p>
          </div>
          <span class="health-delta" :class="{ down: healthDelta < 0 }">
            {{ healthDelta >= 0 ? '较上周↑' : '较上周↓' }}{{ Math.abs(healthDelta) }}分
          </span>
        </div>

        <div class="radar-body">
          <div ref="healthRadarRef" class="chart radar-chart"></div>
          <div class="score-core">
            <strong>{{ healthScore }}</strong>
            <small>综合学习健康度评分</small>
          </div>
        </div>
      </article>

      <aside class="issue-panel">
        <button class="issue-card weak" @click="jumpToWeaknessArea">
          <div class="issue-top">
            <span>⚠️ 薄弱知识点</span>
            <strong>{{ weakPointCards.length }}个待补强</strong>
          </div>
          <p>较上周{{ weakDeltaLabel }}</p>
          <el-progress :percentage="metrics.masteryRate" :show-text="false" :stroke-width="8" color="#f59e0b" />
          <small>已掌握 {{ metrics.masteryRate }}%</small>
        </button>

        <button class="issue-card mistake" @click="openMistakeDialog">
          <div class="issue-top">
            <span>📝 错题待重做</span>
            <strong>{{ metrics.retakeCount }}道待复盘</strong>
          </div>
          <p>平均正确率 {{ metrics.correctRate }}%</p>
          <small>点击查看错题详情弹窗</small>
        </button>

        <el-tooltip
          effect="dark"
          placement="left"
          content="专注度 = 有效学习时长 / 总学习时长，当前为 6.5h / 7.6h"
        >
          <button class="issue-card focus">
            <div class="issue-top">
              <span>⏱️ 学习专注度</span>
              <strong>{{ metrics.focusScore }}% 优秀</strong>
            </div>
            <p>本周有效学习时长 {{ metrics.effectiveHours }}h</p>
            <small>悬停查看计算规则</small>
          </button>
        </el-tooltip>

        <button class="issue-card qa" @click="openQaDialog">
          <div class="issue-top">
            <span>💬 互动问答</span>
            <strong>{{ metrics.qaCount }}次提问</strong>
          </div>
          <p>问题解决率 {{ metrics.qaResolveRate }}%</p>
          <small>高频提问：{{ topQuestionTopics }}</small>
        </button>
      </aside>
    </section>

    <section ref="diagnosisSectionRef" class="diagnosis-section">
      <div class="section-head">
        <div>
          <h4>核心问题诊断区</h4>
          <p>主页面只保留“薄弱点诊断”和“学习趋势分析”两个核心标签</p>
        </div>
        <el-button plain type="primary" @click="openMoreData">更多数据</el-button>
      </div>

      <el-tabs v-model="diagnosisTab" class="diagnosis-tabs">
        <el-tab-pane label="📌 薄弱点诊断" name="weakness">
          <div class="weak-grid">
            <article v-for="item in weakPointCards" :key="item.id" class="weak-card">
              <div class="weak-head">
                <div>
                  <h5>{{ item.name }}</h5>
                  <p>{{ item.chapter }} · 优先级{{ item.priority }}</p>
                </div>
                <span class="weak-score">{{ item.mastery }}%</span>
              </div>
              <p class="weak-reason">薄弱原因：{{ item.reason }}</p>
              <p class="weak-advice">AI建议：{{ item.advice }}</p>
              <div class="weak-actions">
                <el-button size="small" type="primary" plain @click="askAiExplain(item)">AI讲解</el-button>
                <el-button size="small" @click="collectWeakPoint(item)">收藏</el-button>
              </div>
            </article>
          </div>

          <div v-if="props.currentWeakPoint || props.currentExplain || props.currentTest" class="backend-feedback-panel">
            <h5>后端联动反馈</h5>
            <p v-if="props.currentWeakPoint">当前讲解知识点：{{ props.currentWeakPoint }}</p>
            <p v-if="props.currentExplain">AI讲解：{{ props.currentExplain }}</p>
            <p v-if="props.currentTest?.question">随堂检验题：{{ props.currentTest.question }}</p>
            <p v-if="props.testResult?.msg">答题反馈：{{ props.testResult.msg }} {{ props.testResult.analysis || '' }}</p>
          </div>
        </el-tab-pane>

        <el-tab-pane label="📊 学习趋势分析" name="trend">
          <div class="trend-grid">
            <article class="trend-card">
              <h5>近7天知识点掌握度趋势</h5>
              <div ref="masteryTrendRef" class="chart trend-chart"></div>
            </article>
            <article class="trend-card">
              <h5>近7天习题正确率趋势</h5>
              <div ref="accuracyTrendRef" class="chart trend-chart"></div>
            </article>
          </div>
          <article class="trend-summary">
            <h5>AI趋势总结</h5>
            <p>{{ trendSummary }}</p>
          </article>
        </el-tab-pane>
      </el-tabs>
    </section>

    <section class="fixed-action-bar">
      <p>{{ actionSuggestion }}</p>
      <div class="fixed-action-buttons">
        <el-button type="primary" size="large" @click="openActionDialog('review')">一键生成复习计划</el-button>
        <el-button size="large" @click="openActionDialog('redo')">错题重做路径</el-button>
        <el-button size="large" @click="openActionDialog('special')">专项学习方案</el-button>
      </div>
    </section>

    <el-drawer v-model="moreDataDrawerVisible" title="更多学习明细数据" direction="rtl" size="44%">
      <el-tabs v-model="moreDataTab" class="more-data-tabs">
        <el-tab-pane label="错题分析" name="mistake">
          <div class="drawer-grid">
            <article class="drawer-metric-card">
              <span>错题总量</span>
              <strong>{{ metrics.retakeCount }}</strong>
            </article>
            <article class="drawer-metric-card">
              <span>平均正确率</span>
              <strong>{{ metrics.correctRate }}%</strong>
            </article>
            <article class="drawer-metric-card">
              <span>已完成重做</span>
              <strong>{{ Math.max(1, metrics.retakeCount - 2) }}</strong>
            </article>
          </div>
          <div class="drawer-list">
            <article v-for="item in wrongQuestionList" :key="item.id" class="drawer-list-item">
              <h6>{{ item.stem }}</h6>
              <p>错因：{{ item.reason }}</p>
              <p>建议：{{ item.answer }}</p>
            </article>
          </div>
        </el-tab-pane>

        <el-tab-pane label="学习行为" name="behavior">
          <div class="behavior-list">
            <article v-for="row in behaviorRows" :key="row.label" class="behavior-row">
              <span>{{ row.label }}</span>
              <el-progress :percentage="row.percent" :show-text="false" :stroke-width="10" />
              <strong>{{ row.percent }}%</strong>
            </article>
          </div>
          <p class="drawer-note">计算规则：各行为占比 = 对应行为时长 / 总学习时长，时间窗口采用 {{ timeRangeLabel }}。</p>
        </el-tab-pane>

        <el-tab-pane label="问答详情" name="qa">
          <div class="drawer-list">
            <article v-for="qa in qaHistory" :key="qa.id" class="drawer-list-item">
              <h6>Q：{{ qa.question }}</h6>
              <p>A：{{ qa.answer }}</p>
              <small>{{ qa.time }}</small>
            </article>
          </div>
        </el-tab-pane>

        <el-tab-pane label="诊断报告" name="report">
          <article class="report-card">
            <h5>学情诊断摘要</h5>
            <p>本阶段综合学习健康度为 {{ healthScore }} 分，较上周{{ healthDelta >= 0 ? '提升' : '下降' }} {{ Math.abs(healthDelta) }} 分。重点问题集中在 {{ weakPointCards[0]?.name || '核心薄弱点' }} 与 {{ weakPointCards[1]?.name || '配套知识点' }}。</p>
            <ul>
              <li v-for="item in reportHighlights" :key="item">{{ item }}</li>
            </ul>
          </article>
        </el-tab-pane>
      </el-tabs>
    </el-drawer>

    <el-dialog v-model="mistakeDialogVisible" title="错题待重做详情" width="640px">
      <div class="dialog-list">
        <article v-for="item in wrongQuestionList" :key="`dialog-${item.id}`" class="dialog-item">
          <h6>{{ item.stem }}</h6>
          <p>知识点：{{ item.point }}</p>
          <p>错因：{{ item.reason }}</p>
        </article>
      </div>
    </el-dialog>

    <el-dialog v-model="qaDialogVisible" title="历史问答记录" width="640px">
      <div class="dialog-list">
        <article v-for="qa in qaHistory" :key="`qa-${qa.id}`" class="dialog-item">
          <h6>Q：{{ qa.question }}</h6>
          <p>A：{{ qa.answer }}</p>
          <small>{{ qa.time }}</small>
        </article>
      </div>
    </el-dialog>

    <el-dialog v-model="actionDialogVisible" :title="actionDialogTitle" width="560px">
      <div class="dialog-list">
        <p v-for="(line, index) in actionDialogContent" :key="`${actionDialogTitle}-${index}`" class="dialog-item">
          {{ line }}
        </p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
/* eslint-disable no-undef */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'

const props = defineProps({
  learningStats: {
    type: Object,
    default: () => ({})
  },
  weakPointTags: {
    type: Array,
    default: () => []
  },
  studentId: {
    type: String,
    default: ''
  },
  courseId: {
    type: String,
    default: ''
  },
  currentExplain: {
    type: String,
    default: ''
  },
  currentWeakPoint: {
    type: String,
    default: ''
  },
  currentTest: {
    type: Object,
    default: () => null
  },
  testResult: {
    type: Object,
    default: () => null
  }
})

const emit = defineEmits(['start-weak-point', 'generate-test', 'check-answer', 'collect-weak-point'])

const selectedCourse = ref('current')
const selectedTimeRange = ref('week')
const diagnosisTab = ref('weakness')
const moreDataTab = ref('mistake')
const dataUpdatedAt = ref(new Date().toLocaleString('zh-CN'))

const moreDataDrawerVisible = ref(false)
const mistakeDialogVisible = ref(false)
const qaDialogVisible = ref(false)
const actionDialogVisible = ref(false)
const actionDialogTitle = ref('')
const actionDialogContent = ref([])

const diagnosisSectionRef = ref(null)
const healthRadarRef = ref(null)
const masteryTrendRef = ref(null)
const accuracyTrendRef = ref(null)

const clamp = (value, min, max) => {
  const n = Number(value)
  if (Number.isNaN(n)) return min
  return Math.min(max, Math.max(min, n))
}

const chapterPool = ['第1章 应力分析', '第2章 应变理论', '第3章 材料性质', '第4章 组合应用']
const reasonPool = ['习题正确率偏低', '概念区分不清晰', '课堂追问频率偏高', '错题重做间隔过长']
const advicePool = ['先听AI概念讲解再做3题巩固', '优先完成错题重做并复盘解题步骤', '结合课堂笔记回顾关键公式']

const metrics = computed(() => {
  const source = props.learningStats || {}
  const masteryRate = clamp(source.masteryRate || 69, 40, 96)
  const focusScore = clamp(source.focusScore || 85, 45, 98)
  const totalQuestions = Math.max(6, Number(source.totalQuestions || 24))
  const weakPointCount = Math.max(1, Number(source.weakPointCount || props.weakPointTags.length || 3))
  const correctRate = clamp(Math.round(masteryRate * 0.78 + 18), 52, 97)
  const qaCount = Math.max(4, Math.round(totalQuestions * 0.4))
  const qaResolveRate = clamp(Math.round(84 + (focusScore - 70) * 0.35), 70, 98)
  const effectiveHours = Number((focusScore * 0.076).toFixed(1))
  const weeklyHours = 7.6
  const retakeCount = Math.max(2, Math.round(weakPointCount * 3))
  return {
    masteryRate,
    focusScore,
    totalQuestions,
    weakPointCount,
    correctRate,
    qaCount,
    qaResolveRate,
    effectiveHours,
    weeklyHours,
    retakeCount
  }
})

const timeRangeLabel = computed(() => {
  const map = {
    week: '本周',
    month: '本月',
    term: '本学期'
  }
  return map[selectedTimeRange.value] || '本周'
})

const weakPointCards = computed(() => {
  const fromApi = (props.weakPointTags || [])
    .filter(item => item && item.name)
    .slice(0, 6)
    .map((item, index) => ({
      id: item.id || `weak-${index + 1}`,
      name: item.name
    }))

  const fallbackNames = ['主应力概念', '应变张量', '弹性模量', '切应力方向判定']
  const names = fromApi.length ? fromApi : fallbackNames.map((name, index) => ({ id: `mock-${index + 1}`, name }))
  const masteryBaseline = clamp(metrics.value.masteryRate - 12, 35, 80)

  return names.map((item, index) => ({
    id: item.id,
    name: item.name,
    chapter: chapterPool[index % chapterPool.length],
    mastery: clamp(Math.round(masteryBaseline - index * 5 + (index % 2 === 0 ? 1 : -2)), 32, 82),
    reason: reasonPool[index % reasonPool.length],
    advice: advicePool[index % advicePool.length],
    priority: index + 1
  }))
})

const weakDeltaLabel = computed(() => {
  const delta = Math.max(1, weakPointCards.value.length + 2 - weakPointCards.value.length)
  return `减少${delta}个`
})

const radarIndicators = [
  { name: '知识点掌握度', max: 100, rule: '掌握节点数 / 总节点数', source: '课堂学习+笔记复盘' },
  { name: '习题正确率', max: 100, rule: '正确题数 / 总作答题数', source: '随堂练习记录' },
  { name: '学习专注度', max: 100, rule: '有效时长 / 学习总时长', source: '学习行为日志' },
  { name: '互动参与度', max: 100, rule: '有效提问解决率', source: 'AI问答互动' },
  { name: '学习持续性', max: 100, rule: '连续学习天数权重得分', source: '学习轨迹统计' }
]

const radarCurrentValues = computed(() => {
  const consistency = clamp(Math.round((metrics.value.effectiveHours / metrics.value.weeklyHours) * 100), 45, 98)
  return [
    metrics.value.masteryRate,
    metrics.value.correctRate,
    metrics.value.focusScore,
    clamp(metrics.value.qaResolveRate - 4, 50, 98),
    consistency
  ]
})

const radarLastWeekValues = computed(() => {
  const offsets = [5, 4, 3, 4, 5]
  return radarCurrentValues.value.map((value, index) => clamp(value - offsets[index], 28, 96))
})

const healthScore = computed(() => {
  const sum = radarCurrentValues.value.reduce((acc, item) => acc + item, 0)
  return Math.round(sum / radarCurrentValues.value.length)
})

const lastWeekHealthScore = computed(() => {
  const sum = radarLastWeekValues.value.reduce((acc, item) => acc + item, 0)
  return Math.round(sum / radarLastWeekValues.value.length)
})

const healthDelta = computed(() => healthScore.value - lastWeekHealthScore.value)

const trendLabels = computed(() => {
  if (selectedTimeRange.value === 'month') return ['第1周', '第2周', '第3周', '第4周', '第5周', '第6周', '第7周']
  if (selectedTimeRange.value === 'term') return ['阶段1', '阶段2', '阶段3', '阶段4', '阶段5', '阶段6', '阶段7']
  return ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
})

const masteryTrendValues = computed(() => {
  const base = clamp(metrics.value.masteryRate - 6, 36, 92)
  const offsets = [-3, -2, -1, 1, 1, 3, 4]
  return offsets.map((offset, index) => clamp(base + offset + Math.floor(index / 2), 30, 98))
})

const accuracyTrendValues = computed(() => {
  const offsets = [-2, -1, 0, 1, 0, 2, 3]
  return masteryTrendValues.value.map((value, index) => clamp(value - 5 + offsets[index], 25, 97))
})

const trendSummary = computed(() => {
  const masteryStart = masteryTrendValues.value[0]
  const masteryEnd = masteryTrendValues.value[masteryTrendValues.value.length - 1]
  const accuracyStart = accuracyTrendValues.value[0]
  const accuracyEnd = accuracyTrendValues.value[accuracyTrendValues.value.length - 1]
  return `掌握度由 ${masteryStart}% 提升至 ${masteryEnd}%，习题正确率由 ${accuracyStart}% 提升至 ${accuracyEnd}%。近期在 ${weakPointCards.value[0]?.name || '核心薄弱点'} 已出现回升趋势，建议继续保持“讲解+练习+复盘”的学习节奏。`
})

const wrongQuestionList = computed(() => {
  return weakPointCards.value.slice(0, 5).map((item, index) => ({
    id: `wrong-${index + 1}`,
    point: item.name,
    stem: `【${item.name}】应用题第${index + 1}题`,
    reason: item.reason,
    answer: '先复述概念，再写完整求解步骤，并核对单位与方向。'
  }))
})

const behaviorRows = computed(() => {
  const focusBonus = Math.round((metrics.value.focusScore - 80) / 6)
  const video = clamp(38 + focusBonus, 30, 48)
  const practice = clamp(31 - Math.round(focusBonus / 2), 24, 36)
  const qa = 18
  const notes = 100 - video - practice - qa
  return [
    { label: '视频学习', percent: video },
    { label: '习题练习', percent: practice },
    { label: '问答互动', percent: qa },
    { label: '整理笔记', percent: notes }
  ]
})

const qaHistory = computed(() => {
  const first = weakPointCards.value[0]?.name || '主应力概念'
  const second = weakPointCards.value[1]?.name || '应变张量'
  return [
    { id: 1, question: `${first}和切应力的判定规则是什么？`, answer: '先确认截面法向，再判断分力方向。', time: '今天 14:30' },
    { id: 2, question: `${second}题为什么总在第二步出错？`, answer: '通常是张量分量展开顺序不一致导致。', time: '今天 10:12' },
    { id: 3, question: '弹性模量的适用前提是什么？', answer: '在线弹性范围内近似为常数。', time: '昨天 20:45' },
    { id: 4, question: '错题重做时先看答案还是先复做？', answer: '建议先复做，再对照答案定位误区。', time: '昨天 18:20' }
  ]
})

const reportHighlights = computed(() => [
  `薄弱知识点数量：${weakPointCards.value.length} 个，重点为 ${weakPointCards.value[0]?.name || '核心节点'}`,
  `习题正确率：${metrics.value.correctRate}% ，建议本周追加 ${Math.max(4, weakPointCards.value.length * 2)} 题专项练习`,
  `问答解决率：${metrics.value.qaResolveRate}% ，建议对高频问题建立个人错因模板`
])

const topQuestionTopics = computed(() => {
  return weakPointCards.value.slice(0, 2).map(item => item.name).join('、')
})

const actionSuggestion = computed(() => {
  const first = weakPointCards.value[0]?.name || '主应力概念'
  const second = weakPointCards.value[1]?.name || '应变张量'
  return `基于你的学情，建议优先补强「${first}」「${second}」，并在今日完成错题重做闭环。`
})

let radarChartInstance = null
let masteryTrendChartInstance = null
let accuracyTrendChartInstance = null

const renderRadarChart = () => {
  if (!healthRadarRef.value) return
  if (!radarChartInstance) {
    radarChartInstance = echarts.init(healthRadarRef.value)
  }

  radarChartInstance.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(15, 23, 42, 0.92)',
      borderColor: '#3f8f62',
      textStyle: { color: '#f8fbff', fontSize: 12 },
      formatter: params => {
        const values = params.value || []
        const rows = radarIndicators.map((indicator, index) => {
          return `${indicator.name}: ${values[index]}分<br/>计算规则：${indicator.rule}<br/>数据来源：${indicator.source}`
        })
        return rows.join('<br/><br/>')
      }
    },
    legend: {
      top: 2,
      right: 8,
      icon: 'roundRect',
      itemWidth: 14,
      textStyle: { color: '#4f6f60', fontSize: 11 },
      data: ['本周', '上周']
    },
    radar: {
      radius: '67%',
      center: ['50%', '56%'],
      indicator: radarIndicators,
      splitNumber: 4,
      axisName: { color: '#4f6f60', fontSize: 12 },
      splitLine: { lineStyle: { color: '#d5e7dc' } },
      splitArea: { areaStyle: { color: ['#f8fcf9', '#eef7f0'] } }
    },
    series: [
      {
        type: 'radar',
        symbol: 'circle',
        symbolSize: 6,
        data: [
          {
            value: radarCurrentValues.value,
            name: '本周',
            lineStyle: { color: '#3f8f62', width: 2 },
            itemStyle: { color: '#3f8f62' },
            areaStyle: { color: 'rgba(63, 143, 98, 0.32)' }
          },
          {
            value: radarLastWeekValues.value,
            name: '上周',
            lineStyle: { color: '#95afa0', width: 2, type: 'dashed' },
            itemStyle: { color: '#95afa0' },
            areaStyle: { color: 'rgba(149, 175, 160, 0.1)' }
          }
        ]
      }
    ]
  }, true)
}

const renderMasteryTrendChart = () => {
  if (!masteryTrendRef.value) return
  if (!masteryTrendChartInstance) {
    masteryTrendChartInstance = echarts.init(masteryTrendRef.value)
  }
  masteryTrendChartInstance.setOption({
    grid: { left: 36, right: 18, top: 24, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const target = params[0]
        return `${target.axisValue}<br/>掌握度：${target.data}%<br/>计算规则：已掌握节点数 / 总节点数`
      }
    },
    xAxis: {
      type: 'category',
      data: trendLabels.value,
      axisLine: { lineStyle: { color: '#cde2d6' } },
      axisLabel: { color: '#587367' }
    },
    yAxis: {
      type: 'value',
      min: 20,
      max: 100,
      axisLabel: { color: '#587367', formatter: '{value}%' },
      splitLine: { lineStyle: { color: '#e2efe6' } }
    },
    series: [
      {
        type: 'line',
        smooth: true,
        data: masteryTrendValues.value,
        symbol: 'circle',
        symbolSize: 8,
        lineStyle: { color: '#3f8f62', width: 3 },
        itemStyle: { color: '#3f8f62' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(63, 143, 98, 0.34)' },
            { offset: 1, color: 'rgba(63, 143, 98, 0.04)' }
          ])
        }
      }
    ]
  }, true)
}

const renderAccuracyTrendChart = () => {
  if (!accuracyTrendRef.value) return
  if (!accuracyTrendChartInstance) {
    accuracyTrendChartInstance = echarts.init(accuracyTrendRef.value)
  }
  accuracyTrendChartInstance.setOption({
    grid: { left: 36, right: 18, top: 24, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      formatter: params => {
        const target = params[0]
        return `${target.axisValue}<br/>正确率：${target.data}%<br/>计算规则：正确题数 / 作答总题数`
      }
    },
    xAxis: {
      type: 'category',
      data: trendLabels.value,
      axisLine: { lineStyle: { color: '#cde2d6' } },
      axisLabel: { color: '#587367' }
    },
    yAxis: {
      type: 'value',
      min: 20,
      max: 100,
      axisLabel: { color: '#587367', formatter: '{value}%' },
      splitLine: { lineStyle: { color: '#e2efe6' } }
    },
    series: [
      {
        type: 'bar',
        barWidth: 24,
        data: accuracyTrendValues.value,
        itemStyle: {
          borderRadius: [8, 8, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#77c59a' },
            { offset: 1, color: '#3f8f62' }
          ])
        }
      }
    ]
  }, true)
}

const renderAllCharts = async () => {
  await nextTick()
  renderRadarChart()
  if (diagnosisTab.value === 'trend') {
    renderMasteryTrendChart()
    renderAccuracyTrendChart()
  }
}

const resizeCharts = () => {
  radarChartInstance?.resize()
  masteryTrendChartInstance?.resize()
  accuracyTrendChartInstance?.resize()
}

const disposeCharts = () => {
  radarChartInstance?.dispose()
  masteryTrendChartInstance?.dispose()
  accuracyTrendChartInstance?.dispose()
  radarChartInstance = null
  masteryTrendChartInstance = null
  accuracyTrendChartInstance = null
}

const refreshData = async () => {
  dataUpdatedAt.value = new Date().toLocaleString('zh-CN')
  await renderAllCharts()
  ElMessage.success('学习分析数据已刷新')
}

const exportReport = () => {
  openActionDialog('report')
}

const jumpToWeaknessArea = () => {
  diagnosisTab.value = 'weakness'
  nextTick(() => {
    diagnosisSectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

const openMoreData = () => {
  moreDataDrawerVisible.value = true
}

const openMistakeDialog = () => {
  mistakeDialogVisible.value = true
}

const openQaDialog = () => {
  qaDialogVisible.value = true
}

const askAiExplain = item => {
  emit('start-weak-point', { id: item.id, name: item.name })
  ElMessage.success(`已请求 AI 讲解：${item.name}`)
}

const collectWeakPoint = item => {
  emit('collect-weak-point', item)
}

const openActionDialog = (type, payload = null) => {
  const name = payload?.name || '当前薄弱点'
  const actions = {
    review: {
      title: '一键复习计划',
      lines: [
        `优先复习：${weakPointCards.value[0]?.name || name}、${weakPointCards.value[1]?.name || '配套知识点'}`,
        `计划结构：讲解 10 分钟 + 练习 ${Math.max(4, weakPointCards.value.length * 2)} 题 + 复盘 8 分钟`,
        '已同步到个人学习待办清单'
      ]
    },
    redo: {
      title: '错题重做路径',
      lines: [
        '第一步：按知识点归类错题，优先处理高频错因',
        '第二步：重做后立即对照解析，记录易错模板',
        '第三步：次日进行5题回测确认掌握度'
      ]
    },
    special: {
      title: '专项学习方案',
      lines: [
        `本次专项主题：${weakPointCards.value[0]?.name || name}`,
        '建议路径：AI讲解 -> 随堂例题 -> 变式训练 -> 错因复盘',
        '预估完成时长：35 分钟'
      ]
    },
    practice: {
      title: `练习任务：${name}`,
      lines: [
        '已生成基础题3道、进阶题2道，建议先独立完成再看解析',
        '完成后可在“更多数据 > 错题分析”查看变化趋势'
      ]
    },
    report: {
      title: '导出报告说明',
      lines: [
        `导出范围：${timeRangeLabel.value}学习分析`,
        '内容包含：健康度雷达、薄弱点卡片、趋势图与行动建议',
        '状态：报告模板已生成，可直接分享给教师端'
      ]
    }
  }

  const current = actions[type] || {
    title: '学习提示',
    lines: ['当前操作已完成。']
  }

  actionDialogTitle.value = current.title
  actionDialogContent.value = current.lines
  actionDialogVisible.value = true
}

watch(
  [selectedCourse, selectedTimeRange, metrics, weakPointCards, radarCurrentValues, radarLastWeekValues],
  () => {
    renderAllCharts()
  },
  { deep: true }
)

watch(diagnosisTab, tab => {
  if (tab === 'trend') {
    nextTick(() => {
      renderMasteryTrendChart()
      renderAccuracyTrendChart()
    })
  }
})

onMounted(() => {
  renderAllCharts()
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  disposeCharts()
})
</script>

<style scoped>
.study-analytics-page {
  --primary: #3f8f62;
  --primary-soft: #eaf7ef;
  --ink-900: #214a37;
  --ink-700: #4f6f60;
  --ink-500: #739382;
  --line: #d4e7dc;

  height: 100%;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  border-radius: 20px;
  border: 1px solid var(--line);
  background:
    radial-gradient(circle at 10% 12%, rgba(63, 143, 98, 0.13), transparent 42%),
    radial-gradient(circle at 90% 2%, rgba(121, 188, 145, 0.18), transparent 36%),
    linear-gradient(180deg, #f8fcf9 0%, #f2f9f4 38%, #f7fcf8 100%);
}

.analysis-header {
  position: relative;
  z-index: 1;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: rgba(248, 253, 249, 0.96);
  backdrop-filter: blur(6px);
  padding: 14px;
  display: grid;
  gap: 10px;
}

.analysis-header-main h3 {
  margin: 2px 0 8px;
  color: var(--ink-900);
  font-size: 24px;
}

.header-kicker {
  margin: 0;
  font-size: 12px;
  color: #4f8a67;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
}

.flow-strip {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 10px;
  background: var(--primary-soft);
  border: 1px solid #c8e1d1;
  color: #3f6a55;
  font-size: 12px;
}

.flow-label {
  font-weight: 700;
  color: #2d5c45;
}

.flow-node {
  background: #fff;
  border: 1px solid #c3ddcd;
  border-radius: 999px;
  padding: 3px 10px;
}

.flow-arrow {
  color: #5f8a74;
  font-weight: 700;
}

.analysis-header-controls {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.data-source-tip {
  margin: 0;
  color: var(--ink-700);
  font-size: 12px;
}

.health-overview {
  display: grid;
  grid-template-columns: 1.65fr 1fr;
  gap: 14px;
}

.health-radar-panel {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fff;
  padding: 14px;
  display: grid;
  gap: 10px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
}

.panel-head h4 {
  margin: 0;
  color: var(--ink-900);
  font-size: 18px;
}

.panel-head p {
  margin: 4px 0 0;
  color: var(--ink-500);
  font-size: 12px;
}

.health-delta {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: #eafaf3;
  color: #1f8f5f;
  border: 1px solid #bde8cf;
  font-size: 12px;
  font-weight: 700;
  padding: 6px 10px;
}

.health-delta.down {
  color: #b42318;
  background: #fff2f0;
  border-color: #ffd0c7;
}

.radar-body {
  position: relative;
}

.chart {
  width: 100%;
}

.radar-chart {
  height: 360px;
}

.score-core {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -48%);
  width: 136px;
  height: 136px;
  border-radius: 50%;
  border: 1px solid #c5decd;
  background: radial-gradient(circle at 30% 26%, #ffffff 0%, #eaf6ef 72%);
  display: grid;
  place-content: center;
  text-align: center;
}

.score-core strong {
  color: var(--primary);
  font-size: 44px;
  line-height: 1;
}

.score-core small {
  color: var(--ink-700);
  font-size: 12px;
}

.issue-panel {
  display: grid;
  gap: 10px;
}

.issue-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fff;
  padding: 12px;
  text-align: left;
  display: grid;
  gap: 8px;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.issue-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 12px 24px rgba(63, 143, 98, 0.18);
}

.issue-card :deep(.el-progress-bar__outer) {
  background: #ecf5ef;
}

.issue-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  color: var(--ink-900);
  font-size: 13px;
}

.issue-top strong {
  font-size: 15px;
}

.issue-card p {
  margin: 0;
  font-size: 12px;
  color: var(--ink-700);
}

.issue-card small {
  color: var(--ink-500);
  font-size: 11px;
}

.issue-card.weak {
  background: linear-gradient(130deg, #f3fbf5 0%, #fff 86%);
}

.issue-card.mistake {
  background: linear-gradient(130deg, #f5fbf7 0%, #fff 86%);
}

.issue-card.focus {
  background: linear-gradient(130deg, #f0faf4 0%, #fff 86%);
}

.issue-card.qa {
  background: linear-gradient(130deg, #f2f9f4 0%, #fff 86%);
}

.diagnosis-section {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fff;
  padding: 14px;
  display: grid;
  gap: 12px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.section-head h4 {
  margin: 0;
  color: var(--ink-900);
}

.section-head p {
  margin: 3px 0 0;
  color: var(--ink-500);
  font-size: 12px;
}

.diagnosis-tabs :deep(.el-tabs__item) {
  font-weight: 600;
}

.diagnosis-tabs :deep(.el-tabs__active-bar) {
  background: var(--primary);
}

.weak-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.weak-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  display: grid;
  gap: 8px;
  background: linear-gradient(148deg, #ffffff 0%, #f3faf5 100%);
}

.weak-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.weak-head h5 {
  margin: 0;
  color: var(--ink-900);
  font-size: 15px;
}

.weak-head p {
  margin: 4px 0 0;
  color: var(--ink-500);
  font-size: 12px;
}

.weak-score {
  align-self: center;
  background: #eaf6ef;
  border: 1px solid #c7ddce;
  color: #2f6d4b;
  border-radius: 999px;
  font-size: 12px;
  padding: 4px 9px;
  font-weight: 700;
}

.weak-reason,
.weak-advice {
  margin: 0;
  font-size: 12px;
  color: var(--ink-700);
  line-height: 1.55;
}

.weak-actions {
  display: flex;
  gap: 8px;
}

.backend-feedback-panel {
  margin-top: 12px;
  border: 1px dashed #c3decd;
  border-radius: 12px;
  background: #f3faf5;
  padding: 12px;
  display: grid;
  gap: 6px;
}

.backend-feedback-panel h5 {
  margin: 0;
  color: #2f6d4b;
}

.backend-feedback-panel p {
  margin: 0;
  color: var(--ink-700);
  font-size: 13px;
  line-height: 1.5;
}

.trend-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.trend-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #fdfefe;
  padding: 10px;
}

.trend-card h5,
.trend-summary h5 {
  margin: 0;
  color: var(--ink-900);
}

.trend-chart {
  height: 260px;
}

.trend-summary {
  margin-top: 10px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f3faf5;
  padding: 12px;
}

.trend-summary p {
  margin: 8px 0 0;
  color: var(--ink-700);
  line-height: 1.6;
  font-size: 13px;
}

.fixed-action-bar {
  position: relative;
  z-index: 1;
  border: 1px solid #bfdccc;
  border-radius: 14px;
  background: rgba(236, 248, 240, 0.95);
  backdrop-filter: blur(4px);
  padding: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.fixed-action-bar p {
  margin: 0;
  color: #2b6147;
  font-size: 13px;
  line-height: 1.5;
}

.fixed-action-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.fixed-action-buttons :deep(.el-button) {
  border-radius: 10px;
}

.more-data-tabs :deep(.el-tabs__content) {
  max-height: 65vh;
  overflow: auto;
  padding-right: 4px;
}

.drawer-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.drawer-metric-card {
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #f4faf6;
  padding: 10px;
  display: grid;
  gap: 4px;
}

.drawer-metric-card span {
  color: var(--ink-500);
  font-size: 12px;
}

.drawer-metric-card strong {
  color: var(--ink-900);
  font-size: 22px;
}

.drawer-list {
  display: grid;
  gap: 8px;
}

.drawer-list-item {
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
  padding: 10px;
  display: grid;
  gap: 5px;
}

.drawer-list-item h6 {
  margin: 0;
  color: var(--ink-900);
  font-size: 13px;
}

.drawer-list-item p {
  margin: 0;
  color: var(--ink-700);
  line-height: 1.45;
  font-size: 12px;
}

.drawer-list-item small {
  color: var(--ink-500);
}

.behavior-list {
  display: grid;
  gap: 8px;
}

.behavior-row {
  display: grid;
  grid-template-columns: 90px 1fr 48px;
  align-items: center;
  gap: 8px;
}

.behavior-row span,
.behavior-row strong {
  color: var(--ink-700);
  font-size: 13px;
}

.drawer-note {
  margin: 12px 0 0;
  color: var(--ink-500);
  font-size: 12px;
}

.report-card {
  border: 1px solid var(--line);
  border-radius: 12px;
  background: #f3faf5;
  padding: 12px;
}

.report-card h5 {
  margin: 0;
  color: var(--ink-900);
}

.report-card p {
  margin: 8px 0;
  color: var(--ink-700);
  line-height: 1.6;
  font-size: 13px;
}

.report-card ul {
  margin: 0;
  padding-left: 18px;
  color: var(--ink-700);
  line-height: 1.6;
  font-size: 13px;
}

.dialog-list {
  display: grid;
  gap: 8px;
}

.dialog-item {
  margin: 0;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #f4faf6;
  padding: 10px;
  color: var(--ink-700);
  font-size: 13px;
  line-height: 1.5;
}

.dialog-item h6 {
  margin: 0 0 4px;
  color: var(--ink-900);
}

.dialog-item p,
.dialog-item small {
  margin: 0;
}

@media (max-width: 1220px) {
  .health-overview {
    grid-template-columns: 1fr;
  }

  .weak-grid,
  .trend-grid {
    grid-template-columns: 1fr;
  }

  .fixed-action-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .fixed-action-buttons {
    justify-content: flex-start;
  }
}

@media (max-width: 820px) {
  .analysis-header-controls {
    justify-content: flex-start;
  }

  .flow-strip {
    width: 100%;
  }

  .drawer-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .study-analytics-page {
    padding: 10px;
  }

  .analysis-header-main h3 {
    font-size: 20px;
  }

  .radar-chart {
    height: 320px;
  }

  .score-core {
    width: 118px;
    height: 118px;
  }

  .score-core strong {
    font-size: 36px;
  }

  .behavior-row {
    grid-template-columns: 70px 1fr 40px;
  }
}
</style>