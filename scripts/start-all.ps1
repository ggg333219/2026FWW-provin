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

if ([string]::IsNullOrWhiteSpace($env:AI_BASE_URL) -or $env:AI_BASE_URL -match 'example\.com') {
    $env:AI_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
}

if ([string]::IsNullOrWhiteSpace($env:AI_MODEL) -or $env:AI_MODEL -match '^gpt-4o') {
    $env:AI_MODEL = 'qwen-plus'
}

if ([string]::IsNullOrWhiteSpace($env:AI_GEN_MODE)) {
    $env:AI_GEN_MODE = 'llm'
}

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

function Get-StudentFrontendUrlFromLog {
    param(
        [Parameter(Mandatory)][string]$LogPath
    )

    if (-not (Test-Path $LogPath)) { return $null }

    try {
        $tail = Get-Content -Path $LogPath -Tail 200 -ErrorAction Stop
    } catch {
        return $null
    }

    foreach ($line in $tail) {
        $m = [regex]::Match($line, 'http://localhost:(\d+)\s*/?')
        if ($m.Success) {
            return "http://localhost:$($m.Groups[1].Value)"
        }
    }

    return $null
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

    $proc = Start-Process -FilePath $startFilePath -ArgumentList $startArgumentList -WorkingDirectory $WorkingDirectory -NoNewWindow -PassThru -RedirectStandardOutput $StdOut -RedirectStandardError $StdErr
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
    $cliServiceBin = Join-Path $binDir 'vue-cli-service'
    $cliServiceBinCmd = Join-Path $binDir 'vue-cli-service.cmd'
    $depsLookHealthy = (Test-Path $nodeModules) -and (Test-Path $binDir) -and ((Test-Path $cliServiceBin) -or (Test-Path $cliServiceBinCmd))
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

Start-Background -Name "ai_engine" -FilePath "conda" -ArgumentList @('run','-n','fuww_ai','python','ai_engine/main.py') -WorkingDirectory $root -StdOut "$logsDir\ai_engine.log" -StdErr "$logsDir\ai_engine.err.log"
Start-Background -Name "backend" -FilePath "go" -ArgumentList @('run','./api/main.go') -WorkingDirectory (Join-Path $root "backend") -StdOut "$logsDir\backend.log" -StdErr "$logsDir\backend.err.log"
Ensure-NodeDependencies -ProjectName "student_frontend" -WorkingDirectory (Join-Path $root "frontend\student")
Start-Background -Name "student_frontend" -FilePath "npm" -ArgumentList @('run','serve') -WorkingDirectory (Join-Path $root "frontend\student") -StdOut "$logsDir\student_frontend.log" -StdErr "$logsDir\student_frontend.err.log"
Ensure-NodeDependencies -ProjectName "teacher_frontend" -WorkingDirectory (Join-Path $root "frontend\teacher")
Start-Background -Name "teacher_frontend" -FilePath "npm" -ArgumentList @('run','dev','--','--host','0.0.0.0','--port','5173') -WorkingDirectory (Join-Path $root "frontend\teacher") -StdOut "$logsDir\teacher_frontend.log" -StdErr "$logsDir\teacher_frontend.err.log"

$pidFile = Join-Path $scriptsDir "pids.json"
$pids | ConvertTo-Json | Out-File -Encoding utf8 $pidFile

Write-Host "Started components. PID file: $pidFile"
Write-Host "Logs: $logsDir"
Write-Host "If something fails, check the log files and run scripts/stop-all.ps1 to stop the background processes."
if (Test-EndpointReady -Url 'http://localhost:18080/health' -RetryCount 25 -DelayMilliseconds 1000) {
    Write-Host "Backend health check: OK (http://localhost:18080/health)"
} else {
    Write-Warning "Backend health check failed. Please inspect logs/backend.log and logs/backend.err.log"
}

$studentLog = Join-Path $logsDir 'student_frontend.log'
$studentUrl = Get-StudentFrontendUrlFromLog -LogPath $studentLog
if (-not $studentUrl) { $studentUrl = 'http://localhost:8080' }
if (Test-EndpointReady -Url $studentUrl -RetryCount 25 -DelayMilliseconds 1000) {
    Write-Host "Student frontend ready: $studentUrl"
} else {
    Write-Warning "Student frontend readiness check failed. Please inspect logs/student_frontend.log"
}

if (Test-EndpointReady -Url 'http://localhost:5173' -RetryCount 25 -DelayMilliseconds 1000) {
    Write-Host "Teacher frontend ready: http://localhost:5173"
} else {
    Write-Warning "Teacher frontend readiness check failed. Please inspect logs/teacher_frontend.log"
}

Write-Host "Done."
Write-Host ""
Write-Host "Access URLs (local):"
Write-Host "- 学生端前端: http://localhost:8080 (vue-cli serve 默认端口)"
Write-Host "- 教师端前端: http://localhost:5173 (vite 默认端口)"
Write-Host "- 统一后端: http://localhost:18080 (健康检查: /health, API 根路径: /api)"
Write-Host ""
Write-Host "Notes:"
Write-Host "- 如果使用 Docker 启动，端口映射在 backend/docker-compose.yml 中定义。"
Write-Host "- 如页面无法访问，请检查对应日志文件（logs/ 目录）或运行 'docker compose ps' 查看容器状态。"