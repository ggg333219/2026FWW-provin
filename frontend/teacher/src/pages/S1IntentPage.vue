<template>
  <AppShell>
    <div class="s1-page">
      <div class="page-header">
        <div>
          <h2>S1 意图理解</h2>
          <p>教学意图捕获与结构化分析</p>
        </div>
        <div class="page-header-right">
          <div class="step-pills">
            <span class="pill active">S1 意图</span>
            <router-link v-if="activationReady" :to="{ name: 'S2Material', query: { project_id: projectStore.projectId } }" class="pill">资料上传（可选）</router-link>
            <span v-else class="pill pill-disabled" aria-disabled="true">资料上传（可选）</span>
            <router-link v-if="activationReady" :to="{ name: 'S3Studio', query: { project_id: projectStore.projectId } }" class="pill">S3 生成</router-link>
            <span v-else class="pill pill-disabled" aria-disabled="true">S3 生成</span>
            <router-link v-if="activationReady" :to="{ name: 'S4Version', query: { project_id: projectStore.projectId } }" class="pill">S4 版本</router-link>
            <span v-else class="pill pill-disabled" aria-disabled="true">S4 版本</span>
            <router-link :to="{ name: 'Middle' }" class="pill back-pill">返回中间页</router-link>
          </div>
        </div>
      </div>
      <p v-if="activationError" class="activation-error" role="alert">{{ activationError }}</p>
      <div v-if="!activationReady" class="activation-loading" role="status">
        <span>{{ activationError || '正在恢复课件意图…' }}</span>
        <button v-if="activationError" type="button" @click="activateProject(String(route.query.project_id || projectStore.projectId || ''))">重试加载</button>
      </div>
      <TeacherIntentPanel v-else :defer-initialize="true" />
      <!-- 主流程：S1 → S3；资料上传保留为可选入口 -->
      <div v-if="activationReady" class="next-step-bar">
        <router-link :to="{ name: 'S3Studio', query: { project_id: projectStore.projectId, auto_evidence: '1' } }" class="next-step-btn">
          下一步：自动检索并生成课件 →
        </router-link>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import AppShell from '../components/layout/AppShell.vue'
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
.activation-error { margin: 0 0 14px; padding: 10px 12px; border: 1px solid #f2b7b7; border-radius: 6px; color: #a52b2b; background: #fff5f5; }
.activation-loading { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 120px; padding: 20px; border: 1px solid #dce9e3; border-radius: 8px; color: #607a71; background: #fff; }
.activation-loading button { padding: 8px 12px; border: 1px solid #c8ded4; border-radius: 6px; color: #244f49; background: #f5faf7; cursor: pointer; }
.pill-disabled { opacity: .55; cursor: not-allowed; }
.s1-page {
  --ink: #18231f;
  --muted: #718078;
  --forest: #244f49;
  --mint: #65a68f;
  padding: 20px;
  min-height: calc(100vh - 140px);
  background:
    radial-gradient(circle at 86% -15%, rgba(175, 221, 203, .2), transparent 30%),
    linear-gradient(180deg, #fcfefd 0%, #f7faf8 100%);
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}
.page-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.page-body {
  flex: 1;
}
.step-pills {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.pill {
  font-size: 12px;
  font-weight: 600;
  color: #5f7467;
  background: #f0f5f2;
  border: 1px solid #e2ece6;
  border-radius: 999px;
  padding: 6px 14px;
  text-decoration: none;
  transition: all 0.15s;
}
.pill:hover {
  border-color: #5ca68f;
  color: #2f605a;
}
.pill.active {
  color: #fff;
  background: #2f605a;
  border-color: #2f605a;
}
.next-step-bar {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #e2ece6;
  text-align: right;
}
.next-step-btn {
  display: inline-block;
  padding: 10px 24px;
  background: #2f605a;
  color: #fff;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  transition: background 0.15s;
}
.next-step-btn:hover {
  background: #1e4a44;
}
@media (max-width: 760px) {
  .page-header {
    flex-direction: column;
  }
}
  .pill.back-pill {
    background: #e8f0ed;
    border-color: #c6d9d0;
    color: #3d6b60;
  }
  .pill.back-pill:hover {
    background: #d6e8e0;
  }
  .page-header h2 {
    margin: 0;
    font-size: 22px;
    color: #111827;
  }
  .page-header p {
    margin: 6px 0 0;
    font-size: 14px;
    color: #607a71;
  }
</style>
