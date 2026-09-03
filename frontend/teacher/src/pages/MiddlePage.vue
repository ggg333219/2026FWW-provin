<template>
  <AppShell ref="shellRef">
    <div class="teacher-middle-layout">
      <!-- 左侧用户信息栏 -->
      <aside class="middle-user-sidebar">
        <div class="middle-avatar">{{ (authStore.username || '教').slice(0, 1).toUpperCase() }}</div>
        <div class="middle-username">{{ authStore.username || '教师' }}</div>
        <div class="middle-subtitle">教学中间页</div>

        <button class="middle-side-btn primary" @click="enterNewFlow">📋 新建课件</button>
        <button class="middle-side-btn" @click="switchView('home')">课程中间页</button>
        <button class="middle-side-btn" @click="switchView('platform')">平台管理</button>
      </aside>

      <!-- 主面板 -->
      <section class="middle-main-panel" v-loading="workspaceStore.platformOverviewLoading">
        <template v-if="currentView === 'home'">
          <div class="middle-head">
            <div>
              <h3>教师中间页</h3>
              <p>登录后先进入这里。点击课程卡片进入教学页面，平台管理在左侧按钮中打开。</p>
            </div>
            <button class="ghost-btn" @click="workspaceStore.loadPlatformOverview()">刷新</button>
          </div>

          <div class="middle-tile-grid">
            <button
              v-for="tile in platformTiles"
              :key="tile.id"
              class="middle-tile"
              :class="{ mock: tile.mock }"
              @click="openTile(tile)"
            >
              <div class="tile-badge">{{ tile.mock ? '占位课程' : '平台课程' }}</div>
              <h4>{{ tile.name }}</h4>
              <p>{{ tile.desc }}</p>
              <div class="tile-meta">
                <span>{{ tile.metaA }}</span>
                <span>{{ tile.metaB }}</span>
              </div>
            </button>
          </div>
        </template>

        <template v-else>
          <div class="middle-head compact">
            <div>
              <h3>平台管理</h3>
              <p>这里保留原平台管理功能，确保兼容历史流程。</p>
            </div>
            <button class="ghost-btn" @click="switchView('home')">返回中间页</button>
          </div>
          <PlatformManagementPanel />
        </template>
      </section>
    </div>
  </AppShell>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import { useWorkspaceStore } from '../stores/workspaceStore'
import AppShell from '../components/layout/AppShell.vue'
import PlatformManagementPanel from '../components/teacher/PlatformManagementPanel.vue'

const router = useRouter()
const authStore = useAuthStore()
const workspaceStore = useWorkspaceStore()
const shellRef = ref(null)

const currentView = ref('home')

const switchView = (view) => {
  currentView.value = view
  if (view === 'platform') {
    // platform 视图由 PlatformManagementPanel 自行管理
  }
}

const platformTiles = computed(() => {
  const courseItems = Array.isArray(workspaceStore.platformOverviewData?.recentCourses)
    ? workspaceStore.platformOverviewData.recentCourses
    : []
  if (courseItems.length > 0) {
    return courseItems.map((item, index) => ({
      id: String(item.courseId || `platform-course-${index + 1}`),
      name: item.title || `未命名课程 ${index + 1}`,
      desc: '来自平台课程池，点击进入附加功能页继续管理。',
      metaA: item.semester || '未设学期',
      metaB: item.status || 'unknown',
      mock: false
    }))
  }
  return Array.from({ length: 6 }).map((_, index) => ({
    id: `platform-mock-${index + 1}`,
    name: `平台占位课程 ${String(index + 1).padStart(2, '0')}`,
    desc: '暂无真实平台课程数据，先使用占位卡片维持中间页结构。',
    metaA: '示例学期',
    metaB: 'draft',
    mock: true
  }))
})

const openTile = (tile) => {
  if (!tile) return
  workspaceStore.enterWorkspace()
  router.push({ name: 'Workspace', query: { courseId: tile.id } })
}

const enterNewFlow = () => {
  router.push({ name: 'S1Intent' })
}

onMounted(async () => {
  await workspaceStore.loadPlatformOverview()
})
</script>

<style scoped>
.teacher-middle-layout {
  margin-top: 14px;
  min-height: calc(100vh - 110px);
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 14px;
  padding: 14px;
}

.middle-user-sidebar {
  border-radius: 20px;
  border: 1px solid #d3e3db;
  background: linear-gradient(180deg, #f4fbf7 0%, #e8f4ee 100%);
  color: #2f5e55;
  padding: 20px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 0 12px 24px rgba(33, 61, 54, 0.1);
}

.middle-avatar {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
  font-weight: 800;
  color: #2a5a50;
  background: linear-gradient(180deg, #ffffff 0%, #dceee6 100%);
}

.middle-username {
  margin-top: 12px;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.middle-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #6b887e;
}

.middle-side-btn {
  margin-top: 10px;
  width: 100%;
  border: 1px solid #bdd8cb;
  border-radius: 12px;
  padding: 10px 12px;
  background: #ffffff;
  color: #2f605a;
  font-weight: 600;
  cursor: pointer;
}

.middle-side-btn:hover {
  border-color: #8fbcae;
  background: #f4fbf7;
}
.middle-side-btn.primary {
  background: #2f605a;
  color: #fff;
  border-color: #2f605a;
}
.middle-side-btn.primary:hover {
  background: #3d7a70;
  border-color: #3d7a70;
}

.middle-main-panel {
  border-radius: 20px;
  border: 1px solid #dbe6df;
  background: linear-gradient(180deg, #ffffff 0%, #f6faf8 100%);
  padding: 18px;
  box-shadow: 0 16px 30px rgba(33, 61, 54, 0.08);
}

.middle-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.middle-head h3 {
  margin: 0;
  font-size: 24px;
  color: #0f172a;
}

.middle-head p {
  margin: 8px 0 0;
  font-size: 14px;
  color: #607a71;
}

.middle-head.compact {
  margin-bottom: 12px;
}

.ghost-btn {
  border: 0;
  background: #ffffff;
  color: #334155;
  border-radius: 999px;
  padding: 8px 16px;
  font-size: 12px;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(15, 23, 42, 0.08);
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.ghost-btn:hover {
  background: #f7f8fc;
  transform: translateY(-1px);
  box-shadow: 0 8px 16px rgba(15, 23, 42, 0.1);
}

.middle-tile-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
  max-height: calc(100vh - 280px);
  overflow: auto;
  padding-right: 4px;
}

.middle-tile {
  border: 1px solid #d8e6de;
  border-radius: 16px;
  background: linear-gradient(180deg, #ffffff 0%, #f5faf7 100%);
  padding: 14px;
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.middle-tile:hover {
  transform: translateY(-2px);
  border-color: #8fbcae;
  box-shadow: 0 12px 20px rgba(33, 61, 54, 0.1);
}

.middle-tile.mock {
  background: linear-gradient(180deg, #fcfcff 0%, #f4f6fd 100%);
}

.middle-tile h4 {
  margin: 10px 0 6px;
  font-size: 17px;
  color: #284a43;
}

.middle-tile p {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: #638075;
}

.tile-badge {
  display: inline-flex;
  padding: 3px 9px;
  border-radius: 999px;
  background: #edf5f2;
  color: #2f605a;
  font-size: 11px;
  font-weight: 700;
}

.tile-meta {
  margin-top: 10px;
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: #4d665d;
}

@media (max-width: 980px) {
  .teacher-middle-layout {
    grid-template-columns: 1fr;
  }

  .middle-user-sidebar {
    align-items: flex-start;
  }

  .middle-tile-grid {
    max-height: none;
  }
}
</style>
