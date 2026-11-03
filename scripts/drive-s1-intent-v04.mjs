// S1 意图面板浏览器端到端验收 —— 三态来源可观测性（V04）
//   浏览器 → Go 网关(8082) → Python AI 引擎(8000/8020) → 模型端点(8899)
//
// 目标：在**真实浏览器**里确认三件事
//   1) 真实模型路径：界面不出现任何降级提示，知识点正确
//   2) 规则兜底路径（模型不可达）：界面明确提示"本地规则提取"
//   3) 前端 mock 路径（后端不可达）：界面明确提示"未接入真实模型"
//
// 防 mock 断言：抓取浏览器真实发出的 /intent/extract 响应体，
// 校验其中带 engine / used_fallback / model_source —— 旧 mock 返回体没有这些字段。
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// 仓库根目录 = 本脚本所在目录的上一级；截图输出到 <repo>/记录/screenshots/v04
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
const SCENARIO = process.env.SCENARIO || 'real_model'
const OUT = process.env.OUT || path.join(REPO_ROOT, '记录', 'screenshots', 'v04')
const FIXED = '请帮我做一节45分钟的冒泡排序与快速排序课件，面向大一计算机专业学生，教师要求包含互动选择题。'

fs.mkdirSync(OUT, { recursive: true })

const results = []
const check = (label, ok, detail = '') => {
  results.push({ ok, label, detail })
  console.log(`  [${ok ? 'PASS' : 'FAIL'}] ${label}${detail ? '  —— ' + detail : ''}`)
}

const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } })

// 注意：init script 在浏览器上下文执行，不能读 process.env，必须用参数传入。
await page.addInitScript((mockMode) => {
  localStorage.setItem('fuww_teacher_logged_in', '1')
  localStorage.setItem('fuww_teacher_username', 'szh')
  localStorage.setItem('fuww_teacher_role', 'teacher')
  // mock_frontend 场景：显式置位 mock 标志。
  // 配合 VITE_API_BASE 指向不可达端口，isBackendReachable() 探测失败 → 保持 mock 模式。
  if (mockMode) {
    localStorage.setItem('fuww_mock_mode', 'true')
  }
}, SCENARIO === 'mock_frontend')

const consoleErrors = []
page.on('console', (m) => {
  if (m.type() === 'error') {
    const loc = m.location() || {}
    consoleErrors.push({ text: m.text(), url: loc.url || '' })
  }
})

let intentResponse = null
let intentUrl = ''
page.on('response', async (resp) => {
  if (resp.url().includes('/intent/extract')) {
    intentUrl = resp.url()
    try { intentResponse = await resp.json() } catch { intentResponse = null }
  }
})

console.log(`\n===== 场景：${SCENARIO} =====`)
console.log('[步骤 1] 打开教师端 S1 意图页面')
await page.goto(`${FRONT}/courseware/create/s1-intent`, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForTimeout(1500)

const textarea = page.locator('textarea').first()
await textarea.waitFor({ state: 'visible', timeout: 30000 })

console.log('[步骤 2] 输入团队固定主样例并发送')
await textarea.fill(FIXED)
await page.screenshot({ path: `${OUT}/${SCENARIO}-02-已输入.png` })
await page.locator('button.send-button').click()

console.log('[步骤 3] 等待意图解析结果')
await page.waitForTimeout(1200)
await page.waitForFunction(() => {
  const t = document.body.innerText
  return t.includes('核心知识点') && (t.includes('冒泡排序') || t.includes('快速排序') || t.includes('知识点待补充'))
}, { timeout: 60000 }).catch(() => console.log('  (等待超时，继续取证)'))
await page.waitForTimeout(2500)

const bodyText = await page.evaluate(() => document.body.innerText)
await page.screenshot({ path: `${OUT}/${SCENARIO}-03-结果.png`, fullPage: true })

console.log('[步骤 4] 网络层取证')
const data = intentResponse?.data ?? intentResponse ?? {}
console.log('  请求 URL:', intentUrl || '(无 /intent/extract 请求)')
console.log('  model_source =', JSON.stringify(data.model_source))
console.log('  engine =', JSON.stringify(data.engine))
console.log('  used_fallback =', JSON.stringify(data.used_fallback))
console.log('  degraded =', JSON.stringify(data.degraded), '(类型:', typeof data.degraded, ')')
console.log('  fallback_reason =', JSON.stringify(data.fallback_reason))
console.log('  normalization_notes =', JSON.stringify(data.normalization_notes))

const s = data.intent_summary ?? {}

if (SCENARIO === 'real_model') {
  check('请求确实打到 Go 网关', intentUrl.includes(':8082'), intentUrl)
  check('model_source === "real_model"',
    data.model_source === 'real_model', `model_source=${data.model_source}`)
  check('degraded 为布尔 false（字段存在，不是 undefined）',
    typeof data.degraded === 'boolean' && data.degraded === false,
    `degraded=${JSON.stringify(data.degraded)} 类型=${typeof data.degraded}`)
  check('used_fallback === false', data.used_fallback === false, `used_fallback=${data.used_fallback}`)
  check('engine === LLMIntentEngine（真实模型引擎，非规则兜底）',
    data.engine === 'LLMIntentEngine', `engine=${data.engine}`)
  check('知识点未被"互动选择题"污染',
    !s.knowledge_points?.some((k) => String(k).includes('互动')),
    `kp=${JSON.stringify(s.knowledge_points)}`)
  check('界面无"当前使用本地规则提取"提示',
    !bodyText.includes('当前使用本地规则提取'), '')
  check('界面无"未接入真实模型"提示',
    !bodyText.includes('未接入真实模型'), '')
  check('完整度为 100%', String(data.completion_pct) === '100', `completion_pct=${data.completion_pct}`)
  check('知识点精确等于 [冒泡排序, 快速排序]',
    JSON.stringify(s.knowledge_points) === JSON.stringify(['冒泡排序', '快速排序']),
    `实际=${JSON.stringify(s.knowledge_points)}`)
}

if (SCENARIO === 'rule_fallback') {
  check('model_source === "rule_fallback"',
    data.model_source === 'rule_fallback', `model_source=${data.model_source}`)
  check('used_fallback === true', data.used_fallback === true, `used_fallback=${data.used_fallback}`)
  check('degraded === true', data.degraded === true, `degraded=${data.degraded}`)
  check('fallback_reason 非空（给出真实降级根因）',
    typeof data.fallback_reason === 'string' && data.fallback_reason.length > 0,
    `fallback_reason=${data.fallback_reason}`)
  check('界面明确提示"当前使用本地规则提取"',
    bodyText.includes('当前使用本地规则提取'),
    bodyText.includes('当前使用本地规则提取') ? '已显示' : '未显示')
  // 防插值缺陷：JS 模板字符串里若误用 Vue 的 {{ }}，界面会原样显示 "{{ ... }}"
  check('提示语已完成真实插值（不含未渲染的 {{ }} 模板残留）',
    !bodyText.includes('{{') && !bodyText.includes('}}'),
    bodyText.includes('{{') ? '界面存在未渲染的模板语法' : '无残留')
  check('提示语包含具体降级原因文案（AI 服务返回异常）',
    bodyText.includes('AI 服务返回异常'),
    bodyText.includes('AI 服务返回异常') ? '已显示' : '未显示具体原因')
  check('界面未误报"未接入真实模型"（模型确实接了，是调用失败）',
    !bodyText.includes('未接入真实模型'), '')
}

if (SCENARIO === 'mock_frontend') {
  check('界面明确提示"当前未接入真实模型"',
    bodyText.includes('未接入真实模型'),
    bodyText.includes('未接入真实模型') ? '已显示' : '未显示')
  check('界面未误报"当前使用本地规则提取"',
    !bodyText.includes('当前使用本地规则提取'), '')
}

console.log('[步骤 5] 控制台错误')
// 已知良性噪声（与 F01/F02 及本次可观测性修复无关）：
//   /api/health —— 前端健康检查先试 /api/health 再试 /health，而 Go 的 S1 轻量模式只注册了 /health
//   /favicon.ico —— dev server 的 public/ 下没有 favicon.ico，浏览器自动请求
//   ERR_CONNECTION_REFUSED —— 仅 mock_frontend 场景：后端被**故意**指向不可达端口以触发离线回退，
//                              这正是该场景的测试前提，属预期噪声而非缺陷。
const BENIGN = /\/api\/health|\/favicon\.ico/
const SCENARIO_BENIGN = SCENARIO === 'mock_frontend' ? /ERR_CONNECTION_REFUSED/ : /$^/
const realErrors = consoleErrors.filter((e) => !BENIGN.test(e.url) && !SCENARIO_BENIGN.test(e.text))
const benignErrors = consoleErrors.filter((e) => BENIGN.test(e.url) || SCENARIO_BENIGN.test(e.text))
if (benignErrors.length) {
  console.log(`  (已知良性噪声 ${benignErrors.length} 条：${[...new Set(benignErrors.map(e => e.url || e.text))].join(' , ')})`)
}
check('无其它控制台错误', realErrors.length === 0,
  realErrors.slice(0, 3).map((e) => `${e.text} @ ${e.url}`).join(' | '))

console.log('\n===== 界面提示区域原文 =====')
const noteIdx = bodyText.indexOf('当前使用本地规则提取')
const mockIdx = bodyText.indexOf('未接入真实模型')
if (noteIdx >= 0) console.log('  [规则兜底提示]', bodyText.slice(noteIdx, noteIdx + 70))
if (mockIdx >= 0) console.log('  [未接模型提示]', bodyText.slice(mockIdx, mockIdx + 70))
if (noteIdx < 0 && mockIdx < 0) console.log('  （无任何降级提示 —— 真实模型路径符合预期）')

await browser.close()

const pass = results.filter((r) => r.ok).length
const fail = results.filter((r) => !r.ok)
console.log('\n' + '='.repeat(70))
console.log(`浏览器验收[${SCENARIO}]：${pass} 通过 / ${fail.length} 不通过 / 共 ${results.length} 项`)
if (fail.length) {
  console.log('不通过项：')
  fail.forEach((r) => console.log(`  - ${r.label}  ${r.detail}`))
}
process.exit(fail.length ? 1 : 0)
