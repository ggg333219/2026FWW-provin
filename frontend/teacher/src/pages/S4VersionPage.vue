<template>
  <AppShell>
    <div class="s4-page">
      <div class="page-header">
        <h2>S4 版本管理</h2>
        <p>课件版本控制、修改指令与发布管理</p>
      </div>
      <div class="page-body">
        <div class="s4-layout">
          <section class="s4-versions">
            <div class="section-card">
              <h3>版本历史</h3>
              <div v-if="versionStore.versions.length === 0" class="empty-tip">暂无版本记录</div>
              <div v-else class="version-list">
                <div v-for="v in versionStore.versions" :key="v.id" class="version-item">
                  <strong>v{{ v.version }}</strong>
                  <span>{{ v.title }}</span>
                  <small>{{ v.createdAt }}</small>
                </div>
              </div>
            </div>
          </section>
          <section class="s4-changes">
            <div class="section-card">
              <h3>待处理修改</h3>
              <div v-if="versionStore.pendingChanges.length === 0" class="empty-tip">暂无待处理修改</div>
              <div v-else class="change-list">
                <div v-for="c in versionStore.pendingChanges" :key="c.id" class="change-item">
                  <span class="change-type">{{ c.type }}</span>
                  <span>{{ c.target }}</span>
                  <span class="change-status" :class="c.status">{{ c.status }}</span>
                </div>
              </div>
            </div>
          </section>
          <section class="s4-publish">
            <div class="section-card">
              <h3>发布管理</h3>
              <div class="publish-info">
                <p v-if="versionStore.publishState.lastPublishedAt">
                  上次发布：{{ versionStore.publishState.lastPublishedAt }}
                </p>
                <p v-else>尚未发布</p>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<script setup>
import { useVersionStore } from '../stores/versionStore'
import AppShell from '../components/layout/AppShell.vue'

const versionStore = useVersionStore()
</script>

<style scoped>
.s4-page { padding: 20px; min-height: calc(100vh - 140px); }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 22px; color: #111827; }
.page-header p { margin: 6px 0 0; font-size: 14px; color: #607a71; }
.page-body { flex: 1; }
.s4-layout { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.section-card { background: #fff; border: 1px solid #dbe6df; border-radius: 16px; padding: 16px; box-shadow: 0 4px 12px rgba(15,23,42,0.04); }
.section-card h3 { margin: 0 0 12px; font-size: 16px; color: #2d5f58; }
.empty-tip { color: #94a3b8; text-align: center; padding: 40px 0; font-size: 14px; }
.version-list, .change-list { display: flex; flex-direction: column; gap: 8px; }
.version-item { display: flex; align-items: center; gap: 12px; padding: 10px; background: #f6faf8; border-radius: 10px; }
.version-item strong { color: #5ca68f; min-width: 32px; }
.version-item span { flex: 1; font-size: 14px; color: #334155; }
.version-item small { font-size: 12px; color: #94a3b8; }
.change-item { display: flex; align-items: center; gap: 10px; padding: 8px 10px; background: #f6faf8; border-radius: 10px; }
.change-type { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: #edf5f2; color: #2f605a; }
.change-status { font-size: 11px; padding: 2px 8px; border-radius: 999px; }
.change-status.pending { background: #fef3c7; color: #92400e; }
.change-status.applied { background: #d1fae5; color: #065f46; }
.publish-info p { color: #607a71; font-size: 14px; }

@media (max-width: 1200px) {
  .s4-layout { grid-template-columns: 1fr; }
}
</style>
