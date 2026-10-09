# 多模态 AI 互动式教学智能体（A12）

本代码包交付教师端流程：S1 意图理解 → S2 资料解析与知识库检索 → S3 课件生成 → S4 预览、修改、版本与导出。独立学生端不属于本次交付。教师端的学情统计和知识图谱仍保留共享数据模型。

## 目录与环境

- `frontend/teacher/`：Vue 3 + Vite 教师端。
- `backend/cmd/teacher/`：Go 教师端 API；`backend/internal/` 包含服务、路由和数据模型。
- `ai_engine/`：FastAPI、LLM、RAG 与 PPTX/DOCX/HTML5 生成。
- `backend/docker-compose.yml`：PostgreSQL/pgvector、Redis、MinIO；可选启动教师端容器。
- `scripts/start-all.ps1`、`scripts/stop-all.ps1`：Windows 本地启停。

建议 Go 1.25.1、Node.js 20.19+、Python 3.10+，并安装 Docker Desktop。首次运行安装 `ai_engine/requirements.txt` 和 `frontend/teacher/package-lock.json` 中的依赖。

## Windows 本地启动

1. 将根目录 `.env.example` 复制为 `.env`，填写自己的模型 API Key，并按实际环境设置数据库、Redis 与 MinIO 参数。**不要把 `.env` 提交或打包。**
2. 在仓库根目录运行：

   ```powershell
   powershell.exe -NoProfile -File scripts/start-all.ps1
   ```

   脚本读取根目录 `.env`，启动 Docker 基础服务、AI Engine、Go 教师端和 Vite。可用 `-SkipDocker` 跳过容器启动（需要基础服务已经就绪）。
3. 打开 `http://localhost:5173`。AI Engine 健康检查为 `http://localhost:8000/health`；Go 教师端默认从 `http://localhost:8082/health` 检查，若端口被占用，以启动日志和 `backend/.runtime/teacher.json` 公告为准。
4. 停止时运行 `powershell.exe -NoProfile -File scripts/stop-all.ps1`；如果希望保留数据库容器，使用 `-SkipDocker`。

生产容器方案见 `deploy/docker-compose.server.yml`。只启动本地基础服务可运行：

```powershell
docker compose --env-file .env -f backend/docker-compose.yml up -d postgres redis minio
```

## 验证

```powershell
cd backend; go test ./...
cd ../ai_engine; python -m pytest
cd ../frontend/teacher; npm.cmd ci; npm.cmd run build; npm.cmd exec -- vitest run --configLoader runner
```

生成、检索与导出依赖外部模型及基础服务；离线单元测试通过不等于真实模型链路已验收。知识库文档和索引不会随代码包自动提供，需要在目标环境按需导入。

## 提交代码包前

不要直接压缩整个工作目录：它可能包含 `.env`、本地配置、用户上传资料、日志、数据库快照和历史 Git 对象。应从干净的 Git 提交导出代码，再在独立目录配置密钥。详见 `.gitignore`；任何曾经提交过的真实密钥都应先吊销并更换。
