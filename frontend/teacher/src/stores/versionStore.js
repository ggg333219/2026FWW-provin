import { defineStore } from "pinia";
import { teacherV1Api } from "../services/v1";
import { API_BASE } from "../config/api";
import { projectModifyApi } from "../services/v1/projectModifyApi";

function diffNodes(leftNodes = [], rightNodes = [], leftVersion, rightVersion) {
  const leftMap = new Map(leftNodes.map((node, index) => [node.node_id, { node, index }]));
  const rightMap = new Map(rightNodes.map((node, index) => [node.node_id, { node, index }]));
  const added = [], removed = [], changed = [], same = [];
  for (const [id, entry] of rightMap) {
    const old = leftMap.get(id);
    if (!old) { added.push({ node_id: id, title: entry.node.title || id }); continue; }
    const fields = [];
    for (const field of ["title", "summary", "content", "script", "node_type", "citation_refs", "source_chunk_ids", "layout_hint", "font_size_hint", "slide_background", "metadata"]) {
      if (JSON.stringify(old.node[field] ?? null) !== JSON.stringify(entry.node[field] ?? null)) fields.push(field);
    }
    if (old.index !== entry.index) fields.push("order");
    (fields.length ? changed : same).push({ node_id: id, title: entry.node.title || id, changes: fields });
  }
  for (const [id, entry] of leftMap) if (!rightMap.has(id)) removed.push({ node_id: id, title: entry.node.title || id });
  return { v1: leftVersion, v2: rightVersion, added, removed, changed, same };
}

function snapshotNodes(data = {}) {
  if (Array.isArray(data.nodes) && data.nodes.length) return data.nodes;
  if (Array.isArray(data.snapshot?.content)) return data.snapshot.content;
  if (Array.isArray(data.snapshot?.content?.nodes)) return data.snapshot.content.nodes;
  return [];
}

function snapshotOutline(data = {}) {
  const outline = data.snapshot?.outline
  return outline && typeof outline === 'object' && !Array.isArray(outline) ? outline : null
}

/** 后端/Mock 返回相对下载路径时补齐 API_BASE，保证跨端口可下载；blob/data 保持原样 */
function normalizeDownloadUrl(url) {
  if (!url) return "";
  if (
    /^https?:\/\//.test(url) ||
    url.startsWith("blob:") ||
    url.startsWith("data:")
  )
    return url;
  if (url.startsWith("/")) return `${API_BASE}${url}`;
  return url;
}

/**
 * S4 版本管理 + 导出 Store
 */
export const useVersionStore = defineStore("version", {
  state: () => ({
    /** 版本列表 */
    versions: [],
    /** 当前加载的版本详情（含 nodes_snapshot） */
    currentVersionDetail: null,
    comparison: null,
    comparing: false,
    /** 当前 generation_id */
    genId: "",
    /** 当前 courseware project_id；存在时版本历史以项目快照为准 */
    projectId: "",
    /** 修改指令列表 */
    pendingChanges: [],
    /** 发布/锁定状态 */
    publishState: {
      isPublishing: false,
      lastPublishedAt: null,
    },

    // ---- 导出 ----
    /** 导出任务 ID */
    exportJobId: "",
    /** 导出状态: idle | pending | exporting | done | failed */
    exportStatus: "idle",
    /** 导出格式 */
    exportFormat: "pptx",
    /** 导出下载地址 */
    exportDownloadUrl: "",
    /** 多格式导出文件 { pptx, docx, html } */
    exportFiles: {},
    /** 导出错误 */
    exportError: "",
    /** PPTX 导出质量报告 */
    exportQualityReport: null,

    loading: false,
    error: "",
  }),

  getters: {
    versionCount: (state) => state.versions.length,
    hasPendingChanges: (state) =>
      state.pendingChanges.some((c) => c.status === "pending"),
    latestVersion: (state) =>
      state.versions.length > 0 ? state.versions[0] : null,
    isExportDone: (state) => state.exportStatus === "done",
    isCurrentLocked: (state) => !!state.currentVersionDetail?.locked,
    exportIsActive: (state) =>
      ["pending", "exporting"].includes(state.exportStatus),
  },

  actions: {
    // ================================================================
    // 版本历史
    // ================================================================
    async loadVersions(genId) {
      if (!genId) return;
      this.genId = genId;
      this.loading = true;
      this.error = "";
      try {
        const raw = await teacherV1Api.version.history(genId);
        const data = raw?.data || raw || {};
        this.versions = (data.versions || []).map((v) => ({
          id: v.id,
          version: v.version_number,
          title: v.summary || `版本 ${v.version_number}`,
          summary: v.summary || "",
          locked: v.locked || false,
          createdAt: v.created_at || "",
          createdBy: "",
        }));
      } catch (err) {
        this.error = err.message || "加载版本历史失败";
        console.warn("[versionStore] 加载版本失败", err);
      } finally {
        this.loading = false;
      }
    },

    async loadVersion(genId, versionNumber = null) {
      if (!genId) return;
      this.loading = true;
      try {
        const raw = await teacherV1Api.version.load(genId, versionNumber);
        const data = raw?.data || raw || {};
        this.currentVersionDetail = {
          version: data.version_number,
          id: data.id,
          nodes: data.nodes_snapshot || [],
          pageBindings: data.page_bindings || [],
          presentation: data.presentation || {},
          generationInstructionSet: data.metadata?.generation_instruction_set || {},
          summary: data.summary || "",
          locked: data.locked || false,
          createdAt: data.created_at || "",
        };
        return this.currentVersionDetail;
      } catch (err) {
        console.warn("[versionStore] 加载版本详情失败", err);
        this.currentVersionDetail = null;
      } finally {
        this.loading = false;
      }
    },

    async loadProjectVersions(projectId) {
      if (!projectId) return;
      if (this.projectId !== projectId) this.currentVersionDetail = null;
      this.projectId = projectId;
      this.loading = true;
      this.error = "";
      try {
        const raw = await projectModifyApi.versions(projectId);
        const data = raw?.data || raw || {};
        this.versions = (data.items || []).map((v) => ({
          id: v.version_id,
          version: v.version_no,
          title: v.version_summary || v.modify_instruction || `版本 ${v.version_no}`,
          summary: v.version_summary || v.modify_instruction || "",
          locked: false,
          createdAt: v.created_at || "",
          nodes: v.nodes || [],
          presentation: v.presentation || {},
        })).sort((left, right) => Number(right.version) - Number(left.version));
      } catch (err) {
        this.versions = [];
        this.currentVersionDetail = null;
        this.error = err.message || "加载项目版本历史失败";
        throw err;
      } finally { this.loading = false; }
    },

    async loadProjectVersion(projectId, versionNumber = null) {
      if (!projectId) return null;
      if (!this.versions.length || this.projectId !== projectId) await this.loadProjectVersions(projectId);
      const item = versionNumber == null
        ? this.versions[0]
        : this.versions.find((v) => Number(v.version) === Number(versionNumber));
      if (!item) { this.currentVersionDetail = null; return null; }
      this.loading = true;
      try {
        const raw = await projectModifyApi.versionDetail(projectId, item.id);
        const data = raw?.data || raw || {};
        this.currentVersionDetail = {
          version: data.version_no,
          id: data.version_id,
          nodes: snapshotNodes(data),
          outline: snapshotOutline(data),
          pageBindings: data.page_bindings || data.snapshot?.page_bindings || [],
          presentation: data.presentation || data.snapshot?.style || {},
          generationInstructionSet: data.generation_instruction_set || data.snapshot?.generation_instruction_set || {},
          summary: data.version_summary || data.change_note || "",
          locked: false,
          createdAt: data.created_at || "",
        };
        return this.currentVersionDetail;
      } finally { this.loading = false; }
    },

    async compareProjectVersions(projectId, leftVersion, rightVersion) {
      if (!projectId || !leftVersion || !rightVersion || leftVersion === rightVersion) return null;
      this.comparing = true;
      try {
        const leftItem = this.versions.find((v) => Number(v.version) === Number(leftVersion));
        const rightItem = this.versions.find((v) => Number(v.version) === Number(rightVersion));
        const [leftRaw, rightRaw] = await Promise.all([
          projectModifyApi.versionDetail(projectId, leftItem.id),
          projectModifyApi.versionDetail(projectId, rightItem.id),
        ]);
        const left = leftRaw?.data || leftRaw || {};
        const right = rightRaw?.data || rightRaw || {};
        this.comparison = diffNodes(snapshotNodes(left), snapshotNodes(right), leftVersion, rightVersion);
        return this.comparison;
      } catch (err) {
        this.error = err.message || "版本对比失败";
        throw err;
      } finally { this.comparing = false; }
    },

    async rollbackProject(projectId, targetVersion) {
      const item = this.versions.find((v) => Number(v.version) === Number(targetVersion));
      if (!projectId || !item) throw new Error("未找到要回滚的项目版本");
      this.loading = true;
      try {
        const result = await projectModifyApi.rollback(projectId, item.id);
        await this.loadProjectVersions(projectId);
        await this.loadProjectVersion(projectId);
        return result;
      } catch (err) {
        this.error = err.message || "创建回滚分支失败";
        throw err;
      } finally { this.loading = false; }
    },

    async compareVersions(genId, leftVersion, rightVersion) {
      if (!genId || !leftVersion || !rightVersion || leftVersion === rightVersion) return null;
      this.comparing = true;
      this.error = "";
      try {
        const [leftRaw, rightRaw] = await Promise.all([
          teacherV1Api.version.load(genId, leftVersion),
          teacherV1Api.version.load(genId, rightVersion),
        ]);
        const left = leftRaw?.data || leftRaw || {};
        const right = rightRaw?.data || rightRaw || {};
        const leftNodes = Array.isArray(left.nodes_snapshot) ? left.nodes_snapshot : [];
        const rightNodes = Array.isArray(right.nodes_snapshot) ? right.nodes_snapshot : [];
        this.comparison = diffNodes(leftNodes, rightNodes, leftVersion, rightVersion);
        return this.comparison;
      } catch (err) {
        this.error = err.message || "版本对比失败";
        throw err;
      } finally { this.comparing = false; }
    },

    // ================================================================
    // 回滚
    // ================================================================
    async rollbackTo(genId, targetVersion) {
      if (!genId) return;
      this.loading = true;
      this.error = "";
      try {
        const result = await teacherV1Api.version.rollback(
          genId,
          targetVersion,
        );
        // 回滚后刷新列表
        await this.loadVersions(genId);
        await this.loadVersion(genId);
        return result;
      } catch (err) {
        this.error = err.message || "回滚失败";
        throw err;
      } finally {
        this.loading = false;
      }
    },

    // ================================================================
    // 锁定
    // ================================================================
    async lockVersion(genId) {
      if (!genId) return;
      this.loading = true;
      this.error = "";
      try {
        const result = await teacherV1Api.version.lock(genId);
        await this.loadVersions(genId);
        await this.loadVersion(genId);
        return result;
      } catch (err) {
        this.error = err.message || "锁定失败";
        throw err;
      } finally {
        this.loading = false;
      }
    },

    // ================================================================
    // 修改指令
    // ================================================================
    addChange(change) {
      this.pendingChanges.push({
        id: change.id || `change_${Date.now()}`,
        type: change.type || "update_node",
        target: change.target || "",
        before: change.before || null,
        after: change.after || null,
        status: "pending",
        appliedAt: null,
      });
    },

    applyChange(changeId) {
      const change = this.pendingChanges.find((c) => c.id === changeId);
      if (change) {
        change.status = "applied";
        change.appliedAt = new Date().toISOString();
      }
    },

    /** 提交所有 pending 修改到后端 */
    async submitModify(genId) {
      if (!genId || !this.currentVersionDetail?.nodes) {
        this.error = "无可用节点，无法提交修改";
        return;
      }
      const pending = this.pendingChanges.filter((c) => c.status === "pending");
      if (!pending.length) {
        this.error = "无待处理的修改指令";
        return;
      }
      this.loading = true;
      this.error = "";
      try {
        // 构建 commands 格式
        const commands = pending.map((c) => ({
          type: c.type,
          node_id: c.target,
          content: c.after || "",
        }));
        await teacherV1Api.version.modify(genId, commands);
        // 全部标记为已应用
        pending.forEach((c) => {
          c.status = "applied";
          c.appliedAt = new Date().toISOString();
        });
        // 刷新版本列表
        await this.loadVersions(genId);
      } catch (err) {
        this.error = err.message || "修改提交失败";
        throw err;
      } finally {
        this.loading = false;
      }
    },

    rejectChange(changeId) {
      const change = this.pendingChanges.find((c) => c.id === changeId);
      if (change) {
        change.status = "rejected";
      }
    },

    clearPending() {
      this.pendingChanges = [];
      this.comparison = null;
      this.comparing = false;
    },

    // ================================================================
    // 导出
    // ================================================================
    async startExport(genId, format = "pptx", version = null, coursewareTitle = "", nodes = [], projectId = "", generationInstructionSet = {}) {
      if (!genId) return;
      this.exportStatus = "pending";
      this.exportFormat = format;
      this.exportError = "";
      this.exportQualityReport = null;
      this.exportFiles = {};
      try {
        // 统一兼容 {code,message,data} 信封（Mock）与裸响应（FastAPI 网关）
        const response = await teacherV1Api.version.exportCreate(genId, format, version, coursewareTitle, nodes, projectId, generationInstructionSet);
        const job = response?.data || response || {};
        this.exportJobId = job.job_id || "";
        this.exportStatus = job.status === "done" ? "done" : "pending";
        this.exportDownloadUrl = normalizeDownloadUrl(job.download_url);
        this.exportFiles = Object.fromEntries(
          Object.entries(job.files || {}).map(([format, url]) => [format, normalizeDownloadUrl(url)]),
        );
        // 如果不是立即完成，启动轮询
        if (this.exportStatus !== "done" && this.exportJobId) {
          this._pollExport();
        }
      } catch (err) {
        this.exportStatus = "failed";
        this.exportError = err.message || "导出任务创建失败";
      }
    },

    async _pollExport() {
      const maxPolls = 30; // 最多轮询 30 次（约 60 秒）
      let polls = 0;
      const poll = async () => {
        if (polls >= maxPolls || !this.exportJobId) {
          if (this.exportStatus === "pending") {
            this.exportStatus = "failed";
            this.exportError = "导出超时";
          }
          return;
        }
        polls++;
        try {
          const response = await teacherV1Api.version.exportStatus(
            this.exportJobId,
          );
          const job = response?.data || response || {};
          this.exportStatus = job.status || "pending";
          this.exportDownloadUrl = normalizeDownloadUrl(job.download_url);
          this.exportFiles = Object.fromEntries(
            Object.entries(job.files || {}).map(([format, url]) => [format, normalizeDownloadUrl(url)]),
          );
          this.exportError = job.error || "";
          this.exportQualityReport = job.quality_report || null;
          if (this.exportStatus === "done" || this.exportStatus === "failed") {
            return;
          }
          // 继续轮询
          setTimeout(poll, 2000);
        } catch (err) {
          if (polls >= maxPolls) {
            this.exportStatus = "failed";
            this.exportError = err.message || "导出状态查询失败";
          } else {
            setTimeout(poll, 2000);
          }
        }
      };
      poll();
    },

    resetExport() {
      this.exportJobId = "";
      this.exportStatus = "idle";
      this.exportFormat = "pptx";
      this.exportDownloadUrl = "";
      this.exportFiles = {};
      this.exportError = "";
      this.exportQualityReport = null;
    },

    // ================================================================
    // 清理
    // ================================================================
    reset() {
      this.versions = [];
      this.currentVersionDetail = null;
      this.genId = "";
      this.projectId = "";
      this.pendingChanges = [];
      this.error = "";
      this.resetExport();
    },
  },
});
