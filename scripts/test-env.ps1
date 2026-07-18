param(
    [ValidateSet('up', 'down', 'logs', 'ps')]
    [string]$Action = 'up'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'docker-compose.test.yml'
$envFile = Join-Path $root '.env.test'
$envExample = Join-Path $root '.env.test.example'

if (-not (Test-Path $envFile)) {
    if (-not (Test-Path $envExample)) {
        throw "未找到 $envExample"
    }

    Copy-Item $envExample $envFile
    Write-Host "已生成测试环境配置：$envFile"
}

$composeArgs = @('--env-file', $envFile, '-f', $composeFile)

switch ($Action) {
    'up' {
        docker compose @composeArgs up -d --build
    }
    'down' {
        docker compose @composeArgs down -v
    }
    'logs' {
        docker compose @composeArgs logs -f
    }
    'ps' {
        docker compose @composeArgs ps
    }
}