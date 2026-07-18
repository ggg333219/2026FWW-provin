<template>
  <div class="unified-md-renderer">
    <div v-if="errors.length" class="render-tip error">
      <strong>渲染异常：</strong>{{ errors.join('；') }}
    </div>
    <div v-else-if="warnings.length" class="render-tip warning">
      <strong>格式提示：</strong>{{ warnings.join('；') }}
    </div>
    <div ref="containerRef" class="markdown-body" v-html="renderedHtml"></div>
  </div>
</template>

<script setup>
/* eslint-disable no-undef */
import { computed, nextTick, ref, watch } from 'vue'
import { renderMarkdown, validateMarkdownFormat } from '../markdown/markdownRendererCore'

const props = defineProps({
  mdText: {
    type: String,
    default: ''
  },
  enableMermaid: {
    type: Boolean,
    default: true
  },
  mermaidRenderer: {
    type: Function,
    default: null
  }
})

const emit = defineEmits(['rendered', 'render-error'])

const containerRef = ref(null)
const renderedHtml = ref('')
const errors = ref([])
const warnings = ref([])

const inputText = computed(() => String(props.mdText || ''))

watch(
  () => inputText.value,
  async (text) => {
    const validation = validateMarkdownFormat(text)
    warnings.value = validation.issues || []

    const result = renderMarkdown(text)
    renderedHtml.value = result.html || ''
    errors.value = result.errors || []

    await nextTick()
    bindImageFallbacks()

    if (props.enableMermaid) {
      await renderMermaid()
    }

    if (errors.value.length) {
      emit('render-error', errors.value)
    }
    emit('rendered', { html: renderedHtml.value, errors: errors.value, warnings: warnings.value })
  },
  { immediate: true }
)

function createImagePlaceholderDataUrl(alt) {
  const label = encodeURIComponent(String(alt || '图片加载失败'))
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="100%" height="100%" fill="#f1f5f9"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#64748b" font-size="22">${label}</text></svg>`
  return `data:image/svg+xml;utf8,${svg}`
}

function bindImageFallbacks() {
  if (!containerRef.value) return
  const images = containerRef.value.querySelectorAll('img[data-md-image="1"]')

  images.forEach((img) => {
    if (img.dataset.fallbackBound === '1') return

    img.dataset.fallbackBound = '1'
    img.addEventListener('error', () => {
      if (img.dataset.fallbackApplied === '1') return
      img.dataset.fallbackApplied = '1'
      img.classList.add('md-image-broken')
      img.src = createImagePlaceholderDataUrl(img.alt)
    })
  })
}

async function renderMermaid() {
  if (!containerRef.value) return
  const blocks = containerRef.value.querySelectorAll('pre.mermaid-block[data-mermaid="true"]')
  if (!blocks.length) return

  if (typeof props.mermaidRenderer !== 'function') {
    warnings.value = [...warnings.value, 'Mermaid 渲染器不可用，图表将以文本显示']
    return
  }

  try {
    for (const block of blocks) {
      const graph = block.textContent || ''
      const id = `mermaid-${Math.random().toString(36).slice(2, 10)}`
      try {
        const svg = await props.mermaidRenderer(id, graph)
        block.outerHTML = `<div class="mermaid-chart">${svg}</div>`
      } catch (error) {
        block.outerHTML = '<div class="mermaid-error">图表渲染失败，已降级显示。</div>'
      }
    }
  } catch (error) {
    warnings.value = [...warnings.value, 'Mermaid 模块加载失败，图表将以文本显示']
  }
}

defineExpose({
  renderNow: () => ({ html: renderedHtml.value, errors: errors.value, warnings: warnings.value })
})
</script>

<style scoped>
.render-tip {
  margin-bottom: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
}

.render-tip.error {
  border: 1px solid #fecaca;
  background: #fff1f2;
  color: #991b1b;
}

.render-tip.warning {
  border: 1px solid #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.markdown-body {
  color: #334155;
  line-height: 1.7;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
}

.markdown-body :deep(.md-table-wrap) {
  width: 100%;
  overflow-x: auto;
  margin: 10px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #dbe5ee;
  padding: 6px 8px;
}

.markdown-body :deep(th) {
  background: #f8fafc;
  font-weight: 700;
}

.markdown-body :deep(tr:nth-child(even)) {
  background: #fcfdff;
}

.markdown-body :deep(img) {
  display: block;
  max-width: 100%;
  border-radius: 6px;
  border: 1px solid #dbe5ee;
  background: #f8fafc;
}

.markdown-body :deep(.md-image-placeholder) {
  padding: 12px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  color: #64748b;
  background: #f8fafc;
}

.markdown-body :deep(.md-format-error-panel) {
  margin-bottom: 12px;
  border: 1px solid #fca5a5;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fff1f2;
  color: #991b1b;
}

.markdown-body :deep(.md-format-error-panel ul) {
  margin: 8px 0 0;
  padding-left: 18px;
}

.markdown-body :deep(.md-error-token) {
  color: #b91c1c;
  background: #fee2e2;
  border: 1px solid #fca5a5;
  border-radius: 6px;
  padding: 1px 6px;
  display: inline-block;
}

.markdown-body :deep(pre) {
  overflow: auto;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid #dbe5ee;
  background: #f8fafc;
}

.markdown-body :deep(.mermaid-chart) {
  overflow: auto;
}

.markdown-body :deep(.mermaid-error) {
  padding: 8px 10px;
  border: 1px solid #fecaca;
  background: #fff1f2;
  color: #991b1b;
  border-radius: 8px;
}
</style>
