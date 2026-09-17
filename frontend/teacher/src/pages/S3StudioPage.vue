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
          <div class="step-pills">
            <router-link :to="{ name: 'S1Intent' }" class="pill"
              >S1 意图</router-link
            >
            <router-link :to="{ name: 'S2Material' }" class="pill"
              >S2 资料</router-link
            >
            <span class="pill active">S3 生成</span>
            <router-link :to="{ name: 'S4Version' }" class="pill"
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
        <router-link :to="{ name: 'S2Material' }">返回补充资料</router-link>
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
      </div>

      <!-- ==================== 大纲阶段 ==================== -->
      <!-- ==================== 大纲阶段 ==================== -->
      <!-- C6: AI 修改对话面板（右侧浮动；projectId 绑定后显示） -->
      <ModifyPanel />
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
            :class="`page-status-${page.status}`"
          >
            <div class="page-item-left">
              <span class="page-order">第 {{ page.page_order }} 页</span>
              <span class="page-node">关联节点：{{ page.node_id }}</span>
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
import { ref, computed, onMounted, watch } from "vue";
import AppShell from "../components/layout/AppShell.vue";
import OutlineEditor from "../components/teacher/OutlineEditor.vue";
import ModifyPanel from "../components/teacher/ModifyPanel.vue";
import { useGenerationStore } from "../stores/generationStore";
import { useOutlineStore } from "../stores/outlineStore";
import { useInteractiveStore } from "../stores/interactiveStore";
import { useIntentStore } from "../stores/intentStore";
import { useModifyStore } from "../stores/modifyStore";
import { teacherV1Api } from "../services/v1";
import { API_BASE, AI_API_BASE } from "../config/api";

const generationStore = useGenerationStore();
const outlineStore = useOutlineStore();
const interactiveStore = useInteractiveStore();
const intentStore = useIntentStore();
const modifyStore = useModifyStore();

// 阶段：outline | generating | pages
const currentPhase = ref("outline");
const generationMode = ref("");
const generateMode = ref("page_incremental");
const genError = ref("");
const generationPages = ref([]);
const regeneratingPageId = ref("");
const previewFrameSrc = ref("");

// 是否有参考资料
const hasEvidence = computed(() => {
  try {
    const raw = window.localStorage.getItem("fuww_s2_evidence_packet");
    return !!raw;
  } catch {
    return false;
  }
});

// 需要互动资源的节点（大纲中标记为 interactive / quiz 的节点）
const interactiveNodes = computed(() =>
  (outlineStore.nodes || []).filter(
    (n) => n.node_type === "interactive" || n.node_type === "quiz",
  ),
);

onMounted(async () => {
  // 恢复 S1 会话/意图（刷新或直接进入 S3 时 store 内存为空，
  // 不恢复会导致 sessionId 缺失 → AI 生成大纲被 "缺少 session_id" 拦截）
  intentStore.initialize();
  if (typeof window !== "undefined") {
    generationMode.value =
      window.localStorage.getItem(
        `fuww_s2_generation_mode:${intentStore.sessionId}`,
      ) || "";
  }

  // C6: 绑定修改面板到当前课件项目
  // 优先用 generation_id（S3 生成后产生），其次用 localStorage 持久化的 last_gen_id
  const lastGenId =
    typeof window !== "undefined"
      ? window.localStorage.getItem("fuww_last_gen_id") || ""
      : "";
  if (lastGenId) {
    modifyStore.bindProject(lastGenId);
    await modifyStore.loadVersionHistory();
  }
  // 尝试从 localStorage 恢复大纲
  const restored = outlineStore.restore();
  if (restored && outlineStore.isConfirmed) {
    currentPhase.value = "generating";
  }
  // 恢复最近生成记录
  generationStore.restoreLastGenId();
  if (generationStore.lastGenId) {
    interactiveStore.setGenerationId(generationStore.lastGenId);
    await loadGenerationStatus();
  }
});

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
      const raw = window.localStorage.getItem("fuww_s2_evidence_packet");
      if (raw) evidence = JSON.parse(raw);
    } catch {}

    generationStore.setGenerateProgress(15, "创建生成任务");
    const resp = await teacherV1Api.generation.createGeneration({
      session_id: intentStore.sessionId,
      outline_id: outlineStore.outline_id,
      outline_version: outlineStore.outline_version,
      outline_confirmed: true,
      template_id: "default",
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
    await interactiveStore.pollAssetStatus(node.node_id);
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
  import("vue-router").then(({ useRouter }) => {
    const router = useRouter();
    router.push({ name: "S4Version" });
  });
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
  padding: 20px;
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
