"""
P3 KB 知识库 RAG 单元测试

覆盖模块: chunker, embed, store (InMemory), retrieve (BM25 + Hybrid),
          rerank, evidence

运行方式:
    python -m pytest ai_engine/tests/test_rag.py -v
    python -m unittest ai_engine.tests.test_rag -v
"""

from __future__ import annotations

import asyncio
import os
import unittest

# ---- 确保 mock 模式，不依赖真实 API ----
os.environ["AI_GEN_MODE"] = "mock"

from ai_engine.core.schema import (
    Chunk,
    Citation,
    EvidencePacket,
    SearchResult,
    SourceType,
)


# =============================================================================
# 1. chunker 测试
# =============================================================================

class TestDocumentChunker(unittest.TestCase):
    """DocumentChunker 分块策略测试。"""

    @classmethod
    def setUpClass(cls):
        from ai_engine.rag.chunker import DocumentChunker, ChunkingStrategy
        cls.DocumentChunker = DocumentChunker
        cls.ChunkingStrategy = ChunkingStrategy

    def test_paragraph_strategy(self):
        """段落策略：按双换行拆分。"""
        chunker = self.DocumentChunker(strategy=self.ChunkingStrategy.PARAGRAPH)
        text = "第一段。\n\n第二段。\n\n第三段。"
        chunks = chunker.chunk_text(text, source_ref="test", source_type=SourceType.TEXT)
        self.assertGreaterEqual(len(chunks), 1)
        for c in chunks:
            # chunk_id 改为基于 (source_ref, seq_index) 的确定性 ID；
            # 测试用例源是单测期间的稳定字符串，确保格式可断言。
            # 详细不变量见 TestChunkIdDeterminism。
            self.assertRegex(c.chunk_id, r"^test::s\d{4}$", msg=f"非确定性 chunk_id: {c.chunk_id}")
            self.assertEqual(c.source_type, SourceType.TEXT)
            self.assertEqual(c.source_ref, "test")

    def test_slide_strategy(self):
        """幻灯片策略：按 --- 拆分，不限制大小。"""
        chunker = self.DocumentChunker(strategy=self.ChunkingStrategy.SLIDE)
        text = "Slide 1\n---\nSlide 2\n---\nSlide 3"
        chunks = chunker.chunk_text(text, source_ref="test.pptx", source_type=SourceType.PPTX)
        self.assertGreaterEqual(len(chunks), 2)
        for i, c in enumerate(chunks):
            self.assertEqual(c.seq_index, i)

    def test_section_strategy(self):
        """章节策略：按 # 标题拆分。"""
        chunker = self.DocumentChunker(strategy=self.ChunkingStrategy.SECTION)
        text = "# 第一章\n内容A\n\n# 第二章\n内容B\n\n# 第三章\n内容C"
        chunks = chunker.chunk_text(text, source_ref="test", source_type=SourceType.DOCX)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("第一章", chunks[0].content)

    def test_sentence_strategy(self):
        """句子策略：按句末标点拆分。"""
        chunker = self.DocumentChunker(strategy=self.ChunkingStrategy.SENTENCE)
        text = "第一句话。第二句话！第三句话？"
        chunks = chunker.chunk_text(text, source_ref="test", source_type=SourceType.IMAGE)
        self.assertGreaterEqual(len(chunks), 1)

    def test_window_strategy(self):
        """窗口策略：滑窗+overlap。"""
        chunker = self.DocumentChunker(
            strategy=self.ChunkingStrategy.WINDOW,
            chunk_size=128,
            overlap=16,
        )
        # 足够长的文本（多个段落），使用不同句子以避免被去重
        sentences = [f"第{i}句话。" for i in range(80)]
        text = "\n\n".join(sentences)
        chunks = chunker.chunk_text(text, source_ref="test", source_type=SourceType.VIDEO)
        self.assertGreater(len(chunks), 1)

    def test_auto_strategy_by_source_type(self):
        """自动根据 SourceType 选择策略。"""
        chunker = self.DocumentChunker()
        text = "Hello\n\nWorld"
        # PDF → PARAGRAPH
        chunks = chunker.chunk_text(text, source_ref="test.pdf", source_type=SourceType.PDF)
        self.assertGreater(len(chunks), 0)
        # PPTX → SLIDE
        chunks_pptx = chunker.chunk_text(text, source_ref="test.pptx", source_type=SourceType.PPTX)
        self.assertGreater(len(chunks_pptx), 0)

    def test_empty_text(self):
        """空文本不崩溃。"""
        chunker = self.DocumentChunker()
        chunks = chunker.chunk_text("", source_ref="test", source_type=SourceType.TEXT)
        self.assertEqual(len(chunks), 0)
        chunks = chunker.chunk_text("   \n\n   ", source_ref="test", source_type=SourceType.TEXT)
        self.assertEqual(len(chunks), 0)

    def test_rechunk(self):
        """rechunk: 对已分块的 Chunk 做二次切分。"""
        chunker = self.DocumentChunker(strategy=self.ChunkingStrategy.SENTENCE)
        existing = [
            Chunk(
                chunk_id="c1", source_type=SourceType.TEXT,
                source_ref="doc", content="句子A。句子B。句子C。"
            ),
            Chunk(
                chunk_id="c2", source_type=SourceType.TEXT,
                source_ref="doc", content="句子D。句子E。"
            ),
        ]
        result = chunker.rechunk(existing)
        # 二次切分后总数应 >= 原始数量
        self.assertGreaterEqual(len(result), len(existing))

    def test_metadata_passthrough(self):
        """metadata 传递到每个 Chunk。"""
        chunker = self.DocumentChunker()
        chunks = chunker.chunk_text(
            "测试内容", source_ref="test", source_type=SourceType.TEXT,
            metadata={"author": "张三", "year": 2024},
        )
        self.assertEqual(chunks[0].metadata.get("author"), "张三")
        self.assertEqual(chunks[0].metadata.get("year"), 2024)


# =============================================================================
# 2. embed 测试
# =============================================================================

class TestEmbeddingService(unittest.TestCase):
    """EmbeddingService 向量化测试。"""

    @classmethod
    def setUpClass(cls):
        from ai_engine.rag.embed import EmbeddingService
        cls.EmbeddingService = EmbeddingService

    def test_embed_text_mock(self):
        """Mock 模式返回零向量。"""
        svc = self.EmbeddingService()
        vec = svc.embed_text("hello")
        self.assertEqual(len(vec), 1024)
        self.assertTrue(all(v == 0.0 for v in vec))

    def test_embed_batch_mock(self):
        """批量向量化。"""
        svc = self.EmbeddingService(batch_size=2)
        texts = ["a", "b", "c", "d", "e"]
        vectors = svc.embed_batch(texts)
        self.assertEqual(len(vectors), 5)
        for v in vectors:
            self.assertEqual(len(v), 1024)

    def test_embed_chunks(self):
        """Chunk 列表批量嵌入。"""
        svc = self.EmbeddingService()
        chunks = [
            Chunk(chunk_id="c1", source_type=SourceType.TEXT, content="hello"),
            Chunk(chunk_id="c2", source_type=SourceType.TEXT, content="world"),
        ]
        result = svc.embed_chunks(chunks)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0].embedding), 1024)

    def test_empty_batch(self):
        """空列表不崩溃。"""
        svc = self.EmbeddingService()
        self.assertEqual(svc.embed_batch([]), [])
        self.assertEqual(svc.embed_chunks([]), [])

    def test_cosine_similarity_identical(self):
        """余弦相似度：相同向量 = 1.0。"""
        from ai_engine.rag.embed import cosine_similarity
        vec = [1.0, 2.0, 3.0]
        sim = cosine_similarity(vec, vec)
        self.assertAlmostEqual(sim, 1.0, places=4)

    def test_cosine_similarity_orthogonal(self):
        """余弦相似度：正交向量 = 0.0。"""
        from ai_engine.rag.embed import cosine_similarity
        sim = cosine_similarity([1.0, 0.0], [0.0, 1.0])
        self.assertAlmostEqual(sim, 0.0, places=4)

    def test_cosine_similarity_negative(self):
        """余弦相似度：反向向量 = -1.0。"""
        from ai_engine.rag.embed import cosine_similarity
        sim = cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        self.assertAlmostEqual(sim, -1.0, places=4)

    def test_cosine_similarity_empty(self):
        """空向量返回 0.0。"""
        from ai_engine.rag.embed import cosine_similarity
        self.assertEqual(cosine_similarity([], [1.0]), 0.0)
        self.assertEqual(cosine_similarity([1.0], []), 0.0)


# =============================================================================
# 3. store (InMemory) 测试
# =============================================================================

class TestInMemoryVectorStore(unittest.TestCase):
    """InMemoryVectorStore CRUD 测试。"""

    @classmethod
    def setUpClass(cls):
        from ai_engine.rag.store import InMemoryVectorStore
        cls.InMemoryVectorStore = InMemoryVectorStore

    def setUp(self):
        self.store = self.InMemoryVectorStore()

    def _make_chunk(self, cid: str, content: str, embedding=None) -> Chunk:
        return Chunk(
            chunk_id=cid, source_type=SourceType.TEXT,
            source_ref="test", content=content,
            embedding=embedding or [float(i % 10) for i in range(1024)],
        )

    def test_insert_and_count(self):
        """插入后 count 正确。"""
        chunks = [self._make_chunk(f"c{i}", f"content-{i}") for i in range(10)]
        ids = self.store.insert_batch(chunks, doc_id="doc_001")
        self.assertEqual(len(ids), 10)
        self.assertEqual(self.store.count(), 10)

    def test_search_returns_results(self):
        """向量检索返回结果。"""
        chunks = [
            self._make_chunk("c1", "apple banana"),
            self._make_chunk("c2", "cat dog"),
            self._make_chunk("c3", "apple pie"),
        ]
        self.store.insert_batch(chunks, doc_id="doc_001")

        query = [float(i % 10) for i in range(1024)]  # 与 c1/c2/c3 相似
        hits = self.store.search(query, top_k=2)
        self.assertEqual(len(hits), 2)
        self.assertGreaterEqual(hits[0].score, hits[1].score)

    def test_search_min_score_filter(self):
        """min_score 过滤。"""
        chunks = [self._make_chunk(f"c{i}", f"content-{i}") for i in range(5)]
        self.store.insert_batch(chunks, doc_id="doc_001")

        # 查询与第一块完全相同 → 分数很高
        query = list(chunks[0].embedding)
        hits = self.store.search(query, top_k=5, min_score=0.99)
        self.assertGreaterEqual(len(hits), 1)

    def test_search_source_type_filter(self):
        """按 SourceType 过滤。"""
        pdf_chunk = Chunk(chunk_id="c_pdf", source_type=SourceType.PDF,
                          content="pdf", embedding=[1.0] * 1024)
        txt_chunk = Chunk(chunk_id="c_txt", source_type=SourceType.TEXT,
                          content="text", embedding=[1.0] * 1024)
        self.store.insert_batch([pdf_chunk, txt_chunk])

        hits = self.store.search([1.0] * 1024, top_k=5, source_type=SourceType.PDF)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].chunk.chunk_id, "c_pdf")

    def test_hybrid_retriever_filters_knowledge_base(self):
        from ai_engine.rag.retrieve import HybridRetriever

        class _Embed:
            def embed_text(self, _query):
                return [1.0] * 1024

        kb_a = self._make_chunk("kb-a", "alpha", embedding=[1.0] * 1024)
        kb_a.metadata = {"knowledge_base_id": "kb_a"}
        kb_b = self._make_chunk("kb-b", "beta", embedding=[1.0] * 1024)
        kb_b.metadata = {"knowledge_base_id": "kb_b"}
        self.store.insert_batch([kb_a], doc_id="doc_a")
        self.store.insert_batch([kb_b], doc_id="doc_b")

        retriever = HybridRetriever(store=self.store, embed_service=_Embed())
        results = retriever.search("alpha", top_k=5, min_score=0.0, knowledge_base_ids=["kb_b"])

        self.assertTrue(results)
        self.assertTrue(all(item.metadata["knowledge_base_id"] == "kb_b" for item in results))

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
        c = self._make_chunk("c1", "hello")
        self.store.insert_batch([c], doc_id="doc_001")
        found = self.store.get_chunk("c1")
        self.assertIsNotNone(found)
        self.assertEqual(found.content, "hello")

    def test_list_documents(self):
        """列出所有文档。"""
        self.store.insert_batch(
            [self._make_chunk("c1", "a")], doc_id="doc_a",
        )
        self.store.insert_batch(
            [self._make_chunk("c2", "b")], doc_id="doc_b",
        )
        docs = self.store.list_documents()
        self.assertEqual(len(docs), 2)
        doc_ids = {d.doc_id for d in docs}
        self.assertIn("doc_a", doc_ids)
        self.assertIn("doc_b", doc_ids)

    def test_clear(self):
        """清空所有数据。"""
        self.store.insert_batch(
            [self._make_chunk("c1", "a")], doc_id="doc_001",
        )
        self.store.clear()
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(len(self.store.list_documents()), 0)

    def test_document_record_status(self):
        """文档记录状态为 INDEXED。"""
        from ai_engine.core.schema import ParseStatus
        chunks = [self._make_chunk("c1", "a")]
        self.store.insert_batch(chunks, doc_id="doc_001")
        docs = self.store.list_documents()
        self.assertEqual(docs[0].status, ParseStatus.INDEXED)


# =============================================================================
# 4. retrieve (BM25 + Hybrid) 测试
# =============================================================================

class TestBM25Scorer(unittest.TestCase):
    """BM25Scorer 关键词检索测试。"""

    @classmethod
    def setUpClass(cls):
        from ai_engine.rag.retrieve import BM25Scorer
        cls.BM25Scorer = BM25Scorer

    def test_tokenize_chinese(self):
        """中文分词：单字 + 2-gram。"""
        tokens = self.BM25Scorer.tokenize("排序算法")
        self.assertIn("排", tokens)
        self.assertIn("序", tokens)
        self.assertIn("排序", tokens)
        self.assertIn("算法", tokens)

    def test_tokenize_english(self):
        """英文分词：小写单词。"""
        tokens = self.BM25Scorer.tokenize("Hello World")
        self.assertIn("hello", tokens)
        self.assertIn("world", tokens)

    def test_tokenize_empty(self):
        """空文本分词。"""
        self.assertEqual(self.BM25Scorer.tokenize(""), [])

    def test_index_and_search(self):
        """索引 + 检索。"""
        bm25 = self.BM25Scorer()
        docs = [
            "冒泡排序是一种简单的排序算法",
            "快速排序采用分治策略",
            "归并排序也是分治算法且稳定",
        ]
        bm25.index(docs)

        results = bm25.search("排序算法", top_k=2)
        self.assertGreater(len(results), 0)
        self.assertGreater(results[0][1], 0)  # score > 0

    def test_search_no_results(self):
        """无匹配时返回空。"""
        bm25 = self.BM25Scorer()
        bm25.index(["只有中文", "没有匹配"])
        results = bm25.search("xyz abc", top_k=5)
        self.assertEqual(len(results), 0)

    def test_search_empty_corpus(self):
        """空索引检索不崩溃。"""
        bm25 = self.BM25Scorer()
        bm25.index([])
        results = bm25.search("test", top_k=5)
        self.assertEqual(len(results), 0)


class TestHybridRetriever(unittest.TestCase):
    """HybridRetriever 混合检索测试。"""

    @classmethod
    def setUpClass(cls):
        from ai_engine.rag.embed import EmbeddingService
        from ai_engine.rag.store import InMemoryVectorStore
        from ai_engine.rag.retrieve import HybridRetriever
        cls.EmbeddingService = EmbeddingService
        cls.InMemoryVectorStore = InMemoryVectorStore
        cls.HybridRetriever = HybridRetriever

    def setUp(self):
        self.store = self.InMemoryVectorStore()
        self.embed = self.EmbeddingService()
        self.retriever = self.HybridRetriever(
            store=self.store, embed_service=self.embed,
        )

    def _add_test_data(self):
        """添加测试数据到 store。"""
        texts = [
            "冒泡排序通过重复遍历列表，比较相邻元素并交换",
            "快速排序选择一个基准元素，将数组分为两部分",
            "归并排序将数组递归地分为两半，分别排序后合并",
            "插入排序类似于整理扑克牌，将元素插入已排序部分",
            "堆排序利用堆数据结构，每次取出最大或最小元素",
            "选择排序每次从未排序部分选出最小元素",
            "希尔排序是插入排序的改进版本，使用递减增量",
            "计数排序不是比较排序，适用于整数且范围有限",
            "基数排序按位数从低到高依次排序，稳定高效",
            "桶排序将数据分散到多个桶，每个桶内部排序后合并",
        ]
        chunks = [
            Chunk(
                chunk_id=f"c{i}",
                source_type=SourceType.TEXT,
                source_ref="algorithms.txt",
                content=t,
                seq_index=i,
            )
            for i, t in enumerate(texts)
        ]
        self.embed.embed_chunks(chunks)
        self.store.insert_batch(chunks, doc_id="doc_algo")

    def test_hybrid_search(self):
        """混合检索基础功能。"""
        self._add_test_data()
        results = self.retriever.search("排序算法", top_k=5, min_score=0.0)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertTrue(r.chunk_id)
            self.assertIsInstance(r.score, float)
            self.assertIsInstance(r.content, str)

    def test_hybrid_search_score_descending(self):
        """分数降序。"""
        self._add_test_data()
        results = self.retriever.search("快速排序", top_k=5, min_score=0.0)
        if len(results) >= 2:
            self.assertGreaterEqual(results[0].score, results[1].score)

    def test_hybrid_search_min_score(self):
        """min_score 过滤。"""
        self._add_test_data()
        results = self.retriever.search("排序", top_k=10, min_score=0.6)
        # 所有结果分数 >= 0.6 或为空
        for r in results:
            self.assertGreaterEqual(r.score, 0.6)

    def test_hybrid_search_empty_store(self):
        """空 store 检索不崩溃。"""
        results = self.retriever.search("test", top_k=5, min_score=0.0)
        self.assertEqual(len(results), 0)

    def test_rebuild_bm25(self):
        """重建 BM25 索引。"""
        self._add_test_data()
        self.retriever.rebuild_bm25()  # 不崩溃


# =============================================================================
# 5. rerank 测试
# =============================================================================

class TestReRanker(unittest.TestCase):
    """ReRanker 重排序测试。"""

    @classmethod
    def setUpClass(cls):
        from ai_engine.rag.rerank import ReRanker
        cls.ReRanker = ReRanker

    def test_pass_through_no_model(self):
        """无模型时透传。"""
        reranker = self.ReRanker()
        candidates = [
            SearchResult(chunk_id="c1", content="aaa", score=0.3),
            SearchResult(chunk_id="c2", content="bbb", score=0.9),
            SearchResult(chunk_id="c3", content="ccc", score=0.5),
        ]
        result = reranker.rerank(query="test", candidates=candidates, top_k=2)
        self.assertEqual(len(result), 2)
        # 透传：保持原顺序，取前 2
        self.assertEqual(result[0].chunk_id, "c1")
        self.assertEqual(result[1].chunk_id, "c2")

    def test_empty_candidates(self):
        """空列表不崩溃。"""
        reranker = self.ReRanker()
        result = reranker.rerank(query="test", candidates=[], top_k=5)
        self.assertEqual(len(result), 0)

    def test_top_k_larger_than_candidates(self):
        """top_k > len(candidates) 时返回全部。"""
        reranker = self.ReRanker()
        candidates = [
            SearchResult(chunk_id="c1", content="a", score=0.5),
        ]
        result = reranker.rerank(query="test", candidates=candidates, top_k=5)
        self.assertEqual(len(result), 1)

    def test_model_name_not_installed_fallback(self):
        """模型未安装时回退透传。"""
        reranker = self.ReRanker(model_name="nonexistent/model-name")
        candidates = [
            SearchResult(chunk_id="c1", content="test", score=0.8),
        ]
        result = reranker.rerank(query="test", candidates=candidates, top_k=5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].chunk_id, "c1")


# =============================================================================
# 6. evidence 测试
# =============================================================================

class TestEvidenceSynthesizer(unittest.TestCase):
    """EvidenceSynthesizer 证据合成测试。"""

    @classmethod
    def setUpClass(cls):
        from ai_engine.core import LLMClient
        from ai_engine.rag.evidence import EvidenceSynthesizer
        cls.LLMClient = LLMClient
        cls.EvidenceSynthesizer = EvidenceSynthesizer

    def test_synthesize_mock(self):
        """Mock 模式合成。"""
        llm = self.LLMClient()
        synth = self.EvidenceSynthesizer(llm_client=llm)
        results = [
            SearchResult(
                chunk_id="c1",
                content="冒泡排序的时间复杂度是 O(n^2)",
                score=0.95,
                source={"file_name": "algo.pdf", "page": 3},
            ),
            SearchResult(
                chunk_id="c2",
                content="快速排序平均时间复杂度 O(n log n)",
                score=0.88,
                source={"file_name": "algo.pdf", "page": 5},
            ),
        ]
        packet = synth.synthesize(
            search_results=results,
            query="排序算法复杂度对比",
            context={"topic": "排序算法", "duration_minutes": 45},
        )
        self.assertIsInstance(packet, EvidencePacket)
        self.assertEqual(len(packet.relevant_chunks), 2)
        self.assertEqual(packet.query, "排序算法复杂度对比")

    def test_synthesize_empty(self):
        """空结果不崩溃。"""
        llm = self.LLMClient()
        synth = self.EvidenceSynthesizer(llm_client=llm)
        packet = synth.synthesize(search_results=[], query="test")
        self.assertEqual(len(packet.relevant_chunks), 0)
        self.assertEqual(len(packet.citations), 0)

    def test_synthesize_to_response(self):
        """合成并包装为 EvidenceResponse。"""
        llm = self.LLMClient()
        synth = self.EvidenceSynthesizer(llm_client=llm)
        results = [
            SearchResult(chunk_id="c1", content="test content", score=0.9),
        ]
        response = synth.synthesize_to_response(
            search_results=results,
            query="test",
            context={"key": "value"},
        )
        self.assertIsNotNone(response.evidence_packet)
        self.assertEqual(response.evidence_packet.query, "test")

    def test_fallback_citation_generation(self):
        """回退模式下 citation 自动生成。"""
        llm = self.LLMClient()
        synth = self.EvidenceSynthesizer(llm_client=llm)
        results = [
            SearchResult(
                chunk_id="c1",
                content="some content for fallback test",
                score=0.8,
                source={"file_name": "doc.pdf", "page": 1},
            ),
        ]
        packet = synth.synthesize(results, query="fallback test")
        # Mock 模式 LLM 不可用 → 回退拼接
        self.assertGreater(len(packet.synthesized_context), 0)
        self.assertGreater(len(packet.citations), 0)


# =============================================================================
# 7. store_pgvector (skip if not installed) 测试
# =============================================================================

class TestPGVectorStore(unittest.TestCase):
    """PGVectorStore 基础测试（Skip if no pgvector available）。"""

    def test_import(self):
        """PGVectorStore 可导入。"""
        try:
            from ai_engine.rag.store_pgvector import PGVectorStore
            self.assertTrue(True)
        except ImportError as e:
            self.skipTest(f"pgvector 依赖未安装: {e}")

    def test_format_vector(self):
        """向量格式化辅助函数。"""
        from ai_engine.rag.store_pgvector import _format_vector
        formatted = _format_vector([1.0, 2.0, 3.0])
        self.assertIn("1", formatted)
        self.assertIn("2", formatted)
        self.assertIn("3", formatted)


# =============================================================================
# 8. S2 → KB 对接测试
# =============================================================================

class TestS2ToKBBridge(unittest.TestCase):
    """S2 解析完成后自动注册 chunks 到 KB 的桥接测试。"""

    def test_register_session_chunks(self):
        """register_session_chunks 将 chunks 存入 session 映射。"""
        from ai_engine.rag.router import (
            register_session_chunks,
            _find_session_chunks,
            _session_parsed_chunks,
        )

        session_id = "test_session_001"
        # 清理可能的前置数据
        _session_parsed_chunks.pop(session_id, None)

        chunks = [
            Chunk(chunk_id="c1", source_type=SourceType.TEXT,
                  source_ref="doc.pdf", content="hello world"),
            Chunk(chunk_id="c2", source_type=SourceType.PDF,
                  source_ref="doc.pdf", content="second chunk"),
        ]
        register_session_chunks(session_id, chunks)

        found = _find_session_chunks(session_id)
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].chunk_id, "c1")
        self.assertEqual(found[1].chunk_id, "c2")

        # 追加注册不会覆盖
        register_session_chunks(session_id, [Chunk(chunk_id="c3", source_type=SourceType.TEXT, content="third")])
        found = _find_session_chunks(session_id)
        self.assertEqual(len(found), 3)

        # 清理
        _session_parsed_chunks.pop(session_id, None)

    def test_find_session_chunks_empty(self):
        """空 session 返回空列表。"""
        from ai_engine.rag.router import _find_session_chunks
        result = _find_session_chunks("nonexistent_session")
        self.assertEqual(result, [])

    def test_kb_upload_from_session(self):
        """知识库上传端点能通过 session_id 找到 S2 产出的 chunks。"""
        import asyncio
        from ai_engine.rag.router import (
            _find_session_chunks,
            _session_parsed_chunks,
            knowledge_upload,
            KnowledgeUploadRequest,
            register_session_chunks,
        )

        session_id = "kb_upload_test_session"
        _session_parsed_chunks.pop(session_id, None)

        # 模拟 S2 注册 chunks
        chunks = [
            Chunk(chunk_id="s2_c1", source_type=SourceType.TEXT,
                  source_ref="material.pdf", content="排序算法是计算机科学的基础"),
            Chunk(chunk_id="s2_c2", source_type=SourceType.TEXT,
                  source_ref="material.pdf", content="快速排序平均复杂度 O(n log n)"),
        ]
        register_session_chunks(session_id, chunks)

        # 调用知识库上传（通过 session_id）
        req = KnowledgeUploadRequest(session_id=session_id)
        response = asyncio.run(knowledge_upload(req))

        self.assertEqual(response.status, "done")
        self.assertGreater(response.chunk_count, 0)
        self.assertTrue(response.document_id)

        # 清理
        _session_parsed_chunks.pop(session_id, None)


# =============================================================================
# 9. SearchRequest 默认值（min_score 修复）
# =============================================================================

class TestSearchRequestDefaults(unittest.TestCase):
    """SearchRequest 默认值回归测试。

    历史：旧版 min_score 默认 0.6 偏高，用户侧易误判"知识库没生效"。
    修复后默认值降到 0.2，且 SearchRequest 接受 0-1 间任意阈值覆盖。
    """

    def test_min_score_default_is_lowered(self):
        from ai_engine.core.schema import SearchRequest
        req = SearchRequest(query="hello")
        self.assertEqual(req.min_score, 0.2)

    def test_min_score_override_accepted(self):
        from ai_engine.core.schema import SearchRequest
        req = SearchRequest(query="hello", min_score=0.5)
        self.assertEqual(req.min_score, 0.5)

    def test_min_score_zero_means_no_filter(self):
        """min_score=0 应被允许（用于调试与 RAG 召回探查）。"""
        from ai_engine.core.schema import SearchRequest
        req = SearchRequest(query="hello", min_score=0.0)
        self.assertEqual(req.min_score, 0.0)


# =============================================================================
# 10. chunker chunk_id 确定性（idempotent 灌库前置）
# =============================================================================

class TestChunkIdDeterminism(unittest.TestCase):
    """chunk_id 必须是 (source_ref, seq_index) 决定，与执行次数无关。

    这是 idempotent 灌库的前置条件：每次启动语料扫描必须复用同一组
    chunk_id，否则 store.insert_batch 会累积重复切片。
    """

    @classmethod
    def setUpClass(cls):
        from ai_engine.rag.chunker import DocumentChunker
        cls.DocumentChunker = DocumentChunker

    def test_same_source_ref_produces_same_chunk_id(self):
        """同 source_ref + 文本 → 同 chunk_id 序列。"""
        chunker = self.DocumentChunker()
        text = "段落1\n\n段落2\n\n段落3"
        chunks1 = chunker.chunk_text(text, source_ref="教材.pdf", source_type=SourceType.PDF)
        chunks2 = chunker.chunk_text(text, source_ref="教材.pdf", source_type=SourceType.PDF)
        ids1 = [c.chunk_id for c in chunks1]
        ids2 = [c.chunk_id for c in chunks2]
        self.assertEqual(ids1, ids2, msg="同输入两次必须产出同 chunk_id")

    def test_different_seq_produces_different_id(self):
        """同 source_ref 不同 seq_index 必须产生不同 chunk_id。

        PARAGRAPH 默认 chunk_size=512 token。短文本会被合并成 1 个窗口，
        所以必须给出能突破窗口大小的输入才能产生 ≥2 个 chunk。
        """
        from ai_engine.rag.chunker import ChunkingStrategy
        # 用 WINDOW 策略 + 小 chunk_size，强制分出多块
        chunker = self.DocumentChunker(
            strategy=ChunkingStrategy.WINDOW, chunk_size=64, overlap=8,
        )
        paragraphs = [f"第{i}段内容：" + "x" * 80 for i in range(12)]
        ids = [c.chunk_id for c in chunker.chunk_text(
            "\n\n".join(paragraphs), source_ref="y", source_type=SourceType.TEXT,
        )]
        self.assertGreaterEqual(len(ids), 2, msg=f"期望 ≥2 chunks，实际 {len(ids)}")
        # 同 source_ref 但不同 seq_index → 必须产生不同 chunk_id
        self.assertEqual(len(set(ids)), len(ids), msg=f"chunk_id 出现重复: {ids}")

    def test_chunk_id_uses_safe_chars(self):
        """chunk_id 仅含 [A-Za-z0-9._-] + ::s + 数字；避免 PG/Redis 解析异常。"""
        chunker = self.DocumentChunker()
        # 故意用含空格、中文、特殊字符的 source_ref
        weird_ref = r"D:\path\to\file 1 (中文).pdf"
        chunks = chunker.chunk_text("内容", source_ref=weird_ref, source_type=SourceType.PDF)
        for c in chunks:
            self.assertRegex(
                c.chunk_id, r"^[A-Za-z0-9._\-]+::s\d{4}$",
                msg=f"非安全字符 chunk_id: {c.chunk_id!r}",
            )

    def test_chunk_id_within_64_chars(self):
        """chunk_id 必须 ≤64 chars（PG VARCHAR(64) 列宽限制）。"""
        chunker = self.DocumentChunker()
        chunks = chunker.chunk_text(
            "内容", source_ref="a" * 200 + ".pdf", source_type=SourceType.PDF
        )
        for c in chunks:
            self.assertLessEqual(len(c.chunk_id), 64, msg=f"超长 chunk_id: {c.chunk_id!r}")

    def test_chunk_id_no_random_per_call(self):
        """两次调用不应出现 chunk_{uuid} 形式的随机 ID（旧版格式）。"""
        import re as _re
        chunker = self.DocumentChunker()
        ids = [c.chunk_id for c in chunker.chunk_text("a\n\nb", source_ref="x", source_type=SourceType.TEXT)]
        for cid in ids:
            self.assertNotRegex(cid, r"^chunk_[0-9a-f]{12}$", msg=f"仍含随机 chunk_id: {cid}")


# =============================================================================
# 11. InMemoryVectorStore: idempotent upsert + list_chunk_ids 抽象方法
# =============================================================================

class TestInMemoryStoreUpsertAndListIds(unittest.TestCase):
    """幂等 upsert：同 chunk_id 二次 insert 不应产生重复切片。

    与此前的实现差异：旧 insert_batch 直接覆盖 self._chunks[key]，但
    新增 _doc_chunks 追加新 doc_id 映射，会导致 list_documents() 返回
    多次同名文档。本次测试同时覆盖 list_chunk_ids(doc_id) 这条新抽象
    接口（为 PGVectorStore 接入做准备）。
    """

    @classmethod
    def setUpClass(cls):
        from ai_engine.rag.store import InMemoryVectorStore, VectorStore
        cls.InMemoryVectorStore = InMemoryVectorStore
        cls.VectorStore = VectorStore

    def setUp(self):
        self.store = self.InMemoryVectorStore()

    def _make_chunk(self, cid, content="hi", embedding=None):
        return Chunk(
            chunk_id=cid, source_type=SourceType.TEXT, source_ref="src",
            content=content, embedding=embedding or [0.1] * 1024,
        )

    def test_insert_batch_is_idempotent(self):
        """同 chunk_id 二次 insert_batch：count 不变、最新内容胜出。"""
        ch = self._make_chunk("abc::s0001", content="first")
        self.store.insert_batch([ch], doc_id="doc1")
        self.assertEqual(self.store.count(), 1)

        ch2 = self._make_chunk("abc::s0001", content="second")
        self.store.insert_batch([ch2], doc_id="doc2")
        # count 不变（幂等）；最新内容胜出
        self.assertEqual(self.store.count(), 1)
        fetched = self.store.get_chunk("abc::s0001")
        self.assertEqual(fetched.content, "second")

    def test_insert_batch_idempotent_keeps_single_doc_view(self):
        """二次灌同源 → count 不变；list_documents 列出两个 doc 但 chunk 不重复。"""
        chunks = [self._make_chunk(f"src::s{i:04d}", content=f"c{i}") for i in range(3)]
        self.store.insert_batch(chunks, doc_id="doc1")
        self.store.insert_batch(chunks, doc_id="doc2")  # 同 chunk_ids
        self.assertEqual(self.store.count(), 3)
        self.assertEqual(len(self.store.list_documents()), 2)

    def test_list_chunk_ids_returns_chunk_ids_for_doc(self):
        """list_chunk_ids(doc_id) 返回该 doc 下的 chunk_id 列表。"""
        chunks = [self._make_chunk(f"x::s{i:04d}", content=f"c{i}") for i in range(3)]
        self.store.insert_batch(chunks, doc_id="doc1")
        ids = self.store.list_chunk_ids("doc1")
        self.assertEqual(sorted(ids), ["x::s0000", "x::s0001", "x::s0002"])

    def test_list_chunk_ids_unknown_doc_returns_empty(self):
        """list_chunk_ids 不存在的 doc 返回空列表（不抛异常）。"""
        self.assertEqual(self.store.list_chunk_ids("ghost_doc"), [])

    def test_list_chunk_ids_is_abstract_on_vector_store(self):
        """list_chunk_ids 必须是 VectorStore 抽象方法 —— PG 实现必须实现。"""
        self.assertTrue(
            hasattr(self.VectorStore, "list_chunk_ids"),
            msg="VectorStore 必须暴露 list_chunk_ids 抽象方法",
        )
        # VectorStore 本身应仍是抽象类（不能直接实例化）
        import inspect
        self.assertTrue(inspect.isabstract(self.VectorStore))

    def test_rebuild_bm25_does_not_touch_private_attr(self):
        """HybridRetriever.rebuild_bm25 不再读取 store._doc_chunks 私有属性。

        旧实现 hasattr(store, '_doc_chunks') 摸私有属性，PG 接入后返回
        空导致 BM25 静默退化。新实现应通过抽象 list_chunk_ids(doc_id) 拿。
        """
        from ai_engine.rag.retrieve import HybridRetriever
        from ai_engine.rag.embed import EmbeddingService

        # 1. 先正常灌入 chunks（走 insert_batch 接口）
        chunks = [
            self._make_chunk(f"y::s{i:04d}", content=f"排序算法内容 {i}")
            for i in range(5)
        ]
        self.store.insert_batch(chunks, doc_id="doc1")

        # 2. 模拟 PG 实现：抹掉私有 _doc_chunks，让旧 hasattr 分支退化
        #    （旧实现走 hasattr 摸私有属性 → BM25 索引为空 → 静默失败）
        if hasattr(self.store, "_doc_chunks"):
            del self.store._doc_chunks  # 让 hasattr 返回 False

        # 3. rebuild_bm25 / search 应仍能正常返回结果
        retriever = HybridRetriever(store=self.store, embed_service=EmbeddingService())
        retriever.rebuild_bm25()  # 不应抛 AttributeError 或退化
        results = retriever.search("排序算法", top_k=3, min_score=0.0)
        self.assertGreater(len(results), 0, msg="BM25 应能通过 list_chunk_ids 重建索引")


if __name__ == "__main__":
    unittest.main()
