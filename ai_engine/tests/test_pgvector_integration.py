"""
PGVector 集成测试 (test_pgvector_integration.py)

在真实 PostgreSQL + pgvector 环境下运行。
无依赖或无法连接 DB 时自动跳过。

运行方式:
    # 需要先安装依赖并启动 PostgreSQL + pgvector:
    pip install psycopg2-binary pgvector
    # 执行 DB 迁移:
    psql -U postgres -d teaching -f ai_engine/rag/migrations/001_create_rag_tables.sql

    python -m pytest ai_engine/tests/test_pgvector_integration.py -v
    python -m unittest ai_engine.tests.test_pgvector_integration -v
"""

from __future__ import annotations

import os
import unittest
from typing import Optional


def _check_pgvector_available() -> tuple[bool, Optional[str]]:
    """检查 pgvector 依赖是否可用。"""
    try:
        import psycopg2  # noqa: F401
        return True, None
    except ImportError:
        return False, "psycopg2-binary 未安装"


def _check_db_available() -> tuple[bool, Optional[str]]:
    """检查 PostgreSQL 是否可连接。"""
    try:
        import psycopg2
        conn_string = (
            f"postgresql://"
            f"{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '123456')}"
            f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
            f"/{os.getenv('DB_NAME', 'teaching')}"
        )
        conn = psycopg2.connect(conn_string, connect_timeout=3)
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)


def _check_pgvector_extension(cur) -> tuple[bool, Optional[str]]:
    """检查 pgvector 扩展是否已安装。"""
    try:
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        if cur.fetchone():
            return True, None
        return False, "pgvector 扩展未安装 (CREATE EXTENSION vector;)"
    except Exception as e:
        return False, str(e)


# =============================================================================
# 测试类（条件跳过）
# =============================================================================

class TestPGVectorIntegration(unittest.TestCase):
    """PGVector 集成测试（需要真实 DB）。"""

    @classmethod
    def setUpClass(cls):
        available, reason = _check_pgvector_available()
        if not available:
            raise unittest.SkipTest(f"跳过: {reason}")

        available, reason = _check_db_available()
        if not available:
            raise unittest.SkipTest(f"跳过: 数据库不可连接 ({reason})")

        from ai_engine.rag.store_pgvector import PGVectorStore, _format_vector
        from ai_engine.core.schema import Chunk, SourceType, ParseStatus
        cls.PGVectorStore = PGVectorStore
        cls._format_vector = _format_vector
        cls.Chunk = Chunk
        cls.SourceType = SourceType
        cls.ParseStatus = ParseStatus

    def setUp(self):
        import psycopg2
        conn_string = (
            f"postgresql://"
            f"{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '123456')}"
            f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
            f"/{os.getenv('DB_NAME', 'teaching')}"
        )
        self.store = self.PGVectorStore(conn_string=conn_string, table_prefix="test_rag_")
        # 确保表已创建
        self.store._ensure_tables()
        # 清理测试数据
        self._cleanup()

    def _cleanup(self):
        """清理测试表数据。"""
        cur = self.store.conn.cursor()
        try:
            cur.execute(f"DELETE FROM {self.store._t('rag_chunks')}")
            cur.execute(f"DELETE FROM {self.store._t('rag_documents')}")
            self.store.conn.commit()
        except Exception:
            self.store.conn.rollback()
        finally:
            cur.close()

    def tearDown(self):
        self._cleanup()
        self.store.close()

    def _make_chunk(self, cid: str, content: str, dim: int = 1024) -> "Chunk":
        """创建带向量的测试 Chunk。"""
        import hashlib
        h = hashlib.md5(content.encode()).hexdigest()
        vec = [float(int(h[i:i+2], 16)) / 255.0 for i in range(0, min(len(h), dim * 2), 2)]
        # 补齐或截断到 dim
        vec = (vec + [0.0] * dim)[:dim]
        return self.Chunk(
            chunk_id=cid,
            source_type=self.SourceType.TEXT,
            source_ref="test.txt",
            content=content,
            seq_index=0,
            embedding=vec,
        )

    # ---- 基础 CRUD ----

    def test_insert_and_count(self):
        """插入后 count 正确。"""
        chunks = [self._make_chunk(f"c{i}", f"content-{i}") for i in range(10)]
        ids = self.store.insert_batch(chunks, doc_id="doc_001")
        self.assertEqual(len(ids), 10)
        self.assertEqual(self.store.count(), 10)

    def test_search_returns_results(self):
        """向量检索返回结果。"""
        chunks = [
            self._make_chunk("c1", "apple banana cherry"),
            self._make_chunk("c2", "cat dog elephant"),
            self._make_chunk("c3", "apple pie recipe"),
        ]
        self.store.insert_batch(chunks, doc_id="doc_001")

        query_vec = self._make_chunk("q", "apple").embedding
        hits = self.store.search(query_vec, top_k=2)
        self.assertEqual(len(hits), 2)
        self.assertGreaterEqual(hits[0].score, hits[1].score)

    def test_search_min_score_filter(self):
        """min_score 过滤。"""
        c = self._make_chunk("c1", "target content")
        self.store.insert_batch([c], doc_id="doc_001")
        query_vec = c.embedding  # 完全相同 → 分数接近 1.0
        hits = self.store.search(query_vec, top_k=5, min_score=0.99)
        self.assertGreaterEqual(len(hits), 1)

    def test_delete_by_doc(self):
        """按文档 ID 删除。"""
        chunks = [self._make_chunk(f"c{i}", f"content-{i}") for i in range(5)]
        self.store.insert_batch(chunks, doc_id="doc_001")
        self.assertEqual(self.store.count(), 5)

        deleted = self.store.delete_by_doc("doc_001")
        self.assertEqual(deleted, 5)
        self.assertEqual(self.store.count(), 0)

    def test_delete_by_chunk_id(self):
        """按 chunk ID 删除。"""
        c = self._make_chunk("c1", "hello")
        self.store.insert_batch([c], doc_id="doc_001")
        self.assertTrue(self.store.delete_by_chunk_id("c1"))
        self.assertIsNone(self.store.get_chunk("c1"))

    def test_get_chunk(self):
        """按 ID 查询。"""
        c = self._make_chunk("c1", "hello world")
        self.store.insert_batch([c], doc_id="doc_001")
        found = self.store.get_chunk("c1")
        self.assertIsNotNone(found)
        self.assertEqual(found.content, "hello world")

    def test_list_documents(self):
        """列出所有文档。"""
        self.store.insert_batch([self._make_chunk("c1", "a")], doc_id="doc_a")
        self.store.insert_batch([self._make_chunk("c2", "b")], doc_id="doc_b")
        docs = self.store.list_documents()
        self.assertEqual(len(docs), 2)
        doc_ids = {d.doc_id for d in docs}
        self.assertIn("doc_a", doc_ids)
        self.assertIn("doc_b", doc_ids)

    def test_document_status_indexed(self):
        """文档记录状态为 INDEXED。"""
        chunks = [self._make_chunk("c1", "test")]
        self.store.insert_batch(chunks, doc_id="doc_001")
        docs = self.store.list_documents()
        self.assertEqual(docs[0].status, self.ParseStatus.INDEXED)

    def test_insert_batch_empty(self):
        """空列表不崩溃。"""
        ids = self.store.insert_batch([], doc_id="doc_empty")
        self.assertEqual(ids, [])

    def test_search_empty_query(self):
        """空查询向量返回空。"""
        results = self.store.search([], top_k=5)
        self.assertEqual(len(results), 0)

    def test_upsert_existing_chunk(self):
        """重复插入同一 chunk_id 会更新。"""
        c1 = self._make_chunk("c1", "original")
        self.store.insert_batch([c1], doc_id="doc_001")

        c2 = self.Chunk(
            chunk_id="c1",
            source_type=self.SourceType.TEXT,
            source_ref="test",
            content="updated content",
            seq_index=0,
            embedding=self._make_chunk("x", "updated").embedding,
        )
        self.store.insert_batch([c2], doc_id="doc_001")
        self.assertEqual(self.store.count(), 1)
        found = self.store.get_chunk("c1")
        self.assertEqual(found.content, "updated content")

    def test_multi_document_isolation(self):
        """多文档隔离删除。"""
        self.store.insert_batch(
            [self._make_chunk("c1", "doc_a")], doc_id="doc_a",
        )
        self.store.insert_batch(
            [self._make_chunk("c2", "doc_b")], doc_id="doc_b",
        )
        self.assertEqual(self.store.count(), 2)

        self.store.delete_by_doc("doc_a")
        self.assertEqual(self.store.count(), 1)
        hits = self.store.search(self._make_chunk("q", "doc_b").embedding, top_k=5)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.doc_id, "doc_b")

    def test_source_type_filter(self):
        """按来源类型过滤。"""
        pdf_chunk = self.Chunk(
            chunk_id="c_pdf",
            source_type=self.SourceType.PDF,
            content="pdf content",
            seq_index=0,
            embedding=[1.0] * 1024,
        )
        txt_chunk = self.Chunk(
            chunk_id="c_txt",
            source_type=self.SourceType.TEXT,
            content="text content",
            seq_index=0,
            embedding=[1.0] * 1024,
        )
        self.store.insert_batch([pdf_chunk, txt_chunk])

        hits = self.store.search([1.0] * 1024, top_k=5, source_type=self.SourceType.PDF)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.chunk_id, "c_pdf")


# =============================================================================
# 入口
# =============================================================================

if __name__ == "__main__":
    unittest.main()
