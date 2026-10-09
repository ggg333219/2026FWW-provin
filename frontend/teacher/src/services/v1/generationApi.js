import { AI_API_BASE } from "../../config/api";
import { requestJson } from "./request";

// 内容生成会触发多个节点的 LLM 调用，不能使用 request.js 的通用 10 秒上限。
// 创建接口只负责提交异步任务；状态查询仍保持默认短超时。
const CONTENT_GENERATE_TIMEOUT_MS = 120000;

/**
 * S3 讲稿生成 API (Studio)
 *
 * 负责讲稿的生成、节点树管理、分段与音频生成。
 *
 * 注意：S2 讲稿/节点 CRUD 方法在 coursewareApi.js 中，
 * 本文件仅包含 S3 gen API（生成 + 修改 + 预览）。
 */
export const teacherGenerationApi = {
  // ================================================================
  // gen API（S3 生成 + 修改 + 预览）
  // ================================================================

  /** 创建生成任务 (gen/create) */
  createGeneration: ({
    session_id,
    course_id,
    title,
    markdown,
    intent,
    evidence_packet,
    generation_instruction_set,
    template_id,
    // S3 规范 3.6 参数
    outline_id,
    outline_version,
    outline_confirmed,
    generate_mode,
    generation_scope,
    project_id
  } = {}) =>
    requestJson("/api/v1/gen/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: session_id || "",
        course_id,
        title: title || "",
        markdown: markdown || "",
        intent: intent || undefined,
        evidence_packet: evidence_packet || null,
        generation_instruction_set: generation_instruction_set || {},
        project_id: project_id || '',
        template_id: template_id || 'default',
        // 规范 3.6：确认大纲后必须传递完整 outline 上下文
        ...(outline_id
          ? {
              outline_id,
              outline_version,
              outline_confirmed: !!outline_confirmed,
              generate_mode: generate_mode || "page_incremental",
              generation_scope: generation_scope || "content_only",
            }
          : {}),
      }),
    }),

  /** 查询生成任务状态 (gen/status) */
  getGenerationStatus: (taskId) =>
    requestJson(`/api/v1/gen/status/${encodeURIComponent(taskId)}`),

  /** 提交修改命令 (gen/modify) */
  modifyNodes: ({ generation_id, commands, nodes } = {}) =>
    requestJson("/api/v1/gen/modify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        generation_id,
        commands: commands || [],
        nodes: nodes || [],
      }),
    }),

  /** 将当前内容、样式和证据引用固化为新的正式版本快照 */
  finalize: ({ generation_id, nodes, course_name, summary, outline_id, outline_version, page_bindings, presentation, generation_instruction_set } = {}) =>
    requestJson('/api/v1/gen/finalize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        generation_id: generation_id || '',
        nodes: nodes || [],
        course_name: course_name || '未命名课件',
        summary: summary || '教师保存的新版本',
        outline_id: outline_id || '',
        outline_version: outline_version || 0,
        page_bindings: page_bindings || [],
        presentation: presentation || {},
        generation_instruction_set: generation_instruction_set || {},
      })
    }),

  /** 获取预览 (gen/preview)
   *  支持两种调用：
   *    - inline nodes：直接渲染当前节点树
   *    - 版本快照：传 gen_id（可选 version），后端按版本恢复节点渲染
   */
  preview: ({ nodes, course_name, gen_id, version } = {}) =>
    requestJson("/api/v1/gen/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nodes: nodes || [],
        course_name: course_name || "课件预览",
        gen_id: gen_id || "",
        version: version || null,
      }),
    }),

  /** 生成 HTML 课件预览（deck-skill，直连 AI Engine） */
  skillDeckPreview: (params = {}) => {
    const {
      intent = {},
      evidence_packet = null,
      nodes = null,
      template_id = "deck-swiss-edu",
      palette = "klein-blue",
    } = params || {};
    return fetch(`${AI_API_BASE}/api/v1/skill/deck`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intent,
        evidence_packet,
        nodes,
        template_id,
        palette,
      }),
    }).then((r) => r.json());
  },

  // ================================================================
  // page API（S3 单页操作，规范 3.7~3.10）
  // ================================================================

  /** GET /api/v1/generations/{generation_id} 查询生成任务状态（规范 3.7） */
  getGeneration: (generationId) =>
    requestJson(`/api/v1/generations/${encodeURIComponent(generationId)}`),

  /** GET /api/v1/generations/{generation_id}/pages/{page_id} 查询单页（规范 3.8） */
  getPage: (generationId, pageId) =>
    requestJson(
      `/api/v1/generations/${encodeURIComponent(generationId)}/pages/${encodeURIComponent(pageId)}`,
    ),

  /** POST /api/v1/generations/{generation_id}/pages/{page_id}/regenerate 单页重生成（规范 3.9） */
  regeneratePage: (generationId, pageId, { reason, mode = "ai" } = {}) =>
    requestJson(
      `/api/v1/generations/${encodeURIComponent(generationId)}/pages/${encodeURIComponent(pageId)}/regenerate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: reason || "", mode }),
      },
    ),

  /** POST /api/v1/generations/{generation_id}/pages/{page_id}/revise AI修改页面（规范 3.10） */
  revisePage: (
    generationId,
    pageId,
    { message, base_version, auto_apply = false } = {},
  ) =>
    requestJson(
      `/api/v1/generations/${encodeURIComponent(generationId)}/pages/${encodeURIComponent(pageId)}/revise`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: message || "",
          base_version: base_version != null ? base_version : 1,
          auto_apply,
        }),
      },
    ),

  // ================================================================
  // content API（P1：大纲确认后的内容生成阶段）
  // 与 gen API 的区别：
  //   gen API = 全流程（outline → nodes → PPT）
  //   content API = 仅生成节点讲稿内容（outline → content），供教师确认后再生成 PPT
  // ================================================================

  /** POST /api/v1/gen/content — 为已确认大纲的节点生成讲稿内容 */
  generateContent: ({
    nodes,
    context_markdown = "",
    course_name = "课件",
    mode = "llm",
    enhanced = false,
    outline_id = "",
    outline_version = 0,
    outline_nodes = [],
    generation_instruction_set = {},
  } = {}) =>
    requestJson("/api/v1/gen/content", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      timeoutMs: CONTENT_GENERATE_TIMEOUT_MS,
      body: JSON.stringify({
        nodes: nodes || [],
        context_markdown,
        course_name,
        mode,
        enhanced,
        outline_id,
        outline_version,
        outline_nodes: outline_nodes || [],
        generation_instruction_set: generation_instruction_set || {},
      }),
    }),

  /** GET /api/v1/gen/content/status/:content_id — 查询内容生成状态 */
  getContentStatus: (contentId) =>
    requestJson(`/api/v1/gen/content/status/${encodeURIComponent(contentId)}`),

  /**
   * POST /api/v1/gen/content/modify — AI 修改单个节点内容（自然语言指令）
   *
   * nodes 必须带上：引擎侧是「基于当前节点内容做局部重生成」，只给一句指令
   * 等于让它凭空重写一节，老师看到的就是内容被换掉而不是被改好。
   * action 可留空，后端会按 message 兜底推断 simplify / expand / rewrite。
   */
  modifyContent: ({
    content_id,
    node_id,
    message,
    nodes = [],
    action = "",
    course_name = "",
    context_markdown = "",
    outline_id = "",
    outline_version = 0,
    intent = undefined,
  } = {}) =>
    requestJson("/api/v1/gen/content/modify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // 节点重生成会调用真实大模型，还要等引擎侧的异步任务轮询完成。
      timeoutMs: 120000,
      body: JSON.stringify({
        content_id: content_id || "",
        node_id: node_id || "",
        message: message || "",
        action: action || "",
        nodes: nodes || [],
        course_name: course_name || "",
        context_markdown: context_markdown || "",
        outline_id: outline_id || "",
        outline_version: outline_version || 0,
        intent: intent || undefined,
      }),
    }),
  /**
   * POST /api/v1/gen/content/modify-script — 讲稿 AI 编辑（只改当前节点讲稿文本，同步返回）。
   * 与 modifyContent（内容层整节点重生成）互补：教师只想润色讲稿时用这个。
   */
  modifyScript: ({ node_id, title, script, message, course_name } = {}) =>
    requestJson("/api/v1/gen/content/modify-script", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      timeoutMs: 120000,
      body: JSON.stringify({
        node_id,
        title: title || "",
        script: script || "",
        message: message || "",
        course_name: course_name || "课件",
      }),
    }),

  // ================================================================
  // 兼容旧接口（保留，Phase 4 清理）
  // ================================================================

  /** 获取增强讲稿（AI API 模式，已废弃，保留兼容） */
  getEnhancedScript: (params = {}) => {
    return fetch(`${AI_API_BASE}/generate-enhanced`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        markdown: params.markdown,
        course_name: params.courseName || "未命名课程",
        mode: params.mode || "llm",
      }),
    }).then((r) => r.json());
  },
};
