---
name: 队友肯定都装了wsl的-启动服务的时候不要和队友本身的电脑配置冲突了-尽量选一个不常用的端口就行
description: 队友肯定都装了wsl的，启动服务的时候不要和队友本身的电脑配置冲突了，尽量选一个不常用的端口就行 — verified by 4 checks
triggers: ['config.yaml', 'config.local.yaml', 'docker-compose', 'null']
---

# 队友肯定都装了wsl的-启动服务的时候不要和队友本身的电脑配置冲突了-尽量选一个不常用的端口就行

> 自动从会话 98a0e59f 蒸馏的草稿。审核后用 `/skill approve 队友肯定都装了wsl的-启动服务的时候不要和队友本身的电脑配置冲突了-尽量选一个不常用的端口就行` 入库，或 `/skill reject 队友肯定都装了wsl的-启动服务的时候不要和队友本身的电脑配置冲突了-尽量选一个不常用的端口就行` 丢弃。

## Steps
1. 阅读 / 搜索：echo "=== 候选端口占用检查 ===" && for p in 25432 26379 29、echo "=== 1xxxx 段候选 ===" && for p in 15432 16379 1、echo "=== config.yaml 是否 tracked ===" && (git ls-f
2. 操作：todo
3. 阅读 / 搜索：cat .env.example、C:\Users\34511\AppData\Local\Temp\rivet-raw\2cdf5d0c289b30eefc08bffb.raw、cp .env.example .env.example.bak && python - << 'E
4. 修改：D:\Desktop\2026FWW-provin\backend\config\config.yaml.example、D:\Desktop\2026FWW-provin\backend\config\config.local.yaml.example
5. 阅读 / 搜索：echo "=== backend/.env.example 是否存在 ===" && ls -la
6. 修改：D:\Desktop\2026FWW-provin\backend\docker-compose.yml
7. 阅读 / 搜索：echo "=== 现有 teaching-* 容器（5433 那批）===" && docker、echo "=== 旧 teaching-postgres 的数据量（是否有真实数据）===" &&、echo "=== 用独立项目名验证新端口（不碰旧容器）===" && PROJECT=fuwwve
8. 修改：D:\Desktop\2026FWW-provin\README.md
9. 阅读 / 搜索：echo "=== README 里残留的旧端口引用 ===" && grep -nE "5432|
10. 验证：go build ./... 2>&1 | head -3; echo "BUILD=${PIPES、deliver_task
11. 阅读 / 搜索：echo "=== .env.example 行数与端口 ===" && wc -l .env.ex、python -c "
s = open('.env.example','rb').read()
p、echo "=== outline.py 语法 + 关键函数完整性 ===" && python -
12. 验证：deliver_task
13. 阅读 / 搜索：echo "=== core.autocrlf 设置 ===" && git config --ge、echo "=== d212cdd（我改之前）的 .env.example 行尾 ===" && g、echo "=== c38e70b 相对 d212cdd 的实际 diff（前 30 行）==="

## Verified by
- cd /d/Desktop/2026FWW-provin && echo "=== 候选端口占用检查 ===" && for p in 25432 26379 29000 29001 18080; do if netstat -ano 2>/dev/null | grep -q ":$p .*LISTENING"; then echo "$p 占用"; else echo "$p 空闲"; fi; (passed 0)
- cd /d/Desktop/2026FWW-provin && grep -n "container_name" backend/docker-compose.yml docker-compose.yml backend/docker-compose.test.yml 2>/dev/null | head -15 (passed 0)
- cd /d/Desktop/2026FWW-provin/backend && go build ./... 2>&1 | head -3; echo "BUILD=${PIPESTATUS[0]}"; go test -count=1 ./internal/service/ 2>&1 | tail -3; echo "TEST=${PIPESTATUS[0]}"; cd /d/Desktop/2 (passed 0)
- cd /d/Desktop/2026FWW-provin && echo "=== d212cdd（我改之前）的 .env.example 行尾 ===" && git show d212cdd:.env.example | python -c "import sys; s=sys.stdin.buffer.read(); print('CRLF:', s.count(b'\r\n'), 'LF: (passed 0)

<!-- skill-draft-key: 8f94fd811b84 -->
<!-- source-session: 98a0e59f -->
