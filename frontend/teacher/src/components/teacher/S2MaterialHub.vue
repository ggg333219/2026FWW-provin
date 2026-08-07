<template>
  <div class="s2-hub">
    <!-- ============ 上传区 ============ -->
    <section class="hub-card upload-card">
      <div class="card-head">
        <div>
          <h3>资料上传</h3>
          <span class="card-desc">支持 PPT / PDF / DOCX / 视频 / 音频 / 图片，上传后自动解析为切片</span>
        </div>
        <span class="stat-badge">{{ materialStore.materials.length }} 份素材</span>
      </div>

      <div
        class="drop-zone"
        :class="{ dragging: isDragging, uploading: materialStore.uploading }"
        @click="triggerPick"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleDrop"
      >
        <input
          ref="fileInput"
          type="file"
          multiple
          :accept="ACCEPT_EXTS"
          class="file-input"
          @change="handleFiles($event.target.files)"
        />
        <template v-if="!materialStore.uploading">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="drop-icon">
            <path d="M12 16V4m0 0l-4 4m4-4l4 4" />
            <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
          </svg>
          <p class="drop-title">点击选择或拖拽文件到此处</p>
          <p class="drop-sub">PDF / PPTX / DOCX / MP4 / MP3 / 图片，单文件 ≤ 200MB</p>
        </template>
        <template v-else>
          <div class="uploading-box">
            <div class="spinner"></div>
            <p class="drop-title">正在上传解析…</p>
          </div>
        </template>
      </div>

      <p v-if="uploadError" class="upload-error">{{ uploadError }}</p>
    </section>

    <!-- ============ 解析状态区 ============ -->
    <section v-if="activeParseTasks.length > 0" class="hub-card">
      <div class="card-head">
        <div>
          <h3>解析任务</h3>
          <span class="card-desc">解析状态机：uploaded → parsing → done / failed</span>
        </div>
      </div>
      <div class="task-list">
        <div v-for="task in activeParseTasks" :key="task.taskId" class="task-row">
          <span class="task-file">{{ task.fileName }}</span>
          <span class="task-status" :class="task.status">{{ statusText(task.status) }}</span>
          <span v-if="task.chunkCount > 0" class="task-count">{{ task.chunkCount }} chunks</span>
          <span v-if="task.error" class="task-error" :title="task.error">解析失败</span>
        </div>
      </div>
    </section>

    <!-- ============ 素材列表 + 切片预览 ============ -->
    <section class="hub-card">
      <div class="card-head">
        <div>
          <h3>素材与切片预览</h3>
          <span class="card-desc">勾选素材后在右侧查看 ChunkSchema 切片</span>
        </div>
        <button
          v-if="materialStore.hasSelection"
          class="ghost-link"
          @click="materialStore.clearSelection()"
        >清空选择 ({{ materialStore.selectedCount }})</button>
      </div>

      <div v-if="materialStore.loading" class="state-block">加载素材中…</div>
      <div v-else-if="materialStore.materials.length === 0" class="state-block">
        暂无素材，请先上传资料
      </div>
      <div v-else class="material-layout">
        <!-- 素材列表 -->
        <div class="material-list">
          <div
            v-for="item in materialStore.materials"
            :key="item.id"
            class="material-row"
            :class="{ selected: isSelected(item.id) }"
          >
            <label class="check-box" @click.stop>
              <input
                type="checkbox"
                :checked="isSelected(item.id)"
                @change="materialStore.toggleMaterial(item.id)"
              />
            </label>
            <div class="material-main" @click="materialStore.toggleMaterial(item.id)">
              <span class="type-tag" :class="item.type">{{ typeLabel(item.type) }}</span>
              <div class="material-info">
                <p class="material-title" :title="item.title">{{ item.title }}</p>
                <p class="material-meta">
                  {{ item.source || '未标注来源' }}
                  <template v-if="item.fileSize"> · {{ formatSize(item.fileSize) }}</template>
                  <template v-if="item.chunks && item.chunks.length"> · {{ item.chunks.length }} chunks</template>
                </p>
              </div>
            </div>
            <span class="parse-badge" :class="item.parseStatus || 'uploaded'">
              {{ parseStatusText(item.parseStatus) }}
            </span>
            <button class="del-btn" title="删除素材" @click="removeMaterial(item.id)">×</button>
          </div>
        </div>

        <!-- 切片预览 -->
        <div class="chunk-preview">
          <template v-if="previewChunks.length > 0">
            <div class="chunk-scroll">
              <div v-for="chunk in previewChunks" :key="chunk.chunkId" class="chunk-item">
                <div class="chunk-head">
                  <span class="chunk-seq">#{{ chunk.seqIndex != null ? chunk.seqIndex + 1 : '—' }}</span>
                  <span v-if="chunk.pageStart" class="chunk-loc">第 {{ chunk.pageStart }}<template v-if="chunk.pageEnd && chunk.pageEnd !== chunk.pageStart">-{{ chunk.pageEnd }}</template> 页</span>
                  <span v-else-if="chunk.timeStart != null" class="chunk-loc">{{ fmtTime(chunk.timeStart) }} - {{ fmtTime(chunk.timeEnd) }}</span>
                  <span v-if="chunk.relevanceScore != null" class="chunk-score" :class="{ hot: chunk.relevanceScore >= 0.9 }">
                    相关度 {{ (chunk.relevanceScore * 100).toFixed(0) }}
                  </span>
                </div>
                <p class="chunk-content">{{ chunk.content }}</p>
              </div>
            </div>
          </template>
          <div v-else class="state-block">
            {{ materialStore.hasSelection ? '所选素材暂无切片，请等待解析完成' : '勾选素材以查看切片预览' }}
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMaterialStore } from '../../stores/materialStore'
import { teacherMaterialApi } from '../../services/v1/materialApi'

const props = defineProps({
  /** 会话ID，贯穿 S1 → S2 → S3 */
  sessionId: {
    type: String,
    default: ''
  },
  /** 是否自动加载素材列表 */
  autoLoad: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['toast', 'task-finished'])

const materialStore = useMaterialStore()
const fileInput = ref(null)
const isDragging = ref(false)
const uploadError = ref('')

const ACCEPT_EXTS = [
  '.pdf', '.pptx', '.ppt', '.docx', '.doc', '.txt', '.md',
  '.mp4', '.avi', '.mov', '.mp3', '.wav',
  '.png', '.jpg', '.jpeg', '.gif', '.webp'
].join(',')

const typeMap = { video: '视频', audio: '音频', image: '图片', document: '文档' }

const isSelected = (id) => materialStore.selectedMaterials.includes(id)

const previewChunks = computed(() => {
  if (!materialStore.hasSelection) return []
  return materialStore.materials
    .filter((m) => materialStore.selectedMaterials.includes(m.id))
    .flatMap((m) => m.chunks || [])
})

/** 展示中的解析任务：store 中新增的 + 本地轮询中的 */
const activeParseTasks = computed(() => materialStore.parseTasks)

const typeLabel = (type) => typeMap[type] || '素材'

const statusText = (status) => {
  const map = { processing: '解析中', done: '完成', failed: '失败', pending: '等待' }
  return map[status] || status
}

const parseStatusText = (status) => {
  const map = { uploaded: '已上传', parsing: '解析中', done: '已完成', failed: '失败' }
  return map[status] || status || '已上传'
}

const formatSize = (bytes) => {
  const n = Number(bytes) || 0
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

const fmtTime = (sec) => {
  const s = Number(sec) || 0
  const m = Math.floor(s / 60)
  const r = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`
}

const triggerPick = () => {
  if (materialStore.uploading) return
  fileInput.value?.click()
}

const handleDrop = (event) => {
  isDragging.value = false
  const files = event.dataTransfer?.files
  if (files && files.length) handleFiles(files)
}

const handleFiles = async (fileList) => {
  const files = Array.from(fileList || [])
  if (files.length === 0) return
  uploadError.value = ''
  materialStore.setUploading(true)
  // 多文件并行上传：单个失败不阻塞其余文件
  const results = await Promise.allSettled(files.map(uploadOne))
  materialStore.setUploading(false)
  if (fileInput.value) fileInput.value.value = ''
  const failed = results.filter((r) => r.status === 'rejected')
  if (failed.length > 0) {
    uploadError.value = `有 ${failed.length} 个文件上传失败，其余已正常处理`
    emit('toast', `${failed.length} 个文件上传失败，其余已正常处理`)
  }
}

/** 单个文件：先 multipart 上传，再创建解析任务并轮询 */
async function uploadOne(file) {
  try {
    // 步骤0：立即添加本地占位素材，让用户立即看到上传中状态
    const placeholderId = `placeholder_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
    const placeholderMaterial = {
      id: placeholderId,
      title: file.name,
      type: fileTypeFromName(file.name),
      fileType: String(file.name).split('.').pop() || 'file',
      fileSize: file.size,
      source: '本次上传',
      tags: [],
      parseStatus: 'parsing',
      uploadedAt: new Date().toISOString(),
      chunks: []
    }
    materialStore.addMaterial(placeholderMaterial)
    materialStore.selectMaterial(placeholderId)

    const taskId = `local_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
    materialStore.addParseTask({
      taskId,
      fileName: file.name,
      fileSize: file.size,
      status: 'processing',
      chunkCount: 0,
      error: '',
      createdAt: new Date().toISOString()
    })

    // 步骤1：multipart 上传。
    // 优先走 S2 专用上传（文件落盘到引擎可读目录，返回本地路径，真实后端解析磁盘文件）。
    // 失败时回退到课件上传（minio:// 路径，Mock 端可直接放行）。
    let parseLocalPath = ''
    try {
      const uploadResp = await teacherMaterialApi.uploadParseFile({
        file,
        sessionId: props.sessionId
      })
      parseLocalPath = uploadResp?.data?.file_path || ''
    } catch (err) {
      console.warn('[S2Hub] parse/upload fallback:', err)
    }

    let uploadFallbackPath = ''
    if (!parseLocalPath) {
      try {
        const uploadResp = await teacherMaterialApi.uploadCourseware({
          file,
          title: file.name.replace(/\.[^.]+$/, '')
        })
        const courseId = uploadResp?.data?.courseId || ''
        uploadFallbackPath = courseId ? `minio://courses/${courseId}/${file.name}` : file.name
      } catch (err) {
        // 上传接口不可用时不阻塞后续解析（前端契约已对齐）
        console.warn('[S2Hub] upload fallback:', err)
      }
    }
    const pathHint = parseLocalPath || uploadFallbackPath || file.name

    // 仅对纯文本文件读取头部文本，供 Mock 端生成真实切片。
    // 二进制文件（PDF/PPTX/DOCX/视频/音频/图片）按 UTF-8 解码会产生
    // "%PDF-1.7..." 之类的乱码，直接跳过，交给后端解析磁盘文件 / Mock 种子内容。
    let fileText = ''
    if (isTextFile(file.name)) {
      try {
        fileText = await readTextSmart(file)
      } catch {
        fileText = ''
      }
    }

    const parseResp = await teacherMaterialApi.parseProcess({
      sessionId: props.sessionId,
      filePaths: [pathHint],
      fileContents: fileText ? { [pathHint]: fileText } : undefined
    })
    const realTaskId = parseResp?.data?.task_id || taskId
    materialStore.updateParseTask(taskId, { taskId: realTaskId })

    // 步骤3：轮询解析状态
    pollParseTask(realTaskId, file.name, placeholderId)
    emit('task-finished', { taskId: realTaskId, fileName: file.name })
  } catch (err) {
    materialStore.setError(String(err?.message || err))
    emit('toast', `上传失败：${err?.message || err}`)
    throw err
  }
}

function fileTypeFromName(name) {
  const ext = (String(name || '').split('.').pop() || '').toLowerCase()
  if (['mp4', 'avi', 'mov', 'webm'].includes(ext)) return 'video'
  if (['mp3', 'wav', 'ogg', 'flac'].includes(ext)) return 'audio'
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'].includes(ext)) return 'image'
  return 'document'
}

/** 纯文本扩展名（可安全按 UTF-8 读取头部）。其余视为二进制，交由后端解析。 */
const TEXT_EXTS = ['txt', 'md', 'csv', 'json', 'log', 'html', 'htm', 'xml', 'yaml', 'yml', 'js', 'ts', 'py']
function isTextFile(name) {
  const ext = (String(name || '').split('.').pop() || '').toLowerCase()
  return TEXT_EXTS.includes(ext)
}

async function readTextSmart(file, maxBytes = 1024 * 1024) {
  const ext = (String(file?.name || '').split('.').pop() || '').toLowerCase()
  const blob = file.slice(0, Math.min(file.size || 0, maxBytes))
  const buffer = await blob.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  const encodings = ['utf-8', 'utf-8-sig', 'gb18030', 'gbk', 'big5']
  let best = ''
  let bestScore = -1

  for (const encoding of encodings) {
    try {
      const text = new TextDecoder(encoding, { fatal: false }).decode(bytes)
      const score = scoreDecodedText(text)
      if (score > bestScore) {
        bestScore = score
        best = text
      }
    } catch {
      // ignore unsupported encoding
    }
  }

  const normalized = normalizeTextForFormat(best || '', ext)
  return normalized.trim()
}

function scoreDecodedText(text) {
  const value = String(text || '')
  if (!value) return -1
  const replacementCount = (value.match(/\uFFFD/g) || []).length
  let printable = 0
  let control = 0
  let total = 0
  for (const ch of value) {
    total += 1
    const code = ch.codePointAt(0) || 0
    if (code === 0 || (code < 32 && code !== 9 && code !== 10 && code !== 13)) control += 1
    if (code >= 32 || ch === '\n' || ch === '\t' || ch === '\r') printable += 1
  }
  if (total === 0) return -1
  return (printable / total) * 100 - (control / total) * 400 - replacementCount * 20
}

function normalizeTextForFormat(text, ext) {
  const normalized = String(text || '').replace(/\r\n?/g, '\n').trim()
  if (!normalized) return ''
  if (ext === 'json') {
    try {
      return JSON.stringify(JSON.parse(normalized), null, 2)
    } catch {
      return normalized
    }
  }
  if (ext === 'csv') {
    const lines = normalized.split('\n').map((line) => line.replace(/[ \t]+$/g, ''))
    return lines.filter((line) => line.trim().length > 0).join('\n')
  }
  return normalized
}

/**
 * 统一引擎返回的 ChunkSchema 字段命名。
 * 真实引擎返回 chunk_id / page_ref / seq_index，前端展示用 chunkId / pageStart / seqIndex。
 */
function normalizeChunk(c, materialId) {
  const meta = c.metadata || {}
  const timeRange = Array.isArray(meta.timestamp_range) ? meta.timestamp_range : null
  const pageStart = c.pageStart != null
    ? c.pageStart
    : (c.page_ref != null ? c.page_ref : (meta.page != null ? meta.page : undefined))
  const pageEnd = c.pageEnd != null
    ? c.pageEnd
    : (meta.page_end != null ? meta.page_end : (meta.end_page != null ? meta.end_page : pageStart))
  const sourceType = c.sourceType || c.source_type || meta.source_type || 'text'
  return {
    ...c,
    chunkId: c.chunkId || c.chunk_id,
    materialId: c.materialId || materialId,
    content: c.content || '',
    sourceType,
    sourceRef: c.sourceRef || c.source_ref || c.sourceRefId || c.file_name || meta.file_name || '',
    seqIndex: c.seqIndex != null ? c.seqIndex : (c.seq_index != null ? c.seq_index : 0),
    pageRef: c.pageRef != null ? c.pageRef : (c.page_ref != null ? c.page_ref : pageStart),
    pageStart,
    pageEnd,
    timeStart: c.timeStart != null ? c.timeStart : (timeRange ? timeRange[0] : undefined),
    timeEnd: c.timeEnd != null ? c.timeEnd : (timeRange ? timeRange[1] : undefined),
    relevanceScore: c.relevanceScore != null ? c.relevanceScore : 0.9,
    metadata: meta
  }
}

/** 轮询解析状态直到 done / failed */
let pollTimers = {}
function pollParseTask(taskId, fileName, placeholderId) {
  if (pollTimers[taskId]) return
  const tick = async () => {
    let response
    try {
      response = await teacherMaterialApi.parseStatus(taskId)
    } catch (err) {
      // 单次查询失败不终止轮询，等待下次
      pollTimers[taskId] = window.setTimeout(tick, 1800)
      return
    }
    const data = response?.data || {}
    const status = data.status || 'done'

    if (status === 'done' || status === 'failed') {
      delete pollTimers[taskId]
      const chunkCount = Array.isArray(data.chunks) ? data.chunks.length : 0
      materialStore.updateParseTask(taskId, {
        status: status === 'done' ? 'done' : 'failed',
        chunkCount,
        error: data.error || ''
      })

      // 移除占位素材，用真实数据替换
      if (placeholderId) {
        materialStore.removeMaterial(placeholderId)
      }

      // 更新素材（如果解析成功且后端有 chunks 返回）
      if (status === 'done' && chunkCount > 0) {
        // 后端返回的 materialIds（真实后端/Mock 均可提供），优先使用真实 ID
        const materialIds = data.materialIds || data.material_ids || []
        if (materialIds.length > 0) {
          // 刷新列表拿到真实素材记录，避免本地重复登记
          await materialStore.loadMaterials()
          const materialId = materialIds[0]
          const target = materialStore.materials.find((m) => m.id === materialId)
          if (target) {
            materialStore.selectMaterial(materialId)
            emit('toast', `「${fileName}」解析完成，生成 ${chunkCount} 个切片`)
            emit('task-finished', { taskId, fileName, status, chunkCount })
            return
          }
        }

        // 无 materialIds：先刷新列表，看后端是否已登记同名素材（Mock 端解析完成后会自动入库）
        await materialStore.loadMaterials()
        const matched = [...materialStore.materials].find(
          (m) => m.title === fileName && m.parseStatus === 'done' && (m.chunks || []).length > 0
        )
        if (matched) {
          // 后端已登记：直接选中，避免重复创建同一素材
          materialStore.selectMaterial(matched.id)
        } else {
          // 后端未登记（如真实后端无素材列表接口）：用返回的 chunks 本地登记，
          // 使用稳定的 taskId 派生 ID，避免每次刷新后 ID 漂移
          const materialId = `mat_${taskId}`
          const exists = materialStore.materials.some((m) => m.id === materialId)
          if (!exists) {
            const newMaterial = {
              id: materialId,
              title: fileName,
              type: fileTypeFromName(fileName),
              fileType: String(fileName).split('.').pop() || 'file',
              fileSize: 0,
              source: '本次上传',
              tags: [],
              parseStatus: 'done',
              uploadedAt: new Date().toISOString(),
              chunks: data.chunks.map((c) => normalizeChunk(c, materialId))
            }
            materialStore.addMaterial(newMaterial)
          }
          materialStore.selectMaterial(materialId)
        }
      } else {
        // 无 chunks 返回，尝试从后端拉取最新素材列表
        await materialStore.loadMaterials()
      }
      emit('toast', status === 'done'
        ? `「${fileName}」解析完成，生成 ${chunkCount} 个切片`
        : `「${fileName}」解析失败`)
      emit('task-finished', { taskId, fileName, status, chunkCount })
      return
    }

    // 未完成，继续轮询
    materialStore.updateParseTask(taskId, { status: 'processing' })
    pollTimers[taskId] = window.setTimeout(tick, 1600)
  }
  tick()
}

async function removeMaterial(id) {
  try {
    // 先尝试同步到后端；失败时仅在本地移除（如占位素材/离线 Mock）
    await teacherMaterialApi.delete(id)
  } catch (err) {
    console.warn('[S2Hub] 删除素材未同步到后端，仅本地移除:', err)
  }
  materialStore.removeMaterial(id)
  emit('toast', '素材已删除')
}

onMounted(async () => {
  if (props.autoLoad) {
    await materialStore.loadMaterials()
  }
})

onUnmounted(() => {
  Object.values(pollTimers).forEach((timer) => window.clearTimeout(timer))
  pollTimers = {}
})
</script>

<style scoped>
.s2-hub {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hub-card {
  background: #fff;
  border: 1px solid #e4ede8;
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.card-head h3 {
  margin: 0;
  font-size: 16px;
  color: #1f2a37;
}

.card-desc {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #7a8a9a;
}

.stat-badge {
  flex-shrink: 0;
  font-size: 12px;
  color: #2f605a;
  background: #e8f0ef;
  border-radius: 999px;
  padding: 4px 12px;
  font-weight: 600;
}

/* ---------- 上传区 ---------- */
.drop-zone {
  border: 1.5px dashed #b8cdc6;
  border-radius: 14px;
  padding: 30px 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  background: #fafcfa;
}

.drop-zone:hover,
.drop-zone.dragging {
  border-color: #5ca68f;
  background: #f0f9f5;
}

.drop-zone.uploading {
  cursor: wait;
}

.file-input {
  display: none;
}

.drop-icon {
  width: 34px;
  height: 34px;
  color: #5ca68f;
  margin: 0 auto 8px;
}

.drop-title {
  margin: 0;
  font-size: 14px;
  color: #334155;
  font-weight: 600;
}

.drop-sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: #8ba098;
}

.uploading-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.spinner {
  width: 22px;
  height: 22px;
  border: 3px solid #d7e6e0;
  border-top-color: #5ca68f;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.upload-error {
  margin: 10px 0 0;
  color: #b91c1c;
  font-size: 13px;
}

/* ---------- 解析任务 ---------- */
.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: #f8fbf9;
  border: 1px solid #e4ede8;
  border-radius: 10px;
  font-size: 13px;
}

.task-file {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #334155;
}

.task-status {
  font-size: 12px;
  font-weight: 600;
  border-radius: 999px;
  padding: 2px 10px;
}

.task-status.processing {
  color: #1d4ed8;
  background: #dbeafe;
}

.task-status.done {
  color: #166534;
  background: #dcfce7;
}

.task-status.failed {
  color: #991b1b;
  background: #fee2e2;
}

.task-count {
  font-size: 12px;
  color: #64748b;
}

.task-error {
  font-size: 12px;
  color: #b91c1c;
}

/* ---------- 素材布局 ---------- */
.material-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 16px;
}

.material-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 420px;
  overflow-y: auto;
  padding-right: 4px;
}

.material-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #e7efeb;
  border-radius: 12px;
  transition: all 0.15s;
}

.material-row:hover {
  border-color: #b9d4ca;
}

.material-row.selected {
  border-color: #5ca68f;
  background: #f0f9f5;
}

.check-box {
  display: flex;
  align-items: center;
}

.check-box input {
  width: 16px;
  height: 16px;
  accent-color: #5ca68f;
  cursor: pointer;
}

.material-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.type-tag {
  flex-shrink: 0;
  font-size: 11px;
  border-radius: 6px;
  padding: 3px 8px;
  font-weight: 600;
}

.type-tag.document { background: #e8f0ef; color: #2f605a; }
.type-tag.video { background: #fef3c7; color: #92400e; }
.type-tag.audio { background: #fce7f3; color: #9d174d; }
.type-tag.image { background: #ede9fe; color: #5b21b6; }

.material-info {
  min-width: 0;
}

.material-title {
  margin: 0;
  font-size: 13px;
  color: #1f2a37;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.material-meta {
  margin: 3px 0 0;
  font-size: 11px;
  color: #8ba098;
}

.parse-badge {
  flex-shrink: 0;
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 9px;
  font-weight: 600;
}

.parse-badge.done { color: #166534; background: #dcfce7; }
.parse-badge.parsing { color: #1d4ed8; background: #dbeafe; }
.parse-badge.uploaded { color: #92400e; background: #fef3c7; }
.parse-badge.failed { color: #991b1b; background: #fee2e2; }

.del-btn {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #94a3b8;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.del-btn:hover {
  background: #fef2f2;
  color: #b91c1c;
}

/* ---------- 切片预览 ---------- */
.chunk-preview {
  border: 1px solid #e7efeb;
  border-radius: 12px;
  background: #fafcfa;
  min-height: 200px;
  max-height: 420px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.chunk-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chunk-item {
  background: #fff;
  border: 1px solid #e7efeb;
  border-radius: 10px;
  padding: 10px 12px;
}

.chunk-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.chunk-seq {
  font-size: 11px;
  font-weight: 700;
  color: #5ca68f;
  background: #e8f5f0;
  border-radius: 6px;
  padding: 2px 7px;
}

.chunk-loc {
  font-size: 11px;
  color: #64748b;
}

.chunk-score {
  margin-left: auto;
  font-size: 11px;
  color: #64748b;
  background: #f1f5f9;
  border-radius: 999px;
  padding: 2px 8px;
}

.chunk-score.hot {
  color: #166534;
  background: #dcfce7;
}

.chunk-content {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: #334155;
}

/* ---------- 通用 ---------- */
.state-block {
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  padding: 48px 16px;
}

.ghost-link {
  border: 0;
  background: transparent;
  color: #5ca68f;
  font-size: 12px;
  cursor: pointer;
  font-weight: 600;
}

.ghost-link:hover {
  color: #2f605a;
  text-decoration: underline;
}

@media (max-width: 1100px) {
  .material-layout {
    grid-template-columns: 1fr;
  }
}
</style>
