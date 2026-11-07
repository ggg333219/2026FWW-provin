<template>
  <AppShell>
    <div class="s4-page">
      <header class="page-head">
        <div class="page-head__text">
          <p class="page-head__eyebrow">课件生成流程</p>
          <h1 class="page-head__title">S4 版本管理</h1>
          <p class="page-head__desc">课件版本控制、修改指令与导出管理</p>
        </div>
      </header>
      <StepNav
        current="s4"
        :project-id="projectStore.projectId"
        :overrides="{ s3: { name: 'S3Studio', query: { project_id: route.query.project_id, generation_id: genIdInput } } }"
      />
      <div class="page-body">
        <!-- 工具栏 -->
        <div class="toolbar">
          <input
            v-model="genIdInput"
            type="text"
            placeholder="Generation ID（项目版本可自动加载）"
            class="gen-id-input"
            @keyup.enter="loadData"
          />
          <button class="btn btn-primary" :disabled="versionStore.loading" @click="loadData">
            {{ versionStore.loading ? '加载中...' : '加载版本' }}
          </button>
        </div>

        <!-- 错误提示 -->
        <div v-if="versionStore.error" class="error-banner">
          {{ versionStore.error }}
          <button class="btn-text" @click="versionStore.error = ''">×</button>
        </div>
        <div v-if="versionStore.isCurrentLocked" class="locked-banner"><span>🔒 当前版本已锁定，只能查看、对比和导出。</span><button class="btn btn-sm" @click="handleContinueFromLocked">基于此版本继续创建</button></div>

        <div class="s4-layout">
          <!-- 版本历史 -->
          <section class="s4-versions">
            <div class="section-card">
              <h3>版本历史 ({{ versionStore.versionCount }})</h3>
              <div v-if="versionStore.loading" class="empty-tip">加载中...</div>
              <div v-else-if="versionStore.versions.length === 0" class="empty-tip">
                当前项目还没有版本，请先在 S3 保存新版本
              </div>
              <div v-else class="version-list">
                <div
                  v-for="v in versionStore.versions"
                  :key="v.id"
                  class="version-item"
                  :class="{ locked: v.locked, selected: versionStore.currentVersionDetail?.version === v.version }"
                  @click="loadSelectedVersion(v.version)"
                >
                  <div class="version-main">
                    <strong>v{{ v.version }}</strong>
                    <span class="version-summary">{{ v.summary || v.title }}</span>
                  </div>
                  <div class="version-meta">
                    <small>{{ formatTime(v.createdAt) }}</small>
                    <span v-if="v.locked" class="lock-badge">🔒 已锁定</span>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- 操作面板 -->
          <section class="s4-actions">
            <div class="section-card">
              <h3>版本操作</h3>
              <div v-if="!versionStore.genId && !versionStore.projectId" class="empty-tip">请先加载版本</div>
              <div v-else class="action-group">
                <!-- 回滚 -->
                <div class="action-row">
                  <label>选择分叉起点:</label>
                  <select v-model="rollbackTarget" class="action-select">
                    <option :value="null" disabled>选择目标版本</option>
                    <option v-for="v in versionStore.versions" :key="v.id" :value="v.version">
                      v{{ v.version }} — {{ v.summary || v.title }}
                    </option>
                  </select>
                  <button
                    class="btn btn-sm"
                    :disabled="!rollbackTarget || versionStore.loading"
                    @click="handleRollback"
                  >
                    基于此版本新建版本
                  </button>
                </div>

                <!-- 锁定 -->
                <div v-if="projectStore.projectId && versionStore.currentVersionDetail" class="action-row fork-outline-row">
                  <button class="btn btn-sm btn-primary" :disabled="versionStore.loading" @click="handleContinueFromLocked">
                    基于当前版本编辑大纲
                  </button>
                  <span class="action-help">复制当前版本为新草稿，不重新生成整份大纲</span>
                </div>

                <div v-if="!projectStore.projectId" class="action-row">
                  <button
                    class="btn btn-sm btn-warn"
                    :disabled="versionStore.loading || versionStore.isCurrentLocked"
                    @click="handleLock"
                  >
                    🔒 锁定最新版本
                  </button>
                </div>

                <!-- 修改指令 -->
                <div v-if="!projectStore.projectId" class="action-divider"></div>
                <h4 v-if="!projectStore.projectId">修改指令</h4>
                <div v-if="!projectStore.projectId" class="action-row">
                  <select v-model="changeType" class="action-select" :disabled="versionStore.isCurrentLocked">
                    <option value="update_node">更新节点</option>
                    <option value="add_node">新增节点</option>
                    <option value="delete_node">删除节点</option>
                    <option value="swap_nodes">交换节点</option>
                    <option value="change_template">切换模板</option>
                  </select>
                  <input v-model="changeTarget" type="text" placeholder="目标节点ID" class="action-input" :disabled="versionStore.isCurrentLocked" />
                  <button class="btn btn-sm" :disabled="versionStore.isCurrentLocked" @click="handleAddChange">添加</button>
                </div>

                <!-- 待处理列表 -->
                <div v-if="!projectStore.projectId && versionStore.pendingChanges.length > 0" class="change-mini-list">
                  <div v-for="c in versionStore.pendingChanges" :key="c.id" class="change-mini-row">
                    <span class="change-type-badge">{{ c.type }}</span>
                    <span class="change-target">{{ c.target }}</span>
                    <span class="change-status-badge" :class="c.status">{{ c.status }}</span>
                    <button
                      v-if="c.status === 'pending'"
                      class="btn-icon"
                      title="应用"
                      @click="versionStore.applyChange(c.id)"
                    >✓</button>
                    <button
                      v-if="c.status === 'pending'"
                      class="btn-icon"
                      title="拒绝"
                      @click="versionStore.rejectChange(c.id)"
                    >✗</button>
                  </div>
                  <button
                    v-if="versionStore.hasPendingChanges"
                    class="btn btn-sm btn-primary"
                    :disabled="versionStore.loading || versionStore.isCurrentLocked"
                    @click="handleSubmitModify"
                  >
                    提交修改到后端
                  </button>
                </div>
              </div>
            </div>
          </section>

          <!-- 导出中心 -->
          <section class="s4-export">
            <S4VersionExportCenter
              :gen-id="exportGenId"
              :export-status="versionStore.exportStatus"
              :export-format="versionStore.exportFormat"
              :export-download-url="versionStore.exportDownloadUrl"
              :export-files="versionStore.exportFiles"
              :export-error="versionStore.exportError"
              :export-quality-report="versionStore.exportQualityReport"
              :export-lesson-plan-source="versionStore.exportLessonPlanSource"
              :export-lesson-plan-fallback-reason="versionStore.exportLessonPlanFallbackReason"
              :export-lesson-plan-filled-sections="versionStore.exportLessonPlanFilledSections"
              :loading="versionStore.loading"
              :nodes="exportVersionNodes"
              :course-title="courseTitle"
              :version-label="currentVersionLabel"
              @start-export="handleStartExport"
              @reset-export="versionStore.resetExport()"
            />
          </section>
        </div>

        <section v-if="versionStore.versions.length >= 2" class="compare-card section-card">
          <div class="compare-head"><div><h3>版本对比</h3><p>对比内容、顺序、样式与证据引用的变化。</p></div><div class="compare-controls"><select v-model="compareLeft"><option v-for="v in versionStore.versions" :key="`l${v.id}`" :value="v.version">v{{ v.version }}</option></select><span>→</span><select v-model="compareRight"><option v-for="v in versionStore.versions" :key="`r${v.id}`" :value="v.version">v{{ v.version }}</option></select><button class="btn btn-primary" :disabled="compareLeft === compareRight || versionStore.comparing" @click="runCompare">{{ versionStore.comparing ? '对比中…' : '开始对比' }}</button></div></div>
          <div v-if="versionStore.comparison" class="diff-grid">
            <div class="diff-stat added"><strong>+{{ versionStore.comparison.added.length }}</strong><span>新增节点</span></div>
            <div class="diff-stat removed"><strong>-{{ versionStore.comparison.removed.length }}</strong><span>删除节点</span></div>
            <div class="diff-stat changed"><strong>{{ versionStore.comparison.changed.length }}</strong><span>修改节点</span></div>
            <div class="diff-list"><article v-for="item in versionStore.comparison.changed" :key="item.node_id"><b>{{ item.title }}</b><span>{{ changeLabels(item.changes).join('、') }}</span></article><p v-if="!versionStore.comparison.changed.length">两个版本没有节点内容差异。</p></div>
          </div>
        </section>

        <!-- 当前版本详情 -->
        <div v-if="versionStore.currentVersionDetail" class="version-detail">
          <h3>版本详情 — v{{ versionStore.currentVersionDetail.version }}</h3>
          <p class="detail-summary">{{ versionStore.currentVersionDetail.summary }}</p>
          <div class="node-preview-grid">
            <div
              v-for="node in (versionStore.currentVersionDetail.nodes || []).slice(0, 6)"
              :key="node.node_id"
              class="node-preview-card"
            >
              <strong>{{ node.title || node.node_id }}</strong>
              <small v-if="node.node_type">{{ node.node_type }}</small>
              <p>{{ (node.summary || node.content || '').slice(0, 80) }}...</p>
            </div>
          </div>
        </div>

        <section v-if="versionStore.currentVersionDetail" class="evidence-trace section-card">
          <div class="trace-head"><div><h3>证据追溯</h3><p>当前版本共有 {{ evidenceTrace.length }} 个引用关系，按节点定位来源。</p></div><router-link :to="{ name: 'S3Studio', query: { project_id: route.query.project_id, generation_id: genIdInput } }">返回 S3 调整证据</router-link></div>
          <div v-if="!evidenceTrace.length" class="empty-tip">当前版本未记录证据引用</div>
          <div v-else class="trace-list"><article v-for="item in evidenceTrace" :key="`${item.nodeId}:${item.chunkId}`"><div><b>{{ item.nodeTitle }}</b><span>{{ item.chunkId }}</span></div><p>{{ item.source || '来源切片已绑定，可在资料与证据中心查看原文。' }}</p></article></div>
        </section>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useVersionStore } from '../stores/versionStore'
import { useGenerationStore } from '../stores/generationStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { useIntentStore } from '../stores/intentStore'
import { useCoursewareProjectStore } from '../stores/coursewareProjectStore'
import AppShell from '../components/layout/AppShell.vue'
import StepNav from '../components/common/StepNav.vue'
import S4VersionExportCenter from '../components/teacher/S4VersionExportCenter.vue'
import { writeResumeDraft } from '../utils/coursewareDraft'
import { withOutlineInteractivePlans } from '../utils/interactiveExport'
import { outlineFromVersion } from '../utils/versionOutline'
import { teacherV1Api } from '../services/v1'

const versionStore = useVersionStore()
const generationStore = useGenerationStore()
const workspaceStore = useWorkspaceStore()
const intentStore = useIntentStore()
const projectStore = useCoursewareProjectStore()

const route = useRoute()
const router = useRouter()

const genIdInput = ref(
  route.query.project_id
    ? ''
    : String(route.query.generation_id || route.query.genId || generationStore.lastGenId || generationStore.restoreLastGenId() || workspaceStore.currentCourseId || '')
)

// 路由参数变化时自动加载版本（S3 一键生成后带 genId 跳转过来）
watch(() => route.query.generation_id || route.query.genId, (id) => {
  if (id && typeof id === 'string') {
    genIdInput.value = id
    if (!route.query.project_id) loadData()
  }
}, { immediate: true })
watch(() => route.query.project_id, async (id) => {
  if (!id || typeof id !== 'string') return
  projectStore.setActive(id)
  const context = await projectStore.resume(id).catch(() => null)
  genIdInput.value = String(context?.project?.gen_id || '')
  projectStore.updateStep('s4_version').catch(() => {})
  await loadData()
}, { immediate: true })
onMounted(() => {
  if (!route.query.project_id && !(route.query.generation_id || route.query.genId) && genIdInput.value) loadData()
})
const courseTitle = computed(() => projectStore.project?.title || intentStore.intentSummary?.topic || '未命名课件')
const exportGenId = computed(() => versionStore.genId || (projectStore.projectId && versionStore.currentVersionDetail ? projectStore.projectId : ''))
const exportVersionNodes = computed(() => {
  const nodes = withOutlineInteractivePlans(
    versionStore.currentVersionDetail?.nodes || [],
    versionStore.currentVersionDetail?.outline?.nodes || [],
  )
  const presentation = versionStore.currentVersionDetail?.presentation || {}
  if (!nodes.length || !Object.keys(presentation).length) return nodes
  // Keep old Go gateways compatible: they already forward node metadata even
  // when they do not yet understand the separate presentation request field.
  const first = nodes[0]
  return [{
    ...first,
    metadata: {
      ...(first.metadata || {}),
      presentation: { ...(first.metadata?.presentation || {}), ...presentation },
    },
  }, ...nodes.slice(1)]
})
const currentVersionLabel = computed(() => `v${versionStore.currentVersionDetail?.version || versionStore.versions?.[0]?.version || 1}`)
const rollbackTarget = ref(null)
const changeType = ref('update_node')
const changeTarget = ref('')
const compareLeft = ref(null)
const compareRight = ref(null)
const evidenceTrace = computed(() => {
  const nodes = versionStore.currentVersionDetail?.nodes || []
  const packet = projectStore.draft?.evidence_packet || null
  const sourceMap = new Map([
    ...(packet?.citations || []),
    ...(packet?.relevant_chunks || []),
  ].map((item) => [item.chunk_id, item.text_snippet || item.content || item.source_ref || '']))
  return nodes.flatMap((node) => [...new Set([...(node.citation_refs || []), ...(node.source_chunk_ids || [])])].map((chunkId) => ({
    nodeId: node.node_id,
    nodeTitle: node.title || node.node_id,
    chunkId,
    source: sourceMap.get(chunkId) || '',
  })))
})

async function loadData() {
  const id = genIdInput.value.trim()
  const projectId = String(route.query.project_id || projectStore.projectId || '')
  if (!id && !projectId) return
  versionStore.genId = id
  if (projectId) await versionStore.loadProjectVersions(projectId)
  else await versionStore.loadVersions(id)
  if (versionStore.versions.length > 0) {
    if (projectId) await versionStore.loadProjectVersion(projectId)
    else await versionStore.loadVersion(id)
    compareRight.value = versionStore.versions[0]?.version || null
    compareLeft.value = versionStore.versions[1]?.version || null
  }
}

async function loadSelectedVersion(version) {
  if (projectStore.projectId) await versionStore.loadProjectVersion(projectStore.projectId, version)
  else await versionStore.loadVersion(versionStore.genId, version)
}
async function runCompare() {
  if (projectStore.projectId) await versionStore.compareProjectVersions(projectStore.projectId, compareLeft.value, compareRight.value)
  else await versionStore.compareVersions(versionStore.genId, compareLeft.value, compareRight.value)
}
function changeLabels(changes = []) {
  const labels = { title: '标题', summary: '摘要', content: '正文', script: '讲稿', node_type: '节点类型', citation_refs: '证据引用', source_chunk_ids: '来源切片', layout_hint: '版式', font_size_hint: '字号', slide_background: '配色', metadata: '样式/互动元数据', order: '顺序' }
  return changes.map((item) => labels[item] || item)
}

async function handleRollback() {
  if (!rollbackTarget.value || (!versionStore.genId && !projectStore.projectId)) return
  try {
    const targetVersion = Number(rollbackTarget.value)
    const targetDetail = projectStore.projectId
      ? await versionStore.loadProjectVersion(projectStore.projectId, targetVersion)
      : await versionStore.loadVersion(versionStore.genId, targetVersion)
    const result = projectStore.projectId
      ? await versionStore.rollbackProject(projectStore.projectId, targetVersion)
      : await versionStore.rollbackTo(versionStore.genId, targetVersion)
    const data = result?.data || result || {}
    const newVersion = Number(data.new_draft_version_no || data.current_version || data.new_version_no || versionStore.currentVersionDetail?.version || targetVersion + 1)
    generationStore.setLastGenId(versionStore.genId)
    const nodes = data.nodes || targetDetail?.nodes || []
    generationStore.setNodes(nodes)
    await persistRollbackDraft({
      nodes,
      outline: targetDetail?.outline,
      pageBindings: data.page_bindings || targetDetail?.pageBindings || [],
      presentation: data.presentation || targetDetail?.presentation || {},
      generationInstructionSet: targetDetail?.generationInstructionSet || {},
    })
    await projectStore.updateStep('s3_studio').catch(() => {})
    rollbackTarget.value = null
    await router.push({ name: 'S3Studio', query: { project_id: projectStore.projectId, generation_id: versionStore.genId, base_version: newVersion, from_rollback_version: targetVersion, phase: 'outline' } })
  } catch (error) {
    versionStore.error = error?.message || '基于所选版本创建分支失败'
  }
}

async function handleLock() {
  if (!versionStore.genId) return
  try {
    await versionStore.lockVersion(versionStore.genId)
  } catch {
    // 错误已在 store 中设置
  }
}

function handleAddChange() {
  if (versionStore.isCurrentLocked) return
  if (!changeTarget.value.trim()) return
  versionStore.addChange({
    type: changeType.value,
    target: changeTarget.value.trim()
  })
  changeTarget.value = ''
}

async function handleSubmitModify() {
  if (!versionStore.genId || versionStore.isCurrentLocked) return
  try {
    await versionStore.submitModify(versionStore.genId)
  } catch { /* 错误已在 store */ }
}

function handleStartExport(format) {
  if (!exportGenId.value) return
  versionStore.startExport(
    exportGenId.value,
    format,
    versionStore.currentVersionDetail?.version || null,
    courseTitle.value,
    exportVersionNodes.value,
    projectStore.projectId,
    versionStore.currentVersionDetail?.generationInstructionSet || projectStore.draft?.generation_instruction_set || {},
    versionStore.currentVersionDetail?.presentation || {},
  )
}

async function handleContinueFromLocked() {
  const version = versionStore.currentVersionDetail?.version
  if (!version || (!versionStore.genId && !projectStore.projectId)) return
  try {
    // rollbackProject 会刷新 currentVersionDetail；先固定教师选中的版本。
    const selected = versionStore.currentVersionDetail
    const result = projectStore.projectId
      ? await versionStore.rollbackProject(projectStore.projectId, version)
      : await versionStore.rollbackTo(versionStore.genId, version)
    const data = result?.data || result || {}
    const newVersion = Number(data.new_draft_version_no || data.current_version || data.new_version_no || version + 1)
    generationStore.setLastGenId(versionStore.genId)
    const restoredNodes = data.nodes || selected.nodes || []
    generationStore.setNodes(restoredNodes)
    await persistRollbackDraft({
      nodes: restoredNodes,
      outline: selected.outline,
      pageBindings: data.page_bindings || selected.pageBindings || [],
      presentation: data.presentation || selected.presentation || {},
      generationInstructionSet: selected.generationInstructionSet || {},
    })
    await projectStore.updateStep('s3_studio').catch(() => {})
    await router.push({ name: 'S3Studio', query: { project_id: projectStore.projectId, generation_id: versionStore.genId, base_version: newVersion, from_rollback_version: version, editable_outline: '1', phase: 'outline' } })
  } catch (error) {
    versionStore.error = error?.message || '基于当前版本创建分支失败'
  }
}

async function persistRollbackDraft({ nodes, outline, pageBindings, presentation, generationInstructionSet }) {
  if (!projectStore.projectId) return
  const source = outlineFromVersion(outline, nodes, courseTitle.value)
  if (!source.nodes.length) throw new Error('所选版本没有可复用的大纲或内容节点，无法创建编辑分支')
  const response = await teacherV1Api.outline.createFromNodes({
    session_id: source.session_id || intentStore.sessionId || projectStore.projectId,
    intent_id: source.intent_id || intentStore.intentId || '',
    course_name: source.title,
    nodes: source.nodes,
  })
  const created = response?.data || response || {}
  if (!created.outline_id) throw new Error('从版本快照建立大纲草稿失败')
  const current = projectStore.draft && typeof projectStore.draft === 'object' ? projectStore.draft : {}
  const restored = {
    ...current,
    outline: {
      ...source,
      ...created,
      status: 'draft',
      confirmed_at: null,
      editable_after_rollback: true,
    },
    generation: {
      ...(current.generation || {}),
      generation_id: versionStore.genId || generationStore.lastGenId || '',
      nodes: nodes || [],
    },
    // 删除记录只属于上一份正在编辑的草稿，不能带到新选中的历史版本。
    deleted_outline_node_ids: [],
    needs_version_save: false,
    page_bindings: pageBindings || [],
    presentation: presentation || current.presentation || {},
    generation_instruction_set: generationInstructionSet || current.generation_instruction_set || {},
  }
  await projectStore.saveNow(restored)
  writeResumeDraft(String(route.query.project_id || projectStore.projectId || ''), restored)
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN')
}
</script>

<style scoped>
.s4-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: 100%;
  max-width: 100%;
  padding: var(--space-6);
  min-height: calc(100dvh - var(--topbar-height) - var(--shell-gutter) * 2);
  background: var(--bg-page);
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-5);
}
.page-head__eyebrow {
  margin: 0 0 var(--space-1);
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  letter-spacing: 0.06em;
  color: var(--color-primary);
}
.page-head__title {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: var(--weight-semibold);
  line-height: var(--leading-tight);
  color: var(--text-primary);
}
.page-head__desc {
  margin: var(--space-1) 0 0;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.page-body { flex: 1; }

/* 工具栏 */
.toolbar { display: flex; gap: var(--space-2); align-items: center; }
.gen-id-input {
  flex: 1;
  max-width: 360px;
  min-height: 38px;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  background: var(--bg-surface);
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-standard),
              box-shadow var(--duration-fast) var(--ease-standard);
}
.gen-id-input::placeholder { color: var(--text-disabled); }
.gen-id-input:focus { border-color: var(--color-primary); box-shadow: var(--shadow-focus); }

/* 反馈条 */
.error-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-control);
  background: var(--color-danger-soft);
  color: var(--color-danger);
  font-size: var(--text-xs);
}
.locked-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-control);
  background: var(--color-warning-soft);
  color: var(--color-warning);
  font-size: var(--text-xs);
}

/* 按钮 */
.btn {
  min-height: 36px;
  padding: 0 var(--space-4);
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  cursor: pointer;
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  transition: background var(--duration-fast) var(--ease-standard),
              border-color var(--duration-fast) var(--ease-standard);
}
.btn:disabled { opacity: 0.48; cursor: not-allowed; }
.btn-primary { background: var(--color-primary); color: var(--color-on-primary); }
.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover); }
.btn-sm {
  min-height: 30px;
  padding: 0 var(--space-3);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  border-color: var(--color-primary-border);
  border-radius: var(--radius-control);
  font-size: var(--text-2xs);
}
.btn-sm:hover:not(:disabled) { background: var(--brand-100); }
.btn-warn { background: var(--color-warning-soft); color: var(--color-warning); border-color: var(--color-warning-border); }
.btn-warn:hover:not(:disabled) { filter: brightness(0.97); }
.btn-text { background: none; border: none; cursor: pointer; font-size: var(--text-md); color: var(--text-tertiary); padding: 0 var(--space-1); }
.btn-text:hover { color: var(--text-primary); }
.btn-icon { background: none; border: none; cursor: pointer; font-size: var(--text-xs); padding: 2px var(--space-2); border-radius: var(--radius-control); color: var(--text-secondary); }
.btn-icon:hover { background: var(--bg-subtle); }

/* 三栏布局 */
.s4-layout {
  display: grid;
  grid-template-columns: minmax(180px, .8fr) minmax(0, 1.25fr) minmax(240px, .9fr);
  gap: var(--space-4);
  align-items: start;
}
.s4-layout > section { min-width: 0; }

/* 卡片 */
.section-card {
  padding: var(--space-4);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-xs);
}
.section-card h3 { margin: 0 0 var(--space-3); font-size: var(--text-md); font-weight: var(--weight-semibold); color: var(--text-primary); }
.section-card h4 { margin: var(--space-4) 0 var(--space-2); font-size: var(--text-sm); color: var(--text-secondary); }
.empty-tip { padding: var(--space-10) 0; text-align: center; font-size: var(--text-xs); color: var(--text-tertiary); }

/* 版本列表 */
.version-list { display: flex; flex-direction: column; gap: var(--space-2); max-height: 320px; overflow-y: auto; }
.version-item {
  padding: var(--space-3);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  cursor: pointer;
  transition: border-color var(--duration-fast) var(--ease-standard),
              background var(--duration-fast) var(--ease-standard);
}
.version-item:hover { border-color: var(--border-default); }
.version-item.selected { border-color: var(--color-primary-border); background: var(--color-primary-soft); }
.version-item.locked { border-left: 3px solid var(--color-warning); background: var(--color-warning-soft); }
.version-main { display: flex; align-items: center; gap: var(--space-3); }
.version-main strong { min-width: 36px; font-size: var(--text-sm); color: var(--color-primary); }
.version-summary { font-size: var(--text-xs); color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.version-meta { display: flex; justify-content: space-between; align-items: center; margin-top: var(--space-1); }
.version-meta small { font-size: var(--text-2xs); color: var(--text-tertiary); }
.lock-badge { padding: 2px var(--space-2); border-radius: var(--radius-pill); background: var(--color-warning-soft); color: var(--color-warning); font-size: var(--text-2xs); }

/* 操作面板 */
.action-group { display: flex; flex-direction: column; gap: var(--space-3); }
.action-row { display: flex; gap: var(--space-2); align-items: center; min-width: 0; flex-wrap: wrap; }
.action-help { font-size: var(--text-2xs); line-height: var(--leading-relaxed); color: var(--text-tertiary); }
.action-row label { font-size: var(--text-2xs); color: var(--text-secondary); min-width: 80px; }
.action-select, .action-input {
  min-height: 34px;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-control);
  background: var(--bg-surface);
  font-size: var(--text-2xs);
}
.action-select:focus, .action-input:focus { outline: none; border-color: var(--color-primary); box-shadow: var(--shadow-focus); }
.action-select { flex: 1 1 160px; min-width: 0; max-width: 100%; }
.action-input { flex: 2 1 180px; min-width: 0; max-width: 100%; }
.action-divider { height: 1px; margin: var(--space-2) 0; background: var(--border-subtle); }

/* 修改指令迷你列表 */
.change-mini-list { display: flex; flex-direction: column; gap: var(--space-1); max-height: 200px; overflow-y: auto; }
.change-mini-row { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-1) var(--space-2); border-radius: var(--radius-control); background: var(--bg-subtle); font-size: var(--text-2xs); }
.change-type-badge { padding: 1px var(--space-2); border-radius: var(--radius-pill); background: var(--color-primary-soft); color: var(--color-primary); white-space: nowrap; font-size: var(--text-2xs); }
.change-target { flex: 1; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.change-status-badge { padding: 1px var(--space-2); border-radius: var(--radius-pill); font-size: var(--text-2xs); white-space: nowrap; }
.change-status-badge.pending { background: var(--color-warning-soft); color: var(--color-warning); }
.change-status-badge.applied { background: var(--color-success-soft); color: var(--color-success); }
.change-status-badge.rejected { background: var(--color-danger-soft); color: var(--color-danger); }

/* 版本详情 */
.version-detail { margin-top: var(--space-5); }
.version-detail h3 { margin: 0 0 var(--space-2); font-size: var(--text-md); color: var(--text-primary); }
.detail-summary { margin: 0 0 var(--space-3); font-size: var(--text-xs); color: var(--text-secondary); }
.node-preview-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-3); }
.node-preview-card {
  padding: var(--space-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-xs);
}
.node-preview-card strong { display: block; margin-bottom: 2px; font-size: var(--text-2xs); color: var(--text-primary); }
.node-preview-card small { font-size: var(--text-2xs); color: var(--text-tertiary); text-transform: uppercase; }
.node-preview-card p { margin: var(--space-2) 0 0; font-size: var(--text-2xs); line-height: var(--leading-relaxed); color: var(--text-secondary); }

/* 对比与证据溯源 */
.compare-card, .evidence-trace { margin-top: var(--space-5); }
.compare-head, .trace-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-5); }
.compare-head h3, .trace-head h3 { margin: 0; font-size: var(--text-md); color: var(--text-primary); }
.compare-head p, .trace-head p { margin: var(--space-1) 0 0; font-size: var(--text-2xs); color: var(--text-tertiary); }
.compare-controls { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.compare-controls select { min-height: 34px; padding: var(--space-2) var(--space-3); border: 1px solid var(--border-default); border-radius: var(--radius-control); background: var(--bg-surface); font-size: var(--text-2xs); }
.diff-grid { display: grid; grid-template-columns: repeat(3, 140px) 1fr; gap: var(--space-3); margin-top: var(--space-4); }
.diff-stat { display: grid; place-content: center; min-height: 90px; text-align: center; border-radius: var(--radius-md); background: var(--bg-subtle); }
.diff-stat strong { font-size: var(--text-2xl); font-variant-numeric: tabular-nums; }
.diff-stat span { font-size: var(--text-2xs); color: var(--text-tertiary); }
.diff-stat.added strong { color: var(--color-success); }
.diff-stat.removed strong { color: var(--color-danger); }
.diff-stat.changed strong { color: var(--color-warning); }
.diff-list { max-height: 180px; overflow: auto; padding: var(--space-2); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); }
.diff-list article { display: flex; justify-content: space-between; gap: var(--space-3); padding: var(--space-2); border-bottom: 1px solid var(--border-subtle); font-size: var(--text-2xs); }
.diff-list article:last-child { border-bottom: 0; }
.diff-list span { color: var(--color-warning); }
.trace-head a { font-size: var(--text-2xs); color: var(--color-primary); text-decoration: none; }
.trace-head a:hover { text-decoration: underline; }
.trace-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--space-3); margin-top: var(--space-4); }
.trace-list article { padding: var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); background: var(--bg-surface); }
.trace-list article div { display: flex; justify-content: space-between; gap: var(--space-2); }
.trace-list b { font-size: var(--text-2xs); color: var(--text-primary); }
.trace-list span { font-size: var(--text-2xs); color: var(--color-primary); }
.trace-list p { margin: var(--space-2) 0 0; font-size: var(--text-2xs); line-height: var(--leading-relaxed); color: var(--text-secondary); }

/* 统一断点：1280 / 1024 / 768 */
@media (max-width: 1279px) {
  .s4-layout { grid-template-columns: 1fr; }
}
@media (max-width: 1023px) {
  .compare-head, .trace-head { flex-direction: column; }
  .diff-grid { grid-template-columns: repeat(3, 1fr); }
  .diff-list { grid-column: 1 / -1; }
}
@media (max-width: 767px) {
  .s4-page { padding: var(--space-4); gap: var(--space-3); }
  .toolbar { flex-direction: column; align-items: stretch; }
  .gen-id-input { max-width: none; }
  .diff-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
</style>
