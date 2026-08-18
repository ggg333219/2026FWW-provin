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
                @prev-page="handlePrevPage"
                @next-page="handleNextPage"
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
            <div v-else-if="activeTab === 'material'" class="tab-container">
              <S2MaterialWorkspace />
              <!-- 下一步：S2 → S3 讲稿编辑（同 Workspace 内嵌 S3 工作台） -->
              <div class="next-step-bar">
                <button type="button" class="next-step-btn" @click="activeTab = 'script'">
                  下一步：进入 S3 生成 →
                </button>
              </div>
            </div>
            <div v-else-if="activeTab === 'version'" class="tab-container">
              <div class="version-panel-inline">
                <div class="vp-toolbar">
                  <input
                    v-model="versionGenId"
                    type="text"
                    placeholder="输入 Generation ID"
                    class="vp-gen-input"
                    @keyup.enter="loadVersionData"
                  />
                  <button class="vp-btn vp-btn-primary" :disabled="versionStore.loading" @click="loadVersionData">
                    {{ versionStore.loading ? '加载中...' : '加载版本' }}
                  </button>
                </div>
                <div v-if="versionStore.error" class="vp-error">{{ versionStore.error }}</div>
                <div class="vp-grid">
                  <!-- 版本历史 -->
                  <div class="vp-card">
                    <h4>版本历史 ({{ versionStore.versionCount }})</h4>
                    <div v-if="versionStore.loading" class="vp-empty">加载中...</div>
                    <div v-else-if="versionStore.versions.length === 0" class="vp-empty">输入 Generation ID 加载版本</div>
                    <div v-else class="vp-list">
                      <div v-for="v in versionStore.versions" :key="v.id" class="vp-row" :class="{ locked: v.locked }">
                        <strong>v{{ v.version }}</strong>
                        <span>{{ v.summary || v.title }}</span>
                        <small>{{ formatVersionTime(v.createdAt) }}</small>
                        <span v-if="v.locked" class="vp-lock">🔒</span>
                      </div>
                    </div>
                  </div>
                  <!-- 操作 -->
                  <div class="vp-card">
                    <h4>版本操作</h4>
                    <div v-if="!versionStore.genId" class="vp-empty">请先加载版本</div>
                    <div v-else class="vp-actions">
                      <!-- 回滚 -->
                      <div class="vp-action-row">
                        <select v-model="rollbackTarget" class="vp-select">
                          <option :value="null" disabled>回滚目标版本</option>
                          <option v-for="v in versionStore.versions" :key="v.id" :value="v.version">v{{ v.version }}</option>
                        </select>
                        <button class="vp-btn vp-btn-sm" :disabled="!rollbackTarget || versionStore.loading" @click="handleRollback">回滚</button>
                      </div>
                      <!-- 锁定 -->
                      <div class="vp-action-row">
                        <button class="vp-btn vp-btn-sm vp-btn-warn" :disabled="versionStore.loading" @click="handleLock">🔒 锁定最新版本</button>
                      </div>
                      <!-- 修改指令 -->
                      <div class="vp-action-divider"></div>
                      <div class="vp-action-row">
                        <select v-model="changeType" class="vp-select">
                          <option value="update_node">更新节点</option>
                          <option value="add_node">新增节点</option>
                          <option value="delete_node">删除节点</option>
                          <option value="swap_nodes">交换节点</option>
                          <option value="change_template">切换模板</option>
                        </select>
                        <input v-model="changeTarget" type="text" placeholder="节点ID" class="vp-input" />
                        <button class="vp-btn vp-btn-sm" @click="handleAddChange">+</button>
                      </div>
                      <!-- 待提交 -->
                      <div v-if="versionStore.pendingChanges.length > 0" class="vp-change-mini">
                        <div v-for="c in versionStore.pendingChanges" :key="c.id" class="vp-change-row">
                          <span class="c-badge">{{ c.type }}</span>
                          <span class="c-target">{{ c.target }}</span>
                          <span class="c-status" :class="c.status">{{ c.status }}</span>
                        </div>
                        <button
                          v-if="versionStore.hasPendingChanges"
                          class="vp-btn vp-btn-primary"
                          :disabled="versionStore.loading"
                          @click="handleSubmitModify"
                        >
                          提交修改到后端
                        </button>
                      </div>
                    </div>
                  </div>
                  <!-- 导出 -->
                  <div class="vp-card">
                    <S4VersionExportCenter
                      :gen-id="versionStore.genId"
                      :export-status="versionStore.exportStatus"
                      :export-download-url="versionStore.exportDownloadUrl"
                      :export-error="versionStore.exportError"
                      :loading="versionStore.loading"
                      @start-export="(fmt) => versionStore.startExport(versionStore.genId, fmt)"
                      @reset-export="versionStore.resetExport()"
                    />
                  </div>
                </div>
              </div>
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
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import { useIntentStore } from '../stores/intentStore'
import { useMaterialStore } from '../stores/materialStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { useGenerationStore } from '../stores/generationStore'
import { useAnalyticsStore } from '../stores/analyticsStore'
import { useVersionStore } from '../stores/versionStore'
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
import S4VersionExportCenter from '../components/teacher/S4VersionExportCenter.vue'
import S2MaterialWorkspace from '../components/teacher/S2MaterialWorkspace.vue'

const router = useRouter()
const authStore = useAuthStore()
const intentStore = useIntentStore()
const materialStore = useMaterialStore()
const workspaceStore = useWorkspaceStore()
const generationStore = useGenerationStore()
const analyticsStore = useAnalyticsStore()
const versionStore = useVersionStore()
const shellRef = ref(null)

const activeTab = ref('script')
const isLeftMenuCollapsed = ref(window.innerWidth <= 1024)

// ---- S4 版本管理状态 ----
const versionGenId = ref('')
const rollbackTarget = ref(null)
const changeType = ref('update_node')
const changeTarget = ref('')
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
  { key: 'intent', label: '意图理解', iconPath: '<path d="M12 2v6"/><path d="M12 22v-6"/><circle cx="12" cy="12" r="3"/>' },
  { key: 'material', label: '资料中心', iconPath: '<path d="M4 4h16v16H4z"/><path d="M4 9h16"/><path d="M9 9v11"/>' },
  { key: 'version', label: '版本管理', iconPath: '<polyline points="6 9 12 15 18 9"/>' }
]

const switchTab = (item) => {
  activeTab.value = item.key
}

function readHandoff(key) {
  try {
    return window.localStorage.getItem(key) || ''
  } catch {
    return ''
  }
}

function writeHandoff(key, value) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // localStorage 不可用时不影响当前 Tab 的独立工作。
  }
}

function persistWorkspaceIntent(summary, status, intentId) {
  if (!['confirmed', 'locked'].includes(status)) return
  const topic = String(summary?.topic || '').trim()
  if (!topic) return
  const subject = String(summary?.subject || summary?.discipline || '').trim()
  writeHandoff('fuww_intent_parsed', JSON.stringify({
    ...summary,
    topic,
    ...(subject ? { subject } : {}),
    search_query: [topic, subject].filter(Boolean).join(' '),
    intent_id: intentId || summary?.intent_id || '',
    session_id: intentStore.sessionId || summary?.session_id || '',
    schema_version: 1
  }))
}

function restoreGenIdToVersion() {
  const generationId = generationStore.lastGenId ||
    generationStore.restoreLastGenId() ||
    readHandoff('fuww_last_gen_id')
  if (!generationId) return
  versionGenId.value = generationId
  if (!versionStore.genId) versionStore.genId = generationId
}

watch(
  () => [intentStore.intentSummary, intentStore.sessionStatus, intentStore.intentId],
  ([summary, status, intentId]) => persistWorkspaceIntent(summary, status, intentId),
  { deep: true, immediate: true }
)

watch(
  () => materialStore.latestEvidencePacket,
  (entry) => {
    if (entry?.packet) writeHandoff('fuww_s2_evidence_packet', JSON.stringify(entry.packet))
  },
  { deep: true }
)

watch(
  () => generationStore.lastGenId,
  (generationId) => {
    if (generationId) writeHandoff('fuww_last_gen_id', generationId)
  }
)

watch(activeTab, async (tab) => {
  await nextTick()
  if (tab === 'version') restoreGenIdToVersion()
})

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

const handlePrevPage = () => {
  const page = workspaceStore.currentEditPage - 1
  if (page >= 1) {
    workspaceStore.currentEditPage = page
    loadScriptAndNodes(workspaceStore.currentCourseId, page)
  }
}

const handleNextPage = () => {
  const page = workspaceStore.currentEditPage + 1
  const max = workspaceStore.currentCourseTotalPages || Infinity
  if (page <= max) {
    workspaceStore.currentEditPage = page
    loadScriptAndNodes(workspaceStore.currentCourseId, page)
  }
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
  if (!workspaceStore.currentCourseId) return
  generationStore.setGenerating(true)
  generationStore.setGenerateProgress(8, '正在分析课件内容')
  try {
    // 尝试从 localStorage 读取证据包（S2 证据透传，成员B）
    let evidence = null
    try {
      const raw = window.localStorage.getItem('fuww_s2_evidence_packet')
      if (raw) {
        evidence = JSON.parse(raw)
        console.log('[WorkspacePage] 从 localStorage 读取证据包:', evidence)
      }
    } catch (e) {
      console.warn('[WorkspacePage] 读取证据包失败', e)
    }

    generationStore.setGenerateProgress(30, '正在调用 AI 生成讲稿')
    const resp = await teacherV1Api.coursewares.generateScript({
      courseId: workspaceStore.currentCourseId,
      pageNum: workspaceStore.currentEditPage,
      evidence
    })
    generationStore.setGenerateProgress(80, '正在加载讲稿')

    // 重新从后端拉取刚生成的讲稿与节点
    const payload = resp?.data || resp || {}
    if (payload.content) {
      generationStore.setScript(payload.content)
    }
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

// ---- S4 版本操作方法 ----
async function loadVersionData() {
  const id = versionGenId.value.trim()
  if (!id) return
  await versionStore.loadVersions(id)
  if (versionStore.versions.length > 0) {
    await versionStore.loadVersion(id)
  }
}

async function handleRollback() {
  if (!rollbackTarget.value || !versionStore.genId) return
  try {
    await versionStore.rollbackTo(versionStore.genId, rollbackTarget.value)
    rollbackTarget.value = null
  } catch { /* 错误已在 store */ }
}

async function handleLock() {
  if (!versionStore.genId) return
  try {
    await versionStore.lockVersion(versionStore.genId)
  } catch { /* 错误已在 store */ }
}

function handleAddChange() {
  if (!changeTarget.value.trim()) return
  versionStore.addChange({
    type: changeType.value,
    target: changeTarget.value.trim()
  })
  changeTarget.value = ''
}

async function handleSubmitModify() {
  if (!versionStore.genId) return
  try {
    await versionStore.submitModify(versionStore.genId)
  } catch { /* 错误已在 store */ }
}

function formatVersionTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN')
}

onMounted(async () => {
  restoreGenIdToVersion()
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

/* 下一步：S2 → S3 讲稿编辑 */
.next-step-bar {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #e2ece6;
  text-align: right;
}

.next-step-btn {
  display: inline-block;
  padding: 10px 24px;
  background: #2f605a;
  color: #fff;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  border: 0;
  cursor: pointer;
  transition: background 0.15s;
}

.next-step-btn:hover {
  background: #1e4a44;
}

/* ---- 版本管理面板样式 ---- */
.version-panel-inline { display: flex; flex-direction: column; gap: 14px; }
.vp-toolbar { display: flex; gap: 10px; align-items: center; }
.vp-gen-input {
  flex: 1; max-width: 300px; padding: 8px 14px; border: 1px solid #cbd5e1;
  border-radius: 10px; font-size: 14px; outline: none; background: #fff;
}
.vp-gen-input:focus { border-color: #5ca68f; box-shadow: 0 0 0 3px rgba(92,166,143,0.15); }
.vp-error { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 8px 12px; border-radius: 8px; font-size: 13px; }
.vp-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
@media (max-width: 1100px) { .vp-grid { grid-template-columns: 1fr; } }
.vp-card { background: #fff; border: 1px solid #dbe6df; border-radius: 14px; padding: 14px; box-shadow: 0 2px 8px rgba(15,23,42,0.03); }
.vp-card h4 { margin: 0 0 10px; font-size: 15px; color: #2d5f58; }
.vp-empty { color: #94a3b8; text-align: center; padding: 30px 0; font-size: 14px; }
.vp-list { display: flex; flex-direction: column; gap: 6px; max-height: 280px; overflow-y: auto; }
.vp-row { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: #f6faf8; border-radius: 8px; font-size: 13px; }
.vp-row.locked { border-left: 3px solid #eab308; background: #fffdf0; }
.vp-row strong { color: #5ca68f; min-width: 32px; }
.vp-row span { flex: 1; color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vp-row small { font-size: 11px; color: #94a3b8; }
.vp-lock { font-size: 12px; }
.vp-actions { display: flex; flex-direction: column; gap: 8px; }
.vp-action-row { display: flex; gap: 8px; align-items: center; }
.vp-select { flex: 1; padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; background: #fff; }
.vp-btn { padding: 8px 16px; border: none; border-radius: 10px; cursor: pointer; font-size: 14px; font-weight: 500; transition: all 0.15s; }
.vp-btn-primary { background: #5ca68f; color: #fff; }
.vp-btn-primary:hover { background: #4a8d78; }
.vp-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.vp-btn-sm { padding: 6px 12px; font-size: 13px; background: #edf5f2; color: #2d5f58; border: 1px solid #c6ded6; border-radius: 8px; }
.vp-btn-sm:hover { background: #d6ece3; }
.vp-btn-warn { background: #fff7ed; color: #9a3412; border-color: #fed7aa; }
.vp-btn-warn:hover { background: #ffedd5; }
.vp-action-divider { height: 1px; background: #e2e8f0; margin: 4px 0; }
.vp-input { flex: 1; padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; background: #fff; max-width: 130px; }
.vp-change-mini { display: flex; flex-direction: column; gap: 4px; max-height: 160px; overflow-y: auto; }
.vp-change-row { display: flex; align-items: center; gap: 6px; padding: 4px 8px; background: #f8fafc; border-radius: 6px; font-size: 12px; }
.c-badge { font-size: 10px; padding: 1px 6px; border-radius: 999px; background: #edf5f2; color: #2f605a; white-space: nowrap; }
.c-target { flex: 1; color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.c-status { font-size: 10px; padding: 1px 6px; border-radius: 999px; }
.c-status.pending { background: #fef3c7; color: #92400e; }
.c-status.applied { background: #d1fae5; color: #065f46; }
.c-status.rejected { background: #fee2e2; color: #991b1b; }

@media (max-width: 980px) {
  .right-sidebar-shell {
    flex-basis: 40px;
    width: 40px;
    min-width: 40px;
  }
}
</style>
