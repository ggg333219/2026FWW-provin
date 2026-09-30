/**
 * previewPatch 的页级补丁测试。
 *
 * 本仓 vitest 跑在 `node` 环境（vitest.config.js），没有 DOM。这里按需引入 jsdom
 * 自建一个 document，而不是用 `@vitest-environment jsdom` 指令 —— 那种写法在
 * jsdom 未安装时会直接让整个测试文件报错。改成动态 import 后：
 * 装了 jsdom 就跑全量，没装就整组跳过，`npm run test:unit` 在任何一种情况下都是绿的。
 *
 * 要跑起来：`npm i -D jsdom`
 */
import { beforeAll, describe, expect, it } from 'vitest'
import { patchPreview, PATCH_MODE } from './previewPatch'

let JSDOM = null
try {
  ;({ JSDOM } = await import('jsdom'))
} catch {
  // 未安装 jsdom —— 下面的用例整组跳过
}

const describeWithDom = JSDOM ? describe : describe.skip

const STYLE = '.slide { color: #123; } .script-panel { font-size: 12px; }'

/** 造一份与引擎 `_wrap_html` 同构的预览 HTML：页单元 = slide 外壳 + 紧随的讲稿折叠区。 */
function buildHtml({ style = STYLE, pages = [], palette = 'classic' } = {}) {
  const body = pages
    .map((page) => [
      `<div class="slide content-slide" data-node-id="${page.id}">`,
      `<div class="slide-num">${page.order}</div>${page.body}`,
      `</div>`,
      `<details class="script-panel"><summary>讲稿</summary>${page.script || ''}</details>`,
    ].join(''))
    .join('')
  return [
    '<!doctype html><html><head><style>', style, '</style></head><body>',
    `<div class="presentation" data-palette="${palette}" data-layout="balanced" data-density="comfortable">`,
    body,
    '</div></body></html>',
  ].join('')
}

const THREE_PAGES = [
  { id: 'node_1', order: 1, body: '引言正文', script: '引言讲稿' },
  { id: 'node_2', order: 2, body: '冒泡排序正文', script: '冒泡讲稿' },
  { id: 'node_3', order: 3, body: '快速排序正文', script: '快排讲稿' },
]

function mount(html) {
  const dom = new JSDOM(html)
  return { window: dom.window, iframe: { contentDocument: dom.window.document } }
}

/** 取出某一页的页单元 outerHTML（slide + 讲稿），用于逐字比对。 */
function pageUnitHtml(doc, nodeId) {
  const slide = doc.querySelector(`.slide[data-node-id="${nodeId}"]`)
  const details = slide.nextElementSibling
  return slide.outerHTML + (details?.tagName === 'DETAILS' ? details.outerHTML : '')
}

describeWithDom('patchPreview', () => {
  beforeAll(() => {
    // 模块内部用全局 DOMParser 解析新 HTML，node 环境没有，借 jsdom 的
    globalThis.DOMParser = new JSDOM('').window.DOMParser
  })

  it('只换变了的那一页，其余页逐字不变', () => {
    const { iframe, window } = mount(buildHtml({ pages: THREE_PAGES }))
    const before1 = pageUnitHtml(window.document, 'node_1')
    const before3 = pageUnitHtml(window.document, 'node_3')

    const next = buildHtml({
      pages: [
        THREE_PAGES[0],
        { ...THREE_PAGES[1], body: '冒泡排序正文（已精简）', script: '冒泡讲稿（已精简）' },
        THREE_PAGES[2],
      ],
    })
    const result = patchPreview(iframe, next)

    expect(result.mode).toBe(PATCH_MODE.PATCH)
    expect(result.patched).toEqual(['node_2'])
    // 关键断言：没被点到的页必须一个字节都没动（滚动位置靠这个保住）
    expect(pageUnitHtml(window.document, 'node_1')).toBe(before1)
    expect(pageUnitHtml(window.document, 'node_3')).toBe(before3)
    expect(window.document.querySelector('.slide[data-node-id="node_2"]').textContent)
      .toContain('已精简')
  })

  it('内容没变时一页都不换', () => {
    const { iframe } = mount(buildHtml({ pages: THREE_PAGES }))
    const result = patchPreview(iframe, buildHtml({ pages: THREE_PAGES }))
    expect(result.mode).toBe(PATCH_MODE.PATCH)
    expect(result.patched).toEqual([])
  })

  it('讲稿折叠区的展开状态被保留', () => {
    const { iframe, window } = mount(buildHtml({ pages: THREE_PAGES }))
    const details = window.document
      .querySelector('.slide[data-node-id="node_2"]').nextElementSibling
    details.open = true

    patchPreview(iframe, buildHtml({
      pages: [THREE_PAGES[0], { ...THREE_PAGES[1], body: '改过' }, THREE_PAGES[2]],
    }))

    const after = window.document
      .querySelector('.slide[data-node-id="node_2"]').nextElementSibling
    expect(after.open).toBe(true)
  })

  it('页数变了 → 退回整份重设', () => {
    const { iframe } = mount(buildHtml({ pages: THREE_PAGES }))
    const result = patchPreview(iframe, buildHtml({ pages: THREE_PAGES.slice(0, 2) }))
    expect(result.mode).toBe(PATCH_MODE.SRCDOC)
  })

  it('页序变了 → 退回整份重设', () => {
    const { iframe } = mount(buildHtml({ pages: THREE_PAGES }))
    const swapped = [THREE_PAGES[1], THREE_PAGES[0], THREE_PAGES[2]]
    const result = patchPreview(iframe, buildHtml({ pages: swapped }))
    expect(result.mode).toBe(PATCH_MODE.SRCDOC)
  })

  it('样式变了 → 退回整份重设（restyle 走全量）', () => {
    const { iframe } = mount(buildHtml({ pages: THREE_PAGES }))
    const next = buildHtml({ pages: THREE_PAGES, style: `${STYLE} .slide { color: #c00; }` })
    expect(patchPreview(iframe, next).mode).toBe(PATCH_MODE.SRCDOC)
  })

  it('配色变了 → 退回整份重设', () => {
    const { iframe } = mount(buildHtml({ pages: THREE_PAGES }))
    const next = buildHtml({ pages: THREE_PAGES, palette: 'klein-blue' })
    expect(patchPreview(iframe, next).mode).toBe(PATCH_MODE.SRCDOC)
  })

  it('取不到 contentDocument → 退回整份重设，不抛错', () => {
    const throwing = {
      get contentDocument() {
        throw new Error('opaque origin')
      },
    }
    expect(patchPreview(throwing, buildHtml({ pages: THREE_PAGES })).mode).toBe(PATCH_MODE.SRCDOC)
    expect(patchPreview(null, buildHtml({ pages: THREE_PAGES })).mode).toBe(PATCH_MODE.SRCDOC)
  })

  it('HTML 里没有 .presentation → 退回整份重设', () => {
    const { iframe } = mount(buildHtml({ pages: THREE_PAGES }))
    expect(patchPreview(iframe, '<html><body>nope</body></html>').mode).toBe(PATCH_MODE.SRCDOC)
  })

  it('只有讲稿变、幻灯片没变时，自动把讲稿摊开', () => {
    const { iframe, window } = mount(buildHtml({ pages: THREE_PAGES }))
    const before = window.document
      .querySelector('.slide[data-node-id="node_2"]').nextElementSibling
    expect(before.open).toBe(false)

    // 局部修改默认只重写 script / segments，它们不上幻灯片 ——
    // 不摊开的话，老师看到的就是「对话说已更新，页面纹丝不动」
    patchPreview(iframe, buildHtml({
      pages: [THREE_PAGES[0], { ...THREE_PAGES[1], script: '冒泡讲稿（已重写）' }, THREE_PAGES[2]],
    }))

    const after = window.document
      .querySelector('.slide[data-node-id="node_2"]').nextElementSibling
    expect(after.open).toBe(true)
    expect(after.textContent).toContain('已重写')
  })

  it('幻灯片本身变了就不多摊讲稿（改动已经看得见了）', () => {
    const { iframe, window } = mount(buildHtml({ pages: THREE_PAGES }))
    patchPreview(iframe, buildHtml({
      pages: [THREE_PAGES[0], { ...THREE_PAGES[1], body: '新正文' }, THREE_PAGES[2]],
    }))
    const after = window.document
      .querySelector('.slide[data-node-id="node_2"]').nextElementSibling
    expect(after.open).toBe(false)
  })

  it('展开讲稿不算「这页改了」（open 是视图状态，不是内容）', () => {
    const { iframe, window } = mount(buildHtml({ pages: THREE_PAGES }))
    const details = window.document
      .querySelector('.slide[data-node-id="node_2"]').nextElementSibling
    details.open = true

    // 内容一字未改，只是教师把讲稿展开了 —— 不该被当成变更去替换
    const result = patchPreview(iframe, buildHtml({ pages: THREE_PAGES }))
    expect(result.patched).toEqual([])
  })

  it('连续补丁两次仍然走补丁（高亮样式不该污染下一次比对）', () => {
    const { iframe } = mount(buildHtml({ pages: THREE_PAGES }))
    const first = patchPreview(iframe, buildHtml({
      pages: [THREE_PAGES[0], { ...THREE_PAGES[1], body: '第一次改' }, THREE_PAGES[2]],
    }))
    const second = patchPreview(iframe, buildHtml({
      pages: [THREE_PAGES[0], { ...THREE_PAGES[1], body: '第二次改' }, THREE_PAGES[2]],
    }))

    expect(first.mode).toBe(PATCH_MODE.PATCH)
    // 补丁会在预览文档里注入高亮 <style>；它不能被算进样式指纹，
    // 否则第二次比对永远不等，补丁退化成整份重设。
    expect(second.mode).toBe(PATCH_MODE.PATCH)
    expect(second.patched).toEqual(['node_2'])
  })

  it('给了 changedNodeIds 就只信它，不再逐页比对', () => {
    const { iframe } = mount(buildHtml({ pages: THREE_PAGES }))
    const next = buildHtml({
      pages: [THREE_PAGES[0], { ...THREE_PAGES[1], body: '改过' }, THREE_PAGES[2]],
    })
    const result = patchPreview(iframe, next, ['node_1'])
    // node_2 的正文其实也变了，但显式指定了目标就只有 node_1 被换
    expect(result.patched).toEqual(['node_1'])
  })
})
