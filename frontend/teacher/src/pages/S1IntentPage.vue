<template>
  <AppShell>
    <div class="s1-page">
      <div class="page-header">
        <h2>S1 意图理解</h2>
        <p>教学意图捕获与结构化分析</p>
      </div>
      <div class="page-body">
        <TeacherIntentPanel />
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import AppShell from '../components/layout/AppShell.vue'
import TeacherIntentPanel from '../components/teacher/TeacherIntentPanel.vue'
</script>

<style scoped>
.s1-page {
  padding: 20px;
  min-height: calc(100vh - 140px);
}
.page-header {
  margin-bottom: 20px;
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
.page-body {
  flex: 1;
}
</style>
