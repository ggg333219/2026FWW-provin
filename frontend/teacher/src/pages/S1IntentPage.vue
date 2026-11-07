<template>
  <AppShell>
    <div class="s1-page">
      <header class="page-head">
        <div class="page-head__text">
          <p class="page-head__eyebrow">课件生成流程</p>
          <h1 class="page-head__title">S1 意图理解</h1>
          <p class="page-head__desc">教学意图捕获与结构化分析</p>
        </div>
        <p class="page-head__aside">用对话说明课程主题、课时、授课对象与产出形式，系统会整理为结构化教学意图。</p>
      </header>

      <StepNav current="s1" :project-id="projectStore.projectId" :ready="activationReady" />

      <p v-if="activationError" class="ds-notice ds-notice--danger activation-notice" role="alert">
        <span>{{ activationError }}</span>
        <button
          class="ds-btn ds-btn--secondary ds-btn--sm"
          type="button"
          @click="activateProject(String(route.query.project_id || projectStore.projectId || ''))"
        >重试加载</button>
      </p>

      <div v-if="!activationReady && !activationError" class="ds-card activation-loading" role="status">
        <LoadingState type="loading" text="正在恢复课件意图…" hint="正在读取上次的会话与草稿，请稍候" />
      </div>

      <TeacherIntentPanel v-else-if="activationReady" :defer-initialize="true" />

      <!-- 主流程：S1 → S3；资料上传保留为可选入口 -->
      <footer v-if="activationReady" class="next-step-bar">
        <p class="next-step-hint">确认教学意图后，即可进入课件生成；补充资料可在流程中随时添加。</p>
        <router-link
          :to="{ name: 'S3Studio', query: { project_id: projectStore.projectId, auto_evidence: '1' } }"
          class="ds-btn ds-btn--primary ds-btn--lg next-step-btn"
        >下一步：自动检索并生成课件 →</router-link>
      </footer>
    </div>
  </AppShell>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import AppShell from '../components/layout/AppShell.vue'
import StepNav from '../components/common/StepNav.vue'
import LoadingState from '../components/common/LoadingState.vue'
import TeacherIntentPanel from '../components/teacher/TeacherIntentPanel.vue'
import { intentStorageKey, useIntentStore } from '../stores/intentStore'
import { useCoursewareProjectStore } from '../stores/coursewareProjectStore'

const intentStore = useIntentStore()
const projectStore = useCoursewareProjectStore()
const route = useRoute()
const router = useRouter()
const activationError = ref('')
const activationReady = ref(false)
let activationEpoch = 0
const handoffKey = () => intentStorageKey('fuww_intent_parsed', intentStore.projectId || route.query.project_id || projectStore.projectId)
const intentDraft = () => ({
  ...(projectStore.draft || {}),
  intent: intentStore.intentSummary,
  intent_session: {
    session_id: intentStore.sessionId,
    intent_id: intentStore.intentId,
    status: intentStore.sessionStatus,
    messages: intentStore.messages,
  },
})

const activateProject = async (projectId) => {
  const epoch = ++activationEpoch
  activationReady.value = false
  activationError.value = ''
  const currentProjectId = projectStore.projectId || projectStore.restoreActiveId() || ''
  if (currentProjectId && currentProjectId !== projectId) {
    try {
      await projectStore.saveNow(intentDraft())
    } catch {
      if (epoch === activationEpoch) {
        activationError.value = '当前课件草稿保存失败，已取消切换。请检查网络后重试。'
        activationReady.value = true
        await router.replace({ name: 'S1Intent', query: { project_id: currentProjectId } })
      }
      return
    }
    if (epoch !== activationEpoch) return
  }
  projectStore.setActive(projectId)
  if (projectId && !projectStore.draft) {
    try {
      await projectStore.resume(projectId, () => epoch === activationEpoch && String(route.query.project_id || projectStore.projectId || '') === projectId)
    } catch {
      if (epoch === activationEpoch) activationError.value = '课件恢复失败，已暂停编辑以避免覆盖已有草稿。请检查网络后重试。'
      return
    }
    if (epoch !== activationEpoch) return
  }
  intentStore.initialize(projectId)
  activationReady.value = true
}
onMounted(async () => {
  const projectId = String(route.query.project_id || projectStore.restoreActiveId() || '')
  await activateProject(projectId)
  if (activationReady.value) await projectStore.updateStep('s1_intent').catch(() => {})
})
watch(() => route.query.project_id, (value) => {
  const projectId = String(value || '')
  if (projectId && projectId !== projectStore.projectId) void activateProject(projectId)
})
onBeforeUnmount(() => { if (activationReady.value) projectStore.saveNow(intentDraft()).catch(() => {}) })
onBeforeRouteLeave(async () => { if (activationReady.value) await projectStore.saveNow(intentDraft()).catch(() => {}) })

/**
 * S1 → S3 的冻结交接契约（S2 资料上传为可选补充入口）。
 *
 * 只发布已经确认的意图，避免 S2 在教师仍然澄清需求时使用半成品数据。
 * 保留当前 IntentSummary 的 snake_case 字段，同时兼容旧任务文档中的
 * subject 等字段，便于 S2 和后续 Workspace 编排统一消费。
 */
const persistConfirmedIntent = (summary, status, intentId) => {
  if (typeof window === 'undefined') return

  if (!['confirmed', 'locked'].includes(status)) {
    // “重新开始”会生成新 session 并清空摘要；同步清理旧交接，避免 S2 误用上一次意图。
    if (intentStore.sessionId && status === 'collecting' && !summary) {
      try {
        window.localStorage.removeItem(handoffKey())
      } catch {
        // localStorage 不可用时不阻塞 S1 初始化。
      }
    }
    return
  }

  const topic = String(summary?.topic || '').trim()
  if (!topic) return

  const subject = String(summary?.subject || summary?.discipline || '').trim()
  const payload = {
    ...summary,
    topic,
    ...(subject ? { subject } : {}),
    search_query: [topic, subject].filter(Boolean).join(' '),
    intent_id: intentId || summary?.intent_id || '',
    session_id: intentStore.sessionId || summary?.session_id || '',
    schema_version: 1
  }

  try {
    const serialized = JSON.stringify(payload)
    if (window.localStorage.getItem(handoffKey()) !== serialized) {
      window.localStorage.setItem(handoffKey(), serialized)
    }
  } catch {
    // localStorage 不可用时不阻塞确认与页面跳转主流程。
  }
}

watch(
  () => [intentStore.intentSummary, intentStore.sessionStatus, intentStore.intentId],
  ([summary, status, intentId]) => persistConfirmedIntent(summary, status, intentId),
  { deep: true, immediate: true }
)

watch(
  () => [intentStore.intentSummary, intentStore.messages, intentStore.sessionStatus, intentStore.intentId],
  () => { if (activationReady.value) projectStore.scheduleSave(intentDraft()) },
  { deep: true }
)
</script>

<style scoped>
.s1-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-6);
  min-height: calc(100dvh - var(--topbar-height) - var(--shell-gutter) * 2);
  background: var(--bg-page);
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-8);
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
  margin: var(--space-1) 0 0;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.page-head__aside {
  max-width: 40ch;
  margin: 0;
  font-size: var(--text-2xs);
  line-height: var(--leading-relaxed);
  color: var(--text-tertiary);
  text-align: right;
}

.activation-notice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}
.activation-loading { min-height: 200px; display: flex; align-items: center; justify-content: center; }

.next-step-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5);
  margin-top: auto;
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-subtle);
}
.next-step-hint {
  margin: 0;
  font-size: var(--text-2xs);
  line-height: var(--leading-relaxed);
  color: var(--text-tertiary);
}
.next-step-btn { flex-shrink: 0; }

@media (max-width: 1023px) {
  .page-head__aside { display: none; }
}
@media (max-width: 767px) {
  .s1-page { padding: var(--space-4); gap: var(--space-4); }
  .next-step-bar { flex-direction: column; align-items: stretch; gap: var(--space-3); }
  .next-step-btn { width: 100%; white-space: normal; }
  .activation-notice { flex-direction: column; align-items: stretch; }
}
</style>
