// 修复 PPT 预览 404：清除过期的 MinIO 签名 URL，让后端走 RasterPagePreview 渲染
import { execSync } from 'child_process'

// 1. 验证 MinIO 健康
try {
  const resp = await fetch('http://127.0.0.1:29000/minio/health/live', { signal: AbortSignal.timeout(5000) })
  console.log('MinIO 健康检查:', resp.status)
} catch (e) {
  console.log('MinIO 健康检查失败:', e.message)
}

// 2. 清除 DB 中过期的签名 URL
try {
  const result = execSync(
    `"C:\\Program Files\\PostgreSQL\\16\\bin\\psql.exe" -h localhost -p 25432 -U postgres -d teaching_test -c "UPDATE course_pages SET image_url = '' WHERE image_url LIKE '%X-Amz%' OR image_url LIKE '%29000%';"`,
    { env: { ...process.env, PGPASSWORD: '123456' }, timeout: 10000 }
  )
  console.log('DB 清理:', result.toString().trim())
} catch (e) {
  console.log('DB 清理失败（可能已清理）:', (e.stderr || e.message).toString().split('\n')[0])
}

// 3. 验证预览接口
try {
  const resp = await fetch('http://localhost:8082/api/courseware/3be64dfe-5ef7-4a6b-a0c7-0635fd69d6d4/page/1', { redirect: 'manual' })
  const ct = resp.headers.get('content-type') || ''
  const buf = await resp.arrayBuffer()
  console.log(`预览接口: HTTP ${resp.status}, Content-Type: ${ct}, Size: ${buf.byteLength}`)
  if (resp.status === 200 && ct.includes('image/png') && buf.byteLength > 500) {
    console.log('✅ PPT 预览正常，返回 PNG 图片')
  } else if (resp.status === 302) {
    console.log('⚠️  仍返回 302 重定向，可能还有残留的签名 URL')
  } else {
    console.log(`⚠️  异常响应: ${resp.status}`)
  }
} catch (e) {
  console.log('预览接口测试失败:', e.message)
}