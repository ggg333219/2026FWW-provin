# 泛雅 AI 智课系统 — Dify 集成交接文档

> **文档版本：** 2026-05-24  
> **适用范围：** FuWuWaiBao 后端 + Dify 自托管 + 通义千问  
> **状态：** 8 项 AI 能力已全部在 Dify 侧配置并通过测试

---

## 一、总体架构

```
Vue 前端（教师/学生）
        ↓ HTTP
Go 后端（Gin，:18080）
        ↓ DifyClient（AIEngine 接口）
        ├─ Chat API     → Dify「智课问答」应用（AskWithContext）
        └─ Workflow API → Dify「统一 Workflow」应用（7 个 scene 分支）
                ↓
        通义 qwen-plus / qwen3-tts-flash
                ↓（失败时）
        Python AI 引擎（:8000，可选降级）
```

**设计要点：**

- Go 后端只对接 **一个** `AIEngine` 接口；`APP_AI_USE_DIFY=true` 时走 Dify，失败可降级 Python 引擎。
- Dify 侧采用 **1 个 Chat 应用 + 1 个 Workflow 应用**（Workflow 内用 IF/ELSE 按 `scene` 路由）。
- Workflow 结束节点统一输出 **`result`**（JSON 字符串），Go 从 `data.outputs.result` 解析。

---

## 二、8 项功能清单

| # | 功能 | scene 值 | Dify API | 后端方法 | 配置指南 | Go 联调脚本 | 状态 |
|---|------|----------|----------|----------|----------|-------------|------|
| 1 | 上下文问答 | `ask_with_context` | Chat `/v1/chat-messages` | `AskWithContext` | Chat 应用内配置 | `test_dify_integration.go` | ✅ |
| 2 | 页级讲稿 | `generate_script` | Workflow | `GenerateScript` | `workflows/01-generate_script.md` | `test_workflow_generate_script.go` | ✅ |
| 3 | 知识点解析 | `parse_knowledge` | Workflow | `ParseKnowledge` | `workflows/02-parse_knowledge.md` | `test_workflow_parse_knowledge.go` | ✅ |
| 4 | Markdown 三阶段 Pipeline | `generate_from_markdown` | Workflow | `GenerateFromMarkdown` | `workflows/03-generate_from_markdown.md` | `test_workflow_generate_from_markdown.go` | ✅ |
| 5 | 讲授节点讲稿 | `generate_node_script` | Workflow | `GenerateNodeScript` | `workflows/04-generate_node_script.md` | `test_workflow_generate_node_script.go` | ✅ |
| 6 | 课件重构节点 | `reconstruct_document` | Workflow | `ReconstructDocument` | `workflows/05-reconstruct_document.md` | `test_workflow_reconstruct_document.go` | ✅ |
| 7 | 文档解析 | `parse_document` | Workflow + 文件上传 | `ParseDocument` | `workflows/06-parse_document.md` | `test_workflow_parse_document.go` | ✅ |
| 8 | 音频时间轴（真实 TTS） | `generate_audio` | Workflow + 代码节点 | `GenerateAudio` | `workflows/07-generate_audio.md` | `test_workflow_generate_audio.go` | ✅ |

---

## 三、Dify 应用与 API Key

| 应用类型 | 用途 | 环境变量 | 说明 |
|----------|------|----------|------|
| **Chat 应用**「智课问答」 | 功能 #1 问答 | `APP_AI_DIFY_API_KEY` | 输入变量：`context`、`current_page`（可选） |
| **Workflow 应用**（统一） | 功能 #2–#8 | `APP_AI_DIFY_WORKFLOW_API_KEY` | 开始节点变量 `scene` 路由；结束节点输出 `result` |

> ⚠️ **Workflow 必须发布**后，外部 API（Go 后端）才能调用；Dify 界面「测试运行」可走草稿，API 走已发布版本。

---

## 四、部署与端口

### 4.1 目录结构

```
FuWuWaiBao/
├── .env                          # 全局配置（AI Key、Dify Key、TTS 等）
├── backend/
│   ├── internal/service/dify_client.go   # Dify 客户端实现
│   ├── internal/service/dify_client_test.go
│   └── test_workflow_*.go        # 各 scene 联调脚本
└── dify/
    ├── docker-compose.yml        # Dify 自托管（含 sandbox）
    ├── sandbox/conf/config.yaml  # 代码沙箱配置
    ├── DIFY交接文档.md           # 本文档
    └── workflows/                # 01–07 配置指南
```

### 4.2 容器与端口

| 容器 | 端口 | 说明 |
|------|------|------|
| dify-web | **13000** | Dify 控制台 http://localhost:13000 |
| dify-api | **18001** | API http://127.0.0.1:18001 |
| dify-postgres | 5433 | 数据库 |
| dify-redis | 6380 | 缓存 / Celery |
| dify-sandbox | 8194（内部） | **代码节点执行**（generate_audio 等） |
| dify-qdrant | 6333 | 向量库 |
| dify-plugin-daemon | 5003 | 通义等插件 |

### 4.3 启动 / 重启

```powershell
cd dify
docker compose up -d
```

**常见运维命令：**

```powershell
# 查看状态
docker compose ps

# API 卡住 / 页面一直加载 / 联调超时
docker compose restart dify-api dify-worker dify-web

# postgres/redis 退出时
docker compose up -d
docker compose restart dify-api dify-worker

# 更新 sandbox 配置后
docker compose up -d --force-recreate dify-sandbox
```

---

## 五、环境变量（`.env` 关键项）

```ini
# 通义 DashScope（LLM + TTS 共用）
AI_API_KEY=sk-你的通义Key
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# TTS（generate_audio）
TTS_PROVIDER=dashscope
TTS_VOICE=Cherry

# 启用 Dify
APP_AI_USE_DIFY=true
APP_AI_DIFY_BASE_URL=http://127.0.0.1:18001
APP_AI_DIFY_API_KEY=app-xxx          # Chat 应用 Key
APP_AI_DIFY_WORKFLOW_API_KEY=app-yyy # Workflow 应用 Key

# Python 降级引擎（可选）
APP_AI_BASE_URL=http://127.0.0.1:8000
```

**后端读取逻辑：** `backend/pkg/config/config.go` → `main.go` 中 `NewDifyClientWithFallback(...)`。

---

## 六、后端集成说明

### 6.1 核心代码

| 文件 | 职责 |
|------|------|
| `backend/internal/service/dify_client.go` | 8 个 AIEngine 方法、Chat/Workflow/文件上传 |
| `backend/internal/service/ai_engine_client.go` | 请求/响应类型定义 |
| `backend/api/main.go` | `APP_AI_USE_DIFY=true` 时注入 DifyClient |

### 6.2 双 API Key

- **Chat Key** → `/v1/chat-messages`（AskWithContext）
- **Workflow Key** → `/v1/workflows/run`、文件上传（其余 7 项）

### 6.3 Workflow 输出约定

- 结束节点变量名：**`result`**
- 值类型：**JSON 字符串**
- Go 解析：`data.outputs.result` → `json.Unmarshal` 到对应 Response 结构体

### 6.4 generate_audio 特殊说明

- 使用 **代码节点** 调用通义 `qwen3-tts-flash`，非 LLM。
- 后端自动传入 `dashscope_api_key`（来自 `AI_API_KEY`）。
- Dify 内测需手动填 `dashscope_api_key`；代码沙箱**读不到** Docker 环境变量。
- 代码节点必须开启 **「网络」**；HTTPS 需 `ssl._create_unverified_context()`（见 07 指南）。
- 成功返回 `status: ready`，`sections[].audio_url` 为 DashScope OSS 链接。

---

## 七、Workflow 分支结构（统一应用）

```
开始（scene + 各 scene 所需变量）
  ↓
IF/ELSE（scene）
  ├─ generate_script          → LLM → 结束(result)
  ├─ parse_knowledge          → LLM → 代码/结束(result)
  ├─ generate_from_markdown   → LLM×3 → 代码组装 → 结束(result)
  ├─ generate_node_script     → LLM → 结束(result)
  ├─ reconstruct_document   → LLM → 结束(result)
  ├─ parse_document           → 文档提取器 → LLM → 结束(result)
  └─ generate_audio           → 代码(TTS) → 结束(result)
```

**scene 值必须与上表完全一致**（区分下划线，如 `generate_from_markdown` 不是 `from_markdown`）。

---

## 八、测试方法

### 8.1 单元测试（Mock，不依赖 Dify）

```powershell
cd backend
go test ./internal/service/ -count=1 -v
```

### 8.2 联调脚本（真实 Dify）

先确保 Dify API 正常，再加载 `.env` 运行：

```powershell
cd backend

# 加载 .env（PowerShell 示例）
Get-Content ..\.env | ForEach-Object {
  if ($_ -match '^\s*([^#=]+)=(.*)$') {
    [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
  }
}

go run test_dify_integration.go              # AskWithContext
go run test_workflow_generate_script.go
go run test_workflow_parse_knowledge.go
go run test_workflow_generate_from_markdown.go
go run test_workflow_generate_node_script.go
go run test_workflow_reconstruct_document.go
go run test_workflow_parse_document.go
go run test_workflow_generate_audio.go       # 真实 TTS，约 5–40s
```

### 8.3 启动完整后端

```powershell
cd backend
go run ./api
# 日志应出现：使用 Dify AI 客户端
# 健康检查：GET http://127.0.0.1:18080/health
```

---

## 九、常见问题排查

| 现象 | 原因 | 处理 |
|------|------|------|
| Dify 页面一直加载 | postgres/redis 退出或 API 挂死 | `docker compose up -d` + restart api/worker |
| API 联调 120s 超时 | dify-api 卡住 | `docker compose restart dify-api dify-worker` |
| 代码节点 name resolution | 缺少 dify-sandbox | `docker compose up -d dify-sandbox` |
| `unexpected keyword argument` | 代码节点参数名与 `main()` 不一致 | 对齐输入变量名 |
| TTS 仍 mock / fallback_ready | 未开网络、Key 未传、SSL 错误 | 开网络 + 传 `dashscope_api_key` + SSL 修复代码 |
| `CERTIFICATE_VERIFY_FAILED` | 沙箱缺 CA | 使用 07 指南中 `_SSL_CTX` 方案 |
| Workflow API 与 UI 结果不一致 | API 调未发布版本 | 在 Dify 中 **发布** Workflow |
| scene 走错分支 | scene 字符串拼写错误 | 对照第二节表格 |

---

## 十、交接检查清单

接手人可按下列项逐项确认：

- [ ] `.env` 中 `AI_API_KEY`、两个 Dify API Key 已配置且有效
- [ ] `docker compose ps` 全部容器 Up（尤其 postgres、redis、sandbox）
- [ ] Dify 控制台可访问 http://localhost:13000
- [ ] Chat 应用「智课问答」已发布
- [ ] 统一 Workflow 已发布，8 个 scene 分支均可测试 SUCCESS
- [ ] `go test ./internal/service/` 全部 PASS
- [ ] 至少跑通 `test_dify_integration.go` + `test_workflow_generate_audio.go`
- [ ] Go 后端启动日志显示「使用 Dify AI 客户端」
- [ ] 熟悉 `dify/workflows/01–07` 各指南，能独立修改 Prompt / Schema

---

## 十一、相关文档索引

| 文档 | 路径 |
|------|------|
| Workflow 配置指南 1–7 | `dify/workflows/01-generate_script.md` … `07-generate_audio.md` |
| Dify 需求分析 | `dify需求分析.md` |
| API 设计 | `docs/API_DESIGN_V2.md` |
| Dify 客户端源码 | `backend/internal/service/dify_client.go` |
| 类型定义 | `backend/internal/service/ai_engine_client.go` |

---

## 十二、后续可选优化

1. **音频持久化：** 当前 TTS 返回 DashScope 临时 OSS URL，可扩展为下载后上传 MinIO，避免链接过期。
2. **Python 引擎：** 降级路径存在 BOM 等小问题，非 Dify 主路径，可按需修复。
3. **监控：** 对 Dify API 延迟/超时做告警，自动 restart 脚本。
4. **密钥安全：** 生产环境将 API Key 迁至密钥管理服务，避免明文 `.env`。

---

## 十三、联系人 / 备注

- **Dify 版本：** 1.14.x（镜像 `langgenius/dify-api:latest`）
- **默认模型：** `qwen-plus`（LLM）、`qwen3-tts-flash`（TTS）
- **统一 Workflow 设计决策：** 单 Workflow + IF/ELSE 路由，一个 Workflow API Key 覆盖 7 个 scene，降低运维复杂度。

---

*文档随项目更新；Workflow Prompt 细节以 `dify/workflows/` 下各指南为准。*
