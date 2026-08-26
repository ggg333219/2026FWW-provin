import { defineStore } from 'pinia'
import { teacherV1Api } from '../services/v1'

/**
 * 前端节点 → 预览渲染节点映射。
 * 页面编辑节点用 scriptText / nodeId 等字段，后端渲染器读取 script / content /
 * node_type / key_points / segments 等标准字段，这里做一次轻量归一，
 * 保证「预览内容与结构化数据完全同步一致」。
 */
function toPreviewNodes(nodes) {
  return (Array.isArray(nodes) ? nodes : []).map((node) => {
    const n = { ...node }
    if (!n.script && n.scriptText) n.script = n.scriptText
    if (!n.content && n.scriptText) n.content = n.scriptText
    if (n.nodeId && !n.node_id) n.node_id = n.nodeId
    if (!n.node_type && !n.type) n.node_type = ''
    if (!n.title) n.title = n.node_title || ''
    return n
  })
}

/**
 * S3 讲稿生成 Store (Studio)
 *
 * 对应讲稿生成与节点编辑模块的状态管理，包括：
 * - 讲稿内容与结构化节点树
 * - 节点编辑与版本
 * - AI 生成状态
 * - 音频生成状态
 * - gen/create、gen/status、gen/modify、gen/preview
 *
 * 注意：轮询逻辑在 S3StudioPage.vue 中实现，不在此处。
 */
export const useGenerationStore = defineStore('generation', {
  state: () => ({
    /** 当前页讲稿文本（S2 兼容） */
    currentScript: '',

    /** 当前页结构化节点树 */
    currentScriptNodes: [],
    // currentScriptNodes[i] 结构参考：
    // {
    //   id: string,
    //   nodeId: string,
    //   title: string,
    //   summary: string,
    //   content: string,
    //   scriptText: string,
    //   status: 'pending' | 'generating' | 'completed'
    // }

    /** 最近一次 S3 全流程生成的 generation_id，供 S4 版本管理读取。 */
    lastGenId: '',

    /** 当前页音频（S2 兼容） */
    currentPageAudio: null,
    audioGenerating: false,

    /** AI 生成状态 */
    isGenerating: false,
    scriptSaving: false,
    generateProgress: 0,
    generateStageText: '',

    /** S3 生成结果的 HTML 预览，避免依赖旧的课件图片接口。 */
    previewHtml: '',

    /** 预览渲染状态（持久化到 localStorage，刷新/重试后恢复） */
    previewLoading: false,
    previewGenId: '',
    previewVersion: 0,

    /** 迭代同步通知（S2 兼容） */
    iterationSyncNotice: ''
  }),

  getters: {
    /** S2 兼容：音频是否正在生成 */
    isGeneratingAudio: (state) => state.audioGenerating,
    /** S2 兼容：讲稿是否正在保存 */
    isSaving: (state) => state.scriptSaving,
    /** S2 兼容：是否有节点 */
    hasNodes: (state) => state.currentScriptNodes.length > 0
  },

  actions: {
    setScript(script) {
      this.currentScript = script
    },

    setNodes(nodes) {
      this.currentScriptNodes = nodes
    },

    /** 记录可被 S4 使用的生成 ID，并支持刷新后的工作流续接。 */
    setLastGenId(genId) {
      const normalized = String(genId || '').trim()
      if (!normalized) return ''
      this.lastGenId = normalized
      try {
        window.localStorage.setItem('fuww_last_gen_id', normalized)
      } catch (error) {
        console.warn('[generationStore] 持久化 generation_id 失败', error)
      }
      return normalized
    },

    /** 从 localStorage 恢复最近一次成功生成的 ID。 */
    restoreLastGenId() {
      if (this.lastGenId) return this.lastGenId
      try {
        const cached = window.localStorage.getItem('fuww_last_gen_id')
        if (cached) this.lastGenId = cached
      } catch (error) {
        console.warn('[generationStore] 恢复 generation_id 失败', error)
      }
      return this.lastGenId
    },

    /**
     * 创建 S3 全流程生成任务。响应统一兼容 Go 网关、Python 服务与 Mock 形态。
     */
    async createCoursewareGeneration(request) {
      const response = await teacherV1Api.generation.createGeneration(request)
      const task = response?.data || response || {}
      const generationId = task.generation_id || task.gen_id || task.generationId || task.genId
      if (generationId) this.setLastGenId(generationId)
      return task
    },

    /** 查询生成任务状态，并统一兼容 progress / progress_pct。 */
    async getCoursewareGenerationStatus(taskId) {
      const response = await teacherV1Api.generation.getGenerationStatus(taskId)
      return response?.data || response || {}
    },

    /**
     * 轮询全流程生成任务，并把完成后的节点树回填到 S3 编辑状态。
     */
    async waitForCoursewareGeneration(taskId, { intervalMs = 500, maxAttempts = 240 } = {}) {
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        const status = await this.getCoursewareGenerationStatus(taskId)
        const progress = Number(status.progress_pct ?? (Number(status.progress || 0) * 100))
        this.setGenerateProgress(Number.isFinite(progress) ? progress : 0, status.stage_text || '正在生成课件')

        if (['done', 'completed', 'success'].includes(status.status)) {
          const nodes = Array.isArray(status.nodes) ? status.nodes : []
          this.setNodes(nodes)
          this.setScript(nodes.map((node) => node.script || node.content || node.summary || '').filter(Boolean).join('\n\n'))
          this.setGenerateProgress(100, '生成完成')
          return status
        }
        if (['failed', 'error'].includes(status.status)) {
          throw new Error(status.error || '课件生成失败')
        }
        await new Promise((resolve) => setTimeout(resolve, intervalMs))
      }
      throw new Error('课件生成超时，请稍后在版本管理中查看任务结果')
    },

    /**
     * 渲染课件预览（S3 → S4 版本快照双通道）。
     *
     * 传 genId 时按版本快照恢复并渲染（返回快照节点，可回填编辑区）；
     * 未传 genId 时用当前节点树 inline 渲染。渲染结果缓存到 localStorage。
     */
    async renderCoursewarePreview(courseName = '课件预览', { genId = '', version = null, backfillNodes = false } = {}) {
      this.previewLoading = true
      try {
        const normalizedGenId = String(genId || '').trim()
        const hasNodes = Array.isArray(this.currentScriptNodes) && this.currentScriptNodes.length > 0
        if (!normalizedGenId && !hasNodes) {
          this.previewHtml = ''
          return ''
        }
        const response = await teacherV1Api.generation.preview(
          normalizedGenId
            ? { gen_id: normalizedGenId, version, course_name: courseName }
            : { nodes: toPreviewNodes(this.currentScriptNodes), course_name: courseName }
        )
        const payload = response?.data || response || {}
        const html = String(payload.html || '')
        if (!html) throw new Error('预览服务未返回 HTML')

        this.previewHtml = html
        if (payload.generation_id) this.previewGenId = String(payload.generation_id)
        if (payload.version_number) this.previewVersion = Number(payload.version_number)

        // 版本快照返回的节点回填编辑区，保证「预览内容与结构化数据完全同步一致」
        if (backfillNodes && Array.isArray(payload.nodes) && payload.nodes.length > 0) {
          this.setNodes(payload.nodes)
        }
        this.cachePreview(courseName)
        return html
      } finally {
        this.previewLoading = false
      }
    },

    /** 把最近一次成功渲染的预览与节点写入 localStorage，供刷新/重试恢复。 */
    cachePreview(courseName = '课件预览') {
      try {
        const key = this.previewGenId || 'draft'
        window.localStorage.setItem(`fuww_preview_cache:${key}`, JSON.stringify({
          gen_id: this.previewGenId,
          version: this.previewVersion,
          html: this.previewHtml,
          nodes: this.currentScriptNodes,
          course_name: courseName,
          ts: Date.now()
        }))
      } catch (error) {
        console.warn('[generationStore] 预览缓存失败', error)
      }
    },

    /** 读取指定 gen_id 的本地预览缓存；无参数时读取最近一次缓存。 */
    loadPreviewCache(genId = '') {
      try {
        const key = genId ? `fuww_preview_cache:${genId}` : 'fuww_preview_cache:draft'
        const raw = window.localStorage.getItem(key)
        if (!raw) return null
        const cache = JSON.parse(raw)
        if (!cache || !cache.html) return null
        return cache
      } catch (error) {
        console.warn('[generationStore] 预览缓存读取失败', error)
        return null
      }
    },

    /**
     * 刷新/重试后恢复预览：
     *   1) 本地缓存即时秒出（优先 gen 专属缓存，其次草稿缓存）
     *   2) 再按 gen_id 从版本快照拉取最新；后端确有条目时才覆盖缓存，
     *      避免无快照时用空态覆盖本地已有预览。
     * 仅恢复 HTML，不回填编辑区节点树，避免覆盖正在编辑的页面节点。
     */
    async restorePreview(genId = this.restoreLastGenId(), { version = null } = {}) {
      const normalizedGenId = String(genId || '').trim()
      if (!normalizedGenId) return ''
      // 1) 本地缓存即时恢复
      const cache = this.loadPreviewCache(normalizedGenId) || this.loadPreviewCache('')
      if (cache && cache.html) {
        this.previewHtml = cache.html
        this.previewVersion = cache.version || 0
      }
      // 2) 后端版本快照拉取最新（有内容才覆盖缓存）
      try {
        this.previewLoading = true
        const response = await teacherV1Api.generation.preview({
          gen_id: normalizedGenId,
          version,
          course_name: cache?.course_name || '课件预览'
        })
        const payload = response?.data || response || {}
        const fetchedHtml = String(payload.html || '')
        if (Number(payload.node_count) > 0 && fetchedHtml) {
          this.previewHtml = fetchedHtml
          if (payload.generation_id) this.previewGenId = String(payload.generation_id)
          if (payload.version_number) this.previewVersion = Number(payload.version_number)
          this.cachePreview(cache?.course_name || '课件预览')
        }
        return this.previewHtml
      } catch (error) {
        console.warn('[generationStore] 从版本快照恢复预览失败，使用缓存', error)
        return this.previewHtml
      } finally {
        this.previewLoading = false
      }
    },

    clearPreview() {
      const cachedGenId = this.previewGenId
      this.previewHtml = ''
      this.previewLoading = false
      this.previewGenId = ''
      this.previewVersion = 0
      try {
        window.localStorage.removeItem('fuww_preview_cache:draft')
        if (cachedGenId) window.localStorage.removeItem(`fuww_preview_cache:${cachedGenId}`)
      } catch (error) {
        console.warn('[generationStore] 预览缓存清理失败', error)
      }
    },

    updateNode(index, patch) {
      if (index >= 0 && index < this.currentScriptNodes.length) {
        this.currentScriptNodes[index] = {
          ...this.currentScriptNodes[index],
          ...patch
        }
      }
    },

    setPageAudio(audio) {
      this.currentPageAudio = audio
    },

    setAudioGenerating(generating) {
      this.audioGenerating = generating
    },

    setGenerating(generating) {
      this.isGenerating = generating
      if (!generating) {
        this.generateProgress = 0
        this.generateStageText = ''
      }
    },

    setSaving(saving) {
      this.scriptSaving = saving
    },

    setGenerateProgress(progress, stageText) {
      this.generateProgress = progress
      if (stageText) this.generateStageText = stageText
    },

    setIterationSyncNotice(notice) {
      this.iterationSyncNotice = notice
    }
  }
})
