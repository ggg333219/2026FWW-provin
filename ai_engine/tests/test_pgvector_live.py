#!/usr/bin/env python3
"""
PGVector 真机测试脚本 (test_pgvector_live.py)

在 PostgreSQL + pgvector 已就绪的环境中运行：
    pip install psycopg2-binary pgvector
    # 确保 DB 运行并执行迁移 SQL:
    psql -U postgres -d teaching -f ai_engine/rag/migrations/001_create_rag_tables.sql

    python ai_engine/tests/test_pgvector_live.py

使用环境变量覆盖默认连接：
    DB_HOST=127.0.0.1 DB_PORT=5433 DB_USER=postgres DB_PASSWORD=123456 DB_NAME=teaching \
    python ai_engine/tests/test_pgvector_live.py
"""

from __future__ import annotations

import hashlib
import os
import sys
import time


def main() -> int:
    # ---- 依赖检查 ----
    try:
        import psycopg2  # noqa
    except ImportError:
        print("SKIP: psycopg2-binary 未安装，跳过 pgvector 真机测试")
        print("  安装: pip install psycopg2-binary pgvector")
        return 0

    # ---- 连接检查 ----
    from ai_engine.core.schema import Chunk, ParseStatus, SourceType
    from ai_engine.rag.store_pgvector import (
        PGVectorStore,
        _format_vector,
        _row_to_indexed_chunk,
    )

    conn_string = (
        f"postgresql://"
        f"{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '123456')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
        f"/{os.getenv('DB_NAME', 'teaching')}"
    )

    print(f"连接: {conn_string.split('@')[0]}@***")

    try:
        store = PGVectorStore(conn_string=conn_string, table_prefix="test_live_")
    except RuntimeError as e:
        print(f"SKIP: {e}")
        return 0

    passed = 0
    failed = 0

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS: {name}")
        else:
            failed += 1
            print(f"  FAIL: {name} — {detail}")

    # ---- 辅助 ----

    def _vec(content: str, dim: int = 1024) -> list[float]:
        h = hashlib.md5(content.encode()).hexdigest()
        vec = [float(int(h[i:i+2], 16)) / 255.0 for i in range(0, min(len(h), dim * 2), 2)]
        return (vec + [0.0] * dim)[:dim]

    def _chunk(cid: str, content: str) -> Chunk:
        return Chunk(
            chunk_id=cid,
            source_type=SourceType.TEXT,
            source_ref="test.txt",
            content=content,
            seq_index=0,
            embedding=_vec(content),
        )

    # ---- 清理旧数据 ----
    try:
        cur = store.conn.cursor()
        cur.execute(f"DELETE FROM {store._t('rag_chunks')}")
        cur.execute(f"DELETE FROM {store._t('rag_documents')}")
        store.conn.commit()
        cur.close()
    except Exception:
        pass

    # ---- 测试 ----

    print("\n[1] 基础 CRUD")

    # insert + count
    chunks = [_chunk(f"c{i}", f"content-{i}") for i in range(10)]
    ids = store.insert_batch(chunks, doc_id="doc_001")
    check("insert_batch 返回 10 个 ID", len(ids) == 10, f"got {len(ids)}")
    check("count == 10", store.count() == 10, f"got {store.count()}")

    # search
    query_vec = _vec("content-0")
    hits = store.search(query_vec, top_k=3)
    check("search 返回结果", len(hits) > 0, f"got {len(hits)}")
    check("search 分数降序", all(hits[i].score >= hits[i+1].score for i in range(len(hits)-1)))

    # min_score filter
    hits_high = store.search(query_vec, top_k=5, min_score=0.99)
    check("min_score 过滤", len(hits_high) >= 1, f"got {len(hits_high)}")

    # source_type filter
    pdf_chunk = Chunk(chunk_id="c_pdf", source_type=SourceType.PDF,
                      content="pdf", seq_index=0, embedding=[1.0] * 1024)
    txt_chunk = Chunk(chunk_id="c_txt", source_type=SourceType.TEXT,
                      content="text", seq_index=0, embedding=[1.0] * 1024)
    store.insert_batch([pdf_chunk, txt_chunk])
    hits_pdf = store.search([1.0] * 1024, top_k=5, source_type=SourceType.PDF)
    check("source_type 过滤", len(hits_pdf) == 1 and hits_pdf[0].chunk.chunk_id == "c_pdf",
          f"got {len(hits_pdf)} results")

    # get_chunk
    found = store.get_chunk("c0")
    check("get_chunk 按 ID 查询", found is not None and found.content == "content-0")

    # list_documents
    docs = store.list_documents()
    check("list_documents 返回文档", len(docs) >= 2, f"got {len(docs)}")

    # document status
    doc_statuses = {d.doc_id: d.status for d in docs}
    check("文档状态为 INDEXED", any(s == ParseStatus.INDEXED for s in doc_statuses.values()))

    print("\n[2] 删除操作")

    # delete_by_chunk_id
    store.insert_batch([_chunk("del_1", "to_delete")])
    check("delete_by_chunk_id", store.delete_by_chunk_id("del_1"))
    check("删除后 get_chunk 为空", store.get_chunk("del_1") is None)

    # delete_by_doc
    store.insert_batch([_chunk("doc2_c1", "a")], doc_id="doc_002")
    store.insert_batch([_chunk("doc2_c2", "b")], doc_id="doc_003")
    deleted = store.delete_by_doc("doc_002")
    check("delete_by_doc 删除 1 条", deleted >= 1, f"deleted {deleted}")
    remaining = store.count()
    check(f"删除后剩余 {remaining} 条", remaining >= 10)

    print("\n[3] 向量格式")

    formatted = _format_vector([0.1, 2.5, 3.5])
    check("_format_vector 包含数字", all(str(x) in formatted for x in [0.1, 2.5, 3.5]))

    # _row_to_indexed_chunk
    row = ("chk_01", "doc_x", "file.pdf", "text", "hello world", 5, 0, "[0.1,0.2]", "{}")
    indexed = _row_to_indexed_chunk(row)
    check("_row_to_indexed_chunk 解析", indexed.chunk_id == "chk_01")
    check("_row_to_indexed_chunk embedding", len(indexed.embedding) == 2)

    # ---- 最终清理 ----
    try:
        cur = store.conn.cursor()
        cur.execute(f"DELETE FROM {store._t('rag_chunks')}")
        cur.execute(f"DELETE FROM {store._t('rag_documents')}")
        store.conn.commit()
        cur.close()
        store.close()
    except Exception:
        pass

    # ---- 汇总 ----
    print(f"\n{'='*50}")
    print(f"结果: {passed} passed, {failed} failed")
    print(f"{'='*50}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
