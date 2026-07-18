# Skill 4: 个性化满足 (Personalization) — 详细设计

> 基于 Phase 2 工作流分析结果编写
> 最后更新: 2026-07-15

## 1. 概述

Skill 4 提供迭代优化闭环：教师预览生成内容、给出修改反馈（自然语言或结构化命令）、系统重新生成、版本历史追踪。满意后以标准格式导出。

- **所属层级**: L5 知识与生成层 + L6 应用层交界
- **核心能力**: 预览渲染、命令解析与节点修补、版本管理（历史/对比/回滚/锁定）、异步导出

## 2. 整体生命周期

```
[PREVIEW] → [MODIFYING] → [PREVIEW] → ... → [LOCKED] → [EXPORTING] → [DONE]
    ↑           |
    +-----------+

版本级别:
[V1(editable) → V2(editable) → ... → Vn(LOCKED)]
回滚: 克隆目标版本为新的可编辑版本
```

## 3. 接口契约

### 预览

```http
GET /api/v1/generation/:gen_id/preview
→ { "nodes": [...], "version": 3, "locked": false }
```

### 修改

```http
POST /api/v1/generation/:gen_id/modify
{
  "commands": [
    { "type": "update_node", "node_id": "...", "content": "..." },
    { "type": "swap_nodes", "node_ids": ["a", "b"] },
    { "type": "add_node", "after_node_id": "...", "content": "..." },
    { "type": "change_template", "template_id": "compact" }
  ]
}
→ { "task_id": "uuid", "new_version": 4, "status": "regenerating" }
```

### 版本管理

```http
GET /api/v1/version/:gen_id/history
→ { "versions": [{ "version": 1..N, "created_at", "summary", "locked": bool }] }

POST /api/v1/version/:gen_id/rollback
{ "target_version": 3 }
→ { "current_version": 3, "status": "done" }

POST /api/v1/version/:gen_id/lock
→ { "version": 5, "locked": true, "export_urls": { "ppt": "...", "doc": "..." } }
```

### 导出

```http
POST /api/v1/export/:gen_id
{ "format": "pptx|docx|both", "version": 5 }
→ { "task_id": "uuid", "status": "exporting" }

GET /api/v1/export/status/:task_id
→ { "status": "done", "download_url": "minio://exports/..." }
```

## 4. 内部模块

| 子模块 | 职责 | 文件 |
|--------|------|------|
| `preview_renderer` | 结构化节点 → HTML 预览 | `ai_engine/gen/preview.py` (重构) |
| `command_parser` | 解析并验证用户的修改命令 | `ai_engine/gen/commands.py` (新增) |
| `node_patcher` | 在节点级应用命令，触发需要的地方重新生成 | `ai_engine/gen/patch.py` (新增) |
| `version_manager` | 版本 CRUD、差异对比、回滚、锁定 | `backend/services/version.go` (新增) |
| `export_orchestrator` | 编排异步导出到 PPTX/DOCX，保存到 MinIO | `backend/services/export.go` (新增) |

## 5. 修改命令类型

| 命令类型 | 参数 | 处理方式 |
|----------|------|---------|
| `update_node` | `node_id`, `content` | 替换节点内容，可选标记 `regenerate` 触发 LLM 重写 |
| `swap_nodes` | `node_ids` [a, b] | 交换节点顺序 |
| `add_node` | `after_node_id`, `content`, `type` | 在指定节点后插入新节点 |
| `delete_node` | `node_id` | 移除节点及其子节点 |
| `change_template` | `template_id` | 切换样式模板，保留内容重新布局 |
| `merge_nodes` | `node_ids` | 合并多个节点内容 |
| `split_node` | `node_id`, `split_point` | 在指定位置拆分节点 |

## 6. 版本管理策略

```
versions 表结构:
- id, generation_id, version_number, nodes_snapshot (JSONB),
  summary (VARCHAR), locked (BOOL), created_at

diff 计算:
- 基于节点级 JSON diff，只存储变更的节点
- frontend 展示差异高亮

回滚:
- 读取目标版本的 nodes_snapshot
- 创建新版本 (version_number = max + 1)，内容为目标版
- 不修改原有版本链

锁定:
- `locked = true` 后版本不可编辑
- 锁定后自动触发导出选项可用
- 锁定的版本在任何用户环境持久可用
```

## 7. 依赖关系

- **依赖**: 生成模块（修改触发的重生成）
- **依赖**: 版本模块（历史、回滚、锁定 — Go 后端）
- **依赖**: 导出模块（异步文件生成 — Python + MinIO）
- **被调用**: 前端教师工作台
- **消耗**: 当前生成节点 + 用户编辑命令

## 8. 现有代码复用

- **复用** 现有 `TeacherEdit` 表结构做版本历史
- **复用** 现有 MinIO 上传/下载管道做导出存储
- **复用** 现有前端幻灯片组件的预览渲染
- **新增** 版本 DB schema、回滚逻辑、命令式修改管道、导出任务模型
