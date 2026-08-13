// 驱动 S3 证据透传链路验证脚本（成员B）
// 用已安装的 Chrome 以 headless 方式跑通：
//   login 态 → S3Studio 演示模式 → 注入证据包 → AI 生成 → 校验讲稿含证据上下文
import { chromium } from 'playwright-core'

const BASE = 'http://localhost:5173'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'

const evidencePacket = {
  query: '二次函数图像特征',
  relevant_chunks: [
    {
      chunk_id: 'chunk_001',
      content: '二次函数 y=ax²+bx+c 的图像是一条抛物线，开口方向由 a 决定。',
      source_type: 'pdf',
      page_ref: 3,
      seq_index: 0
    },
    {
      chunk_id: 'chunk_002',
      content: '顶点坐标为 (-b/2a, (4ac-b²)/4a)，对称轴为 x=-b/2a。',
      source_type: 'pdf',
      page_ref: 4,
      seq_index: 1
    }
  ],
  synthesized_context: '基于检索到的 2 段相关资料，综合整理出与二次函数图像特征相关的内容要点。',
  citations: [
    { chunk_id: 'chunk_001', text_snippet: '二次函数 y=ax²+bx+c 的图像是一条...', source_ref: '函数与导数基础.pdf' }
  ]
}

const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1400, height: 900 } })

const consoleErrors = []
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})

let aiGenerateRequest = null
let aiGenerateResponse = null
page.on('request', (req) => {
  if (req.url().includes('/ai-generate') && req.method() === 'POST') {
    aiGenerateRequest = { url: req.url(), postData: req.postData() }
  }
})
page.on('response', (resp) => {
  if (resp.url().includes('/ai-generate')) {
    resp.text().then((t) => { aiGenerateResponse = t }).catch(() => {})
  }
})

// 1. 预置登录态 + 证据包
await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
await page.evaluate((pkt) => {
  localStorage.setItem('fuww_teacher_logged_in', '1')
  localStorage.setItem('fuww_teacher_username', 'demo_teacher')
  localStorage.setItem('fuww_teacher_role', 'teacher')
  localStorage.setItem('fuww_s2_evidence_packet', JSON.stringify(pkt))
}, evidencePacket)

// 2. 进入 S3Studio
await page.goto(`${BASE}/courseware/create/s3-studio`, { waitUntil: 'networkidle' })
await page.waitForSelector('.s3-welcome', { timeout: 10000 })
console.log('[1] S3Studio 欢迎页已加载')

// 3. 加载真实课件（mock store 中的种子课件 cw_demo_001，走真实 S2→S3 链路）
await page.fill('.s3-course-id-input', 'cw_demo_001')
await page.click('text=加载课件')
await page.waitForSelector('.s3-toolbar', { timeout: 10000 })
console.log('[2] 已加载课件 cw_demo_001')

// 4. 点击 AI 生成脚本（触发 handleGenerateAIScript）
await page.click('text=AI 生成脚本')
await page.waitForTimeout(3500)

// 5. 校验讲稿内容（数据层面：generationStore.currentScript —— 生成接口返回的整篇讲稿）
const scriptText = await page.evaluate(() => {
  const ta = document.querySelector('.linked-editor')
  return ta ? ta.value : ''
})
// generationStore 实例可从 vue app 的 pinia 获取；这里直接读 store 的更可靠路径：
// 生成后 content 已写入 mock 持久化存储，且 S3StudioPage loadScriptAndNodes 会把它 set 到 currentScript。
// 用页面 window 上暴露的 pinia 实例（main.js 若未暴露则退化为读 DOM + mock 存储）。
const currentScriptText = await page.evaluate(async () => {
  const m = await import('/src/services/v1/mockBackend.js')
  const raw = localStorage.getItem('fuww_teacher_demo_backend_v1')
  const store = JSON.parse(raw)
  return store?.teacher?.scriptsByCourse?.cw_demo_001?.['1']?.content || ''
})
const hasEvidence = currentScriptText.includes('证据上下文') && currentScriptText.includes('参考资料')
const hasSynthesized = currentScriptText.includes(evidencePacket.synthesized_context.slice(0, 20))
const hasChunkSnippet = currentScriptText.includes('开口方向由 a 决定')
console.log(`   整篇讲稿 content(前300字符): ${currentScriptText.slice(0, 300).replace(/\n/g, '\\n')}`)

console.log(`[3] 讲稿含「证据上下文/参考资料」: ${hasEvidence}`)
console.log(`[4] 含 synthesized_context 片段: ${hasSynthesized}`)
console.log(`[5] 含 relevant_chunks 片段: ${hasChunkSnippet}`)

// 6b. 验证生成后 mock 持久化存储中该页 content 是否包含证据上下文（S3→S4 实际消费的数据）
const storeProbe = await page.evaluate(() => {
  return (async () => {
    const m = await import('/src/services/v1/mockBackend.js')
    const raw = localStorage.getItem('fuww_teacher_demo_backend_v1')
    if (!raw) return { hasKey: false }
    const store = JSON.parse(raw)
    const page1 = store?.teacher?.scriptsByCourse?.cw_demo_001?.['1']
    return {
      hasKey: true,
      content: page1?.content || '',
      hasEvidence: !!(page1?.content || '').includes('证据上下文'),
      courseId: store?.teacher?.coursewares?.[0]?.id
    }
  })()
})
console.log('[6c] Mock 持久化存储 cw_demo_001 第1页 content:')
console.log('    hasEvidence:', storeProbe.hasEvidence)
console.log('    content 前 160 字符:', (storeProbe.content || '').slice(0, 160).replace(/\n/g, '\\n'))

// 6b. 直接从页面内调用 mock 处理器，验证路由是否命中 + 输出内容
const probe = await page.evaluate(async () => {
  const mod = await import('/src/services/v1/mockBackend.js')
  const pkt = JSON.parse(localStorage.getItem('fuww_s2_evidence_packet'))
  const resp = mod.handleMockRequest(
    '/api/v1/teacher/coursewares/cw_demo_001/scripts/ai-generate',
    { method: 'POST', body: JSON.stringify({ pageNum: 1, mode: 'llm', evidence: pkt }) },
    new Error('probe')
  )
  return {
    code: resp?.code,
    content: resp?.data?.content
  }
})
console.log('[6b] 直接调用 mock 处理器 → code:', probe.code)
console.log('    content 前 200 字符:', probe.content ? probe.content.slice(0, 200).replace(/\n/g, '\\n') : '(空)')
console.log('    含证据上下文:', probe.content ? probe.content.includes('证据上下文') : false)

// 6. localStorage 中证据包仍在
const pktStillThere = await page.evaluate(() => !!localStorage.getItem('fuww_s2_evidence_packet'))
console.log(`[6] localStorage 证据包仍在: ${pktStillThere}`)

console.log(`[7] 浏览器 console error 数: ${consoleErrors.length}`)
if (consoleErrors.length) {
  console.log('--- console errors ---')
  consoleErrors.slice(0, 5).forEach((e) => console.log(e))
}

console.log('[8] ai-generate 请求:', aiGenerateRequest ? aiGenerateRequest.postData : '(未捕获)')
console.log('[9] ai-generate 响应:', aiGenerateResponse ? aiGenerateResponse.slice(0, 300) : '(未捕获)')

const pass = hasEvidence && hasSynthesized && hasChunkSnippet && pktStillThere
console.log(`\n== ${pass ? 'PASS：证据透传链路验证通过' : 'FAIL：见上方检查项'} ==`)

// 截图留档
await page.screenshot({ path: 'scripts/s3-evidence-drive.png', fullPage: false })
await browser.close()
process.exit(pass ? 0 : 1)
