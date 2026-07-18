# 示例：按服务端当前规则计算 enc 并调用 /api/v1/platform/syncUser
# 默认签名字段：platformId,userId

# 可覆盖的环境变量
if (-not $env:OPEN_API_STATIC_KEY) { $env:OPEN_API_STATIC_KEY = 'static_test_key' }

$static = $env:OPEN_API_STATIC_KEY
$platformId = 'plat_test'
$userId = 'plat_stu_test'

# 构造 JSON body（满足 syncUserFromPlatform 要求），在顶层同时包含 userId
$body = @{
    platformId = $platformId
    userId = $userId
    userInfo = @{
        userId = $userId
        userName = '李四'
        contactInfo = @{
            email = 'lisi@example.com'
            phone = '13800138000'
        }
    }
}

$json = $body | ConvertTo-Json -Depth 6
Write-Output "Request body: $json"

function stringifyForSign($v) {
    if ($null -eq $v) { return '' }
    if ($v -is [string]) { return $v }
    if ($v -is [bool] -or $v -is [int] -or $v -is [long] -or $v -is [double]) { return [string]$v }
    if ($v -is [System.Collections.IDictionary]) {
        $keys = @()
        foreach ($k in $v.Keys) { $keys += $k }
        $keys = $keys | Sort-Object
        $sb = '{'
        $first = $true
        foreach ($k in $keys) {
            if (-not $first) { $sb += ',' }
            $first = $false
            $sb += '"' + $k + '":' + (stringifyForSign $v[$k])
        }
        $sb += '}'
        return $sb
    }
    if ($v -is [System.Collections.IEnumerable]) {
        # arrays
        $sb = '['
        $first = $true
        foreach ($e in $v) {
            if (-not $first) { $sb += ',' }
            $first = $false
            $sb += (stringifyForSign $e)
        }
        $sb += ']'
        return $sb
    }
    return [string]$v
}

# 计算 builder：按照服务端当前规则，拼接 platformId + userId + static + time
$time = Get-Date -Format 'yyyy-MM-ddHH:mm:ss'
$builder_flat = "platformId$platformId" + "userId$userId" + $static + $time
$enc_flat = [System.BitConverter]::ToString((New-Object System.Security.Cryptography.MD5CryptoServiceProvider).ComputeHash([System.Text.Encoding]::UTF8.GetBytes($builder_flat))).Replace('-','').ToUpper()

Write-Output "Time: $time"
Write-Output "Builder (flat): $builder_flat"
Write-Output "enc_flat: $enc_flat"

$uri = "http://127.0.0.1:18080/api/v1/platform/syncUser?enc=$enc_flat&time=$time"
Write-Output "POST: $uri"

try {
    $r = Invoke-RestMethod -Method Post -Uri $uri -ContentType 'application/json' -Body $json -TimeoutSec 20 -ErrorAction Stop
    Write-Output "Success response: $($r | ConvertTo-Json -Compress)"
} catch {
    Write-Output "Attempt failed: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        try { $_.Exception.Response.GetResponseStream() | % { [System.IO.StreamReader]::new($_).ReadToEnd() } | ForEach-Object { Write-Output "Response body: $_" } } catch { }
    }
}

Write-Output "\n--- Server log (last 60 lines) ---"
if (Test-Path "backend\logs\app.log") { Get-Content "backend\logs\app.log" -Tail 60 | ForEach-Object { Write-Output $_ } } else { Write-Output 'backend/logs/app.log not found' }
