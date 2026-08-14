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
            <router-link :to="{ name: 'S2Material' }" class="pill">S2 资料</router-link>
            <router-link :to="{ name: 'S3Studio' }" class="pill">S3 生成</router-link>
            <router-link :to="{ name: 'S4Version' }" class="pill">S4 版本</router-link>
          </div>
        </div>
      </div>
      <div class="page-body">
        <TeacherIntentPanel />
      </div>
      <!-- 下一步：S1 → S2 -->
      <div class="next-step-bar">
        <router-link :to="{ name: 'S2Material' }" class="next-step-btn">
          下一步：补充教学资料 →
        </router-link>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { watch } from 'vue'
import AppShell from '../components/layout/AppShell.vue'
import TeacherIntentPanel from '../components/teacher/TeacherIntentPanel.vue'
import { useIntentStore } from '../stores/intentStore'

const INTENT_HANDOFF_KEY = 'fuww_intent_parsed'
const intentStore = useIntentStore()

/**
 * S1 → S2 的冻结交接契约。
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
        window.localStorage.removeItem(INTENT_HANDOFF_KEY)
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
    if (window.localStorage.getItem(INTENT_HANDOFF_KEY) !== serialized) {
      window.localStorage.setItem(INTENT_HANDOFF_KEY, serialized)
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
</script>

<style scoped>
.s1-page {
  --ink: #18231f;
  --muted: #718078;
  --forest: #244f49;
  --mint: #65a68f;
  padding: clamp(22px, 3vw, 40px);
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
</style>
