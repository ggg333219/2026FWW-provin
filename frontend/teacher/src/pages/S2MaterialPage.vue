<template>
  <AppShell>
    <div class="s2-page">
      <header class="page-head">
        <div class="page-head__text">
          <p class="page-head__eyebrow">课件生成流程 · 可选环节</p>
          <h1 class="page-head__title">资料与证据中心</h1>
          <p class="page-head__desc">保留资料上传与解析；系统会依据 S1 教学意图自动检索，并把证据包绑定到整份 PPT 草稿。</p>
        </div>
        <button v-if="isMockModeActive" class="ds-tag ds-tag--warning mock-exit-btn" type="button" @click="exitMockMode">
          <span class="ds-status-dot"></span>⚠ Mock 模式 · 点击退出
        </button>
      </header>

      <StepNav current="s2" :project-id="projectStore.projectId" :action-keys="['s3']" @step-action="onStepAction" />

      <!-- 独立路由入口：复用 S2 资料中心工作台（与 Workspace 内嵌 tab 同一组件，路由/内嵌统一） -->
      <S2MaterialWorkspace />

      <!-- S2 是可选补充入口；主流程已改为 S1 → S3。 -->
      <footer class="next-step-bar">
        <p class="next-step-hint">资料为可选补充；没有绑定证据时，也可以选择仅依据 S1 教学意图生成。</p>
        <button class="ds-btn ds-btn--primary ds-btn--lg next-step-btn" type="button" :disabled="navigatingToS3" @click="requestContinue">
          {{ navigatingToS3 ? '跳转中…' : '下一步：进入 S3 生成 →' }}
        </button>
        <div v-if="showNoEvidenceConfirm" class="ds-notice ds-notice--warning continue-confirm" role="alert">
          <div>
            <strong>当前还没有绑定可用证据</strong>
            <p>可以继续上传资料，系统会自动重新检索；也可以明确选择无资料生成。后者将仅依据 S1 教学意图生成。</p>
          </div>
          <div class="continue-actions">
            <button class="ds-btn ds-btn--secondary ds-btn--sm" type="button" @click="showNoEvidenceConfirm = false">继续补充资料</button>
            <button class="ds-btn ds-btn--secondary ds-btn--sm" type="button" @click="confirmWithoutEvidence">确认无资料生成</button>
          </div>
        </div>
      </footer>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, onBeforeUnmount, onMounted, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import AppShell from '../components/layout/AppShell.vue'
import StepNav from '../components/common/StepNav.vue'
import S2MaterialWorkspace from '../components/teacher/S2MaterialWorkspace.vue'
import { useMaterialStore, isEvidencePacketUsable } from '../stores/materialStore'
import { useIntentStore } from '../stores/intentStore'
import { useCoursewareProjectStore } from '../stores/coursewareProjectStore'

const router = useRouter()
const route = useRoute()
const materialStore = useMaterialStore()
const intentStore = useIntentStore()
const projectStore = useCoursewareProjectStore()
projectStore.setActive(String(route.query.project_id || projectStore.restoreActiveId() || ''))
intentStore.initialize(projectStore.projectId)

const materialDraft = () => ({
  ...(projectStore.draft || {}),
  intent: intentStore.intentSummary,
  materials: materialStore.materials,
  selected_materials: materialStore.selectedMaterials,
  evidence_packet: materialStore.s3EvidencePayload,
})

const showNoEvidenceConfirm = ref(false)
const navigatingToS3 = ref(false)

const readEvidence = () => {
  if (isEvidencePacketUsable(materialStore.s3EvidencePayload)) return materialStore.s3EvidencePayload
  if (typeof window === 'undefined') return null
  try {
    return JSON.parse(window.localStorage.getItem(`fuww_s2_evidence_packet:${intentStore.sessionId}`) || 'null')
  } catch {
    return null
  }
}

const writeGenerationMode = (mode) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(`fuww_s2_generation_mode:${intentStore.sessionId}`, mode)
}

const requestContinue = () => {
  if (navigatingToS3.value) return
  if (isEvidencePacketUsable(readEvidence())) {
    navigatingToS3.value = true
    writeGenerationMode('with_evidence')
    projectStore.updateStep('s3_studio').catch(() => {})
    router.push({ name: 'S3Studio', query: { project_id: projectStore.projectId } })
    return
  }
  showNoEvidenceConfirm.value = true
}

const confirmWithoutEvidence = () => {
  navigatingToS3.value = true
  materialStore.clearEvidencePackets()
  writeGenerationMode('without_evidence')
  projectStore.updateStep('s3_studio').catch(() => {})
  router.push({ name: 'S3Studio', query: { project_id: projectStore.projectId } })
}

/** 流程条上的「课件生成」仍需先做无证据确认，不能直接跳路由。 */
const onStepAction = key => {
  if (key === 's3') requestContinue()
}

/** Mock 模式检测与退出 */
const isMockModeActive = ref(false)

onMounted(async () => {
  if (projectStore.projectId && !projectStore.draft) await projectStore.resume(projectStore.projectId).catch(() => {})
  await projectStore.updateStep('s2_material').catch(() => {})
  if (typeof window !== 'undefined') {
    isMockModeActive.value = window.localStorage.getItem('fuww_mock_mode') === 'true'
  }
})

watch(
  () => [materialStore.materials, materialStore.selectedMaterials, materialStore.evidencePackets],
  () => projectStore.scheduleSave(materialDraft()),
  { deep: true }
)
onBeforeUnmount(() => projectStore.saveNow(materialDraft()).catch(() => {}))
onBeforeRouteLeave(async () => { await projectStore.saveNow(materialDraft()).catch(() => {}) })

const exitMockMode = () => {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem('fuww_mock_mode')
  }
  isMockModeActive.value = false
}
</script>

<style scoped>
.s2-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-6);
  min-height: calc(100dvh - var(--topbar-height) - var(--shell-gutter) * 2);
  background: var(--bg-page);
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-6);
}
.page-head__eyebrow {
  margin: 0 0 var(--space-1);
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  letter-spacing: 0.06em;
  color: var(--color-primary);
}
.page-head__title {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: var(--weight-semibold);
  line-height: var(--leading-tight);
  color: var(--text-primary);
}
.page-head__desc {
  max-width: 78ch;
  margin: var(--space-1) 0 0;
  font-size: var(--text-xs);
  line-height: var(--leading-relaxed);
  color: var(--text-secondary);
}

.mock-exit-btn {
  flex-shrink: 0;
  min-height: 28px;
  cursor: pointer;
  font-family: var(--font-sans);
}
.mock-exit-btn:hover { filter: brightness(0.97); }

.next-step-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin-top: auto;
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-subtle);
}
.next-step-hint {
  flex: 1 1 320px;
  margin: 0;
  font-size: var(--text-2xs);
  line-height: var(--leading-relaxed);
  color: var(--text-tertiary);
}
.next-step-btn { flex-shrink: 0; }

.continue-confirm {
  flex: 1 1 100%;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5);
}
.continue-confirm strong { font-size: var(--text-sm); }
.continue-confirm p {
  margin: var(--space-1) 0 0;
  max-width: 72ch;
  font-size: var(--text-2xs);
  line-height: var(--leading-relaxed);
}
.continue-actions { display: flex; gap: var(--space-2); flex-shrink: 0; }

@media (max-width: 767px) {
  .s2-page { padding: var(--space-4); gap: var(--space-4); }
  .page-head { flex-direction: column; }
  .next-step-bar { flex-direction: column; align-items: stretch; }
  .next-step-btn { width: 100%; white-space: normal; }
  .continue-confirm { flex-direction: column; align-items: stretch; }
  .continue-actions { flex-wrap: wrap; }
}
</style>
