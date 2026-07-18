<template>
  <div class="course-card">
    <div class="course-header">
      <div>
        <div class="header-label">课堂内容</div>
        <h3>{{ currentCourseName || '暂无课程' }} · 第{{ currentPage }}页</h3>
      </div>
      <div class="course-tag">
        <el-tag size="small" effect="dark">学习中</el-tag>
        <span class="page-count">{{ currentPage }}/{{ totalPage }}</span>
      </div>
    </div>

    <div class="course-content" ref="courseContentRef">
      <div class="content-switcher" v-if="showContentSwitcher">
        <el-radio-group v-model="contentView" size="small">
          <el-radio-button v-if="hasCourseImage" value="image">课件</el-radio-button>
          <el-radio-button v-if="isVoiceMode" value="voice">讲授</el-radio-button>
          <el-radio-button v-else-if="hasScriptContent" value="script">讲稿</el-radio-button>
        </el-radio-group>
      </div>

      <div class="content-main" :class="{ 'voice-mode': contentView === 'voice' }">
        <template v-if="contentView === 'image'">
          <div class="course-image-view">
            <img
              v-if="hasCourseImage"
              :src="resolvedCourseImg"
              alt="课件内容"
              class="course-img"
              @error="handleCourseImageError"
            />
            <div v-else class="no-courseware">当前页课件暂未返回，请稍后重试或切换页面。</div>
          </div>
        </template>

        <template v-else-if="contentView === 'voice'">
          <div class="voice-progress-shell">
            <div class="voice-progress-head">
              <strong>语音讲授进度</strong>
              <span>{{ pageTimelineDuration > 0 ? `${formatTime(currentTimelineSec)} / ${formatTime(pageTimelineDuration)}` : `页进度 ${progressPercent}%` }}</span>
            </div>
            <div class="voice-progress-track">
              <div class="voice-progress-fill" :style="{ width: `${lectureProgressPercent}%` }"></div>
            </div>
            <div class="voice-progress-meta">
              <span>{{ isPlay ? '正在语音讲授' : '讲授已暂停' }}</span>
              <span>{{ currentNodeTitle || '等待切换节点' }}</span>
              <span>{{ activeNodeTypeLabel || '核心讲解' }}</span>
            </div>
            <div class="voice-milestone-list">
              <article v-for="node in lectureMilestones" :key="node.id" class="voice-milestone" :class="node.state">
                <div class="milestone-row">
                  <strong>{{ node.title }}</strong>
                  <span>{{ node.time }}</span>
                </div>
                <p>{{ node.desc }}</p>
              </article>
            </div>
          </div>
        </template>

        <template v-else>
          <StudentScriptViewer
            v-if="scriptContent"
            :script-content="scriptContent"
            :is-loading="isScriptLoading"
            @error="handleScriptError"
            @warning="handleScriptWarning"
          />
          <div v-else class="script-empty-state">
            <strong>当前页暂无可展示讲稿</strong>
            <p>请先播放本页或切换到含讲稿节点，系统将自动同步进度与文本。</p>
          </div>
        </template>
      </div>

      <div ref="orbDockRef" class="voice-orb-dock" :class="{ dragging: orbDrag.active }" :style="voiceOrbDockStyle" role="group" aria-label="语音控制浮球">
        <div class="orb-mini-actions">
          <button class="orb-mini-btn orb-mini-play" type="button" :title="isPlay ? '暂停讲解' : '开始讲解'" @click="emit('toggle-play')">
            <span>{{ isPlay ? '⏸' : '▶' }}</span>
          </button>

          <button class="orb-mini-btn orb-mini-speed" type="button" :title="`切换倍速（当前 ${playbackRate}x）`" @click="cyclePlaybackRate">
            <span>⚡</span>
            <small>{{ playbackRate }}x</small>
          </button>

          <button class="orb-mini-btn orb-mini-ask" type="button" title="打开问答助手" @click="emit('open-qa')">
            <span>❓</span>
          </button>
        </div>

        <button
          class="voice-orb-main"
          :class="{ playing: isPlay }"
          type="button"
          :title="isPlay ? '语音讲解中（悬浮展开控制）' : '语音已暂停（悬浮展开控制）'"
          @pointerdown="handleOrbPointerDown"
          @click="handleOrbMainClick"
        >
          <span v-if="isPlay" class="orb-playing-wave" aria-hidden="true">
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
            <span class="wave-bar"></span>
          </span>
          <span v-else class="orb-main-icon">◉</span>
        </button>
      </div>
    </div>

    <div class="timeline-seek" v-if="pageTimelineDuration > 0">
      <span>{{ formatTime(currentTimelineSec) }}</span>
      <div class="seek-box">
        <div class="seek-preview-bubble" v-if="seekPreviewText" :style="seekPreviewStyle">
          {{ seekPreviewText }}
        </div>
        <input
          class="seek-input"
          type="range"
          min="0"
          :max="Math.max(0, pageTimelineDuration)"
          :value="Math.max(0, Math.min(pageTimelineDuration, currentTimelineSec))"
          step="1"
          @input="handleSeekInput"
          @change="handleSeekCommit"
        />
      </div>
      <span>{{ formatTime(pageTimelineDuration) }}</span>
    </div>

    <div class="bottom-control-row">
      <el-button class="page-control-btn" @click="$emit('prev-page')" size="small" plain>上一页</el-button>
      <el-button class="page-control-btn page-control-main" @click="$emit('toggle-play')" size="small" type="primary">
        {{ isPlay ? '暂停播放' : '开始播放' }}
      </el-button>
      <el-button class="page-control-btn" @click="$emit('next-page')" size="small" plain>下一页</el-button>
    </div>
  </div>
</template>

<script setup>
/* eslint-disable no-undef */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import StudentScriptViewer from './StudentScriptViewer.vue'

const props = defineProps({
  currentCourseName: {
    type: String,
    default: ''
  },
  currentPage: {
    type: Number,
    default: 1
  },
  totalPage: {
    type: Number,
    default: 1
  },
  pageTimelineDuration: {
    type: Number,
    default: 0
  },
  currentTimelineSec: {
    type: Number,
    default: 0
  },
  activeNodeElapsedSec: {
    type: Number,
    default: 0
  },
  activeNodeDuration: {
    type: Number,
    default: 0
  },
  currentNodeTitle: {
    type: String,
    default: ''
  },
  activeNodeTypeLabel: {
    type: String,
    default: ''
  },
  playbackMode: {
    type: String,
    default: 'duration_timeline'
  },
  playbackAudioMeta: {
    type: Object,
    default: null
  },
  progressPercent: {
    type: Number,
    default: 0
  },
  courseImg: {
    type: String,
    default: ''
  },
  fallbackCourseImg: {
    type: String,
    default: ''
  },
  playbackNodes: {
    type: Array,
    default: () => []
  },
  currentNodeId: {
    type: String,
    default: ''
  },
  ttsEnabled: {
    type: Boolean,
    default: true
  },
  pageSummary: {
    type: String,
    default: ''
  },
  tracePoint: {
    type: Boolean,
    default: false
  },
  traceTop: {
    type: Number,
    default: 0
  },
  traceLeft: {
    type: Number,
    default: 0
  },
  isPlay: {
    type: Boolean,
    default: false
  },
  scriptContent: {
    type: String,
    default: ''
  },
  isScriptLoading: {
    type: Boolean,
    default: false
  },
  showStatusStrip: {
    type: Boolean,
    default: true
  },
  playbackRate: {
    type: Number,
    default: 1
  },
  displayMode: {
    type: String,
    default: 'script'
  }
})

const emit = defineEmits([
  'prev-page',
  'toggle-play',
  'next-page',
  'select-node',
  'toggle-tts',
  'speak-current-node',
  'script-error',
  'script-warning',
  'seek-timeline',
  'seek-step',
  'seek-to-start',
  'open-shortcuts',
  'open-qa',
  'update:playback-rate'
])

/**
 * 处理脚本渲染错误
 */
function handleScriptError(errors) {
  console.error('[StudentCoursePanel] 脚本错误:', errors)
  // 可选：发出错误事件给父组件
}

/**
 * 处理脚本渲染警告
 */
function handleScriptWarning(warnings) {
  console.warn('[StudentCoursePanel] 脚本警告:', warnings)
  // 可选：发出警告事件给父组件
}

const timelinePercent = computed(() => {
  if (!props.pageTimelineDuration) return 0
  return Math.min(100, Math.max(0, Math.round((props.currentTimelineSec / props.pageTimelineDuration) * 100)))
})

const lectureProgressPercent = computed(() => {
  if (props.pageTimelineDuration > 0) return timelinePercent.value
  return Math.min(100, Math.max(0, Number(props.progressPercent || 0)))
})

const isVoiceMode = computed(() => props.displayMode === 'voice')

const imageLoadFailed = ref(false)

const resolvedCourseImg = computed(() => {
  const primary = String(props.courseImg || '').trim()
  if (!imageLoadFailed.value) return primary
  const fallback = String(props.fallbackCourseImg || '').trim()
  return fallback || primary
})

const hasCourseImage = computed(() => String(resolvedCourseImg.value || '').trim().length > 0)

const hasScriptContent = computed(() => String(props.scriptContent || '').trim().length > 0)

const contentView = ref('image')
const courseContentRef = ref(null)
const orbDockRef = ref(null)

const orbPosition = reactive({
  x: null,
  y: null
})

const orbDrag = reactive({
  active: false,
  startPointerX: 0,
  startPointerY: 0,
  originX: 0,
  originY: 0,
  moved: false
})

const suppressNextOrbClick = ref(false)

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

const getOrbBounds = () => {
  const containerEl = courseContentRef.value
  const dockEl = orbDockRef.value
  if (!containerEl || !dockEl) return null

  const containerRect = containerEl.getBoundingClientRect()
  const dockRect = dockEl.getBoundingClientRect()
  const maxX = Math.max(0, containerRect.width - dockRect.width)
  const maxY = Math.max(0, containerRect.height - dockRect.height)

  return {
    containerRect,
    dockRect,
    maxX,
    maxY
  }
}

const ensureOrbPositionInitialized = () => {
  if (orbPosition.x !== null && orbPosition.y !== null) return
  const bounds = getOrbBounds()
  if (!bounds) return

  orbPosition.x = clamp(bounds.dockRect.left - bounds.containerRect.left, 0, bounds.maxX)
  orbPosition.y = clamp(bounds.dockRect.top - bounds.containerRect.top, 0, bounds.maxY)
}

const clampOrbPosition = () => {
  if (orbPosition.x === null || orbPosition.y === null) return
  const bounds = getOrbBounds()
  if (!bounds) return

  orbPosition.x = clamp(orbPosition.x, 0, bounds.maxX)
  orbPosition.y = clamp(orbPosition.y, 0, bounds.maxY)
}

const voiceOrbDockStyle = computed(() => {
  if (orbPosition.x === null || orbPosition.y === null) return {}
  return {
    left: `${Math.round(orbPosition.x)}px`,
    top: `${Math.round(orbPosition.y)}px`,
    right: 'auto',
    bottom: 'auto'
  }
})

const showContentSwitcher = computed(() => {
  let count = 0
  if (hasCourseImage.value) count += 1
  if (isVoiceMode.value || hasScriptContent.value) count += 1
  return count > 1
})

const syncContentView = () => {
  const availableViews = []
  if (hasCourseImage.value) {
    availableViews.push('image')
  }
  if (isVoiceMode.value) {
    availableViews.push('voice')
  } else if (hasScriptContent.value) {
    availableViews.push('script')
  }

  if (!availableViews.length) {
    availableViews.push(isVoiceMode.value ? 'voice' : 'script')
  }

  if (!availableViews.includes(contentView.value)) {
    contentView.value = availableViews[0]
  }
}

watch(
  [() => props.courseImg, () => props.displayMode, () => props.scriptContent],
  () => {
    imageLoadFailed.value = false
    syncContentView()
  },
  { immediate: true }
)

const handleCourseImageError = () => {
  const fallback = String(props.fallbackCourseImg || '').trim()
  if (fallback) {
    imageLoadFailed.value = true
  }
}

const removeOrbDragListeners = () => {
  window.removeEventListener('pointermove', handleOrbPointerMove)
  window.removeEventListener('pointerup', handleOrbPointerUp)
  window.removeEventListener('pointercancel', handleOrbPointerUp)
}

const handleOrbPointerDown = event => {
  if (event.button !== 0) return
  ensureOrbPositionInitialized()
  if (orbPosition.x === null || orbPosition.y === null) return

  orbDrag.active = true
  orbDrag.startPointerX = Number(event.clientX || 0)
  orbDrag.startPointerY = Number(event.clientY || 0)
  orbDrag.originX = Number(orbPosition.x || 0)
  orbDrag.originY = Number(orbPosition.y || 0)
  orbDrag.moved = false

  window.addEventListener('pointermove', handleOrbPointerMove)
  window.addEventListener('pointerup', handleOrbPointerUp)
  window.addEventListener('pointercancel', handleOrbPointerUp)

  event.preventDefault()
}

const handleOrbPointerMove = event => {
  if (!orbDrag.active) return
  const bounds = getOrbBounds()
  if (!bounds) return

  const deltaX = Number(event.clientX || 0) - orbDrag.startPointerX
  const deltaY = Number(event.clientY || 0) - orbDrag.startPointerY
  if (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3) {
    orbDrag.moved = true
  }

  orbPosition.x = clamp(orbDrag.originX + deltaX, 0, bounds.maxX)
  orbPosition.y = clamp(orbDrag.originY + deltaY, 0, bounds.maxY)
}

const handleOrbPointerUp = () => {
  if (!orbDrag.active) return
  const wasMoved = orbDrag.moved

  orbDrag.active = false
  orbDrag.moved = false
  removeOrbDragListeners()
  clampOrbPosition()

  if (wasMoved) {
    suppressNextOrbClick.value = true
    window.setTimeout(() => {
      suppressNextOrbClick.value = false
    }, 0)
  }
}

const handleOrbMainClick = () => {
  if (suppressNextOrbClick.value) {
    suppressNextOrbClick.value = false
    return
  }
  emit('toggle-play')
}

const lectureMilestones = computed(() => {
  const list = (props.playbackNodes || []).slice(0, 6)
  if (!list.length) {
    return [
      { id: 'v1', title: '讲授引导', time: '00:00', desc: '系统等待讲稿节点同步，准备开始语音讲授。', state: 'pending' },
      { id: 'v2', title: '关键概念', time: '00:30', desc: '将按“定义 -> 示例 -> 易错点”顺序讲解。', state: 'pending' },
      { id: 'v3', title: '课堂收束', time: '01:00', desc: '总结节点并同步到左下学习状态栏。', state: 'pending' }
    ]
  }
  return list.map((node, index) => {
    const start = Number(node?.start_sec || 0)
    const end = Number(node?.end_sec || start + 1)
    const elapsed = Number(props.currentTimelineSec || 0)
    let state = 'pending'
    if (elapsed >= end) state = 'done'
    else if (elapsed >= start && elapsed < end) state = 'active'
    return {
      id: node?.node_id || `milestone_${index}`,
      title: node?.title || `讲解节点 ${index + 1}`,
      time: formatTime(start),
      desc: String(node?.text || '系统将自动同步该节点讲稿与语音进度。').slice(0, 48),
      state
    }
  })
})

const seekDraftSec = ref(-1)
let seekPreviewTimer = null

const cyclePlaybackRate = () => {
  const sequence = [0.75, 1, 1.25, 1.5]
  const current = Number(props.playbackRate || 1)
  const currentIndex = sequence.indexOf(current)
  const next = sequence[(currentIndex + 1) % sequence.length]
  emit('update:playback-rate', next)
}

const seekPreviewText = computed(() => {
  if (seekDraftSec.value < 0) return ''
  const sec = Math.max(0, Math.floor(seekDraftSec.value))
  const matchedNode = (props.playbackNodes || []).find((node) => {
    const start = Number(node?.start_sec || 0)
    const end = Number(node?.end_sec || start + 1)
    return sec >= start && sec < end
  })
  const title = String(matchedNode?.title || '').trim()
  return title ? `预览 ${formatTime(sec)} · ${title}` : `预览 ${formatTime(sec)}`
})

const seekPreviewStyle = computed(() => {
  const total = Math.max(1, Number(props.pageTimelineDuration || 1))
  const sec = Math.max(0, Math.min(total, Number(seekDraftSec.value || 0)))
  const percent = (sec / total) * 100
  return {
    left: `calc(${percent}% - 6px)`
  }
})

function handleSeekInput(event) {
  const value = Number(event?.target?.value || 0)
  if (seekPreviewTimer) {
    window.clearTimeout(seekPreviewTimer)
    seekPreviewTimer = null
  }
  seekDraftSec.value = value
  emit('seek-timeline', value)
}

function handleSeekCommit(event) {
  const value = Number(event?.target?.value || 0)
  emit('seek-timeline', value)
  if (seekPreviewTimer) {
    window.clearTimeout(seekPreviewTimer)
  }
  seekPreviewTimer = window.setTimeout(() => {
    seekDraftSec.value = -1
    seekPreviewTimer = null
  }, 900)
}

const handleWindowResize = () => {
  if (orbPosition.x === null || orbPosition.y === null) return
  clampOrbPosition()
}

onMounted(() => {
  nextTick(() => {
    ensureOrbPositionInitialized()
    clampOrbPosition()
  })
  window.addEventListener('resize', handleWindowResize)
})

onBeforeUnmount(() => {
  orbDrag.active = false
  removeOrbDragListeners()
  window.removeEventListener('resize', handleWindowResize)
  if (seekPreviewTimer) {
    window.clearTimeout(seekPreviewTimer)
    seekPreviewTimer = null
  }
})

const formatTime = (seconds) => {
  const normalized = Math.max(0, Math.floor(seconds || 0))
  const mins = String(Math.floor(normalized / 60)).padStart(2, '0')
  const secs = String(normalized % 60).padStart(2, '0')
  return `${mins}:${secs}`
}
</script>

<style scoped>
.course-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.96) 100%);
  border-radius: 24px;
  padding: 14px;
  height: 100%;
  min-height: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.course-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.header-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #0f766e;
  margin-bottom: 4px;
}
.course-header h3 {
  font-size: 20px;
  color: #0f172a;
}
.course-tag {
  display: flex;
  gap: 8px;
  align-items: center;
}
.page-count {
  font-size: 13px;
  color: #475569;
}
.status-strip {
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95) 0%, rgba(244, 250, 247, 0.96) 100%);
  border: 1px solid rgba(148, 163, 184, 0.16);
}
.status-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 7px;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 12px;
  color: #3b5d54;
  background: #edf4f0;
  border: 1px solid #d5e4dc;
}

.status-track,
.progress-track {
  height: 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.7);
  overflow: hidden;
}
.status-fill,
.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #0f766e 0%, #0284c7 100%);
}
.status-note {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 7px;
  font-size: 12px;
  color: #628075;
}
.course-content {
  flex: 1;
  position: relative;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border-radius: 16px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.content-switcher {
  flex: 0 0 auto;
  padding: 10px 12px 0;
}

.content-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.content-main.voice-mode {
  padding: 12px;
  background: linear-gradient(180deg, #f9fdfb 0%, #f2f8f5 100%);
}

.course-content :deep(.student-script-viewer) {
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.course-image-view {
  position: relative;
  flex: 1;
  min-height: 0;
  margin: 10px 12px 12px;
  border-radius: 14px;
  border: 1px solid #d8e6de;
  background: linear-gradient(180deg, #ffffff 0%, #f6fbf8 100%);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.course-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #ffffff;
}

.no-courseware {
  font-size: 13px;
  color: #5f7b71;
  text-align: center;
  padding: 18px;
}

.trace-highlight {
  position: absolute;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid #ffffff;
  background: rgba(239, 68, 68, 0.75);
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.24);
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.voice-progress-shell {
  height: 100%;
  border: 1px solid rgba(178, 209, 196, 0.72);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.96);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  box-sizing: border-box;
}

.voice-progress-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #2f605a;
}

.voice-progress-head strong {
  font-size: 14px;
  color: #1f4a43;
}

.voice-progress-track {
  height: 9px;
  border-radius: 999px;
  background: #e2efe9;
  overflow: hidden;
}

.voice-progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #2f605a 0%, #3f8b79 100%);
  transition: width 0.28s ease;
}

.voice-progress-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: #4b6c62;
}

.voice-milestone-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.voice-milestone {
  border: 1px solid #d4e5dd;
  border-radius: 10px;
  padding: 8px 10px;
  background: #ffffff;
}

.voice-milestone.active {
  border-color: #62a18f;
  background: #f0f8f4;
}

.voice-milestone.done {
  border-color: #b6d9ca;
  background: #f7fbf9;
}

.milestone-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}

.milestone-row strong {
  font-size: 13px;
  color: #294f47;
}

.milestone-row span {
  font-size: 11px;
  color: #6f897f;
}

.voice-milestone p {
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.45;
  color: #5b756b;
}

.script-empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  text-align: center;
}

.script-empty-state strong {
  font-size: 15px;
  color: #23463f;
}

.script-empty-state p {
  margin: 0;
  max-width: 440px;
  font-size: 13px;
  color: #5f7b71;
  line-height: 1.6;
}

.voice-orb-dock {
  position: absolute;
  right: 18px;
  bottom: 18px;
  z-index: 6;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  will-change: left, top;
}

.voice-orb-dock.dragging .orb-mini-actions {
  opacity: 0;
  pointer-events: none;
}

.voice-orb-main {
  position: relative;
  overflow: hidden;
  width: 58px;
  height: 58px;
  border-radius: 50%;
  border: none;
  color: #ffffff;
  background: radial-gradient(circle at 30% 25%, #38bdf8 0%, #0284c7 45%, #075985 100%);
  box-shadow: 0 16px 34px rgba(3, 105, 161, 0.34);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  line-height: 1;
  cursor: grab;
  touch-action: none;
  transition: transform 0.24s ease, box-shadow 0.24s ease;
}

.voice-orb-main:active {
  cursor: grabbing;
}

.voice-orb-main::before,
.voice-orb-main::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 1px solid rgba(103, 232, 249, 0.38);
  opacity: 0;
  pointer-events: none;
}

.voice-orb-main.playing {
  background: radial-gradient(circle at 30% 25%, #4ade80 0%, #10b981 46%, #065f46 100%);
  box-shadow: 0 20px 40px rgba(6, 95, 70, 0.38);
}

.voice-orb-main.playing::before {
  opacity: 1;
  animation: orbRingPulse 1.35s ease-out infinite;
}

.voice-orb-main.playing::after {
  opacity: 1;
  animation: orbRingPulse 1.35s ease-out 0.48s infinite;
}

.orb-main-icon,
.orb-playing-wave {
  position: relative;
  z-index: 1;
}

.orb-main-icon {
  transform: translateY(-1px);
}

.orb-playing-wave {
  display: inline-flex;
  align-items: flex-end;
  gap: 3px;
  height: 22px;
}

.wave-bar {
  width: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  transform-origin: center bottom;
  animation: orbEq 900ms ease-in-out infinite;
}

.wave-bar:nth-child(1) {
  height: 8px;
  animation-delay: 0ms;
}

.wave-bar:nth-child(2) {
  height: 16px;
  animation-delay: 120ms;
}

.wave-bar:nth-child(3) {
  height: 11px;
  animation-delay: 240ms;
}

.wave-bar:nth-child(4) {
  height: 19px;
  animation-delay: 360ms;
}

.voice-orb-main:hover,
.voice-orb-main:focus-visible {
  transform: translateY(-1px) scale(1.03);
  box-shadow: 0 22px 38px rgba(3, 105, 161, 0.42);
}

.orb-mini-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  opacity: 0;
  transform: translateY(8px) scale(0.94);
  pointer-events: none;
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.voice-orb-dock:hover .orb-mini-actions,
.voice-orb-dock:focus-within .orb-mini-actions {
  opacity: 1;
  transform: translateY(0) scale(1);
  pointer-events: auto;
}

.orb-mini-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 1px solid rgba(186, 230, 253, 0.8);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(239, 246, 255, 0.98) 100%);
  color: #0c4a6e;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 10px 20px rgba(14, 116, 144, 0.18);
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.orb-mini-speed {
  gap: 1px;
  flex-direction: column;
  font-size: 12px;
}

.orb-mini-speed small {
  font-size: 8px;
  line-height: 1;
  font-weight: 700;
}

.orb-mini-btn:hover,
.orb-mini-btn:focus-visible {
  transform: translateY(-1px);
  box-shadow: 0 14px 24px rgba(14, 116, 144, 0.24);
  background: linear-gradient(180deg, #ffffff 0%, #dbeafe 100%);
}

@keyframes orbEq {
  0%,
  100% {
    transform: scaleY(0.45);
    opacity: 0.78;
  }
  50% {
    transform: scaleY(1);
    opacity: 1;
  }
}

@keyframes orbRingPulse {
  0% {
    transform: scale(0.92);
    opacity: 0.45;
  }
  100% {
    transform: scale(1.22);
    opacity: 0;
  }
}

.bottom-control-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 10px;
  padding: 2px 2px 0;
}

.page-control-btn {
  min-height: 38px;
  border-radius: 12px;
  font-weight: 600;
}

.page-control-main {
  min-width: 130px;
  border-radius: 12px;
  border: none;
  font-weight: 700;
  color: #ffffff;
  background: linear-gradient(135deg, #2563eb 0%, #0284c7 100%);
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.25);
}
.timeline-seek {
  margin-top: 10px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #64748b;
}
.seek-box {
  position: relative;
  padding-top: 28px;
}
.seek-input {
  width: 100%;
}
.seek-preview-bubble {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  max-width: min(240px, 60vw);
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1.2;
  color: #0f766e;
  border: 1px solid rgba(15, 118, 110, 0.28);
  background: rgba(236, 253, 245, 0.98);
  box-shadow: 0 6px 12px rgba(15, 118, 110, 0.08);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
}
.page-summary,
.node-panel {
  margin-top: 14px;
  background: rgba(248, 250, 252, 0.86);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 16px;
  padding: 12px;
}
.page-summary h4,
.node-panel-header h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #0f172a;
}
.page-summary p {
  margin: 0;
  font-size: 13px;
  color: #475569;
  line-height: 1.7;
}
.node-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.node-panel-header span {
  font-size: 12px;
  color: #64748b;
}
.node-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 220px;
  overflow: auto;
}
.node-chip {
  border: 1px solid #dbe3ef;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border-radius: 14px;
  padding: 10px 12px;
  text-align: left;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}
.node-chip:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 16px rgba(15, 23, 42, 0.06);
}
.node-chip-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 4px;
}
.node-chip strong {
  font-size: 12px;
  color: #2563eb;
}
.node-type {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #475569;
  background: #e2e8f0;
}
.node-type.opening {
  background: rgba(16, 185, 129, 0.14);
  color: #047857;
}
.node-type.explain {
  background: rgba(14, 165, 233, 0.14);
  color: #0369a1;
}
.node-type.transition {
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
}
.node-chip span {
  display: block;
  font-size: 13px;
  color: #334155;
  line-height: 1.6;
}
.node-chip.active {
  border-color: #2563eb;
  box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.15), 0 10px 20px rgba(37, 99, 235, 0.08);
  background: linear-gradient(180deg, #eff6ff 0%, #f8fbff 100%);
}

@media (min-width: 1500px) {
  .course-content {
    min-height: 460px;
  }

  .course-content :deep(.student-script-viewer) {
    padding: 20px;
  }
}

@media (max-width: 720px) {
  .voice-orb-dock {
    right: 12px;
    bottom: 12px;
  }

  .voice-orb-main {
    width: 52px;
    height: 52px;
    font-size: 22px;
  }

  .orb-mini-btn {
    width: 32px;
    height: 32px;
  }

  .bottom-control-row {
    grid-template-columns: 1fr;
  }

  .page-control-main,
  .page-control-btn {
    width: 100%;
  }

  .course-header,
  .progress-meta,
  .playback-head,
  .playback-node-meta,
  .node-chip-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>