// 驱动 S2 知识库 RAG 面板验证（成员B）v2
// 目标：验证「索引知识库」把前端已解析切片文本灌入后端后，RAG 检索能命中默认素材
// 路径：login 态 → /courseware/create/s2-material → 索引 → 检索「函数的定义域」
import { chromium } from 'playwright-core'

const BASE = 'http://localhost:5173'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'

const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } })

const consoleErrors = []
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})

const ragRequests = []
page.on('request', (req) => {
  if (/rag\/(search|evidence)|knowledge\/upload/i.test(req.url())) {
    let body = null
    try { body = req.postData() } catch (e) {}
    ragRequests.push({ url: req.url(), method: req.method(), body })
  }
})
const ragResponses = []
page.on('response', async (resp) => {
  if (/rag\/(search|evidence)|knowledge\/upload/i.test(resp.url())) {
    let text = ''
    try { text = await resp.text() } catch (e) { text = '(unreadable)' }
    ragResponses.push({ url: resp.url(), status: resp.status(), text: text.slice(0, 600) })
  }
})

// 1. 预置登录态
await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
await page.evaluate(() => {
  localStorage.setItem('fuww_teacher_logged_in', '1')
  localStorage.setItem('fuww_teacher_username', 'demo_teacher')
  localStorage.setItem('fuww_teacher_role', 'teacher')
  const sid = localStorage.getItem('fuww_s2_session_id') || `sess_s2_${Date.now().toString(36)}`
  localStorage.setItem('fuww_s2_session_id', sid)
  // 保留默认种子（含 mat_001/mat_002 的 7 个切片），不清空 mock store
})

// 2. 进入 S2 页面，等待素材加载
await page.goto(`${BASE}/courseware/create/s2-material`, { waitUntil: 'networkidle' })
await page.waitForTimeout(2000)
console.log('[1] S2 页面已加载')

// 3. 确认 store 里有多少素材/切片
const storeInfo = await page.evaluate(async () => {
  const m = await import('/src/services/v1/mockBackend.js')
  const raw = localStorage.getItem('fuww_teacher_demo_backend_v1')
  const store = JSON.parse(raw)
  const mats = store?.materials || []
  const chunkCount = mats.reduce((s, ma) => s + (ma.chunks || []).length, 0)
  return { materialCount: mats.length, chunkCount, firstTitle: mats[0]?.title }
})
console.log('[2] mock store 素材数:', storeInfo.materialCount, '| 切片数:', storeInfo.chunkCount, '|', storeInfo.firstTitle)

// 4. 点「索引知识库」
const idxBtn = page.locator('button:has-text("索引知识库")')
if (await idxBtn.count() > 0) {
  await idxBtn.click()
  await page.waitForTimeout(3500)
  console.log('[3] 已点击「索引知识库」')
} else {
  console.log('[3] 索引按钮未找到！')
}

// 5. 检索「函数的定义域」
const queryInput = page.locator('.search-input')
await queryInput.fill('函数的定义域')
await page.locator('button:has-text("检索")').first().click()
await page.waitForTimeout(3000)
console.log('[4] 已执行检索「函数的定义域」')

// 6. 读取结果
const resultState = await page.evaluate(() => {
  const items = document.querySelectorAll('.result-item')
  return {
    resultCount: items.length,
    items: Array.from(items).slice(0, 3).map((el) => ({
      score: el.querySelector('.score')?.textContent || '',
      content: el.querySelector('.result-content')?.textContent?.slice(0, 60) || ''
    })),
    emptyState: document.querySelector('.state-block')?.textContent?.trim() || '',
    statBadge: document.querySelector('.stat-badge')?.textContent || ''
  }
})
console.log('[5] 检索结果数:', resultState.resultCount)
resultState.items.forEach((it) => console.log('    ', it.score, it.content))
console.log('    空态提示:', resultState.emptyState)

// 7. 输出请求/响应
console.log('\n[6] RAG 请求:')
ragRequests.forEach((r) => {
  const path = r.url.split('/api/v1/')[1] || r.url
  console.log('   ', r.method, path, r.body?.slice(0, 140) || '')
})
console.log('\n[7] RAG 响应:')
ragResponses.forEach((r) => {
  const path = r.url.split('/api/v1/')[1] || r.url
  console.log('   ', r.status, path, r.text.slice(0, 260).replace(/\n/g, ' '))
})

console.log('\n[8] console error 数:', consoleErrors.length)
consoleErrors.slice(0, 4).forEach((e) => console.log('   ', e.slice(0, 160)))

await page.screenshot({ path: 'scripts/s2-rag-drive.png', fullPage: false })
await browser.close()
process.exit(0)
