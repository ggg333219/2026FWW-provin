<template>
  <AppShell>
    <div class="s3-page">
      <div class="page-header">
        <h2>S3 讲稿生成</h2>
        <p>讲稿编辑、节点树管理与音频生成</p>
      </div>
      <div class="page-body">
        <p class="section-note">讲稿生成功能已集成到 Workspace 的"编辑讲稿"标签页中。</p>
        <div class="s3-placeholder">
          <p>此处为独立的路由入口，供后续 S3 工作流专用页面使用。</p>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import AppShell from '../components/layout/AppShell.vue'
</script>

<style scoped>
.s3-page { padding: 20px; min-height: calc(100vh - 140px); }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 22px; color: #111827; }
.page-header p { margin: 6px 0 0; font-size: 14px; color: #607a71; }
.page-body { flex: 1; }
.section-note { padding: 12px 16px; background: #f0f9f5; border-radius: 12px; color: #2d5f58; font-size: 14px; margin-bottom: 16px; }
.s3-placeholder { padding: 60px 20px; text-align: center; color: #94a3b8; }
</style>
