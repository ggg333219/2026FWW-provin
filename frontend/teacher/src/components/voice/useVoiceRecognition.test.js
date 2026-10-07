import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { useVoiceRecognition } from './useVoiceRecognition'

let activeScope

afterEach(() => {
  activeScope?.stop()
  activeScope = null
  delete globalThis.window
  vi.useRealTimers()
})

function createSubject(options = {}) {
  let subject
  activeScope = effectScope()
  activeScope.run(() => { subject = useVoiceRecognition(options) })
  return subject
}

describe('useVoiceRecognition', () => {
  it('detects browser support and sends only final transcript segments to the caller', () => {
    const instances = []
    class SpeechRecognitionStub {
      start() { this.started = true }
      stop() { this.onend?.() }
      abort() {}
      constructor() { instances.push(this) }
    }
    globalThis.window = { webkitSpeechRecognition: SpeechRecognitionStub }
    const onTranscript = vi.fn()
    const subject = createSubject({ onTranscript })

    expect(subject.isSupported).toBe(true)
    expect(subject.start()).toBe(true)
    expect(instances[0].lang).toBe('zh-CN')
    instances[0].onresult({
      resultIndex: 0,
      results: [
        Object.assign([{ transcript: ' partial' }], { isFinal: false }),
        Object.assign([{ transcript: ' 课程主题 ' }], { isFinal: true })
      ]
    })

    expect(subject.interimText.value).toBe('partial')
    expect(onTranscript).toHaveBeenCalledExactlyOnceWith('课程主题')
  })

  it('keeps text entry available when speech recognition is unsupported', () => {
    globalThis.window = {}
    const subject = createSubject()

    expect(subject.isSupported).toBe(false)
    expect(subject.buttonTitle.value).toContain('不支持语音识别')
    expect(subject.start()).toBe(false)
  })

  it('shows a recoverable permission error and stops the listening state', () => {
    let recognizer
    class SpeechRecognitionStub {
      constructor() { recognizer = this }
      start() {}
      stop() {}
      abort() {}
    }
    globalThis.window = { SpeechRecognition: SpeechRecognitionStub }
    const subject = createSubject()
    subject.start()
    recognizer.onerror({ error: 'not-allowed' })

    expect(subject.isListening.value).toBe(false)
    expect(subject.errorMessage.value).toContain('允许麦克风权限后重试')
  })
})
