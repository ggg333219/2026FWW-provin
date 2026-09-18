<template>
  <AppShell>
    <div class="s3-page">
      <!-- 页面头部 -->
      <div class="page-header">
        <div>
          <h2>S3 课件生成</h2>
          <p>大纲编辑 → 内容生成 → 页面预览</p>
        </div>
        <div class="page-header-right">
          <button v-if="projectStore.projectId" class="save-state" :class="projectStore.saveState" @click="projectStore.saveNow(draftSnapshot())">{{ projectStore.saveLabel || '保存草稿' }}</button>
          <button v-if="generationStore.currentScriptNodes.length" class="save-version" :disabled="saveVersionState === 'saving'" @click="handleSaveNewVersion">{{ saveVersionState === 'saving' ? '正在保存版本…' : (lastSavedVersion ? `已保存 v${lastSavedVersion}` : '保存新版本') }}</button>
          <div class="step-pills">
            <router-link :to="{ name: 'S1Intent', query: { project_id: projectStore.projectId } }" class="pill"
              >S1 意图</router-link
            >
            <router-link :to="{ name: 'S2Material', query: { project_id: projectStore.projectId } }" class="pill"
              >S2 资料</router-link
            >
            <span class="pill active">S3 生成</span>
            <router-link :to="{ name: 'S4Version', query: { project_id: projectStore.projectId, generation_id: generationStore.lastGenId } }" class="pill"
              >S4 版本</router-link
            >
            <router-link :to="{ name: 'Middle' }" class="pill back-pill"
              >返回中间页</router-link
            >
          </div>
        </div>
      </div>

      <!-- 模式提示条 -->
      <div
        v-if="generationMode === 'without_evidence'"
        class="evidence-warning"
        role="status"
      >
        <div>
          <strong>当前为无参考资料生成模式</strong>
          <span>本次内容仅依据 S1 教学意图生成，不会伪造资料引用。</span>
        </div>
        <router-link :to="{ name: 'S2Material', query: { project_id: projectStore.projectId } }">返回补充资料</router-link>
      </div>

      <!-- S3 阶段指示器 -->
      <div class="phase-tabs">
        <button
          class="phase-tab"
          :class="{ active: currentPhase === 'outline' }"
          @click="currentPhase = 'outline'"
        >
          📋 大纲编辑
        </button>
        <button
          class="phase-tab"
          :class="{ active: currentPhase === 'generating' }"
          @click="currentPhase = 'generating'"
          :disabled="!outlineStore.isConfirmed"
        >
          ⚙️ 内容生成
        </button>
        <button
          class="phase-tab"
          :class="{ active: currentPhase === 'pages' }"
          @click="currentPhase = 'pages'"
          :disabled="!generationStore.lastGenId"
        >
          📄 页面管理
        </button>
        <button class="phase-tab" :class="{ active: currentPhase === 'style' }" :disabled="!generationStore.lastGenId" @click="currentPhase = 'style'">🎨 PPT 样式</button>
      </div>

      <!-- ==================== 大纲阶段 ==================== -->
      <!-- ==================== 大纲阶段 ==================== -->
      <EvidenceSidebar
        :packet="evidencePacket"
        :nodes="generationStore.currentScriptNodes.length ? generationStore.currentScriptNodes : outlineStore.nodes"
        :searching="materialStore.searching"
        :default-query="intentStore.intentSummary?.topic || ''"
        @search="handleEvidenceSearch"
        @apply="handleEvidenceApply"
      />
      <!-- C6: AI 修改对话面板（右侧浮动；projectId 绑定后显示） -->
      <ModifyPanel class="s3-ai-panel" @style-request="handleStyleRequest" />
      <div v-if="currentPhase === 'outline'" class="phase-panel">
        <OutlineEditor
          :session-id="intentStore.sessionId"
          :intent-id="intentStore.intentId"
          :intent-summary="intentStore.intentSummary"
          :auto-restore="true"
          @confirm-complete="handleOutlineConfirmed"
          @outline-created="handleOutlineCreated"
          @error="handleError"
        />
      </div>

      <!-- ==================== 内容生成阶段 ==================== -->
      <div v-else-if="currentPhase === 'generating'" class="phase-panel">
        <!-- 生成控制栏 -->
        <div class="gen-control-bar">
          <div class="gen-info">
            <span class="gen-label">大纲</span>
            <span class="gen-value"
              >{{ outlineStore.outline_id }} v{{
                outlineStore.outline_version
              }}</span
            >
            <span class="gen-label" style="margin-left: 12px">生成模式</span>
            <select v-model="generateMode" class="gen-mode-select">
              <option value="page_incremental">逐页增量生成</option>
              <option value="page_parallel">全页面并行生成</option>
            </select>
          </div>
          <div class="gen-actions">
            <button
              class="btn btn-primary"
              :disabled="generationStore.isGenerating"
              @click="handleStartGeneration"
            >
              {{ generationStore.isGenerating ? "生成中..." : "🚀 开始生成" }}
            </button>
          </div>
        </div>

        <!-- 进度展示 -->
        <div
          v-if="
            generationStore.isGenerating || generationStore.generateProgress > 0
          "
          class="gen-progress-panel"
        >
          <div class="progress-bar-wrap">
            <div
              class="progress-bar-fill"
              :style="{ width: generationStore.generateProgress + '%' }"
            ></div>
          </div>
          <div class="progress-text">
            <span>{{ generationStore.generateProgress }}%</span>
            <span>{{ generationStore.generateStageText }}</span>
          </div>
        </div>

        <!-- 错误展示 -->
        <div v-if="genError" class="error-bar" role="alert">{{ genError }}</div>

        <!-- 生成的节点树预览 -->
        <div
          v-if="generationStore.currentScriptNodes.length > 0"
          class="gen-nodes-preview"
        >
          <h4>已生成节点</h4>
          <div class="nodes-summary">
            <span
              v-for="(node, i) in generationStore.currentScriptNodes"
              :key="i"
              class="node-chip"
            >
              {{ i + 1 }}.
              {{ node.title || node.node_title || "节点" + (i + 1) }}
            </span>
          </div>
        </div>

        <!-- HTML5 预览区 -->
        <div v-if="generationStore.previewHtml" class="preview-section">
          <div class="preview-toolbar">
            <span>📺 HTML5 预览</span>
            <button class="btn btn-sm" @click="openPreviewWindow">
              新窗口打开
            </button>
          </div>
          <iframe
            v-if="previewFrameSrc"
            :src="previewFrameSrc"
            class="preview-frame"
            sandbox="allow-scripts allow-same-origin"
            title="课件预览"
          ></iframe>
          <div v-else class="preview-placeholder">
            预览将在生成完成后自动加载
          </div>
        </div>

        <!-- 无参考资料提示 -->
        <div v-if="!hasEvidence" class="no-evidence-hint">
          ⚠️ 当前无参考资料，内容将基于 S1 意图自动生成。
          <router-link :to="{ name: 'S2Material' }"
            >前往 S2 补充资料</router-link
          >
        </div>

        <!-- 生成完成后操作 -->
        <div
          v-if="generationStore.generateProgress === 100"
          class="gen-complete-actions"
        >
          <button class="btn btn-outline" @click="currentPhase = 'pages'">
            管理生成页面
          </button>
          <button class="btn btn-primary" @click="goToS4">
            下一步：版本管理 →
          </button>
        </div>
      </div>

      <div v-else-if="currentPhase === 'style'" class="phase-panel style-panel">
        <h3>只调整呈现，不改教学事实</h3>
        <p>样式设置不会触发 RAG 检索，也不会修改大纲、引用或生成内容。</p>
        <label>全局模板 <select v-model="templateId"><option value="default">默认教学模板</option><option value="deck-swiss-edu">瑞士教育风</option></select></label>
        <label>配色 <select v-model="palette"><option value="classic">经典青绿</option><option value="klein-blue">克莱因蓝</option></select></label>
        <label>版式 <select v-model="layoutMode"><option value="balanced">图文均衡</option><option value="visual">视觉优先</option><option value="text">内容优先</option></select></label>
        <label>字体 <select v-model="fontFamily"><option value="system">系统默认</option><option value="source-han">思源黑体</option><option value="serif">中文宋体</option></select></label>
        <label>信息密度 <select v-model="density"><option value="comfortable">舒展</option><option value="compact">紧凑</option><option value="minimal">极简</option></select></label>
        <div class="style-ai-hint">也可以在右侧直接告诉 AI：“整体换成简洁商务风”或“这一页改成左图右文”。样式调整只改呈现字段，不重新检索资料。</div>
        <div class="style-actions"><button class="btn btn-outline" @click="projectStore.saveNow(draftSnapshot())">保存样式草稿</button><button class="btn btn-primary" :disabled="generationStore.previewLoading" @click="applyPresentationStyle">{{ generationStore.previewLoading ? '正在刷新…' : '应用并刷新预览' }}</button></div>
      </div>

      <!-- ==================== 页面管理阶段 ==================== -->
      <div v-else-if="currentPhase === 'pages'" class="phase-panel">
        <div class="pages-control-bar">
          <div class="pages-info">
            <span>Generation ID：{{ generationStore.lastGenId }}</span>
          </div>
          <div class="pages-actions">
            <button class="btn btn-sm" @click="loadGenerationStatus">
              🔄 刷新状态
            </button>
          </div>
        </div>

        <!-- 页面列表 -->
        <div v-if="generationPages.length > 0" class="pages-list">
          <div
            v-for="page in generationPages"
            :key="page.page_id"
            class="page-item"
            :class="[`page-status-${page.status}`, { 'page-modified': modifyStore.recentlyModifiedIds.includes(page.node_id) }]"
          >
            <div class="page-item-left">
              <span class="page-order">第 {{ page.page_order }} 页</span>
              <span class="page-node">{{ page.title || page.node_title || `关联节点：${page.node_id}` }}</span>
              <span v-if="modifyStore.recentlyModifiedIds.includes(page.node_id)" class="changed-badge">已修改</span>
            </div>
            <div class="page-item-right">
              <span class="page-status-badge">{{
                statusLabel(page.status)
              }}</span>
              <button
                v-if="page.status === 'failed'"
                class="btn btn-sm"
                :disabled="regeneratingPageId === page.page_id"
                @click="handleRegeneratePage(page)"
              >
                {{
                  regeneratingPageId === page.page_id
                    ? "重生成中..."
                    : "🔄 重试"
                }}
              </button>
              <button
                v-if="page.status === 'done'"
                class="btn btn-sm"
                @click="handlePreviewPage(page)"
              >
                👁 预览
              </button>
            </div>
          </div>
        </div>

        <div v-else class="pages-empty">暂无页面数据，请先生成内容</div>

        <!-- 互动资源入口 -->
        <div v-if="generationStore.lastGenId" class="interactive-section">
          <h4>🎮 互动资源管理</h4>
          <p class="interactive-hint">
            从大纲中标记为互动的节点可在此生成 HTML5 互动资源
          </p>
          <div class="interactive-node-list">
            <div
              v-for="node in interactiveNodes"
              :key="node.node_id"
              class="interactive-node-row"
            >
              <div class="int-node-info">
                <span class="int-node-title">{{ node.title }}</span>
                <span class="int-node-type">{{ node.node_type }}</span>
              </div>
              <div class="int-node-actions">
                <template v-if="interactiveStore.hasAsset(node.node_id)">
                  <span class="asset-done">✅ 已生成</span>
                  <button
                    class="btn btn-sm"
                    @click="openInteractiveAsset(node)"
                  >
                    打开
                  </button>
                </template>
                <template
                  v-else-if="
                    interactiveStore.getAsset(node.node_id)?.status ===
                    'processing'
                  "
                >
                  <span class="asset-pending">⏳ 生成中...</span>
                </template>
                <template v-else>
                  <button
                    class="btn btn-sm btn-primary"
                    :disabled="interactiveStore.loading"
                    @click="handleGenerateInteractive(node)"
                  >
                    生成互动
                  </button>
                </template>
              </div>
            </div>
            <p v-if="interactiveNodes.length === 0" class="no-interactive-hint">
              大纲中无互动节点，可在编辑大纲时将节点类型改为"互动环节"
            </p>
          </div>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import AppShell from "../components/layout/AppShell.vue";
import OutlineEditor from "../components/teacher/OutlineEditor.vue";
import ModifyPanel from "../components/teacher/ModifyPanel.vue";
import EvidenceSidebar from "../components/teacher/EvidenceSidebar.vue";
import { useGenerationStore } from "../stores/generationStore";
import { useOutlineStore } from "../stores/outlineStore";
import { useInteractiveStore } from "../stores/interactiveStore";
import { useIntentStore } from "../stores/intentStore";
import { useMaterialStore } from "../stores/materialStore";
import { useModifyStore } from "../stores/modifyStore";
import { useCoursewareProjectStore } from "../stores/coursewareProjectStore";
import { teacherV1Api } from "../services/v1";
import { API_BASE, AI_API_BASE } from "../config/api";

const generationStore = useGenerationStore();
const outlineStore = useOutlineStore();
const interactiveStore = useInteractiveStore();
const intentStore = useIntentStore();
const materialStore = useMaterialStore();
const modifyStore = useModifyStore();
const projectStore = useCoursewareProjectStore();
const route = useRoute();
const router = useRouter();

// 阶段：outline | generating | pages
const currentPhase = ref("outline");
const generationMode = ref("");
const generateMode = ref("page_incremental");
const genError = ref("");
const generationPages = ref([]);
const regeneratingPageId = ref("");
const previewFrameSrc = ref("");
const templateId = ref("default");
const palette = ref("classic");
const layoutMode = ref("balanced");
const fontFamily = ref("system");
const density = ref("comfortable");
const evidencePacket = ref(null);
const evidenceScope = ref({ scope: "draft", nodeId: "" });
const saveVersionState = ref("idle");
const lastSavedVersion = ref(0);

function draftSnapshot() {
  return { intent: intentStore.intentSummary || null, outline: { outline_id: outlineStore.outline_id, outline_version: outlineStore.outline_version, status: outlineStore.status, title: outlineStore.title, nodes: outlineStore.nodes }, generation: { generation_id: generationStore.lastGenId, task_id: generationStore.lastTaskId, nodes: generationStore.currentScriptNodes }, evidence_packet: evidencePacket.value, evidence_scope: evidenceScope.value, presentation: { template_id: templateId.value, palette: palette.value, layout: layoutMode.value, font_family: fontFamily.value, density: density.value } };
}

// 是否有参考资料
const hasEvidence = computed(() => {
  return !!evidencePacket.value;
});

// 需要互动资源的节点（大纲中标记为 interactive / quiz 的节点）
const interactiveNodes = computed(() =>
  (outlineStore.nodes || []).filter(
    (n) => n.node_type === "interactive" || n.node_type === "quiz",
  ),
);

onMounted(async () => {
	let restoredGenerationNodes = false;
  // 恢复 S1 会话/意图（刷新或直接进入 S3 时 store 内存为空，
  // 不恢复会导致 sessionId 缺失 → AI 生成大纲被 "缺少 session_id" 拦截）
  intentStore.initialize();
  materialStore.activeSessionId = intentStore.sessionId || projectStore.projectId || "";
  if (typeof window !== "undefined") {
    generationMode.value =
      window.localStorage.getItem(
        `fuww_s2_generation_mode:${intentStore.sessionId}`,
      ) || "";
    try {
      const rawEvidence = window.localStorage.getItem(`fuww_s2_evidence_packet:${intentStore.sessionId}`);
      evidencePacket.value = rawEvidence ? JSON.parse(rawEvidence) : null;
    } catch { evidencePacket.value = null; }
  }

  // project_id 才是 AI 对话、草稿与版本的边界；generation_id 只是该项目的生成结果。
  projectStore.setActive(String(route.query.project_id || projectStore.restoreActiveId() || ""));
  if (projectStore.projectId) {
    modifyStore.bindProject(projectStore.projectId);
    await modifyStore.loadVersionHistory();
    await projectStore.updateStep("s3_studio").catch(() => {});
    // 统一恢复入口已把后端 draft 放入 session；优先恢复项目快照，避免误用另一份课件的全局缓存。
    try {
      const rawDraft = window.localStorage.getItem("fuww_courseware_resume_draft");
      const savedDraft = rawDraft ? JSON.parse(rawDraft) : null;
      if (savedDraft?.outline?.outline_id) {
        outlineStore._applyOutlineData(savedDraft.outline);
        outlineStore._persist();
      }
      if (savedDraft?.generation) {
        if (savedDraft.generation.generation_id) generationStore.setLastGenId(savedDraft.generation.generation_id);
        if (savedDraft.generation.task_id) generationStore.setLastTaskId(savedDraft.generation.task_id);
        if (Array.isArray(savedDraft.generation.nodes) && savedDraft.generation.nodes.length) {
          const restoredNodes = savedDraft.generation.nodes;
          generationStore.setNodes(restoredNodes);
          generationPages.value = restoredNodes.map((node, index) => ({
            ...node,
            page_id: node.page_id || node.node_id || `page_${index + 1}`,
            page_order: Number(node.page_order || node.order || index + 1),
            status: node.status || "completed",
          }));
          restoredGenerationNodes = true;
          currentPhase.value = "pages";
        }
      }
      if (savedDraft?.evidence_packet) evidencePacket.value = savedDraft.evidence_packet;
      if (savedDraft?.evidence_scope) evidenceScope.value = savedDraft.evidence_scope;
      if (savedDraft?.presentation) { templateId.value = savedDraft.presentation.template_id || "default"; palette.value = savedDraft.presentation.palette || "classic"; layoutMode.value = savedDraft.presentation.layout || "balanced"; fontFamily.value = savedDraft.presentation.font_family || "system"; density.value = savedDraft.presentation.density || "comfortable"; }
    } catch {}
  }
  // 尝试从 localStorage 恢复大纲
  const restored = outlineStore.restore();
  if (!restoredGenerationNodes && restored && outlineStore.isConfirmed) {
    currentPhase.value = "generating";
  }
  // 恢复最近生成记录
  generationStore.restoreLastGenId();
  if (generationStore.lastGenId) {
    interactiveStore.setGenerationId(generationStore.lastGenId);
    // 项目草稿已经包含完整节点时直接使用，避免全局缓存中的旧 task_id
    // 覆盖当前课件的恢复结果。
    if (!restoredGenerationNodes) await loadGenerationStatus();
  }
});

watch(() => [outlineStore.nodes, generationStore.currentScriptNodes, templateId.value, palette.value, layoutMode.value, fontFamily.value, density.value], () => projectStore.scheduleSave(draftSnapshot()), { deep: true });
watch(() => generationStore.currentScriptNodes, (nodes) => {
  if (!Array.isArray(nodes) || !nodes.length) return;
  generationPages.value = nodes.map((node, index) => {
    const existing = generationPages.value.find((page) => page.node_id === node.node_id) || {};
    return {
      ...existing,
      ...node,
      page_id: existing.page_id || node.page_id || node.node_id || `page_${index + 1}`,
      page_order: Number(node.page_order || node.order || index + 1),
      status: node.status || existing.status || 'done',
    };
  });
}, { deep: true });
watch(() => generationStore.previewHtml, (html) => {
  previewFrameSrc.value = html ? `data:text/html;charset=utf-8,${encodeURIComponent(html)}` : "";
});
onBeforeUnmount(() => { projectStore.saveNow(draftSnapshot()).catch(() => {}); });
onBeforeRouteLeave(async () => { await projectStore.saveNow(draftSnapshot()).catch(() => {}); });

function statusLabel(status) {
  return (
    {
      pending: "等待",
      processing: "生成中",
      done: "完成",
      failed: "失败",
    }[status] || status
  );
}

// 大纲创建完成
function handleOutlineCreated({ outline_id, outline_version }) {
  console.log(
    "[S3StudioPage] 大纲创建完成:",
    outline_id,
    "v" + outline_version,
  );
}

// 大纲确认完成，进入生成阶段
function handleOutlineConfirmed() {
  currentPhase.value = "generating";
}

// 开始生成内容
async function handleStartGeneration() {
  if (!outlineStore.outline_id || !outlineStore.isConfirmed) {
    handleError("请先确认大纲");
    return;
  }
  genError.value = "";
  generationStore.setGenerating(true);
  generationStore.setGenerateProgress(5, "准备生成环境");

  try {
    let evidence = null;
    try {
      const raw = window.localStorage.getItem(`fuww_s2_evidence_packet:${intentStore.sessionId}`);
      if (raw) evidence = JSON.parse(raw);
    } catch {}

    generationStore.setGenerateProgress(15, "创建生成任务");
    const resp = await teacherV1Api.generation.createGeneration({
      session_id: intentStore.sessionId,
      outline_id: outlineStore.outline_id,
      outline_version: outlineStore.outline_version,
      outline_confirmed: true,
      template_id: templateId.value,
      project_id: projectStore.projectId,
      generate_mode: generateMode.value,
      intent: intentStore.intentSummary || undefined,
      evidence_packet: evidence,
    });

    const task = resp?.data || resp || {};
    const taskId = task.task_id || task.generation_id;
    if (!taskId) throw new Error("未返回生成任务 ID");
    generationStore.setLastTaskId(taskId);

    // 记录 generation_id
    const genId = task.generation_id || taskId;
    generationStore.setLastGenId(genId);
    projectStore.scheduleSave(draftSnapshot(), 0);
    interactiveStore.setGenerationId(genId);

    generationStore.setGenerateProgress(25, "正在生成内容");
    const status = await generationStore.waitForCoursewareGeneration(taskId, {
      intervalMs: 800,
      maxAttempts: 300,
    });

    // 加载生成状态（页面列表）
    await loadGenerationStatus();

    // 渲染预览
    generationStore.setGenerateProgress(92, "正在加载预览");
    const html = await generationStore.renderCoursewarePreview(
      outlineStore.title || intentStore.intentSummary?.topic || "课件预览",
      { genId },
    );
    if (html) {
      previewFrameSrc.value = `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
    }

    generationStore.setGenerateProgress(100, "生成完成");
  } catch (err) {
    genError.value = err?.message || "生成失败，请重试";
    generationStore.setGenerateProgress(0, "生成失败");
  } finally {
    generationStore.setGenerating(false);
  }
}

// 加载生成状态
async function loadGenerationStatus() {
  const taskId = generationStore.lastTaskId || generationStore.restoreLastTaskId();
  if (!taskId) return;
  try {
    const resp = await teacherV1Api.generation.getGenerationStatus(taskId);
    const data = resp?.data || resp || {};
    generationPages.value = (Array.isArray(data.nodes) ? data.nodes : []).map((node, index) => ({
      ...node,
      page_id: node.page_id || node.node_id || `page_${index + 1}`,
      page_order: Number(node.page_order || node.order || index + 1),
      status: node.status || 'completed'
    }));
  } catch (err) {
    console.warn("[S3StudioPage] 加载生成状态失败", err);
  }
}

// 单页重生成
async function handleRegeneratePage(page) {
  regeneratingPageId.value = page.page_id;
  try {
    await teacherV1Api.generation.regeneratePage(
      generationStore.lastGenId,
      page.page_id,
      { reason: "教师手动重试", mode: "ai" },
    );
    await loadGenerationStatus();
  } catch (err) {
    handleError("重生成失败: " + (err?.message || ""));
  } finally {
    regeneratingPageId.value = "";
  }
}

// 预览单页
async function handlePreviewPage(page) {
  try {
    const resp = await teacherV1Api.generation.getPage(
      generationStore.lastGenId,
      page.page_id,
    );
    const data = resp?.data || resp || {};
    if (data.preview_url) {
      window.open(data.preview_url, "_blank");
    }
  } catch (err) {
    handleError("预览加载失败");
  }
}

// 生成互动资源
async function handleGenerateInteractive(node) {
  if (!generationStore.lastGenId) return;
  try {
    await interactiveStore.generateInteractive({
      generation_id: generationStore.lastGenId,
      node_id: node.node_id,
      interactive_plan: node.interactive_plan || {
        enabled: true,
        kind: "quiz",
        question_count: 3,
        duration_minutes: 5,
        auto_grading: true,
        delivery: "html5_link",
      },
    });
    const asset = await interactiveStore.pollAssetStatus(node.node_id);
    if (asset?.status === "done") {
      const nodes = (generationStore.currentScriptNodes || []).map((item) => item.node_id === node.node_id
        ? { ...item, metadata: { ...(item.metadata || {}), interactive_asset: asset, interactive_entry_url: asset.entry_url || asset.file_url || "" } }
        : item);
      generationStore.setNodes(nodes);
      const page = generationPages.value.find((item) => item.node_id === node.node_id);
      if (page?.page_id && asset.interactive_asset_id) {
        await interactiveStore.linkToPage({
          generation_id: generationStore.lastGenId,
          page_id: page.page_id,
          interactive_asset_id: asset.interactive_asset_id,
          label: node.title || "互动练习",
        }).catch(() => {});
      }
      projectStore.scheduleSave(draftSnapshot(), 0);
    }
  } catch (err) {
    handleError("生成互动资源失败: " + (err?.message || ""));
  }
}

// 打开互动资源
function openInteractiveAsset(node) {
  const asset = interactiveStore.getAsset(node.node_id);
  if (asset?.entry_url) {
    window.open(asset.entry_url, "_blank");
  }
}

// 新窗口打开 HTML5 预览
function openPreviewWindow() {
  if (!generationStore.previewHtml) return;
  const blob = new Blob([generationStore.previewHtml], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

async function applyPresentationStyle() {
  const presentation = {
    template_id: templateId.value,
    palette: palette.value,
    layout: layoutMode.value,
    font_family: fontFamily.value,
    density: density.value,
  };
  generationStore.setNodes((generationStore.currentScriptNodes || []).map((node) => ({
    ...node,
    layout_hint: layoutMode.value === "visual" ? "text_with_media" : (layoutMode.value === "text" ? "text_only" : (node.layout_hint || "two_column")),
    font_size_hint: density.value === "minimal" ? "large" : (density.value === "compact" ? "small" : "medium"),
    slide_background: palette.value === "klein-blue" ? "preset_blue" : "preset_green",
    metadata: { ...(node.metadata || {}), presentation },
  })));
  await generationStore.renderCoursewarePreview(
    outlineStore.title || intentStore.intentSummary?.topic || "课件预览",
    { genId: "" },
  );
  projectStore.scheduleSave(draftSnapshot(), 0);
  currentPhase.value = "style";
}

async function handleStyleRequest({ instruction = '', presentation = {} } = {}) {
  const text = String(instruction).toLowerCase();
  const style = presentation && typeof presentation === 'object' ? presentation : {};
  if (style.template_id) templateId.value = style.template_id;
  if (style.palette) palette.value = style.palette;
  if (style.layout) layoutMode.value = style.layout;
  if (style.font_family) fontFamily.value = style.font_family;
  if (style.density) density.value = style.density;
  // 兼容旧 AI 响应：仅当结构化字段为空时才使用本地兜底映射。
  if (!Object.values(style).some(Boolean)) {
    if (/商务|business|简洁/.test(text)) { templateId.value = 'deck-swiss-edu'; density.value = 'minimal'; }
    if (/蓝|blue/.test(text)) palette.value = 'klein-blue';
    if (/图|视觉|visual/.test(text)) layoutMode.value = 'visual';
    if (/文字|内容优先/.test(text)) layoutMode.value = 'text';
  }
  currentPhase.value = 'style';
  await applyPresentationStyle();
}

async function handleEvidenceSearch(query) {
  const packet = await materialStore.generateEvidence({
    query,
    context: { intent: intentStore.intentSummary || {}, project_id: projectStore.projectId },
  });
  if (packet) {
    evidencePacket.value = packet;
    projectStore.scheduleSave(draftSnapshot(), 0);
  }
}

async function handleEvidenceApply({ scope, nodeId }) {
  evidenceScope.value = { scope, nodeId: nodeId || "" };
  if (scope === "none" || !evidencePacket.value) {
    projectStore.scheduleSave(draftSnapshot(), 0);
    return;
  }
  const refs = [
    ...(evidencePacket.value.citations || []).map((item) => item.chunk_id),
    ...(evidencePacket.value.relevant_chunks || []).map((item) => item.chunk_id),
  ].filter(Boolean);
  const uniqueRefs = [...new Set(refs)];
  if (generationStore.currentScriptNodes?.length) {
    generationStore.setNodes(generationStore.currentScriptNodes.map((node) => {
      const selected = scope === "draft" || node.node_id === nodeId;
      return selected ? {
        ...node,
        citation_refs: [...new Set([...(node.citation_refs || []), ...uniqueRefs])],
        source_chunk_ids: [...new Set([...(node.source_chunk_ids || []), ...uniqueRefs])],
        metadata: { ...(node.metadata || {}), evidence_scope: scope },
      } : node;
    }));
    await generationStore.renderCoursewarePreview(outlineStore.title || intentStore.intentSummary?.topic || "课件预览", { genId: "" });
  }
  projectStore.scheduleSave(draftSnapshot(), 0);
}

async function handleSaveNewVersion() {
  if (!generationStore.currentScriptNodes.length || saveVersionState.value === "saving") return;
  saveVersionState.value = "saving";
  genError.value = "";
  try {
    await projectStore.saveNow(draftSnapshot());
    const response = await teacherV1Api.generation.finalize({
      generation_id: generationStore.lastGenId,
      nodes: generationStore.currentScriptNodes,
      course_name: outlineStore.title || intentStore.intentSummary?.topic || "未命名课件",
      summary: `教师保存：${new Date().toLocaleString()}`,
      outline_id: outlineStore.outline_id,
      outline_version: outlineStore.outline_version,
    });
    const data = response?.data || response || {};
    if (data.generation_id) generationStore.setLastGenId(data.generation_id);
    lastSavedVersion.value = Number(data.version_number || 0);
    saveVersionState.value = "saved";
    await modifyStore.loadVersionHistory().catch(() => {});
  } catch (error) {
    saveVersionState.value = "error";
    genError.value = error?.message || "保存新版本失败";
  }
}

function goToS4() {
  // 同步大纲信息到 localStorage，供 S4 使用
  try {
    window.localStorage.setItem(
      "fuww_s3_outline_info",
      JSON.stringify({
        outline_id: outlineStore.outline_id,
        outline_version: outlineStore.outline_version,
        generation_id: generationStore.lastGenId,
      }),
    );
  } catch {}
  projectStore.updateStep("s4_version").catch(() => {});
  router.push({ name: "S4Version", query: { project_id: projectStore.projectId, generation_id: generationStore.lastGenId } });
}

function handleError(msg) {
  genError.value = msg;
  console.warn("[S3StudioPage]", msg);
}
</script>

<style scoped>
.s3-page {
  display: flex;
  flex-direction: column;
  padding: 20px 380px 20px 340px;
  min-height: calc(100vh - 140px);
  overflow: hidden;
  background:
    radial-gradient(
      circle at 86% -15%,
      rgba(175, 221, 203, 0.2),
      transparent 30%
    ),
    linear-gradient(180deg, #fcfefd 0%, #f7faf8 100%);
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
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
  margin-bottom: 14px;
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

/* 阶段选项卡 */
.phase-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 14px;
  border-bottom: 2px solid #e2ece6;
}
.phase-tab {
  padding: 8px 18px;
  border: none;
  background: none;
  font-size: 13px;
  font-weight: 500;
  color: #607a71;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.15s;
}
.phase-tab:hover:not(:disabled) {
  color: #2f605a;
}
.phase-tab.active {
  color: #2f605a;
  border-bottom-color: #2f605a;
}
.phase-tab:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 阶段面板 */
.phase-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.s3-ai-panel { position: fixed; top: 118px; right: 20px; bottom: 20px; width: 340px; z-index: 12; box-shadow: 0 12px 34px rgba(30, 72, 60, .12); border: 1px solid #dce9e3; border-radius: 14px; overflow: hidden; }
.style-ai-hint { padding: 12px; border-radius: 10px; background: #f1f8f5; color: #45685e; font-size: 13px; line-height: 1.6; }
@media (max-width: 1400px) { .s3-page { padding-left: 20px; } }
@media (max-width: 1100px) { .s3-page { padding-right: 20px; } .s3-ai-panel { position: static; width: auto; min-height: 420px; margin-bottom: 14px; } }
.save-state { border: 1px solid #bdd8cb; border-radius: 999px; padding: 6px 10px; background: #fff; color: #42675d; font-size: 12px; cursor: pointer; }
.save-state.saving { color: #996a14; }.save-state.error { color: #b42318; }
.save-version { border: 1px solid #2f605a; border-radius: 999px; padding: 6px 11px; background: #2f605a; color: #fff; font-size: 12px; cursor: pointer; }.save-version:disabled{opacity:.55;cursor:not-allowed}
.style-panel { max-width: 680px; padding: 22px; border: 1px solid #dce9e3; border-radius: 14px; background: #fff; }
.style-panel h3 { margin: 0; color: #24483e; }.style-panel p { color: #667b73; font-size: 13px; }
.style-panel label { display: grid; gap: 6px; margin-top: 14px; color: #365e52; font-size: 13px; font-weight: 600; }
.style-panel select { padding: 9px; border: 1px solid #c7ddd4; border-radius: 8px; background: #fff; }.style-actions { display: flex; gap: 10px; margin-top: 20px; }

/* 生成控制栏 */
.gen-control-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 12px 16px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.gen-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  flex-wrap: wrap;
}
.gen-label {
  font-weight: 600;
  color: #2f605a;
}
.gen-value {
  color: #475569;
}
.gen-mode-select {
  padding: 4px 8px;
  border: 1px solid #c6ded6;
  border-radius: 6px;
  font-size: 12px;
  color: #2f605a;
  background: #fff;
  outline: none;
  cursor: pointer;
}
.gen-actions {
  display: flex;
  gap: 8px;
}

/* 进度条 */
.gen-progress-panel {
  padding: 12px 16px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.progress-bar-wrap {
  height: 8px;
  background: #e2ece6;
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 8px;
}
.progress-bar-fill {
  height: 100%;
  background: #2f605a;
  border-radius: 999px;
  transition: width 0.4s ease;
}
.progress-text {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #607a71;
}

/* 错误条 */
.error-bar {
  padding: 10px 14px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #dc2626;
  font-size: 13px;
}

/* 节点预览 */
.gen-nodes-preview {
  padding: 12px 16px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.gen-nodes-preview h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #2f605a;
}
.nodes-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.node-chip {
  font-size: 12px;
  background: #e8f5f0;
  color: #2f605a;
  padding: 3px 10px;
  border-radius: 999px;
}

/* 预览区 */
.preview-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.preview-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: #2f605a;
  font-weight: 600;
}
.preview-frame {
  width: 100%;
  height: 480px;
  border: 1px solid #e2ece6;
  border-radius: 12px;
  background: #fff;
}
.preview-placeholder {
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed #c6ded6;
  border-radius: 12px;
  color: #94a3b8;
  font-size: 13px;
}

/* 无资料提示 */
.no-evidence-hint {
  font-size: 12px;
  color: #7c4a15;
  background: #fffaf0;
  border: 1px solid #f0d5a8;
  border-radius: 8px;
  padding: 10px 14px;
}
.no-evidence-hint a {
  color: #2f605a;
  font-weight: 600;
}

/* 生成完成操作 */
.gen-complete-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

/* 页面管理 */
.pages-control-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 14px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.pages-info {
  font-size: 13px;
  color: #475569;
}
.pages-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.page-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 14px;
  background: #fff;
  border: 1.5px solid #e2ece6;
  border-radius: 10px;
}
.page-item.page-modified {
  border-color: #24a36f;
  background: #effdf7;
  box-shadow: 0 0 0 3px rgba(36, 163, 111, .12);
  animation: pageModified 2s ease-out;
}
.changed-badge {
  padding: 2px 7px;
  border-radius: 999px;
  background: #24a36f;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
}
@keyframes pageModified {
  from { transform: translateY(-2px); }
  to { transform: translateY(0); box-shadow: none; }
}
.page-status-done {
  border-color: #6ee7b7;
}
.page-status-failed {
  border-color: #fca5a5;
}
.page-status-processing {
  border-color: #fcd34d;
}
.page-item-left {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}
.page-order {
  font-weight: 600;
  color: #2f605a;
}
.page-node {
  color: #64748b;
  font-size: 12px;
}
.page-item-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.page-status-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}
.page-status-done .page-status-badge {
  background: #d1fae5;
  color: #065f46;
}
.page-status-failed .page-status-badge {
  background: #fee2e2;
  color: #991b1b;
}
.page-status-processing .page-status-badge {
  background: #fef9c3;
  color: #854d0e;
}
.page-status-pending .page-status-badge {
  background: #f3f4f6;
  color: #6b7280;
}
.pages-empty {
  text-align: center;
  padding: 40px;
  color: #94a3b8;
  font-size: 13px;
}

/* 互动资源 */
.interactive-section {
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #e4ede8;
  border-radius: 12px;
}
.interactive-section h4 {
  margin: 0 0 6px;
  font-size: 14px;
  color: #1e293b;
}
.interactive-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #64748b;
}
.interactive-node-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.interactive-node-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 12px;
  background: #f8fbf9;
  border-radius: 8px;
}
.int-node-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.int-node-title {
  font-size: 13px;
  color: #1e293b;
}
.int-node-type {
  font-size: 11px;
  background: #e8f5f0;
  color: #2f605a;
  padding: 1px 6px;
  border-radius: 999px;
}
.int-node-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.asset-done {
  font-size: 12px;
  color: #065f46;
}
.asset-pending {
  font-size: 12px;
  color: #854d0e;
}
.no-interactive-hint {
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
  padding: 10px 0;
}

/* 通用按钮 */
.btn {
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
  border: 1px solid transparent;
}
.btn-sm {
  padding: 5px 12px;
  font-size: 12px;
}
.btn-outline {
  background: #fff;
  border-color: #c6ded6;
  color: #2f605a;
}
.btn-outline:hover {
  background: #f0f5f2;
}
.btn-primary {
  background: #2f605a;
  color: #fff;
}
.btn-primary:hover:not(:disabled) {
  background: #1e4a44;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 步骤导航 */
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

@media (max-width: 760px) {
  .page-header {
    flex-direction: column;
  }
  .gen-control-bar {
    flex-direction: column;
    align-items: flex-start;
  }
  .phase-tabs {
    overflow-x: auto;
  }
}
.pill.back-pill {
  background: #e8f0ed;
  border-color: #c6d9d0;
  color: #3d6b60;
}
.pill.back-pill:hover {
  background: #d6e8e0;
}
</style>
