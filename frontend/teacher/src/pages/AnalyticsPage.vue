<template>
  <AppShell>
    <div class="analytics-page">
      <header class="page-head">
        <p class="page-head__eyebrow">教学数据</p>
        <h1 class="page-head__title">学情分析</h1>
        <p class="page-head__desc">学情统计、掌握度雷达与班级趋势</p>
      </header>
      <div class="page-body">
        <AnalyticsAndQuestionsPanel
          :student-stats="analyticsStore.studentStats"
          :card-data="analyticsStore.cardData"
          :question-records="analyticsStore.questionRecords"
          @update:filterPage="analyticsStore.setFilterPage($event)"
        />

        <TeacherStatsPanel
          :current-course-id="workspaceStore.currentCourseId"
          :current-course-name="workspaceStore.currentCourseName"
          :student-stats="analyticsStore.studentStats"
          :card-data="analyticsStore.cardData"
          :initial-stats-tab="analyticsStore.statsSubTab"
          @update:stats-tab="analyticsStore.setStatsSubTab($event)"
        />
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { onMounted } from 'vue'
import { useWorkspaceStore } from '../stores/workspaceStore'
import { useAnalyticsStore } from '../stores/analyticsStore'
import AppShell from '../components/layout/AppShell.vue'
import TeacherStatsPanel from '../components/teacher/TeacherStatsPanel.vue'
import AnalyticsAndQuestionsPanel from '../components/teacher/AnalyticsAndQuestionsPanel.vue'

const workspaceStore = useWorkspaceStore()
const analyticsStore = useAnalyticsStore()

onMounted(async () => {
  if (workspaceStore.currentCourseId) {
    await analyticsStore.loadStats(workspaceStore.currentCourseId)
    await analyticsStore.loadCardData(workspaceStore.currentCourseId)
    await analyticsStore.loadQuestionRecords(workspaceStore.currentCourseId)
  }
})
</script>

<style scoped>
.analytics-page {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-6);
  min-height: calc(100dvh - var(--topbar-height) - var(--shell-gutter) * 2);
  background: var(--bg-page);
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
  color: var(--text-primary);
}
.page-head__desc { margin: var(--space-1) 0 0; font-size: var(--text-xs); color: var(--text-secondary); }
.page-body { flex: 1; display: flex; flex-direction: column; gap: var(--space-6); min-width: 0; }
@media (max-width: 767px) {
  .analytics-page { padding: var(--space-4); gap: var(--space-4); }
  .page-body { gap: var(--space-4); }
}
</style>
