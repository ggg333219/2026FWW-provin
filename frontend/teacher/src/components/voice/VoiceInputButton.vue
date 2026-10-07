<template>
  <!-- 特性检测不通过（极老的浏览器缺 MediaRecorder/getUserMedia）时整组件隐藏 -->
  <div v-if="isSupported" class="voice-input">
    <!-- 语音异常静默处理：不弹错误提示（用户可改用系统级语音输入，如 Win+H），
         仅控制台留痕便于排查 -->
    <!-- 录音中 / 识别中状态气泡 -->
    <div v-if="isListening || isTranscribing" class="voice-live" aria-live="polite">
      <i></i>
      <span v-if="isListening">正在聆听，请说话…（{{ recordedSeconds }}s，再次点击结束）</span>
      <span v-else>正在识别语音，请稍候…</span>
    </div>

    <button
      type="button"
      class="voice-button"
      :class="{ recording: isListening, transcribing: isTranscribing }"
      :disabled="disabled || isTranscribing"
      :title="buttonTitle"
      :aria-pressed="isListening"
      :aria-label="buttonTitle"
      @click="toggleRecording"
    >
      <svg v-if="!isTranscribing" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="9" y="3" width="6" height="11" rx="3"/>
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8.5 21h7"/>
      </svg>
      <svg v-else class="voice-spinner" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="8" opacity="0.25"/>
        <path d="M20 12a8 8 0 0 0-8-8"/>
      </svg>
    </button>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { AI_API_BASE } from '../../config/api'

/**
 * VoiceInputButton · 服务端 ASR 语音输入按钮。
 *
 * 链路：MediaRecorder 录音（浏览器通用能力，Chrome/Edge/Firefox/Safari 均可）
 *      → multipart 上传 AI 引擎 /api/v1/asr/transcribe（经同源 /ai/ 反代）
 *      → 服务端转写（dashscope 云端 / 服务器本地 whisper）→ 文本回填输入框。
 *
 * 刻意不用 Web Speech API：它绑定 Chrome/Edge 且依赖 Google 识别服务，国内不可用。
 * - 点击开始录音 / 再次点击结束并上传；最长 MAX_RECORD_SECONDS 自动截断。
 * - 转写文本通过 transcript 事件交给父组件追加；错误通过 error 事件上报。
 */
const props = defineProps({
  /** 外部禁用（例如正在分析或意图已确认时） */
  disabled: { type: Boolean, default: false },
  /** 识别语言，默认中文普通话 */
  lang: { type: String, default: 'zh-CN' }
})

const emit = defineEmits(['transcript', 'error', 'state-change'])

const isListening = ref(false)
const isTranscribing = ref(false)
const recordedSeconds = ref(0)
const errorMessage = ref('')

// 语音异常不再弹 UI 提示（用户可改用系统语音输入）；仅控制台留痕
watch(errorMessage, (msg) => {
  if (msg) console.warn('[voice-input]', msg)
})

const isSupported = typeof navigator !== 'undefined'
  && typeof window.MediaRecorder !== 'undefined'
  && Boolean(window.MediaRecorder.isTypeSupported)

// 浏览器安全策略：getUserMedia 仅在 HTTPS 或 localhost 的安全上下文暴露。
// HTTP 公网访问时 mediaDevices 为 undefined —— 此时按钮仍渲染，点击给出明确引导而非静默消失。
const needsSecureContext = typeof navigator !== 'undefined'
  && typeof window.isSecureContext === 'boolean'
  && !window.isSecureContext

const buttonTitle = computed(() => {
  if (needsSecureContext.value) return '麦克风需要 HTTPS 访问：请改用 https:// 开头的站点地址（或 localhost）'
  if (isTranscribing.value) return '正在识别语音…'
  return isListening.value ? '停止录音并识别' : '语音输入（点击开始）'
})

const MAX_RECORD_SECONDS = 60

let mediaRecorder = null
let mediaStream = null
let chunks = []
let recordTimer = null
let secondsTimer = null

const clearTimers = () => {
  if (recordTimer) {
    clearTimeout(recordTimer)
    recordTimer = null
  }
  if (secondsTimer) {
    clearInterval(secondsTimer)
    secondsTimer = null
  }
}

const releaseStream = () => {
  if (mediaStream) {
    for (const track of mediaStream.getTracks()) track.stop()
    mediaStream = null
  }
}

const pickMimeType = () => {
  if (typeof MediaRecorder === 'undefined') return ''
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  for (const type of candidates) {
    try {
      if (MediaRecorder.isTypeSupported(type)) return type
    } catch {
      // isTypeSupported 异常时继续尝试下一个
    }
  }
  return ''
}

const transcribeBlob = async (blob) => {
  isTranscribing.value = true
  errorMessage.value = ''
  try {
    const form = new FormData()
    const ext = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm'
    form.append('file', blob, `voice-input.${ext}`)
    form.append('language', props.lang)
    const response = await fetch(`${AI_API_BASE}/api/v1/asr/transcribe`, {
      method: 'POST',
      body: form,
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      const detail = payload?.detail
      const code = typeof detail === 'object' ? detail?.error_code : ''
      const message = typeof detail === 'object' ? detail?.message : (typeof detail === 'string' ? detail : '')
      if (code === 'ASR_NOT_CONFIGURED') {
        errorMessage.value = '语音识别服务未在服务器配置，请联系管理员设置 ASR 密钥或本地模型。'
      } else if (code === 'ASR_AUDIO_TOO_LARGE' || code === 'ASR_EMPTY_AUDIO') {
        errorMessage.value = message || '录音数据异常，请重试。'
      } else if (message) {
        errorMessage.value = `语音识别失败：${message}`
      } else {
        errorMessage.value = `语音识别失败（${response.status}），请稍候重试。`
      }
      emit('error', errorMessage.value)
      return
    }
    const text = String(payload?.data?.text || '').trim()
    if (!text) {
      errorMessage.value = '没有听清内容，请靠近麦克风重说一次。'
      emit('error', errorMessage.value)
      return
    }
    emit('transcript', text)
  } catch (err) {
    errorMessage.value = '语音识别服务连接失败，请检查网络后重试。'
    emit('error', errorMessage.value)
  } finally {
    isTranscribing.value = false
  }
}

const stopRecording = () => {
  clearTimers()
  isListening.value = false
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    // onstop 回调里统一做转写上传
    mediaRecorder.stop()
  } else {
    releaseStream()
  }
}

const startRecording = async () => {
  errorMessage.value = ''
  if (needsSecureContext.value || !navigator.mediaDevices?.getUserMedia) {
    errorMessage.value = '浏览器安全策略要求 HTTPS 才能使用麦克风：请改用 https:// 开头的站点地址（或 localhost）访问。'
    emit('error', errorMessage.value)
    return
  }
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (err) {
    if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
      errorMessage.value = '无法使用麦克风：请在浏览器地址栏允许麦克风权限后重试。'
    } else if (err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError') {
      errorMessage.value = '未检测到可用麦克风，请检查设备连接。'
    } else {
      errorMessage.value = `麦克风启动失败（${err?.name || 'unknown'}），请重试。`
    }
    emit('error', errorMessage.value)
    return
  }

  mediaStream = stream
  chunks = []
  const mimeType = pickMimeType()
  try {
    mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream)
  } catch {
    mediaRecorder = new MediaRecorder(stream)
  }

  mediaRecorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) chunks.push(event.data)
  }
  mediaRecorder.onstop = () => {
    releaseStream()
    const blob = new Blob(chunks, { type: mimeType || mediaRecorder.mimeType || 'audio/webm' })
    chunks = []
    if (blob.size > 0) {
      transcribeBlob(blob)
    } else {
      errorMessage.value = '没有录到声音，请重试。'
      emit('error', errorMessage.value)
    }
  }
  mediaRecorder.onerror = () => {
    clearTimers()
    releaseStream()
    isListening.value = false
    errorMessage.value = '录音出错，请重试。'
    emit('error', errorMessage.value)
  }

  mediaRecorder.start()
  isListening.value = true
  recordedSeconds.value = 0
  secondsTimer = setInterval(() => {
    recordedSeconds.value += 1
  }, 1000)
  recordTimer = setTimeout(() => {
    if (isListening.value) stopRecording()
  }, MAX_RECORD_SECONDS * 1000)
}

const toggleRecording = () => {
  if (isTranscribing.value) return
  if (isListening.value) {
    stopRecording()
  } else {
    startRecording()
  }
  emit('state-change', isListening.value)
}

onBeforeUnmount(() => {
  clearTimers()
  isListening.value = false
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    try {
      mediaRecorder.onstop = null
      mediaRecorder.stop()
    } catch {
      // 组件卸载时忽略释放异常
    }
  }
  releaseStream()
})

// isListening 对外可见（父组件如需联动可监听 state-change）
defineExpose({
  stop: stopRecording,
  isSupported
})
</script>

<style scoped>
.voice-input {
  position: relative;
  display: inline-flex;
  align-items: center;
}
.voice-button {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid #e4ebe7;
  border-radius: 10px;
  color: #7f8d86;
  background: #fff;
  cursor: pointer;
  transition: all 0.18s ease;
}
.voice-button:hover:not(:disabled) {
  color: #315e54;
  border-color: #bfd3ca;
  background: #f5faf7;
}
.voice-button svg {
  width: 16px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.voice-button:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}
/* 录音中：红色主体 + 呼吸光圈 */
.voice-button.recording {
  color: #fff;
  border-color: #d26a5f;
  background: linear-gradient(145deg, #d26a5f, #b84c42);
  animation: voice-breathe 1.6s ease-in-out infinite;
}
@keyframes voice-breathe {
  0%, 100% { box-shadow: 0 0 0 0 rgba(210, 106, 95, 0.35); }
  50% { box-shadow: 0 0 0 6px rgba(210, 106, 95, 0.12); }
}
/* 识别中：主题色 + 旋转指示 */
.voice-button.transcribing {
  color: #315e54;
  border-color: #bfd3ca;
  background: #f5faf7;
}
.voice-spinner {
  animation: voice-spin 0.9s linear infinite;
}
@keyframes voice-spin {
  to { transform: rotate(360deg); }
}

/* 状态气泡（录音中 / 识别中共用） */
.voice-live {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 7px;
  max-width: 320px;
  padding: 8px 11px;
  border: 1px solid #f0d4d0;
  border-radius: 12px;
  color: #8a4a43;
  background: #fffdfa;
  box-shadow: 0 10px 26px rgba(120, 60, 50, 0.14);
  font-size: 11px;
  line-height: 1.5;
  white-space: normal;
  text-align: left;
}
.voice-live i {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #d26a5f;
  animation: voice-dot 1.1s ease-in-out infinite;
}
@keyframes voice-dot {
  0%, 100% { opacity: 0.35; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1.1); }
}

/* 错误提示条 */
.voice-error {
  position: absolute;
  right: 0;
  bottom: calc(100% + 8px);
  z-index: 21;
  display: flex;
  align-items: center;
  gap: 7px;
  width: max-content;
  max-width: 340px;
  padding: 8px 10px;
  border: 1px solid #f1d4d1;
  border-radius: 11px;
  color: #a0443f;
  background: #fff8f7;
  font-size: 10px;
  line-height: 1.5;
  text-align: left;
}
.voice-error svg {
  flex: 0 0 auto;
  width: 14px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
}
.voice-error span { flex: 1; }
.voice-error-close {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 6px;
  color: #b07a74;
  background: transparent;
  cursor: pointer;
}
.voice-error-close:hover { background: #fbe9e7; }
.voice-error-close svg { width: 10px; stroke-width: 2; }
</style>
