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

## 3.1 SSE 流式解析接口（新增）

Python 端提供 `text/event-stream` 实时流式解析端点，支持分段推送进度和 Chunk。

### POST /api/v1/parse/stream-process

创建解析任务，以 SSE 流式返回进度+分块。**无需轮询，一请求即完整交付。**

```json
请求体（同 /api/v1/parse/process）:
{
  "session_id": "uuid",
  "file_paths": ["path/to/video.mp4", "path/to/doc.pdf"],
  "intent_id": "uuid"  // 可选
}
```

### GET /api/v1/parse/stream/{task_id}

对已存在的任务"接入"实时流。任务若已完成，立即返回所有数据。

### SSE 事件表

| 事件 | data 字段 | 触发时机 |
| --- | --- | --- |
| `task_start` | `{"task_id","file_count","files"}` | 任务创建成功 |
| `file_start` | `{"file_name","source_type"}` | 开始解析一个文件 |
| `file_chunk_batch` | `{"file_name","type","count","chunks"}` | 解析出一批同类原始块 |
| `file_done` | `{"file_name","chunk_count","normalized_chunks"}` | 单个文件解析完毕 |
| `file_error` | `{"file_name","error"}` | 单个文件解析失败 |
| `task_done` | `{"task_id","status","total_chunks","chunks"}` | 全部文件解析完毕 |
| `task_error` | `{"error"}` | 任务层面异常 |

### 事件流示例

```
event: task_start
data: {"task_id":"parse_abc123","file_count":2,"files":[{"file_name":"test4.mp4","source_type":"VIDEO"},{"file_name":"doc.pdf","source_type":"PDF"}]}

event: file_start
data: {"file_name":"test4.mp4","source_type":"VIDEO"}

event: file_chunk_batch
data: {"file_name":"test4.mp4","type":"video_meta","count":1,"chunks":[{"type":"video_meta","content":"文件: test4.mp4\n大小: 45.2MB\n时长: 120.5秒"}]}

event: file_chunk_batch
data: {"file_name":"test4.mp4","type":"frame","count":3,"chunks":[{"type":"frame","content":"画面是VS Code界面…","page":0,"metadata":{"timestamp_sec":0}},...]}

event: file_chunk_batch
data: {"file_name":"test4.mp4","type":"transcript","count":1,"chunks":[{"type":"transcript","content":"[0.0s-5.2s] 大家好…"}]}

event: file_done
data: {"file_name":"test4.mp4","chunk_count":5,"normalized_chunks":[{"chunk_id":"chunk_xxx","content":"…"},...]}

event: file_start
data: {"file_name":"doc.pdf","source_type":"PDF"}
...
event: file_done
data: {"file_name":"doc.pdf","chunk_count":8,...}

event: task_done
data: {"task_id":"parse_abc123","status":"done","total_chunks":13,"chunks":[...全部Chunk...]}
```

### 前端联调指南

```typescript
// 方式一：EventSource（推荐——自动重连，适合轮不到的起始状态）
const es = new EventSource("/api/v1/parse/stream/parse_abc123");

es.addEventListener("task_start", (e) => {
  const { task_id, file_count } = JSON.parse(e.data);
  showProgressBar(file_count);
});
es.addEventListener("file_start", (e) => {
  const { file_name } = JSON.parse(e.data);
  setCurrentFile(file_name);
});
es.addEventListener("file_chunk_batch", (e) => {
  const { file_name, type, count, chunks } = JSON.parse(e.data);
  appendChunks(type, chunks);  // 实时展示已解析的 Chunk
});
es.addEventListener("file_done", (e) => {
  const { file_name, normalized_chunks } = JSON.parse(e.data);
  markFileDone(file_name);
});
es.addEventListener("file_error", (e) => {
  const { file_name, error } = JSON.parse(e.data);
  showFileError(file_name, error);
});
es.addEventListener("task_done", (e) => {
  const { task_id, chunks } = JSON.parse(e.data);
  es.close();         // 关闭连接
  finishParse(chunks); // 得到全量 Chunk
});
es.addEventListener("task_error", (e) => {
  const { error } = JSON.parse(e.data);
  es.close();
  showError(error);
});

// 方式二：fetch ReadableStream（适合 POST /stream-process 场景）
const response = await fetch("/api/v1/parse/stream-process", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    session_id: "s1", file_paths: ["test4.mp4"],
  }),
});
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  // 按 "\\n\\n" 分割事件
  const parts = buffer.split("\n\n");
  buffer = parts.pop() || "";
  for (const part of parts) {
    const lines = part.split("\n");
    const eventLine = lines.find(l => l.startsWith("event: "));
    const dataLine = lines.find(l => l.startsWith("data: "));
    if (eventLine && dataLine) {
      const event = eventLine.slice(7);
      const data = JSON.parse(dataLine.slice(6));
      handleSseEvent(event, data);
    }
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
| PDF | Marker 转为高质量 Markdown（含 LaTeX 公式、表格） | marker-pdf |
| PPTX | Unstructured 提取结构化元素（标题、正文、图表、备注） | unstructured[pptx] |
| DOCX | Unstructured 提取段落 + 表格 + 样式 | unstructured[docx] |
| 图片 | PaddleOCR 文字识别 + 内置版面分析 | paddleocr |
| 视频 | FFmpeg 抽取关键帧 + Faster-Whisper ASR + Qwen-VL 视觉 Caption | faster-whisper, ffmpeg |

## 7. 依赖关系

- **系统依赖**: FFmpeg（含 ffprobe，用于视频抽帧与时长获取）
- **Python 依赖**:
  - `marker-pdf` — PDF → 高质量 Markdown（LaTeX 公式、表格）
  - `unstructured[pptx,docx]` — PPTX/DOCX 结构化元素提取
  - `paddleocr` — 图片 OCR 中文识别 + 版面分析
  - `faster-whisper` — 视频 ASR（比原版 Whisper 快 4-6 倍）
  - `minio` — MinIO 对象存储客户端
- **VLM**: Qwen-VL-Chat / Qwen-VL-Plus（通过 `AI_VLM_MODEL` 环境变量指定）
- **被调用**: Agent Orchestrator（当意图含 `materials_refs` 时）
- **产出消费**: RAG 索引（块→向量化→存储）、生成器（块→上下文）

## 8. 现有代码复用

- **复用** Go 后端的 MinIO 上传管道
- **复用** `parse-knowledge` 端点结构
- **替换** PDF/PPTX/DOCX 解析为 Marker + Unstructured（替代 PyMuPDF / python-pptx / python-docx）
- **替换** Whisper 为 Faster-Whisper（ASR 速度提升 4-6 倍）
- **新增** 视频处理管道、PaddleOCR 模块、分块标准化器
