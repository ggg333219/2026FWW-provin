// 旧草稿的阶段名称只决定入口；任务与预览的真实状态决定能否进入审阅。
export function resolveS3Phase(legacyPhase, { outlineConfirmed = false, contentStatus = '', taskStatus = '', hasPreview = false, hasNodes = false } = {}) {
  if (legacyPhase === 'outline') return 'outline'
  if (legacyPhase === 'content') return outlineConfirmed ? 'content' : 'outline'
  if (['generating', 'pages', 'style', 'review'].includes(legacyPhase)) {
    if (['pending', 'generating', 'error'].includes(contentStatus)) return outlineConfirmed ? 'content' : 'outline'
    if (['pending', 'processing', 'generating', 'failed', 'error'].includes(taskStatus)) return outlineConfirmed ? 'content' : 'outline'
    return hasPreview && hasNodes ? 'review' : (outlineConfirmed ? 'content' : 'outline')
  }
  return outlineConfirmed ? 'content' : 'outline'
}

export function canStartPageGeneration(contentStatus) {
  return contentStatus === 'done'
}
