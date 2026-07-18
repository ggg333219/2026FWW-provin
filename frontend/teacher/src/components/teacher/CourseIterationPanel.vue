<template>
  <div class="iteration-panel">
    <!-- 面板头部 -->
    <div class="panel-header">
      <h3>自适应教学闭环 - 学情迭代</h3>
      <p>基于上节课班级学情数据，智能推荐重讲节点、前置补充知识点，一键插入生成下节课讲稿，完成教学迭代闭环。</p>
    </div>

    <div class="main-layout">
      <!-- ============ 左侧：智能复盘建议区 ============ -->
      <aside class="left-panel suggestions-panel">
        <header class="panel-section-header">
          <h4>📋 智能复盘建议</h4>
          <small v-if="pendingNodes.length">({{ pendingNodes.length }} 待处理)</small>
        </header>

        <div class="suggestions-container">
          <!-- 建议节点列表 -->
          <div v-if="pendingNodes.length" class="suggestion-list">
            <div
              v-for="node in pendingNodes"
              :key="node.id"
              class="suggestion-item"
              :class="{ 'dragging': draggedNodeId === node.id }"
              draggable="true"
              @dragstart="handleDragStart($event, node)"
              @dragend="draggedNodeId = null"
            >
              <!-- 类型指示器 -->
              <div class="type-badge" :class="node.type">
                {{ node.type === 're_teach' ? '🔴 重讲' : '🟡 前置' }}
              </div>

              <!-- 内容 -->
              <div class="suggestion-content">
                <div class="suggestion-title">{{ node.title }}</div>
                <div class="suggestion-evidence" v-if="node.evidence">学情依据：{{ node.evidence }}</div>
                <div class="suggestion-reason">建议：{{ node.advice || node.reason }}</div>
                <div class="suggestion-model" v-if="node.priorityScore != null">
                  迭代优先级得分 {{ Number(node.priorityScore).toFixed(2) }}（多目标优化模型：停留·测验·互动加权）
                </div>
              </div>

              <!-- 操作按钮 -->
              <div class="suggestion-actions">
                <button type="button" class="text-link-btn" @click="openResourceForSuggestion(node)">匹配推荐资源</button>
                <button
                  type="button"
                  class="insert-btn primary"
                  @click="insertNodeToTree(node)"
                  title="同步到编辑讲稿大纲"
                >
                  插入到讲稿大纲
                </button>
              </div>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-else class="empty-state">
            <p>暂无待处理的建议节点</p>
          </div>

          <div class="replay-recommend-block">
            <div class="replay-recommend-title">🎬 智能复盘资源推荐（B站 / 51教习）</div>

            <div v-if="!boundNodeIds.length" class="mini-empty">
              先在下方把疑问绑定到节点，再自动生成对应视频推荐。
            </div>

            <div v-else class="replay-node-groups">
              <div
                v-for="nodeId in boundNodeIds"
                :key="`reco_${nodeId}`"
                class="replay-node-group"
              >
                <div class="replay-node-head">
                  <strong>{{ getNodeTitle(nodeId) }}</strong>
                  <button class="retry-btn" @click="loadRecommendForNode(nodeId, true)">刷新</button>
                </div>

                <div v-if="recommendLoadingMap[nodeId]" class="mini-loading">
                  正在加载推荐资源...
                </div>

                <div v-else-if="recommendErrorMap[nodeId]" class="mini-error">
                  {{ recommendErrorMap[nodeId] }}
                </div>

                <div v-else-if="(recommendByNodeId[nodeId] || []).length" class="mini-video-list">
                  <div
                    v-for="video in recommendByNodeId[nodeId]"
                    :key="video.id"
                    class="mini-video-item"
                  >
                    <div class="video-title">{{ video.title }}</div>
                    <div class="video-meta">来源：{{ video.source || 'Bilibili' }}</div>
                    <div class="video-reason">{{ video.reason || '与该节点知识点高度相关，适合作为课后复盘补充。' }}</div>
                    <button class="open-link-btn" @click="openVideo(video)">跳转链接</button>
                  </div>
                </div>

                <div v-else class="mini-empty">暂无匹配的推荐资源。</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 分隔线 -->
        <div class="divider"></div>

        <!-- 学生疑问关联池 -->
        <header class="panel-section-header">
          <h4>🤔 待关联疑问</h4>
          <small v-if="pendingCases.length">({{ pendingCases.length }} 待关联)</small>
        </header>

        <div class="questions-container">
          <div v-if="pendingCases.length" class="questions-list">
            <div
              v-for="(caseItem, idx) in pendingCases"
              :key="caseItem.id"
              class="question-item"
              :class="{ 'bound': caseItem.boundNodeId }"
            >
              <div class="question-header">
                <div class="question-content">
                  {{ caseItem.content }}
                </div>
                <span class="student-tag">{{ caseItem.student }}</span>
              </div>

              <div class="question-actions">
                <button
                  v-if="!caseItem.boundNodeId"
                  class="bind-btn"
                  @click="showNodeSelector(caseItem, idx)"
                  title="绑定到节点"
                >
                  绑定节点
                </button>
                <div v-else class="bound-info">
                  <span class="bound-tag">📌 已绑定</span>
                  <button
                    class="unbind-btn"
                    @click="unbindCase(idx)"
                    title="解除绑定"
                  >
                    ✕
                  </button>
                </div>
              </div>

              <!-- 节点选择器（内联展开式） -->
              <div v-if="activeSelectorIdx === idx && !caseItem.boundNodeId" class="node-selector">
                <div class="selector-title">选择目标节点</div>
                <div class="node-options">
                  <button
                    v-for="treeNode in nodeTree"
                    :key="treeNode.id"
                    class="node-option"
                    @click="bindCaseToNode(idx, treeNode.id)"
                  >
                    {{ treeNode.title }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="empty-state">
            <p>暂无待关联的学生疑问</p>
          </div>
        </div>
      </aside>

      <!-- ============ 右侧：课件大纲树与讲稿生成 ============ -->
      <main class="right-panel outline-panel">
        <!-- 大纲树 -->
        <header class="panel-section-header">
          <h4>📚 下节课大纲树</h4>
          <small>({{ nodeTree.length }} 个节点)</small>
        </header>

        <div class="outline-tree">
          <div v-if="nodeTree.length" class="tree-container">
            <div
              v-for="(node, idx) in nodeTree"
              :key="node.id"
              class="tree-node"
              :class="{ 'new-node': node.isNew || node.fromIteration, 'has-cases': (bindingMap[node.id] || []).length > 0 }"
              @drop="handleDropToNode($event, idx)"
              @dragover.prevent="dragOverNodeIdx = idx"
              @dragleave="dragOverNodeIdx = -1"
              :style="{ opacity: dragOverNodeIdx === idx ? 0.7 : 1 }"
            >
              <!-- 节点头部 -->
              <div class="node-header">
                <!-- 新增/迭代标记 -->
                <span v-if="node.isNew || node.fromIteration" class="new-tag">
                  {{ node.fromIteration ? '[迭代新增]' : '[新增]' }}
                </span>

                <!-- 节点标题 -->
                <span class="node-title">{{ node.title }}</span>

                <!-- 关联案例徽章 -->
                <span v-if="(bindingMap[node.id] || []).length > 0" class="case-badge" :title="`关联了 ${bindingMap[node.id].length} 个案例`">
                  📌 {{ bindingMap[node.id].length }}
                </span>
              </div>

              <!-- 节点操作栏 -->
              <div class="node-actions">
                <button
                  v-if="idx > 0"
                  class="action-btn move-up"
                  @click="moveNodeUp(idx)"
                  title="上移"
                >
                  ↑
                </button>
                <button
                  v-if="idx < nodeTree.length - 1"
                  class="action-btn move-down"
                  @click="moveNodeDown(idx)"
                  title="下移"
                >
                  ↓
                </button>
                <button
                  class="action-btn delete-btn"
                  @click="removeNode(idx)"
                  title="删除"
                >
                  ✕
                </button>
              </div>

              <!-- 关联案例信息 -->
              <div v-if="(bindingMap[node.id] || []).length > 0" class="node-cases">
                <div class="cases-title">关联案例:</div>
                <ul class="cases-list">
                  <li v-for="caseId in bindingMap[node.id]" :key="caseId">
                    {{ findCaseContent(caseId) }}
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <div v-else class="empty-state">
            <p>大纲树为空，从左侧拖入建议节点或手动添加。</p>
          </div>
        </div>

        <!-- 新增节点按钮 -->
        <div class="outline-footer">
          <button type="button" class="add-node-btn" @click="addManualNode">
            + 手动新增节点
          </button>
        </div>

        <div class="outline-toolbar bottom-toolbar">
          <button
            type="button"
            class="generate-btn"
            @click="generateScript"
            :disabled="isGenerating || nodeTree.length === 0"
          >
            <span v-if="isGenerating" class="spinner">⌛</span>
            <span v-else>▶</span>
            {{ isGenerating ? '生成讲稿中...' : '一键生成讲稿' }}
          </button>
          <p class="toolbar-hint">生成后将自动跳转「编辑讲稿」，并把大纲同步为讲稿节点</p>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { teacherV1Service } from '../../services/teacher.v1'

// ============ Props & Emits ============
const props = defineProps({
  currentCourseId: {
    type: String,
    default: ''
  },
  questionRecords: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:script', 'script-generated', 'sync-outline-node', 'open-resource-recommend', 'toast'])

// ============ Mock 数据 ============

// 1. 基础大纲树 (下节课原本的计划)
const basicNodeTree = ref([
  { id: 'n1', title: '快速排序的原理', type: 'concept', isNew: false, fromIteration: false, cases: [] },
  { id: 'n2', title: '时间复杂度分析', type: 'concept', isNew: false, fromIteration: false, cases: [] }
])

// 2. 待处理的建议节点 (来自 AI 报告)
const pendingNodes = ref([
  {
    id: 'p1',
    title: '递归的基础概念',
    type: 'prerequisite',
    reason: '复盘发现 30% 学生上节课在该知识点停留偏长',
    evidence: '复盘发现约 30% 学生上节课在该知识点停留时长超班级均值 200%，存在理解卡点',
    advice: '补充前置概念讲解，降低后续算法主线 cognitive load',
    priorityScore: 8.6
  },
  {
    id: 'p2',
    title: '基准值的选择策略',
    type: 're_teach',
    reason: '上节课该知识点随堂测验正确率偏低',
    evidence: '上节课该知识点随堂测验正确率仅 45%，超 60% 学生错题集中于此',
    advice: '重点重讲，并补充 2～3 道配套巩固题',
    priorityScore: 9.1
  }
])

// 3. 待关联的学生案例
const pendingCases = ref([])

// ============ 状态管理 ============

// 当前大纲树（会动态变化）
const nodeTree = ref([...basicNodeTree.value])
const nodeList = nodeTree

// 拖拽状态
const draggedNodeId = ref(null)
const dragOverNodeIdx = ref(-1)

// 节点选择器状态
const activeSelectorIdx = ref(null)

// случจ例与节点的绑定关系: { [nodeId]: [caseId1, caseId2, ...] }
const bindingMap = ref({})

// 讲稿生成状态
const isGenerating = ref(false)
const recommendByNodeId = ref({})
const recommendLoadingMap = ref({})
const recommendErrorMap = ref({})

// ============ 计算属性 ============

// 获取特定节点绑定的案例数量
const getNodeCaseCount = (nodeId) => {
  return (bindingMap.value[nodeId] || []).length
}

const boundNodeIds = computed(() => {
  const ids = new Set(
    (pendingCases.value || [])
      .map(item => item?.boundNodeId)
      .filter(Boolean)
  )
  return Array.from(ids)
})

// ============ 方法 ============

watch(
  () => props.questionRecords,
  (records) => {
    const list = Array.isArray(records) ? records : []
    pendingCases.value = list
      .map((item, index) => {
        const rawId = String(item?.id || '').trim()
        const content = String(item?.content || '').trim()
        const student = String(item?.studentId || item?.userId || '未知学生').trim()
        if (!content) return null
        return {
          id: rawId || `q_${index + 1}`,
          content,
          student,
          boundNodeId: null
        }
      })
      .filter(Boolean)
  },
  { immediate: true, deep: true }
)

/**
 * 拖拽开始：记录被拖动的建议节点
 */
const handleDragStart = (event, node) => {
  draggedNodeId.value = node.id
  event.dataTransfer.effectAllowed = 'copy'
  event.dataTransfer.setData('suggestionsNode', JSON.stringify(node))
}

/**
 * 拖拽结束
 */
const handleDragEnd = () => {
  draggedNodeId.value = null
}

/**
 * 处理节点放置：将建议节点拖入大纲树
 */
const handleDropToNode = (event, idx) => {
  event.preventDefault()
  dragOverNodeIdx.value = -1
  
  try {
    const data = event.dataTransfer.getData('suggestionsNode')
    if (data) {
      const draggedNode = JSON.parse(data)
      // 将建议节点插入到大纲树中
      insertNodeToTree(draggedNode, idx)
    }
  } catch (err) {
    console.error('Drop failed:', err)
  }
}

/**
 * 将建议节点插入到大纲树
 */
const insertNodeToTree = (node, insertIdx = null) => {
  const newNode = {
    id: `n_${Date.now()}_${Math.random().toString(36).slice(2)}`,
    title: node.title,
    type: node.type,
    isNew: true,
    fromIteration: true,
    cases: []
  }

  if (insertIdx !== null && insertIdx !== undefined) {
    nodeTree.value.splice(insertIdx + 1, 0, newNode)
  } else {
    nodeTree.value.push(newNode)
  }

  // 从待处理列表中移除（可选）
  const idx = pendingNodes.value.findIndex(p => p.id === node.id)
  if (idx > -1) {
    pendingNodes.value.splice(idx, 1)
  }

  emit('sync-outline-node', { ...newNode })
}

const openResourceForSuggestion = (node) => {
  const keyword = String(node?.title || '').trim()
  if (!keyword) return
  emit('open-resource-recommend', {
    keyword,
    matchReason: String(node?.evidence || node?.reason || '').trim()
  })
}

/**
 * 显示节点选择器（绑定疑问到节点）
 */
const showNodeSelector = (caseItem, idx) => {
  activeSelectorIdx.value = activeSelectorIdx.value === idx ? null : idx
}

/**
 * 绑定案例到节点
 */
const bindCaseToNode = (caseIdx, nodeId) => {
  // 更新案例的绑定状态
  pendingCases.value[caseIdx].boundNodeId = nodeId

  // 在绑定映射中添加
  if (!bindingMap.value[nodeId]) {
    bindingMap.value[nodeId] = []
  }
  bindingMap.value[nodeId].push(pendingCases.value[caseIdx].id)

  // 关闭选择器
  activeSelectorIdx.value = null

  // 绑定后触发该节点的资源推荐
  loadRecommendForNode(nodeId)
}

/**
 * 解除案例与节点的绑定
 */
const unbindCase = (caseIdx) => {
  const caseId = pendingCases.value[caseIdx].id
  const nodeId = pendingCases.value[caseIdx].boundNodeId

  if (nodeId && bindingMap.value[nodeId]) {
    const idx = bindingMap.value[nodeId].indexOf(caseId)
    if (idx > -1) {
      bindingMap.value[nodeId].splice(idx, 1)
    }
  }

  pendingCases.value[caseIdx].boundNodeId = null
}

/**
 * 根据案例ID查找案例内容
 */
const findCaseContent = (caseId) => {
  const caseItem = pendingCases.value.find(c => c.id === caseId)
  return caseItem ? caseItem.content : '未知案例'
}

/**
 * 上移节点
 */
const moveNodeUp = (idx) => {
  if (idx > 0) {
    [nodeTree.value[idx - 1], nodeTree.value[idx]] = [nodeTree.value[idx], nodeTree.value[idx - 1]]
  }
}

/**
 * 下移节点
 */
const moveNodeDown = (idx) => {
  if (idx < nodeTree.value.length - 1) {
    [nodeTree.value[idx], nodeTree.value[idx + 1]] = [nodeTree.value[idx + 1], nodeTree.value[idx]]
  }
}

/**
 * 删除节点
 */
const removeNode = (idx) => {
  const node = nodeTree.value[idx]
  
  // 清除该节点的绑定关系
  if (bindingMap.value[node.id]) {
    delete bindingMap.value[node.id]
  }
  if (recommendByNodeId.value[node.id]) {
    delete recommendByNodeId.value[node.id]
  }
  if (recommendLoadingMap.value[node.id] !== undefined) {
    delete recommendLoadingMap.value[node.id]
  }
  if (recommendErrorMap.value[node.id]) {
    delete recommendErrorMap.value[node.id]
  }

  nodeTree.value.splice(idx, 1)
}

/**
 * 手动新增节点
 */
const addManualNode = () => {
  const title = prompt('请输入新节点的标题:')
  if (title && title.trim()) {
    const newNode = {
      id: `n_${Date.now()}_${Math.random().toString(36).slice(2)}`,
      title: title.trim(),
      type: 'concept',
      isNew: true,
      fromIteration: false,
      cases: []
    }
    nodeTree.value.push(newNode)
  }
}

const buildScriptFallback = () => {
  if (!nodeList.value.length) return ''

  let markdown = '# 下节课讲稿大纲\n\n'
  nodeList.value.forEach((node, idx) => {
    markdown += `## ${idx + 1}. ${node.title}\n`
    markdown += `### 学习目标\n- 掌握${node.title}的核心要点\n\n`
    markdown += '### 教学活动\n- 讲解（5-10分钟）\n- 案例分析（10分钟）\n- 练习与反馈（5分钟）\n\n'
  })
  return markdown
}

/**
 * 生成讲稿（调用后端接口）
 */
const generateScript = async () => {
  if (nodeList.value.length === 0) {
    alert('请先添加至少一个节点到大纲中')
    return
  }

  isGenerating.value = true

  try {
    const nodeOrder = nodeList.value
      .map(node => String(node?.id || '').trim())
      .filter(Boolean)

    const res = await teacherV1Service.generateIterationScript({
      courseId: props.currentCourseId,
      nodeOrder
    })

    let content = String(res?.data || '').trim()
    if (!content) {
      content = buildScriptFallback()
    }

    emit('update:script', content)
    emit('script-generated', {
      content,
      nodeTree: nodeTree.value,
      bindingMap: bindingMap.value
    })

    emit('toast', '讲稿已生成并同步至编辑讲稿')
  } catch (err) {
    console.error('生成讲稿失败:', err)
    const content = buildScriptFallback()
    emit('update:script', content)
    emit('script-generated', {
      content,
      nodeTree: nodeTree.value,
      bindingMap: bindingMap.value
    })
    emit('toast', '后端不可用，已使用前端模拟讲稿并同步至编辑讲稿')
  } finally {
    isGenerating.value = false
  }
}

const getNodeTitle = (nodeId) => {
  const node = nodeTree.value.find(item => item.id === nodeId)
  return node?.title || '未命名节点'
}

const normalizeRecommendItem = (item, index, nodeId) => {
  const source = String(item?.source || item?.Source || '').trim()
  return {
    id: String(item?.id || item?.ID || `${nodeId}_${index}`),
    title: String(item?.title || item?.Title || '未命名视频').trim(),
    source,
    reason: String(item?.fit_reason || item?.recommend_reason || item?.reason || item?.Reason || '').trim(),
    link: String(item?.link || item?.url || item?.Link || item?.URL || '').trim()
  }
}

const loadRecommendForNode = async (nodeId, force = false) => {
  if (!nodeId) return
  if (recommendByNodeId.value[nodeId]?.length && !force) return

  const nodeTitle = getNodeTitle(nodeId)
  if (!nodeTitle || nodeTitle === '未命名节点') return

  recommendLoadingMap.value = { ...recommendLoadingMap.value, [nodeId]: true }
  recommendErrorMap.value = { ...recommendErrorMap.value, [nodeId]: '' }

  try {
    const res = await teacherV1Service.fetchRecommendedResources({
      keyword: nodeTitle,
      type: '网课',
      source_preference: ['Bilibili', '51jiaoxi'],
      page: 1,
      pageSize: 6
    })

    const list = (res.list || [])
      .map((item, index) => normalizeRecommendItem(item, index, nodeId))
      .filter(item => item.title)

    recommendByNodeId.value = {
      ...recommendByNodeId.value,
      [nodeId]: list.slice(0, 3)
    }
  } catch (error) {
    recommendByNodeId.value = {
      ...recommendByNodeId.value,
      [nodeId]: [
        {
          id: `${nodeId}_mock_1`,
          title: `${nodeTitle} - 复盘精讲（前端模拟）`,
          source: 'Bilibili',
          reason: '基于节点关键字自动匹配的演示资源（模拟链路）。',
          link: 'https://www.bilibili.com/video/BV1Ddemo1'
        },
        {
          id: `${nodeId}_mock_2`,
          title: `${nodeTitle} - 常见误区专项训练（前端模拟）`,
          source: 'Bilibili',
          reason: '聚焦高频错误点，适合课后复盘补强。',
          link: 'https://www.bilibili.com/video/BV1Ddemo2'
        }
      ]
    }
    recommendErrorMap.value = {
      ...recommendErrorMap.value,
      [nodeId]: ''
    }
  } finally {
    recommendLoadingMap.value = { ...recommendLoadingMap.value, [nodeId]: false }
  }
}

const openVideo = (video) => {
  if (!video?.link) {
    alert('该资源暂无可打开链接，已保留为演示占位。')
    return
  }
  window.open(video.link, '_blank', 'noopener,noreferrer')
}

watch(boundNodeIds, (ids) => {
  ids.forEach((nodeId) => {
    loadRecommendForNode(nodeId)
  })
}, { immediate: true })
</script>

<style scoped>
.iteration-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #ffffff;
  border-radius: 14px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

.panel-header {
  padding: 18px;
  border-bottom: 1px solid #e2e8f0;
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  color: #0f172a;
  font-weight: 700;
}

.panel-header p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
}

.main-layout {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
  gap: 0;
  flex: 1;
  overflow: hidden;
}

/* ============ 左侧面板 ============ */

.left-panel {
  display: flex;
  flex-direction: column;
  border-right: 1px solid #e2e8f0;
  overflow-y: auto;
}

.suggestions-panel {
  background: #f8fbfa;
}

.panel-section-header {
  padding: 12px 16px;
  background: #f1f5f3;
  border-bottom: 1px solid #dbe5df;
  position: sticky;
  top: 0;
  z-index: 10;
}

.panel-section-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.panel-section-header small {
  display: block;
  color: #64748b;
  font-size: 12px;
  margin-top: 2px;
}

.suggestions-container {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.replay-recommend-block {
  margin-top: 12px;
  border: 1px solid #dbe5df;
  border-radius: 10px;
  background: #ffffff;
  padding: 10px;
}

.replay-recommend-title {
  font-size: 12px;
  font-weight: 700;
  color: #1f4f49;
  margin-bottom: 8px;
}

.replay-node-groups {
  display: grid;
  gap: 8px;
}

.replay-node-group {
  border: 1px solid #e1ebe6;
  border-radius: 8px;
  padding: 8px;
  background: #fbfefd;
}

.replay-node-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.replay-node-head strong {
  font-size: 12px;
  color: #1f3f3a;
  line-height: 1.3;
}

.retry-btn,
.open-link-btn {
  border: 1px solid #c8d9d2;
  background: #f3faf7;
  color: #285f59;
  border-radius: 6px;
  font-size: 11px;
  padding: 4px 8px;
  cursor: pointer;
}

.mini-loading,
.mini-empty,
.mini-error {
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}

.mini-error {
  color: #b91c1c;
}

.mini-video-list {
  display: grid;
  gap: 6px;
}

.mini-video-item {
  border: 1px solid #e5ede9;
  background: #ffffff;
  border-radius: 8px;
  padding: 8px;
  display: grid;
  gap: 4px;
}

.video-title {
  font-size: 12px;
  font-weight: 700;
  color: #1f2937;
  line-height: 1.35;
}

.video-meta,
.video-reason {
  font-size: 11px;
  color: #64748b;
  line-height: 1.4;
}

.suggestion-list {
  display: grid;
  gap: 10px;
}

.suggestion-item {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 10px 12px;
  align-items: start;
  padding: 16px;
  background: #ffffff;
  border: 1px solid #dbe5df;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  cursor: grab;
  transition: all 0.2s ease;
}

.suggestion-item:hover {
  border-color: #2f605a;
  background: #f9fffe;
}

.suggestion-item.dragging {
  opacity: 0.5;
  scale: 0.95;
}

.type-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  padding: 6px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  background: #f0f4f8;
  color: #334155;
}

.type-badge.re_teach {
  background: #fee2e2;
  color: #7f1d1d;
}

.type-badge.prerequisite {
  background: #fef3c7;
  color: #78350f;
}

.suggestion-content {
  min-width: 0;
}

.suggestion-title {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.suggestion-evidence {
  font-size: 12px;
  color: #666666;
  margin-top: 8px;
  line-height: 1.45;
}

.suggestion-reason {
  font-size: 12px;
  color: #666666;
  margin-top: 8px;
  line-height: 1.45;
}

.suggestion-model {
  font-size: 11px;
  color: #999999;
  margin-top: 6px;
}

.suggestion-actions {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  align-items: center;
  margin-top: 4px;
}

.text-link-btn {
  border: none;
  background: none;
  color: #2d8cf0;
  font-size: 14px;
  cursor: pointer;
  padding: 8px 4px;
  transition: transform 0.15s ease;
}

.text-link-btn:hover {
  text-decoration: underline;
}

.text-link-btn:active {
  transform: scale(0.96);
}

.insert-btn {
  padding: 8px 16px;
  background: #ffffff;
  color: #2d8cf0;
  border: 1px solid #2d8cf0;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.insert-btn.primary {
  background: #2d8cf0;
  color: #ffffff;
  border-color: #2d8cf0;
  padding: 12px 24px;
}

.insert-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(45, 140, 240, 0.25);
}

.insert-btn:active {
  transform: scale(0.96);
}

.divider {
  height: 1px;
  background: #dbe5df;
  margin: 8px 10px;
}

.questions-container {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.questions-list {
  display: grid;
  gap: 10px;
}

.question-item {
  display: grid;
  gap: 8px;
  padding: 10px;
  background: #ffffff;
  border: 1px solid #dbe5df;
  border-radius: 10px;
  transition: all 0.2s ease;
}

.question-item.bound {
  background: #f0fdf4;
  border-color: #22c55e;
}

.question-header {
  display: grid;
  gap: 6px;
}

.question-content {
  font-size: 12px;
  color: #0f172a;
  line-height: 1.4;
  word-break: break-word;
}

.student-tag {
  display: inline-block;
  max-width: fit-content;
  padding: 2px 8px;
  background: #e0f2fe;
  color: #0369a1;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.question-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.bind-btn {
  padding: 5px 10px;
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.bind-btn:hover {
  background: #e5e7eb;
  border-color: #9ca3af;
}

.bound-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.bound-tag {
  padding: 2px 8px;
  background: #dcfce7;
  color: #16a34a;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.unbind-btn {
  padding: 2px 6px;
  background: #fecaca;
  color: #991b1b;
  border: none;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.unbind-btn:hover {
  background: #fca5a5;
}

.node-selector {
  display: grid;
  gap: 8px;
  padding: 8px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 8px;
  margin-top: 4px;
}

.selector-title {
  font-size: 11px;
  font-weight: 700;
  color: #0369a1;
}

.node-options {
  display: grid;
  gap: 4px;
}

.node-option {
  padding: 6px 8px;
  background: #ffffff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
  font-size: 11px;
  color: #0369a1;
  cursor: pointer;
  transition: all 0.2s ease;
  text-align: left;
}

.node-option:hover {
  background: #e0f2fe;
  border-color: #0284c7;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100px;
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
  padding: 16px;
}

/* ============ 右侧面板 ============ */

.right-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #ffffff;
}

.outline-panel {
  padding: 16px;
}

.outline-toolbar {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

.bottom-toolbar {
  margin-bottom: 0;
}

.toolbar-hint {
  margin: 0;
  font-size: 12px;
  color: #999999;
  line-height: 1.4;
}

.generate-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  background: #2d8cf0;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.generate-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(45, 140, 240, 0.35);
}

.generate-btn:active:not(:disabled) {
  transform: translateY(0);
}

.generate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
  display: inline-block;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.outline-tree {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 12px;
}

.tree-container {
  display: grid;
  gap: 12px;
}

.tree-node {
  display: grid;
  gap: 8px;
  padding: 12px;
  background: #ffffff;
  border: 2px solid #dbe5df;
  border-radius: 10px;
  transition: all 0.2s ease;
  position: relative;
}

.tree-node:hover {
  border-color: #2f605a;
  box-shadow: 0 4px 8px rgba(47, 96, 90, 0.1);
}

.tree-node.new-node {
  background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%);
  border-color: #22c55e;
}

.tree-node.new-node::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #22c55e, #16a34a);
  border-radius: 10px 10px 0 0;
}

.tree-node.has-cases {
  background: linear-gradient(135deg, #fef3c7 0%, #fef08a 100%);
}

.node-header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 10px;
  align-items: center;
}

.new-tag {
  padding: 4px 10px;
  background: #22c55e;
  color: #ffffff;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.node-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.case-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: #fbbf24;
  color: #78350f;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.node-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  padding: 5px 8px;
  background: #f3f4f6;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: #e5e7eb;
  border-color: #9ca3af;
}

.action-btn.delete-btn:hover {
  background: #fee2e2;
  border-color: #fca5a5;
  color: #991b1b;
}

.node-cases {
  display: grid;
  gap: 6px;
  padding: 8px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.cases-title {
  font-size: 11px;
  font-weight: 700;
  color: #374151;
}

.cases-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 4px;
}

.cases-list li {
  font-size: 12px;
  color: #4b5563;
  padding-left: 16px;
  position: relative;
  line-height: 1.3;
  word-break: break-word;
}

.cases-list li::before {
  content: '•';
  position: absolute;
  left: 4px;
  color: #9ca3af;
}

.outline-footer {
  display: flex;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid #e2e8f0;
}

.add-node-btn {
  padding: 8px 14px;
  background: #f3f4f6;
  color: #374151;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.add-node-btn:hover {
  background: #e5e7eb;
  border-color: #9ca3af;
}

/* ============ 响应式 ============ */

@media (max-width: 1400px) {
  .main-layout {
    grid-template-columns: 320px 1fr;
  }

  .panel-section-header h4 {
    font-size: 13px;
  }

  .suggestion-item {
    grid-template-columns: auto 1fr;
  }

  .suggestion-actions {
    grid-column: 1 / -1;
    justify-self: flex-end;
    margin-top: 4px;
  }
}

@media (max-width: 1024px) {
  .main-layout {
    grid-template-columns: 280px 1fr;
  }

  .node-header {
    grid-template-columns: auto 1fr;
  }

  .case-badge {
    grid-column: 1 / -1;
    justify-self: flex-start;
    margin-top: 4px;
  }
}
</style>
