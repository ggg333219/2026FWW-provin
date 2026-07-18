# 启动后端并设置必要环境变量（包含签名字段）
$env:OPEN_API_STATIC_KEY='static_test_key'
$env:OPEN_API_DATA_KEY='0123456789abcdef0123456789abcdef'
$env:OPEN_API_JWT_SECRET='dev_jwt_secret_012345'
$env:OPEN_API_SIGN_FIELDS='platformId,userId'
# 本地数据库连接（本机测试常用设置，按需调整）
$env:DB_HOST='127.0.0.1'
$env:DB_PORT='5432'
$env:DB_USER='postgres'
$env:DB_PASSWORD='123456'
$env:DB_NAME='teaching'
Set-Location 'C:\Users\27968\Desktop\FuWuWaiBao\backend'
Write-Output "Starting api with OPEN_API_SIGN_FIELDS=$($env:OPEN_API_SIGN_FIELDS)"
# 直接执行（前台），日志会输出到控制台与 backend/logs/app.log
go run ./api
