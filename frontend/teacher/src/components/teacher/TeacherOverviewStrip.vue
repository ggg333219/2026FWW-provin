<template>
  <div class="overview-strip">
    <template v-if="mode === 'platform'">
      <div class="overview-item course-item">
        <span class="overview-label">当前视图</span>
        <span class="overview-value course-name">平台管理工作台</span>
      </div>
      <div class="overview-item">
        <span class="overview-label">平台用户</span>
        <span class="overview-value">{{ platformSummary.users || 0 }}</span>
      </div>
      <div class="overview-item">
        <span class="overview-label">平台课程</span>
        <span class="overview-value">{{ platformSummary.courses || 0 }}</span>
      </div>
      <div class="overview-item">
        <span class="overview-label">平台班级</span>
        <span class="overview-value">{{ platformSummary.classes || 0 }}</span>
      </div>
      <div class="overview-item">
        <span class="overview-label">平台选课</span>
        <span class="overview-value">{{ platformSummary.enrollments || 0 }}</span>
      </div>
    </template>

    <template v-else>
      <div class="overview-item course-item">
      <span class="overview-label">当前课件</span>
      <span class="overview-value course-name" :title="currentCourseName || '未选择'">
        {{ currentCourseName || '未选择' }}
      </span>
      </div>
      <div class="overview-item">
        <span class="overview-label">页码</span>
        <span class="overview-value">第 {{ currentEditPage }} 页 / 共 {{ currentCourseTotalPages || 0 }} 页</span>
      </div>
      <div class="overview-item">
        <span class="overview-label">发布状态</span>
        <span class="overview-value status-val" :class="currentCoursePublished ? 'success' : 'pending'">
          <span class="status-dot"></span>
          {{ currentCoursePublished ? '已发布' : '未发布' }}
        </span>
      </div>
    </template>
  </div>
</template>

<script setup>
defineProps({
  mode: {
    type: String,
    default: 'course'
  },
  currentCourseName: {
    type: String,
    default: ''
  },
  currentEditPage: {
    type: Number,
    default: 1
  },
  currentCourseTotalPages: {
    type: Number,
    default: 0
  },
  currentCoursePublished: {
    type: Boolean,
    default: false
  },
  platformSummary: {
    type: Object,
    default: () => ({ users: 0, courses: 0, classes: 0, enrollments: 0 })
  }
})
</script>

<style scoped>
.overview-strip {
  min-height: 68px;
  background: rgba(255, 255, 255, 0.72);
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  display: flex;
  align-items: center;
  padding: 12px 24px;
  gap: 12px;
  flex-shrink: 0;
  backdrop-filter: blur(16px);
  overflow-x: auto;
}

.overview-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  min-width: 180px;
  padding: 12px 14px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.95) 0%, rgba(255, 255, 255, 0.96) 100%);
  border: 1px solid rgba(203, 213, 225, 0.7);
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.04);
}

.course-item {
  min-width: 260px;
}

.overview-label {
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
}

.overview-value {
  font-size: 14px;
  color: #0f172a;
  font-weight: 700;
  white-space: nowrap;
}

.overview-value.course-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-val {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.overview-value.success {
  color: #2F605A;
}

.overview-value.success .status-dot {
  background: #2F605A;
}

.overview-value.pending {
  color: #d97706;
}

.overview-value.pending .status-dot {
  background: #d97706;
}
</style>