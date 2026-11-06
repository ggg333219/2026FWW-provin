<template>
  <teleport to="body">
    <div v-if="open" class="llm-mask" @click.self="close">
      <div class="llm-dialog" role="dialog" aria-modal="true" aria-labelledby="llm-dialog-title">
        <div class="llm-header">
          <div>
            <h2 id="llm-dialog-title">接入你的大模型</h2>
            <p class="llm-subtitle">本平台不提供模型服务，需要你接入自己的第三方 API</p>
          </div>
          <button class="llm-close" type="button" aria-label="关闭" @click="close">×</button>
        </div>

        <div class="llm-status" :class="configured ? 'on' : 'off'">
          <span class="llm-dot"></span>
          <span v-if="configured">已接入 · 模型 {{ llm.model }} · Key {{ llm.maskedKey }}</span>
          <span v-else>未接入 · 当前使用本地规则提取 / 演示数据，界面会如实标注结果来源</span>
        </div>

        <div class="llm-form">
          <label class="llm-field">
            <span class="llm-label">API Base URL</span>
            <input
              v-model.trim="form.baseUrl"
              type="url"
              autocomplete="off"
              spellcheck="false"
              placeholder="https://api.example.com/v1"
            />
            <span class="llm-hint">OpenAI 兼容端点，需以 http(s) 开头</span>
          </label>

          <label class="llm-field">
            <span class="llm-label">API Key</span>
            <input
              v-model.trim="form.apiKey"
              type="password"
              autocomplete="off"
              spellcheck="false"
              placeholder="填写你自己的 Key"
            />
            <span class="llm-hint">仅保存在本浏览器，不会写入代码仓库或服务端配置文件</span>
          </label>

          <label class="llm-field">
            <span class="llm-label">模型名称</span>
            <input
              v-model.trim="form.model"
              type="text"
              autocomplete="off"
              spellcheck="false"
              placeholder="例如 gpt-4o-mini"
            />
            <span class="llm-hint">须与你的服务商提供的模型 ID 一致</span>
          </label>
        </div>

        <div class="llm-notice">
          <strong>关于配置与隐私</strong>
          <ul>
            <li>三项配置只保存在当前浏览器的本地存储，随每次意图提取请求发送，服务端仅在本次请求的内存中使用。</li>
            <li>不会写入仓库、环境变量或任何持久化配置文件；仓库里也不包含任何平台方的地址或密钥。</li>
            <li>建议通过 HTTPS 部署后再填写真实 Key；在公用电脑上用完请点「清除配置」。</li>
            <li>若后端不可达，前端会切到离线演示模式，此时不会调用你配置的模型，界面会显示来源提示。</li>
          </ul>
        </div>

        <p v-if="error" class="llm-error" role="alert">{{ error }}</p>

        <div class="llm-footer">
          <button class="llm-btn ghost danger" type="button" @click="handleClear">清除配置</button>
          <div class="llm-footer-right">
            <button class="llm-btn ghost" type="button" @click="close">取消</button>
            <button class="llm-btn primary" type="button" @click="handleSave">保存并启用</button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useLlmConfigStore } from '../../stores/llmConfigStore'

const props = defineProps({
  open: { type: Boolean, default: false }
})
const emit = defineEmits(['close', 'saved'])

const llm = useLlmConfigStore()
const form = ref({ baseUrl: '', apiKey: '', model: '' })
const error = ref('')

const configured = computed(() => llm.isConfigured)

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return
    llm.load()
    form.value = {
      baseUrl: llm.baseUrl,
      apiKey: llm.apiKey,
      model: llm.model
    }
    error.value = ''
  },
  { immediate: true }
)

const close = () => emit('close')

const handleSave = () => {
  const baseUrl = String(form.value.baseUrl || '').trim()
  const apiKey = String(form.value.apiKey || '').trim()
  const model = String(form.value.model || '').trim()
  if (!baseUrl || !apiKey || !model) {
    error.value = '请完整填写 Base URL、API Key 和模型名称。'
    return
  }
  if (!/^https?:\/\//i.test(baseUrl)) {
    error.value = 'Base URL 必须以 http:// 或 https:// 开头。'
    return
  }
  llm.save({ baseUrl, apiKey, model })
  error.value = ''
  emit('saved')
  close()
}

const handleClear = () => {
  llm.clear()
  form.value = { baseUrl: '', apiKey: '', model: '' }
  error.value = ''
  emit('saved')
}
</script>

<style scoped>
.llm-mask {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.42);
  backdrop-filter: blur(3px);
}

.llm-dialog {
  width: min(560px, 100%);
  max-height: min(90vh, 760px);
  overflow-y: auto;
  box-sizing: border-box;
  padding: 24px 26px 20px;
  border-radius: 20px;
  background: #ffffff;
  border: 1px solid rgba(120, 156, 140, 0.24);
  box-shadow: 0 28px 70px rgba(15, 23, 42, 0.24);
  color: #111827;
  font-family: 'SF Pro Display', 'SF Pro Text', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.llm-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.llm-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 680;
  letter-spacing: 0.01em;
}

.llm-subtitle {
  margin: 6px 0 0;
  font-size: 12px;
  color: #5f7467;
}

.llm-close {
  border: 0;
  background: transparent;
  font-size: 24px;
  line-height: 1;
  color: #64748b;
  cursor: pointer;
  padding: 0 4px;
}

.llm-close:hover { color: #111827; }

.llm-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 18px 0 20px;
  padding: 10px 13px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
}

.llm-status.on { background: #ecf8f3; color: #047857; }
.llm-status.off { background: #fffbeb; color: #9a6700; }

.llm-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: currentColor;
}

.llm-form { display: flex; flex-direction: column; gap: 15px; }

.llm-field { display: flex; flex-direction: column; gap: 6px; }

.llm-label { font-size: 13px; font-weight: 650; color: #1f2937; }

.llm-field input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(120, 156, 140, 0.38);
  background: #fbfdfc;
  color: #111827;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.llm-field input:focus {
  border-color: #5ca68f;
  box-shadow: 0 0 0 3px rgba(92, 166, 143, 0.16);
}

.llm-hint { font-size: 11px; color: #6b7f74; line-height: 1.5; }

.llm-notice {
  margin-top: 18px;
  padding: 13px 15px;
  border-radius: 12px;
  background: #f6faf8;
  border: 1px solid rgba(120, 156, 140, 0.2);
  font-size: 11.5px;
  color: #4b5f55;
  line-height: 1.7;
}

.llm-notice strong { display: block; margin-bottom: 4px; color: #2f6052; font-size: 12px; }
.llm-notice ul { margin: 0; padding-left: 18px; }
.llm-notice li { margin: 2px 0; }

.llm-error {
  margin: 12px 0 0;
  padding: 9px 12px;
  border-radius: 10px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 12px;
}

.llm-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 20px;
}

.llm-footer-right { display: flex; gap: 8px; }

.llm-btn {
  padding: 9px 16px;
  border-radius: 10px;
  font-size: 12.5px;
  font-weight: 650;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.2s, border-color 0.2s, color 0.2s;
}

.llm-btn.primary { background: #2f6052; color: #ffffff; }
.llm-btn.primary:hover { background: #244c41; }
.llm-btn.ghost { background: #ffffff; border-color: rgba(120, 156, 140, 0.38); color: #334155; }
.llm-btn.ghost:hover { border-color: #5ca68f; }
.llm-btn.danger { color: #b91c1c; }
.llm-btn.danger:hover { border-color: #ef4444; }
</style>
