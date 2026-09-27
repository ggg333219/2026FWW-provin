/**
 * 课件草稿的本地快照缓存。
 *
 * 该快照用于刷新 / 返回时把项目草稿恢复到 S3（大纲、页面管理与样式）。
 * 历史实现写死一个全局 key 且读取时不校验归属，导致新建或切换课件后，
 * S3 会把上一份课件的大纲与页面节点当作本项目快照恢复。
 * 这里统一按 project_id 归属存放，并提供清理入口。
 */

const RESUME_DRAFT_KEY = 'fuww_courseware_resume_draft'

/** 项目维度的草稿快照 key。 */
export const resumeDraftKey = (projectId) => `${RESUME_DRAFT_KEY}:${projectId}`

/** 写入本项目草稿快照（快照内冗余 project_id，读取时二次校验）。 */
export function writeResumeDraft(projectId, draft) {
  if (!projectId || typeof window === 'undefined') return
  try {
    window.localStorage.setItem(
      resumeDraftKey(projectId),
      JSON.stringify({ ...draft, project_id: projectId })
    )
  } catch (error) {
    console.warn('[coursewareDraft] 草稿快照写入失败', error)
  }
}

/** 读取本项目草稿快照；归属对不上（含历史无归属数据）一律清除并忽略。 */
export function readResumeDraft(projectId) {
  if (!projectId || typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(resumeDraftKey(projectId))
    if (!raw) return null
    const draft = JSON.parse(raw)
    if (!draft || String(draft.project_id || '') !== String(projectId)) {
      window.localStorage.removeItem(resumeDraftKey(projectId))
      return null
    }
    return draft
  } catch {
    return null
  }
}

/** 清除某个项目的草稿快照。 */
export function clearResumeDraft(projectId) {
  if (!projectId || typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(resumeDraftKey(projectId))
  } catch (error) {
    console.warn('[coursewareDraft] 草稿快照清理失败', error)
  }
}

/**
 * 清除历史遗留的全局草稿快照（旧版本写死的无归属 key）。
 * 新建课件时调用：新项目本就没有自己的快照，只需保证旧 key 不再被误读。
 */
export function clearLegacyResumeDraft() {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(RESUME_DRAFT_KEY)
  } catch (error) {
    console.warn('[coursewareDraft] 历史草稿快照清理失败', error)
  }
}
