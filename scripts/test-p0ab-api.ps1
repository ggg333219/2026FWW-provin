# P0 + Iteration A/B regression script
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\scripts\test-p0ab-api.ps1 -CourseId "<course-id>"

param(
    [string]$BaseUrl = "http://localhost:18080",
    [Parameter(Mandatory=$true)][string]$CourseId,
    [string]$StudentId = "stu_test_001",
    [string]$OtherStudentId = "stu_test_002",
    [string]$NodeId = "p1_n1",
    [int]$PageNum = 1
)

$ErrorActionPreference = "Stop"

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message,
        [object]$Context = $null
    )
    if ($Condition) {
        Write-Host "✅ $Message" -ForegroundColor Green
    } else {
        Write-Host "❌ $Message" -ForegroundColor Red
        if ($null -ne $Context) {
            $Context | ConvertTo-Json -Depth 8
        }
        throw "Assertion failed: $Message"
    }
}

function Invoke-JsonPost {
    param([string]$Url, [hashtable]$Body)
    return Invoke-RestMethod -Uri $Url -Method Post -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 8)
}

Write-Host "=== P0+A+B Regression (BaseUrl: $BaseUrl) ===" -ForegroundColor Cyan

# 1) save note (with nodeId)
$saveNote = Invoke-JsonPost -Url "$BaseUrl/api/v1/student/coursewares/$CourseId/notes" -Body @{
    studentId = $StudentId
    nodeId    = $NodeId
    pageNum   = $PageNum
    content   = "regression-note $(Get-Date -Format s)"
}
Write-Host "save-note => $($saveNote.message)"
Assert-True ($saveNote.code -eq 200) "save note code=200" $saveNote

# 2) generate practice
$generate = Invoke-JsonPost -Url "$BaseUrl/api/v1/student/practice/generate" -Body @{
    studentId  = $StudentId
    courseId   = $CourseId
    nodeId     = $NodeId
    pageNum    = $PageNum
    difficulty = 2
    count      = 3
}
Write-Host "practice-generate => $($generate.message)"
Assert-True ($generate.code -eq 200) "generate code=200" $generate
Assert-True ($generate.data.taskId) "generate has taskId" $generate
Assert-True (($generate.data.questions.Count -eq 3)) "generate has 3 questions" $generate.data

$taskId = $generate.data.taskId
$answers = @()
foreach ($q in $generate.data.questions) {
    $answers += @{ questionId = $q.questionId; userAnswer = "A" }
}

# 3) submit #1
$submit1 = Invoke-JsonPost -Url "$BaseUrl/api/v1/student/practice/submit" -Body @{
    taskId    = $taskId
    studentId = $StudentId
    answers   = $answers
}
Write-Host "practice-submit#1 => $($submit1.message)"
Assert-True ($submit1.code -eq 200) "submit1 code=200" $submit1
$attemptId1 = $submit1.data.attemptId

# 4) submit #2 (idempotent)
$submit2 = Invoke-JsonPost -Url "$BaseUrl/api/v1/student/practice/submit" -Body @{
    taskId    = $taskId
    studentId = $StudentId
    answers   = $answers
}
Write-Host "practice-submit#2 => $($submit2.message)"
Assert-True ($submit2.code -eq 200) "submit2 code=200" $submit2
Assert-True ($submit2.data.idempotent -eq $true) "submit2 idempotent=true" $submit2.data
Assert-True ($submit2.data.attemptId -eq $attemptId1) "submit2 attemptId equals submit1" @{ submit1=$attemptId1; submit2=$submit2.data.attemptId }

# 5) create favorite
$createFavorite = Invoke-JsonPost -Url "$BaseUrl/api/v1/student/favorites" -Body @{
    studentId = $StudentId
    courseId  = $CourseId
    nodeId    = $NodeId
    pageNum   = $PageNum
    title     = "regression-fav"
}
Write-Host "favorites-create => $($createFavorite.message)"
Assert-True ($createFavorite.code -eq 200) "favorites create code=200" $createFavorite
$favoriteId = $createFavorite.data.favoriteId

# 6) favorites list pagination
$favoritesList = Invoke-RestMethod -Uri "$BaseUrl/api/v1/student/favorites?studentId=$StudentId&courseId=$CourseId&page=1&pageSize=1" -Method Get
Assert-True ($favoritesList.code -eq 200) "favorites list code=200" $favoritesList
Assert-True (($null -ne $favoritesList.data.page -and $null -ne $favoritesList.data.pageSize -and $null -ne $favoritesList.data.totalPages)) "favorites has pagination fields" $favoritesList.data

# 7) notes list pagination
$notesList = Invoke-RestMethod -Uri "$BaseUrl/api/v1/student/notes?studentId=$StudentId&courseId=$CourseId&page=1&pageSize=1" -Method Get
Assert-True ($notesList.code -eq 200) "notes list code=200" $notesList
Assert-True (($null -ne $notesList.data.page -and $null -ne $notesList.data.pageSize -and $null -ne $notesList.data.totalPages)) "notes has pagination fields" $notesList.data

# 8) delete favorite by other user => 404
try {
    $delOther = Invoke-RestMethod -Uri "$BaseUrl/api/v1/student/favorites/$favoriteId?studentId=$OtherStudentId" -Method Delete
    Assert-True ($false) "delete by other user should fail" $delOther
} catch {
    $body = $_.ErrorDetails.Message | ConvertFrom-Json
    Assert-True ($body.code -eq 404) "delete by other user returns 404" $body
}

# 9) delete favorite by owner => success
$delOwner = Invoke-RestMethod -Uri "$BaseUrl/api/v1/student/favorites/$favoriteId?studentId=$StudentId" -Method Delete
Assert-True ($delOwner.code -eq 200) "delete by owner code=200" $delOwner

# 10) node insights (B)
$insights = Invoke-RestMethod -Uri "$BaseUrl/api/v1/teacher/coursewares/$CourseId/node-insights" -Method Get
Assert-True ($insights.code -eq 200) "node-insights code=200" $insights
Assert-True ($insights.data.items.Count -ge 1) "node-insights has items" $insights.data
$first = $insights.data.items[0]
Assert-True ($null -ne $first.practiceAttemptCount) "insights has practiceAttemptCount" $first
Assert-True ($null -ne $first.practiceAccuracy) "insights has practiceAccuracy" $first
Assert-True ($null -ne $first.reteachCount) "insights has reteachCount" $first
Assert-True ($null -ne $first.reteachRate) "insights has reteachRate" $first
Assert-True ($first.trend7d.Count -eq 7) "insights trend7d length=7" $first.trend7d

$sorted = $true
for ($i = 1; $i -lt $insights.data.items.Count; $i++) {
    if ([int]$insights.data.items[$i-1].insightScore -lt [int]$insights.data.items[$i].insightScore) {
        $sorted = $false
        break
    }
}
Assert-True $sorted "insights sorted by insightScore desc" $insights.data.items

Write-Host ""
Write-Host "=== All checks passed ===" -ForegroundColor Cyan
