# 4 Skill + 知识库 — 架构总览与依赖关系

> 基于 Phase 2 工作流分析结果编写
> 最后更新: 2026-07-15

## 1. 总体流程

```
教师输入
    ↓
[S1] 意图理解 ──→ 多轮对话 → 结构化意图摘要
    │
    ├──────────────────────────────────────────┐
    ↓                                          ↓
[S2] 多模态交互 ← 参考材料上传    [KB] 知识库 RAG ← 解析块摄入
    ↓ 解析/结构化/映射              ↓                     
    │                          证据融合                   
    └──────────────┬──────────────┘
                   ↓
            [S3] 课件生成
              Outline → Nodes → PPTX/DOCX/互动
                   ↓
            [S4] 个性化满足
              预览 → 修改 → 版本 → 导出
```

## 2. 跨层架构原则

| 原则 | 规则 |
|------|------|
| **层隔离** | Agent Orchestrator (Go) 分发任务；Skill 逻辑在 AI Engine (Python) 中。Skill 间不直接调用 — 路由经 Orchestrator |
| **默认异步** | 解析/生成/导出任务走 Redis 任务队列。API 立即返回 task_id，前端轮询状态 |
| **工具复用** | 上传、文档解析、视频解析、OCR、索引是共享工具层模块，不在 Skill 内重复 |
| **证据协议** | 每次生成调用接收结构化的 `evidence_packet`；每个生成输出携带 `citation_refs[]` |
| **版本边界** | 版本模块在生成/预览/导出后调用 — Skill 产生内容，版本模块快照 |

## 3. Skill 间依赖关系

```
                        ┌─────────────────────┐
                        │  Agent Orchestrator  │  (Go)
                        └──────┬──────┬───────┘
                               │      │
                    ┌──────────┘      └──────────┐
                    ▼                              ▼
           ┌────────────────┐           ┌─────────────────┐
           │ S1 Intent      │──┐        │ S2 Multimodal   │
           │ Understanding  │  │        │ Interaction      │
           └────────────────┘  │        └────────┬────────┘
                    │          │                 │
                    ▼          │                 ▼
           ┌────────────────┐  │        ┌─────────────────┐
           │ Structured     │  │        │ Chunks +         │
           │ Intent         │  │        │ Material Map     │
           └───────┬────────┘  │        └────────┬────────┘
                   │           │                 │
                   ▼           │                 ▼
           ┌─────────────────────────────────────────┐
           │  ┌──────────────────────────────────┐   │
           │  │   KB Knowledge Base (RAG)        │   │
           │  │  Index chunks → Retrieve → Re-rank│   │
           │  └──────────────────────────────────┘   │
           └──────────────────┬──────────────────────┘
                              │ evidence_packet
                              ▼
           ┌─────────────────────────────────────────┐
           │   S3 Courseware Generation              │
           │  Outline → Nodes → PPTX/DOCX/Interactive│
           └──────────────────┬──────────────────────┘
                              │ generation_id
                              ▼
           ┌─────────────────────────────────────────┐
           │   S4 Personalization                    │
           │  Preview → Modify → Version → Export     │
           └─────────────────────────────────────────┘
```

## 4. 扩展映射

### Go 后端扩展

| 模块 | 操作 | 关键新增 |
|------|------|---------|
| API Gateway | 扩展 | 新增 conversation, generation, version, export, kb 路由 |
| Task Queue | 扩展 | 新增 parse, generate, vectorize, export 任务类型 |
| Session | 扩展 | 会话摘要持久化、意图缓存 |
| Version | 新增 | `versions` 表、回滚 API、锁定 API |
| Export | 新增 | `export_jobs` 表、状态轮询、MinIO 集成 |
| Knowledge | 新增 | 知识库 CRUD、文档元数据管理 |

### Python AI Engine 扩展

| 模块 | 操作 | 关键新增 |
|------|------|---------|
| intent/ | 新增 | router, extractor, confirm, field collector |
| parse/ | 扩展 | video.py, ocr.py, normalizer.py, mapper.py |
| gen/ | 重构+扩展 | 拆分 generator.py, 新增 export_ppt/doc, interactive |
| rag/ | 新增 | chunker, embed, store, retrieve, rerank, evidence |
| core/ | 新增 | 精简 main.py，提取 LLM 调用、SSE、配置到 core/ |
