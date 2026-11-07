// S1 意图面板浏览器端到端验收 —— 用真实 Chrome 驱动完整链路
//   浏览器 → Go 网关(8082) → Python AI 引擎(8000) → 模型端点(8899)
//
// 关键：**防 mock 断言**。前端在 Go 后端不可达时会静默切到 mockBackend，
// 那样看到的会是假数据。因此这里抓取浏览器真实发出的 /intent/extract 响应体，
// 校验其中带 engine / used_fallback / normalization_notes —— mock 返回体没有这些字段。
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// 仓库根目录 = 本脚本所在目录的上一级；截图输出到 <repo>/记录/screenshots
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

// playwright-core 解析：仓库根没有 package.json，静态 import 在本目录解析不到。
// 这里按候选顺序动态加载，找不到时给出明确的安装指引。
async function loadChromium() {
  const candidates = [
    process.env.PLAYWRIGHT_CORE,
    'playwright-core',
    path.join(REPO_ROOT, 'node_modules', 'playwright-core', 'index.js'),
    path.join(REPO_ROOT, 'frontend', 'teacher', 'node_modules', 'playwright-core', 'index.js'),
  ].filter(Boolean)
  const tried = []
  for (const spec of candidates) {
    try {
      const mod = await import(spec)
      if (mod.chromium) return mod.chromium
      tried.push(`${spec} (无 chromium 导出)`)
    } catch (e) {
      tried.push(`${spec} (${e.code || e.message})`)
    }
  }
  throw new Error(
    '找不到 playwright-core。请先安装：\n' +
      '  npm i -D playwright-core\n' +
      '或用环境变量指定已安装位置：\n' +
      '  set PLAYWRIGHT_CORE=<playwright-core 的 index.js 绝对路径>\n' +
      '已尝试：\n  ' + tried.join('\n  ')
  )
}

const chromium = await loadChromium()

const FRONT = process.env.FRONT || 'http://127.0.0.1:5173'
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const OUT = process.env.OUT || path.join(REPO_ROOT, '记录', 'screenshots')
const FIXED = '请帮我做一节45分钟的冒泡排序与快速排序课件，面向大一计算机专业学生，教师要求包含互动选择题。'

fs.mkdirSync(OUT, { recursive: true })

const results = []
const check = (label, ok, detail = '') => {
  results.push({ ok, label, detail })
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? '  —— ' + detail : ''}`)
}

const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } })

// 注入登录态（后端 S1 轻量模式无鉴权路由，前端路由守卫只看 localStorage）
await page.addInitScript(() => {
  localStorage.setItem('fuww_teacher_logged_in', '1')
  localStorage.setItem('fuww_teacher_username', 'szh')
  localStorage.setItem('fuww_teacher_role', 'teacher')
})

const consoleErrors = []
page.on('console', (m) => {
  if (m.type() === 'error') {
    const loc = m.location() || {}
    consoleErrors.push({ text: m.text(), url: loc.url || '', line: loc.lineNumber })
  }
})

// 抓取真实的意图提取请求与响应
let intentResponse = null
let intentUrl = ''
page.on('response', async (resp) => {
  if (resp.url().includes('/api/v1/intent/extract')) {
    intentUrl = resp.url()
    try { intentResponse = await resp.json() } catch { intentResponse = null }
  }
})

console.log('\n[步骤 1] 打开教师端 S1 意图页面')
await page.goto(`${FRONT}/courseware/create/s1-intent`, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForTimeout(1500)
console.log('  标题:', await page.title())

const textarea = page.locator('textarea').first()
await textarea.waitFor({ state: 'visible', timeout: 30000 })
console.log('  输入框占位符:', await textarea.getAttribute('placeholder'))
await page.screenshot({ path: `${OUT}/F01F02-01-S1页面初始.png`, fullPage: false })

console.log('\n[步骤 2] 输入团队固定主样例并发送')
await textarea.fill(FIXED)
await page.screenshot({ path: `${OUT}/F01F02-02-已输入样例.png` })
await page.locator('button.send-button').click()

console.log('\n[步骤 3] 等待意图解析结果')
await page.waitForTimeout(1000)
// 等"核心知识点"区域出现真实内容
await page.waitForFunction(() => {
  const t = document.body.innerText
  return t.includes('核心知识点') && (t.includes('冒泡排序') || t.includes('快速排序'))
}, { timeout: 60000 }).catch(() => console.log('  (等待超时，继续取证)'))
await page.waitForTimeout(2500)

const bodyText = await page.evaluate(() => document.body.innerText)
await page.screenshot({ path: `${OUT}/F01F02-03-意图解析结果.png`, fullPage: true })

console.log('\n[步骤 4] 网络层取证 —— 确认不是 mock')
console.log('  请求 URL:', intentUrl)
check('请求确实打到 Go 网关 :8082', intentUrl.includes(':8082'), intentUrl)

const data = intentResponse?.data ?? intentResponse ?? {}
check('响应含 engine 字段（mock 返回体没有，证明来自真实后端）',
  typeof data.engine === 'string' && data.engine.length > 0, `engine=${data.engine}`)
check('响应含 used_fallback 字段（mock 返回体没有）',
  typeof data.used_fallback === 'boolean', `used_fallback=${data.used_fallback}`)
check('响应含 normalization_notes（F01 可观测字段，mock 没有）',
  Array.isArray(data.normalization_notes), `notes=${JSON.stringify(data.normalization_notes)}`)
check('模型路径生效（非规则兜底）',
  data.used_fallback === false && data.engine === 'LLMIntentEngine',
  `engine=${data.engine} used_fallback=${data.used_fallback}`)

console.log('\n[步骤 5] 页面呈现断言')
const s = data.intent_summary ?? {}
check('页面显示主题为冒泡排序与快速排序',
  bodyText.includes('冒泡排序与快速排序'), `topic=${s.topic}`)
check('页面显示时长 45 分钟', bodyText.includes('45'), `duration=${s.duration_minutes}`)
check('核心知识点显示 冒泡排序', bodyText.includes('冒泡排序'), `kp=${JSON.stringify(s.knowledge_points)}`)
check('核心知识点显示 快速排序', bodyText.includes('快速排序'), `kp=${JSON.stringify(s.knowledge_points)}`)
check('互动要求未污染知识点（页面无"互动选择题"作为知识点）',
  !s.knowledge_points?.some((k) => String(k).includes('互动')), `kp=${JSON.stringify(s.knowledge_points)}`)
check('接口层知识点精确等于 [冒泡排序, 快速排序]',
  JSON.stringify(s.knowledge_points) === JSON.stringify(['冒泡排序', '快速排序']),
  `实际=${JSON.stringify(s.knowledge_points)}`)
check('with_interactive 为真（互动练习被正确识别为独立字段）',
  s.with_interactive === true, `with_interactive=${s.with_interactive}`)

console.log('\n[步骤 6] 控制台错误')
// 已知的良性 404（与 F01/F02 无关，属既有环境问题）：
//   /api/health —— 前端健康检查先试 /api/health 再试 /health，而 Go 的 S1 轻量模式只注册了 /health
//   /favicon.ico —— dev server 的 public/ 下没有 favicon.ico，浏览器自动请求
const BENIGN = /\/api\/health|\/favicon\.ico/
const realErrors = consoleErrors.filter((e) => !BENIGN.test(e.url))
const benignErrors = consoleErrors.filter((e) => BENIGN.test(e.url))
if (benignErrors.length) {
  console.log(`  (已知良性 404 ${benignErrors.length} 条：${[...new Set(benignErrors.map(e => e.url))].join(' , ')})`)
}
check('无其它控制台错误', realErrors.length === 0,
  realErrors.slice(0, 3).map((e) => `${e.text} @ ${e.url}`).join(' | '))

console.log('\n===== 页面核心知识点区域原文 =====')
const kpIdx = bodyText.indexOf('核心知识点')
if (kpIdx >= 0) console.log(bodyText.slice(kpIdx, kpIdx + 200))
console.log('\n===== human_summary =====')
console.log(data.human_summary ?? '(无)')

await browser.close()

const pass = results.filter((r) => r.ok).length
const fail = results.filter((r) => !r.ok)
console.log('\n' + '='.repeat(70))
console.log(`浏览器验收：${pass} 通过 / ${fail.length} 不通过 / 共 ${results.length} 项`)
if (fail.length) {
  console.log('不通过项：')
  fail.forEach((r) => console.log(`  - ${r.label}  ${r.detail}`))
}
process.exit(fail.length ? 1 : 0)
