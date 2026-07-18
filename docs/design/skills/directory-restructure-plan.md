# 目录重构计划 (Directory Restructure Plan)

> 基于 Phase 2 工作流分析结果编写
> 最后更新: 2026-07-15

## 1. 重构原则

1. **向后兼容** — 不移动现有文件，新功能用新路径；两套路径共存至少 1 个版本
2. **渐进迁移** — 每天迁移 2-3 个文件，每完成一个就跑一次完整测试
3. **职责分层** — 每层只通过接口契约通信，不跨层引用实现
4. **一致性命名** — `kebab-case` 目录名 + `snake_case` 文件名
5. **死代码标记** — 明确识别废弃文件，加注释标记，不立即删除

## 2. 目标目录树

```
├── backend/                    # Go 后端
│   ├── cmd/
│   │   └── server/
│   │       └── main.go
│   ├── internal/
│   │   ├── config/             # 应用配置
│   │   ├── middleware/         # 中间件 (auth, cors, rate-limit)
│   │   ├── handler/           # HTTP 处理器 (gin)
│   │   │   ├── auth.go
│   │   │   ├── teacher.go     # → 拆分为 teacher_handler.go
│   │   │   ├── upload.go      # (扩展)
│   │   │   ├── conversation.go # (新增)
│   │   │   ├── generation.go  # (新增)
│   │   │   ├── version.go     # (新增)
│   │   │   ├── export.go      # (新增)
│   │   │   └── knowledge.go   # (新增)
│   │   ├── service/           # 业务逻辑
│   │   │   ├── auth_service.go
│   │   │   ├── teacher_service.go # → 拆分
│   │   │   ├── conversation.go    # (新增)
│   │   │   ├── version.go         # (新增)
│   │   │   ├── export.go          # (新增)
│   │   │   └── knowledge.go       # (新增)
│   │   ├── model/             # 数据库模型 (GORM)
│   │   ├── repository/        # (新增) 数据访问层
│   │   ├── router/            # 路由注册
│   │   └── pkg/               # 共享工具包
│   │       ├── minio/
│   │       ├── redis/
│   │       └── response/
│   └── go.mod
│
├── ai_engine/                  # Python AI Engine
│   ├── main.py                # FastAPI 入口 (路由精简)
│   ├── core/                  # (新增) 核心 LLM 调用、SSE 协议
│   │   ├── llm.py             # (从 qa.py 提取)
│   │   ├── sse.py             # SSE 流式协议
│   │   └── config.py
│   ├── intent/                # (新增) S1 意图理解
│   │   ├── router.py
│   │   ├── extractor.py
│   │   ├── fields.py
│   │   ├── confirm.py
│   │   └── prompts/
│   ├── parse/                 # (扩展) S2 多模态解析
│   │   ├── doc.py             # (现有 document_parser.py 重构)
│   │   ├── video.py           # (新增)
│   │   ├── ocr.py             # (新增)
│   │   ├── normalizer.py      # (新增)
│   │   └── mapper.py          # (新增)
│   ├── gen/                   # (重构) S3 课件生成
│   │   ├── outline.py         # (新增)
│   │   ├── node.py            # (从 generator.py 提取)
│   │   ├── modify.py          # (新增)
│   │   ├── export_ppt.py      # (新增)
│   │   ├── export_doc.py      # (新增)
│   │   ├── interactive.py     # (新增)
│   │   ├── preview.py         # (新增)
│   │   ├── commands.py        # (新增)
│   │   ├── patch.py           # (新增)
│   │   └── templates/         # (新增)
│   ├── rag/                   # (新增) 知识库 RAG
│   │   ├── chunker.py
│   │   ├── embed.py
│   │   ├── store.py
│   │   ├── retrieve.py
│   │   ├── rerank.py
│   │   └── evidence.py
│   └── requirements.txt
│
├── frontend/
│   ├── teacher/               # 教师端 (Vite)
│   │   └── src/
│   │       ├── router/        # (新增) Vue Router
│   │       ├── views/         # (新增) 路由页面
│   │       │   ├── Workspace.vue   # 主工作台
│   │       │   ├── Conversation.vue # 对话意图
│   │       │   ├── Materials.vue    # 资料管理
│   │       │   ├── Preview.vue      # 课件预览
│   │       │   └── Export.vue       # 导出
│   │       ├── components/    # (重组) 组件按域分组
│   │       │   ├── common/
│   │       │   ├── conversation/
│   │       │   ├── materials/
│   │       │   ├── generation/
│   │       │   └── export/
│   │       └── services/      # API 调用
│   ├── student/               # 学生端 (Vue CLI)
│   │   └── src/
│   │       └── ...
│   └── shared/                # (新增) 共享组件/工具
│
├── docs/                      # 文档
│   └── design/
│       └── skills/
│
└── scripts/                   # 工具脚本
```

## 3. 死代码识别

| 文件 | 行数 | 处理方式 |
|------|------|---------|
| `backend/internal/service/compat_student.go` | 2260 | 提取可用方法到新 service 文件后标记弃用 |
| `backend/internal/service/platform_sync_support.go` | 2033 | 检查是否仍在使用；若无，标记废弃 |
| `backend/internal/service/teacher.go` | 1798 | 拆分为 teacher_service.go + handler 片段 |
| `backend/internal/handler/*` | 31 | 已空，确认后删除 |
| `backend/internal/services/*` | 45 | 确认无引用后删除 |
| `backend/internal/models/*` | 39 | 确认无引用后删除 |
| `backend/*/test_workflow_*.go` | ~515 | 测试用工作流文件，确认后移至归档 |
| `frontend/src/` | 完整目录 | 与 teacher/src/ 和 student/src/ 重叠，确认后删除 |

## 4. 向后兼容策略

1. **重命名 vs. 新增**：
   - 大文件 → 新增小文件，提取方法，原文件保留但加 `@deprecated` 注释
   - 死代码 → 加 `// DEPRECATED: will be removed in v2.0` 标记

2. **API 路由**：
   - 旧路由保留 → 新路由加版本前缀 `/api/v2/`
   - 新旧路由都指向同一 handler（重构后）

3. **过渡期**：
   - 每天迁移 2-3 个文件
   - 每次迁移后跑 `go build ./...` + 回归测试
   - 两周后统一清理 `@deprecated` 标记的文件

## 5. 关键重构优先级

| 优先级 | 文件 | 操作 |
|--------|------|------|
| P0 | `compat_student.go` | 拆分为多个 service 文件：`dialogue.go`, `task.go`, `progress.go` |
| P0 | `teacher.go` | 提取 handler 和 service 逻辑，按业务域拆分 |
| P1 | `frontend/src/` 孤儿目录 | 确认是否被引用，无引用则归档 |
| P1 | AI Engine 目录重组 | 从 flat 平铺转为按域分组 (`intent/`, `gen/`, `rag/`) |
| P2 | `platform_sync_support.go` | 检查业务依赖，无依赖则标记废弃 |
| P2 | 测试工作流文件 | 归档到 `tests/legacy/` |
| P3 | `handlers/` 空目录 | 确认后删除 |
