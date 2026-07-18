<template>
  <div class="panel-root">
    <div v-if="!currentCourseId" class="empty-tip">请先选择一个课件查看提问统计</div>
    <template v-else>
      <section class="top-sticky">
        <div class="header-row">
          <div>
            <h3>提问统计 · {{ currentCourseName }}</h3>
            <p>教学决策中枢：筛选、洞察、建议联动</p>
          </div>
          <div class="actions">
            <button class="btn primary" :disabled="aiGenerating" @click="generateSuggestions">
              {{ aiGenerating ? "AI 分析中..." : "生成教学优化建议" }}
            </button>
            <button class="btn" @click="exportQuestions">导出提问数据</button>
            <button class="btn" @click="markAllHandled">批量标记已处理</button>
          </div>
        </div>

        <div class="filters">
          <select :value="localFilterPage" @change="onPageChange($event.target.value)">
            <option value="">全部页码</option>
            <option v-for="page in currentCourseTotalPages" :key="page" :value="String(page)">第{{ page }}页</option>
          </select>
          <select v-model="selectedNode" multiple>
            <option value="__ALL__">全部节点</option>
            <option v-for="node in nodeOptions" :key="node" :value="node">{{ node }}</option>
          </select>
          <select v-model="selectedStudents" multiple>
            <option value="__ALL_STUDENTS__">全部学生</option>
            <option v-for="student in studentOptions" :key="student" :value="student">学生 {{ student }}</option>
          </select>
          <select v-model="selectedType">
            <option value="">全部疑问类型</option>
            <option value="concept">概念类</option>
            <option value="exercise">习题类</option>
            <option value="extension">拓展类</option>
          </select>
          <select v-model="groupBy">
            <option value="node">按知识点分组</option>
            <option value="type">按疑问类型分组</option>
            <option value="time">按时间分组</option>
          </select>
          <input v-model.trim="searchKeyword" placeholder="关键词搜索提问内容..." />
          <label class="checkbox-line">
            <input v-model="onlyUncoveredQuestions" type="checkbox" />
            仅看未覆盖节点问题
          </label>
        </div>

        <div class="overview-cards">
          <div class="card">
            <span>总提问数</span>
            <strong>{{ filteredQuestions.length }}</strong>
          </div>
          <div class="card">
            <span>今日新增</span>
            <strong>{{ todayCount }}</strong>
          </div>
          <div class="card">
            <span>未处理</span>
            <strong>{{ unhandledCount }}</strong>
          </div>
          <div class="card">
            <span>高频疑问 Top3</span>
            <div class="top3">
              <div v-for="(item, idx) in topKeywords" :key="item.keyword || idx" class="top3-item">
                <span>{{ item.keyword || "暂无" }}</span>
                <em>{{ item.count || 0 }}</em>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="middle-grid">
        <aside class="left-viz">
          <div class="viz-block">
            <h4>疑问关键词词云</h4>
            <div class="word-cloud">
              <button
                v-for="item in keywordCloud"
                :key="item.keyword"
                :style="{ fontSize: `${12 + item.weight * 12}px` }"
                class="word"
                @click="searchKeyword = item.keyword"
              >
                {{ item.keyword }}
              </button>
            </div>
          </div>

          <div class="viz-block">
            <h4>知识点疑问热力图</h4>
            <div class="heat-list">
              <button
                v-for="item in nodeHeat"
                :key="item.node"
                class="heat-item"
                @click="selectedNode = [item.node]"
              >
                <span>{{ item.node }}</span>
                <i :style="{ width: `${item.ratio}%` }"></i>
                <em>{{ item.count }}</em>
              </button>
            </div>
          </div>

          <div class="viz-block">
            <h4>疑问类型分布</h4>
            <div class="type-pills">
              <button
                v-for="t in typeDistribution"
                :key="t.key"
                :class="['pill', t.key]"
                @click="selectedType = t.key"
              >
                {{ t.label }} · {{ t.count }}
              </button>
            </div>
          </div>

          <div class="viz-block">
            <h4>提问趋势（近 7 天）</h4>
            <div class="trend-bars">
              <button
                v-for="item in questionTrend"
                :key="item.day"
                class="trend-item"
                @click="searchKeyword = ''"
                :title="`${item.day}：${item.count}条`"
              >
                <div class="bar-track">
                  <i :style="{ height: `${item.ratio}%` }"></i>
                </div>
                <span>{{ item.day.slice(5) }}</span>
                <em>{{ item.count }}</em>
              </button>
            </div>
          </div>
        </aside>

        <main class="right-list">
          <div class="group-section" v-for="section in groupedQuestionSections" :key="section.key">
            <div class="group-header">
              <button class="group-toggle" @click="toggleGroup(section.key)">
                {{ collapsedGroups[section.key] ? '▶' : '▼' }} {{ section.title }}（{{ section.items.length }}）
              </button>
              <button class="mini" @click="batchReply(section.items)">批量回复本组</button>
            </div>
            <transition-group v-if="!collapsedGroups[section.key]" name="fade-move" tag="div" class="question-cards">
              <article v-for="q in section.items" :key="q.id" class="question-card">
                <header class="meta">
                  <span>学生 {{ q.studentId }}</span>
                  <span>第{{ q.page }}页</span>
                  <button class="node-tag" :class="{ uncovered: isUncoveredNode(q.nodeId) }" @click="$emit('focus-node', q)">
                    {{ q.nodeTitle || q.nodeId || "未标注节点" }}
                  </button>
                  <span :class="['q-type', q.qType]">{{ q.typeLabel }}</span>
                  <span :class="['status', q.status]">{{ q.status === "handled" ? "已处理" : "未处理" }}</span>
                  <time>{{ q.time }}</time>
                </header>
                <div class="body">
                  <div class="question">{{ q.content }}</div>
                  <div v-if="q.answer" class="answer">AI 回复：{{ q.answer }}</div>
                </div>
                <footer class="ops">
                  <button class="mini" @click="markHandled(q.id)">标记已处理</button>
                  <button class="mini" @click="addToLesson(q)">添加到备课优化</button>
                  <button class="mini" @click="replyStudent(q)">回复学生</button>
                  <button class="mini" @click="viewSimilar(q)">查看同类提问</button>
                </footer>
              </article>
            </transition-group>
          </div>
          <div v-if="groupedQuestionSections.length === 0" class="empty-tip">当前筛选条件下暂无提问记录</div>
        </main>
      </section>

      <transition name="slide-fade">
        <section v-if="advicePanelOpen" class="ai-panel">
          <h4>AI 教学优化建议</h4>
          <div class="advice-list">
            <div class="advice-item">
              <h5>① 高频疑问总结</h5>
              <ul>
                <li v-for="item in topKeywords" :key="`sum-${item.keyword}`">{{ item.keyword }}（{{ item.count }}次）</li>
              </ul>
            </div>
            <div class="advice-item">
              <h5>② 教学优化建议</h5>
              <ul>
                <li v-for="item in aiAdvices" :key="item">{{ item }}</li>
              </ul>
            </div>
            <div class="advice-item">
              <h5>③ 备课素材推荐</h5>
              <ul>
                <li>补充 3 道同类型练习题，先易后难。</li>
                <li>对高频概念添加「反例讲解 + 边界条件」讲稿段落。</li>
                <li>下节课开场先做 2 分钟复盘问答。</li>
              </ul>
            </div>
          </div>
          <div class="actions">
            <button class="btn primary" @click="alertAction('已应用到讲稿')">一键应用到讲稿</button>
            <button class="btn" @click="alertAction('已触发生成补充习题')">生成补充习题</button>
            <button class="btn" @click="alertAction('已导出备课报告（演示）')">导出备课报告</button>
          </div>
        </section>
      </transition>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  currentCourseId: {
    type: String,
    default: ''
  },
  currentCourseName: {
    type: String,
    default: ''
  },
  currentCourseTotalPages: {
    type: Number,
    default: 0
  },
  filterPage: {
    type: [String, Number],
    default: ''
  },
  filteredQuestions: {
    type: Array,
    default: () => []
  },
  uncoveredNodeIds: {
    type: Array,
    default: () => []
  }
})

const onlyUncoveredQuestions = ref(false)
const localFilterPage = ref(String(props.filterPage || ''))
const selectedNode = ref([])
const selectedStudents = ref([])
const selectedType = ref('')
const searchKeyword = ref('')
const aiGenerating = ref(false)
const advicePanelOpen = ref(false)
const handledMap = ref({})
const aiAdvices = ref([])
const groupBy = ref('node')
const collapsedGroups = ref({})

const uncoveredNodeIdSet = computed(() => {
  return new Set((props.uncoveredNodeIds || []).map(item => String(item || '').trim()).filter(Boolean))
})

const hasUncoveredNodes = computed(() => uncoveredNodeIdSet.value.size > 0)

watch(() => props.filterPage, (val) => {
  localFilterPage.value = String(val || '')
})

watch(selectedNode, (val) => {
  if (Array.isArray(val) && val.includes('__ALL__')) {
    selectedNode.value = []
  }
})

watch(selectedStudents, (val) => {
  if (Array.isArray(val) && val.includes('__ALL_STUDENTS__')) {
    selectedStudents.value = []
  }
})

const rawQuestions = computed(() => Array.isArray(props.filteredQuestions) ? props.filteredQuestions : [])

const classifyType = (text) => {
  const s = String(text || '')
  if (/(为什么|概念|原理|定义|怎么理解)/.test(s)) return 'concept'
  if (/(题|解|步骤|计算|公式|边界|条件)/.test(s)) return 'exercise'
  return 'extension'
}

const normalizedQuestions = computed(() => {
  return rawQuestions.value.map((q) => {
    const qType = classifyType(q.content)
    return {
      ...q,
      qType,
      typeLabel: qType === 'concept' ? '概念类' : qType === 'exercise' ? '习题类' : '拓展类',
      status: handledMap.value[q.id] ? 'handled' : 'pending'
    }
  })
})

const nodeOptions = computed(() => {
  const set = new Set()
  normalizedQuestions.value.forEach((q) => {
    const key = String(q.nodeTitle || q.nodeId || '').trim()
    if (key) set.add(key)
  })
  return Array.from(set)
})

const studentOptions = computed(() => {
  const set = new Set(normalizedQuestions.value.map(q => String(q.studentId || '').trim()).filter(Boolean))
  return Array.from(set)
})

const filteredQuestions = computed(() => {
  return normalizedQuestions.value.filter((q) => {
    if (localFilterPage.value && Number(localFilterPage.value) !== Number(q.page)) return false
    if (selectedNode.value.length > 0) {
      const node = String(q.nodeTitle || q.nodeId || '').trim()
      if (!selectedNode.value.includes(node)) return false
    }
    if (selectedStudents.value.length > 0 && !selectedStudents.value.includes(String(q.studentId || ''))) return false
    if (selectedType.value && q.qType !== selectedType.value) return false
    if (searchKeyword.value && !String(q.content || '').includes(searchKeyword.value)) return false
    if (onlyUncoveredQuestions.value && !isUncoveredNode(q.nodeId)) return false
    return true
  })
})

const keywordStats = computed(() => {
  const counter = new Map()
  const stopWords = new Set(['这个', '那个', '怎么', '为什么', '一下', '可以', '还是', '我们', '老师', '学生'])
  filteredQuestions.value.forEach((q) => {
    String(q.content || '')
      .split(/[\s，。！？、；：,.!?()（）【】\[\]]+/)
      .map(s => s.trim())
      .filter(s => s.length >= 2 && !stopWords.has(s))
      .forEach((w) => counter.set(w, (counter.get(w) || 0) + 1))
  })
  return Array.from(counter.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([keyword, count]) => ({ keyword, count }))
})

const topKeywords = computed(() => keywordStats.value.slice(0, 3))

const keywordCloud = computed(() => {
  const top = keywordStats.value.slice(0, 16)
  const max = top[0]?.count || 1
  return top.map(item => ({ ...item, weight: item.count / max }))
})

const nodeHeat = computed(() => {
  const counter = new Map()
  filteredQuestions.value.forEach((q) => {
    const key = String(q.nodeTitle || q.nodeId || '未标注节点').trim()
    counter.set(key, (counter.get(key) || 0) + 1)
  })
  const list = Array.from(counter.entries()).map(([node, count]) => ({ node, count }))
  list.sort((a, b) => b.count - a.count)
  const max = list[0]?.count || 1
  return list.slice(0, 10).map((item) => ({ ...item, ratio: Math.max(10, Math.round(item.count / max * 100)) }))
})

const typeDistribution = computed(() => {
  const config = [
    { key: 'concept', label: '概念类' },
    { key: 'exercise', label: '习题类' },
    { key: 'extension', label: '拓展类' }
  ]
  return config.map(item => ({
    ...item,
    count: filteredQuestions.value.filter(q => q.qType === item.key).length
  }))
})

const groupedQuestionSections = computed(() => {
  const map = new Map()
  const buildKey = (q) => {
    if (groupBy.value === 'type') return q.typeLabel
    if (groupBy.value === 'time') return String(q.time || '').split(' ')[0] || '未知日期'
    return String(q.nodeTitle || q.nodeId || '未标注节点')
  }
  filteredQuestions.value.forEach((q) => {
    const k = buildKey(q)
    if (!map.has(k)) map.set(k, [])
    map.get(k).push(q)
  })
  return Array.from(map.entries()).map(([title, items]) => ({
    key: `${groupBy.value}-${title}`,
    title,
    items
  }))
})

const todayCount = computed(() => {
  const today = new Date().toLocaleDateString()
  return filteredQuestions.value.filter((q) => String(q.time || '').includes(today)).length
})

const unhandledCount = computed(() => filteredQuestions.value.filter(q => q.status === 'pending').length)

const isUncoveredNode = (nodeId) => uncoveredNodeIdSet.value.has(String(nodeId || '').trim())

const onPageChange = (value) => {
  localFilterPage.value = String(value || '')
  emit('update:filterPage', localFilterPage.value)
}

const markHandled = (id) => {
  handledMap.value = { ...handledMap.value, [id]: true }
}

const markAllHandled = () => {
  const map = { ...handledMap.value }
  filteredQuestions.value.forEach((q) => { map[q.id] = true })
  handledMap.value = map
}

const toggleGroup = (key) => {
  collapsedGroups.value = { ...collapsedGroups.value, [key]: !collapsedGroups.value[key] }
}

const addToLesson = () => alertAction('已加入备课优化列表')
const replyStudent = () => alertAction('已发送补充讲解给学生（演示）')
const viewSimilar = (q) => { selectedType.value = q.qType }
const batchReply = (items) => alertAction(`已批量回复本组 ${items.length} 条提问（演示）`)

const toDateKey = (value) => {
  const text = String(value || '').trim()
  if (!text) return ''
  const head = text.split(' ')[0].replace(/\//g, '-')
  const m = head.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/)
  if (!m) return ''
  const y = m[1]
  const mo = m[2].padStart(2, '0')
  const d = m[3].padStart(2, '0')
  return `${y}-${mo}-${d}`
}

const questionTrend = computed(() => {
  const dayMap = new Map()
  const now = new Date()
  for (let i = 6; i >= 0; i -= 1) {
    const d = new Date(now)
    d.setDate(now.getDate() - i)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    dayMap.set(key, 0)
  }
  filteredQuestions.value.forEach((q) => {
    const key = toDateKey(q.time)
    if (dayMap.has(key)) dayMap.set(key, dayMap.get(key) + 1)
  })
  const list = Array.from(dayMap.entries()).map(([day, count]) => ({ day, count }))
  const max = Math.max(...list.map(i => i.count), 1)
  return list.map(item => ({ ...item, ratio: Math.max(10, Math.round(item.count / max * 100)) }))
})

const generateSuggestions = async () => {
  aiGenerating.value = true
  advicePanelOpen.value = true
  await new Promise(resolve => setTimeout(resolve, 900))
  aiAdvices.value = [
    '针对高频概念疑问，建议在对应页加入“定义-反例-练习”三段式讲解。',
    '对习题类疑问较高的节点，补充1道课堂例题和2道课后分层题。',
    '将未覆盖节点优先加入下一轮备课迭代，先讲前置知识再讲主节点。'
  ]
  aiGenerating.value = false
}

const exportQuestions = () => {
  const rows = [
    ['学生ID', '页码', '节点', '类型', '提问内容', 'AI回复', '时间', '状态'],
    ...filteredQuestions.value.map((q) => [
      q.studentId,
      q.page,
      q.nodeTitle || q.nodeId || '',
      q.typeLabel,
      q.content || '',
      q.answer || '',
      q.time || '',
      q.status === 'handled' ? '已处理' : '未处理'
    ])
  ]
  const csv = rows.map(row => row.map(item => `"${String(item).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8;' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${props.currentCourseName || '提问统计'}-questions.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

const alertAction = (text) => window.alert(text)

const emit = defineEmits(['update:filterPage', 'focus-node'])
</script>

<style scoped>
.panel-root { display: flex; flex-direction: column; gap: 14px; }
.top-sticky { position: sticky; top: 0; z-index: 5; background: #fff; border: 1px solid #e5ede8; border-radius: 14px; padding: 14px; box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06); }
.header-row { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.header-row h3 { margin: 0; color: #1f3b35; }
.header-row p { margin: 4px 0 0; color: #6b7f78; font-size: 13px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.btn { border: 1px solid #d5e3dc; background: #fff; border-radius: 10px; padding: 8px 12px; cursor: pointer; }
.btn.primary { background: #2f605a; color: #fff; border-color: #2f605a; }
.filters { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.filters select, .filters input { border: 1px solid #d9e6de; border-radius: 10px; padding: 8px 10px; min-width: 0; }
.checkbox-line { display: inline-flex; gap: 6px; align-items: center; font-size: 13px; color: #526a62; }
.overview-cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.card { border: 1px solid #e4ece8; background: #f9fcfa; border-radius: 12px; padding: 10px; }
.card span { color: #6a8179; font-size: 12px; }
.card strong { display: block; margin-top: 4px; font-size: 22px; color: #213d37; }
.top3 { margin-top: 6px; display: grid; gap: 4px; }
.top3-item { display: flex; justify-content: space-between; font-size: 12px; color: #3f5d56; }

.middle-grid { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 12px; }
.left-viz, .right-list { border: 1px solid #e4ece8; border-radius: 14px; background: #fff; padding: 12px; }
.viz-block + .viz-block { margin-top: 12px; }
.viz-block h4 { margin: 0 0 8px; color: #294d45; }
.word-cloud { display: flex; flex-wrap: wrap; gap: 8px; }
.word { border: 0; background: #edf6f2; color: #2f605a; border-radius: 999px; padding: 4px 10px; cursor: pointer; }
.heat-list { display: grid; gap: 6px; }
.heat-item { border: 1px solid #e2ebe7; background: #f9fcfb; border-radius: 8px; display: grid; grid-template-columns: 1fr 1fr auto; align-items: center; gap: 8px; padding: 7px; cursor: pointer; }
.heat-item i { height: 8px; border-radius: 999px; background: linear-gradient(90deg, #94d8c3, #2f605a); display: block; }
.type-pills { display: flex; gap: 8px; flex-wrap: wrap; }
.pill { border: 0; border-radius: 999px; padding: 6px 10px; cursor: pointer; color: #fff; }
.pill.concept { background: #2563eb; }
.pill.exercise { background: #ea580c; }
.pill.extension { background: #059669; }
.trend-bars { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 8px; align-items: end; min-height: 130px; }
.trend-item { border: 1px solid #e2ebe7; border-radius: 8px; background: #f8fcfa; padding: 6px 4px; display: flex; flex-direction: column; align-items: center; gap: 4px; cursor: pointer; }
.bar-track { width: 18px; height: 72px; border-radius: 6px; background: #e8f2ee; position: relative; overflow: hidden; display: flex; align-items: flex-end; }
.trend-item i { position: absolute; left: 1px; right: 1px; bottom: 1px; display: block; border-radius: 6px 6px 0 0; background: linear-gradient(180deg,#9ddfcb,#2f605a); min-height: 6px; }
.trend-item span { font-size: 11px; color: #5e756e; }
.trend-item em { font-size: 11px; color: #2f605a; font-style: normal; }

.question-cards { display: grid; gap: 10px; }
.group-section + .group-section { margin-top: 10px; }
.group-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.group-toggle { border: 1px solid #dce8e2; border-radius: 8px; background: #f7fbf9; color: #325f53; padding: 6px 10px; cursor: pointer; }
.question-card { border: 1px solid #e3ece8; border-radius: 12px; background: #fff; padding: 12px; transition: all .2s ease; }
.question-card:hover { transform: translateY(-2px); box-shadow: 0 10px 16px rgba(15,23,42,.08); }
.meta { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: #667b74; align-items: center; }
.node-tag { border: 1px solid #c9ddd5; background: #edf7f3; color: #2f605a; border-radius: 999px; padding: 2px 8px; cursor: pointer; }
.node-tag.uncovered { border-style: dashed; border-color: #d48e1c; color: #9a560f; background: #fff6e9; }
.q-type { border-radius: 999px; padding: 2px 8px; color: #fff; }
.q-type.concept { background: #2563eb; }
.q-type.exercise { background: #ea580c; }
.q-type.extension { background: #059669; }
.status { border-radius: 999px; padding: 2px 8px; }
.status.pending { background: #fee2e2; color: #b91c1c; }
.status.handled { background: #e5e7eb; color: #4b5563; }
.body { margin-top: 8px; }
.question { color: #12211d; line-height: 1.65; }
.answer { margin-top: 6px; color: #425a53; }
.ops { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
.mini { border: 1px solid #d5e3dc; background: #fff; border-radius: 8px; padding: 5px 10px; cursor: pointer; font-size: 12px; }

.ai-panel { border: 1px solid #dce8e2; background: linear-gradient(180deg,#fff,#f5fbf8); border-radius: 14px; padding: 12px; }
.ai-panel h4 { margin: 0 0 10px; color: #21423a; }
.advice-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.advice-item { border: 1px solid #e2ebe6; background: #fff; border-radius: 10px; padding: 10px; }
.advice-item h5 { margin: 0 0 6px; color: #365f55; }
.advice-item ul { margin: 0; padding-left: 16px; color: #4b635d; }

.fade-move-enter-active, .fade-move-leave-active { transition: all .25s ease; }
.fade-move-enter-from, .fade-move-leave-to { opacity: 0; transform: translateY(8px); }
.slide-fade-enter-active, .slide-fade-leave-active { transition: all .28s ease; }
.slide-fade-enter-from, .slide-fade-leave-to { opacity: 0; transform: translateY(10px); }

.empty-tip {
  text-align: center;
  color: #64748b;
  padding: 24px;
}

@media (max-width: 1200px) {
  .filters { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .overview-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .middle-grid { grid-template-columns: 1fr; }
  .advice-list { grid-template-columns: 1fr; }
}
</style>