# Skill 2: 多模态交互 (Multimodal Interaction) — 详细设计

> 基于 Phase 2 工作流分析结果编写
> 最后更新: 2026-07-15

## 1. 概述

Skill 2 负责多模态参考材料的上传、解析、结构化提取，以及解析内容与教师教学意图之间的映射管理。它是教师工作台"资料上传"环节与 Agent Orchestrator"工具层"之间的衔接桥。

- **所属层级**: L4 工具层 + L5 知识层部分交界
- **依赖上游**: 意图摘要 (S1)、上传入口
- **产出下游**: RAG 入库、课件生成 (S3)、预览
- **现有基础**: PDF/PPTX 解析 (DocumentParser)、MinIO 对象存储、异步任务调度器

## 2. 架构与数据流

```
教师上传 / 系统导入
    |
    v
[文件上传器]  → 验证类型/大小 → MinIO 存储 → DB 记录
    |
    v
[任务调度器] → 根据类型分发：
    |
    +-- PDF -----> DocumentParser (PDF) -> 文本 + 结构
    +-- PPTX ----> DocumentParser (PPTX) -> 幻灯片结构
    +-- DOCX ----> WordParser (新增) ----> 章节文本
    +-- 图片 ----> OCR 引擎 (新增) -------> 文字 + 布局
    +-- 视频 ----> 视频处理器 (新增) -----> 关键帧 + ASR 字幕
    |
    v
[分块标准化器] → 统一块模型 (chunk schema)
    |
    v
[材料映射器] → 构建材料-块映射，关联意图 (intent_id)
    |
    v
+-------+--------+
|                |
v                v
RAG 索引       Agent Orchestrator
(向量化入库)   (提供解析上下文)
```

## 3. 接口契约

### POST /api/v1/tool/process

```json
{
  "session_id": "uuid",
  "intent_id": "uuid",
  "materials": [
    { "file_id": "uuid", "type": "pdf|docx|pptx|image|video", "url": "minio://..." }
  ]
}
→ {
  "task_id": "uuid",
  "status": "processing|done|failed"
}
```

### GET /api/v1/tool/status/:task_id

```json
→ {
  "status": "processing|done|failed",
  "result": {
    "parsed_chunks": [
      { "chunk_id": "uuid", "type": "text|table|image|frame",
        "content": "...", "page_ref": 3, "node_ref": "node-uuid" }
    ],
    "material_to_intent_map": { "file_id": ["chunk_id", ...] },
    "errors": []
  }
}
```

## 4. 内部模块

| 子模块 | 职责 | 文件 |
|--------|------|------|
| `file_uploader` | 接收文件，验证类型/大小，保存到 MinIO，创建 DB 记录 | `backend/handlers/upload.go` (扩展) |
| `doc_parser` | 解析 PDF/DOCX/PPTX 为页面级文本+结构 | `ai_engine/parse/doc.py` (扩展) |
| `video_processor` | 提取视频关键帧 + ASR 字幕 | `ai_engine/parse/video.py` (新增) |
| `ocr_engine` | 图片 OCR + 版面分析 | `ai_engine/parse/ocr.py` (新增) |
| `chunk_normalizer` | 统一所有解析输出为统一分块 schema | `ai_engine/parse/normalizer.py` (新增) |
| `material_mapper` | 构建材料-块的映射关系，关联意图 | `ai_engine/parse/mapper.py` (新增) |

## 5. 文件级状态机

```
每个文件的独立状态:
  [UPLOADED → PARSING → CHUNKED → INDEXED → DONE]
  [UPLOADED → PARSING → FAILED]

任务级状态（所有文件聚合）:
  [PENDING → PROCESSING → DONE | PARTIAL_FAIL]

失败处理: 每个文件重试 2 次，仍失败则标记 FAILED，继续处理其余文件
```

## 6. 各文件格式解析策略

| 格式 | 解析策略 | 第三方依赖 |
|------|---------|-----------|
| PDF | PyMuPDF (fitz) 提取文本 + 表格；pdfplumber 补充 | PyMuPDF, pdfplumber |
| PPTX | python-pptx 提取幻灯片文本 + 形状 + 备注 | python-pptx |
| DOCX | python-docx 提取段落 + 表格 + 样式 | python-docx |
| 图片 | OCR (PaddleOCR/Tesseract) + 版面分析 | paddleocr/tesseract |
| 视频 | FFmpeg 抽取关键帧 + Whisper ASR + VLM 理解 | ffmpeg, whisper, GLM-4V |

## 7. 依赖关系

- **依赖**: MinIO、FFmpeg、ASR 服务、VLM (GLM-4V)
- **依赖**: `parse-knowledge` 和 `reconstruct-document` 现有端点
- **被调用**: Agent Orchestrator（当意图含 `materials_refs` 时）
- **产出消费**: RAG 索引（块→向量化→存储）、生成器（块→上下文）

## 8. 现有代码复用

- **复用** `ai_engine/document_parser.py` 的 PDF/PPTX 解析
- **复用** Go 后端的 MinIO 上传管道
- **复用** `parse-knowledge` 端点结构
- **新增** 视频处理管道、Word 解析器、OCR 模块、分块标准化器
