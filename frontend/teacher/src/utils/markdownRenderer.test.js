import { describe, it, expect } from 'vitest'
import { renderMarkdown, validateMarkdownFormat, extractMarkdownMetadata } from './markdownRenderer'

describe('markdownRenderer fault tolerance', () => {
  it('renders inline and block formulas', () => {
    const input = '行内公式 $a+b$\n\n$$\na^2+b^2=c^2\n$$'
    const result = renderMarkdown(input)

    expect(result.html).toContain('katex')
    expect(result.errors).toBeNull()
  })

  it('detects and marks broken table', () => {
    const input = '| 列1 | 列2 |\n| 数据A | 数据B |'
    const validation = validateMarkdownFormat(input)
    const result = renderMarkdown(input)

    expect(validation.isValid).toBe(false)
    expect((validation.issues || []).join(' ')).toContain('表格')
    expect(result.html).toContain('格式错误提示')
  })

  it('detects and marks illegal image link', () => {
    const input = '![bad](javascript:alert(1))'
    const result = renderMarkdown(input)

    expect((result.warnings || []).join(' ')).toContain('图片链接非法')
    expect(result.html).toContain('md-error-token')
  })

  it('keeps readable content on severely broken markdown', () => {
    const input = '### 标题\n```js\nconst x = 1\n$$\nE=mc^2\n![图](javascript:abc)\n|a|b|'
    const result = renderMarkdown(input)

    expect(result.html).toContain('格式错误提示')
    expect(result.html).toContain('标题')
    expect(result.html.length).toBeGreaterThan(20)
  })

  it('supports image reference style conversion', () => {
    const input = '![图表1][chart]\n\n[chart]: demo.png'
    const result = renderMarkdown(input)

    expect(result.html).toContain('<img')
    expect(result.html).toContain('demo.png')
  })

  it('returns fallback error panel for non-string input', () => {
    const result = renderMarkdown(null)

    expect(result.errors).not.toBeNull()
    expect(result.html).toContain('格式错误提示')
  })

  it('passes validation for well-formed markdown', () => {
    const input = '# 标题\n\n这是一个正常段落，包含行内公式 $x+y$。'
    const validation = validateMarkdownFormat(input)

    expect(validation.isValid).toBe(true)
    expect(validation.issues).toBeNull()
  })

  it('extracts metadata for images links formulas and code blocks', () => {
    const input = '![图1](a.png)\n[官网](https://example.com)\n$$a^2+b^2=c^2$$\n```js\nconsole.log(1)\n```'
    const metadata = extractMarkdownMetadata(input)

    expect(metadata.images.length).toBe(1)
    expect(metadata.links.length).toBeGreaterThanOrEqual(1)
    expect(metadata.formulas.length).toBeGreaterThan(0)
    expect(metadata.codeBlocks.length).toBe(1)
  })
})
