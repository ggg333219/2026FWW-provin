# Skill 3: 课件生成 (Courseware Generation) — 详细设计

> 基于 Phase 2 工作流分析结果编写
> 最后更新: 2026-07-15

## 1. 概述

Skill 3 是核心生成管道：接收确认后的教学意图 + 知识库证据包 + 解析后的材料块，生成结构化课件内容，并导出为 PPT / Word / 互动内容格式。

- **所属层级**: L5 知识与生成层
- **输入**: `structured_intent` + `evidence_packet` + `parsed_chunks`
- **输出**: 结构化节点数组 (slides/sections/quizzes) → 导出文件
- **现有基础**: `ai_engine/generator.py` 脚本/节点生成逻辑、`TeachingNode` 和 `CoursePage` 内容模型

## 2. 三阶段生成管道

```
[INTENT_LOCKED] 
    ↓
[EVIDENCE_GATHERING] ← 从 RAG 获取证据包
    ↓
[STRUCTURING]   ← 构建大纲/目录 (outline_builder)
    ↓
[GENERATING]    ← LLM 逐节点生成内容 (node_generator, 可并行)
    ↓
[PREVIEW]       ← 首版就绪，等待教师审阅
    ↓
[MODIFYING]     ← 接受编辑命令 (更新节点/调整顺序/换风格)
    ↓
[DONE]          ← 锁定并导出/Skill 4 接管
```

## 3. 接口契约

### POST /api/v1/generation/create

```json
{
  "session_id": "uuid",
  "intent": { /* 来自 S1 */ },
  "evidence_packet": { /* 来自 RAG */ },
  "template_id": "default|compact|creative"
}
→ {
  "task_id": "uuid",
  "status": "generating",
  "generation_type": "ppt|doc|interactive"
}
```

### GET /api/v1/generation/status/:task_id

```json
→ {
  "status": "generating|preview|done|failed",
  "current_node": "title-slide",
  "progress_pct": 45,
  "preview_url": null | "minio://.../preview.html",
  "result": null | {
    "generation_id": "uuid",
    "nodes": [
      { "node_id": "uuid", "type": "slide|section|quiz",
        "title": "...", "content": "...", "page_ref": 1 }
    ],
    "file_urls": { "ppt": "minio://...", "doc": "minio://..." },
    "citation_refs": ["chunk_id", ...]
  }
}
```

## 4. 内部模块

| 子模块 | 职责 | 文件 |
|--------|------|------|
| `outline_builder` | 从意图 + 证据生成课件大纲/TOC | `ai_engine/gen/outline.py` (新增) |
| `node_generator` | LLM 逐节点生成内容 (可按节点并行) | `ai_engine/gen/node.py` (从现有 `generator.py` 重构) |
| `ppt_exporter` | 结构化节点 → .pptx (python-pptx) | `ai_engine/gen/export_ppt.py` (新增) |
| `doc_exporter` | 结构化节点 → .docx (python-docx) | `ai_engine/gen/export_doc.py` (新增) |
| `interactive_builder` | 生成测验/投票/闪卡互动内容 | `ai_engine/gen/interactive.py` (新增) |
| `template_manager` | 加载/管理 PPT/DOC 样式模板 | `ai_engine/gen/templates/` (新增) |
| `modification_engine` | 接受节点级部分重生成命令 | `ai_engine/gen/modify.py` (新增) |

## 5. 生成状态机

```
[INTENT_LOCKED → EVIDENCE_GATHERING → STRUCTURING → GENERATING → PREVIEW → MODIFYING → DONE]
                                               ↓                        ↓
                                           [REGENERATE]          [VERSION_SNAPSHOT]
```

- **STRUCTURING**: 从意图 + 证据构建大纲
- **GENERATING**: LLM 生成每节点内容（可按节点并行化）
- **PREVIEW**: 首版就绪供教师审阅
- **MODIFYING**: 接受编辑命令（更新节点/交换顺序/切换风格）
- **VERSION_SNAPSHOT**: 每次预览锁定时调用，由版本模块管理

## 6. PPT 导出架构

```
Structured Nodes
    ↓
template_manager.load(template_id)
    ↓
ppt_exporter.create_presentation(template_path)
    ↓
for each node:
    slide_type = node.type  # title, content, two_column, quiz
    slide_layout = template.get_layout(slide_type)
    ppt_exporter.populate_slide(slide, node.content)
    ↓
ppt_exporter.save(output_path)
    ↓
upload_to_minio(file_path)
    ↓
return download_url
```

Word 导出类似架构，使用 python-docx 逐节构建。

## 7. 依赖关系

- **依赖**: LLM 服务、RAG evidence_packet、模板资产
- **依赖**: python-pptx, python-docx 库
- **依赖**: 版本模块（预览事件后调用）
- **被调用**: Agent Orchestrator
- **消耗**: S1 的 `structured_intent`、RAG 的 `evidence_packet`

## 8. 现有代码复用

- **复用** `ai_engine/generator.py` 的脚本/节点内部生成逻辑
- **复用** 现有 `TeachingNode` 和 `CoursePage` 内容模型
- **复用** 现有 Go 模板渲染模式 (template.go) 的思路
- **新增** PPTX/DOCX 导出器、互动内容构建器、模板系统、修改引擎
