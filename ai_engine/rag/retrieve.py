"""
混合检索器 (retrieve.py)

实现向量相似度 + BM25 关键词混合检索，按设计文档 §6 权重融合：

    score = 0.7 × cosine_sim(query_embedding, chunk_embedding)
          + 0.3 × bm25_score(query, chunk)

质量阈值 min_score = 0.6，低于此阈值的结果丢弃。

使用方式：
    from ai_engine.rag.retrieve import HybridRetriever

    retriever = HybridRetriever(store=store, embed_service=embed_svc)
    results = retriever.search("什么是排序算法？", top_k=5)
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Optional

from ai_engine.core.schema import SearchResult, SourceType
from ai_engine.rag.embed import EmbeddingService
from ai_engine.rag.store import VectorStore, SearchHit

# ---- 混合权重 ----

_VECTOR_WEIGHT = 0.7
_BM25_WEIGHT = 0.3


# =============================================================================
# BM25 实现（纯 Python，零依赖）
# =============================================================================

class BM25Scorer:
    """
    简易 BM25 关键词检索器。

    参考 Okapi BM25 算法，支持中文（单字切分 + 2-gram）。

    使用方式：
        bm25 = BM25Scorer()
        bm25.index(corpus)  # corpus = [text1, text2, ...]
        scores = bm25.search("查询", top_k=10)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._docs: list[str] = []
        self._doc_len: list[int] = []
        self._avgdl: float = 0.0
        self._df: dict[str, int] = defaultdict(int)  # 文档频率
        self._tf: list[dict[str, int]] = []            # 每篇文档的词频
        self._N: int = 0

    # ---- 分词 ----

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """
        中英文混合分词：中文按单字 + 2-gram，英文按小写单词。

        这确保了中英文查询都能匹配，且中文支持部分匹配。
        """
        if not text:
            return []
        tokens: list[str] = []
        # 提取中文连续段和非中文段
        segments = re.findall(r"[一-鿿]+|[a-zA-Z0-9]+", text.lower())
        for seg in segments:
            if re.match(r"[一-鿿]", seg[0]):
                # 中文：单字
                tokens.extend(list(seg))
                # 中文：2-gram
                for i in range(len(seg) - 1):
                    tokens.append(seg[i:i + 2])
            else:
                # 英文/数字：直接作为一个 token
                tokens.append(seg)
        return tokens

    # ---- 索引 ----

    def index(self, docs: list[str]) -> None:
        """
        构建 BM25 索引。

        Args:
            docs: 文档文本列表（通常每篇对应一个 Chunk）。
        """
        self._docs = list(docs)
        self._N = len(docs)
        self._doc_len = []
        self._df.clear()
        self._tf = []

        for doc in docs:
            tokens = self.tokenize(doc)
            self._doc_len.append(len(tokens))
            tf: dict[str, int] = defaultdict(int)
            for t in tokens:
                tf[t] += 1
            self._tf.append(tf)
            for t in set(tokens):
                self._df[t] += 1

        self._avgdl = sum(self._doc_len) / max(self._N, 1)

    def search(self, query: str, top_k: int = 20) -> list[tuple[int, float]]:
        """
        BM25 检索。

        Returns:
            list[(doc_index, score)]: 按分数降序排列。
        """
        if self._N == 0:
            return []

        query_tokens = self.tokenize(query)
        scores: list[tuple[int, float]] = []

        for i in range(self._N):
            score = self._bm25_score(query_tokens, i)
            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _bm25_score(self, query_tokens: list[str], doc_idx: int) -> float:
        """计算单个文档的 BM25 分数。"""
        dl = self._doc_len[doc_idx]
        tf = self._tf[doc_idx]
        score = 0.0
        for t in query_tokens:
            if t not in self._df:
                continue
            df = self._df[t]
            idf = math.log(1 + (self._N - df + 0.5) / (df + 0.5))
            freq = tf.get(t, 0)
            numerator = freq * (self.k1 + 1)
            denominator = freq + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
            score += idf * numerator / denominator if denominator > 0 else 0.0
        return score


# =============================================================================
# HybridRetriever
# =============================================================================

class HybridRetriever:
    """
    混合检索器：向量相似度 (0.7) + BM25 关键词 (0.3)。

    使用方式：
        retriever = HybridRetriever(store=store, embed_service=embed_svc)
        results = retriever.search("冒泡排序的复杂度", top_k=5)
    """

    def __init__(
        self,
        store: VectorStore,
        embed_service: EmbeddingService,
        vector_weight: float = _VECTOR_WEIGHT,
        bm25_weight: float = _BM25_WEIGHT,
    ):
        """
        Args:
            store: 向量存储实例。
            embed_service: 嵌入服务实例。
            vector_weight: 向量相似度权重（默认 0.7）。
            bm25_weight: BM25 关键词权重（默认 0.3）。
        """
        self.store = store
        self.embed = embed_service
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self._bm25: Optional[BM25Scorer] = None
        self._bm25_doc_ids: list[str] = []  # doc_idx → chunk_id 映射

    # ---- 公开 API ----

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.6,
        knowledge_base_ids: Optional[list[str]] = None,
        source_type: Optional[SourceType] = None,
        scope: str = "course",
        node_id: Optional[str] = None,
        page_id: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        混合检索：向量 + BM25 融合打分。

        Args:
            query: 查询文本。
            top_k: 返回结果数。
            min_score: 最低分数阈值（低于此值丢弃）。
            knowledge_base_ids: 限定知识库范围（目前未实现过滤）。
            source_type: 限定来源类型。

        Returns:
            list[SearchResult]: 按融合分数降序排列。
        """
        # 1. 向量检索（召回 top_k × 4 作为候选池）
        query_vec = self.embed.embed_text(query)
        # Embedding 可用性检测：query 向量非零才认为向量侧有效。
        # 当 AI_API_KEY 缺失/占位符或 embed API 失败时，LLMClient.embed 回退为
        # 全零向量，此时混合融合分数上限只有 0.3（BM25 权重），会被 min_score
        # 全部滤掉 → 退化为纯 BM25 兜底，保证无 embedding key 时 RAG 仍可检索。
        vector_available = bool(query_vec) and any(v != 0.0 for v in query_vec)

        vector_hits = self.store.search(
            query_vec,
            top_k=min(top_k * 4, 200),
            min_score=0.0,  # 向量侧不过滤，留给融合后统一阈值
            source_type=source_type,
        )
        vector_hits = [
            hit for hit in vector_hits
            if self._matches_scope(hit.chunk, scope, node_id, page_id)
        ]

        # 向量不可用 → 纯 BM25 检索
        if not vector_available:
            return self._bm25_only_search(query, top_k, min_score, source_type, scope, node_id, page_id)

        if not vector_hits:
            return []

        # 2. 归一化向量分数到 [0, 1]
        v_scores = self._normalize_scores(
            {h.chunk.chunk_id: h.score for h in vector_hits}
        )

        # 3. BM25 关键词检索
        b_scores = self._bm25_scores(query)

        # 4. 融合打分
        fused: list[tuple[SearchHit, float]] = []
        for hit in vector_hits:
            cid = hit.chunk.chunk_id
            v = v_scores.get(cid, 0.0)
            b = b_scores.get(cid, 0.0)
            score = self.vector_weight * v + self.bm25_weight * b
            if score >= min_score:
                fused.append((hit, score))

        fused.sort(key=lambda x: x[1], reverse=True)
        top = fused[:top_k]

        # 5. 构建 SearchResult
        return [
            SearchResult(
                chunk_id=hit.chunk.chunk_id,
                content=hit.chunk.content,
                score=round(score, 4),
                source={
                    "file_name": hit.chunk.source_ref,
                    "page": hit.chunk.page_ref or 0,
                    "type": hit.chunk.source_type.value,
                },
                metadata={
                    "doc_id": hit.chunk.doc_id,
                    "seq_index": hit.chunk.seq_index,
                    **hit.chunk.metadata,
                },
            )
            for hit, score in top
        ]

    def rebuild_bm25(self) -> None:
        """重建 BM25 索引（数据变更后调用）。"""
        self._bm25 = BM25Scorer()
        self._bm25_doc_ids = []

        # 从 store 读取所有 chunk
        docs = self.store.list_documents()
        all_texts: list[str] = []
        for doc in docs:
            for cid in self._get_doc_chunk_ids(doc.doc_id):
                chunk = self.store.get_chunk(cid)
                if chunk:
                    all_texts.append(chunk.content)
                    self._bm25_doc_ids.append(cid)

        self._bm25.index(all_texts)

    # ---- 内部 ----

    def _get_doc_chunk_ids(self, doc_id: str) -> list[str]:
        """获取文档下所有 chunk ID。"""
        # 通过抽象接口 list_chunk_ids(doc_id) 拿，InMemory / PGVectorStore 都实现。
        # 旧实现 hasattr(self.store, '_doc_chunks') 摸 InMemory 私有属性，PG 接入
        # 后直接返回空 → BM25 索引为空，混合检索静默退化为纯向量（带 cache）。
        return self.store.list_chunk_ids(doc_id)

    def _bm25_scores(self, query: str) -> dict[str, float]:
        """计算 BM25 分数，返回 {chunk_id: normalized_score}。"""
        if self._bm25 is None or self._bm25._N == 0:
            self.rebuild_bm25()
        if self._bm25 is None or self._bm25._N == 0:
            return {}

        raw = self._bm25.search(query, top_k=100)
        if not raw:
            return {}

        scored: dict[str, float] = {}
        for doc_idx, score in raw:
            if doc_idx < len(self._bm25_doc_ids):
                scored[self._bm25_doc_ids[doc_idx]] = score

        return self._normalize_scores(scored)

    def _bm25_only_search(
        self,
        query: str,
        top_k: int,
        min_score: float,
        source_type: Optional[SourceType] = None,
        scope: str = "course",
        node_id: Optional[str] = None,
        page_id: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        Embedding 不可用时的纯 BM25 兜底检索。

        与混合路径构造完全一致的 SearchResult，分数为归一化 BM25 分数（[0,1]），
        因此 min_score 语义不变（0.6 阈值对精确匹配仍可通过）。
        """
        b_scores = self._bm25_scores(query)
        if not b_scores:
            return []

        scored = sorted(b_scores.items(), key=lambda x: x[1], reverse=True)
        results: list[SearchResult] = []
        for cid, score in scored:
            if score < min_score:
                continue
            indexed = self.store.get_chunk(cid)
            if indexed is None:
                continue
            if source_type is not None and indexed.source_type != source_type:
                continue
            if not self._matches_scope(indexed, scope, node_id, page_id):
                continue
            results.append(SearchResult(
                chunk_id=indexed.chunk_id,
                content=indexed.content,
                score=round(score, 4),
                source={
                    "file_name": indexed.source_ref,
                    "page": indexed.page_ref or 0,
                    "type": indexed.source_type.value,
                },
                metadata={
                    "doc_id": indexed.doc_id,
                    "seq_index": indexed.seq_index,
                    **indexed.metadata,
                },
            ))
            if len(results) >= top_k:
                break
        return results

    @staticmethod
    def _matches_scope(indexed, scope: str, node_id: Optional[str], page_id: Optional[str]) -> bool:
        normalized_scope = (scope or "course").strip().lower()
        if normalized_scope == "course":
            return True
        metadata = indexed.metadata or {}
        if normalized_scope == "node":
            candidate = metadata.get("node_id") or metadata.get("node_ref")
            return bool(node_id) and str(candidate or "") == str(node_id)
        if normalized_scope == "page":
            candidate = metadata.get("page_id") or metadata.get("page_ref") or indexed.page_ref
            return bool(page_id) and str(candidate or "") == str(page_id)
        return False

    @staticmethod
    def _normalize_scores(scored: dict[str, float]) -> dict[str, float]:
        """将分数归一化到 [0, 1]。"""
        if not scored:
            return {}
        max_s = max(scored.values())
        if max_s <= 0:
            return {k: 0.0 for k in scored}
        return {k: v / max_s for k, v in scored.items()}
