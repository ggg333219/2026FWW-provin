let mdInstance = null
let MarkdownItCtor = null
let markdownItKatexPlugin = null

export function configureMarkdownRendererDependencies(deps = {}) {
  const nextCtor = deps.MarkdownIt || deps.markdownIt || null
  const nextKatex = deps.markdownItKatex || deps.katexPlugin || null

  if (nextCtor && nextCtor !== MarkdownItCtor) {
    MarkdownItCtor = nextCtor
    mdInstance = null
  }
  if (nextKatex && nextKatex !== markdownItKatexPlugin) {
    markdownItKatexPlugin = nextKatex
    mdInstance = null
  }
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function sanitizeHtml(html) {
  if (!html || typeof html !== 'string') return ''
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/\s+on[a-z]+\s*=\s*(["']).*?\1/gi, '')
}

function createFallbackRenderer() {
  return {
    render(text) {
      return `<pre class="md-fallback">${escapeHtml(text)}</pre>`
    }
  }
}

function resolveImageSrc(src) {
  const raw = String(src || '').trim()
  if (!raw) return ''

  const normalized = raw.replace(/\\/g, '/')
  if (/^(https?:|data:|blob:|file:|\/)/i.test(normalized)) return normalized
  if (normalized.startsWith('//')) return `https:${normalized}`

  try {
    return encodeURI(normalized)
  } catch (error) {
    return normalized
  }
}

function countUnescapedDoubleToken(text, token) {
  const source = String(text || '')
  let count = 0
  for (let i = 0; i < source.length - 1; i += 1) {
    if (source[i] === '\\') {
      i += 1
      continue
    }
    if (source.slice(i, i + token.length) === token) {
      count += 1
      i += token.length - 1
    }
  }
  return count
}

function detectInlineDollarIssue(text) {
  const source = String(text || '')
  let count = 0
  for (let i = 0; i < source.length; i += 1) {
    if (source[i] === '\\') {
      i += 1
      continue
    }
    if (source[i] === '$') {
      const prev = source[i - 1]
      const next = source[i + 1]
      if (prev === '$' || next === '$') continue
      count += 1
    }
  }
  return count % 2 !== 0
}

function detectMarkdownIssues(text) {
  // 扫描大模型常见损坏模式，供上层决定告警与自动修复策略。
  const source = String(text || '')
  const issues = []

  const codeFenceCount = countUnescapedDoubleToken(source, '```')
  if (codeFenceCount % 2 !== 0) {
    issues.push({ code: 'code_fence_unclosed', message: '⚠️ 此处格式异常：代码块未闭合' })
  }

  const blockFormulaCount = countUnescapedDoubleToken(source, '$$')
  if (blockFormulaCount % 2 !== 0) {
    issues.push({ code: 'formula_block_unclosed', message: '⚠️ 此处格式异常：块级公式未闭合' })
  }

  if (detectInlineDollarIssue(source)) {
    issues.push({ code: 'formula_inline_unclosed', message: '⚠️ 此处格式异常：行内公式未闭合' })
  }

  const tableLineRegex = /^\s*\|.*\|\s*$/gm
  const tableLines = source.match(tableLineRegex) || []
  if (tableLines.length > 0) {
    const hasHeaderSeparator = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/m.test(source)
    if (!hasHeaderSeparator) {
      issues.push({ code: 'table_unclosed', message: '⚠️ 此处格式异常：表格分隔行缺失或不完整' })
    }
  }

  const invalidImageRegex = /!\[[^\]]*\]\(([^)]*)\)/g
  let match
  while ((match = invalidImageRegex.exec(source))) {
    const target = String(match[1] || '').trim()
    if (!target || /^javascript:/i.test(target)) {
      issues.push({ code: 'image_invalid_link', message: '⚠️ 此处格式异常：图片链接非法或为空' })
      break
    }
  }

  return issues
}

function normalizeImageReferences(text) {
  const raw = String(text || '')
  const definitions = {}
  const definitionRegex = /^\[([^\]]+)\]:\s*(\S+)(?:\s+"[^"]*")?\s*$/gm
  let match

  while ((match = definitionRegex.exec(raw))) {
    definitions[match[1].trim().toLowerCase()] = match[2].trim()
  }

  let normalized = raw

  normalized = normalized.replace(/!\[([^\]]*)\]\[([^\]]*)\]/g, (full, alt, ref) => {
    const key = String(ref || alt || '').trim().toLowerCase()
    const resolved = definitions[key]
    if (!resolved) return full
    return `![${alt}](${resolved})`
  })

  normalized = normalized.replace(/!\[([^\]]+)\](?![[(])/g, (full, ref) => {
    const key = String(ref || '').trim().toLowerCase()
    const resolved = definitions[key]
    if (!resolved) return full
    return `![${ref}](${resolved})`
  })

  normalized = normalized.replace(definitionRegex, (full, label, src) => {
    const isImagePath = /\.(png|jpe?g|gif|webp|svg|bmp)(\?.*)?$/i.test(src)
    const isImageLabel = /(图|图片|图表|image|img|chart)/i.test(label)
    if (isImagePath || isImageLabel) {
      return `![${label}](${src})`
    }
    return full
  })

  return normalized
}

function repairMarkdownInput(text, issues) {
  // 在不丢失可识别内容的前提下做最小修复，确保后续渲染稳定。
  let repaired = normalizeImageReferences(String(text || ''))

  if (issues.some((item) => item.code === 'formula_block_unclosed')) {
    repaired += '\n\n$$\n'
  }
  if (issues.some((item) => item.code === 'code_fence_unclosed')) {
    repaired += '\n\n```\n'
  }

  repaired = repaired.replace(/!\[([^\]]*)\]\(([^)]*)\)/g, (full, alt, src) => {
    const target = String(src || '').trim()
    if (!target || /^javascript:/i.test(target)) {
      return `<span class="md-error-token">⚠️ 此处格式异常：图片链接非法（${escapeHtml(alt || '未命名图片')}）</span>`
    }
    return full
  })

  return repaired
}

function renderIssuesAsHtml(issues) {
  if (!issues.length) return ''
  const rows = issues
    .map((item) => `<li>${escapeHtml(item.message)}</li>`)
    .join('')
  return `<div class="md-format-error-panel"><strong>格式错误提示</strong><ul>${rows}</ul></div>`
}

export function initMarkdownRenderer() {
  if (mdInstance) return mdInstance

  try {
    if (!MarkdownItCtor || !markdownItKatexPlugin) {
      mdInstance = createFallbackRenderer()
      return mdInstance
    }

    const engine = new MarkdownItCtor({
      html: true,
      breaks: true,
      linkify: true,
      typographer: true
    }).use(markdownItKatexPlugin, {
      throwOnError: false,
      errorColor: '#cc0000',
      output: 'htmlAndMathml',
      strict: 'ignore'
    })

    const fallbackFence = engine.renderer.rules.fence || ((tokens, idx, opts, env, self) => self.renderToken(tokens, idx, opts))

    engine.renderer.rules.image = (tokens, idx) => {
      const token = tokens[idx]
      const src = resolveImageSrc(token.attrGet('src') || '')
      const alt = token.content || ''
      if (!src.trim()) {
        return `<div class="md-image-placeholder">图片不可用：${escapeHtml(alt || '未命名图片')}</div>`
      }
      return `<img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy" class="md-image" data-md-image="1" />`
    }

    engine.renderer.rules.table_open = () => '<div class="md-table-wrap"><table class="md-table">'
    engine.renderer.rules.table_close = () => '</table></div>'

    engine.renderer.rules.fence = (tokens, idx, opts, env, self) => {
      const token = tokens[idx]
      const info = String(token.info || '').trim().toLowerCase()
      if (info === 'mermaid' || info.startsWith('mermaid')) {
        return `<pre class="mermaid-block" data-mermaid="true">${escapeHtml(token.content || '')}</pre>`
      }
      return fallbackFence(tokens, idx, opts, env, self)
    }

    engine.normalizeLink = (url) => {
      const raw = String(url || '').trim()
      const lower = raw.toLowerCase()
      const hasDangerousProtocol = lower.startsWith('javascript:') || lower.startsWith('vbscript:')
      const safe = !hasDangerousProtocol
      return safe ? raw : '#'
    }

    mdInstance = engine
    return mdInstance
  } catch (error) {
    console.error('[markdownRenderer] init failed', error)
    mdInstance = createFallbackRenderer()
    return mdInstance
  }
}

export function renderMarkdown(markdownText) {
  // 主入口：先检测问题，再尝试修复并渲染；任何异常都降级为可读输出。
  const errors = []
  const warnings = []

  try {
    if (!markdownText || typeof markdownText !== 'string') {
      return {
        html: '<div class="md-format-error-panel"><strong>格式错误提示</strong><ul><li>⚠️ 此处格式异常：输入不是有效文本</li></ul></div><pre class="md-fallback">(empty)</pre>',
        errors: ['输入不是有效文本'],
        warnings: null
      }
    }

    const issues = detectMarkdownIssues(markdownText)
    if (issues.length) {
      warnings.push(...issues.map((item) => item.message))
    }

    if (markdownText.length > 1024 * 1024) {
      warnings.push('⚠️ 文本过长，可能影响性能')
    }

    const engine = initMarkdownRenderer()
    const repairedInput = repairMarkdownInput(markdownText, issues)
    const issueHtml = renderIssuesAsHtml(issues)

    let html = ''
    try {
      html = engine.render(repairedInput)
    } catch (renderError) {
      errors.push(`Markdown 渲染错误: ${renderError.message}`)
      html = `<pre class="md-fallback">${escapeHtml(repairedInput.slice(0, 5000))}</pre>`
    }

    return {
      html: sanitizeHtml(`${issueHtml}${html}`),
      errors: errors.length ? errors : null,
      warnings: warnings.length ? warnings : null
    }
  } catch (error) {
    return {
      html: `<div class="md-format-error-panel"><strong>格式错误提示</strong><ul><li>⚠️ 此处格式异常：${escapeHtml(error.message || '渲染异常')}</li></ul></div><pre class="md-fallback">${escapeHtml(String(markdownText || '').slice(0, 5000))}</pre>`,
      errors: [error.message || '渲染异常'],
      warnings: null
    }
  }
}

export function validateMarkdownFormat(text) {
  if (!text || typeof text !== 'string') {
    return { isValid: false, issues: ['⚠️ 此处格式异常：文本格式错误'] }
  }
  const issues = detectMarkdownIssues(text).map((item) => item.message)
  return { isValid: issues.length === 0, issues: issues.length ? issues : null }
}

export function extractMarkdownMetadata(text) {
  if (!text || typeof text !== 'string') {
    return { images: [], links: [], formulas: [], codeBlocks: [] }
  }

  const metadata = { images: [], links: [], formulas: [], codeBlocks: [] }

  let match
  const imageRegex = /!\[([^\]]*)\]\(([^)]+)\)/g
  while ((match = imageRegex.exec(text))) {
    metadata.images.push({ alt: match[1], src: match[2] })
  }

  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g
  while ((match = linkRegex.exec(text))) {
    metadata.links.push({ text: match[1], url: match[2] })
  }

  const formulaRegex = /\$\$?([^$]+?)\$\$?/g
  while ((match = formulaRegex.exec(text))) {
    metadata.formulas.push(match[0])
  }

  const codeRegex = /```(\w*)\n([\s\S]*?)```/g
  while ((match = codeRegex.exec(text))) {
    metadata.codeBlocks.push({ language: match[1] || 'plain', code: match[2] })
  }

  return metadata
}

export default {
  renderMarkdown,
  validateMarkdownFormat,
  extractMarkdownMetadata,
  initMarkdownRenderer,
  configureMarkdownRendererDependencies
}
