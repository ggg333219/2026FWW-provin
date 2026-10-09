# A12 教学智能体 — 阿里云服务器部署手册

> 首次部署完成：2026-10-07 · 服务器 114.55.31.135（杭州，2C/1.9G，与其他项目共用）
> 访问入口：**http://114.55.31.135:8098**（安全组已放行 TCP 8098）
> **语音输入入口：https://114.55.31.135:8443**（自签证书，浏览器需"高级→继续访问"信任一次；
> 麦克风 getUserMedia 是浏览器硬性安全策略，仅在 HTTPS 或 localhost 可用，HTTP 下按钮会给出引导提示）

## 1. 部署形态（原生进程，无 Docker）

| 组件 | 端口 | 说明 |
|------|------|------|
| nginx（独立实例） | **8098 / 8443(ssl)** | 公网入口：静态前端 + `/api/`→后端 + `/ai/`→引擎 + `/download/`→引擎 |
| Go 后端（teacher-server-linux） | 18082 | 完整模式（PG+MinIO 均连上） |
| Python AI 引擎（uvicorn） | 18000 | 无 LLM key 自动降级 mock；**ASR 走本地 faster-whisper tiny**（int8/CPU，常驻约 +230MB 内存） |
| PostgreSQL（独立实例） | 15433 | 复用系统 `/usr/bin` 二进制，数据目录 `/var/lib/pgsql/a12_data`，库 teaching |
| MinIO（独立实例） | 19000 | 复用系统 `/usr/local/bin/minio`，数据目录 `/opt/a12teaching/data/minio`，bucket teaching |
| Redis | 6379/db3 | **复用服务器现有实例**（无密码），键空间隔离 |

⚠️ 服务器上 80/8090/8095 等端口被其他项目占用，本套服务全部避让，互不影响。

## 1.1 语音输入（ASR）链路

```
浏览器 MediaRecorder 录音（全浏览器通用，不依赖 Web Speech API）
  → POST /ai/api/v1/asr/transcribe（multipart，≤20MB）
  → AI 引擎 ai_engine/asr.py provider 链（任一失败自动落到下一个）：
      ① dashscope（DASHSCOPE_API_KEY / AI_API_KEY 存在时，Paraformer 云端识别）
      ② local_whisper（faster-whisper tiny int8；走 PyAV 解码，不需要系统装 FFmpeg）
      ③ 全部失败 → 返回错误，并把每个 provider 的失败原因一并返回
  → {text} 回填输入框
```

- 测试素材：`deploy/testdata/voice-test-zh.wav`（Windows TTS 生成），
  `curl -F "file=@voice-test-zh.wav;type=audio/wav" -F "language=zh" .../api/v1/asr/transcribe`
- 实测：tiny 模型中文短句识别可用，首调 ~18s（加载模型），此后 ~1s
- 引擎启动命令必须带：`ASR_ALLOW_LOCAL_WHISPER=1 HF_ENDPOINT=https://hf-mirror.com`
- 不想把 AI_API_KEY 当云端 ASR key 用时，加 `ASR_DASHSCOPE_DISABLE_AI_KEY=1`
- 排障：`grep "\[asr\]" /tmp/ai_a12.log` 能看到"哪个 provider 失败、落到哪一个"

## 1.2 本地知识库自动灌入（资料入库）

```
① 启动自动：KB_AUTO_BOOTSTRAP=1（= docs/knowledge）
            或 KB_AUTO_INGEST_DIR=目录1;目录2
            → 引擎启动后台灌入，日志 [kb-bootstrap] / [kb-ingest]
② 按需调用：POST /ai/api/v1/knowledge/ingest-dir
            {"directory":"docs/knowledge","knowledge_base_id":"kb_x","dry_run":true}
            → 返回计划 / 每个文件的入库块数 / 0 块文件 / 跳过原因 / 检索自检
③ CLI：scripts/ingest_knowledge_dir.py（素材在服务之外时用，走上传端点）
```

- 统一实现在 `ai_engine/rag/ingest.py`，三种入口共用一套扫描与入库逻辑
- 只会真的读取能解析的格式（txt/md/csv/json/html/pdf/pptx/docx）；
  `.ppt/.doc/.xls(x)/图片/压缩包` 与 `~$` 临时文件会被跳过并写明原因——
  否则二进制会被当纯文本读，乱码灌进库里极难清理
- 0 块文件（扫描版 PDF、空文件）单独列在 `zero_chunk`，不伪装成功
- 灌完自动做一次真实检索自检（`retrieval_probe`），区分"库里有内容"和"向量通道失效"
- 出于安全，接口只接受项目目录内的路径；要灌项目外的资料，
  用 `KB_INGEST_ALLOWED_ROOTS=/path/a;/path/b` 显式放行

## 2. 目录与关键文件

```
/opt/a12teaching/                 代码（git，分支 server-deploy，来源 gitcode 镜像）
├── deploy/
│   ├── teacher-server-linux      linux amd64 后端二进制（本地交叉编译，随分支分发）
│   ├── nginx/a12.conf            独立 nginx 配置（pid/日志均在 deploy/nginx/）
│   ├── ai.pid / backend.pid / minio.pid   各进程 PID
│   └── entry_port                入口端口记录（当前 8098）
├── backend/config/config.server.yaml   后端部署配置（CONFIG_FILE=config.server.yaml）
├── ai_engine/.venv               python3.11 虚拟环境（阿里云 pip 镜像安装）
└── data/{minio,redis}            独立数据目录
```

## 3. 启停命令（SSH/Workbench/云助手执行）

```bash
# 停止
pkill -f teacher-server-linux; pkill -f "uvicorn main:app"
nginx -s stop -c /opt/a12teaching/deploy/nginx/a12.conf

# 启动引擎
cd /opt/a12teaching/ai_engine && setsid nohup env PYTHONPATH=/opt/a12teaching \
  MINIO_ENDPOINT=127.0.0.1:19000 MINIO_ACCESS_KEY=minioadmin MINIO_SECRET_KEY=minioadmin ASR_ALLOW_LOCAL_WHISPER=1 HF_ENDPOINT=https://hf-mirror.com MINIO_BUCKET=teaching \
  .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 18000 < /dev/null > /tmp/ai_a12.log 2>&1 &

# 启动后端（A12_PROJECT_ROOT 必配：覆盖交叉编译烧入的构建期路径）
cd /opt/a12teaching/backend && setsid nohup env \
  A12_PROJECT_ROOT=/opt/a12teaching/backend CONFIG_FILE=config.server.yaml \
  /opt/a12teaching/deploy/teacher-server-linux < /dev/null > /tmp/backend_a12.log 2>&1 &

# 启动 nginx（独立实例，不碰系统 nginx）
nginx -c /opt/a12teaching/deploy/nginx/a12.conf

# 启动自建 PG / MinIO（若服务器重启后未随系统拉起）
su -s /bin/bash postgres -c "/usr/bin/pg_ctl -D /var/lib/pgsql/a12_data -o '-p 15433 -c listen_addresses=127.0.0.1 -k /tmp' -l /tmp/pg_a12.log start"
MINIO_ACCESS_KEY=minioadmin MINIO_SECRET_KEY=minioadmin setsid nohup /usr/local/bin/minio server /opt/a12teaching/data/minio --address :19000 --console-address :19001 < /dev/null > /tmp/minio_a12.log 2>&1 &
```

## 4. 更新部署流程

```bash
# 本地（改代码后）：
cd backend && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o deploy/teacher-server-linux ./cmd/teacher
cd frontend/teacher && VITE_API_BASE='' VITE_AI_API_BASE='/ai' npm run build   # 相对地址，换端口无需重建
git add -f deploy/teacher-server-linux frontend/teacher/dist && git commit -m "deploy: 产物更新"
git push gitcode server-deploy          # 产物经 gitcode 分发（服务器直连 GitHub 不稳）

# 服务器：
cd /opt/a12teaching && git fetch origin server-deploy && git reset --hard FETCH_HEAD
chmod +x deploy/teacher-server-linux
pkill -f teacher-server-linux; pkill -f "uvicorn main:app"
# …按第 3 节重启，curl 验收
```

## 5. 健康验收清单

| 检查 | 命令/URL | 期望 |
|------|---------|------|
| 前端 | `curl -I http://114.55.31.135:8098/` | 200 text/html |
| 引擎 | `curl http://114.55.31.135:8098/ai/health` | running（llm.degraded=true 表示无 key 降级，正常） |
| 后端 API | `curl http://114.55.31.135:8098/api/health` | {"status":"UP"} |
| 全链路 | 注册登录→建项目→大纲→生成→导出→下载 | 拿到合法 .pptx（`file` 识别 Microsoft PowerPoint 2007+） |
| 语音输入 | `curl -F "file=@deploy/testdata/voice-test-zh.wav;type=audio/wav" -F "language=zh" http://.../ai/api/v1/asr/transcribe` | 200 且 `data.text` 为可读写法（provider 为 dashscope 或 local_whisper） |
| 知识库自动灌入 | `grep "\[kb-bootstrap\]" /tmp/ai_a12.log` | 启动即出现 `ok ... 1 文件 / N 块` |
| 知识库可检索 | `POST /ai/api/v1/rag/search {"query":"TCP 三次握手","knowledge_base_ids":["kb_auto"]}` | `results` 命中且包含"三次握手" |
| 灌入接口 | `POST /ai/api/v1/knowledge/ingest-dir {"directory":"docs/knowledge","dry_run":true}` | `ok:true` 且 `planned_count>0` |

验收账号：`acceptance / a12demo123`（已注册）。

## 6. 降级容错说明（无 LLM key）

- 引擎启动即打印 `missing_api_key` 警告，`/health` 返回 `degraded:true`；
- S1 意图解析走本地规则引擎（结构化字段/追问照常产出），S3 大纲/内容走模板化 mock（大纲结构完整、可确认、可生成）；
- 导出链路完整：PPTX/DOCX/HTML5 真实文件生成；MinIO 可用时上传，不可用时保留本地文件，下载不受影响；
- 配置 key 的方法：在 `/opt/a12teaching/ai_engine/.env` 写 `AI_API_KEY=...`（可选 `AI_BASE_URL`/`AI_MODEL`）后重启引擎即可回到真实 LLM。

## 7. 已知限制

- 内存约剩 600MB：不要在服务器再叠加重型服务（本地 embedding/whisper 等均未装）；
- Redis 复用现有实例 db3：如对方项目重置 Redis，重启后端即可（无持久化依赖）；
- 前端 dist 内置相对地址，改入口端口只需改 nginx conf 的 listen，无需重建前端。
