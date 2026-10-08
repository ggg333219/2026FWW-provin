import { computed, onScopeDispose, ref } from 'vue'

export function useVoiceRecognition({ lang = 'zh-CN', onTranscript, onError, onStateChange } = {}) {
  const RecognitionCtor = typeof window !== 'undefined'
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null
  const isSupported = Boolean(RecognitionCtor)
  const isListening = ref(false)
  const interimText = ref('')
  const errorMessage = ref('')
  const buttonTitle = computed(() => {
    if (!isSupported) return '当前浏览器不支持语音识别，请使用 Chrome / Edge'
    return isListening.value ? '停止语音输入' : '语音输入（点击开始）'
  })

  let recognition = null
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
    instance.lang = typeof lang === 'function' ? lang() : lang
    instance.continuous = true
    instance.interimResults = true
    instance.maxAlternatives = 1

    instance.onresult = (event) => {
      let interim = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index]
        const text = result[0]?.transcript || ''
        if (result.isFinal) {
          const trimmed = text.trim()
          if (trimmed) onTranscript?.(trimmed)
        } else {
          interim += text
        }
      }
      interimText.value = interim.trim()
    }

    instance.onerror = (event) => {
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
        errorMessage.value = '语音识别失败，请重试或改用文字输入。'
      }
      onError?.(errorMessage.value)
      onStateChange?.(false)
    }

    instance.onend = () => {
      if (shouldListen) {
        clearRestartTimer()
        restartTimer = setTimeout(() => {
          if (!shouldListen) return
          try {
            instance.start()
          } catch {
            // Web Speech may emit onend before the browser releases its recognizer.
          }
        }, 250)
        return
      }
      isListening.value = false
      interimText.value = ''
      onStateChange?.(false)
    }
    return instance
  }

  const stop = () => {
    shouldListen = false
    clearRestartTimer()
    if (recognition) {
      try {
        recognition.stop()
      } catch {
        // Ignore a recognizer that has already stopped.
      }
    }
    isListening.value = false
    interimText.value = ''
    onStateChange?.(false)
  }

  const start = () => {
    if (!isSupported) return false
    errorMessage.value = ''
    try {
      recognition = recognition || buildRecognition()
      recognition.lang = typeof lang === 'function' ? lang() : lang
      recognition.start()
      shouldListen = true
      isListening.value = true
      onStateChange?.(true)
      return true
    } catch {
      errorMessage.value = '语音输入启动失败，请稍候重试或改用文字输入。'
      onError?.(errorMessage.value)
      return false
    }
  }

  const toggle = () => {
    if (isListening.value) stop()
    else start()
  }

  onScopeDispose(() => {
    shouldListen = false
    clearRestartTimer()
    try {
      recognition?.abort()
    } catch {
      // Ignore cleanup errors on unmount.
    }
  })

  return { isSupported, isListening, interimText, errorMessage, buttonTitle, start, stop, toggle }
}
