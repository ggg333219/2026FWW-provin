# Chunk Schema — S2 多模态解析标准输出

> 基于真实解析输出（test4.mp4）编写
> 最后更新: 2026-07-23

## 概述

`Chunk` 是 S2 多模态解析模块的**标准化输出单元**。所有来源（PDF/PPTX/DOCX/图片/视频/音频）最终都归一为 `Chunk` 模型，供下游 KB 知识库 RAG 和 S3 课件生成消费。

- **定义位置**: `ai_engine/core/schema.py` → `Chunk` class
- **生产者**: `task_manager.py` → `_chunk_normalizer.normalize()`
- **消费者**: KB 向量化索引、Agent Orchestrator、S3 OutlineBuilder

---

## Chunk 字段定义

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `chunk_id` | `string` | 是 | 全局唯一 ID，格式 `chunk_{uuid_hex[:12]}` |
| `source_type` | `string` | 是 | 来源类型：`pdf` / `pptx` / `docx` / `image` / `video` / `audio` / `text` |
| `source_ref` | `string` | 是 | 来源标识，如文件绝对路径或 MinIO URL |
| `content` | `string` | 是 | 解析后的文本内容。视频：字幕文本；文档：Markdown 文本；图片：OCR 文字 |
| `page_ref` | `int` 或 `null` | 否 | 页码引用（文档/图片）；视频统一为 `0` |
| `seq_index` | `int` | 是 | 在文件中的顺序索引（从 0 递增） |
| `metadata` | `object` | 是 | 额外元数据，**按 source_type 不同结构不同**（见下方） |
| `embedding` | `array[float]` 或 `null` | 否 | 向量化嵌入，入库后填充；未向量化时为 `null` |

---

## 按 source_type 的 metadata 结构

### video / audio

```json
{
  "chunk_id": "chunk_b31be2b6673d",
  "source_type": "video",
  "source_ref": "D:/videos/test4.mp4",
  "content": "文件: test4.mp4\n大小: 27.97MB\n时长: 159.03秒\n",
  "page_ref": 0,
  "seq_index": 0,
  "metadata": {
    "source_type": "video",
    "file_name": "test4.mp4",
    "file_size": 29333739,
    "file_size_mb": 27.97,
    "duration_sec": 159.03,
    "duration_method": "python_parser"
  },
  "embedding": null
}
```

#### metadata 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `source_type` | `string` | 冗余来源类型标签，取值 `video` / `audio` |
| `file_name` | `string` | 文件名（含扩展名） |
| `file_size` | `int` | 文件大小（字节） |
| `file_size_mb` | `number` | 文件大小（MB，保留 2 位小数） |
| `duration_sec` | `number` | 媒体时长（秒） |
| `duration_method` | `string` | 时长获取方式：`ffprobe`（优先）或 `python_parser`（降级） |
| `width` / `height` | `int` | 分辨率（仅当 ffprobe 可用时出现） |

---

### transcript（视频/音频 ASR 字幕识别）

从视频/音频提取的语音识别结果，由 `VideoProcessor._transcribe()` 产出。

```json
{
  "chunk_id": "chunk_9cdffb040add",
  "source_type": "video",
  "source_ref": "D:/videos/test4.mp4",
  "content": "[0.0s-3.7s] VS Code 可以不要了,但这四个 AI 制作工具,你必须知道。\n[3.7s-9.9s] 作为靠 AI 硬盘上的把自己分成五个员工的内容创业者...\n",
  "page_ref": 0,
  "seq_index": 1,
  "metadata": {
    "source": "faster-whisper",
    "model": "medium",
    "segment_count": 43,
    "segments": [
      {
        "start": 0,
        "end": 3.68,
        "text": "Open Claw 可以不要了,但这四个 AI 制作工具,你必须知道。"
      },
      {
        "start": 3.68,
        "end": 9.88,
        "text": "作为靠 AI 硬盘上的把自己分成五个员工的内容创业者,，这些工具都是我们的血和泪筛选出来的。"
      }
    ],
    "llm_corrected": true
  },
  "embedding": null
}
```

#### content 格式

每行一条字幕，格式：
```
[{start_sec:.1f}s-{end_sec:.1f}s] {text}
```

示例：
```
[0.0s-3.7s] VS Code 可以不要了,但这四个 AI 制作工具,你必须知道。
[3.7s-9.9s] 作为靠 AI 硬盘上的把自己分成五个员工的内容创业者...
```

#### metadata 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `source` | `string` | ASR 引擎，当前始终为 `faster-whisper` |
| `model` | `string` | Whisper 模型尺寸，如 `medium` / `base` / `large-v3` |
| `segment_count` | `int` | 时间片段总数 |
| `segments` | `array[object]` | 完整片段列表（最多保留前 100 条） |
| `segments[].start` | `number` | 片段开始时间（秒） |
| `segments[].end` | `number` | 片段结束时间（秒） |
| `segments[].text` | `string` | 该片段 ASR 原始文本（**未经过 LLM 纠错的原始输出**） |
| `llm_corrected` | `bool` | content 是否经过 LLM 纠错后处理 |

> **注意**: `segments[].text` 是 Whisper 原始输出（含可能的识别错误），`content` 是经过 LLM 纠错后的文本。两者可能存在差异。

---

### frame（视频关键帧视觉描述）

由 `VideoProcessor._describe_frame_with_qwen()` 产出。

```json
{
  "chunk_id": "chunk_xxxx",
  "source_type": "video",
  "source_ref": "D:/videos/test4.mp4",
  "content": "画面主要内容：VS Code 编辑器界面，左侧文件列表，中间代码窗口...",
  "page_ref": 0,
  "seq_index": 2,
  "metadata": {
    "timestamp_sec": 30,
    "frame_path": "/tmp/video_frames_xxx/frame_0030.jpg",
    "vlm_model": "qwen-vl-plus"
  },
  "embedding": null
}
```

#### metadata 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `timestamp_sec` | `int` | 帧在视频中的时间位置（秒） |
| `frame_path` | `string` | 帧图片本地临时路径 |
| `vlm_model` | `string` | 使用的视觉模型名，如 `qwen-vl-plus` |

content 为 Qwen-VL 模型对帧画面的中文描述。

---

### pdf / pptx / docx（文档解析）

由 `DocumentParser` 各格式解析器产出。每页产出一个或多个 Chunk。

```json
{
  "chunk_id": "chunk_d4e5f6aabbcc",
  "source_type": "pdf",
  "source_ref": "D:/docs/课件.pdf",
  "content": "## 第一章：排序算法\n\n冒泡排序（Bubble Sort）是一种简单的排序算法...",
  "page_ref": 1,
  "seq_index": 0,
  "metadata": {
    "type": "text",
    "slide_title": "第一章：排序算法"
  },
  "embedding": null
}
```

#### metadata 字段（文档通用）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `type` | `string` | 块类型：`text` / `table` / `image` / `slide` |
| `slide_title` | `string` | 页面/幻灯片标题（如有） |

---

### image（图片 OCR）

由 `OCREngine` 产出。

```json
{
  "chunk_id": "chunk_f1a2b3c4d5e6",
  "source_type": "image",
  "source_ref": "D:/images/流程图.png",
  "content": "OCR 识别出的文字内容...",
  "page_ref": 0,
  "seq_index": 0,
  "metadata": {
    "type": "image",
    "width": 1920,
    "height": 1080,
    "format": "PNG",
    "ocr_engine": "paddleocr",
    "text_blocks": [],
    "layout": {}
  },
  "embedding": null
}
```

---

## ParseStatusResponse 外层包装

所有 Chunk 通过 `ParseStatusResponse` 返回给调用方：

```json
{
  "task_id": "parse_7f9c9ed0b18e",
  "status": "done",
  "chunks": [ ...Chunk 列表... ],
  "error": null
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | `string` | 解析任务 ID，格式 `parse_{uuid_hex[:12]}` |
| `status` | `string` | 任务状态：`uploaded` / `parsing` / `chunked` / `indexed` / `done` / `failed` |
| `chunks` | `array[Chunk]` | 标准化 Chunk 数组，空数组表示尚未解析完成 |
| `error` | `string` 或 `null` | 错误信息，仅 `status=failed` 或 `partial_fail` 时有值 |

---

## 常量与限制

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `MAX_CONTENT_CHARS` | `15000` | 单条 Chunk 最大字符数，超出截断 |
| `segments` 最大保留 | `100` 条 | metadata 中 segments 数组上限 |
| `chunk_id` 前缀 | `chunk_` | UUID hex 12 位 |

---

## 相关文件

| 文件 | 职责 |
| --- | --- |
| `ai_engine/core/schema.py` | Chunk Pydantic 模型定义 |
| `ai_engine/parse/chunk_normalizer.py` | 原始块 → 标准化 Chunk |
| `ai_engine/parse/task_manager.py` | 异步解析调度 + 结果组装 |
| `ai_engine/parse/video_processor.py` | 视频/音频解析 → 原始块 |
| `ai_engine/parse/doc_parser.py` | 文档解析 → 原始块 |
| `ai_engine/parse/ocr_engine.py` | 图片 OCR → 原始块 |
