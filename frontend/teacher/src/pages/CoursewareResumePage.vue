<template>
  <div class="resume-page">
    <section class="resume-card" role="status" aria-live="polite">
      <div class="resume-icon" :class="{ 'is-failed': failed }" aria-hidden="true">
        <svg v-if="failed" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
          <circle cx="12" cy="12" r="9" /><path d="M12 7.5v5M12 16h.01" />
        </svg>
        <span v-else class="resume-spinner"></span>
      </div>
      <h1>{{ failed ? '无法恢复课件' : '正在恢复课件' }}</h1>
      <p>{{ message }}</p>
      <div v-if="failed" class="actions">
        <button class="ds-btn ds-btn--secondary" type="button" @click="router.replace({ name: 'Middle' })">返回我的课件</button>
        <button class="ds-btn ds-btn--primary" type="button" @click="restart">重新开始</button>
      </div>
    </section>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCoursewareProjectStore } from '../stores/coursewareProjectStore'
import { teacherV1Api } from '../services/v1'
import { useIntentStore } from '../stores/intentStore'
import { useMaterialStore } from '../stores/materialStore'
import { useOutlineStore } from '../stores/outlineStore'
import { useGenerationStore } from '../stores/generationStore'
import { useVersionStore } from '../stores/versionStore'
import { useModifyStore } from '../stores/modifyStore'
import { useContentStore } from '../stores/contentStore'
import { writeResumeDraft, clearLegacyResumeDraft } from '../utils/coursewareDraft'

const route = useRoute(); const router = useRouter(); const projects = useCoursewareProjectStore(); const message = ref('正在读取最新编辑进度…'); const failed = ref(false)
const intentStore = useIntentStore(); const materialStore = useMaterialStore(); const outlineStore = useOutlineStore(); const generationStore = useGenerationStore()
const routeForStep = { s1_intent: 'S1Intent', s2_material: 'S2Material', s3_studio: 'S3Studio', s4_version: 'S4Version' }
function hydrateDraft(draft, projectId) {
  const intentSession = draft.intent_session || {}
  if (draft.intent || intentSession.session_id) {
    intentStore.initialize(projectId)
    intentStore.intentSummary = draft.intent || intentStore.intentSummary
    intentStore.sessionId = intentSession.session_id || intentStore.sessionId
    intentStore.intentId = intentSession.intent_id || intentStore.intentId
    intentStore.sessionStatus = intentSession.status || intentStore.sessionStatus
    if (Array.isArray(intentSession.messages)) intentStore.messages = intentSession.messages
    intentStore.persist?.()
  }
  if (Array.isArray(draft.materials)) materialStore.materials = draft.materials
  if (Array.isArray(draft.selected_materials)) materialStore.selectedMaterials = draft.selected_materials
  if (draft.evidence_packet) {
    materialStore.evidencePackets = [{ id: `resume_${Date.now()}`, packet: draft.evidence_packet, createdAt: new Date().toISOString() }]
  }
  if (draft.outline?.outline_id) {
    outlineStore._applyOutlineData(draft.outline)
    outlineStore._persist()
  }
  if (draft.generation) {
    if (draft.generation.generation_id) generationStore.setLastGenId(draft.generation.generation_id)
    if (draft.generation.task_id) generationStore.setLastTaskId(draft.generation.task_id)
    if (Array.isArray(draft.generation.nodes)) generationStore.setNodes(draft.generation.nodes)
  }
}
async function restart() {
  try {
    const project = await projects.create('未命名课件')
    for (const store of [useIntentStore(), useMaterialStore(), useOutlineStore(), useGenerationStore(), useVersionStore(), useModifyStore(), useContentStore()]) store.reset?.()
    clearLegacyResumeDraft()
    await projects.updateStep('s1_intent')
    router.replace({ name: 'S1Intent', query: { project_id: project.id || project.project_id } })
  } catch (error) { message.value = error?.message || '重新开始失败，请稍后重试' }
}
onMounted(async () => {
  try {
    let projectId = String(route.query.project_id || '')
    if (!projectId && route.query.generation_id) {
      const list = await projects.loadProjects()
      const match = list.find(item => String(item.gen_id || item.generation_id || '') === String(route.query.generation_id))
      projectId = String(match?.id || match?.project_id || '')
    }
    if (!projectId) throw new Error('未找到该课件的本地编辑数据，是否重新开始？')
    const context = await projects.resume(projectId)
    const draftSource = context.draft || context.draft_json
    let draft = {}
    if (draftSource && typeof draftSource === 'object') draft = draftSource
    else if (typeof draftSource === 'string') {
      try { draft = JSON.parse(draftSource) || {} } catch { draft = {} }
    }
    projects.setActive(projectId)
    hydrateDraft(draft, projectId)
    writeResumeDraft(projectId, draft)
    const generationId = context.generation_id || context.project?.gen_id || draft.generation_id || draft.generation?.generation_id || ''
    let latestLocked = false
    if (generationId) {
      try {
        const historyRaw = await teacherV1Api.version.history(generationId)
        const versions = (historyRaw?.data || historyRaw || {}).versions || []
        latestLocked = !!versions.slice().sort((a, b) => Number(b.version_number) - Number(a.version_number))[0]?.locked
      } catch { latestLocked = false }
    }
    const target = latestLocked ? 'S4Version' : (routeForStep[context.current_step || context.project?.current_step] || 'S1Intent')
    router.replace({ name: target, query: { project_id: projectId, generation_id: generationId, ...(latestLocked ? { readonly: '1' } : {}) } })
  } catch (error) { failed.value = true; message.value = error?.message || '未找到该课件的本地编辑数据，是否重新开始？' }
})
</script>
<style scoped>
.resume-page {
  display: grid;
  min-height: 100dvh;
  place-items: center;
  padding: var(--space-5);
  background: var(--bg-page);
}
.resume-card {
  width: min(480px, 100%);
  padding: var(--space-10) var(--space-8);
  text-align: center;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  box-shadow: var(--shadow-md);
}
.resume-icon {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  margin: 0 auto var(--space-4);
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
}
.resume-icon.is-failed { background: var(--color-danger-soft); color: var(--color-danger); }
.resume-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--brand-200);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: resume-spin 0.8s linear infinite;
}
@keyframes resume-spin { to { transform: rotate(360deg); } }
.resume-card h1 { margin: 0; color: var(--text-primary); font-size: var(--text-lg); font-weight: var(--weight-semibold); }
.resume-card p { margin: var(--space-3) 0 0; color: var(--text-secondary); font-size: var(--text-xs); line-height: var(--leading-relaxed); }
.actions { display: flex; justify-content: center; gap: var(--space-2); margin-top: var(--space-6); flex-wrap: wrap; }
@media (prefers-reduced-motion: reduce) { .resume-spinner { animation-duration: 0.01ms; } }
</style>
