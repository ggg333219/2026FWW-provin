# 泛雅 AI 智课系统

一个集成 Go 后端、Python AI 引擎与多套前端的教学平台样例工程。

## 概览

- `backend/`：Go 后端服务（Gin + GORM + Redis + MinIO）
- `ai_engine/`：Python AI 服务（PDF/PPTX 解析、讲稿生成、问答）
- `frontend/`：包含学生、教师等前端应用（Vue）
- `docs/`：项目设计与 API 文档（已生成）
- `uploads/`：上传的临时文件存放目录

> 本仓库为教学/演示用途，目录与运行方式可根据部署环境调整。

## 快速开始（本地开发）

先决条件：已安装 Docker、Go、Node.js、npm/yarn、以及 Python（推荐通过 conda 管理虚拟环境）。

后端配置优先级如下：操作系统环境变量 > 本地 `.env` 文件 > backend/config/config.local.yaml > backend/config/config.yaml > backend/config/config.yaml.example。

后端启动时会自动读取这些本地环境文件（若存在）：项目根目录 `.env`、项目根目录 `.env.local`。

当前仓库默认 LLM 配置已切为千问兼容模式：

```bash
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_MODEL=qwen-plus
AI_GEN_MODE=llm
```

1. 启动基础服务（Postgres/Redis/MinIO）

```bash
cp .env.example .env
docker compose --env-file .env -f backend/docker-compose.yml up -d
```

1. 启动 AI 引擎（Python）

```bash
cd ai_engine
conda activate fuww_ai   # 或使用你自己的虚拟环境
pip install -r requirements.txt
python main.py
```

1. 运行后端（Go）

```bash
cp backend/config/config.yaml.example backend/config/config.yaml
cp .env.example .env.local
cd backend
go run ./api/main.go
```

如果你的数据库、Redis、MinIO、AI 引擎地址与默认值不同，优先把本机差异写进项目根目录 `.env.local`，例如：

```bash
# 在根目录 .env.local 中配置
APP_OSS_ENDPOINT=192.168.1.8:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
DB_HOST=127.0.0.1
REDIS_HOST=127.0.0.1
AI_BASE_URL=http://127.0.0.1:8000
```

如果你更习惯 YAML，也可以只改 backend/config/config.local.yaml。

1. 启动前端示例（学生端）

```bash
cd frontend/student
npm install
npm run serve
```

## 测试环境

如果你要在本地快速拉起一套隔离的测试环境，可以使用仓库根目录的测试 compose：

```powershell
Copy-Item .env.test.example .env.test
.\scripts\test-env.ps1 -Action up
```

这套环境会启动 Postgres、Redis、MinIO、AI 引擎容器和后端容器。默认测试模式下 AI 引擎使用 `mock`，不依赖外部大模型网络。

常用地址：

- 后端健康检查：<http://localhost:28080/health>
- AI 引擎健康检查：<http://localhost:28000/health>
- MinIO 控制台：<http://localhost:29001>

停止环境：

```powershell
.\scripts\test-env.ps1 -Action down
```

## 文档

详细接口与设计文档保存在 `docs/` 目录，请参考该目录下的 Markdown 文件以获取 API 说明、联调清单与系统架构等内容。

## 开发建议与调试

- 开发 AI 模块时，优先在 `ai_engine/` 下使用提供的测试数据（`ai_engine/tests/mocks/`）进行快速迭代。
- 后端配置文件位于 `backend/config/`，上线前请检查数据库与 MinIO 的连接配置。
- 不要把你本机专用的 `.env`、`.env.local`、backend/config/config.yaml、backend/config/config.local.yaml 提交到仓库。
- 单元测试集中放在 backend/tests/ 下面，按模块分成 config、oss 等子目录；这样目录统一，但仍然符合 Go 的包规则。

## 常见命令汇总

- 启动全部依赖：

```bash
docker compose --env-file .env -f backend/docker-compose.yml up -d
```

- 启动 AI 服务：

```bash
cd ai_engine
python main.py
```

- 运行后端：

```bash
cd backend
go run ./api/main.go
```

## 贡献与联系

如果你希望贡献代码或有问题，请在仓库中创建 issue 或联系维护者。文档已放在 `docs/` 中，优先阅读后提交改动。

---
更新于：项目结构与文档已同步到 `docs/`，README 已适配最新目录。

## 本地服务地址（默认）

开发时常用的服务地址（如果你使用了 `scripts/start-all.ps1 -SkipDocker` 或按 README 的步骤启动）：

- **后端 API**: <http://localhost:18080>
- **AI 引擎**: <http://localhost:8000>
- **学生端 (Vue CLI)**: <http://localhost:8080>
- **教师端 (Vite)**: <http://localhost:5173>

如果你在本机上使用不同端口或把服务放到容器中，请以实际运行日志为准（日志目录：`logs/`）。

