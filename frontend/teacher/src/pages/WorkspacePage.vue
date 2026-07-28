<template>
  <AppShell ref="shellRef">
    <div class="workspace-shell-inner">
      <!-- 左侧 MENU 导航栏 -->
      <div class="left-sidebar-menu" :class="{ collapsed: isLeftMenuCollapsed }">
        <div class="menu-header">
          <span v-show="!isLeftMenuCollapsed">菜单</span>
          <button
            class="menu-toggle-btn"
            @click="isLeftMenuCollapsed = !isLeftMenuCollapsed"
            :title="isLeftMenuCollapsed ? '展开菜单' : '收起菜单'"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 12h18"></path><path d="M3 6h18"></path><path d="M3 18h18"></path>
            </svg>
          </button>
        </div>
        <div class="menu-list">
          <div
            v-for="item in menuItems"
            :key="item.key"
            class="menu-item"
            :class="{ active: activeTab === item.key }"
            @click="switchTab(item)"
            :title="item.label"
          >
            <svg class="ins-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" v-html="item.iconPath" />
            <span v-show="!isLeftMenuCollapsed">{{ item.label }}</span>
          </div>
        </div>
      </div>

      <!-- 中间内容编辑区 -->
      <div class="editor-section">
        <div class="workspace-back-row">
          <button class="ghost-btn" @click="backToMiddle">返回中间页</button>
        </div>
        <transition name="tab-switch" mode="out-in">
          <div :key="activeTab" class="tab-switch-host">
            <div v-if="activeTab === 'script'" class="tab-container">
              <TeacherScriptPanel
                :preview-url="previewUrl"
                :current-course-name="workspaceStore.currentCourseName"
                :current-course-id="workspaceStore.currentCourseId"
                :current-edit-page="workspaceStore.currentEditPage"
                :total-pages="workspaceStore.currentCourseTotalPages"
                :current-script="generationStore.currentScript"
                :current-script-nodes="generationStore.currentScriptNodes"
                :script-generating="generationStore.isGenerating"
                :script-saving="generationStore.isSaving"
                :ai-generate-progress="generationStore.generateProgress"
                :ai-generate-stage-text="generationStore.generateStageText"
                :iteration-sync-notice="generationStore.iterationSyncNotice"
                :node-insights="analyticsStore.nodeInsights"
                :current-page-audio="generationStore.currentPageAudio"
                :audio-generating="generationStore.audioGenerating"
                @generate-ai-script="handleGenerateAIScript"
                @generate-audio="handleGenerateAudio"
                @save-script="handleSaveScript"
                @update:current-script="generationStore.setScript($event)"
                @update:current-script-nodes="generationStore.setNodes($event)"
              />
            </div>
            <div v-else-if="activeTab === 'stats'" class="tab-container">
              <TeacherStatsPanel
                :current-course-id="workspaceStore.currentCourseId"
                :current-course-name="workspaceStore.currentCourseName"
                :student-stats="analyticsStore.studentStats"
                :card-data="analyticsStore.cardData"
                :initial-stats-tab="analyticsStore.statsSubTab"
                @update:stats-tab="analyticsStore.setStatsSubTab($event)"
              />
            </div>
            <div v-else-if="activeTab === 'questions'" class="tab-container">
              <TeacherQuestionsPanel
                :current-course-id="workspaceStore.currentCourseId"
                :current-course-name="workspaceStore.currentCourseName"
                :current-course-total-pages="workspaceStore.currentCourseTotalPages"
                :filter-page="analyticsStore.filterPage"
                :filtered-questions="analyticsStore.filteredQuestions"
                :uncovered-node-ids="analyticsStore.studentStats.mappingCoverage?.uncoveredNodeIds || []"
                @update:filter-page="analyticsStore.setFilterPage($event)"
              />
            </div>
            <div v-else-if="activeTab === 'iteration'" class="tab-container">
              <CourseIterationPanel
                :current-course-id="workspaceStore.currentCourseId"
                :question-records="analyticsStore.questionRecords"
              />
            </div>
            <div v-else-if="activeTab === 'knowledge'" class="tab-container">
              <TeacherKnowledgeGraphPanel
                :course-id="workspaceStore.currentCourseId"
                :course-name="workspaceStore.currentCourseName"
              />
            </div>
            <div v-else-if="activeTab === 'intent'" class="tab-container">
              <TeacherIntentPanel />
            </div>
            <div v-else class="tab-container"></div>
          </div>
        </transition>
      </div>

      <!-- 右侧课件侧边栏 -->
      <div v-show="workspaceStore.isSidebarVisible" class="right-sidebar-shell">
        <TeacherCoursewareSidebar
          :courseware-list="workspaceStore.coursewareList"
          :current-course-id="workspaceStore.currentCourseId"
          :current-course-name="workspaceStore.currentCourseName"
          :current-course-total-pages="workspaceStore.currentCourseTotalPages"
          :current-edit-page="workspaceStore.currentEditPage"
          :course-list-loading="workspaceStore.courseListLoading"
          @select-course="handleSelectCourse"
          @select-page="handleSelectPage"
        />
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { useGenerationStore } from '../stores/generationStore'
import { useAnalyticsStore } from '../stores/analyticsStore'
import { teacherV1Api } from '../services/v1'
import { API_BASE } from '../config/api'

// 组件引入
import AppShell from '../components/layout/AppShell.vue'
import TeacherTopBar from '../components/teacher/TeacherTopBar.vue'
import TeacherScriptPanel from '../components/teacher/TeacherScriptPanel.vue'
import TeacherStatsPanel from '../components/teacher/TeacherStatsPanel.vue'
import TeacherQuestionsPanel from '../components/teacher/TeacherQuestionsPanel.vue'
import TeacherKnowledgeGraphPanel from '../components/teacher/TeacherKnowledgeGraphPanel.vue'
import TeacherCoursewareSidebar from '../components/teacher/TeacherCoursewareSidebar.vue'
import CourseIterationPanel from '../components/teacher/CourseIterationPanel.vue'
import TeacherIntentPanel from '../components/teacher/TeacherIntentPanel.vue'

const router = useRouter()
const authStore = useAuthStore()
const workspaceStore = useWorkspaceStore()
const generationStore = useGenerationStore()
const analyticsStore = useAnalyticsStore()
const shellRef = ref(null)

const activeTab = ref('script')
const isLeftMenuCollapsed = ref(window.innerWidth <= 1024)
const previewUrl = computed(() => {
  if (!workspaceStore.currentCourseId) return ''
  return `${API_BASE}/api/courseware/${workspaceStore.currentCourseId}/page/${workspaceStore.currentEditPage}`
})

const menuItems = [
  { key: 'script', label: '编辑讲稿', iconPath: '<path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>' },
  { key: 'stats', label: '学情分析', iconPath: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>' },
  { key: 'questions', label: '提问统计', iconPath: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>' },
  { key: 'knowledge', label: '知识库', iconPath: '<path d="M3 6.5C3 5.12 4.12 4 5.5 4H10v16H5.5A2.5 2.5 0 0 1 3 17.5v-11z"/><path d="M21 6.5C21 5.12 19.88 4 18.5 4H14v16h4.5a2.5 2.5 0 0 0 2.5-2.5v-11z"/>' },
  { key: 'iteration', label: '学情迭代', iconPath: '<path d="M21.5 2v6h-6"/><path d="M2.5 22v-6h6"/><path d="M2 11.5a10 10 0 0 1 18.8-4.3"/><path d="M22 12.5a10 10 0 0 1-18.8 2.2"/>' },
  { key: 'intent', label: '意图理解', iconPath: '<path d="M12 2v6"/><path d="M12 22v-6"/><circle cx="12" cy="12" r="3"/>' }
]

const switchTab = (item) => {
  activeTab.value = item.key
}

const backToMiddle = () => {
  workspaceStore.backToMiddle()
  router.push({ name: 'Middle' })
}

const handleSelectCourse = async (course) => {
  workspaceStore.selectCourse(course.id)
  await loadCourseContext(course.id)
}

const handleSelectPage = async (page) => {
  workspaceStore.currentEditPage = page
  await loadScriptAndNodes(workspaceStore.currentCourseId, page)
}

const loadCourseContext = async (courseId) => {
  await Promise.all([
    loadScriptAndNodes(courseId, workspaceStore.currentEditPage),
    analyticsStore.loadStats(courseId),
    analyticsStore.loadCardData(courseId),
    analyticsStore.loadQuestionRecords(courseId)
  ])
}

const loadScriptAndNodes = async (courseId, page) => {
  if (!courseId) return
  try {
    const scriptResp = await teacherV1Api.coursewares.getScript(courseId, page)
    const payload = scriptResp?.data || {}
    generationStore.setScript(payload.content || '')
    if (Array.isArray(payload.nodes) && payload.nodes.length > 0) {
      generationStore.setNodes(normalizeNodes(payload.nodes, page))
      return
    }
    const nodesResp = await teacherV1Api.coursewares.getNodes(courseId, page)
    const nodes = nodesResp?.data?.nodes || []
    generationStore.setNodes(normalizeNodes(nodes, page))
  } catch {
    const nodes = buildDemoNodes(page)
    generationStore.setNodes(nodes)
  }
}

const handleGenerateAIScript = async () => {
  generationStore.setGenerating(true)
  generationStore.setGenerateProgress(8, '正在分析课件内容')
  try {
    await teacherV1Api.coursewares.generateScript({
      courseId: workspaceStore.currentCourseId,
      pageNum: workspaceStore.currentEditPage
    })
    await loadScriptAndNodes(workspaceStore.currentCourseId, workspaceStore.currentEditPage)
    generationStore.setGenerateProgress(100, '生成完成')
  } catch (err) {
    console.warn('生成讲稿失败', err)
  } finally {
    setTimeout(() => {
      generationStore.setGenerating(false)
    }, 650)
  }
}

const handleGenerateAudio = async () => {
  if (!workspaceStore.currentCourseId) return
  generationStore.setAudioGenerating(true)
  try {
    await teacherV1Api.coursewares.generateAudio({
      courseId: workspaceStore.currentCourseId,
      pageNum: workspaceStore.currentEditPage
    })
  } catch (err) {
    console.warn('生成音频失败', err)
  } finally {
    generationStore.setAudioGenerating(false)
  }
}

const handleSaveScript = async () => {
  if (!workspaceStore.currentCourseId) return
  generationStore.setSaving(true)
  try {
    await teacherV1Api.coursewares.saveNodes({
      courseId: workspaceStore.currentCourseId,
      pageNum: workspaceStore.currentEditPage,
      nodes: generationStore.currentScriptNodes
    })
    await teacherV1Api.coursewares.saveScript({
      courseId: workspaceStore.currentCourseId,
      pageNum: workspaceStore.currentEditPage,
      content: generationStore.currentScript
    })
    alert('讲稿保存成功！')
  } catch {
    alert('后端保存不可用，已使用前端模拟保存。')
  } finally {
    generationStore.setSaving(false)
  }
}

function normalizeNodes(nodes, page, rawScript = '') {
  const source = Array.isArray(nodes) ? nodes : []
  if (source.length > 0) {
    return source.map((item, index) => ({
      id: item.id || '',
      nodeId: item.nodeId || `p${page}_n${index + 1}`,
      title: item.title || `节点${index + 1}`,
      summary: item.summary || '',
      scriptText: String(item.scriptText || item.text || '').trim(),
      reteachScript: item.reteachScript || '',
      transitionText: item.transitionText || '',
      estimatedDuration: Number(item.estimatedDuration) || 28,
      sortOrder: index + 1
    }))
  }
  return []
}

function buildDemoNodes(page) {
  return [
    { id: '', nodeId: `p${page}_n1`, title: `节点1：第${page}页导入`, summary: '明确本页学习目标', scriptText: `同学们好，我们先快速回顾上页内容，再进入第${page}页核心目标。`, reteachScript: '', transitionText: '', estimatedDuration: 26, sortOrder: 1 },
    { id: '', nodeId: `p${page}_n2`, title: '节点2：核心讲解', summary: '讲解关键方法与思路', scriptText: '本节点重点讲清方法步骤，并配套一题课堂演示。', reteachScript: '', transitionText: '', estimatedDuration: 34, sortOrder: 2 },
    { id: '', nodeId: `p${page}_n3`, title: '节点3：总结与练习', summary: '通过练习巩固并总结', scriptText: '最后用两道快问快答巩固本页内容，并总结常见易错点。', reteachScript: '', transitionText: '', estimatedDuration: 28, sortOrder: 3 }
  ]
}

onMounted(async () => {
  await workspaceStore.loadCoursewareList()
  if (workspaceStore.currentCourseId) {
    await loadCourseContext(workspaceStore.currentCourseId)
  }
})
</script>

<style scoped>
.workspace-shell-inner {
  display: flex;
  min-height: calc(100vh - 158px);
  height: auto;
  overflow-y: auto;
  padding: 14px;
  gap: 14px;
}

.left-sidebar-menu {
  flex: 0 0 206px;
  background: #ffffff;
  border-radius: 22px;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
  display: flex;
  flex-direction: column;
  padding: 14px 10px;
  transition: flex-basis 0.3s ease;
}

.left-sidebar-menu.collapsed {
  flex-basis: 78px;
}

.menu-header {
  padding: 6px 12px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: #5f7467;
  letter-spacing: 0.04em;
}

.left-sidebar-menu.collapsed .menu-header {
  padding: 6px 0 10px;
  justify-content: center;
}

.menu-toggle-btn {
  background: transparent;
  border: 0;
  cursor: pointer;
  color: #5f7467;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border-radius: 9px;
  transition: background 0.2s, color 0.2s;
}

.menu-toggle-btn:hover {
  background: #ecf7f2;
  color: #111827;
}

.menu-toggle-btn svg {
  width: 18px;
  height: 18px;
}

.menu-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  cursor: pointer;
  color: #475569;
  transition: all 0.2s;
  border: 0;
  border-radius: 14px;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
}

.left-sidebar-menu.collapsed .menu-item {
  padding: 12px 0;
  justify-content: center;
}

.menu-item:hover {
  background: #eef8f3;
}

.menu-item.active {
  color: #2f6052;
  background: rgba(227, 245, 238, 0.96);
  font-weight: 600;
  box-shadow: 0 6px 16px rgba(92, 166, 143, 0.18);
}

.ins-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  stroke: currentColor;
}

.editor-section {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: visible;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-radius: 22px;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
  padding: 14px;
  transition: filter 0.28s ease, transform 0.28s ease;
}

.right-sidebar-shell {
  flex: 0 0 44px;
  width: 44px;
  min-width: 44px;
  min-height: 0;
  position: relative;
  overflow: visible;
  z-index: 3;
}

.workspace-back-row {
  margin-bottom: 14px;
  padding: 0;
}

.tab-container {
  flex: 1;
  min-height: 0;
  overflow: visible;
  display: flex;
  flex-direction: column;
  border: 0;
  border-radius: 20px;
  background: transparent;
  box-shadow: none;
}

.tab-switch-host {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.tab-switch-enter-active,
.tab-switch-leave-active {
  transition: opacity 0.28s ease-out, transform 0.28s ease-out;
}

.tab-switch-enter-from {
  opacity: 0;
  transform: translateX(18px);
}

.tab-switch-leave-to {
  opacity: 0;
  transform: translateX(-18px);
}

.ghost-btn {
  border: 0;
  background: #ffffff;
  color: #334155;
  border-radius: 999px;
  padding: 8px 16px;
  font-size: 12px;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.08);
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.ghost-btn:hover {
  background: #f7f8fc;
  transform: translateY(-1px);
  box-shadow: 0 8px 16px rgba(15, 23, 42, 0.1);
}

@media (max-width: 980px) {
  .right-sidebar-shell {
    flex-basis: 40px;
    width: 40px;
    min-width: 40px;
  }
}
</style>
