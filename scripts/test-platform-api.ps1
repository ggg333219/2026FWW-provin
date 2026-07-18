# Platform V1 API test script
# Start backend first: go run ./api (or scripts/start-all.ps1)
# Default: http://localhost:18080. Override: .\test-platform-api.ps1 -BaseUrl "http://localhost:8082"

param(
    [string]$BaseUrl = "http://localhost:18080"
)

$api = $BaseUrl + "/api/v1/platform"

Write-Host "=== Platform V1 API Test (BaseUrl: $BaseUrl) ===" -ForegroundColor Cyan
Write-Host ""

function Test-Get {
    param([string]$Name, [string]$Path, [string]$Query = "")
    $url = if ($Query) { $api + $Path + "?" + $Query } else { $api + $Path }
    Write-Host "[GET] $Name" -ForegroundColor Yellow
    Write-Host "  URL: $url"
    try {
        $r = Invoke-RestMethod -Uri $url -Method Get -ErrorAction Stop
        Write-Host "  OK | code: $($r.code) | message: $($r.message)" -ForegroundColor Green
        if ($r.data) {
            $data = $r.data
            if ($data.counts) { Write-Host "  counts: $($data.counts | ConvertTo-Json -Compress)" }
            if ($data.items) { Write-Host "  items count: $($data.items.Count)" }
            if ($data.pagination) { Write-Host "  pagination: $($data.pagination | ConvertTo-Json -Compress)" }
        }
    } catch {
        Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host ""
}

Test-Get -Name "overview" -Path "/overview"
Test-Get -Name "users" -Path "/users" -Query "page=1&pageSize=5"
Test-Get -Name "courses" -Path "/courses" -Query "page=1&pageSize=5"
Test-Get -Name "classes" -Path "/classes" -Query "page=1&pageSize=5"
Test-Get -Name "enrollments" -Path "/enrollments" -Query "page=1&pageSize=5"

Write-Host "[GET] health" -ForegroundColor Yellow
Write-Host "  URL: $BaseUrl/health"
try {
    $h = Invoke-RestMethod -Uri ($BaseUrl + "/health") -Method Get -ErrorAction Stop
    Write-Host "  OK | status: $($h.status)" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
Write-Host "More: user detail GET $api/users/{userId}, course detail GET $api/courses/{courseId}"
Write-Host "      create course POST $api/courses, sync POST $api/syncCourse or $api/syncUser"
