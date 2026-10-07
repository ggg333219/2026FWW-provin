import { defineStore } from 'pinia'
import { projectModifyApi } from '../services/v1/projectModifyApi'

const PROJECT_KEY = 'fuww_active_courseware_project'

const unwrap = (response) => response?.data || response || {}

export const useCoursewareProjectStore = defineStore('coursewareProject', {
  state: () => ({
    projectId: '',
    project: null,
    draft: null,
    items: [],
    loading: false,
    saving: false,
    saveState: 'idle', // idle | dirty | saving | saved | error
    savedAt: '',
    error: '',
    _timer: 0,
    _lastDraft: null,
    _saveQueue: Promise.resolve(),
  }),
  getters: {
    saveLabel: (state) => ({
      dirty: '有未保存变更', saving: '正在保存…',
      saved: state.savedAt ? `已保存草稿 · ${new Date(state.savedAt).toLocaleTimeString()}` : '已保存草稿',
      error: '保存失败 · 点击重试',
    })[state.saveState] || '',
  },
  actions: {
    restoreActiveId() {
      if (!this.projectId && typeof window !== 'undefined') this.projectId = window.localStorage.getItem(PROJECT_KEY) || ''
      return this.projectId
    },
    setActive(project) {
      const id = String(project?.id || project?.project_id || project || '')
      if (id !== this.projectId) {
        if (this._timer) clearTimeout(this._timer)
        this._timer = 0
        this.project = null
        this.draft = null
        this._lastDraft = null
        this.saveState = 'idle'
        this.savedAt = ''
        this.error = ''
      }
      this.projectId = id
      if (project && typeof project === 'object') this.project = project
      if (typeof window !== 'undefined' && id) window.localStorage.setItem(PROJECT_KEY, id)
    },
    async loadProjects() {
      this.loading = true; this.error = ''
      try {
        const data = unwrap(await projectModifyApi.list())
        this.items = Array.isArray(data.items) ? data.items : (Array.isArray(data) ? data : [])
        return this.items
      } catch (error) { this.error = error?.message || '课件列表加载失败'; throw error }
      finally { this.loading = false }
    },
    async create(title) {
      const data = unwrap(await projectModifyApi.create({ title }))
      this.setActive(data); this.items.unshift(data)
      return data
    },
    async remove(projectId) {
      await projectModifyApi.remove(projectId)
      this.items = this.items.filter((item) => String(item.id || item.project_id) !== String(projectId))
      if (String(this.projectId) === String(projectId)) {
        this.projectId = ''; this.project = null; this.draft = null
        if (typeof window !== 'undefined') window.localStorage.removeItem(PROJECT_KEY)
      }
    },
    async resume(projectId, isCurrent = () => true) {
      const data = unwrap(await projectModifyApi.context(projectId))
      if (!isCurrent()) return data
      this.setActive(data.project || { id: projectId })
      this.draft = data.draft || data.draft_json || null
      return data
    },
    async updateStep(step) {
      if (!this.projectId) return
      await projectModifyApi.updateStep(this.projectId, step)
      if (this.project) this.project.current_step = step
    },
    scheduleSave(draft, delay = 1500) {
      if (!this.projectId) return
      this._lastDraft = draft; this.saveState = 'dirty'
      if (this._timer) clearTimeout(this._timer)
      this._timer = setTimeout(() => this.saveNow().catch(() => {}), delay)
    },
    async saveNow(draft = this._lastDraft) {
      if (!this.projectId || !draft) return
      const projectId = this.projectId
      if (this._timer) { clearTimeout(this._timer); this._timer = 0 }
      this._lastDraft = draft
      const save = async () => {
        this.saving = true
        if (this.projectId === projectId) { this.saveState = 'saving'; this.error = '' }
        try {
          const data = unwrap(await projectModifyApi.saveDraft(projectId, draft))
          if (this.projectId === projectId) {
            this.draft = draft
            this.savedAt = data.saved_at || data.project?.updated_at || new Date().toISOString()
            this.saveState = 'saved'
          }
        } catch (error) {
          if (this.projectId === projectId) {
            this.error = error?.message || '草稿保存失败'
            this.saveState = 'error'
          }
          throw error
        } finally {
          this.saving = false
        }
      }
      const queued = this._saveQueue.catch(() => {}).then(save)
      this._saveQueue = queued
      return queued
    },
  },
})
