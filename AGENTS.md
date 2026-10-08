# 多模态 AI 互动式教学智能体 — 项目全貌

> 本文件是项目的**完整启动说明书**。把它拖进任何 AI 工具（Claude Code 等），AI 读完就能理解整个项目并开始工作。
>
> 锐捷网络 · 服务外包赛题 A12 · 2026

---

## 第 1 章 · 项目身份卡

### 1.1 一句话

把现有的"泛雅 AI 智课系统"（讲授型课件 + 学生 Q&A）重构为 **"多模态 AI 互动式教学智能体"**（教师多轮对话 → 多模态资料融合 → 智能课件生成 → 预览修改 → 版本导出）。

### 1.2 基本信息

| 项目 | 说明 |
|------|------|
| 赛题编号 | A12 |
| 赛题名称 | 多模态 AI 互动式教学智能体 |
| 主办方 | 锐捷网络 |
| 技术架构 | Vue 3 前端 ↔ Go 1.22 后端 ↔ Python 3.10 AI Engine |
| 数据层 | PostgreSQL + Redis + MinIO |
| 原系统 | 泛雅 AI 智课系统（泛雅平台教学配套） |

### 1.3 代码规模

| 层 | 文件数 | 主要语言 |
|----|--------|---------|
| 后端 | 64 `.go` | Go + GORM + Gin |
| AI Engine | 19 `.py` | Python + FastAPI |
| 前端教师端 | 40 `.vue` | Vue 3 + Vite |
| 前端学生端 | 22 `.vue` | Vue 2 + Vue CLI |
| 文档 | 117 `.md` | Markdown |

### 1.4 仓库根目录快照

```
├── backend/              # Go 后端（API 网关 + 业务逻辑 + 数据层）
├── ai_engine/            # Python AI Engine（LLM / 解析 / 生成 / RAG）
├── frontend/
│   ├── teacher/          # 教师端（Vite + Vue 3）
│   └── student/          # 学生端（Vue CLI + Vue 2）
├── docs/
│   └── design/skills/    # 7 份 Skill 架构设计文档
├── 文档/                  # 方案任务包（6 份，给队友的）
├── 记录/                  # 决策日志 + 进度跟踪（内部用）
├── docs-selected/        # 比赛资料（评委手册摘录）
├── projects/             # 答辩 PPT 产物
├── scripts/              # 工具脚本
└── .gitignore
```

---

## 第 2 章 · 要解决什么

### 2.1 原系统 vs 新系统

| 对比项 | 原系统（泛雅 AI 智课） | 新系统（多模态互动教学智能体） |
|-------|----------------------|---------------------------|
| 主要用户 | 学生为主，教师为辅 | 教师为主，智能体协作 |
| 核心目标 | 讲授与答疑 | 教学共创与课件生成 |
| 交互方式 | 播放中提问、续接 | 多轮对话、主动追问、再生成 |
| 主要输入 | 课件文件 | 教学意图 + 参考资料 + 知识库 |
| 主要输出 | 讲稿、答疑、进度 | PPT/Word 教案、互动内容、导出文件 |
| AI 使用方式 | 解析、生成、问答 | 规划、追问、融合、生成、版本控制 |
| 架构形态 | 传统服务架构 | Agent 编排式工作流架构 |

### 2.2 原系统流程图

```
教师上传课件 → 解析为页面 → 生成讲授脚本 + 思维导图
                           ↓
学生播放课件 → 可以提问 → 系统答疑 + 记录薄弱点
                           ↓
                    进度续接（从上次中断点继续）
```

### 2.3 新系统流程图

```
教师输入需求 → 多轮对话澄清 → 上传多模态参考资料
                                    ↓
                          系统解析（PDF/PPTX/视频/图片）
                                    ↓
                          RAG 知识库检索 + 证据融合
                                    ↓
                          生成课件初稿（PPT/Word/互动）
                                    ↓
                          教师预览 → 修改命令 → 再生成
                                    ↓
                          锁定版本 → 导出成品
```

### 2.4 一句话总结

原系统解决的是"课件怎么讲、学生怎么问"，新系统解决的是"教师怎么把课件快速做出来、还能反复修改直到满意"。

---

## 第 3 章 · 系统架构

### 3.1 三层物理架构

```
┌──────────────────┐     HTTP REST     ┌──────────────────┐     HTTP REST     ┌─────────────────────┐
│   Vue Frontend   │ ◄──────────────► │   Go Backend     │ ◄──────────────► │   Python AI Engine  │
│  (教师端 + 学生端) │                   │  Gin + GORM      │                   │  FastAPI + LLM      │
│                   │                   │  + Redis + MinIO │                   │  + RAG (pgvector)   │
│                   │                   │  + JWT           │                   │  + 多模态解析        │
└──────────────────┘                   └──────────────────┘                   └─────────────────────┘
```

### 3.2 4 Skill + KB 逻辑架构

```
教师输入
    ↓
[S1] 意图理解 ──→ 多轮对话 → 结构化意图摘要
    │                               │
    ├───────────────────────────────┤
    ↓                               ↓
[S2] 多模态交互 ← 参考材料上传  [KB] 知识库 RAG ← 解析块摄入
    ↓ 解析/结构化/映射            ↓ 证据融合
    └──────────────┬──────────────┘
                   ↓
            [S3] 课件生成
              Outline → Nodes → PPTX/DOCX/互动
                   ↓
            [S4] 个性化满足
              预览 → 修改 → 版本 → 导出
```

### 3.3 7 层逻辑分层

```
 L1 [交互层]       教师端工作台 · 知识库维护页        ← Vue Frontend
                       ↓
 L2 [接入与会话层]  API Gateway · Conversation · Redis Session  ← Go
                       ↓
 L3 [Agent 编排层]  Orchestrator · Planner · Memory · Version  ← Go
                       ↓
 L4 [工具层 Tool]   Upload · ParseDoc · ParseVideo · OCR · Export  ← Go + Python
                       ↓
 L5 [知识与生成层]  RAG · PPT/Word/互动生成 · 预览与反馈  ← Python
                       ↓
 L6 [数据层]        Postgres · Redis · MinIO · 向量库  ← 基础设施
                       ↓
 L7 [外部 AI 能力]  LLM · VLM 多模态 · ASR · TTS       ← 外部服务
```

一句话理解 7 层：**Conversation 负责"聊明白"，Agent 负责"调度谁来干活"，Tool 负责"干脏活累活"，RAG 负责"找资料、找依据"，Generation 负责"写成课件"，Version 负责"留历史、可回滚"，Export 负责"交付文件"**。

### 3.4 跨层原则

| 原则 | 规则 |
|------|------|
| **层隔离** | Agent Orchestrator (Go) 分发任务；Skill 逻辑在 AI Engine (Python) 中。Skill 间不直接调用 |
| **默认异步** | 解析/生成/导出任务走 Redis 队列。API 立即返回 task_id，前端轮询 |
| **工具复用** | 上传、文档解析、视频解析、OCR、索引是共享工具层，不在 Skill 内重复 |
| **证据协议** | 每次生成调用接收 `evidence_packet`；输出携带 `citation_refs[]` |
| **版本边界** | 版本模块在生成/预览/导出后调用 — Skill 产生内容，版本模块快照 |

### 3.5 完整数据流（教师操作→系统响应）

```
教师操作                      系统响应
─────────                   ────────
打开工作台                  → 加载对话界面 (GET /api/v1/conversations)
输入"帮我做排序算法课件"     → S1 开始收集字段，返回追问
回答"45分钟，大一计算机"     → S1 更新意图摘要，检测字段齐全
点击确认                    → S1→confirmed，生成 intent_id
上传教材 PDF                → S2 解析（异步），返回 task_id
查询解析状态                → S2 完成（轮询 GET /task_id）
点击生成课件                → S3 创建生成任务，返回 task_id
预览课件                    → S3 完成，返回 nodes[] 供预览
拖拽调整第 3 页顺序         → S4 接受 modify 命令，再生成
点击"锁定版本"              → S4 锁定版本，可选导出
导出 PPTX                  → Export 任务 → MinIO → 下载链接
```

---

## 第 4 章 · 代码全貌

### 4.1 后端 Go 目录结构 (`backend/`)

```
backend/
├── cmd/server/main.go       # 入口
├── internal/
│   ├── config/              # 配置管理
│   ├── middleware/           # 中间件（auth/cors/ratelimit）
│   ├── handler/             # HTTP 处理器（25+ 文件）
│   │   ├── auth.go
│   │   ├── teacher.go       # 1798 行 — 需拆分 ⚠️
│   │   ├── student.go       # 667 行
│   │   └── upload.go
│   ├── service/             # 业务逻辑层
│   │   ├── ai_engine_client.go  # AI Engine HTTP 客户端 (420 行)
│   │   ├── teacher.go       # 1798 行 — 需拆分 ⚠️
│   │   ├── compat_student.go    # 2260 行 — 需拆分 ⚠️
│   │   ├── platform_sync_support.go # 2033 行 — 待检查
│   │   ├── dialogue_support.go # 对话支持函数
│   │   └── models.go        # GORM 模型定义
│   ├── model/               # 数据模型（GORM）
│   ├── repository/          # 数据访问层
│   ├── router/              # 路由注册
│   └── pkg/                 # 共享工具
│       ├── minio/           # MinIO 操作封装
│       ├── redis/           # Redis 操作封装
│       └── response/        # 统一响应格式
├── go.mod
├── go.sum
└── config/                  # 配置文件
```

#### 关键文件说明

| 文件 | 行数 | 说明 |
|------|------|------|
| `internal/service/ai_engine_client.go` | 420 | Go ↔ Python 接口定义（8+1 个方法） |
| `internal/service/compat_student.go` | 2260 | **God Object** — 需拆分为 dialogue/task/progress |
| `internal/service/teacher.go` | 1798 | **God Object** — 需拆分 handler 和 service |
| `internal/service/platform_sync_support.go` | 2033 | 可能已废弃 — 需确认 |
| `internal/service/dialogue_support.go` | ~120 | 对话操作复用模板 |
| `internal/handler/teacher.go` | 1798 | 教师端 handler（和 service 有耦合） |

#### 死代码清单（已确认可清理）

| 文件 | 行数 | 说明 |
|------|------|------|
| `internal/handlers/` 整个目录 | 31 | 2 个 stub，用 `net/http` 而非 Gin，无引用 |
| `internal/services/` 整个目录 | 45 | 2 个 stub，无引用 |
| `internal/models/` 整个目录 | 39 | 3 个 struct，无引用 |
| `frontend/src/` 整个目录 | ~60 | 与 teacher/src、student/src 重叠 |

### 4.2 AI Engine Python 目录 (`ai_engine/`)

```
ai_engine/
├── main.py               # FastAPI 入口 (543 行)
├── schema.py             # 数据模型定义 (486 行)
├── generator.py          # 脚本/节点生成逻辑 (689 行) — 核心
├── qa.py                 # 问答 + LLM 调用封装
├── parser.py             # PDF/PPTX 文档解析 (297 行)
├── document_parser.py    # 另一份文档解析
├── reconstructor.py      # 文档重建
├── generate.py           # CLI 生成入口
├── ask.py                # CLI 问答入口
├── debug_harness.py      # 一键调试验收脚本
├── recommendation/
│   └── service.py        # 教辅推荐 (665 行)
└── tests/
    ├── test_core.py
    └── test_recommendation.py
```

#### 现有能力评估

| 能力 | 状态 | 说明 |
|------|------|------|
| PDF 解析 | ✅ 已有 | DocumentParser，页级结构化输出 |
| PPT 解析 | ✅ 已有 | 支持 pptx 幻灯片 + notes |
| 讲稿生成 | ✅ 已有 | LessonGenerator，按页输出脚本+导图 |
| 问答（含重讲） | ✅ 已有 | QAResponder，含 source_page / need_reteach |
| Markdown 三阶段生成 | ✅ 已有 | generate-from-markdown |
| 节点重构 | ✅ 已有 | reconstruct-document |
| 音频生成 | ✅ 已有 | mock / openai-tts |
| 知识点树解析 | ✅ 已有 | parse-knowledge |
| 视频解析 | ❌ 缺失 | 需新增（FFmpeg + Whisper） |
| Word 教案生成 | ❌ 缺失 | 需新增（python-docx） |
| PPT 成品导出 | ❌ 缺失 | 需新增（python-pptx） |
| 本地知识库 RAG | ❌ 缺失 | 需新增（pgvector） |

**已知代码 bug**：
- `ai_engine/generate.py` 第 16 行使用了 `os.getenv`，顶部缺少 `import os`
- `ai_engine/ask.py` 第 30 行同样缺少 `import os`

### 4.3 前端 Vue 目录 (`frontend/`)

```
frontend/
├── teacher/               # 教师端（Vite + Vue 3）
│   └── src/
│       ├── App.vue        # 2261 行 — 需拆分为路由视图
│       ├── components/    # 组件
│       └── ...
├── student/               # 学生端（Vue CLI + Vue 2）
│   └── src/
│       ├── App.vue        # 7408 行 — 暂不动
│       └── ...
└── src/                   # 孤儿目录 ⚠️ 待清理
    ├── components/
    │   ├── MistakeBook.vue
    │   └── RecordList.vue
    └── router/
```

#### AI 入场后建议阅读顺序

```
1. 先读：backend/internal/service/ai_engine_client.go   ← 接口契约（全局关键）
2. 再读：backend/internal/service/models.go              ← 数据模型
3. 再读：docs/design/skills/architecture-overview.md     ← 架构理解
4. 再读：ai_engine/main.py                               ← AI 入口
5. 再读：ai_engine/generator.py + qa.py                  ← 核心逻辑
6. 再读：backend/internal/service/compat_student.go      ← God Object（如有改动）
7. 选择性：docs/design/skills/S1~S4 + KB*.md             ← Skill 详细设计
```

---

## 第 5 章 · 4 Skill + KB 详细说明

### 5.1 S1 · 意图理解

**一句话**：教师输入需求 → 多轮对话追问 → 结构化意图摘要。

**会话状态机**：

```
collecting → clarifying → confirming → confirmed → locked
     ↑           ↑                          ↓
     └───────────┴── 教师新消息回到 collecting
```

| 状态 | 含义 |
|------|------|
| `collecting` | 收集信息中，字段不全 |
| `clarifying` | 追问中，部分字段已填 |
| `confirming` | 所有字段齐备，等待教师确认 |
| `confirmed` | 教师已确认意图 |
| `locked` | 生成请求已到达，不再接受修改 |

**核心接口**：
- `POST /api/v1/intent/extract` — 对话→结构化意图
- `POST /api/v1/intent/confirm` — 确认意图

**关键文件**：
- Go: `internal/service/dialogue_support.go`（复用已有对话模式）
- Python: `ai_engine/qa.py`（复用 LLM 调用封装）
- 新增: `ai_engine/intent/` 目录（extractor, fields, confirm）

**字段优先级**：`topic > duration_minutes > style > target_student > others`

**边界**：最多 8 轮澄清，超时 30 分钟自动终止。

### 5.2 S2 · 多模态交互

**一句话**：上传多模态资料 → 按类型解析 → 标准化分块 → 建立映射。

**文件状态机**（每个文件独立）：

```
UPLOADED → PARSING → CHUNKED → INDEXED → DONE
UPLOADED → PARSING → FAILED
```

**任务级状态**（多文件聚合）：`PENDING → PROCESSING → DONE | PARTIAL_FAIL`

**5 种格式解析策略**：

| 格式 | 解析策略 | 依赖 |
|------|---------|------|
| PDF | PyMuPDF + pdfplumber 提取文本+表格 | PyMuPDF, pdfplumber |
| PPTX | python-pptx 提取幻灯片文本+形状+备注 | python-pptx |
| DOCX | python-docx 提取段落+表格+样式 | python-docx |
| 图片 | PaddleOCR/Tesseract + 版面分析 | paddleocr / tesseract |
| 视频 | FFmpeg 抽帧 + Whisper ASR + VLM（可选） | ffmpeg, whisper |

**核心接口**：
- `POST /api/v1/parse/process` — 上传触发解析（异步）
- `GET /api/v1/parse/status/:task_id` — 查询解析状态
- `POST /api/v1/parse/video` — 视频专用解析

**关键文件**：
- 复用: `ai_engine/parser.py`、`ai_engine/document_parser.py`
- 新增: `ai_engine/parse/video.py`、`ocr.py`、`normalizer.py`、`mapper.py`

### 5.3 S3 · 课件生成

**一句话**：结构化意图 + 证据包 → 生成大纲 → LLM 逐节点生成 → 导出 PPTX/DOCX。

**三阶段生成管道**：

```
[EVIDENCE_GATHERING] ← 从 RAG 获取证据包
       ↓
[STRUCTURING] ← 构建大纲 (outline_builder)
       ↓
[GENERATING] ← LLM 逐节点生成 (可并行)
       ↓
[PREVIEW] ← 首版就绪
       ↓
[MODIFYING] ← 接受编辑命令
       ↓
[DONE] ← 锁定并导出
```

**核心接口**：
- `POST /api/v1/gen/create` — 创建生成任务
- `GET /api/v1/gen/status/:task_id` — 查询生成状态
- `POST /api/v1/gen/modify` — 修改节点
- `POST /api/v1/gen/export` — 导出课件

**7 个子模块**：

| 子模块 | 职责 | 文件 |
|--------|------|------|
| outline_builder | 从意图+证据生成大纲 | `ai_engine/gen/outline.py` |
| node_generator | LLM 逐节点生成 | `ai_engine/gen/node.py`（从 generator.py 重构）|
| ppt_exporter | 节点→.pptx | `ai_engine/gen/export_ppt.py` |
| doc_exporter | 节点→.docx | `ai_engine/gen/export_doc.py` |
| interactive_builder | 测验/投票/闪卡 | `ai_engine/gen/interactive.py` |
| template_manager | 样式模板管理 | `ai_engine/gen/templates/` |
| modification_engine | 节点级重生成 | `ai_engine/gen/modify.py` |

**关键文件**：主要复用 `ai_engine/generator.py` 的 `AIScriptGenerator` 类。

### 5.4 S4 · 个性化满足

**一句话**：预览课件 → 接受修改命令 → 版本管理 → 锁定导出。

**整体生命周期**：

```
[PREVIEW] → [MODIFYING] → [PREVIEW] → ... → [LOCKED] → [EXPORTING] → [DONE]
    ↑           |
    +-----------+
```

**版本生命周期**：

```
V1(editable) → V2(editable) → ... → Vn(LOCKED)
回滚: 克隆目标版本为新的可编辑版本
```

**7 种修改命令**：

| 命令 | 参数 | 处理方式 |
|------|------|---------|
| `update_node` | node_id, content | 替换内容，可选 LLM 重写 |
| `swap_nodes` | node_ids [a, b] | 交换顺序 |
| `add_node` | after_node_id, content | 插入新节点 |
| `delete_node` | node_id | 移除节点 |
| `change_template` | template_id | 切换样式模板 |
| `merge_nodes` | node_ids | 合并内容 |
| `split_node` | node_id, split_point | 拆分节点 |

**核心接口**：
- `GET /api/v1/versions/:gen_id/history` — 版本历史
- `POST /api/v1/versions/:gen_id/rollback` — 回滚
- `POST /api/v1/versions/:gen_id/lock` — 锁定
- `POST /api/v1/exports/:gen_id` — 导出
- `GET /api/v1/exports/status/:job_id` — 导出状态

**关键文件**：新增 `backend/internal/service/version_service.go`、`export_service.go`

### 5.5 KB · 知识库 RAG

**一句话**：文档分块 → 向量化 → 混合检索 → 证据融合 → 提供给生成使用。

**完整流程**：

```
文档 → 分块管道 → 嵌入 API → pgvector 存储
                                ↓
查询 → 混合检索(vector 0.7 + BM25 0.3) → top-20
                                ↓
                         重排序(cross-encoder) → top-5
                                ↓
                     LLM 合成 → evidence_packet
```

**分块策略**：

| 文档类型 | 策略 | 块大小 | 重叠 |
|----------|------|--------|------|
| PDF (教材) | 按段落+标题层级 | 512 tokens | 64 |
| PPTX (课件) | 按幻灯片 | 每张独立 | 0 |
| DOCX (教案) | 按章节 | 512 tokens | 64 |
| 图片 (OCR) | 按版面区域 | 图片块 | 0 |
| 视频 (ASR) | 按时间窗口 | 30s | 5s |

**混合检索公式**：`score = 0.7 × cosine_sim(embedding(q), embedding(chunk)) + 0.3 × bm25_score(q, chunk)`

**质量阈值**：`min_score = 0.6`，低于此阈值的结果丢弃。

**向量数据库**：pgvector（PostgreSQL 扩展，无需额外部署）

**核心接口**：
- `POST /api/v1/rag/search` — 知识检索
- `POST /api/v1/rag/evidence` — 证据融合（供生成用）
- `POST /api/v1/knowledge/upload` — 文档上传索引

**关键文件**：新增 `ai_engine/rag/` 全套 6 模块（chunker, embed, store, retrieve, rerank, evidence）

---

## 第 6 章 · 数据模型与接口契约

### 6.1 通用数据模型

**IntentSummary（结构化意图）**：
```json
{
  "topic": "string | null",
  "duration_minutes": "integer | null",
  "style": "string | null",
  "target_student": "string | null",
  "knowledge_points": ["string"],
  "output_format": ["ppt", "doc", "both"],
  "with_interactive": "boolean",
  "key_difficulties": ["string"],
  "expected_outcomes": ["string"],
  "missing_fields": ["string"]
}
```

**TeachingNode（教学节点）**：
```json
{
  "node_id": "string",
  "title": "string",
  "type": "slide | section | quiz",
  "content": "string",
  "page_ref": "integer",
  "source_pages": ["integer"],
  "summary": "string",
  "core_points": ["string"],
  "examples": ["string"],
  "estimated_duration": "integer",
  "next_node_id": "string | null"
}
```

**EvidencePacket（证据包）**：
```json
{
  "relevant_chunks": [{"chunk_id": "string", "content": "string", "score": "float"}],
  "synthesized_context": "string",
  "citations": [{"chunk_id": "string", "text_snippet": "string", "source_ref": "string"}]
}
```

**Chunk（分块）**：
```json
{
  "chunk_id": "string",
  "source_type": "pdf | pptx | docx | image | video",
  "content": "string",
  "page_ref": "integer | null",
  "metadata": {},
  "embedding": ["float | null"]
}
```

**Version（版本）**：
```json
{
  "id": "string",
  "generation_id": "string",
  "version_number": "integer",
  "nodes_snapshot": {},
  "summary": "string",
  "locked": "boolean",
  "created_at": "datetime"
}
```

**ExportJob（导出任务）**：
```json
{
  "id": "string",
  "gen_id": "string",
  "format": "pptx | docx | both",
  "status": "pending | exporting | done | failed",
  "minio_path": "string | null",
  "created_at": "datetime"
}
```

### 6.2 API 端点速查

#### S1 意图理解

| 方法 | 路径 | 说明 | 异步 |
|------|------|------|------|
| POST | `/api/v1/intent/extract` | 对话历史→结构化意图 | 否 |
| POST | `/api/v1/intent/confirm` | 确认意图摘要 | 否 |

#### S2 多模态交互

| 方法 | 路径 | 说明 | 异步 |
|------|------|------|------|
| POST | `/api/v1/parse/process` | 上传文件触发解析 | ✅ |
| GET | `/api/v1/parse/status/:task_id` | 查询解析状态 | 否 |
| POST | `/api/v1/parse/video` | 视频专用解析 | ✅ |

#### KB 知识库

| 方法 | 路径 | 说明 | 异步 |
|------|------|------|------|
| POST | `/api/v1/rag/search` | 知识检索 | 否 |
| POST | `/api/v1/rag/evidence` | 证据融合（供生成用） | 否 |
| POST | `/api/v1/knowledge/upload` | 文档上传索引 | ✅ |
| GET | `/api/v1/knowledge/status/:task_id` | 查询索引状态 | 否 |

#### S3 课件生成

| 方法 | 路径 | 说明 | 异步 |
|------|------|------|------|
| POST | `/api/v1/gen/create` | 创建生成任务 | ✅ |
| GET | `/api/v1/gen/status/:task_id` | 查询生成状态 | 否 |
| GET | `/api/v1/gen/preview/:gen_id` | 获取预览内容 | 否 |
| POST | `/api/v1/gen/modify` | 修改节点 | ✅ |
| POST | `/api/v1/gen/export` | 导出课件 | ✅ |

#### S4 个性化满足

| 方法 | 路径 | 说明 | 异步 |
|------|------|------|------|
| GET | `/api/v1/versions/:gen_id/history` | 版本历史 | 否 |
| POST | `/api/v1/versions/:gen_id/rollback` | 回滚 | 否 |
| POST | `/api/v1/versions/:gen_id/lock` | 锁定版本 | 否 |
| GET | `/api/v1/exports/status/:job_id` | 导出状态 | 否 |

### 6.3 Agent ↔ Tool 调用协议

**通用请求体**：
```json
{
  "tool_name": "parse_document | parse_video | generate_script | ...",
  "request_id": "req_xxx",
  "payload": {}
}
```

**通用响应体**：
```json
{
  "ok": true,
  "tool_name": "parse_document",
  "tool_version": "v1",
  "request_id": "req_xxx",
  "data": {},
  "error": ""
}
```

**接口版本规则**：字段只增不删，废弃先标记 deprecated 保留一个迭代周期。

### 6.4 数据库

#### 已有表（10 张，直接复用）

| 表名 | 用途 |
|------|------|
| courses | 课件主表 |
| course_pages | 页级内容 |
| teaching_nodes | 节点化讲授内容 |
| teaching_node_relations | 节点关系图 |
| mind_map_nodes | 导图节点 |
| dialogue_sessions | 会话主表 |
| dialogue_turns | 会话轮次 |
| question_logs | 提问日志 |
| user_progresses | 学习进度 |
| weak_points | 薄弱点 |

#### 新增表（9 张）

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| conversation_summaries | 需求结构化摘要 | conversation_id, summary_json, status |
| material_assets | 参考资料元信息 | owner_id, file_url, file_type, parse_status |
| material_mappings | 资料与意图映射 | conversation_id, material_id, target_knowledge |
| generation_versions | 生成版本主表 | course_id, version_no, parent_version_id, status |
| generation_contents | 版本内容明细 | version_id, content_type, content_json |
| export_jobs | 导出任务 | version_id, formats, status, output_url |
| rag_documents | 知识库文档 | source_type, source_ref, status |
| rag_chunks | 切片内容 | document_id, chunk_text, chunk_index, embedding_ref |
| rag_retrieval_logs | 检索日志 | request_id, query_text, hit_chunks, latency_ms |

---

## 第 7 章 · 怎么跑起来

### 7.1 环境要求

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| Go | 1.22+ | 后端 |
| Python | 3.10+ | AI Engine |
| Node.js | 18+ | 前端 |
| PostgreSQL | 14+ | 主数据库（含 pgvector 扩展） |
| Redis | 6+ | 会话缓存 + 任务队列 |
| MinIO | 最新 | 对象存储 |
| FFmpeg | 最新 | 视频处理（可选，S2 用） |

### 7.2 启动命令

**Go 后端**：
```bash
cd backend
go mod tidy
go run cmd/server/main.go
# 默认监听 :8080
```

**Python AI Engine**：
```bash
cd ai_engine
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# 默认监听 :8000
```

**前端教师端**：
```bash
cd frontend/teacher
npm install
npm run dev
# 默认监听 :5173
```

**前端学生端**：
```bash
cd frontend/student
npm install
npm run serve
```

### 7.3 服务间关系

```
教师端 :5173  ──HTTP──►  后端 :8080  ──HTTP──►  AI Engine :8000
学生端 :8081  ──HTTP──►  后端 :8080
```

### 7.4 比赛资料位置

| 路径 | 内容 |
|------|------|
| `docs-selected/` | 评委手册摘录（比赛参考资料） |
| `projects/` | 答辩 PPT 产物 |
| `docs/design/skills/` | 7 份 Skill 架构设计文档 |
| `记录/` | 决策日志 + 进度跟踪 |
| `文档/` | 方案任务包（团队分工用） |

---

## 附录 A · 文件映射速查

### A.1 Go 后端关键文件

```
backend/internal/service/ai_engine_client.go   ← Go ↔ Python 接口定义（必读）
backend/internal/service/models.go             ← 数据模型定义
backend/internal/service/compat_student.go     ← God Object（2260 行）
backend/internal/service/teacher.go            ← God Object（1798 行）
backend/internal/service/dialogue_support.go   ← 对话复用模板
backend/internal/handler/teacher.go            ← 教师端 handler
backend/internal/handler/student.go            ← 学生端 handler
backend/internal/handler/upload.go              ← 上传处理器
backend/internal/middleware/auth.go             ← 鉴权中间件
backend/internal/router/router.go              ← 路由注册
```

### A.2 Python AI Engine 关键文件

```
ai_engine/main.py          ← FastAPI 入口，所有路由
ai_engine/generator.py     ← 课件生成核心逻辑（必读）
ai_engine/qa.py            ← 问答 + LLM 调用封装
ai_engine/parser.py        ← 文档解析（PDF/PPTX）
ai_engine/document_parser.py ← 另一份文档解析
ai_engine/reconstructor.py ← 文档重建
ai_engine/schema.py        ← 数据模型
ai_engine/recommendation/service.py ← 教辅推荐
```

### A.3 Vue 前端关键文件

```
frontend/teacher/src/App.vue          ← 教师端入口（2261 行）
frontend/student/src/App.vue          ← 学生端入口（7408 行）
frontend/teacher/src/components/      ← 教师端组件
frontend/student/src/components/      ← 学生端组件
```

### A.4 设计文档

```
docs/design/skills/architecture-overview.md     ← 架构总览
docs/design/skills/S1-intent-understanding.md   ← S1 详细设计
docs/design/skills/S2-multimodal-interaction.md ← S2 详细设计
docs/design/skills/S3-courseware-generation.md  ← S3 详细设计
docs/design/skills/S4-personalization.md        ← S4 详细设计
docs/design/skills/KB-knowledge-base.md         ← KB 详细设计
docs/design/skills/directory-restructure-plan.md ← 目录重构计划
```

---

## 附录 B · 依赖关系总图

```
Skill 间依赖（→ 表示"被依赖"）:
  S1(意图理解) → S3(课件生成) → S4(个性化满足)
  S2(多模态交互) → KB(知识库) → S3
  
模块间依赖:
  Conversation 依赖: LLM, Redis, Postgres
  Agent 依赖: Conversation, Tool Layer, RAG, Version
  Tool Layer 依赖: MinIO, FFmpeg, ASR, OCR
  Generation 依赖: LLM, RAG(evidence_packet)
  RAG 依赖: 向量库(pgvector), Embedding API
  Version 依赖: Postgres, Generation
  Export 依赖: MinIO, Generation
```

---

## 附录 C · 项目 5 阶段总览

```
Phase 1 [████████████████████] 100% ✅  项目现状分析与需求提取
Phase 2 [████████████████████] 100% ✅  4 Skill + 知识库架构设计
Phase 3 [░░░░░░░░░░░░░░░░░░░░]   0%    代码质量提升与解耦
Phase 4 [░░░░░░░░░░░░░░░░░░░░]   0%    Skill 实现开发
Phase 5 [░░░░░░░░░░░░░░░░░░░░]   0%    记录跟踪与收尾
```

## Agent skills

### Issue tracker

Issues are tracked as local Markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default canonical triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository using root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.
