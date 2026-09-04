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
            <router-link :to="{ name: 'S1Intent' }" class="pill">S1 意图</router-link>
            <router-link :to="{ name: 'S2Material' }" class="pill">S2 资料</router-link>
            <router-link :to="{ name: 'S3Studio' }" class="pill">S3 生成</router-link>
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
            placeholder="输入 Generation ID"
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

        <div class="s4-layout">
          <!-- 版本历史 -->
          <section class="s4-versions">
            <div class="section-card">
              <h3>版本历史 ({{ versionStore.versionCount }})</h3>
              <div v-if="versionStore.loading" class="empty-tip">加载中...</div>
              <div v-else-if="versionStore.versions.length === 0" class="empty-tip">
                输入 Generation ID 并加载版本
              </div>
              <div v-else class="version-list">
                <div
                  v-for="v in versionStore.versions"
                  :key="v.id"
                  class="version-item"
                  :class="{ locked: v.locked }"
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
              <div v-if="!versionStore.genId" class="empty-tip">请先加载版本</div>
              <div v-else class="action-group">
                <!-- 回滚 -->
                <div class="action-row">
                  <label>回滚到版本:</label>
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
                    回滚
                  </button>
                </div>

                <!-- 锁定 -->
                <div class="action-row">
                  <button
                    class="btn btn-sm btn-warn"
                    :disabled="versionStore.loading"
                    @click="handleLock"
                  >
                    🔒 锁定最新版本
                  </button>
                </div>

                <!-- 修改指令 -->
                <div class="action-divider"></div>
                <h4>修改指令</h4>
                <div class="action-row">
                  <select v-model="changeType" class="action-select">
                    <option value="update_node">更新节点</option>
                    <option value="add_node">新增节点</option>
                    <option value="delete_node">删除节点</option>
                    <option value="swap_nodes">交换节点</option>
                    <option value="change_template">切换模板</option>
                  </select>
                  <input v-model="changeTarget" type="text" placeholder="目标节点ID" class="action-input" />
                  <button class="btn btn-sm" @click="handleAddChange">添加</button>
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
                    :disabled="versionStore.loading"
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
              :export-error="versionStore.exportError"
              :loading="versionStore.loading"
              :intent="intentStore.intentSummary || {}"
              :nodes="versionStore.currentVersionDetail?.nodes || []"
              @start-export="handleStartExport"
              @reset-export="versionStore.resetExport()"
            />
          </section>
        </div>

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
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useVersionStore } from '../stores/versionStore'
import { useGenerationStore } from '../stores/generationStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { useIntentStore } from '../stores/intentStore'
import AppShell from '../components/layout/AppShell.vue'
import S4VersionExportCenter from '../components/teacher/S4VersionExportCenter.vue'

const versionStore = useVersionStore()
const generationStore = useGenerationStore()
const workspaceStore = useWorkspaceStore()
const intentStore = useIntentStore()

const route = useRoute()

const genIdInput = ref(
  generationStore.lastGenId ||
  generationStore.restoreLastGenId() ||
  workspaceStore.currentCourseId ||
  ''
)

// 路由参数变化时自动加载版本（S3 一键生成后带 genId 跳转过来）
watch(() => route.query.genId, (id) => {
  if (id && typeof id === 'string') {
    genIdInput.value = id
    loadData()
  }
}, { immediate: true })
const rollbackTarget = ref(null)
const changeType = ref('update_node')
const changeTarget = ref('')

async function loadData() {
  const id = genIdInput.value.trim()
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

function handleStartExport(format) {
  if (!versionStore.genId) return
  versionStore.startExport(versionStore.genId, format)
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
.version-item { padding: 10px; background: #f6faf8; border-radius: 10px; }
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
  .pill.back-pill {
    background: #e8f0ed;
    border-color: #c6d9d0;
    color: #3d6b60;
  }
  .pill.back-pill:hover {
    background: #d6e8e0;
  }
</style>
