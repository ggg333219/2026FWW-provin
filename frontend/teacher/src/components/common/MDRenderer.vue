<template>
  <div class="md-renderer-container" :class="{ 'md-has-errors': hasErrors }">
    <!-- 错误提示 -->
    <div v-if="hasErrors" class="md-error-banner">
      <div class="error-icon">⚠️</div>
      <div class="error-content">
        <strong>内容格式异常</strong>
        <ul v-if="errors && errors.length" class="error-list">
          <li v-for="(error, idx) in errors" :key="idx">{{ error }}</li>
        </ul>
      </div>
      <button class="error-close" @click="dismissErrors">✕</button>
    </div>

    <!-- 警告提示 -->
    <div v-if="hasWarnings && !errorDismissed" class="md-warning-banner">
      <div class="warning-icon">ℹ️</div>
      <div class="warning-content">
        <strong>提示</strong>
        <ul v-if="warnings && warnings.length" class="warning-list">
          <li v-for="(warning, idx) in warnings" :key="idx">{{ warning }}</li>
        </ul>
      </div>
    </div>

    <!-- 主内容渲染区域 -->
    <div class="md-content" v-html="renderedHtml" @mounted="renderMermaidDiagrams"></div>
  </div>
</template>

<script setup>
import { computed, watch, ref, onMounted, nextTick } from 'vue'
import { renderMarkdown, validateMarkdownFormat } from '@/utils/markdownRenderer'

const props = defineProps({
  content: {
    type: String,
    default: '',
    required: false
  },
  markdown: {
    type: String,
    default: '',
    required: false
  }
})

const emit = defineEmits(['render-complete', 'error', 'warning'])

const renderedHtml = ref('')
const errors = ref(null)
const warnings = ref(null)
const errorDismissed = ref(false)

const hasErrors = computed(() => errors.value && errors.value.length > 0 && !errorDismissed.value)
const hasWarnings = computed(() => warnings.value && warnings.value.length > 0)

// 使用 content 或 markdown 属性，content 优先用于向后兼容
const markdownContent = computed(() => props.content || props.markdown)

// 监听内容变化，执行渲染
watch(
  () => markdownContent.value,
  async (newContent) => {
    if (newContent) {
      await renderContent(newContent)
    }
  },
  { immediate: true }
)

/**
 * 渲染 Markdown 内容
 */
async function renderContent(content) {
  try {
    // 验证格式
    const validation = validateMarkdownFormat(content)
    if (!validation.isValid && validation.issues) {
      warnings.value = validation.issues
    }

    // 执行渲染
    const result = renderMarkdown(content)

    renderedHtml.value = result.html || ''
    errors.value = result.errors
    warnings.value = result.warnings

    // 触发事件
    emit('render-complete', { html: renderedHtml.value, errors: result.errors })

    if (result.errors) {
      emit('error', result.errors)
    }
    if (result.warnings) {
      emit('warning', result.warnings)
    }

    // 等待 DOM 更新后渲染 Mermaid 图表
    await nextTick()
    renderMermaidDiagrams()
  } catch (err) {
    console.error('[MDRenderer] 渲染失败:', err)
    errors.value = [err.message]
    emit('error', [err.message])
  }
}

/**
 * 渲染 Mermaid 图表
 */
async function renderMermaidDiagrams() {
  try {
    // 动态导入 Mermaid（减少初始加载体积）
    const mermaid = await import('mermaid')
    mermaid.initialize({ startOnLoad: true, theme: 'default' })

    // 查找所有 mermaid 块
    const mermaidBlocks = document.querySelectorAll('.mermaid-block[data-mermaid="true"]')

    if (mermaidBlocks.length === 0) return

    for (const block of mermaidBlocks) {
      try {
        const code = block.textContent
        const svg = await mermaid.render(`mermaid-${Date.now()}`, code)
        const container = document.createElement('div')
        container.className = 'mermaid-container'
        container.innerHTML = svg.svg
        block.replaceWith(container)
      } catch (err) {
        console.warn('[Mermaid] 单个图表渲染失败:', err)
        // 保留错误信息，不破坏整体内容
        block.className = 'mermaid-error'
        block.textContent = `图表渲染失败: ${err.message}`
      }
    }
  } catch (err) {
    console.error('[Mermaid] 动态导入失败，跳过图表渲染:', err)
    // 降级：Mermaid 不可用时不影响其他内容
  }
}

/**
 * 关闭错误提示
 */
function dismissErrors() {
  errorDismissed.value = true
}

// 初始化时执行渲染
onMounted(() => {
  if (markdownContent.value) {
    renderContent(markdownContent.value)
  }
})

// 暴露方法供外部调用
defineExpose({
  renderContent,
  renderMermaidDiagrams
})
</script>

<style scoped>
.md-renderer-container {
  width: 100%;
  position: relative;
}

/* 错误和警告横幅样式 */
.md-error-banner,
.md-warning-banner {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 6px;
  font-size: 14px;
  line-height: 1.5;
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.md-error-banner {
  background-color: #fff5f5;
  border: 1px solid #fcb8b8;
  color: #d32f2f;
}

.md-warning-banner {
  background-color: #fffbf0;
  border: 1px solid #fbd38d;
  color: #f57f17;
}

.error-icon,
.warning-icon {
  flex-shrink: 0;
  font-size: 18px;
}

.error-content,
.warning-content {
  flex: 1;
}

.error-content > strong,
.warning-content > strong {
  display: block;
  margin-bottom: 4px;
}

.error-list,
.warning-list {
  margin: 8px 0 0 0;
  padding-left: 20px;
}

.error-list li,
.warning-list li {
  margin: 4px 0;
}

.error-close {
  flex-shrink: 0;
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: inherit;
  padding: 0;
  opacity: 0.6;
}

.error-close:hover {
  opacity: 1;
}

/* 主内容样式 */
.md-content {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  color: #333;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

/* Markdown 元素样式 */
.md-content h1,
.md-content h2,
.md-content h3,
.md-content h4,
.md-content h5,
.md-content h6 {
  margin: 16px 0 8px 0;
  font-weight: 600;
  color: #222;
}

.md-content h1 {
  font-size: 28px;
  border-bottom: 2px solid #eee;
  padding-bottom: 8px;
}

.md-content h2 {
  font-size: 24px;
}

.md-content h3 {
  font-size: 20px;
}

.md-content h4 {
  font-size: 18px;
}

.md-content h5 {
  font-size: 16px;
}

.md-content h6 {
  font-size: 14px;
  color: #666;
}

.md-content p {
  margin: 12px 0;
}

.md-content blockquote {
  margin: 12px 0;
  padding: 8px 12px;
  border-left: 4px solid #ddd;
  background-color: #f5f5f5;
  color: #666;
}

.md-content code {
  background-color: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 14px;
  color: #e83e8c;
}

.md-content pre {
  background-color: #f5f5f5;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 12px 0;
}

.md-content pre code {
  background: none;
  padding: 0;
  color: #333;
}

.md-content ul,
.md-content ol {
  margin: 12px 0;
  padding-left: 24px;
}

.md-content li {
  margin: 4px 0;
}

.md-content a {
  color: #0066cc;
  text-decoration: none;
}

.md-content a:hover {
  text-decoration: underline;
}

/* 表格样式 */
.md-content table {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
}

.md-content table th,
.md-content table td {
  border: 1px solid #ddd;
  padding: 8px 12px;
  text-align: left;
}

.md-content table th {
  background-color: #f5f5f5;
  font-weight: 600;
}

.md-content table tr:nth-child(even) {
  background-color: #fafafa;
}

.md-content table tr:hover {
  background-color: #f0f0f0;
}

/* 图片样式 */
.md-content img {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  border: 1px solid #ddd;
  margin: 12px 0;
  display: block;
}

.md-image-error {
  display: inline-block;
  background-color: #f5f5f5;
  padding: 8px 12px;
  border-radius: 4px;
  color: #999;
  font-size: 12px;
  border: 1px dashed #ddd;
}

/* KaTeX 公式样式 */
:deep(.katex-block) {
  margin: 12px 0;
  padding: 8px;
  background-color: #f9f9f9;
  border-radius: 4px;
  overflow-x: auto;
}

:deep(.katex) {
  font-size: 1.1em;
}

/* Mermaid 图表容器 */
.mermaid-container {
  margin: 12px 0;
  padding: 12px;
  background-color: #f9f9f9;
  border-radius: 6px;
  border: 1px solid #eee;
  overflow-x: auto;
}

.mermaid-block[data-mermaid='true'] {
  display: none;
}

.mermaid-error {
  display: block;
  background-color: #fff5f5;
  color: #d32f2f;
  padding: 12px;
  border-radius: 4px;
  border: 1px solid #fcb8b8;
  margin: 12px 0;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 其他元素 */
.md-content strong {
  font-weight: 600;
}

.md-content em {
  font-style: italic;
}

.md-content del {
  text-decoration: line-through;
  color: #999;
}

.md-content hr {
  margin: 16px 0;
  border: none;
  border-top: 2px solid #eee;
}

/* 错误容器状态 */
.md-has-errors .md-content {
  opacity: 0.9;
}

/* 响应式 */
@media (max-width: 768px) {
  .md-content {
    font-size: 14px;
  }

  .md-content h1 {
    font-size: 24px;
  }

  .md-content h2 {
    font-size: 20px;
  }

  .md-content h3 {
    font-size: 18px;
  }

  .error-banner,
  .warning-banner {
    flex-direction: column;
    gap: 8px;
  }

  .error-close,
  .warning-close {
    align-self: flex-end;
  }
}
</style>
