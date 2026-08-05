<template>
  <AppShell>
    <div class="analytics-page">
      <div class="page-header">
        <h2>学情分析</h2>
        <p>学情统计、掌握度雷达与班级趋势</p>
      </div>
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
.analytics-page { padding: 20px; min-height: calc(100vh - 140px); }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 22px; color: #111827; }
.page-header p { margin: 6px 0 0; font-size: 14px; color: #607a71; }
.page-body { flex: 1; display: flex; flex-direction: column; gap: 24px; }
</style>
