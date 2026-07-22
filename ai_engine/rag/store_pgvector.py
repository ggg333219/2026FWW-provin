"""
PGVector 向量存储 (store_pgvector.py)

基于 pgvector 扩展的 PostgreSQL 向量存储实现。

与 InMemoryVectorStore 实现相同的 VectorStore 接口，
支持数据持久化、HNSW 索引加速、事务一致性。

前置条件：
  1. PostgreSQL 14+ 安装 pgvector 扩展：
     CREATE EXTENSION IF NOT EXISTS vector;
  2. 建表 SQL: ai_engine/rag/migrations/001_create_rag_tables.sql
  3. pip install psycopg2-binary pgvector

使用方式：
    from ai_engine.rag.store_pgvector import PGVectorStore

    store = PGVectorStore(conn_string="postgresql://...")
    store.insert_batch(chunks)
    results = store.search(query_vec, top_k=5)
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from ai_engine.core.schema import Chunk, SourceType, ParseStatus
from ai_engine.rag.embed import cosine_similarity
from ai_engine.rag.store import (
    VectorStore,
    IndexedChunk,
    SearchHit,
    DocumentRecord,
)

# ---- 默认连接 ----

_DEFAULT_CONN_STRING = (
    f"postgresql://"
    f"{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '123456')}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
    f"/{os.getenv('DB_NAME', 'teaching')}"
)


# =============================================================================
# PGVectorStore
# =============================================================================

class PGVectorStore(VectorStore):
    """
    pgvector 向量存储实现。

    特性：
      - HNSW 向量索引（余弦距离算子 <=>）
      - 支持按 doc_id 批量删除
      - 自动创建/迁移表结构
      - 事务安全

    表结构：
      rag_documents: 文档级元数据
      rag_chunks:    分块 + 向量（pgvector halfvec 类型）
    """

    def __init__(
        self,
        conn_string: str = "",
        table_prefix: str = "",
        embedding_dim: int = 1024,
    ):
        """
        Args:
            conn_string: PostgreSQL 连接字符串
                         （默认从 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME 构建）。
            table_prefix: 表前缀（多租户场景）。
            embedding_dim: 向量维度。
        """
        self.conn_string = conn_string or _DEFAULT_CONN_STRING
        self.table_prefix = table_prefix
        self.embedding_dim = embedding_dim
        self._conn = None

    # ---- 连接管理 ----

    @property
    def conn(self):
        """懒连接 PostgreSQL。"""
        if self._conn is None or self._conn.closed:
            import psycopg2
            self._conn = psycopg2.connect(self.conn_string)
            self._conn.autocommit = False
            self._ensure_tables()
        return self._conn

    def _ensure_tables(self) -> None:
        """自动创建表和索引（幂等）。"""
        cur = self._conn.cursor()
        try:
            # pgvector 扩展
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

            # 文档表
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._t('rag_documents')} (
                    doc_id       VARCHAR(64) PRIMARY KEY,
                    file_name    TEXT NOT NULL DEFAULT '',
                    source_type  VARCHAR(20) NOT NULL DEFAULT 'text',
                    chunk_count  INTEGER NOT NULL DEFAULT 0,
                    status       VARCHAR(20) NOT NULL DEFAULT 'uploaded',
                    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
                    metadata     JSONB DEFAULT '{{}}'
                )
            """)

            # 分块表（pgvector halfvec 精度更高）
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self._t('rag_chunks')} (
                    chunk_id     VARCHAR(64) PRIMARY KEY,
                    doc_id       VARCHAR(64) NOT NULL
                                 REFERENCES {self._t('rag_documents')}(doc_id)
                                 ON DELETE CASCADE,
                    source_ref   TEXT NOT NULL DEFAULT '',
                    source_type  VARCHAR(20) NOT NULL DEFAULT 'text',
                    content      TEXT NOT NULL DEFAULT '',
                    page_ref     INTEGER,
                    seq_index    INTEGER NOT NULL DEFAULT 0,
                    embedding    halfvec({self.embedding_dim}),
                    metadata     JSONB DEFAULT '{{}}',
                    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """)

            # HNSW 索引（余弦距离）
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {self._t('idx_rag_chunks_embedding')}
                ON {self._t('rag_chunks')}
                USING hnsw (embedding halfvec_cosine_ops)
                WITH (m = 16, ef_construction = 200)
            """)

            # 辅助索引
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {self._t('idx_rag_chunks_doc_id')}
                ON {self._t('rag_chunks')}(doc_id)
            """)

            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    def _t(self, name: str) -> str:
        """表名前缀。"""
        return f"{self.table_prefix}{name}" if self.table_prefix else name

    # ---- VectorStore 实现 ----

    def insert_batch(self, chunks: list[Chunk], doc_id: str = "") -> list[str]:
        if not chunks:
            return []

        import uuid as _uuid
        if not doc_id:
            doc_id = f"doc_{_uuid.uuid4().hex[:12]}"

        sample = chunks[0]
        cur = self.conn.cursor()
        chunk_ids: list[str] = []

        try:
            # 1. 插入或更新文档记录
            cur.execute(
                f"""
                INSERT INTO {self._t('rag_documents')}
                    (doc_id, file_name, source_type, chunk_count, status)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (doc_id) DO UPDATE SET
                    chunk_count = {self._t('rag_documents')}.chunk_count + %s,
                    status = 'indexed'
                """,
                (
                    doc_id,
                    sample.source_ref or "",
                    sample.source_type.value,
                    len(chunks),
                    ParseStatus.INDEXED.value,
                    len(chunks),
                ),
            )

            # 2. 批量插入分块
            for ch in chunks:
                embedding_vec = _format_vector(ch.embedding) if ch.embedding else None
                cur.execute(
                    f"""
                    INSERT INTO {self._t('rag_chunks')}
                        (chunk_id, doc_id, source_ref, source_type,
                         content, page_ref, seq_index, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        content = EXCLUDED.content
                    """,
                    (
                        ch.chunk_id,
                        doc_id,
                        ch.source_ref,
                        ch.source_type.value,
                        ch.content,
                        ch.page_ref,
                        ch.seq_index,
                        embedding_vec,
                        json.dumps(ch.metadata, ensure_ascii=False),
                    ),
                )
                chunk_ids.append(ch.chunk_id)

            self.conn.commit()
            return chunk_ids

        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def search(
        self,
        query_vec: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
        source_type: Optional[SourceType] = None,
    ) -> list[SearchHit]:
        if not query_vec:
            return []

        vec_str = _format_vector(query_vec)
        cur = self.conn.cursor()

        try:
            where = ""
            params: list[Any] = [vec_str, top_k]
            if source_type is not None:
                where = "AND source_type = %s"
                params.insert(1, source_type.value)

            # 使用余弦距离算子 <=>（1 - cosine_similarity）
            cur.execute(
                f"""
                SELECT chunk_id, doc_id, source_ref, source_type,
                       content, page_ref, seq_index, embedding, metadata,
                       1.0 - (embedding <=> %s) AS score
                FROM {self._t('rag_chunks')}
                WHERE embedding IS NOT NULL {where}
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()

            hits: list[SearchHit] = []
            for row in rows:
                score = float(row[9])
                if score < min_score:
                    continue
                indexed = _row_to_indexed_chunk(row)
                hits.append(SearchHit(chunk=indexed, score=score))
            return hits

        finally:
            cur.close()

    def delete_by_doc(self, doc_id: str) -> int:
        cur = self.conn.cursor()
        try:
            # CASCADE 自动删除关联 chunks
            cur.execute(
                f"DELETE FROM {self._t('rag_documents')} WHERE doc_id = %s",
                (doc_id,),
            )
            count = cur.rowcount
            self.conn.commit()
            return count
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def delete_by_chunk_id(self, chunk_id: str) -> bool:
        cur = self.conn.cursor()
        try:
            cur.execute(
                f"DELETE FROM {self._t('rag_chunks')} WHERE chunk_id = %s",
                (chunk_id,),
            )
            deleted = cur.rowcount > 0
            self.conn.commit()
            return deleted
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cur.close()

    def get_chunk(self, chunk_id: str) -> Optional[IndexedChunk]:
        cur = self.conn.cursor()
        try:
            cur.execute(
                f"""
                SELECT chunk_id, doc_id, source_ref, source_type,
                       content, page_ref, seq_index, embedding, metadata
                FROM {self._t('rag_chunks')}
                WHERE chunk_id = %s
                """,
                (chunk_id,),
            )
            row = cur.fetchone()
            return _row_to_indexed_chunk(row) if row else None
        finally:
            cur.close()

    def count(self) -> int:
        cur = self.conn.cursor()
        try:
            cur.execute(f"SELECT COUNT(*) FROM {self._t('rag_chunks')}")
            return int(cur.fetchone()[0])
        finally:
            cur.close()

    def list_documents(self) -> list[DocumentRecord]:
        cur = self.conn.cursor()
        try:
            cur.execute(
                f"""
                SELECT doc_id, file_name, source_type, chunk_count, status
                FROM {self._t('rag_documents')}
                ORDER BY created_at DESC
                """
            )
            return [
                DocumentRecord(
                    doc_id=r[0],
                    file_name=r[1],
                    source_type=SourceType(r[2]),
                    chunk_count=r[3],
                    status=ParseStatus(r[4]),
                )
                for r in cur.fetchall()
            ]
        finally:
            cur.close()

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None


# ---- 辅助函数 ----

def _format_vector(vec: list[float]) -> str:
    """将 list[float] 格式化为 pgvector 的字符串表示。

    pgvector 接受 '[0.1, 0.2, ...]' 格式。
    """
    return "[" + ",".join(f"{v:.8g}" for v in vec) + "]"


def _row_to_indexed_chunk(row: tuple) -> IndexedChunk:
    """数据库行 → IndexedChunk。"""
    embedding: list[float] = []
    if row[7] is not None:
        raw = row[7]
        # pgvector 返回的 halfvec 可能是字符串或已解析列表
        if isinstance(raw, str):
            # 去掉方括号后按逗号分割
            raw = raw.strip("[]")
            embedding = [float(x) for x in raw.split(",") if x.strip()]
        elif isinstance(raw, list):
            embedding = [float(x) for x in raw]
        else:
            embedding = list(float(x) for x in raw)

    metadata = row[8] if isinstance(row[8], dict) else json.loads(row[8] or "{}")

    source_type_str = row[3] or "text"
    try:
        source_type = SourceType(source_type_str)
    except ValueError:
        source_type = SourceType.TEXT

    return IndexedChunk(
        chunk_id=row[0],
        doc_id=row[1] or "",
        source_ref=row[2] or "",
        source_type=source_type,
        content=row[4] or "",
        page_ref=row[5],
        seq_index=row[6] or 0,
        embedding=embedding,
        metadata=metadata,
    )
