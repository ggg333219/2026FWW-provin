<template>
  <AppShell>
    <div class="s3-page">
      <div class="page-header">
        <div>
          <h2>S3 讲稿生成</h2>
          <p>讲稿编辑、节点树管理与音频生成</p>
        </div>
        <div class="page-header-right">
          <div class="step-pills">
            <router-link :to="{ name: 'S1Intent' }" class="pill">S1 意图</router-link>
            <router-link :to="{ name: 'S2Material' }" class="pill">S2 资料</router-link>
            <span class="pill active">S3 生成</span>
            <router-link :to="{ name: 'S4Version' }" class="pill">S4 版本</router-link>
          </div>
        </div>
      </div>
      <div v-if="generationMode === 'without_evidence'" class="evidence-warning" role="status">
        <div>
          <strong>当前为无参考资料生成模式</strong>
          <span>本次内容仅依据 S1 教学意图生成，不会伪造资料引用；需要更准确的内容时可返回补充教材或课件。</span>
        </div>
        <router-link :to="{ name: 'S2Material' }">返回补充资料</router-link>
      </div>
      <div class="page-body">
        <!-- 课件上下文工具栏 -->
        <div class="s3-toolbar">
          <div class="s3-toolbar-left">
            <label class="toolbar-label">课件 ID：</label>
            <input
              v-model="courseIdInput"
              type="text"
              class="s3-course-id-input"
              placeholder="输入课件 ID 或留空使用演示模式"
              @keyup.enter="loadCourseContext"
            />
            <button class="btn btn-sm" :disabled="loading" @click="loadCourseContext">
              {{ loading ? '加载中...' : '加载课件' }}
            </button>
          </div>
          <div class="s3-toolbar-right">
            <span class="page-indicator" v-if="courseId">
              第 <strong>{{ editPage }}</strong> / {{ totalPages || 1 }} 页
            </span>
            <button class="btn btn-icon-round" :disabled="editPage <= 1" @click="editPage--; loadScriptAndNodes(); console.log('[S3] prev:', editPage)" title="上一页">‹</button>
            <button class="btn btn-icon-round" :disabled="editPage >= (totalPages || 1)" @click="editPage++; loadScriptAndNodes(); console.log('[S3] next:', editPage, 'totalPages:', totalPages)" title="下一页">›</button>
          </div>
        </div>

        <div v-if="!courseId" class="s3-welcome">
          <div class="welcome-card">
            <h3>欢迎使用讲稿生成工作台</h3>
            <p>输入课件 ID 加载已有课件，或直接使用下方的演示模式体验讲稿编辑功能。</p>
            <p class="welcome-hint">演示模式下将生成示例节点，编辑与保存操作仅缓存至本地。</p>
            <button class="btn btn-primary" @click="loadDemoMode">进入演示模式</button>
          </div>
        </div>

        <template v-else>
          <TeacherScriptPanel
            :preview-url="previewUrl"
            :current-course-name="courseName"
            :current-course-id="courseId"
            :current-edit-page="editPage"
            :total-pages="totalPages"
            :current-script="generationStore.currentScript"
            :current-script-nodes="generationStore.currentScriptNodes"
            :script-generating="generationStore.isGenerating"
            :script-saving="generationStore.isSaving"
            :ai-generate-progress="generationStore.generateProgress"
            :ai-generate-stage-text="generationStore.generateStageText"
            :iteration-sync-notice="generationStore.iterationSyncNotice"
            :node-insights="[]"
            :current-page-audio="generationStore.currentPageAudio"
            :audio-generating="generationStore.audioGenerating"
            @generate-ai-script="handleGenerateAIScript"
            @generate-audio="handleGenerateAudio"
            @save-script="handleSaveScript"
            @update:current-script="generationStore.setScript($event)"
            @update:current-script-nodes="generationStore.setNodes($event)"
            @prev-page="editPage--; loadScriptAndNodes()"
            @next-page="editPage++; loadScriptAndNodes()"
          />
        </template>
      </div>
      <!-- 下一步：S3 → S4 -->
      <div class="next-step-bar">
        <router-link :to="{ name: 'S4Version' }" class="next-step-btn">
          下一步：版本管理 →
        </router-link>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppShell from '../components/layout/AppShell.vue'
import TeacherScriptPanel from '../components/teacher/TeacherScriptPanel.vue'
import { useGenerationStore } from '../stores/generationStore'
import { teacherV1Api } from '../services/v1'
import { API_BASE } from '../config/api'
import { useIntentStore } from '../stores/intentStore'

const generationStore = useGenerationStore()
const intentStore = useIntentStore()
intentStore.initialize()
const generationMode = ref('')

onMounted(() => {
  if (typeof window !== 'undefined') {
    generationMode.value = window.localStorage.getItem(`fuww_s2_generation_mode:${intentStore.sessionId}`) || ''
  }
})

const DEMO_COURSE_ID = 'demo_course_s3'
const DEMO_TOTAL_PAGES = 3

const courseIdInput = ref('')
const courseId = ref('')
const courseName = ref('')
const editPage = ref(1)
const totalPages = ref(1)
const loading = ref(false)

const previewUrl = computed(() => {
  if (!courseId.value) return ''
  return `${API_BASE}/api/courseware/${courseId.value}/page/${editPage.value}`
})

async function loadCourseContext() {
  const id = courseIdInput.value.trim()
  if (!id) {
    loadDemoMode()
    return
  }
  loading.value = true
  courseId.value = id
  courseName.value = `课件 ${id}`
  editPage.value = 1
  totalPages.value = 1

  // Fetch course detail to get total pages
  try {
    const resp = await teacherV1Api.coursewares.list()
    const list = resp?.data?.list || resp?.data || []
    console.log('[S3] course list:', list.length, 'items, looking for id:', id)
    const course = list.find(c => String(c.id) === id || c.course_id === id)
    console.log('[S3] matched course:', course)
    if (course && course.total_page > 0) {
      totalPages.value = course.total_page
      console.log('[S3] totalPages set to:', course.total_page)
    } else {
      console.warn('[S3] course not found in list or total_page=0')
    }
  } catch (e) {
    console.error('[S3] load course list failed:', e)
  }

  loadScriptAndNodes().finally(() => {
    loading.value = false
  })
}

function loadDemoMode() {
  courseId.value = DEMO_COURSE_ID
  courseName.value = '演示课件'
  editPage.value = 1
  totalPages.value = DEMO_TOTAL_PAGES
  const nodes = buildDemoNodes(1)
  generationStore.setNodes(nodes)
  generationStore.setScript(nodes.map(n => n.scriptText).join('\n\n'))
}

async function loadScriptAndNodes() {
  if (!courseId.value) return
  try {
    const scriptResp = await teacherV1Api.coursewares.getScript(courseId.value, editPage.value)
    const payload = scriptResp?.data || {}
    generationStore.setScript(payload.content || '')
    if (Array.isArray(payload.nodes) && payload.nodes.length > 0) {
      generationStore.setNodes(normalizeNodes(payload.nodes, editPage.value))
      return
    }
    const nodesResp = await teacherV1Api.coursewares.getNodes(courseId.value, editPage.value)
    const nodes = nodesResp?.data?.nodes || []
    generationStore.setNodes(normalizeNodes(nodes, editPage.value))
  } catch {
    const nodes = buildDemoNodes(editPage.value)
    generationStore.setNodes(nodes)
  }
}

async function handleGenerateAIScript() {
  if (!courseId.value) return
  generationStore.setGenerating(true)
  generationStore.setGenerateProgress(8, '正在分析课件内容')
  try {
    // 尝试从 localStorage 读取证据包（S2 证据透传）
    let evidence = null
    try {
      const raw = window.localStorage.getItem('fuww_s2_evidence_packet')
      if (raw) {
        evidence = JSON.parse(raw)
        console.log('[S3StudioPage] 从 localStorage 读取证据包:', evidence)
      }
    } catch (e) {
      console.warn('[S3StudioPage] 读取证据包失败', e)
    }

    generationStore.setGenerateProgress(30, '正在调用 AI 生成讲稿')
    const resp = await teacherV1Api.coursewares.generateScript({
      courseId: courseId.value,
      pageNum: editPage.value,
      evidence
    })
    generationStore.setGenerateProgress(80, '正在加载讲稿')

    // 重新从后端拉取刚生成的讲稿与节点
    const payload = resp?.data || resp || {}
    if (payload.content) {
      generationStore.setScript(payload.content)
    }
    await loadScriptAndNodes()

    generationStore.setGenerateProgress(100, '生成完成')
  } catch (err) {
    console.warn('生成讲稿失败', err)
  } finally {
    setTimeout(() => {
      generationStore.setGenerating(false)
    }, 650)
  }
}

async function handleGenerateAudio() {
  if (!courseId.value) return
  generationStore.setAudioGenerating(true)
  try {
    await teacherV1Api.coursewares.generateAudio({
      courseId: courseId.value,
      pageNum: editPage.value
    })
  } catch (err) {
    console.warn('生成音频失败', err)
  } finally {
    generationStore.setAudioGenerating(false)
  }
}

async function handleSaveScript() {
  if (!courseId.value) return
  generationStore.setSaving(true)
  try {
    await teacherV1Api.coursewares.saveNodes({
      courseId: courseId.value,
      pageNum: editPage.value,
      nodes: generationStore.currentScriptNodes
    })
    await teacherV1Api.coursewares.saveScript({
      courseId: courseId.value,
      pageNum: editPage.value,
      content: generationStore.currentScript
    })
    alert('讲稿保存成功！')
  } catch {
    alert('后端保存不可用，已使用前端模拟保存。')
  } finally {
    generationStore.setSaving(false)
  }
}

function normalizeNodes(nodes, page) {
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
    {
      id: '', nodeId: `p${page}_n1`, title: `节点1：第${page}页导入`, summary: '明确本页学习目标',
      scriptText: `同学们好，我们先快速回顾上页内容，再进入第${page}页核心目标。`,
      reteachScript: '', transitionText: '', estimatedDuration: 26, sortOrder: 1
    },
    {
      id: '', nodeId: `p${page}_n2`, title: '节点2：核心讲解', summary: '讲解关键方法与思路',
      scriptText: '本节点重点讲清方法步骤，并配套一题课堂演示。',
      reteachScript: '', transitionText: '', estimatedDuration: 34, sortOrder: 2
    },
    {
      id: '', nodeId: `p${page}_n3`, title: '节点3：总结与练习', summary: '通过练习巩固并总结',
      scriptText: '最后用两道快问快答巩固本页内容，并总结常见易错点。',
      reteachScript: '', transitionText: '', estimatedDuration: 28, sortOrder: 3
    }
  ]
}
</script>

<style scoped>
.s3-page {
  display: flex;
  flex-direction: column;
  padding: 20px;
  min-height: calc(100vh - 140px);
  overflow: hidden;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0;
  font-size: 22px;
  color: #111827;
}
.page-header p {
  margin: 6px 0 0;
  font-size: 14px;
  color: #607a71;
}
.page-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.page-body {
  flex: 1;
}
.evidence-warning {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin: 0 0 16px;
  padding: 13px 16px;
  border: 1px solid #f0d5a8;
  border-radius: 12px;
  background: #fffaf0;
  color: #7c4a15;
}
.evidence-warning div {
  display: flex;
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}
.evidence-warning strong {
  flex-shrink: 0;
  font-size: 13px;
}
.evidence-warning span {
  font-size: 12px;
  line-height: 1.55;
  color: #8a6337;
}
.evidence-warning a {
  flex-shrink: 0;
  color: #2f605a;
  font-size: 12px;
  font-weight: 700;
  text-decoration: none;
}
.step-pills {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.pill {
  font-size: 12px;
  font-weight: 600;
  color: #5f7467;
  background: #f0f5f2;
  border: 1px solid #e2ece6;
  border-radius: 999px;
  padding: 6px 14px;
  text-decoration: none;
  transition: all 0.15s;
}
.pill:hover {
  border-color: #5ca68f;
  color: #2f605a;
}
.pill.active {
  color: #fff;
  background: #2f605a;
  border-color: #2f605a;
}
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
  transition: background 0.15s;
}
.next-step-btn:hover {
  background: #1e4a44;
}

/* 工具栏 */
.s3-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 10px 14px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
  flex-wrap: wrap;
}
.s3-toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.s3-toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.toolbar-label {
  font-size: 13px;
  font-weight: 600;
  color: #2f605a;
  white-space: nowrap;
}
.s3-course-id-input {
  padding: 6px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 13px;
  width: 200px;
  outline: none;
  background: #fff;
}
.s3-course-id-input:focus {
  border-color: #5ca68f;
  box-shadow: 0 0 0 3px rgba(92, 166, 143, 0.12);
}
.page-indicator {
  font-size: 13px;
  color: #607a71;
  margin-right: 4px;
}
.page-indicator strong {
  color: #2f605a;
}

/* 欢迎卡片 */
.s3-welcome {
  display: flex;
  justify-content: center;
  padding: 60px 20px;
}
.welcome-card {
  max-width: 480px;
  text-align: center;
  padding: 40px 32px;
  background: #fff;
  border: 1px solid #dbe6df;
  border-radius: 20px;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
}
.welcome-card h3 {
  margin: 0 0 12px;
  font-size: 18px;
  color: #1e293b;
}
.welcome-card p {
  margin: 0 0 8px;
  font-size: 14px;
  color: #607a71;
  line-height: 1.6;
}
.welcome-hint {
  font-size: 12px;
  color: #94a3b8;
}
.welcome-card .btn-primary {
  margin-top: 16px;
}

/* 通用按钮 */
.btn {
  padding: 6px 14px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
}
.btn-sm {
  background: #edf5f2;
  color: #2d5f58;
  border: 1px solid #c6ded6;
}
.btn-sm:hover {
  background: #d6ece3;
}
.btn-primary {
  padding: 10px 24px;
  background: #2f605a;
  color: #fff;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
}
.btn-primary:hover {
  background: #1e4a44;
}
.btn-icon-round {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid #d5e3dc;
  background: #fff;
  color: #2f605a;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}
.btn-icon-round:hover:not(:disabled) {
  background: #edf5f2;
  border-color: #5ca68f;
}
.btn-icon-round:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

@media (max-width: 760px) {
  .page-header {
    flex-direction: column;
  }
  .evidence-warning,
  .evidence-warning div {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
