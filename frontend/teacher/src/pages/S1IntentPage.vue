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
import AppShell from '../components/layout/AppShell.vue'
import TeacherIntentPanel from '../components/teacher/TeacherIntentPanel.vue'
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