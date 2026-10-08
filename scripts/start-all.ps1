param(
    [switch]$SkipDocker
)

$root = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $root "logs"
$tmpDir = Join-Path $root "tmp"
$scriptsDir = Join-Path $root "scripts"
$isWindowsHost = $env:OS -eq 'Windows_NT'

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
New-Item -ItemType Directory -Force -Path $tmpDir | Out-Null
New-Item -ItemType Directory -Force -Path $scriptsDir | Out-Null

# Load the project-level .env before applying defaults so every child process
# (especially the AI Engine) inherits the configured provider, model and key.
$envFile = Join-Path $root ".env"
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith('#')) {
            continue
        }

        if ($trimmed.StartsWith('export ')) {
            $trimmed = $trimmed.Substring(7).Trim()
        }

        $separator = $trimmed.IndexOf('=')
        if ($separator -le 0) {
            continue
        }

        $name = $trimmed.Substring(0, $separator).Trim()
        $value = $trimmed.Substring($separator + 1).Trim()
        if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
            continue
        }

        if ($value.Length -ge 2) {
            $first = $value[0]
            $last = $value[$value.Length - 1]
            if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
    Write-Host "Loaded environment: $envFile"
}

if ([string]::IsNullOrWhiteSpace($env:AI_BASE_URL) -or $env:AI_BASE_URL -match 'example\.com') {
    $env:AI_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
}

if ([string]::IsNullOrWhiteSpace($env:AI_MODEL) -or $env:AI_MODEL -match '^gpt-4o') {
    $env:AI_MODEL = 'qwen-plus'
}

if ([string]::IsNullOrWhiteSpace($env:AI_GEN_MODE)) {
    $env:AI_GEN_MODE = 'llm'
}

# Docker Compose maps Redis to host port 16379; keep explicit overrides available.
if ([string]::IsNullOrWhiteSpace($env:REDIS_HOST)) { $env:REDIS_HOST = '127.0.0.1' }
if ([string]::IsNullOrWhiteSpace($env:REDIS_PORT)) { $env:REDIS_PORT = '16379' }
if ([string]::IsNullOrWhiteSpace($env:REDIS_ENABLED)) { $env:REDIS_ENABLED = '1' }
if ([string]::IsNullOrWhiteSpace($env:RAG_STORE_BACKEND)) { $env:RAG_STORE_BACKEND = 'pgvector' }
if ([string]::IsNullOrWhiteSpace($env:AI_EMBEDDING_DIM)) { $env:AI_EMBEDDING_DIM = '512' }
if ([string]::IsNullOrWhiteSpace($env:DB_HOST)) { $env:DB_HOST = '127.0.0.1' }
if ([string]::IsNullOrWhiteSpace($env:DB_PORT)) { $env:DB_PORT = '15432' }

Write-Host "Root: $root"
Write-Host "AI provider: $($env:AI_BASE_URL) | model: $($env:AI_MODEL)"

function Resolve-CommandPath {
    param(
        [Parameter(Mandatory)]
        [string]$Command
    )

    $resolved = Get-Command $Command -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $resolved) {
        return $Command
    }

    if ($resolved.Path) {
        return $resolved.Path
    }

    if ($resolved.Source) {
        return $resolved.Source
    }

    return $Command
}

function Format-CmdInvokerArguments {
    param(
        [Parameter(Mandatory)]
        [string]$CommandPath,
        [Parameter(Mandatory)]
        [string[]]$ArgumentList
    )

    return @('/d', '/c', ('"' + $CommandPath + '"')) + $ArgumentList
}

function Invoke-DockerCompose {
    param(
        [Parameter(Mandatory)]
        [string[]]$ActionArgs
    )

    $composeFile = Join-Path $root "backend\docker-compose.yml"
    $envFile = Join-Path $root ".env"
    $composeBaseArgs = @("-f", $composeFile)

    if (Test-Path $envFile) {
        $composeBaseArgs += @("--env-file", $envFile)
    }

    $variants = @(
        @{ Cmd = "docker"; Args = @("compose") + $composeBaseArgs + $ActionArgs },
        @{ Cmd = "docker-compose"; Args = $composeBaseArgs + $ActionArgs }
    )

    foreach ($variant in $variants) {
        if (Get-Command $variant.Cmd -ErrorAction SilentlyContinue) {
            Write-Host "Running $($variant.Cmd) $($variant.Args -join ' ') ..."
            & $variant.Cmd @($variant.Args)
            if ($LASTEXITCODE -eq 0) {
                return
            }
            throw "Command '$($variant.Cmd) $($variant.Args -join ' ')' failed with exit code $LASTEXITCODE."
        }
    }

    throw "Neither 'docker' nor 'docker-compose' is available in PATH. Please install Docker CLI before running this script."
}

if (-not $SkipDocker) {
    Invoke-DockerCompose -ActionArgs @('up','-d','postgres','redis','minio')
}

$pids = @{}

function Test-EndpointReady {
    param(
        [Parameter(Mandatory)][string]$Url,
        [int]$RetryCount = 20,
        [int]$DelayMilliseconds = 1000
    )

    for ($attempt = 1; $attempt -le $RetryCount; $attempt++) {
        try {
            $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            return $true
        } catch {
            Start-Sleep -Milliseconds $DelayMilliseconds
        }
    }

    return $false
}

function Start-Background {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][string]$StdOut,
        [Parameter(Mandatory)][string]$StdErr
    )

    Write-Host "Starting $Name..."

    $resolvedFilePath = Resolve-CommandPath -Command $FilePath
    $startFilePath = $resolvedFilePath
    $startArgumentList = $ArgumentList
    $extension = [System.IO.Path]::GetExtension($resolvedFilePath).ToLowerInvariant()

    if ($isWindowsHost -and $extension -in @('.cmd', '.bat')) {
        $startFilePath = $env:ComSpec
        $startArgumentList = Format-CmdInvokerArguments -CommandPath $resolvedFilePath -ArgumentList $ArgumentList
    } elseif ($isWindowsHost -and $extension -eq '.ps1') {
        $batchFilePath = [System.IO.Path]::ChangeExtension($resolvedFilePath, '.cmd')

        if (Test-Path $batchFilePath) {
            $startFilePath = $env:ComSpec
            $startArgumentList = Format-CmdInvokerArguments -CommandPath $batchFilePath -ArgumentList $ArgumentList
        } else {
            $startFilePath = "powershell.exe"
            $startArgumentList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $resolvedFilePath) + $ArgumentList
        }
    }

    $startOptions = @{
        FilePath = $startFilePath
        ArgumentList = $startArgumentList
        WorkingDirectory = $WorkingDirectory
        PassThru = $true
        RedirectStandardOutput = $StdOut
        RedirectStandardError = $StdErr
    }
    if ($isWindowsHost) {
        $startOptions.WindowStyle = 'Hidden'
    } else {
        $startOptions.NoNewWindow = $true
    }
    $proc = Start-Process @startOptions
    Start-Sleep -Milliseconds 1200

    if ($proc -and -not $proc.HasExited -and $proc.Id) {
        $pids[$Name] = $proc.Id
        Write-Host "$Name started (PID $($proc.Id))"
    } else {
        $exitCode = $null
        if ($proc -and $proc.HasExited) {
            $exitCode = $proc.ExitCode
        }

        if ($null -ne $exitCode) {
            Write-Warning "Failed to start ${Name} (exit code $exitCode)"
        } else {
            Write-Warning "Failed to start $Name"
        }
    }
}

function Invoke-ProcessAndWait {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList,
        [Parameter(Mandatory)][string]$WorkingDirectory
    )

    $resolvedFilePath = Resolve-CommandPath -Command $FilePath
    $startFilePath = $resolvedFilePath
    $startArgumentList = $ArgumentList
    $extension = [System.IO.Path]::GetExtension($resolvedFilePath).ToLowerInvariant()

    if ($isWindowsHost -and $extension -in @('.cmd', '.bat')) {
        $startFilePath = $env:ComSpec
        $startArgumentList = Format-CmdInvokerArguments -CommandPath $resolvedFilePath -ArgumentList $ArgumentList
    } elseif ($isWindowsHost -and $extension -eq '.ps1') {
        $batchFilePath = [System.IO.Path]::ChangeExtension($resolvedFilePath, '.cmd')

        if (Test-Path $batchFilePath) {
            $startFilePath = $env:ComSpec
            $startArgumentList = Format-CmdInvokerArguments -CommandPath $batchFilePath -ArgumentList $ArgumentList
        } else {
            $startFilePath = 'powershell.exe'
            $startArgumentList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $resolvedFilePath) + $ArgumentList
        }
    }

    $proc = Start-Process -FilePath $startFilePath -ArgumentList $startArgumentList -WorkingDirectory $WorkingDirectory -NoNewWindow -PassThru -Wait
    return $proc.ExitCode
}

function Ensure-NodeDependencies {
    param(
        [Parameter(Mandatory)][string]$ProjectName,
        [Parameter(Mandatory)][string]$WorkingDirectory
    )

    $packageJson = Join-Path $WorkingDirectory 'package.json'
    if (-not (Test-Path $packageJson)) {
        return
    }

    $nodeModules = Join-Path $WorkingDirectory 'node_modules'
    $binDir = Join-Path $nodeModules '.bin'
    $viteBin = Join-Path $binDir 'vite'
    $viteBinCmd = Join-Path $binDir 'vite.cmd'
    $depsLookHealthy = (Test-Path $nodeModules) -and (Test-Path $binDir) -and ((Test-Path $viteBin) -or (Test-Path $viteBinCmd))
    if ($depsLookHealthy) { return }

    $attempts = @()
    if (Test-Path (Join-Path $WorkingDirectory 'package-lock.json')) {
        $attempts += ,@('ci')
    }
    $attempts += ,@('install')

    foreach ($installArgs in $attempts) {
        Write-Host "$ProjectName dependencies missing. Running npm $($installArgs -join ' ')..."
        $exitCode = Invoke-ProcessAndWait -FilePath 'npm' -ArgumentList $installArgs -WorkingDirectory $WorkingDirectory
        if ($exitCode -eq 0) {
            return
        }

        Write-Warning "npm $($installArgs -join ' ') failed for ${ProjectName} (exit code $exitCode)."
    }

    throw "Unable to install dependencies for $ProjectName."
}

if (-not [string]::IsNullOrWhiteSpace($env:AI_PYTHON)) {
    $aiPython = $env:AI_PYTHON
} else {
    $conda = Get-Command 'conda' -ErrorAction SilentlyContinue | Select-Object -First 1
    $condaExe = if ($conda) { $conda.Source } else { Join-Path $HOME 'miniconda3\Scripts\conda.exe' }
    $condaReady = $false
    if (Test-Path $condaExe) {
        try {
            & $condaExe run -n fuww_ai python -c 'import fastapi, uvicorn' 2>$null
            $condaReady = $LASTEXITCODE -eq 0
        } catch {
            $condaReady = $false
        }
    }
    if ($condaReady) {
        $aiPython = $condaExe
        $aiPythonArgs = @('run','-n','fuww_ai','python','ai_engine/main.py')
    } else {
        $python = Get-Command 'python' -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $python) {
            throw 'AI Engine requires Python. Set AI_PYTHON to its interpreter or install Python/Conda.'
        }
        $aiPython = $python.Source
        $aiPythonArgs = @('ai_engine/main.py')
    }
}
if (-not $aiPythonArgs) { $aiPythonArgs = @('ai_engine/main.py') }
try {
    if ($aiPythonArgs.Count -ge 4 -and $aiPythonArgs[0] -eq 'run') {
        $redisCheckArgs = @('run','-n','fuww_ai','python','-c','import redis')
    } else {
        $redisCheckArgs = @('-c','import redis')
    }
    & $aiPython @redisCheckArgs 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Python package redis is missing; AI Engine task/session persistence will fall back to process memory. Install ai_engine/requirements.txt.' }
} catch {
    Write-Warning 'Could not verify redis-py; AI Engine task/session persistence may fall back to process memory.'
}
Start-Background -Name "ai_engine" -FilePath $aiPython -ArgumentList $aiPythonArgs -WorkingDirectory $root -StdOut "$logsDir\ai_engine.log" -StdErr "$logsDir\ai_engine.err.log"

# Read only a port announcement written by this invocation; an older JSON file can point at a stale port.
$backendStartTimeUtc = [DateTime]::UtcNow
$runtimePortFile = Join-Path $root 'backend\.runtime\teacher.json'
Start-Background -Name "backend" -FilePath "go" -ArgumentList @('run','./cmd/teacher') -WorkingDirectory (Join-Path $root "backend") -StdOut "$logsDir\backend.log" -StdErr "$logsDir\backend.err.log"
$backendPort = 8082
for ($attempt = 1; $attempt -le 60; $attempt++) {
    try {
        if (Test-Path $runtimePortFile) {
            $portAnnouncement = Get-Content $runtimePortFile -Raw | ConvertFrom-Json
            $announcementTimeUtc = [DateTime]::Parse($portAnnouncement.started_at).ToUniversalTime()
            if ($announcementTimeUtc -ge $backendStartTimeUtc -and $portAnnouncement.port -ge 1 -and $portAnnouncement.port -le 65535) {
                $backendPort = [int]$portAnnouncement.port
                break
            }
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
$env:VITE_API_BASE = "http://localhost:$backendPort"
Ensure-NodeDependencies -ProjectName "teacher_frontend" -WorkingDirectory (Join-Path $root "frontend\teacher")
Start-Background -Name "teacher_frontend" -FilePath "npm" -ArgumentList @('run','dev','--','--host','0.0.0.0','--port','5173','--strictPort') -WorkingDirectory (Join-Path $root "frontend\teacher") -StdOut "$logsDir\teacher_frontend.log" -StdErr "$logsDir\teacher_frontend.err.log"

$pidFile = Join-Path $scriptsDir "pids.json"
$pids | ConvertTo-Json | Out-File -Encoding utf8 $pidFile

Write-Host "Started components. PID file: $pidFile"
Write-Host "Logs: $logsDir"
Write-Host "If something fails, check the log files and run scripts/stop-all.ps1 to stop the background processes."
if (Test-EndpointReady -Url "http://localhost:$backendPort/health" -RetryCount 25 -DelayMilliseconds 1000) {
    Write-Host "Backend health check: OK (http://localhost:$backendPort/health)"
} else {
    Write-Warning "Backend health check failed. Please inspect logs/backend.log and logs/backend.err.log"
}

if (Test-EndpointReady -Url 'http://localhost:5173' -RetryCount 25 -DelayMilliseconds 1000) {
    Write-Host "Teacher frontend ready: http://localhost:5173"
} else {
    Write-Warning "Teacher frontend readiness check failed. Please inspect logs/teacher_frontend.log"
}

if (Test-EndpointReady -Url 'http://localhost:8000/health' -RetryCount 25 -DelayMilliseconds 1000) {
    Write-Host "AI Engine health check: OK (http://localhost:8000/health)"
} else {
    Write-Warning "AI Engine health check failed. Please inspect logs/ai_engine.log and logs/ai_engine.err.log"
}

Write-Host "Done."
Write-Host ""
Write-Host "Access URLs (local):"
Write-Host "- 教师端前端: http://localhost:5173 (vite 默认端口)"
Write-Host "- 教师端后端: http://localhost:$backendPort (健康检查: /health, API 根路径: /api)"
Write-Host "- AI 引擎: http://localhost:8000"
Write-Host ""
Write-Host "Notes:"
Write-Host "- 如果使用 Docker 启动，端口映射在 backend/docker-compose.yml 中定义。"
Write-Host "- 如页面无法访问，请检查对应日志文件（logs/ 目录）或运行 'docker compose ps' 查看容器状态。"
