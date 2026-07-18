<template>
  <div class="courseware-manage-section">
    <nav class="right-rail" aria-label="右侧功能导航">
      <button
        class="rail-btn"
        :class="{ active: activePanel === 'courseware' }"
        @click="togglePanel('courseware')"
        title="课件管理"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="4" y="4" width="16" height="16" rx="2"></rect>
          <line x1="8" y1="9" x2="16" y2="9"></line>
          <line x1="8" y1="13" x2="16" y2="13"></line>
          <line x1="8" y1="17" x2="13" y2="17"></line>
        </svg>
        <span>课件</span>
      </button>

      <button
        class="rail-btn"
        :class="{ active: activePanel === 'graph' }"
        :disabled="!currentCourseId"
        @click="togglePanel('graph')"
        :title="currentCourseId ? '知识图谱维护' : '请先选择课件'"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="5" cy="6" r="2"></circle>
          <circle cx="19" cy="6" r="2"></circle>
          <circle cx="12" cy="18" r="2"></circle>
          <path d="M7 7.4l3.8 7.1"></path>
          <path d="M17 7.4l-3.8 7.1"></path>
        </svg>
        <span>图谱</span>
      </button>
    </nav>

    <transition name="drawer-slide">
      <section v-if="isOverlayOpen" class="overlay-drawer">
        <header class="section-header">
          <h3>{{ activePanel === 'courseware' ? '课件管理' : '知识图谱维护' }}</h3>
          <div class="header-actions">
            <template v-if="activePanel === 'courseware'">
              <button @click="$emit('open-publish')" class="publish-btn" :disabled="!currentCourseId">发布</button>
              <button @click="$emit('open-upload')" class="upload-btn">+ 上传</button>
            </template>
            <button class="close-btn" @click="closeOverlay" title="收起面板">关闭</button>
          </div>
        </header>

        <div v-if="activePanel === 'courseware'" class="panel-body">
          <div class="courseware-list">
            <div v-if="courseListLoading" class="list-loading-tip">
              课件列表加载中...
            </div>
            <template v-else>
              <div
                v-for="course in coursewareList"
                :key="course.id"
                class="course-item"
                :class="{ active: course.id === currentCourseId }"
                @click="$emit('select-course', course)"
              >
                <div class="course-main">
                  <span class="course-name" :title="course.name">{{ course.name }}</span>
                  <div class="course-meta-row">
                    <span class="course-type-badge" :class="fileTypeClass(course.fileType)">{{ fileTypeBadge(course.fileType) }}</span>
                    <span class="course-meta-text">共{{ Number(course.knowledgePointCount) || 0 }}个知识点</span>
                  </div>
                </div>
                <div class="course-actions">
                  <span v-if="course.published" class="published-tag">已发布</span>
                  <button @click.stop="$emit('delete-course', course.id)" class="del-btn" :disabled="courseListLoading">删除</button>
                </div>
              </div>

              <div v-if="coursewareList.length === 0" class="empty-list-tip">
                <div class="empty-icon">📂</div>
                <p>暂无课件</p>
                <span>点击上方按钮上传第一个课件</span>
              </div>
            </template>
          </div>

          <div class="page-selector" v-if="currentCourseId">
            <div class="page-header-row">
              <h4>{{ currentCourseName }}</h4>
              <span class="page-indicator">{{ currentEditPage }} / {{ currentCourseTotalPages }}</span>
            </div>
            <div class="page-nav-controls">
              <button
                class="nav-icon-btn"
                :disabled="currentEditPage <= 1"
                @click="$emit('select-page', currentEditPage - 1)"
                title="上一页"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"></polyline></svg>
              </button>
              <div class="page-nav-center">切换页码</div>
              <button
                class="nav-icon-btn"
                :disabled="currentEditPage >= currentCourseTotalPages"
                @click="$emit('select-page', currentEditPage + 1)"
                title="下一页"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
              </button>
            </div>
          </div>
        </div>

        <div v-else class="panel-body graph-body">
          <TeacherKnowledgeGraphPanel
            :course-id="currentCourseId"
            :course-name="currentCourseName"
            @cite-resource="$emit('cite-to-script', $event)"
          />
        </div>
      </section>
    </transition>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import TeacherKnowledgeGraphPanel from './TeacherKnowledgeGraphPanel.vue'

const activePanel = ref('')

const props = defineProps({
  coursewareList: {
    type: Array,
    default: () => []
  },
  currentCourseId: {
    type: String,
    default: ''
  },
  currentCourseName: {
    type: String,
    default: ''
  },
  currentCourseTotalPages: {
    type: Number,
    default: 0
  },
  currentEditPage: {
    type: Number,
    default: 1
  },
  courseListLoading: {
    type: Boolean,
    default: false
  }
})

defineEmits(['open-publish', 'open-upload', 'select-course', 'delete-course', 'select-page', 'cite-to-script'])

const isOverlayOpen = computed(() => activePanel.value !== '')

const togglePanel = (panel) => {
  if (panel === 'graph' && !props.currentCourseId) return
  activePanel.value = activePanel.value === panel ? '' : panel
}

const closeOverlay = () => {
  activePanel.value = ''
}

watch(
  () => props.currentCourseId,
  (courseId) => {
    if (!courseId && activePanel.value === 'graph') {
      activePanel.value = 'courseware'
    }
  }
)

const normalizedFileType = (fileType) => String(fileType || '').trim().toLowerCase()

const fileTypeBadge = (fileType) => {
  const type = normalizedFileType(fileType)
  if (type.includes('pdf')) return 'PDF'
  if (type.includes('ppt') || type.includes('pptx')) return 'PPT'
  if (type.includes('doc')) return 'DOC'
  return 'FILE'
}

const fileTypeClass = (fileType) => {
  const type = normalizedFileType(fileType)
  if (type.includes('pdf')) return 'pdf'
  if (type.includes('ppt')) return 'ppt'
  if (type.includes('doc')) return 'doc'
  return 'file'
}
</script>

<style scoped>
.courseware-manage-section {
  position: relative;
  height: 100%;
  z-index: 5;
}

.right-rail {
  width: 56px;
  height: 100%;
  border-radius: 16px;
  background: linear-gradient(180deg, #f7fcf9 0%, #eef6f2 100%);
  border: 1px solid rgba(120, 156, 140, 0.28);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 8px;
  gap: 10px;
}

.rail-btn {
  width: 100%;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: #5f7467;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 8px 4px;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.rail-btn svg {
  width: 16px;
  height: 16px;
}

.rail-btn span {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.rail-btn:hover:not(:disabled) {
  background: rgba(92, 166, 143, 0.12);
  color: #2f5e52;
  transform: translateY(-1px);
}

.rail-btn.active {
  background: linear-gradient(180deg, #79c3ab 0%, #5ca68f 100%);
  color: #ffffff;
  box-shadow: 0 8px 16px rgba(92, 166, 143, 0.24);
}

.rail-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.overlay-drawer {
  position: absolute;
  top: 0;
  right: 66px;
  width: min(360px, 46vw);
  height: 100%;
  border-radius: 20px;
  background: #ffffff;
  border: 1px solid rgba(120, 156, 140, 0.2);
  box-shadow: 0 24px 44px rgba(15, 23, 42, 0.18);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.section-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 14px 12px;
  border-bottom: 1px solid rgba(120, 156, 140, 0.22);
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  color: #0f172a;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.publish-btn,
.upload-btn,
.close-btn,
.del-btn {
  border: none;
  cursor: pointer;
}

.publish-btn,
.upload-btn {
  padding: 6px 11px;
  font-size: 13px;
  color: #fff;
  border-radius: 10px;
  background: linear-gradient(180deg, #79c3ab 0%, #5ca68f 100%);
  box-shadow: 0 6px 14px rgba(92, 166, 143, 0.22);
}

.upload-btn {
  background: linear-gradient(180deg, #8ecfbb 0%, #6cb59e 100%);
}

.publish-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.close-btn {
  padding: 6px 10px;
  border-radius: 10px;
  font-size: 12px;
  background: #e8f2ed;
  color: #2f5e52;
}

.panel-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.courseware-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.course-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border: 0;
  border-radius: 14px;
  cursor: pointer;
  background: #ffffff;
  transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.course-item:hover {
  background: #f2f9f5;
  box-shadow: 0 8px 20px rgba(50, 88, 72, 0.1);
  transform: translateY(-1px);
}

.course-item.active {
  background: rgba(227, 245, 238, 0.92);
  box-shadow: 0 8px 20px rgba(92, 166, 143, 0.18);
}

.course-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.course-name {
  font-size: 15px;
  color: #0f172a;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 150px;
}

.course-meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.course-type-badge {
  min-width: 34px;
  padding: 1px 6px;
  border-radius: 999px;
  border: 1px solid #cbd5e1;
  text-align: center;
  font-size: 10px;
  font-weight: 700;
  color: #334155;
  background: #f8fafc;
}

.course-meta-text {
  font-size: 12px;
  color: #5f7467;
}

.course-type-badge.pdf {
  color: #b45309;
  border-color: #f5d0a8;
  background: #fff7ed;
}

.course-type-badge.ppt {
  color: #1d4ed8;
  border-color: #bfdbfe;
  background: #eff6ff;
}

.course-type-badge.doc {
  color: #065f46;
  border-color: #a7f3d0;
  background: #ecfdf5;
}

.course-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.published-tag {
  font-size: 11px;
  color: #5ca68f;
  background: rgba(92, 166, 143, 0.16);
  border: 1px solid rgba(92, 166, 143, 0.35);
  padding: 1px 7px;
  border-radius: 999px;
  white-space: nowrap;
}

.del-btn {
  padding: 4px 8px;
  font-size: 12px;
  background: #fee2e2;
  color: #dc2626;
  border-radius: 6px;
}

.del-btn:hover:not(:disabled) {
  background: #fecaca;
}

.empty-list-tip {
  padding: 36px 16px;
  text-align: center;
  background: #f8fcfa;
  border: 1px dashed rgba(86, 130, 112, 0.34);
  border-radius: 12px;
}

.empty-icon {
  font-size: 30px;
  margin-bottom: 10px;
}

.empty-list-tip p {
  color: #334155;
  font-weight: 500;
  margin: 0 0 4px 0;
  font-size: 14px;
}

.empty-list-tip span {
  font-size: 12px;
  color: #94a3b8;
}

.list-loading-tip {
  text-align: center;
  padding: 20px;
  color: #5f7467;
  font-size: 13px;
  font-style: italic;
}

.page-selector {
  flex-shrink: 0;
  padding: 14px 12px;
  border-top: 1px solid rgba(120, 156, 140, 0.22);
  background: #ffffff;
}

.page-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.page-header-row h4 {
  font-size: 13px;
  font-weight: 600;
  margin: 0;
  color: #334155;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 160px;
}

.page-indicator {
  font-size: 12px;
  font-weight: 500;
  color: #5f7467;
  background: #f2f8f5;
  padding: 2px 8px;
  border-radius: 12px;
}

.page-nav-controls {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.nav-icon-btn {
  width: 44px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  background: #f2f8f5;
  color: #5f7467;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.nav-icon-btn svg {
  width: 18px;
  height: 18px;
}

.page-nav-center {
  flex: 1;
  text-align: center;
  font-size: 12px;
  color: #5f7467;
  letter-spacing: 0.02em;
}

.nav-icon-btn:hover:not(:disabled) {
  background: #e9f5ef;
  color: #2d5f52;
  box-shadow: 0 4px 10px rgba(42, 78, 64, 0.14);
}

.nav-icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.graph-body {
  padding: 10px;
}

.drawer-slide-enter-active,
.drawer-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
}

.drawer-slide-enter-from,
.drawer-slide-leave-to {
  transform: translateX(28px);
  opacity: 0;
}

@media (max-width: 1280px) {
  .overlay-drawer {
    width: min(330px, calc(100vw - 120px));
  }
}

@media (max-width: 768px) {
  .right-rail {
    width: 48px;
    padding: 10px 6px;
  }

  .overlay-drawer {
    right: 56px;
    width: min(88vw, 336px);
  }
}
</style>
