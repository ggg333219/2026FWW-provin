import { describe, expect, it } from 'vitest'
import { resolveS3Phase, canStartPageGeneration } from './s3Phase'

describe('S3 旧阶段恢复', () => {
  const confirmed = { outlineConfirmed: true }
  const ready = { ...confirmed, taskStatus: 'done', hasPreview: true, hasNodes: true }

  it('首次进入、确认大纲后刷新分别进入大纲和内容', () => {
    expect(resolveS3Phase('', {})).toBe('outline')
    expect(resolveS3Phase('outline', ready)).toBe('outline')
    expect(resolveS3Phase('content', confirmed)).toBe('content')
  })

  it.each(['generating', 'pages', 'style'])('旧阶段 %s 只在任务完成且可预览时进入审阅', phase => {
    expect(resolveS3Phase(phase, ready)).toBe('review')
    expect(resolveS3Phase(phase, { ...ready, hasPreview: false })).toBe('content')
    expect(resolveS3Phase(phase, { ...ready, hasNodes: false })).toBe('content')
  })

  it.each(['pending', 'processing', 'generating', 'failed', 'error'])('任务状态 %s 保留在内容阶段', status => {
    expect(resolveS3Phase('generating', { ...ready, taskStatus: status })).toBe('content')
    expect(resolveS3Phase('pages', { ...ready, taskStatus: status })).toBe('content')
  })

  it.each(['pending', 'generating', 'error'])('讲稿状态 %s 不把旧预览误判为本次完成', status => {
    expect(resolveS3Phase('pages', { ...ready, contentStatus: status })).toBe('content')
  })

  it('历史版本与 S4 返回 S3 按实际预览状态恢复', () => {
    expect(resolveS3Phase('review', ready)).toBe('review')
    expect(resolveS3Phase('outline', ready)).toBe('outline')
  })

  it('讲稿任务完成前不能启动页面生成，失败也不能误报完成', () => {
    for (const status of ['idle', 'pending', 'generating', 'error']) expect(canStartPageGeneration(status)).toBe(false)
    expect(canStartPageGeneration('done')).toBe(true)
  })
})
