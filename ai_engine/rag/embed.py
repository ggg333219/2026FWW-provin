"""
嵌入向量化服务 (embed.py)

调用 LLMClient.embed() 将 Chunk 文本转为向量。

LLM 调用统一走 core/llm.py → LLMClient.embed()，
不直接 import openai，遵循开发规范 §2 原则 2。

支持：
  - OpenAI / DashScope 等兼容 API
  - 自动批量处理（减少 API 调用次数）
  - Mock 模式回退（零向量）
  - 多维度支持（默认 1024 维）

使用方式：
    from ai_engine.rag.embed import EmbeddingService

    svc = EmbeddingService(model="text-embedding-v3")
    chunks = svc.embed_chunks(chunks)
    # 每个 chunk.embedding 现在已填充
"""

from __future__ import annotations

import os
from typing import Optional

from ai_engine.core import LLMClient
from ai_engine.core.config import settings
from ai_engine.core.schema import Chunk

# ---- 默认值 ----

_DEFAULT_EMBEDDING_MODEL = "text-embedding-v3"
_DEFAULT_EMBEDDING_DIM = 1024
_DEFAULT_BATCH_SIZE = 20


def _env_embedding_model() -> str:
    return (os.getenv("AI_EMBEDDING_MODEL") or _DEFAULT_EMBEDDING_MODEL).strip()


def _env_embedding_dim() -> int:
    try:
        return int(os.getenv("AI_EMBEDDING_DIM", str(_DEFAULT_EMBEDDING_DIM)))
    except (TypeError, ValueError):
        return _DEFAULT_EMBEDDING_DIM


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """纯 Python 余弦相似度。"""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# =============================================================================
# EmbeddingService
# =============================================================================

class EmbeddingService:
    """
    嵌入向量化服务。

    委托 core.LLMClient.embed() 完成向量化调用，遵循
    "LLM 调用统一走 core/" 的规范。

    使用示例：
        svc = EmbeddingService()
        chunks = svc.embed_chunks(chunks)
        vec = svc.embed_text("什么是排序算法？")
    """

    def __init__(
        self,
        model: Optional[str] = None,
        dim: Optional[int] = None,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ):
        """
        Args:
            model: 嵌入模型名（默认从 AI_EMBEDDING_MODEL 环境变量读取）。
            dim: 输出向量维度（默认 1024）。
            batch_size: API 每批最大文本数。
        """
        self.model = model or _env_embedding_model()
        self.dim = dim or _env_embedding_dim()
        self.batch_size = max(1, min(batch_size, 100))
        # 统一使用 LLMClient 进行 embedding 调用
        self._client = LLMClient(model=self.model)

    # ---- 公开 API ----

    def embed_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """
        批量为 Chunk 列表填充 embedding 字段。

        Args:
            chunks: Chunk 列表（content 非空）。

        Returns:
            同一列表（原地修改），每个 Chunk.embedding 已填充。
        """
        texts = [ch.content for ch in chunks]
        vectors = self.embed_batch(texts)
        for ch, vec in zip(chunks, vectors):
            ch.embedding = vec
        return chunks

    def embed_text(self, text: str) -> list[float]:
        """对单段文本做向量化。"""
        results = self.embed_batch([text])
        return results[0] if results else [0.0] * self.dim

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        批量向量化，自动分批 + 回退。

        Args:
            texts: 文本列表。

        Returns:
            等长的 list[list[float]]。
        """
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            vectors = self._client.embed(batch, model=self.model, dim=self.dim)
            all_vectors.extend(vectors)

        return all_vectors
