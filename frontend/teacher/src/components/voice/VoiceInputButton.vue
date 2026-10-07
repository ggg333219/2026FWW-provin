<template>
  <div class="voice-input" :class="{ listening: isListening }">
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
import { useVoiceRecognition } from './useVoiceRecognition'

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

const {
  isSupported,
  isListening,
  interimText,
  errorMessage,
  buttonTitle,
  stop: stopListening,
  toggle: toggleListening
} = useVoiceRecognition({
  lang: () => props.lang,
  onTranscript: (text) => emit('transcript', text),
  onError: (message) => emit('error', message),
  onStateChange: (listening) => emit('state-change', listening)
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
