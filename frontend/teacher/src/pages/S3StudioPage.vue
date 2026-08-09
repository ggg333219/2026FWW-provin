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
import { ref, onMounted, onUnmounted } from 'vue'
import { useGenerationStore } from '../stores/generationStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { teacherV1Api } from '../services/v1'
import AppShell from '../components/layout/AppShell.vue'
import S3CoursewareStudio from '../components/teacher/S3CoursewareStudio.vue'

const generationStore = useGenerationStore()
const workspaceStore = useWorkspaceStore()
const studioRef = ref(null)

let _unmounted = false
let _pollTimer = null

onUnmounted(() => {
  _unmounted = true
  if (_pollTimer) clearTimeout(_pollTimer)
})

// 生成课件
async function handleGenerate() {
  const courseId = workspaceStore.currentCourseId
  if (!courseId) {
    studioRef.value?.addLog('未选择课件，请先在工作台选择课件', 'error')
    return
  }

  try {
    generationStore.setGenerateProgress(10, '正在创建生成任务…')
    studioRef.value?.addLog('正在创建生成任务…', 'info')

    const response = await teacherV1Api.generation.createGeneration({
      course_id: courseId
    })
    const data = response?.data || response
    const taskId = data?.task_id || data?.taskId
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
    if (_unmounted) return

    await new Promise(resolve => {
      _pollTimer = setTimeout(resolve, interval)
    })
    if (_unmounted) return

    try {
      const status = await teacherV1Api.generation.getGenerationStatus(taskId)
      const data = status?.data || status
      const s = data?.status || ''
      const progress = data?.progress ?? (data?.progress_pct ? data.progress_pct / 100 : 0)
      const stageText = data?.stage_text || ''
      const nodes = data?.nodes || data?.result?.nodes || []

      // 后端返回 progress 为 0-1，前端显示 0-100
      generationStore.setGenerateProgress(30 + Math.round(progress * 60), stageText || '生成中…')

      if (s === 'completed' || s === 'done') {
        if (nodes.length > 0) {
          generationStore.setNodes(nodes)
          studioRef.value?.setOutlineNodes(nodes)
          studioRef.value?.addLog(`生成了 ${nodes.length} 个节点`, 'success')
        }
        generationStore.setGenerateProgress(100, '生成完成')
        generationStore.setGenerating(false)
        studioRef.value?.addLog('生成完成', 'success')

        // 自动刷新预览
        setTimeout(() => {
          if (!_unmounted) handlePreview()
        }, 500)
        return
      }

      if (s === 'failed' || s === 'error') {
        const errMsg = data?.error || '未知错误'
        studioRef.value?.addLog(`生成失败: ${errMsg}`, 'error')
        generationStore.setGenerating(false)
        return
      }

      studioRef.value?.addLog(`生成中… (${Math.round(progress * 100)}%)`, 'info')
    } catch (err) {
      console.warn('轮询状态失败', err)
    }
  }

  // 超时
  if (!_unmounted) {
    studioRef.value?.addLog('生成超时，请重试', 'error')
    generationStore.setGenerating(false)
  }
}

// 预览
async function handlePreview() {
  try {
    const resp = await teacherV1Api.generation.preview({
      nodes: generationStore.currentScriptNodes
    })
    const html = resp?.html || resp?.data?.html || ''
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