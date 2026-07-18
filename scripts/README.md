# 启动脚本说明

仓库根目录下提供了方便在 Windows (PowerShell) 上一键启动/停止本项目前端、后端、AI 引擎和依赖服务的脚本。

文件：
- `scripts/start-all.ps1`：一键启动脚本，会根据宿主机提供的 CLI 选择 `docker compose`（优先）或 `docker-compose`，再执行 `up -d`；接着调用 `conda run -n fuww_ai python ai_engine/main.py`、`go run ./api/main.go` 以及带 `--host 0.0.0.0`/指定端口的 `npm run serve`（学生端）和 `npm run dev`（教师端）并把它们的 PID 写到 `scripts/pids.json`，以便 `stop-all.ps1` 使用。
- 如果学生端或教师端缺少 `node_modules`，`start-all.ps1` 会先在对应目录自动执行 `npm ci`（无 `package-lock.json` 时退回到 `npm install`），再继续启动前端进程。
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
