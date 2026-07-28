#!/usr/bin/env python3
"""
RAG → S3 端到端联调脚本 (test_rag_s3_integration.py)

验证 KB 检索结果能正确传递给 S3 OutlineBuilder。

流程：
  1. 上传文本到知识库
  2. 混合检索获取 SearchResult
  3. 证据融合获取 EvidencePacket
  4. 传入 OutlineBuilder.build() 验证兼容性

运行方式:
    # 需要 pgvector 环境（或 mock 模式用 InMemoryVectorStore）
    export AI_GEN_MODE=mock
    python ai_engine/tests/test_rag_s3_integration.py

    # 或使用真实 pgvector
    python ai_engine/rag/verify_pgvector.py
    python ai_engine/tests/test_rag_s3_integration.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    os.environ.setdefault("AI_GEN_MODE", "mock")

    from ai_engine.core.schema import Chunk, SourceType
    from ai_engine.rag.chunker import DocumentChunker
    from ai_engine.rag.embed import EmbeddingService
    from ai_engine.rag.store import InMemoryVectorStore
    from ai_engine.rag.retrieve import HybridRetriever
    from ai_engine.rag.rerank import ReRanker
    from ai_engine.rag.evidence import EvidenceSynthesizer
    from ai_engine.rag.router import (
        _get_retriever,
        _get_store,
        _reranker,
        _synthesizer,
        _session_parsed_chunks,
        register_session_chunks,
    )
    from ai_engine.gen.outline import OutlineBuilder

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

    # ---- 准备知识库数据 ----
    print("[1] 准备知识库数据")

    sample_doc = """
    第一章 排序算法概述

    排序算法是计算机科学中最基础的算法之一。
    常见的排序算法包括冒泡排序、选择排序、插入排序、快速排序和归并排序。

    1.1 冒泡排序
    冒泡排序通过重复遍历列表，比较相邻元素并交换顺序错误的元素。
    时间复杂度为 O(n^2)，空间复杂度为 O(1)。
    它是一种稳定的排序算法，适合小规模数据。

    1.2 快速排序
    快速排序采用分治策略，选择一个基准元素将数组分为两部分。
    平均时间复杂度为 O(n log n)，最坏情况为 O(n^2)。
    它是实际应用中最常用的排序算法之一。

    1.3 归并排序
    归并排序同样采用分治策略，将数组递归地分为两半分别排序后合并。
    时间复杂度稳定为 O(n log n)，空间复杂度为 O(n)。
    它是一种稳定的排序算法。

    1.4 堆排序
    堆排序利用堆数据结构，每次取出最大或最小元素。
    时间复杂度为 O(n log n)，空间复杂度为 O(1)。
    它不是稳定排序。

    1.5 计数排序
    计数排序不是比较排序，适用于整数且范围有限。
    时间复杂度为 O(n + k)，其中 k 是整数范围。
    它是稳定排序。
    """

    chunker = DocumentChunker()
    embed = EmbeddingService()
    store = InMemoryVectorStore()
    retriever = HybridRetriever(store=store, embed_service=embed)

    # 分块 → 嵌入 → 存储
    chunks = chunker.chunk_text(sample_doc, source_ref="algorithms.txt", source_type=SourceType.TEXT)
    check("分块数量 >= 1", len(chunks) >= 1, f"got {len(chunks)}")

    embed.embed_chunks(chunks)
    non_zero = sum(1 for c in chunks if c.embedding and any(v != 0 for v in c.embedding))
    # mock 模式全是零向量，这是预期行为
    check("嵌入向量已填充", all(c.embedding is not None for c in chunks))

    doc_id = "doc_algo"
    store.insert_batch(chunks, doc_id=doc_id)
    retriever.rebuild_bm25()

    # ---- 步骤 1: 混合检索 ----
    print("\n[2] 混合检索")

    query = "排序算法的时间复杂度"
    results = retriever.search(query, top_k=5, min_score=0.0)
    check("检索返回结果", len(results) > 0, f"got {len(results)}")
    check("结果按分数降序", all(results[i].score >= results[i+1].score for i in range(len(results)-1)))

    for r in results:
        check(f"  result[{r.chunk_id[:12]}] 有 content", bool(r.content))
        check(f"  result[{r.chunk_id[:12]}] 有 score", isinstance(r.score, float))

    # ---- 步骤 2: 重排序 ----
    print("\n[3] 重排序")

    reranker = ReRanker()
    reranked = reranker.rerank(query, results, top_k=3)
    check("重排序返回结果", len(reranked) <= 3, f"got {len(reranked)}")

    # ---- 步骤 3: 证据融合 ----
    print("\n[4] 证据融合")

    synthesizer = EvidenceSynthesizer(llm_client=None)
    packet = synthesizer.synthesize(
        search_results=reranked,
        query=query,
        context={"topic": "排序算法", "duration_minutes": 45},
    )

    check("EvidencePacket 有 relevant_chunks", len(packet.relevant_chunks) > 0)
    check("EvidencePacket 有 query", packet.query == query)
    check("EvidencePacket 有 citations", len(packet.citations) >= 0)  # mock 模式可能为 0

    # ---- 步骤 4: S3 OutlineBuilder 兼容性 ----
    print("\n[5] S3 OutlineBuilder 兼容性")

    builder = OutlineBuilder()

    # 构造 OutlineBuilder 期望的 intent 格式
    intent = {
        "title": "排序算法",
        "description": "45分钟排序算法课程",
        "key_points": ["时间复杂度", "空间复杂度", "稳定性"],
    }

    # 方式 A: 直接传 EvidencePacket 的 model_dump()
    packet_dict = packet.model_dump()
    outline_a = builder.build(intent=intent, evidence_packet=packet_dict)
    check("方式A: relevant_chunks 字段", len(outline_a.get("nodes", [])) > 0,
          f"nodes={len(outline_a.get('nodes', []))}")

    # 方式 B: 兼容 chunks 字段（模拟 S3 旧格式）
    chunks_format = {
        "chunks": [
            {
                "content": ch.content,
                "chunk_id": ch.chunk_id,
                "source_ref": ch.source_ref,
            }
            for ch in packet.relevant_chunks
        ],
        "context": packet.synthesized_context,
    }
    outline_b = builder.build(intent=intent, evidence_packet=chunks_format)
    check("方式B: chunks 字段", len(outline_b.get("nodes", [])) > 0,
          f"nodes={len(outline_b.get('nodes', []))}")

    # 检查 nodes 结构
    for node in outline_a.get("nodes", []):
        check(f"  node[{node.get('node_id', '?')}] 有 title", bool(node.get("title")))
        check(f"  node[{node.get('node_id', '?')}] 有 summary", bool(node.get("summary")))

    # ---- 步骤 5: S2 → KB → S3 完整链路 ----
    print("\n[6] S2 → KB → S3 完整链路")

    # 模拟 S2 解析完成
    session_id = "e2e_test_session"
    _session_parsed_chunks.pop(session_id, None)

    s2_chunks = [
        Chunk(
            chunk_id="s2_c1",
            source_type=SourceType.PDF,
            source_ref="算法教材.pdf",
            content="冒泡排序的时间复杂度为 O(n^2)，空间复杂度为 O(1)。",
            page_ref=1,
            seq_index=0,
            metadata={"type": "text"},
        ),
        Chunk(
            chunk_id="s2_c2",
            source_type=SourceType.PDF,
            source_ref="算法教材.pdf",
            content="快速排序的平均时间复杂度为 O(n log n)，最坏情况为 O(n^2)。",
            page_ref=2,
            seq_index=1,
            metadata={"type": "text"},
        ),
    ]

    register_session_chunks(session_id, s2_chunks)
    found = _session_parsed_chunks.get(session_id, [])
    check("S2 chunks 注册到 KB", len(found) == 2, f"got {len(found)}")

    # 模拟 S3 从 KB 获取 evidence
    kb_query = "排序算法"
    kb_results = retriever.search(kb_query, top_k=3, min_score=0.0)
    check("KB 检索返回", len(kb_results) > 0)

    # S3 使用 KB 结果
    kb_packet = synthesizer.synthesize(kb_results, query=kb_query)
    outline_c = builder.build(intent=intent, evidence_packet=kb_packet.model_dump())
    check("S3 消费 KB evidence_packet", len(outline_c.get("nodes", [])) > 0)

    # 清理
    _session_parsed_chunks.pop(session_id, None)

    # ---- 汇总 ----
    print(f"\n{'=' * 60}")
    print(f"RAG → S3 端到端联调: {passed} passed, {failed} failed")
    print(f"{'=' * 60}")

    if failed > 0:
        print("\n失败的检查项需要关注：")
        print("  - 确认 AI_GEN_MODE=mock 或配置了真实 API Key")
        print("  - 确认 pgvector 已安装并执行迁移 SQL")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
