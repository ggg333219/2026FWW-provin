<template>
  <AppShell>
    <div class="s3-page">
      <div class="page-header">
        <h2>S3 课件生成工作台</h2>
        <p>大纲构建 → 节点编辑 → 课件预览 → 版本管理，一站式生成教学课件</p>
      </div>
      <div class="page-body">
        <S3CoursewareStudio
          ref="studioRef"
          @generate="handleGenerate"
          @preview="handlePreview"
          @sync-nodes="handleSyncNodes"
        />
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useGenerationStore from '../stores/generationStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import AppShell from '../components/layout/AppShell.vue'
import S3CoursewareStudio from '../components/teacher/S3CoursewareStudio.vue'

const router = useRouter()
const generationStore = useGenerationStore()
const workspaceStore = useWorkspaceStore()
const studioRef = ref(null)

// 生成课件
async function handleGenerate() {
  const courseId = workspaceStore.currentCourseId
  if (!courseId) {
    studioRef.value?.addLog('未选择课件，请先在工作台选择课件', 'error')
    return
  }

  try {
    // 调用 gen/create API
    generationStore.setGenerateProgress(10, '正在创建生成任务…')
    studioRef.value?.addLog('正在创建生成任务…', 'info')

    let response
    try {
      const { teacherV1Api } = await import('../services/v1')
      response = await teacherV1Api.generation.createGeneration({
        course_id: courseId
      })
    } catch {
      // mock fallback
      const { mockBackend } = await import('../services/v1/mockBackend')
      response = await mockBackend.fetch('/api/v1/gen/create', {
        method: 'POST',
        body: JSON.stringify({ course_id: courseId })
      }).then(r => r.json())
    }

    const taskId = response?.task_id || response?.data?.task_id
    if (!taskId) {
      throw new Error('创建任务失败：未返回 task_id')
    }

    studioRef.value?.addLog(`任务已创建: ${taskId}`, 'success')
    generationStore.setGenerateProgress(30, '任务已创建，等待生成结果…')

    // 轮询生成状态
    await pollGenerationStatus(taskId)
  } catch (err) {
    console.error('生成失败', err)
    studioRef.value?.addLog(`生成失败: ${err.message}`, 'error')
    generationStore.setGenerating(false)
  }
}

async function pollGenerationStatus(taskId) {
  const maxRetries = 30
  const interval = 2000

  for (let i = 0; i < maxRetries; i++) {
    await new Promise(resolve => setTimeout(resolve, interval))

    let status
    try {
      const { teacherV1Api } = await import('../services/v1')
      status = await teacherV1Api.generation.getGenerationStatus(taskId)
    } catch {
      const { mockBackend } = await import('../services/v1/mockBackend')
      status = await mockBackend.fetch(`/api/v1/gen/status/${taskId}`).then(r => r.json())
    }

    const s = status?.status || status?.data?.status || ''
    const progress = status?.progress || status?.data?.progress || 0
    const stageText = status?.stage_text || status?.data?.stage_text || ''

    generationStore.setGenerateProgress(30 + progress * 0.6, stageText || '生成中…')

    if (s === 'completed' || s === 'done') {
      // 加载节点
      const nodes = status?.nodes || status?.data?.nodes || status?.result?.nodes || []
      if (nodes.length > 0) {
        generationStore.setNodes(nodes)
        studioRef.value?.setOutlineNodes(nodes)
        studioRef.value?.addLog(`生成了 ${nodes.length} 个节点`, 'success')
      }
      generationStore.setGenerateProgress(100, '生成完成')
      generationStore.setGenerating(false)

      // 自动刷新预览
      setTimeout(() => handlePreview(), 500)
      return
    }

    if (s === 'failed' || s === 'error') {
      const errMsg = status?.error || status?.data?.error || '未知错误'
      studioRef.value?.addLog(`生成失败: ${errMsg}`, 'error')
      generationStore.setGenerating(false)
      return
    }

    studioRef.value?.addLog(`生成中… (${Math.round(progress * 100)}%)`, 'info')
  }

  // 超时
  studioRef.value?.addLog('生成超时，请重试', 'error')
  generationStore.setGenerating(false)
}

// 预览
async function handlePreview() {
  const courseId = workspaceStore.currentCourseId
  if (!courseId) return

  try {
    let html
    try {
      const { teacherV1Api } = await import('../services/v1')
      const resp = await teacherV1Api.generation.preview({
        nodes: generationStore.currentScriptNodes
      })
      html = resp?.html || resp?.data?.html || ''
    } catch {
      // 本地 fallback: 从节点生成预览
      const nodes = generationStore.currentScriptNodes
      if (nodes.length > 0) {
        html = buildPreviewHtml(nodes, workspaceStore.currentCourseName)
      }
    }

    if (html) {
      studioRef.value?.setPreviewHtml(html)
    } else {
      studioRef.value?.setPreviewError('无法生成预览')
    }
  } catch (err) {
    studioRef.value?.setPreviewError(err.message)
  }
}

// 同步节点到 Store
function handleSyncNodes(nodes) {
  generationStore.setNodes(nodes)
}

// 本地预览生成
function buildPreviewHtml(nodes, courseName) {
  const title = courseName || '课件预览'
  const items = nodes.map((n, i) => {
    const t = n.title || `节点 ${i + 1}`
    const c = (n.content || n.scriptText || n.script || n.summary || '').substring(0, 200)
    return `<div class="slide">
      <h2>${t}</h2>
      <p>${c.replace(/\n/g, '<br>')}</p>
    </div>`
  }).join('\n')

  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>${title}</title>
<style>
body { font-family: -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f8fafc; }
.slide { background: #fff; border-radius: 12px; padding: 32px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.slide h2 { color: #111827; font-size: 20px; margin: 0 0 12px; }
.slide p { color: #475569; line-height: 1.6; margin: 0; }
</style></head><body>
<h1>${title}</h1>
${items}
</body></html>`
}

onMounted(() => {
  // 如果已有节点，加载预览
  if (generationStore.currentScriptNodes.length > 0) {
    studioRef.value?.setOutlineNodes(generationStore.currentScriptNodes)
    setTimeout(() => handlePreview(), 300)
  }
})
</script>

<style scoped>
.s3-page { padding: 20px; min-height: calc(100vh - 140px); display: flex; flex-direction: column; }
.page-header { margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 22px; color: #111827; }
.page-header p { margin: 6px 0 0; font-size: 14px; color: #607a71; }
.page-body { flex: 1; min-height: 0; }
</style>