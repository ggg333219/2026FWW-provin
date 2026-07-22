-- =============================================================================
-- KB 知识库 RAG 表结构迁移
-- =============================================================================
-- 前置条件: PostgreSQL 14+ + pgvector 扩展
-- 运行: psql -U postgres -d teaching -f 001_create_rag_tables.sql
-- =============================================================================

-- 1. 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. 文档表: 每个上传/导入的文档一条记录
CREATE TABLE IF NOT EXISTS rag_documents (
    doc_id       VARCHAR(64) PRIMARY KEY,
    file_name    TEXT NOT NULL DEFAULT '',
    source_type  VARCHAR(20) NOT NULL DEFAULT 'text',
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    status       VARCHAR(20) NOT NULL DEFAULT 'uploaded',
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata     JSONB DEFAULT '{}'
);

COMMENT ON TABLE rag_documents IS 'KB 知识库文档索引记录';
COMMENT ON COLUMN rag_documents.status IS 'uploaded | parsing | chunked | indexed | done | failed';

-- 3. 分块表: 每个分块一条记录，含向量
CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id     VARCHAR(64) PRIMARY KEY,
    doc_id       VARCHAR(64) NOT NULL
                 REFERENCES rag_documents(doc_id)
                 ON DELETE CASCADE,
    source_ref   TEXT NOT NULL DEFAULT '',
    source_type  VARCHAR(20) NOT NULL DEFAULT 'text',
    content      TEXT NOT NULL DEFAULT '',
    page_ref     INTEGER,
    seq_index    INTEGER NOT NULL DEFAULT 0,
    embedding    halfvec(1024),   -- pgvector half precision, 1024-dim. 按需调整维度
    metadata     JSONB DEFAULT '{}',
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE rag_chunks IS 'KB 知识库分块 + 向量';
COMMENT ON COLUMN rag_chunks.embedding IS 'halfvec: 半精度浮点向量 (1024-dim)';

-- 4. HNSW 向量索引 (余弦距离, 生产推荐参数)
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
ON rag_chunks
USING hnsw (embedding halfvec_cosine_ops)
WITH (m = 16, ef_construction = 200);

-- 5. 辅助索引: 按文档查询
CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc_id
ON rag_chunks(doc_id);

-- 6. 辅助索引: 按来源类型过滤
CREATE INDEX IF NOT EXISTS idx_rag_chunks_source_type
ON rag_chunks(source_type);

-- 7. GIN 索引: metadata JSONB 查询 (可选, 按需创建)
-- CREATE INDEX IF NOT EXISTS idx_rag_chunks_metadata
-- ON rag_chunks USING GIN (metadata);
