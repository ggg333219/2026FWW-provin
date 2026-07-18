<template>
  <div class="header-shell">
    <header class="topbar">
      <div class="brand">
        <div class="logo">学</div>
        <div>
          <div class="brand-title">智能学习课堂系统</div>
          <div class="brand-sub">学生端学习驾驶舱</div>
        </div>
      </div>
      <div class="status-group">
        <span class="pill">账号 {{ studentId }}</span>
        <span class="pill ellipsis">课程 {{ currentCourseName || '未分配课程' }}</span>
        <span class="pill" :class="backendStatus">后端 {{ backendStatusLabel }}</span>
      </div>
    </header>

    <section class="overview">
      <div class="progress-card">
        <div class="overview-title">学习进度</div>
        <el-progress :percentage="progressPercent" :stroke-width="12" :show-text="true" color="#2f605a" />
      </div>
      <div class="state-card">
        <div class="overview-title">学习状态</div>
        <div class="overview-meta">
          <span>第 {{ currentPage }} 页</span>
          <span>{{ isPlay ? '讲授进行中' : '讲授已暂停' }}</span>
        </div>
        <div class="state-indicators">
          <div class="indicator-item">
            <span class="label">学习时长</span>
            <span class="value">{{ studyDuration }} 分钟</span>
          </div>
          <div class="indicator-item">
            <span class="label">专注度</span>
            <span class="value">{{ focusScore }}%</span>
          </div>
          <div class="indicator-item">
            <span class="label">掌握度</span>
            <span class="value">{{ masteryRate }}%</span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
/* eslint-disable no-undef */
defineProps({
  studentId: {
    type: String,
    required: true
  },
  currentCourseName: {
    type: String,
    default: ''
  },
  backendStatus: {
    type: String,
    default: 'checking'
  },
  backendStatusLabel: {
    type: String,
    default: '检测中'
  },
  progressPercent: {
    type: Number,
    default: 0
  },
  currentPage: {
    type: Number,
    default: 1
  },
  isPlay: {
    type: Boolean,
    default: false
  },
  studyDuration: {
    type: Number,
    default: 0
  },
  focusScore: {
    type: Number,
    default: 0
  },
  masteryRate: {
    type: Number,
    default: 0
  }
})
</script>

<style scoped>
.header-shell {
  padding: 14px 18px 0;
}

.topbar {
  min-height: 64px;
  background: linear-gradient(135deg, #2f605a 0%, #4d8a80 55%, #6ca99f 100%);
  color: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-radius: 14px;
  box-shadow: 0 12px 24px rgba(47, 96, 90, 0.25);
  gap: 12px;
}

.overview {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}

.progress-card, .state-card {
  background: #fff;
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

.overview-title {
  font-size: 14px;
  font-weight: 700;
  color: #475569;
  margin-bottom: 8px;
}

.overview-meta {
  display: flex;
  gap: 12px;
  font-size: 13px;
  color: #64748b;
}

.state-indicators {
  margin-top: 8px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.indicator-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px;
  background: #f8fafc;
  border-radius: 8px;
}

.label {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 2px;
}

.value {
  font-size: 14px;
  font-weight: 700;
  color: #334155;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.16);
  border: 1px solid rgba(255, 255, 255, 0.35);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 700;
}

.brand-title {
  font-size: 16px;
  font-weight: 700;
}

.brand-sub {
  font-size: 12px;
  opacity: 0.9;
  margin-top: 2px;
}

.status-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.pill {
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.17);
  border: 1px solid rgba(255, 255, 255, 0.26);
  font-size: 12px;
  line-height: 1.2;
}

.ellipsis {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pill.online {
  background: rgba(22, 163, 74, 0.25);
  border-color: rgba(220, 252, 231, 0.35);
}

.pill.offline {
  background: rgba(220, 38, 38, 0.25);
  border-color: rgba(254, 202, 202, 0.35);
}

.pill.checking {
  background: rgba(245, 158, 11, 0.22);
  border-color: rgba(254, 240, 138, 0.35);
}

.overview {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 12px;
  margin-top: 10px;
}

.progress-card,
.state-card {
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #d9e7df;
  padding: 12px 16px;
  box-shadow: 0 10px 18px rgba(33, 61, 54, 0.06);
}

.overview-title {
  font-size: 13px;
  color: #50655c;
  font-weight: 700;
  margin-bottom: 8px;
}

.overview-meta {
  display: flex;
  gap: 18px;
  font-size: 13px;
  color: #2d4e47;
}

@media (max-width: 980px) {
  .topbar {
    flex-direction: column;
    align-items: flex-start;
  }

  .status-group {
    justify-content: flex-start;
  }

  .overview {
    grid-template-columns: 1fr;
  }
}
</style>