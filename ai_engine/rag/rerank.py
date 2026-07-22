"""
重排序器 (rerank.py)

对混合检索的 top-K 结果进行 Cross-encoder 精排。

根据设计文档 KB-knowledge-base.md §6：
  - 混合检索取 top-20 → Cross-encoder 重排序 → 取 top-5
  - Cross-encoder 为可选模块：无模型时直接透传原始顺序

使用方式：
    from ai_engine.rag.rerank import ReRanker

    reranker = ReRanker()
    reranked = reranker.rerank(query="...", candidates=candidates, top_k=5)
"""

from __future__ import annotations

from typing import Optional

from ai_engine.core.schema import SearchResult


class ReRanker:
    """
    Cross-encoder 重排序器。

    当前实现为占位透传（pass-through），保留原始检索顺序。
    后续可接入 sentence-transformers 的 CrossEncoder 模型实现真正的重排序。

    TODO: 接入 cross-encoder 模型
        from sentence_transformers import CrossEncoder
        model = CrossEncoder("BAAI/bge-reranker-v2-m3")
        scores = model.predict([(query, doc.content) for doc in candidates])
    """

    def __init__(self, model_name: Optional[str] = None):
        """
        Args:
            model_name: Cross-encoder 模型名。
                        None 时使用透传模式。
                        例如 "BAAI/bge-reranker-v2-m3"。
        """
        self.model_name = model_name
        self._model = None

    def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        top_k: int = 5,
    ) -> list[SearchResult]:
        """
        对候选结果重排序。

        Args:
            query: 原始查询。
            candidates: 候选结果列表（通常 20 条）。
            top_k: 返回前 K 条。

        Returns:
            list[SearchResult]: 重排序后的 top-K 结果。
        """
        if not candidates:
            return []

        if self.model_name is None:
            # 透传模式：保留原始顺序
            return candidates[:top_k]

        # 尝试加载 cross-encoder
        if self._model is None:
            try:
                self._model = self._load_model()
            except Exception:
                # 加载失败，回退透传
                return candidates[:top_k]

        # 真正的 cross-encoder 重排序
        try:
            return self._cross_encoder_rerank(query, candidates, top_k)
        except Exception:
            return candidates[:top_k]

    def _load_model(self):
        """加载 cross-encoder 模型。"""
        from sentence_transformers import CrossEncoder
        return CrossEncoder(
            self.model_name or "BAAI/bge-reranker-v2-m3",
            max_length=512,
        )

    def _cross_encoder_rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        """Cross-encoder 精排。"""
        pairs = [(query, c.content) for c in candidates]
        scores = self._model.predict(pairs, show_progress_bar=False)

        # 按分数排序
        indexed = list(enumerate(scores))
        indexed.sort(key=lambda x: x[1], reverse=True)

        reranked: list[SearchResult] = []
        for i, score in indexed[:top_k]:
            c = candidates[i]
            c.score = round(float(score), 4)  # 更新分数
            reranked.append(c)

        return reranked
