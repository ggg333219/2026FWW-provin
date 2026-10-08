-- 将已有 1024 维 rag_chunks 表迁移到本地 BGE-small-zh 使用的 512 维。
-- 旧向量无法安全转换为 512 维，因此保留旧表作为备份，重建空表后重新灌库。
-- 执行前请确认当前知识库已备份；本地验证环境的旧表仅包含失败测试残留数据。

BEGIN;

ALTER TABLE IF EXISTS rag_chunks
    RENAME TO rag_chunks_legacy_1024;

ALTER TABLE IF EXISTS rag_documents
    RENAME TO rag_documents_legacy_1024;

DROP INDEX IF EXISTS idx_rag_chunks_embedding;
DROP INDEX IF EXISTS idx_rag_chunks_doc_id;
DROP INDEX IF EXISTS idx_rag_chunks_source_type;

CREATE TABLE IF NOT EXISTS rag_documents (
    doc_id       VARCHAR(64) PRIMARY KEY,
    file_name    TEXT NOT NULL DEFAULT '',
    source_type  VARCHAR(20) NOT NULL DEFAULT 'text',
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    status       VARCHAR(20) NOT NULL DEFAULT 'uploaded',
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    metadata     JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id     VARCHAR(64) PRIMARY KEY,
    doc_id       VARCHAR(64) NOT NULL REFERENCES rag_documents(doc_id) ON DELETE CASCADE,
    source_ref   TEXT NOT NULL DEFAULT '',
    source_type  VARCHAR(20) NOT NULL DEFAULT 'text',
    content      TEXT NOT NULL DEFAULT '',
    page_ref     INTEGER,
    seq_index    INTEGER NOT NULL DEFAULT 0,
    embedding    halfvec(512),
    metadata     JSONB DEFAULT '{}',
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding
    ON rag_chunks USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 200);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc_id ON rag_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_source_type ON rag_chunks(source_type);

COMMIT;
