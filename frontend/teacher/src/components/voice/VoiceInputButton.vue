<template>
  <!-- 特性检测不通过（如 Firefox）时整组件隐藏，不留置灰占位（H2 要求） -->
  <div v-if="isSupported" class="voice-input" :class="{ listening: isListening }">
    <!-- 语音识别错误提示条（自动消失，也可手动关闭） -->
    <div v-if="errorMessage" class="voice-error" role="alert">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.1"/></svg>
      <span>{{ errorMessage }}</span>
      <button type="button" class="voice-error-close" aria-label="关闭提示" @click="errorMessage = ''">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
      </button>
    </div>

    <!-- 实时转写预览气泡（中间结果，最终结果会写入输入框） -->
    <div v-if="isListening" class="voice-live" aria-live="polite">
      <i></i>
      <span>{{ interimText || '正在聆听，请说话…' }}</span>
    </div>

    <button
      type="button"
      class="voice-button"
      :class="{ recording: isListening, unsupported: !isSupported }"
      :disabled="disabled || !isSupported"
      :title="buttonTitle"
      :aria-pressed="isListening"
      :aria-label="buttonTitle"
      @click="toggleListening"
    >
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="9" y="3" width="6" height="11" rx="3"/>
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8.5 21h7"/>
      </svg>
    </button>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

/**
 * VoiceInputButton · 基于 Web Speech API 的语音输入按钮。
 *
 * - 点击开始 / 再次点击结束（桌面端比按住说话更稳，不受鼠标移出丢失事件影响）。
 * - 中间结果仅在气泡内预览；每个最终片段通过 transcript 事件交给父组件追加。
 * - 浏览器不支持时按钮置灰并通过 title 提示，不影响页面其他功能。
 * - 权限被拒 / 无麦克风 / 网络错误时显示可关闭的提示条，并通过 error 事件上报。
 */
const props = defineProps({
  /** 外部禁用（例如正在分析或意图已确认时） */
  disabled: { type: Boolean, default: false },
  /** 识别语言，默认中文普通话 */
  lang: { type: String, default: 'zh-CN' }
})

const emit = defineEmits(['transcript', 'error', 'state-change'])

const isListening = ref(false)
const interimText = ref('')
const errorMessage = ref('')

const RecognitionCtor = typeof window !== 'undefined'
  ? window.SpeechRecognition || window.webkitSpeechRecognition
  : null
const isSupported = Boolean(RecognitionCtor)

const buttonTitle = computed(() => {
  if (!isSupported.value) return '当前浏览器不支持语音识别，请使用 Chrome / Edge'
  return isListening.value ? '停止语音输入' : '语音输入（点击开始）'
})

let recognition = null
// 用户意图上“仍在录音”的标记：Chrome 会在静音后自动 onend，需要据此重启会话。
let shouldListen = false
let restartTimer = null

const clearRestartTimer = () => {
  if (restartTimer) {
    clearTimeout(restartTimer)
    restartTimer = null
  }
}

const buildRecognition = () => {
  const instance = new RecognitionCtor()
  instance.lang = props.lang
  instance.continuous = true
  instance.interimResults = true
  instance.maxAlternatives = 1

  instance.onresult = (event) => {
    let interim = ''
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i]
      const text = result[0]?.transcript || ''
      if (result.isFinal) {
        const trimmed = text.trim()
        if (trimmed) emit('transcript', trimmed)
      } else {
        interim += text
      }
    }
    interimText.value = interim.trim()
  }

  instance.onerror = (event) => {
    // no-speech 属于正常静音，交给 onend 自动重启即可；其余错误提示并停止。
    if (event.error === 'no-speech' || event.error === 'aborted') return
    shouldListen = false
    isListening.value = false
    if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
      errorMessage.value = '无法使用麦克风：请在浏览器地址栏允许麦克风权限后重试。'
    } else if (event.error === 'audio-capture') {
      errorMessage.value = '未检测到可用麦克风，请检查设备连接。'
    } else if (event.error === 'network') {
      errorMessage.value = '语音识别服务网络异常，请检查网络后重试。'
    } else {
      errorMessage.value = `语音识别出错（${event.error}），请重试。`
    }
    emit('error', errorMessage.value)
  }

  instance.onend = () => {
    // Chrome 在静音或达时长上限后会自动结束，只要用户没有主动停止就续开。
    if (shouldListen) {
      clearRestartTimer()
      restartTimer = setTimeout(() => {
        if (!shouldListen) return
        try {
          instance.start()
        } catch {
          // start() 在实例未完全停止时会抛 InvalidStateError，下一轮 onend 再试。
        }
      }, 250)
      return
    }
    isListening.value = false
    interimText.value = ''
  }

  return instance
}

const stopListening = () => {
  shouldListen = false
  clearRestartTimer()
  if (recognition) {
    try {
      recognition.stop()
    } catch {
      // 忽略停止时实例已释放的异常。
    }
  }
  isListening.value = false
  interimText.value = ''
}

const startListening = () => {
  if (!isSupported.value) return
  errorMessage.value = ''
  try {
    recognition = recognition || buildRecognition()
    recognition.lang = props.lang
    recognition.start()
    shouldListen = true
    isListening.value = true
  } catch {
    // 连续快速点击时 start() 可能抛错，稍后由 onend 兜底重启。
    errorMessage.value = '语音输入启动失败，请稍候重试。'
    emit('error', errorMessage.value)
  }
}

const toggleListening = () => {
  if (isListening.value) {
    stopListening()
  } else {
    startListening()
  }
  emit('state-change', isListening.value)
}

onBeforeUnmount(() => {
  shouldListen = false
  clearRestartTimer()
  if (recognition) {
    try {
      recognition.abort()
    } catch {
      // 组件卸载时忽略释放异常。
    }
  }
})

// isListening 对外可见（父组件如需联动可监听 state-change）
defineExpose({
  stop: stopListening,
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
.voice-button:hover:not(:disabled):not(.unsupported) {
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
.voice-button.unsupported,
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

/* 实时转写预览气泡 */
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
