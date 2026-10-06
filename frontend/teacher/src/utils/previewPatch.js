/**
 * 预览局部补丁 —— 「改一页只换一页」。
 *
 * 背景：预览是服务端渲染的一整份 HTML，塞进 iframe。此前每次修改完都换掉 iframe 的
 * `src`，于是整份课件重载、闪一下、滚动位置回到顶部 —— 改一页和改十页的观感一模一样。
 *
 * 现在预览走 `srcdoc`（继承父源，`contentDocument` 可访问），引擎又给每页外壳打了
 * `data-node-id`，于是可以在**不重载文档**的前提下，只把变了的页就地替换掉。
 *
 * 页单元的定义：一个带 `data-node-id` 的外壳，加上紧随其后的兄弟节点（讲稿折叠区）
 * —— 两者同属一页，必须同进同退，否则会留下与新正文对不上的旧讲稿。
 *
 * 什么时候退回整份重设（`mode: 'srcdoc'`，即改动前的行为）：
 *   - 取不到 `contentDocument`（跨源 / 未挂载 / 沙箱不给）
 *   - 样式层变了（配色、版式、字体、密度）—— 只换页会让页面与样式脱节，restyle 天然走这条
 *   - 页数或页序变了 —— 补丁无从对齐
 * 任何一条命中都只是**降级**，不会白屏。
 *
 * 页单元由引擎 gen/preview.py 的 `_render_slide` 产出，两端的契约就是 `data-node-id`。
 */

/** 补丁模式。`srcdoc` = 整份重设，即这个模块出现之前的行为。 */
export const PATCH_MODE = {
  PATCH: 'patch',
  SRCDOC: 'srcdoc',
}

const PRESENTATION_SELECTOR = '.presentation'
const PAGE_ATTR = 'data-node-id'
const HIGHLIGHT_CLASS = 's3-preview-updated'
const HIGHLIGHT_STYLE_ID = 's3-preview-patch-style'
const HIGHLIGHT_MS = 1600

const HIGHLIGHT_CSS = `
.${HIGHLIGHT_CLASS} {
  animation: s3PreviewUpdated ${HIGHLIGHT_MS}ms ease-out;
}
@keyframes s3PreviewUpdated {
  0% { box-shadow: 0 0 0 3px rgba(36, 163, 111, 0.55); }
  60% { box-shadow: 0 0 0 3px rgba(36, 163, 111, 0.28); }
  100% { box-shadow: 0 0 0 3px rgba(36, 163, 111, 0); }
}
`

function contentDocumentOf(iframeEl) {
  try {
    return iframeEl?.contentDocument || null
  } catch {
    // data: URL 是不透明源，取 contentDocument 会抛；跨源同理。
    return null
  }
}

/**
 * `<style>` 文本的指纹：配色 / 字体 / 密度 / 版式都在里面。
 *
 * 必须排掉自己注入的高亮样式 —— 它在第一次补丁后就留在预览文档里，算进去会让
 * 下一次比对永远不相等，于是第一次补丁成功、之后每次都退回整份重设。
 */
function styleSignature(doc) {
  return Array.from(doc.querySelectorAll('style'))
    .filter((el) => el.id !== HIGHLIGHT_STYLE_ID)
    .map((el) => el.textContent || '')
    .join('\n')
}

/** `.presentation` 上的 data-palette / data-layout / data-density。 */
function attributeSignature(el) {
  return Array.from(el.attributes || [])
    .map((attr) => `${attr.name}=${attr.value}`)
    .sort()
    .join('|')
}

/**
 * 把 `.presentation` 的子元素按页切分。
 * 一个 `[data-node-id]` 开启新的一页，其后的无标记兄弟节点（讲稿折叠区）归它。
 */
function collectPageUnits(root) {
  const units = []
  for (const child of Array.from(root.children)) {
    const id = child.getAttribute?.(PAGE_ATTR)
    if (id) {
      units.push({ id, nodes: [child] })
    } else if (units.length) {
      units[units.length - 1].nodes.push(child)
    }
  }
  return units
}

/**
 * 比对用的页指纹 —— 与逐字序列化相比，只多摘掉讲稿折叠区的展开态。
 *
 * `open` 是教师当下的临时视图（他自己点开的），不是这页的内容。不摘掉的话：
 * 展开着讲稿的那页在每次修改后都会被判成「变了」而重新替换一遍，白闪一次。
 */
function unitSignature(unit) {
  return unit.nodes
    .map((node) => {
      if (node.tagName !== 'DETAILS') return node.outerHTML
      const clone = node.cloneNode(true)
      clone.removeAttribute('open')
      return clone.outerHTML
    })
    .join('')
}

/**
 * 就地替换一页。
 *
 * 折叠态的处理：`<details>` 的展开与否是教师的临时视图，不该因为改一页就折回去。
 * 反过来，当**只有讲稿变了、幻灯片一字未动**时（局部修改默认就只重写 script /
 * segments，它们不上幻灯片），就替老师把讲稿摊开 —— 否则他看到的正是
 * 「对话说已更新，页面纹丝不动」。
 */
function replaceUnit(doc, liveUnit, nextUnit) {
  const wasOpen = liveUnit.nodes.some((node) => node.tagName === 'DETAILS' && node.open)
  const slideChanged = liveUnit.nodes[0].outerHTML !== nextUnit.nodes[0].outerHTML
  const unfold = !slideChanged && !wasOpen
  const imported = nextUnit.nodes.map((node) => doc.importNode(node, true))
  imported.forEach((node) => {
    if (node.tagName === 'DETAILS' && (wasOpen || unfold)) node.open = true
  })
  liveUnit.nodes[0].replaceWith(...imported)
  liveUnit.nodes.slice(1).forEach((node) => node.remove())
}

/**
 * 高亮样式注入预览文档自身 —— SFC 的 scoped 样式进不了 iframe，
 * 而把这条规则写进引擎的 `_wrap_html` 会污染导出产物。
 */
function ensureHighlightStyle(doc) {
  if (doc.getElementById(HIGHLIGHT_STYLE_ID)) return
  const style = doc.createElement('style')
  style.id = HIGHLIGHT_STYLE_ID
  style.textContent = HIGHLIGHT_CSS
  ;(doc.head || doc.documentElement)?.appendChild(style)
}

function highlightPages(doc, nodeIds) {
  if (!nodeIds.length) return
  ensureHighlightStyle(doc)
  nodeIds.forEach((id) => {
    const slide = doc.querySelector(`.slide[${PAGE_ATTR}="${escapeAttr(id)}"]`)
    if (!slide) return
    slide.classList.remove(HIGHLIGHT_CLASS)
    // 强制回流，让同一页连续两次修改都能重新播放动画
    void slide.offsetWidth
    slide.classList.add(HIGHLIGHT_CLASS)
    setTimeout(() => slide.classList.remove(HIGHLIGHT_CLASS), HIGHLIGHT_MS)
  })
}

function escapeAttr(value) {
  return String(value).replace(/["\\]/g, '\\$&')
}

/**
 * 把新渲染的 HTML 补进已加载的预览 iframe。
 *
 * @param {HTMLIFrameElement} iframeEl 预览 iframe（走 srcdoc，否则拿不到 document）
 * @param {string} newHtml 引擎刚渲染出的整份 HTML
 * @param {string[]} [changedNodeIds] 已知变更的页；留空则逐页比对 HTML（更准，也省得调方透传）
 * @returns {{ mode: 'patch'|'srcdoc', patched: string[] }}
 */
export function patchPreview(iframeEl, newHtml, changedNodeIds = []) {
  const fallback = { mode: PATCH_MODE.SRCDOC, patched: [] }
  const doc = contentDocumentOf(iframeEl)
  if (!doc || !newHtml) return fallback

  let next
  try {
    next = new DOMParser().parseFromString(newHtml, 'text/html')
  } catch {
    return fallback
  }

  const liveRoot = doc.querySelector(PRESENTATION_SELECTOR)
  const nextRoot = next.querySelector(PRESENTATION_SELECTOR)
  if (!liveRoot || !nextRoot) return fallback

  // 样式层变了 → 只换页会与新样式脱节，整份重设
  if (styleSignature(doc) !== styleSignature(next)) return fallback
  if (attributeSignature(liveRoot) !== attributeSignature(nextRoot)) return fallback

  const liveUnits = collectPageUnits(liveRoot)
  const nextUnits = collectPageUnits(nextRoot)
  if (!liveUnits.length || liveUnits.length !== nextUnits.length) return fallback
  if (liveUnits.some((unit, index) => unit.id !== nextUnits[index].id)) return fallback

  const wanted = new Set((changedNodeIds || []).map(String).filter(Boolean))
  const patched = []
  nextUnits.forEach((nextUnit, index) => {
    const liveUnit = liveUnits[index]
    const changed = wanted.size
      ? wanted.has(nextUnit.id)
      : unitSignature(liveUnit) !== unitSignature(nextUnit)
    if (!changed) return
    replaceUnit(doc, liveUnit, nextUnit)
    patched.push(nextUnit.id)
  })

  // 收敛自检：换完再比一次。仍有差异说明补丁没真正生效（导入失败、序列化对不上…），
  // 这时绝不能当作成功 —— 否则预览会停在旧内容上，而对话已经报了「已更新」。
  // 退回整份重设，慢一点但一定是对的。
  const settled = collectPageUnits(liveRoot)
  const unconverged = nextUnits.some((nextUnit, index) => {
    if (wanted.size && !wanted.has(nextUnit.id)) return false
    const unit = settled[index]
    return !unit || unit.id !== nextUnit.id || unitSignature(unit) !== unitSignature(nextUnit)
  })
  if (unconverged) return fallback

  highlightPages(doc, patched)
  return { mode: PATCH_MODE.PATCH, patched }
}

export default patchPreview
