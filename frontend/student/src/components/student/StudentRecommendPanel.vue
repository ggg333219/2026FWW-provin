<template>
  <section class="recommend-panel">
    <header class="recommend-header">
      <div>
        <div class="recommend-kicker">学习推荐</div>
        <h3>遗传算法课件配套推荐中心</h3>
        <p>{{ recommendModeDesc }}</p>
      </div>
      <el-button type="primary" plain @click="openPlanDialog">查看今日学习单</el-button>
    </header>

    <div class="status-pills">
      <span class="status-pill" :class="{ live: resourceMode === 'live', fallback: resourceMode !== 'live' }">{{ recommendModeLabel }}</span>
      <span class="status-pill neutral">{{ recommendRefreshLabel }}</span>
    </div>

    <div class="demo-director-strip">
      <div>
        <strong>学习闭环路线：推荐资源 → 提交练习 → 个人中心复盘</strong>
        <p>先加入学习单，再点击“一键学习闭环”，可直接推进到随堂练习页面。</p>
      </div>
      <div class="director-actions">
        <el-button size="small" plain @click="emit('navigate-section', 'classroom')">回课堂学习</el-button>
        <el-button size="small" type="primary" plain @click="emit('navigate-section', 'practice')">去随堂练习</el-button>
      </div>
    </div>

    <div class="recommend-body">
      <aside class="recommend-left-pane">
        <div class="recommend-toolbar">
          <el-input
            v-model.trim="keyword"
            clearable
            placeholder="输入关键词，如：遗传算法 选择复制"
            @keyup.enter="searchResources"
          />
          <el-button type="primary" :loading="resourceLoading" @click="searchResources">
            {{ resourceLoading ? '推荐中' : '筛选资源' }}
          </el-button>
        </div>

        <div class="hint-row" v-if="defaultKeyword">
          建议关键词：{{ defaultKeyword }}
          <el-button text size="small" @click="useDefaultKeyword">一键应用</el-button>
        </div>

        <div class="filter-grid">
          <el-select v-model="selectedSource" size="small">
            <el-option label="全部来源" value="all" />
            <el-option label="B站" value="Bilibili" />
            <el-option label="51教习" value="51教习" />
            <el-option label="慕课" value="MOOC" />
          </el-select>
          <el-select v-model="selectedDifficulty" size="small">
            <el-option label="全部难度" value="all" />
            <el-option label="入门" value="入门" />
            <el-option label="进阶" value="进阶" />
            <el-option label="强化" value="强化" />
          </el-select>
        </div>

        <div class="quick-actions">
          <el-button size="small" plain @click="openFlowDialog('导学')">导学流程</el-button>
          <el-button size="small" plain @click="openFlowDialog('练习')">练习流程</el-button>
          <el-button size="small" plain @click="openFlowDialog('冲刺')">冲刺流程</el-button>
          <el-button size="small" type="primary" plain :loading="resourceLoading" @click="refreshRecommendations">智能刷新</el-button>
        </div>

        <div class="queue-card">
          <h4>今日学习单</h4>
          <div v-if="studyQueue.length" class="queue-list">
            <article v-for="item in studyQueue" :key="item.id" class="queue-item">
              <strong>{{ item.title }}</strong>
              <span>{{ item.duration }} · {{ item.source }}</span>
            </article>
          </div>
          <div v-else class="queue-empty">还未加入资源，点击右侧“加入学习单”即可。</div>
        </div>
      </aside>

      <section class="recommend-right-pane">
        <div class="recommend-count">{{ recommendCountText }}</div>
        <div v-if="isFilterFallbackActive" class="recommend-fallback-tip">
          {{ filterFallbackTipText }}
          <el-button text size="small" @click="resetFilters">恢复默认筛选</el-button>
        </div>

        <div v-if="resourceLoading" class="recommend-skeleton-grid" aria-live="polite">
          <article v-for="index in 4" :key="`skeleton-${index}`" class="recommend-skeleton-item">
            <div class="skeleton-line w-70"></div>
            <div class="skeleton-line w-35"></div>
            <div class="skeleton-line w-100"></div>
            <div class="skeleton-line w-85"></div>
            <div class="skeleton-row">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </article>
        </div>

        <div v-else-if="displayResources.length" class="recommend-grid">
          <article class="recommend-item" :class="{ 'is-active': selectedResourceId === item.id }" v-for="item in displayResources" :key="item.id">
            <header>
              <h4>{{ item.title }}</h4>
              <span class="source-tag">{{ item.source }}</span>
            </header>
            <p class="reason">{{ item.reason }}</p>
            <div class="meta-row">
              <span>{{ item.duration }}</span>
              <span>{{ item.difficulty }}</span>
              <span>{{ item.fitNode }}</span>
            </div>
            <div class="actions">
              <el-button size="small" type="primary" @click="openDetail(item)">详情</el-button>
              <el-button size="small" plain @click="enqueueResource(item)">加入学习单</el-button>
              <el-button size="small" plain @click="simulateLearning(item)">快速学习</el-button>
              <el-button size="small" type="success" plain @click="runDemoFlow(item)">一键学习闭环</el-button>
            </div>
          </article>
        </div>
        <div v-else class="recommend-empty">{{ recommendEmptyText }}</div>
      </section>
    </div>

    <el-dialog v-model="detailDialogVisible" title="资源详情" width="560px">
      <div v-if="activeResource" class="detail-dialog">
        <h4>{{ activeResource.title }}</h4>
        <p>{{ activeResource.reason }}</p>
        <ul>
          <li>来源：{{ activeResource.source }}</li>
          <li>时长：{{ activeResource.duration }}</li>
          <li>适配节点：{{ activeResource.fitNode }}</li>
          <li>推荐策略：{{ activeResource.strategy }}</li>
        </ul>
      </div>
    </el-dialog>

    <el-dialog v-model="planDialogVisible" title="今日学习单" width="620px">
      <div class="plan-dialog">
        <article v-for="(item, index) in studyQueue" :key="item.id" class="plan-step">
          <span>{{ index + 1 }}</span>
          <div>
            <strong>{{ item.title }}</strong>
            <p>{{ item.duration }} · {{ item.source }} · {{ item.fitNode }}</p>
          </div>
        </article>
        <div v-if="!studyQueue.length" class="queue-empty">学习单为空，请先加入推荐资源。</div>
      </div>
    </el-dialog>

    <el-dialog v-model="flowDialogVisible" :title="flowDialogTitle" width="560px">
      <div class="flow-dialog">
        <p v-for="(line, index) in flowDialogLines" :key="`${flowDialogTitle}-${index}`">{{ line }}</p>
      </div>
    </el-dialog>
  </section>
</template>

<script setup>
/* eslint-disable no-undef */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { studentV1Api } from '../../services/v1'

const props = defineProps({
  courseName: {
    type: String,
    default: ''
  },
  currentNodeTitle: {
    type: String,
    default: ''
  },
  currentPage: {
    type: Number,
    default: 1
  }
})
const emit = defineEmits(['navigate-section'])

const keyword = ref('')
const selectedSource = ref('all')
const selectedDifficulty = ref('all')
const querySnapshot = ref('')
const resourceLoading = ref(false)
const resourceMode = ref('demo')
const resourceUpdatedAt = ref('')
const selectedResourceId = ref('')
const remoteResources = ref([])
const activeResource = ref(null)
const detailDialogVisible = ref(false)
const planDialogVisible = ref(false)
const flowDialogVisible = ref(false)
const flowDialogTitle = ref('')
const flowDialogLines = ref([])
const studyQueue = ref([])
const isBootstrapped = ref(false)
let activeSearchRequestId = 0

const DIFFICULTY_WEIGHT_MAP = Object.freeze({
  入门: 0.35,
  进阶: 0.65,
  强化: 0.9
})

const mockResources = ref([
  {
    id: 'ga-1',
    title: '遗传算法入门：编码、适应度与种群演化',
    source: 'Bilibili',
    duration: '18分钟',
    difficulty: '入门',
    fitNode: '基础概念',
    strategy: '先建立概念图，再看例题',
    reason: '适合第1页到第3页的术语理解，覆盖“编码-选择-交叉-变异”完整主线。'
  },
  {
    id: 'ga-2',
    title: '轮盘赌选择与锦标赛选择对比实验',
    source: '51教习',
    duration: '25分钟',
    difficulty: '进阶',
    fitNode: '选择复制',
    strategy: '先看对比图，再做参数实验',
    reason: '针对“选择复制”薄弱点，给出两类策略的收敛速度和多样性差异。'
  },
  {
    id: 'ga-3',
    title: '单点交叉、多点交叉与变异率调参实战',
    source: 'MOOC',
    duration: '32分钟',
    difficulty: '强化',
    fitNode: '交叉与变异',
    strategy: '先固定编码长度，再逐步调变异率',
    reason: '用于课堂练习后的强化复盘，能直接映射你当前课件中的应用题。'
  },
  {
    id: 'ga-4',
    title: '遗传算法在路径规划中的可视化讲解',
    source: 'Bilibili',
    duration: '21分钟',
    difficulty: '进阶',
    fitNode: '应用案例',
    strategy: '先看动画，再回到公式推导',
    reason: '可将抽象流程映射到具体问题，减少“会背不会用”的情况。'
  },
  {
    id: 'ga-5',
    title: 'GA 课堂冲刺：高频题型与易错点清单',
    source: '51教习',
    duration: '16分钟',
    difficulty: '强化',
    fitNode: '期末冲刺',
    strategy: '错因分类 + 速记卡片',
    reason: '适合考前 24 小时快速过一遍，重点覆盖概率计算与交叉结果判断。'
  }
])

const formatRefreshTime = (value = new Date()) => {
  const d = value instanceof Date ? value : new Date(value)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

const pickText = (...candidates) => {
  for (const value of candidates) {
    const text = String(value || '').trim()
    if (text) return text
  }
  return ''
}

const normalizeDifficultyLabel = (value) => {
  const text = String(value || '').trim()
  if (['入门', '进阶', '强化'].includes(text)) return text
  const score = Number(value)
  if (Number.isFinite(score)) {
    if (score >= 0.8) return '强化'
    if (score >= 0.55) return '进阶'
    return '入门'
  }
  return '进阶'
}

const normalizeDurationLabel = (value) => {
  const text = String(value || '').trim()
  if (!text) return '20分钟'
  if (/[分时钟钟]/.test(text)) return text
  const minutes = Number(text)
  if (Number.isFinite(minutes) && minutes > 0) {
    return `${Math.round(minutes)}分钟`
  }
  return text
}

const normalizeRecommendItem = (item, index = 0) => {
  const id = pickText(item?.id, item?.resource_id, item?.resourceId, item?.url, `remote-${index + 1}`)
  return {
    id,
    title: pickText(item?.title, item?.name, item?.resource_name, `推荐资源 ${index + 1}`),
    source: pickText(item?.source, item?.platform, item?.provider, '综合来源'),
    duration: normalizeDurationLabel(pickText(item?.duration, item?.length, item?.time_cost, item?.estimate_duration)),
    difficulty: normalizeDifficultyLabel(pickText(item?.difficulty_label, item?.difficulty, item?.level)),
    fitNode: pickText(item?.fit_node, item?.fitNode, item?.node, item?.focus, props.currentNodeTitle, '当前节点'),
    strategy: pickText(item?.strategy, item?.study_strategy, item?.plan, '先理解核心概念，再完成对应练习。'),
    reason: pickText(item?.reason, item?.recommend_reason, item?.summary, '该资源与当前知识点和学习进度匹配度较高。')
  }
}

const activeResources = computed(() => {
  if (remoteResources.value.length > 0) return remoteResources.value
  return mockResources.value
})

const addResourceToQueue = (item) => {
  const exists = studyQueue.value.some((record) => {
    const sameId = String(record.id || '') && String(record.id || '') === String(item.id || '')
    const sameTitleAndSource = record.title === item.title && record.source === item.source
    return sameId || sameTitleAndSource
  })
  if (exists) return false
  studyQueue.value = [...studyQueue.value, item]
  return true
}

const resolveErrorText = (error) => {
  if (!error) return '未知错误'
  if (typeof error === 'string') return error
  if (typeof error?.message === 'string' && error.message.trim()) return error.message.trim()
  try {
    return JSON.stringify(error)
  } catch (_) {
    return String(error)
  }
}

const defaultKeyword = computed(() => {
  const parts = [
    String(props.currentNodeTitle || '').trim(),
    String(props.courseName || '').trim(),
    props.currentPage ? `第${props.currentPage}页` : ''
  ].filter(Boolean)
  return parts.join(' ')
})

const recommendModeLabel = computed(() => (resourceMode.value === 'live' ? '智能推荐在线' : '基础资源模式'))

const recommendModeDesc = computed(() => {
  if (resourceMode.value === 'live') {
    return '已连接推荐接口：可按关键词与难度实时刷新资源结果。'
  }
  return '推荐接口异常时自动回退到基础资源，保证课堂流程不中断。'
})

const recommendRefreshLabel = computed(() => {
  if (!resourceUpdatedAt.value) return '等待首次推荐'
  return `最近刷新：${resourceUpdatedAt.value}`
})

const queryText = computed(() => String(querySnapshot.value || keyword.value || '').trim().toLowerCase())

const filterResources = (resources, { allowSource = true, allowDifficulty = true, allowQuery = true } = {}) => {
  const query = allowQuery ? queryText.value : ''
  return resources.filter((item) => {
    const sourceMatch = !allowSource || selectedSource.value === 'all' || item.source === selectedSource.value
    const diffMatch = !allowDifficulty || selectedDifficulty.value === 'all' || item.difficulty === selectedDifficulty.value
    const queryMatch = !query || [item.title, item.reason, item.fitNode, item.strategy].join(' ').toLowerCase().includes(query)
    return sourceMatch && diffMatch && queryMatch
  })
}

const filteredResources = computed(() => {
  return filterResources(activeResources.value, {
    allowSource: true,
    allowDifficulty: true,
    allowQuery: true
  })
})

const fallbackDisplayState = computed(() => {
  if (!activeResources.value.length) {
    return {
      items: [],
      reason: ''
    }
  }

  if (filteredResources.value.length > 0) {
    return {
      items: filteredResources.value,
      reason: ''
    }
  }

  if (queryText.value) {
    const noQuery = filterResources(activeResources.value, {
      allowSource: true,
      allowDifficulty: true,
      allowQuery: false
    })
    if (noQuery.length > 0) {
      return {
        items: noQuery,
        reason: '关键词暂未命中，已先展示同筛选条件下的推荐资源。'
      }
    }
  }

  if (selectedDifficulty.value !== 'all') {
    const noDifficulty = filterResources(activeResources.value, {
      allowSource: true,
      allowDifficulty: false,
      allowQuery: false
    })
    if (noDifficulty.length > 0) {
      return {
        items: noDifficulty,
        reason: '已放宽难度筛选，优先保证你能看到可用推荐。'
      }
    }
  }

  return {
    items: activeResources.value,
    reason: '当前筛选过严，已展示全部可用推荐。'
  }
})

const displayResources = computed(() => {
  return fallbackDisplayState.value.items
})

const isFilterFallbackActive = computed(() => {
  if (resourceLoading.value) return false
  return Boolean(fallbackDisplayState.value.reason)
})

const filterFallbackTipText = computed(() => {
  return fallbackDisplayState.value.reason || '当前筛选条件未命中，已自动展示可用推荐。'
})

const recommendCountText = computed(() => {
  const modePrefix = resourceMode.value === 'live' ? '实时' : '基础'
  const fallbackSuffix = isFilterFallbackActive.value ? '（已自动放宽筛选）' : ''
  return `${modePrefix}推荐共 ${displayResources.value.length} 条${fallbackSuffix}`
})

const recommendEmptyText = computed(() => {
  if (resourceLoading.value) return '正在加载推荐资源...'
  if (!activeResources.value.length) return '当前暂无可展示推荐，请点击“智能刷新”重试。'
  return '当前筛选条件下暂无资源，建议切换关键词或难度。'
})

const buildRecommendRequestPayload = (targetKeyword) => {
  const sourcePreference = selectedSource.value === 'all' ? [] : [selectedSource.value]
  return {
    keyword: targetKeyword,
    type: '网课',
    difficulty: DIFFICULTY_WEIGHT_MAP[selectedDifficulty.value] || 0.6,
    duration: 30,
    source_preference: sourcePreference,
    subject: String(props.courseName || '遗传算法').trim(),
    stage: String(props.currentPage || 1)
  }
}

const searchResources = async (options = {}) => {
  const forceKeyword = String(options?.forceKeyword || '').trim()
  const silent = Boolean(options?.silent)
  const targetKeyword = forceKeyword || String(keyword.value || '').trim() || defaultKeyword.value
  if (!targetKeyword) {
    if (!silent) {
      ElMessage.warning('请输入关键词后再筛选')
    }
    return
  }

  querySnapshot.value = targetKeyword
  keyword.value = targetKeyword
  resourceLoading.value = true
  const requestId = ++activeSearchRequestId

  try {
    const response = await studentV1Api.recommend.fetchRecommendedResources(
      buildRecommendRequestPayload(targetKeyword)
    )
    if (requestId !== activeSearchRequestId) return
    const list = Array.isArray(response?.list) ? response.list : []
    const normalized = list.map((item, index) => normalizeRecommendItem(item, index)).filter((item) => item.title)
    if (normalized.length > 0) {
      remoteResources.value = normalized
      resourceMode.value = 'live'
      if (!silent) {
        ElMessage.success(`已更新 ${normalized.length} 条智能推荐`) 
      }
    } else {
      remoteResources.value = []
      resourceMode.value = 'demo'
      if (!silent) {
        ElMessage.warning('接口已响应但暂无结果，已切换基础推荐')
      }
    }
  } catch (error) {
    if (requestId !== activeSearchRequestId) return
    remoteResources.value = []
    resourceMode.value = 'demo'
    const errorText = resolveErrorText(error)
    if (!silent) {
      ElMessage.warning(`智能推荐暂不可用（${errorText}），已回退基础资源`)
    }
  } finally {
    if (requestId === activeSearchRequestId) {
      resourceUpdatedAt.value = formatRefreshTime(new Date())
      resourceLoading.value = false
    }
  }
}

const refreshRecommendations = async () => {
  await searchResources({ forceKeyword: querySnapshot.value || keyword.value || defaultKeyword.value })
}

const resetFilters = () => {
  selectedSource.value = 'all'
  selectedDifficulty.value = 'all'
  querySnapshot.value = ''
  keyword.value = ''
}

const useDefaultKeyword = async () => {
  if (!defaultKeyword.value) return
  keyword.value = defaultKeyword.value
  await searchResources({ forceKeyword: defaultKeyword.value })
}

const openDetail = (item) => {
  selectedResourceId.value = String(item?.id || '')
  const keywordText = pickText(item?.title)
  if (!keywordText) {
    ElMessage.warning('当前资源缺少标题，暂时无法跳转搜索')
    return
  }
  const searchUrl = `https://search.bilibili.com/all?keyword=${encodeURIComponent(keywordText)}`
  if (typeof window !== 'undefined') {
    const opened = window.open(searchUrl, '_blank', 'noopener,noreferrer')
    if (!opened) {
      window.location.href = searchUrl
    }
  }
}

const enqueueResource = (item) => {
  selectedResourceId.value = String(item?.id || '')
  const inserted = addResourceToQueue(item)
  if (inserted) {
    ElMessage.success(`已加入学习单：${item.title}`)
  } else {
    ElMessage.info('该资源已在学习单中，可直接进入随堂练习')
  }
  planDialogVisible.value = true
}

const simulateLearning = (item) => {
  selectedResourceId.value = String(item?.id || '')
  flowDialogTitle.value = `学习流程：${item.title}`
  flowDialogLines.value = [
    '1. 进入资源并完成导学预览（约 3 分钟）',
    '2. 结合课件当前页做 2 道自测题（约 6 分钟）',
    '3. AI 助手回顾错因并输出复习提纲（约 4 分钟）',
    '4. 自动写入今日学习单，等待课堂回放联动（已同步）'
  ]
  flowDialogVisible.value = true
}

const runDemoFlow = (item) => {
  selectedResourceId.value = String(item?.id || '')
  const inserted = addResourceToQueue(item)
  if (inserted) {
    ElMessage.success('资源已加入学习单，正在进入随堂练习')
  } else {
    ElMessage.success('学习单已存在该资源，正在进入随堂练习')
  }
  emit('navigate-section', 'practice')
}

const openFlowDialog = (mode) => {
  const map = {
    导学: [
      '导学模式：先理解概念定义，再看流程图。',
      '建议顺序：基础概念 -> 选择复制 -> 交叉变异。'
    ],
    练习: [
      '练习模式：每学完 1 个节点立即做 2 题。',
      '错题自动加入“薄弱强化”队列。'
    ],
    冲刺: [
      '冲刺模式：优先做概率与交叉计算题。',
      '建议在 30 分钟内完成 1 轮专题复习。'
    ]
  }
  flowDialogTitle.value = `${mode}流程说明`
  flowDialogLines.value = map[mode] || ['当前模式暂无说明。']
  flowDialogVisible.value = true
}

const openPlanDialog = () => {
  planDialogVisible.value = true
}

watch(defaultKeyword, (next) => {
  if (!keyword.value && next) {
    keyword.value = next
    querySnapshot.value = next
  }
  if (!isBootstrapped.value && next) {
    isBootstrapped.value = true
    void searchResources({ silent: true, forceKeyword: next })
  }
}, { immediate: true })
</script>

<style scoped>
.recommend-panel {
  height: 100%;
  min-height: 0;
  border: 1px solid #d8e5de;
  border-radius: 18px;
  background:
    radial-gradient(circle at 92% 4%, rgba(91, 165, 131, 0.16) 0%, rgba(91, 165, 131, 0) 42%),
    linear-gradient(180deg, #ffffff 0%, #f6faf8 100%);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: hidden;
}

.status-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.status-pill {
  font-size: 11px;
  line-height: 1;
  border-radius: 999px;
  padding: 6px 10px;
  border: 1px solid transparent;
  font-weight: 600;
}

.status-pill.live {
  background: #eaf7f1;
  border-color: #b8ddcb;
  color: #1e6048;
}

.status-pill.fallback {
  background: #f8f3e5;
  border-color: #e6d8a9;
  color: #715e22;
}

.status-pill.neutral {
  background: #eff3f1;
  border-color: #d4dfd9;
  color: #4a6359;
}

.recommend-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.demo-director-strip {
  border: 1px solid #d6e5dd;
  border-radius: 12px;
  background: linear-gradient(145deg, #f3f9f5 0%, #eaf4ef 100%);
  padding: 10px 12px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.demo-director-strip strong {
  font-size: 13px;
  color: #21483f;
}

.demo-director-strip p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #55756b;
}

.director-actions {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.recommend-kicker {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  color: #6a8278;
}

.recommend-header h3 {
  margin-top: 4px;
  font-size: 18px;
  color: #23463f;
}

.recommend-header p {
  margin-top: 6px;
  font-size: 13px;
  color: #6f867d;
}

.recommend-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 310px minmax(0, 1fr);
  gap: 10px;
  overflow: hidden;
}

.recommend-left-pane,
.recommend-right-pane {
  min-height: 0;
  border: 1px solid #dbe8e1;
  border-radius: 14px;
  background: #fff;
  padding: 10px;
}

.recommend-left-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
}

.recommend-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.hint-row {
  font-size: 12px;
  color: #58736a;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.filter-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.queue-card {
  border: 1px solid #dce9e2;
  border-radius: 12px;
  background: #f8fcf9;
  padding: 10px;
}

.queue-card h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #274d46;
}

.queue-list {
  display: grid;
  gap: 8px;
}

.queue-item {
  border: 1px solid #d6e6de;
  border-radius: 10px;
  background: #fff;
  padding: 8px;
  display: grid;
  gap: 4px;
}

.queue-item strong {
  font-size: 13px;
  color: #24493f;
}

.queue-item span,
.queue-empty {
  font-size: 12px;
  color: #678077;
}

.recommend-right-pane {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}

.recommend-count {
  font-size: 12px;
  color: #58746a;
}

.recommend-fallback-tip {
  border: 1px dashed #c5ddd1;
  border-radius: 10px;
  background: #f6fbf8;
  color: #4f6f63;
  font-size: 12px;
  padding: 8px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.recommend-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  overflow: auto;
  padding-right: 2px;
}

.recommend-skeleton-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  overflow: auto;
  padding-right: 2px;
}

.recommend-skeleton-item {
  border: 1px solid #d9e6df;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f7fbf9 100%);
  padding: 10px;
  display: grid;
  gap: 8px;
}

.skeleton-line {
  height: 10px;
  border-radius: 999px;
  background: linear-gradient(90deg, #e8f0eb 25%, #dce9e2 40%, #e8f0eb 65%);
  background-size: 240% 100%;
  animation: skeleton-shimmer 1.2s linear infinite;
}

.skeleton-line.w-35 { width: 35%; }
.skeleton-line.w-70 { width: 70%; }
.skeleton-line.w-85 { width: 85%; }
.skeleton-line.w-100 { width: 100%; }

.skeleton-row {
  display: flex;
  gap: 6px;
}

.skeleton-row span {
  width: 56px;
  height: 18px;
  border-radius: 999px;
  background: #ebf2ee;
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -40% 0; }
}

.recommend-item {
  border: 1px solid #d7e5dd;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fcfa 100%);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
}

.recommend-item:hover {
  transform: translateY(-2px);
  border-color: #bfd8cb;
  box-shadow: 0 10px 24px rgba(74, 115, 95, 0.12);
}

.recommend-item.is-active {
  border-color: #8fc2a8;
  box-shadow: 0 0 0 2px rgba(143, 194, 168, 0.24);
}

.recommend-item header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.recommend-item h4 {
  margin: 0;
  font-size: 15px;
  color: #274d46;
}

.source-tag {
  font-size: 11px;
  border-radius: 999px;
  border: 1px solid #d1e2da;
  padding: 2px 8px;
  color: #42665d;
  background: #eef5f1;
}

.reason {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: #577068;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #5f7a70;
}

.actions {
  margin-top: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.actions :deep(.el-button) {
  border-radius: 999px;
}

.recommend-empty {
  flex: 1;
  min-height: 0;
  border: 1px dashed #cfddd5;
  border-radius: 12px;
  padding: 12px;
  color: #70857c;
  font-size: 13px;
}

.detail-dialog h4 {
  margin: 0 0 8px;
  color: #254a41;
}

.detail-dialog p {
  margin: 0 0 10px;
  color: #5f7b71;
}

.detail-dialog ul {
  margin: 0;
  padding-left: 18px;
  color: #4c665d;
  line-height: 1.8;
}

.plan-dialog {
  display: grid;
  gap: 10px;
}

.plan-step {
  display: flex;
  gap: 10px;
  border: 1px solid #dbe8e2;
  border-radius: 10px;
  padding: 10px;
}

.plan-step span {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: #e7f2ec;
  color: #2f605a;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.plan-step p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #668177;
}

.flow-dialog {
  display: grid;
  gap: 8px;
}

.flow-dialog p {
  margin: 0;
  border: 1px solid #dbe8e2;
  background: #f7fbf9;
  border-radius: 10px;
  padding: 8px 10px;
  color: #4f6d63;
  font-size: 13px;
}

@media (max-width: 1080px) {
  .recommend-body {
    grid-template-columns: 1fr;
  }

  .recommend-grid,
  .recommend-skeleton-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .recommend-toolbar {
    grid-template-columns: minmax(0, 1fr);
  }

  .recommend-header {
    flex-direction: column;
  }

  .demo-director-strip {
    flex-direction: column;
  }
}
</style>
