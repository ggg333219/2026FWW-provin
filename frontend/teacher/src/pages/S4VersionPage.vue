<template>
  <AppShell>
    <div class="s4-page">
      <div class="page-header">
        <div>
          <h2>S4 版本管理</h2>
          <p>课件版本控制、修改指令与导出管理</p>
        </div>
        <div class="page-header-right">
          <div class="step-pills">
            <router-link :to="{ name: 'S1Intent', query: { project_id: projectStore.projectId } }" class="pill">S1 意图</router-link>
            <router-link :to="{ name: 'S2Material', query: { project_id: projectStore.projectId } }" class="pill">S2 资料</router-link>
            <router-link :to="{ name: 'S3Studio', query: { project_id: route.query.project_id, generation_id: genIdInput } }" class="pill">S3 生成</router-link>
            <span class="pill active">S4 版本</span>
            <router-link :to="{ name: 'Middle' }" class="pill back-pill">返回中间页</router-link>
          </div>
        </div>
      </div>
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
                <div class="action-row">
                  <button
                    class="btn btn-sm btn-warn"
                    :disabled="versionStore.loading || versionStore.isCurrentLocked"
                    @click="handleLock"
                  >
                    🔒 锁定最新版本
                  </button>
                </div>

                <!-- 修改指令 -->
                <div class="action-divider"></div>
                <h4>修改指令</h4>
                <div class="action-row">
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
                <div v-if="versionStore.pendingChanges.length > 0" class="change-mini-list">
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
              :gen-id="versionStore.genId"
              :export-status="versionStore.exportStatus"
              :export-format="versionStore.exportFormat"
              :export-download-url="versionStore.exportDownloadUrl"
              :export-files="versionStore.exportFiles"
              :export-error="versionStore.exportError"
              :loading="versionStore.loading"
              :intent="intentStore.intentSummary || {}"
              :nodes="versionStore.currentVersionDetail?.nodes || []"
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
import S4VersionExportCenter from '../components/teacher/S4VersionExportCenter.vue'

const versionStore = useVersionStore()
const generationStore = useGenerationStore()
const workspaceStore = useWorkspaceStore()
const intentStore = useIntentStore()
const projectStore = useCoursewareProjectStore()

const route = useRoute()
const router = useRouter()

const genIdInput = ref(
  generationStore.lastGenId ||
  generationStore.restoreLastGenId() ||
  workspaceStore.currentCourseId ||
  ''
)

// 路由参数变化时自动加载版本（S3 一键生成后带 genId 跳转过来）
watch(() => route.query.generation_id || route.query.genId, (id) => {
  if (id && typeof id === 'string') {
    genIdInput.value = id
    loadData()
  }
}, { immediate: true })
watch(() => route.query.project_id, async (id) => {
  if (!id || typeof id !== 'string') return
  projectStore.setActive(id)
  await projectStore.resume(id).catch(() => {})
  projectStore.updateStep('s4_version').catch(() => {})
  await loadData()
}, { immediate: true })
onMounted(() => {
  if (!(route.query.generation_id || route.query.genId) && genIdInput.value) loadData()
})
const courseTitle = computed(() => projectStore.project?.title || intentStore.intentSummary?.topic || '未命名课件')
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
  const projectId = projectStore.projectId || String(route.query.project_id || '')
  if (!id && !projectId) return
  if (id) versionStore.genId = id
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
    })
    await projectStore.updateStep('s3_studio').catch(() => {})
    rollbackTarget.value = null
    await router.push({ name: 'S3Studio', query: { project_id: projectStore.projectId, generation_id: versionStore.genId, base_version: newVersion, from_rollback_version: targetVersion, phase: 'outline' } })
  } catch {
    // 错误已在 store 中设置
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
  if (!versionStore.genId) return
  versionStore.startExport(versionStore.genId, format, versionStore.currentVersionDetail?.version || null, courseTitle.value)
}

async function handleContinueFromLocked() {
  const version = versionStore.currentVersionDetail?.version
  if (!version || (!versionStore.genId && !projectStore.projectId)) return
  const nodes = versionStore.currentVersionDetail?.nodes || []
  const result = projectStore.projectId
    ? await versionStore.rollbackProject(projectStore.projectId, version)
    : await versionStore.rollbackTo(versionStore.genId, version)
  const data = result?.data || result || {}
  const newVersion = Number(data.new_draft_version_no || data.current_version || data.new_version_no || version + 1)
  generationStore.setLastGenId(versionStore.genId)
  const restoredNodes = data.nodes || nodes
  generationStore.setNodes(restoredNodes)
  await persistRollbackDraft({
    nodes: restoredNodes,
    outline: versionStore.currentVersionDetail?.outline,
    pageBindings: data.page_bindings || versionStore.currentVersionDetail?.pageBindings || [],
    presentation: data.presentation || versionStore.currentVersionDetail?.presentation || {},
  })
  await projectStore.updateStep('s3_studio').catch(() => {})
  router.push({ name: 'S3Studio', query: { project_id: projectStore.projectId, generation_id: versionStore.genId, base_version: newVersion, from_rollback_version: version, phase: 'outline' } })
}

async function persistRollbackDraft({ nodes, outline, pageBindings, presentation }) {
  if (!projectStore.projectId) return
  const current = projectStore.draft && typeof projectStore.draft === 'object' ? projectStore.draft : {}
  const restored = {
    ...current,
    outline: outline && typeof outline === 'object' ? {
      ...outline,
      status: 'draft',
      confirmed_at: null,
      forked_from_version: Number(outline.outline_version || 0),
      editable_after_rollback: true,
    } : current.outline,
    generation: {
      ...(current.generation || {}),
      generation_id: versionStore.genId,
      nodes: nodes || [],
    },
    page_bindings: pageBindings || [],
    presentation: { ...(current.presentation || {}), ...(presentation || {}) },
  }
  await projectStore.saveNow(restored).catch(() => {})
  try {
    window.localStorage.setItem('fuww_courseware_resume_draft', JSON.stringify(restored))
  } catch {}
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
  padding: 20px;
  min-height: calc(100vh - 140px);
  background:
    radial-gradient(circle at 86% -15%, rgba(175, 221, 203, .2), transparent 30%),
    linear-gradient(180deg, #fcfefd 0%, #f7faf8 100%);
}
.page-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 22px; color: #111827; }
.page-header p { margin: 6px 0 0; font-size: 14px; color: #607a71; }
.page-header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.step-pills { display: flex; gap: 6px; flex-wrap: wrap; }
.pill { font-size: 12px; font-weight: 600; color: #5f7467; background: #f0f5f2; border: 1px solid #e2ece6; border-radius: 999px; padding: 6px 14px; text-decoration: none; transition: all 0.15s; }
.pill:hover { border-color: #5ca68f; color: #2f605a; }
.pill.active { color: #fff; background: #2f605a; border-color: #2f605a; }
.page-body { flex: 1; }

/* 工具栏 */
.toolbar { display: flex; gap: 10px; margin-bottom: 16px; align-items: center; }
.gen-id-input {
  flex: 1; max-width: 360px; padding: 8px 14px; border: 1px solid #cbd5e1;
  border-radius: 10px; font-size: 14px; outline: none; background: #fff;
}
.gen-id-input:focus { border-color: #5ca68f; box-shadow: 0 0 0 3px rgba(92,166,143,0.15); }

/* 错误横幅 */
.error-banner {
  background: #fef2f2; border: 1px solid #fecaca; color: #991b1b;
  padding: 10px 14px; border-radius: 10px; margin-bottom: 16px;
  display: flex; justify-content: space-between; align-items: center; font-size: 13px;
}
.locked-banner { display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px;padding:11px 14px;border:1px solid #f0d58a;border-radius:10px;background:#fff9e7;color:#815b0d;font-size:13px; }

/* 按钮 */
.btn {
  padding: 8px 18px; border: none; border-radius: 10px; cursor: pointer;
  font-size: 14px; font-weight: 500; transition: all 0.15s;
}
.btn-primary { background: #5ca68f; color: #fff; }
.btn-primary:hover { background: #4a8d78; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sm { padding: 6px 14px; font-size: 13px; background: #edf5f2; color: #2d5f58; border: 1px solid #c6ded6; border-radius: 8px; }
.btn-sm:hover { background: #d6ece3; }
.btn-warn { background: #fff7ed; color: #9a3412; border-color: #fed7aa; }
.btn-warn:hover { background: #ffedd5; }
.btn-text { background: none; border: none; cursor: pointer; font-size: 16px; color: #94a3b8; padding: 0 4px; }
.btn-icon { background: none; border: none; cursor: pointer; font-size: 14px; padding: 2px 6px; border-radius: 4px; color: #64748b; }
.btn-icon:hover { background: #f1f5f9; }

/* 三栏布局 */
.s4-layout { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 20px; }
@media (max-width: 1200px) {
  .s4-layout { grid-template-columns: 1fr; }
}

/* 卡片 */
.section-card {
  background: #fff; border: 1px solid #dbe6df; border-radius: 16px;
  padding: 16px; box-shadow: 0 4px 12px rgba(15,23,42,0.04);
}
.section-card h3 { margin: 0 0 12px; font-size: 16px; color: #2d5f58; }
.section-card h4 { margin: 14px 0 8px; font-size: 14px; color: #334155; }
.empty-tip { color: #94a3b8; text-align: center; padding: 40px 0; font-size: 14px; }

/* 版本列表 */
.version-list { display: flex; flex-direction: column; gap: 8px; max-height: 320px; overflow-y: auto; }
.version-item { padding: 10px; background: #f6faf8; border: 1px solid transparent; border-radius: 10px; cursor: pointer; }
.version-item.selected { border-color: #5ca68f; box-shadow: 0 0 0 2px rgba(92,166,143,.12); }
.version-item.locked { border-left: 3px solid #eab308; background: #fffdf0; }
.version-main { display: flex; align-items: center; gap: 10px; }
.version-main strong { color: #5ca68f; min-width: 36px; font-size: 14px; }
.version-summary { font-size: 14px; color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.version-meta { display: flex; justify-content: space-between; align-items: center; margin-top: 4px; }
.version-meta small { font-size: 12px; color: #94a3b8; }
.lock-badge { font-size: 11px; padding: 2px 6px; border-radius: 999px; background: #fef3c7; color: #92400e; }

/* 操作面板 */
.action-group { display: flex; flex-direction: column; gap: 10px; }
.action-row { display: flex; gap: 8px; align-items: center; }
.action-row label { font-size: 13px; color: #607a71; min-width: 80px; }
.action-select { padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; background: #fff; flex: 1; }
.action-input { padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; flex: 2; }
.action-divider { height: 1px; background: #e2e8f0; margin: 6px 0; }

/* 修改指令迷你列表 */
.change-mini-list { display: flex; flex-direction: column; gap: 4px; max-height: 200px; overflow-y: auto; }
.change-mini-row { display: flex; align-items: center; gap: 6px; padding: 5px 8px; background: #f8fafc; border-radius: 8px; font-size: 12px; }
.change-type-badge { font-size: 10px; padding: 1px 6px; border-radius: 999px; background: #edf5f2; color: #2f605a; white-space: nowrap; }
.change-target { flex: 1; color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.change-status-badge { font-size: 10px; padding: 1px 6px; border-radius: 999px; }
.change-status-badge.pending { background: #fef3c7; color: #92400e; }
.change-status-badge.applied { background: #d1fae5; color: #065f46; }
.change-status-badge.rejected { background: #fee2e2; color: #991b1b; }

/* 版本详情 */
.version-detail { margin-top: 20px; }
.version-detail h3 { color: #1e293b; font-size: 16px; margin: 0 0 8px; }
.detail-summary { color: #607a71; font-size: 14px; margin: 0 0 12px; }
.node-preview-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.node-preview-card {
  background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px;
  box-shadow: 0 2px 6px rgba(15,23,42,0.03);
}
.node-preview-card strong { display: block; font-size: 13px; color: #1e293b; margin-bottom: 2px; }
.node-preview-card small { font-size: 11px; color: #94a3b8; text-transform: uppercase; }
.node-preview-card p { font-size: 12px; color: #64748b; margin: 6px 0 0; line-height: 1.4; }
.compare-card,.evidence-trace{margin-top:20px}.compare-head,.trace-head{display:flex;justify-content:space-between;align-items:flex-start;gap:18px}.compare-head h3,.trace-head h3{margin:0;color:#2d5f58}.compare-head p,.trace-head p{margin:5px 0 0;color:#71847d;font-size:12px}.compare-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.compare-controls select{padding:7px 9px;border:1px solid #cbd5e1;border-radius:8px;background:#fff}.diff-grid{display:grid;grid-template-columns:repeat(3,140px) 1fr;gap:10px;margin-top:16px}.diff-stat{display:grid;place-content:center;min-height:90px;text-align:center;border-radius:12px;background:#f8fafc}.diff-stat strong{font-size:24px}.diff-stat span{font-size:12px;color:#64748b}.diff-stat.added strong{color:#059669}.diff-stat.removed strong{color:#dc2626}.diff-stat.changed strong{color:#b45309}.diff-list{max-height:180px;overflow:auto;border:1px solid #e5ebe8;border-radius:12px;padding:8px}.diff-list article{display:flex;justify-content:space-between;gap:12px;padding:7px;border-bottom:1px solid #eef2f0;font-size:12px}.diff-list span{color:#9a6514}.trace-head a{font-size:12px;color:#28735f;text-decoration:none}.trace-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px;margin-top:14px}.trace-list article{padding:11px;border:1px solid #e0ebe6;border-radius:10px;background:#fcfefd}.trace-list article div{display:flex;justify-content:space-between;gap:8px}.trace-list b{font-size:13px;color:#334155}.trace-list span{font-size:10px;color:#28735f}.trace-list p{margin:7px 0 0;font-size:12px;line-height:1.5;color:#64748b}@media(max-width:900px){.compare-head,.trace-head{flex-direction:column}.diff-grid{grid-template-columns:repeat(3,1fr)}.diff-list{grid-column:1/-1}}
  .pill.back-pill {
    background: #e8f0ed;
    border-color: #c6d9d0;
    color: #3d6b60;
  }
  .pill.back-pill:hover {
    background: #d6e8e0;
  }
</style>
