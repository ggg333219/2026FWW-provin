# 启动脚本说明

仓库根目录下提供了方便在 Windows (PowerShell) 上一键启动/停止本项目前端、后端、AI 引擎和依赖服务的脚本。

文件：
- `scripts/start-all.ps1`：一键启动 Docker 依赖、AI 引擎、Go 教师端后端和 Vue 教师端前端，并把进程 PID 写到 `scripts/pids.json`，供 `stop-all.ps1` 使用。
- 如果教师端缺少 `node_modules`，`start-all.ps1` 会在 `frontend/teacher` 自动执行 `npm ci`（无 `package-lock.json` 时退回到 `npm install`）。
- 在 Windows 上，启动脚本会自动解析 `npm.cmd`/`.bat` 这类包装器后再启动，因此不需要手工把前端命令改成 `cmd /c npm ...`。
- `scripts/stop-all.ps1`：停止 `scripts/pids.json` 中的后台进程并按需执行 `docker compose`（或 `docker-compose`）`down`（可加 `-SkipDocker` 跳过）。

使用方法（在 PowerShell 中，以仓库根目录为当前目录运行）：

启动（含 docker-compose）：
```powershell
.\scripts\start-all.ps1
```
注意需要先开启docker destop

若想跳过 docker-compose（例如你已经用容器外的服务），可以：
```powershell
.\scripts\start-all.ps1 -SkipDocker
```
---

全局停止：
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-all.ps1
```

如果也希望跳过 docker 服务，可以传入 `-SkipDocker`：
```powershell
.\scripts\stop-all.ps1 -SkipDocker
```

停止docker容器：
```
docker compose -f .\backend\docker-compose.yml down
```


注意：
- 这些脚本假设系统上已安装并可用的命令：`docker` 或 `docker-compose`、`conda`、`go`、`npm`。请确保将 `conda` 命令加入到 PATH，或在运行脚本前从 Anaconda/Miniconda 的 PowerShell 快捷方式打开。
- AI 引擎使用的 conda 环境默认名为 `fuww_ai`（与仓库内说明一致）。如果你的环境名不同，请修改 `scripts/start-all.ps1` 中对应的 `-n` 参数或在命令前激活正确的 conda 环境。
- 日志保存在 `logs/` 目录下（脚本会自动创建），PID 信息保存到 `scripts/pids.json`，供 `stop-all.ps1` 使用。

如需我在当前机器上运行并验证这些脚本，我可以继续执行。需要我现在运行吗？

---

## S1 意图理解验收脚本（F01 / F02 / V04）

这一组脚本用于**复现** S1 意图理解的验收证据。
背景、根因与完整验证记录见 `docs/handoff/F01-F02-S1意图解析-交接文档.md`。

### 依赖

```bash
cd scripts && npm install     # 只装 playwright-core，独立于仓库根与前端工程
```

浏览器不需要下载 —— 脚本默认用本机已安装的 Chrome，可用 `CHROME` 环境变量覆盖。

### 脚本清单

| 脚本 | 层级 | 用途 |
|---|---|---|
| `fake-llm-server.py` | 工具 | 受控模型桩（OpenAI 兼容，`:8899`）。注入真实模型常见的格式偏差：`"45分钟"`、`"需要"`、`["PPT"]`、脑补知识点、脏格式 |
| `verify-f01-f02.py` | **L2 接口层** | F01/F02 验收 14 项，走完整真实链路（Go 网关 → Python 引擎 → 模型端点） |
| `probe-intent-http.py` | 工具 | 打印一次请求的关键字段，重点看 `model_source` |
| `drive-s1-intent.mjs` | **L3 浏览器** | F01/F02 浏览器验收 13 项（真实 Chrome） |
| `drive-s1-intent-v04.mjs` | **L3 浏览器** | 来源三态验收：`real_model` 11 项 / `rule_fallback` 9 项 / `mock_frontend` 3 项 |

### 完整复现步骤

```bash
# ① 受控模型桩
python scripts/fake-llm-server.py                                   # :8899

# ② AI 引擎（真实模型路径）
cd ai_engine && PYTHONPATH="<repo>" AI_GEN_MODE=llm AI_MODEL=controlled-fake-model \
  AI_BASE_URL="http://127.0.0.1:8899/v1" AI_API_KEY="sk-local-controlled-test-key" \
  python -m uvicorn main:app --host 127.0.0.1 --port 8000

# ③ Go 网关（S1 轻量模式，无 PostgreSQL/MinIO 也能起）
cd backend && go build -o ../tmp/teacher_realtest.exe ./cmd/teacher
A12_PROJECT_ROOT="<repo>/backend" ../tmp/teacher_realtest.exe        # :8082

# ④ 教师端前端
cd frontend/teacher && VITE_API_BASE="http://localhost:8082" \
  VITE_AI_API_BASE="http://localhost:8000" npx vite --port 5173 --host 127.0.0.1

# ⑤ 跑验收
python scripts/verify-f01-f02.py
cd scripts && node drive-s1-intent.mjs
SCENARIO=real_model node drive-s1-intent-v04.mjs
```

### ⚠️ 关于「真实模型」的界定

`fake-llm-server.py` 是**受控桩**，不是真实大模型。
它证明的是「归一 / 合并 / 透传逻辑在**真实链路**上成立」，
**不等于**「真实大模型（DashScope / qwen-plus）已验证」。

现场自查跑的到底是什么：

```bash
curl -s http://127.0.0.1:8000/health
# degraded:true / reason:"missing_api_key" → 跑的是 mock，不是真模型
```
