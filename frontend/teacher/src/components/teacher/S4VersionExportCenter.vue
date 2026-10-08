<template>
  <div class="section-card">
    <h3>导出中心</h3>
    <p v-if="genId" class="export-context">{{ exportDescription }}</p>

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
        <label>
          <input v-model="selectedFormat" type="radio" value="lesson_plan" :disabled="exportIsActive" />
          <span class="fmt-label">📄 Word 标准教案</span>
        </label>
        <label>
          <input v-model="selectedFormat" type="radio" value="interactive" :disabled="exportIsActive" />
          <span class="fmt-label">🎮 HTML5 互动课件</span>
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

      <!-- HTML 课件预览 -->
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
          <div v-if="downloadFiles.length" class="download-list">
            <button v-for="file in downloadFiles" :key="file.format" class="btn btn-sm" @click="handleDownload(file.url, file.format)">
              下载 {{ file.label }}
            </button>
          </div>
          <button
            v-else-if="exportDownloadUrl"
            class="btn btn-sm"
            @click="handleDownload(exportDownloadUrl, selectedFormat)"
          >
            下载文件
          </button>
          <button class="btn btn-sm" @click="$emit('reset-export')">重新导出</button>
        </div>
        <p v-if="downloadError" class="error-msg">{{ downloadError }}</p>

        <div v-if="exportQualityReport" class="quality-report" :class="exportQualityReport.status">
          <strong>{{ qualityStatusText }}</strong>
          <span>已检查 {{ exportQualityReport.slide_count }} 页</span>
          <ul v-if="exportQualityReport.findings?.length">
            <li v-for="(finding, index) in exportQualityReport.findings" :key="`${finding.code}-${index}`">
              {{ finding.slide_number ? `第 ${finding.slide_number} 页：` : '' }}{{ finding.message }}
            </li>
          </ul>
        </div>

        <div v-if="exportStatus === 'failed' && Object.keys(exportFiles).length" class="partial-files">
          <strong>其他格式仍可下载</strong>
          <button v-for="file in downloadFiles" :key="file.format" class="btn btn-sm" @click="handleDownload(file.url, file.format)">
            下载 {{ file.label }}
          </button>
        </div>

        <!-- 失败 -->
        <div v-if="exportStatus === 'failed'" class="error-section">
          <span class="error-icon">❌ 导出失败</span>
          <p v-if="exportError" class="error-msg">{{ exportError }}</p>
          <button class="btn btn-sm" @click="$emit('start-export', selectedFormat)">重试</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { API_BASE } from '../../config/api'

const props = defineProps({
  genId: { type: String, default: '' },
  exportStatus: { type: String, default: 'idle' },
  exportFormat: { type: String, default: 'pptx' },
  exportDownloadUrl: { type: String, default: '' },
  exportFiles: { type: Object, default: () => ({}) },
  exportError: { type: String, default: '' },
  exportQualityReport: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  courseTitle: { type: String, default: '未命名课件' }
  ,versionLabel: { type: String, default: 'v1' }
})

defineEmits(['start-export', 'reset-export'])

const selectedFormat = ref(props.exportFormat || 'pptx')
const downloadError = ref('')

const exportIsActive = computed(() => ['pending', 'exporting'].includes(props.exportStatus))
const exportFileName = computed(() => {
  const safeTitle = String(props.courseTitle || '未命名课件').replace(/[\\/:*?"<>|]/g, '_')
  const extension = selectedFormat.value === 'both' ? 'zip' : (selectedFormat.value === 'interactive' ? 'html' : (selectedFormat.value === 'lesson_plan' ? 'docx' : selectedFormat.value))
  return `${safeTitle}_${props.versionLabel}.${extension}`
})
const exportDescription = computed(() => selectedFormat.value === 'both'
  ? `导出文件：${String(props.courseTitle || '未命名课件')}_${props.versionLabel}（PPTX + DOCX + HTML5）`
  : `导出文件：${exportFileName.value}`)
const downloadFiles = computed(() => {
  const labels = { pptx: 'PPTX', docx: 'DOCX', html: 'HTML5', html5: 'HTML5', interactive: 'HTML5' }
  return Object.entries(props.exportFiles || {})
    .filter(([, url]) => Boolean(url))
    .map(([format, url]) => ({ format, url, label: labels[format] || format.toUpperCase() }))
})

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

async function handleDownload(url, format = 'pptx') {
  if (!url) return
  downloadError.value = ''
  try {
    const target = new URL(url, API_BASE)
    const headers = new Headers()
    if (target.origin === new URL(API_BASE).origin) {
      const token = window.localStorage.getItem('fuww_teacher_auth_token')
      if (token && !token.startsWith('local_')) headers.set('Authorization', `Bearer ${token}`)
    }
    const response = await fetch(target.href, { headers })
    if (!response.ok) throw new Error(`下载失败（${response.status}）`)
    const objectUrl = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = `${String(props.courseTitle || '课件').replace(/[\\/:*?"<>|]/g, '_')}_${props.versionLabel}.${format === 'html5' || format === 'interactive' ? 'html' : format === 'lesson_plan' ? 'docx' : format}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
  } catch (error) {
    downloadError.value = error?.message || '下载失败'
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
.export-context { margin: -5px 0 12px; color: #71847d; font-size: 12px; }
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
.btn-secondary { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }
.btn-secondary:hover { background: #bae6fd; }
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.preview-hint { font-size: 12px; color: #94a3b8; margin: 0; }
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

.done-section { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 4px; }
.download-list { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.done-icon { font-size: 14px; color: #059669; font-weight: 500; }

.error-section { margin-top: 4px; }
.error-icon { font-size: 14px; color: #dc2626; font-weight: 500; }
.error-msg { font-size: 12px; color: #991b1b; margin: 4px 0 8px; }
.quality-report { margin-top: 10px; padding: 10px 12px; border-left: 3px solid #15803d; background: #f0fdf4; color: #166534; font-size: 13px; }
.quality-report.passed_with_warnings { border-color: #d97706; background: #fffbeb; color: #92400e; }
.quality-report.failed { border-color: #dc2626; background: #fef2f2; color: #991b1b; }
.quality-report span { margin-left: 10px; }
.quality-report ul { margin: 6px 0 0; padding-left: 18px; }
.quality-report li + li { margin-top: 4px; }
</style>
