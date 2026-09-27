# 多模态 AI 互动式教学智能体 — 方案总览

> 锐捷网络 · 服务外包赛题 A12  
> 最后更新: 2026-09-23

## 目录

| 文件 | 内容 | 读者 |
|------|------|------|
| [001-分工方案-总览.md](001-分工方案-总览.md) | 三人分工 + 协作边界 | **所有人** |
| [002-任务包-Go后端-A.md](002-任务包-Go后端-A.md) | Go 后端任务：死代码清理、God Object 拆分、会话/版本/导出模块 | **后端同学** |
| [003-任务包-PythonAI引擎-B.md](003-任务包-PythonAI引擎-B.md) | Python AI Engine 任务：目录重组、多模态解析、课件生成、RAG 知识库 | **AI 同学** |
| [004-任务包-Vue前端-C.md](004-任务包-Vue前端-C.md) | Vue 前端任务：教师工作台重构、组件按域分组、API 对接 | **前端同学** |
| [005-接口契约手册.md](005-接口契约手册.md) | 三层间关键 API 定义、数据模型、状态机（旧版，参考） | **所有人（参考）** |
| 006-进度与里程碑.md | 当前进度、里程碑、验收标准 | **所有人** |
| **[011-S2S3新功能接口契约-v1.0.md](011-S2S3新功能接口契约-v1.0.md)** | **S2-S3 新功能的权威契约（页面级资料绑定 / 版本迭代 / 互动导出）。008/009/010 已被本文替代** | **所有人（必读）** |
| ~~008-任务包-B-AI引擎-页面级资料绑定.md~~ | **已废**：被 011 模块 1 替代 | — |
| ~~009-任务包-A-Go后端-页面级资料绑定.md~~ | **已废**：被 011 模块 1 替代 | — |
| ~~010-任务包-C-前端-页面级资料绑定.md~~ | **已废**：被 011 模块 1 替代 | — |
| [重设计方案](../docs/design/skills/S2-S3-redesign-2026-09-intent-driven-binding.md) | 页面级绑定 + 意图自动绑定 + 三层确认门（011 的设计基线） | **所有人（必读）** |

> ⚠️ 008/009/010 是 v0.2 任务包，字段命名、错误码、信封格式已被 011（契约 v1.0）覆盖。
> 看到任何以这四个编号命名的 issue / PR，请先对照 011。

## 项目一句话

把现有的"泛雅 AI 智课系统"（讲授型课件 + 学生 Q&A）重构为 **"多模态 AI 互动式教学智能体"**（教师多轮对话 → 多模态资料融合 → 智能课件生成 → 预览修改 → 版本导出）。

## 架构总览

```
┌──────────┐    ┌──────────────────┐    ┌─────────────────────┐
│  Vue 3   │◄──►│    Go Backend    │◄──►│  Python AI Engine   │
│  Frontend│    │  Gin + GORM      │    │  FastAPI + LLM      │
│  (教师端) │    │  + Redis + MinIO │    │  + RAG (pgvector)   │
│  (学生端) │    │  + JWT           │    │  + 多模态解析        │
└──────────┘    └──────────────────┘    └─────────────────────┘
```

## 5 阶段总进度

```
Phase 1 [████████████████████] 100% ✅  项目现状分析与需求提取
Phase 2 [████████████████████] 100% ✅  4 Skill + 知识库架构设计
Phase 3 [████████████████████] 100% ✅  代码质量提升与解耦
Phase 4 [██░░░░░░░░░░░░░░░░░░░]  10%   Skill 实现开发 ← 本轮起点
        └─ 模块 1 页面级资料绑定 ✅（契约 v1.0 接口 1/2/3 已落代码 + 单测 + 真库集成）
        └─ 模块 2 版本迭代闭环   ⏳
        └─ 模块 3 互动+导出增强  ⏳
Phase 5 [░░░░░░░░░░░░░░░░░░░░]   0%    记录跟踪与收尾
```

## 4 Skill + KB 架构

```
教师输入
    ↓
[S1] 意图理解 ──→ 多轮对话 → 结构化意图摘要
    │
    ├──────────────────────────────────┐
    ↓                                  ↓
[S2] 多模态交互 ← 参考材料上传  [KB] 知识库 RAG ← 解析块摄入
    ↓ 解析/结构化/映射            ↓
    └──────────────┬──────────────┘
                   ↓
            [S3] 课件生成
              Outline → Nodes → PPTX/DOCX/互动
                   ↓
            [S4] 个性化满足
              预览 → 修改 → 版本 → 导出
```

## 新旧架构对比

### 原系统 vs 新系统

| 对比项 | 原系统（泛雅 AI 智课） | 新系统（多模态互动教学智能体） |
|-------|----------------------|---------------------------|
| **主要用户** | 学生为主，教师为辅 | 教师为主，智能体协作 |
| **核心目标** | 讲授与答疑 | 教学共创与课件生成 |
| **交互方式** | 播放中提问、续接 | 多轮对话、主动追问、再生成 |
| **主要输入** | 课件文件 | 教学意图 + 参考资料 + 知识库 |
| **主要输出** | 讲稿、答疑、进度 | PPT/Word 教案、互动内容、导出文件 |
| **AI 使用方式** | 解析、生成、问答 | 规划、追问、融合、生成、版本控制 |
| **架构形态** | 传统服务架构 | Agent 编排式工作流架构 |

### 7 层架构

```
 L1 [交互层]       教师端工作台 · 知识库维护页
                       ↓
 L2 [接入与会话层]  API Gateway · Conversation 会话管理 · Redis Session
                       ↓
 L3 [Agent 编排层]  Orchestrator · Planner · Memory · Version 版本管理
                       ↓
 L4 [工具层 Tool]   Upload · ParseDoc · ParseVideo · OCR · Index · Export
                       ↓
 L5 [知识与生成层]  RAG 检索与证据融合 · PPT/Word/互动生成 · 预览与反馈
                       ↓
 L6 [数据层]        Postgres · Redis · MinIO · 向量库
                       ↓
 L7 [外部 AI 能力]  LLM · VLM 多模态模型 · ASR · TTS
```

用一句话理解这 7 层：**Conversation 负责"聊明白"，Agent 负责"调度谁来干活"，Tool 负责"干脏活累活"，RAG 负责"找资料、找依据"，Generation 负责"写成课件"，Version 负责"留历史、可回滚"，Export 负责"交付文件"**。

## 跨层原则

| 原则 | 规则 |
|------|------|
| **层隔离** | Agent Orchestrator (Go) 分发任务；Skill 逻辑在 AI Engine (Python) 中。Skill 间不直接调用 |
| **默认异步** | 解析/生成/导出任务走 Redis 队列。API 立即返回 task_id，前端轮询 |
| **工具复用** | 上传、文档解析、视频解析、OCR、索引是共享工具层，不在 Skill 内重复 |
| **证据协议** | 每次生成调用接收 `evidence_packet`；输出携带 `citation_refs[]` |
| **版本边界** | 版本模块在生成/预览/导出后调用 — Skill 产生内容，版本模块快照 |

## 运行期约定（2026-09-23 起）

### 端口自动顺延

本机同时跑教师端（8082）、学生端（8081）、API 单体（18080）时，配置端口被占用是最常见的
启动失败原因。三个入口现在都通过 `backend/pkg/serveraddr.Serve` 自动顺延：

- **不会**终止占用端口的进程（避免误杀用户本地已起的服务）
- 首选端口被占 → 顺延 `+1`…`+99`，再不行交给系统分配
- 顺延后会在日志打 `WARN` 提示实际端口，并写入机器可读的端口公告
- 前端 dev server、CI、脚本想跟自动化，可读：

```
backend/.runtime/teacher.json   {"service":"teacher","port":8083,"started_at":"…"}
backend/.runtime/student.json   {"service":"student","port":8082,"started_at":"…"}
backend/.runtime/api.json       {"service":"api","port":18080,"started_at":"…"}
```

`.runtime/` 已被 `.gitignore` 忽略，是临时态，不要手动提交。

### 学生端配置路径回归（已修复）

`cmd/student/main.go` 的 `projectRoot` 多了一层 `filepath.Dir`，会指向仓库根目录而非 `backend/`，
于是 `resolveConfigFiles` 找不到 `backend/config/`、**不报错**而是返回空列表，配置静默退回
viper 默认值（`database.host=localhost` 而不是 docker 里的 `teaching-postgres`）。已修正为 3 层。
学生端在没有 `SERVER_PORT` / `config.yaml.server.port` 时也会回退到拆分前的 `8081`。

### 契约 v1.0 模块 1 已交付

`PUT/GET /api/v1/coursewares/:project_id/page-bindings` 与 `POST /api/v1/gen/modify` 的
`evidence_refs` / `page_id` / `user_instruction` / `citation_refs` / `evidence_used` 全部对齐
`011-S2S3新功能接口契约-v1.0.md`。验证三件套：

```
go test ./internal/handler -run TestPageBindings  -count=1   # 内存 store + 契约信封
go test ./internal/service -run TestPageBindings  -count=1   # gorm + 真实 PostgreSQL
COURSEWARE_PG_DSN=postgres://postgres:123456@127.0.0.1:25432/teaching_test?sslmode=disable \
  go test ./internal/handler -run TestPageBindingsHTTPOverPostgres -count=1 -v  # HTTP 端到端
```
