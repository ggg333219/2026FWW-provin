"""
ai_engine/rag — KB 知识库 RAG 管道

P3 负责的知识库检索增强生成模块。
从 S2 产出的 Chunk 中构建向量索引，提供混合检索 + 证据融合能力。

模块：
  - chunker:   文档分块（按页/段落/语义边界）
  - embed:     嵌入向量化（OpenAI 兼容 API）
  - store:     向量存储（pgvector / 内存回退）
  - retrieve:  混合检索（向量 0.7 + BM25 0.3）
  - rerank:    Cross-encoder 重排序
  - evidence:  检索结果 + LLM → EvidencePacket
  - router:    FastAPI 路由（/rag/search, /rag/evidence, /knowledge/upload）
"""

from .chunker import DocumentChunker, ChunkingStrategy
from .embed import EmbeddingService
from .store import InMemoryVectorStore, VectorStore
from .retrieve import HybridRetriever, BM25Scorer
from .rerank import ReRanker
from .evidence import EvidenceSynthesizer
from .router import router

__all__ = [
    "DocumentChunker",
    "ChunkingStrategy",
    "EmbeddingService",
    "InMemoryVectorStore",
    "VectorStore",
    "HybridRetriever",
    "BM25Scorer",
    "ReRanker",
    "EvidenceSynthesizer",
    "router",
]
