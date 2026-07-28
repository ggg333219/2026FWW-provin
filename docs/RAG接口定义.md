# RAG 接口定义

> P3 KB 知识库 RAG — HTTP API 契约
> 最后更新: 2026-07-27

## 概述

KB 知识库提供 3 个 HTTP 端点，供 Go 后端（`KnowledgeHandler`）和 S3 课件生成调用。

- **Base URL**: `http://localhost:8000/api/v1`
- **协议**: REST + JSON
- **认证**: 无（内部服务间调用）

---

## 端点清单

| 方法 | 路径 | 用途 | Go Handler |
|------|------|------|-----------|
| `POST` | `/rag/search` | 混合检索 | `KnowledgeHandler.Search` |
| `POST` | `/rag/evidence` | 证据融合 | `KnowledgeHandler.Evidence` |
| `POST` | `/knowledge/upload` | 知识库上传/索引 | `KnowledgeHandler.Upload` |

---

## 1. POST /rag/search — 混合检索

检索与查询最相关的知识库分块。

### 请求

```json
{
  "query": "冒泡排序的时间复杂度",
  "knowledge_base_ids": ["doc_001"],
  "top_k": 5,
  "min_score": 0.6
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | `string` | 是 | - | 查询文本 |
| `knowledge_base_ids` | `string[]` | 否 | `[]` | 限定知识库范围（当前未实现过滤） |
| `top_k` | `int` | 否 | `5` | 返回结果数 |
| `min_score` | `float` | 否 | `0.6` | 最低分数阈值，低于此值丢弃 |

### 响应

```json
{
  "results": [
    {
      "chunk_id": "chunk_abc123",
      "content": "冒泡排序的时间复杂度为 O(n^2)...",
      "score": 0.92,
      "source": {
        "file_name": "算法教材.pdf",
        "page": 3,
        "type": "pdf"
      },
      "metadata": {
        "doc_id": "doc_001",
        "seq_index": 5
      }
    }
  ],
  "total_chunks": 150
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `results` | `SearchResult[]` | 检索结果列表 |
| `results[].chunk_id` | `string` | 分块 ID |
| `results[].content` | `string` | 分块文本内容 |
| `results[].score` | `float` | 融合分数（0~1） |
| `results[].source` | `object` | 来源信息 |
| `results[].source.file_name` | `string` | 文件名 |
| `results[].source.page` | `int` | 页码 |
| `results[].source.type` | `string` | 来源类型 |
| `results[].metadata` | `object` | 附加元数据 |
| `total_chunks` | `int` | 知识库总 chunk 数 |

### 检索策略

```
score = 0.7 × cosine_sim(query_vec, chunk_vec)
       + 0.3 × bm25_score(query, chunk)
```

- 向量检索召回 top_k×4 候选
- BM25 关键词归一化后融合
- 可选 Cross-encoder 精排（当前透传模式）

---

## 2. POST /rag/evidence — 证据融合

将检索结果融合为结构化 `EvidencePacket`，供 S3 课件生成使用。

### 请求

```json
{
  "query": "排序算法的时间复杂度对比",
  "context": {
    "topic": "排序算法",
    "duration_minutes": 45,
    "style": "讲练结合"
  },
  "knowledge_base_ids": ["doc_001"]
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | `string` | 是 | - | 原始查询文本 |
| `context` | `object` | 否 | `{}` | 意图上下文（来自 S1） |
| `knowledge_base_ids` | `string[]` | 否 | `[]` | 限定知识库范围 |

### 响应

```json
{
  "evidence_packet": {
    "relevant_chunks": [
      {
        "chunk_id": "chunk_abc123",
        "source_type": "pdf",
        "source_ref": "算法教材.pdf",
        "content": "冒泡排序的时间复杂度为 O(n^2)...",
        "page_ref": 3,
        "seq_index": 5,
        "metadata": {}
      }
    ],
    "synthesized_context": "冒泡排序是最简单的排序算法，时间复杂度 O(n^2)，空间复杂度 O(1)...",
    "citations": [
      {
        "chunk_id": "chunk_abc123",
        "text_snippet": "冒泡排序的时间复杂度为 O(n^2)",
        "source_ref": "算法教材.pdf"
      }
    ],
    "query": "排序算法的时间复杂度对比"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `evidence_packet` | `EvidencePacket` | 证据融合包 |
| `evidence_packet.relevant_chunks` | `Chunk[]` | 最相关的 top-5 分块 |
| `evidence_packet.synthesized_context` | `string` | LLM 合成的浓缩上下文（200-500字） |
| `evidence_packet.citations` | `Citation[]` | 引用标注 |
| `evidence_packet.citations[].chunk_id` | `string` | 引用来源 chunk ID |
| `evidence_packet.citations[].text_snippet` | `string` | 原文片段（≤100字） |
| `evidence_packet.citations[].source_ref` | `string` | 来源标识 |
| `evidence_packet.query` | `string` | 触发检索的原始查询 |

### S3 兼容性

S3 `OutlineBuilder._format_evidence()` 同时支持两种字段名：

```python
# OutlineBuilder 内部兼容逻辑
chunks = evidence_packet.get("chunks") or evidence_packet.get("relevant_chunks") or []
```

因此以下两种格式均可被 S3 正确消费：

```json
// 格式 A: KB 原始输出（recommended）
{"relevant_chunks": [...], "synthesized_context": "..."}

// 格式 B: S3 旧约定（仍兼容）
{"chunks": [{"content": "...", "chunk_id": "..."}], "context": "..."}
```

---

## 3. POST /knowledge/upload — 知识库上传/索引

将文档或文本摄入知识库，执行分块 → 嵌入向量化 → 写入向量存储。

### 请求

```json
{
  "session_id": "sess_001",
  "knowledge_base_id": "kb_math",
  "files": [
    "uploads/sorting_algorithms.pdf",
    "minio://teaching/2024/算法课件.pptx"
  ],
  "texts": [
    "冒泡排序是一种简单的排序算法..."
  ]
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `session_id` | `string` | 否 | `""` | 会话 ID，S2 解析完成后通过此字段自动关联 chunks |
| `knowledge_base_id` | `string` | 否 | `""` | 知识库集合 ID（当前未实现多集合隔离） |
| `files` | `string[]` | 否 | `[]` | 文件 URL 列表（本地路径或 `minio://` 协议） |
| `texts` | `string[]` | 否 | `[]` | 直接文本片段（测试/手动添加用） |

> **注意**: `session_id`、`files`、`texts` 至少提供一个。如果只提供 `session_id`，将自动消费 S2 已解析的 chunks。

### 响应

```json
{
  "task_id": "kb_upload_abc123def456",
  "status": "done",
  "chunk_count": 42,
  "document_id": "doc_xyz789"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | `string` | 任务 ID |
| `status` | `string` | 状态：`done` / `failed` |
| `chunk_count` | `int` | 本次索引的分块总数 |
| `document_id` | `string` | 生成的文档 ID，用于后续删除/管理 |

### 处理流程

```
输入 (files / texts / session_id)
    ↓
分块 (DocumentChunker)
    ↓
嵌入向量化 (EmbeddingService → LLMClient.embed)
    ↓
写入向量存储 (InMemoryVectorStore / PGVectorStore)
    ↓
重建 BM25 索引
    ↓
返回 task_id + chunk_count
```

---

## 错误响应

所有端点统一错误格式：

```json
{
  "detail": "错误描述"
}
```

| HTTP 状态码 | 场景 |
|------------|------|
| `400` | 请求参数缺失/格式错误 |
| `500` | 服务端内部错误（LLM 调用失败、DB 连接失败等） |

---

## 跨模块数据流

```
S2 (parse)                      KB (rag)
  │                                │
  │  register_session_chunks()     │
  │ ─────────────────────────────► │
  │  session_id → [Chunk]          │
  │                                │
  │  POST /knowledge/upload        │
  │ ─────────────────────────────► │
  │  session_id                    │
  │                                │  chunk → embed → store
  │                                │
  │  POST /rag/search              │
  │ ◄───────────────────────────── │
  │  SearchResult[]                │
  │                                │
  │  POST /rag/evidence            │
  │ ◄───────────────────────────── │
  │  EvidencePacket                │
  │     ↓                          │
  │  S3 (OutlineBuilder)           │
  │     ↓                          │
  │  TeachingNode[]                │
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AI_API_KEY` | `""` | OpenAI 兼容 API Key |
| `AI_BASE_URL` | `""` | API Base URL |
| `AI_EMBEDDING_MODEL` | `text-embedding-v3` | 嵌入模型名 |
| `AI_EMBEDDING_DIM` | `1024` | 向量维度 |
| `AI_GEN_MODE` | `llm` | `mock` 模式返回零向量 |
| `DB_HOST` | `localhost` | PostgreSQL 地址 |
| `DB_PORT` | `5432` | PostgreSQL 端口 |
| `DB_USER` | `postgres` | PostgreSQL 用户名 |
| `DB_PASSWORD` | `123456` | PostgreSQL 密码 |
| `DB_NAME` | `teaching` | PostgreSQL 数据库名 |

---

## 相关文件

| 文件 | 职责 |
|------|------|
| `ai_engine/rag/router.py` | FastAPI 路由（3 个端点） |
| `ai_engine/rag/chunker.py` | 文档分块 |
| `ai_engine/rag/embed.py` | 嵌入向量化 |
| `ai_engine/rag/store.py` | 向量存储（InMemory） |
| `ai_engine/rag/store_pgvector.py` | 向量存储（pgvector） |
| `ai_engine/rag/retrieve.py` | 混合检索 |
| `ai_engine/rag/rerank.py` | Cross-encoder 重排序 |
| `ai_engine/rag/evidence.py` | 证据合成 |
| `ai_engine/core/schema.py` | Chunk / EvidencePacket / SearchResult 模型定义 |
| `ai_engine/core/llm.py` | LLMClient.embed() 嵌入调用 |
| `ai_engine/gen/outline.py` | S3 消费者（接收 EvidencePacket） |
| `ai_engine/rag/migrations/001_create_rag_tables.sql` | DB 迁移脚本 |
