# 知识库 (Knowledge Base / RAG) — 跨层基础设施详细设计

> 基于 Phase 2 工作流分析结果编写
> 最后更新: 2026-07-15

## 1. 总体角色

知识库是**跨层基础设施层**，服务于所有四个 Skill。它在现有系统架构中占据两个节点：

- **索引** (Tool Layer L4) — 将解析内容摄入向量存储
- **RAG** (Knowledge & Generation Layer L5) — 检索证据并融合到 LLM 上下文

## 2. 架构与数据流

```
教师上传 / 系统导入
    |
    [索引工具]  ← Agent Orchestrator 触发
    |
    v
  ParseDoc / ParseVideo / OCR  → 文本提取器
    |
    v
  分块管道 (ChunkingPipeline)
    |
    +-- 块 (Chunks)  +-- 元数据 (Metadata)
    |                    |
    v                    v
  嵌入 API → 向量存储 (pgvector)
    |                    |
    v                    v
  rag_chunks 表        rag_documents 表 (Postgres)
    |
    ^
  [RAG 服务]  ← GenPPT/GenDoc/GenInteractive/QA 查询
    |
  混合检索器 (vector 0.7 + BM25 0.3)
    |
  重排序器 (可选 cross-encoder)
    |
  检索块 + 引用
    |
  LLM 上下文构建器
```

## 3. 接口契约

### 管理：上传文档

```http
POST /api/v1/knowledge/upload
{ "files": [...], "knowledge_base_id": "uuid" }
→ { "task_id": "uuid", "status": "indexing" }

GET /api/v1/knowledge/status/:task_id
→ { "status": "done|failed", "chunk_count": 150, "error": null }
```

### 搜索

```http
POST /api/v1/rag/search
{
  "query": "...",
  "knowledge_base_ids": ["uuid"],
  "top_k": 5,
  "min_score": 0.6
}
→ {
  "results": [
    { "chunk_id": "uuid", "content": "...", "score": 0.92,
      "source": { "file_name": "...", "page": 3, "url": "minio://..." },
      "metadata": { "node_ref": "...", "type": "text|table|image" } }
  ],
  "total_chunks": 150
}
```

### 证据融合（供生成使用）

```http
POST /api/v1/rag/evidence
{
  "query": "...",
  "context": { "intent": {...}, "current_nodes": [...] },
  "knowledge_base_ids": ["uuid"]
}
→ {
  "evidence_packet": {
    "relevant_chunks": [...],
    "synthesized_context": "...",
    "citations": [{ "chunk_id", "text_snippet", "source_ref" }]
  }
}
```

## 4. 内部模块

| 子模块 | 职责 | 文件 |
|--------|------|------|
| `document_chunker` | 文档分块（按页/段落/语义边界） | `ai_engine/rag/chunker.py` (新增) |
| `embedding_service` | 调用嵌入 API 向量化分块 | `ai_engine/rag/embed.py` (新增) |
| `vector_store` | 向量数据库 CRUD (pgvector) | `ai_engine/rag/store.py` (新增) |
| `retriever` | 混合搜索（向量 + 关键词），分数融合 | `ai_engine/rag/retrieve.py` (新增) |
| `re_ranker` | 交叉编码器重排序 top-K 结果 | `ai_engine/rag/rerank.py` (新增) |
| `evidence_synthesizer` | 检索块 + LLM 合成 → evidence_packet | `ai_engine/rag/evidence.py` (新增) |
| `kb_manager` | 知识库集合 CRUD，文档元数据管理 | `backend/services/knowledge.go` (新增) |

## 5. 分块策略

| 文档类型 | 分块策略 | 块大小 | 重叠 |
|----------|---------|--------|------|
| PDF (教材) | 按段落 + 标题层级 | 512 tokens | 64 tokens |
| PPTX (课件) | 按幻灯片 | 每张独立 | 0 |
| DOCX (教案) | 按章节 (§) | 512 tokens | 64 tokens |
| 图片 (OCR) | 按版面区域 | 图片块 | 0 |
| 视频 (ASR) | 按时间窗口 | 30s 段落 | 5s |

## 6. 检索策略

**混合检索权重**: 向量相似度 0.7 + BM25 关键词 0.3

```
score = 0.7 * cosine_sim(embedding(q), embedding(chunk))
       + 0.3 * bm25_score(q, chunk)
```

**重排序**: 可选 cross-encoder 对 top-20 结果重排序，取 top-5 作为最终结果。

**质量阈值**: `min_score = 0.6`，低于此阈值的结果丢弃。

## 7. 证据融合流程

```
query → hybrid_retrieve(q, k=20) → rerank(retrieved, k=5)
→ synthesize(evidence, query, intent_context) → evidence_packet

evidence_packet 结构:
{
  "relevant_chunks": [最相关的前 5 个块],
  "synthesized_context": "LLM 生成的摘要...",
  "citations": [{"chunk_id", "text_snippet", "source_ref"}]
}
```

## 8. 向量数据库选择

**推荐方案: pgvector (PostgreSQL 扩展)**

理由：
- 无新增基础设施 — 当前系统已使用 PostgreSQL
- 数据一致性 — 文档元数据与向量共存于同一事务
- 成熟度 — pgvector 0.8+ 支持 HNSW 索引、IVFFlat 索引
- 运维成本 — 无需额外部署 Milvus/Qdrant 集群

## 9. 文档生命周期

```
[UPLOADED → CHUNKING → VECTORIZING → INDEXED]  (成功)
[UPLOADED → CHUNKING → FAILED]                  (重试 2x)

搜索为无状态操作（查询入 → 结果出）。
证据融合无持久状态 — 是 RAG 管道：检索 → 重排 → 合成。
```

## 10. 依赖关系

- **依赖**: 嵌入 API，向量数据库 (pgvector)，LLM（合成）
- **依赖**: S2 多模态工具层输出（已解析材料的分块）
- **被调用**: 生成模块 (evidence_packet)、问答模块 (search)
- **产出消费**: 生成、问答、Agent Orchestrator（路由决策）

## 11. 现有代码复用

- **复用** 现有 LLM 调用包装器（`qa.py`）
- **复用** MinIO 文档存储管道
- **复用** 现有 Go 模型/数据库连接模式
- **新增** 全部分块、嵌入、检索、重排、合成管道
