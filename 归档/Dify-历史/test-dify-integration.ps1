$ErrorActionPreference = "Stop"

Write-Host "`n========================================`n  Dify 集成完整性测试`n========================================`n" -ForegroundColor Green

Write-Host "[1/5] 检查后端是否运行..." -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "http://localhost:18080/health" -TimeoutSec 8
    Write-Host "✓ 后端健康检查：$($health.status)" -ForegroundColor Green
} catch {
    Write-Host "✗ 后端不可达：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "`n[2/5] 检查 Dify 服务是否运行..." -ForegroundColor Cyan
try {
    $difyHealth = Invoke-RestMethod -Uri "http://127.0.0.1:18001/health" -TimeoutSec 8
    Write-Host "✓ Dify 健康检查：$($difyHealth.status)，版本：$($difyHealth.version)" -ForegroundColor Green
} catch {
    Write-Host "✗ Dify 不可达：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "`n[3/5] 检查配置文件..." -ForegroundColor Cyan
if ((Test-Path ".env") -and (Select-String "APP_AI_USE_DIFY" .env)) {
    Write-Host "✓ .env 配置文件有效" -ForegroundColor Green
} else {
    Write-Host "✗ .env 配置不完整" -ForegroundColor Red
    exit 1
}

Write-Host "`n[4/5] 验证 DifyClient 编译..." -ForegroundColor Cyan
if ((Test-Path "backend/internal/service/dify_client.go")) {
    $lineCount = (Get-Content "backend/internal/service/dify_client.go" | Measure-Object -Line).Lines
    Write-Host "✓ dify_client.go 存在 ($lineCount 行代码)" -ForegroundColor Green
} else {
    Write-Host "✗ dify_client.go 不存在" -ForegroundColor Red
    exit 1
}

Write-Host "`n[5/5] 检查已编译的二进制..." -ForegroundColor Cyan
if ((Test-Path "backend/api.exe")) {
    $size = (Get-Item "backend/api.exe").Length / 1MB
    Write-Host "✓ api.exe 编译成功 ($('{0:N2}' -f $size) MB)" -ForegroundColor Green
} else {
    Write-Host "✗ api.exe 不存在，需要运行：cd backend && go build ./api" -ForegroundColor Red
    exit 1
}

Write-Host "`n========================================`n  所有检查都通过！`n========================================`n" -ForegroundColor Green

Write-Host "后续步骤：`n" -ForegroundColor Yellow
Write-Host "1. 启用 Dify：编辑 .env，设置 APP_AI_USE_DIFY=true`n" -ForegroundColor Yellow
Write-Host "2. 设置 API Key：APP_AI_DIFY_API_KEY=<从 Dify console 获取>`n" -ForegroundColor Yellow
Write-Host "3. 重启后端（杀死当前进程，重新运行）`n" -ForegroundColor Yellow
Write-Host "4. 测试 API 调用：`n" -ForegroundColor Yellow
Write-Host "   POST http://localhost:18080/api/v1/ai/coursewares/test/ask`n" -ForegroundColor Yellow
Write-Host "   {`n" -ForegroundColor Yellow
Write-Host "     `"studentId`": `"test`",`n" -ForegroundColor Yellow
Write-Host "     `"pageNum`": 1,`n" -ForegroundColor Yellow
Write-Host "     `"nodeId`": `"test_node`",`n" -ForegroundColor Yellow
Write-Host "     `"question`": `"这是什么意思?`"`n" -ForegroundColor Yellow
Write-Host "   }`n" -ForegroundColor Yellow
