<template>
  <div class="section-card">
    <h3>导出中心</h3>

    <div v-if="!genId" class="empty-tip">请先加载版本</div>
    <div v-else class="export-panel">
      <!-- 格式选择 -->
      <div class="export-formats">
        <label>
          <input v-model="selectedFormat" type="radio" value="pptx" :disabled="exportIsActive" />
          <span class="fmt-label">PPTX 演示文稿</span>
        </label>
        <label>
          <input v-model="selectedFormat" type="radio" value="docx" :disabled="exportIsActive" />
          <span class="fmt-label">DOCX 教案文档</span>
        </label>
        <label>
          <input v-model="selectedFormat" type="radio" value="both" :disabled="exportIsActive" />
          <span class="fmt-label">同时导出</span>
        </label>
      </div>

      <!-- 操作按钮 -->
      <button
        class="btn btn-primary"
        :disabled="!genId || exportIsActive || loading"
        @click="$emit('start-export', selectedFormat)"
      >
        {{ exportIsActive ? '导出中...' : '开始导出' }}
      </button>

      <!-- 状态与进度 -->
      <div v-if="exportStatus !== 'idle'" class="export-status">
        <div class="status-row">
          <span class="status-label">状态:</span>
          <span class="status-value" :class="exportStatus">
            {{ statusText }}
          </span>
        </div>

        <div v-if="exportIsActive" class="progress-bar-track">
          <div class="progress-bar-fill" :style="{ width: progressPct + '%' }"></div>
        </div>

        <!-- 完成 -->
        <div v-if="exportStatus === 'done'" class="done-section">
          <span class="done-icon">✅ 导出完成</span>
          <button
            v-if="exportDownloadUrl"
            class="btn btn-sm"
            @click="handleDownload"
          >
            下载文件
          </button>
          <button class="btn btn-sm" @click="$emit('reset-export')">重新导出</button>
        </div>

        <!-- 失败 -->
        <div v-if="exportStatus === 'failed'" class="error-section">
          <span class="error-icon">❌ 导出失败</span>
          <p v-if="exportError" class="error-msg">{{ exportError }}</p>
          <button class="btn btn-sm" @click="$emit('reset-export')">重试</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  genId: { type: String, default: '' },
  exportStatus: { type: String, default: 'idle' },
  exportFormat: { type: String, default: 'pptx' },
  exportDownloadUrl: { type: String, default: '' },
  exportError: { type: String, default: '' },
  loading: { type: Boolean, default: false }
})

defineEmits(['start-export', 'reset-export'])

const selectedFormat = ref(props.exportFormat || 'pptx')

const exportIsActive = computed(() => ['pending', 'exporting'].includes(props.exportStatus))

const statusText = computed(() => {
  const map = {
    idle: '待导出',
    pending: '排队中',
    exporting: '导出中',
    done: '已完成',
    failed: '失败'
  }
  return map[props.exportStatus] || props.exportStatus
})

const progressPct = ref(0)
// Simulated progress bar animation
let progressTimer = null
import { watch } from 'vue'
watch(() => props.exportStatus, (val) => {
  if (val === 'pending' || val === 'exporting') {
    progressPct.value = 0
    progressTimer = setInterval(() => {
      if (progressPct.value < 90) {
        progressPct.value += Math.random() * 15 + 2
      }
    }, 600)
  } else if (val === 'done') {
    progressPct.value = 100
    if (progressTimer) clearInterval(progressTimer)
  } else {
    progressPct.value = 0
    if (progressTimer) clearInterval(progressTimer)
  }
})

function handleDownload() {
  if (props.exportDownloadUrl) {
    window.open(props.exportDownloadUrl, '_blank')
  }
}
</script>

<style scoped>
.section-card {
  background: #fff; border: 1px solid #dbe6df; border-radius: 16px;
  padding: 16px; box-shadow: 0 4px 12px rgba(15,23,42,0.04);
  height: fit-content;
}
.section-card h3 { margin: 0 0 12px; font-size: 16px; color: #2d5f58; }
.empty-tip { color: #94a3b8; text-align: center; padding: 40px 0; font-size: 14px; }

.export-panel { display: flex; flex-direction: column; gap: 14px; }
.export-formats { display: flex; flex-direction: column; gap: 8px; }
.export-formats label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 14px; color: #334155; }
.export-formats input[type="radio"] { accent-color: #5ca68f; }
.fmt-label { user-select: none; }

.btn {
  padding: 8px 18px; border: none; border-radius: 10px; cursor: pointer;
  font-size: 14px; font-weight: 500; transition: all 0.15s;
}
.btn-primary { background: #5ca68f; color: #fff; }
.btn-primary:hover { background: #4a8d78; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sm { padding: 6px 14px; font-size: 13px; background: #edf5f2; color: #2d5f58; border: 1px solid #c6ded6; border-radius: 8px; margin-right: 6px; }
.btn-sm:hover { background: #d6ece3; }

.export-status { margin-top: 4px; }
.status-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.status-label { font-size: 13px; color: #607a71; }
.status-value { font-size: 13px; font-weight: 600; }
.status-value.pending, .status-value.exporting { color: #b45309; }
.status-value.done { color: #059669; }
.status-value.failed { color: #dc2626; }

.progress-bar-track {
  height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; margin-bottom: 8px;
}
.progress-bar-fill {
  height: 100%; background: linear-gradient(90deg, #5ca68f, #3b8b7a); border-radius: 3px; transition: width 0.4s;
}

.done-section { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
.done-icon { font-size: 14px; color: #059669; font-weight: 500; }

.error-section { margin-top: 4px; }
.error-icon { font-size: 14px; color: #dc2626; font-weight: 500; }
.error-msg { font-size: 12px; color: #991b1b; margin: 4px 0 8px; }
</style>
