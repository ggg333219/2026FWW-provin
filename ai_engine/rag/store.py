"""
向量存储 (store.py)

提供向量数据库的抽象接口和实现。

实现：
  - VectorStore (ABC):          抽象接口
  - InMemoryVectorStore:       开发/测试用内存实现（零依赖）
  - PGVectorStore (TODO):      生产用 pgvector 实现

使用方式：
    from ai_engine.rag.store import InMemoryVectorStore

    store = InMemoryVectorStore()
    store.insert_batch(chunks)           # 批量写入
    results = store.search(query_vec, top_k=5)  # 向量检索
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ai_engine.core.schema import Chunk, SourceType, ParseStatus
from ai_engine.rag.embed import cosine_similarity


# =============================================================================
# 内部数据结构
# =============================================================================

@dataclass
class IndexedChunk:
    """存储在向量库中的单条记录。"""
    chunk_id: str
    source_ref: str
    source_type: SourceType
    content: str
    embedding: list[float]
    page_ref: Optional[int] = None
    seq_index: int = 0
    metadata: dict = field(default_factory=dict)
    doc_id: str = ""  # 所属知识库文档 ID

    def to_chunk(self) -> Chunk:
        """还原为 Chunk schema。"""
        return Chunk(
            chunk_id=self.chunk_id,
            source_type=self.source_type,
            source_ref=self.source_ref,
            content=self.content,
            page_ref=self.page_ref,
            seq_index=self.seq_index,
            metadata=dict(self.metadata),
            embedding=list(self.embedding),
        )

    @classmethod
    def from_chunk(cls, ch: Chunk, doc_id: str = "") -> "IndexedChunk":
        return cls(
            chunk_id=ch.chunk_id,
            source_ref=ch.source_ref,
            source_type=ch.source_type,
            content=ch.content,
            embedding=list(ch.embedding) if ch.embedding else [],
            page_ref=ch.page_ref,
            seq_index=ch.seq_index,
            metadata=dict(ch.metadata),
            doc_id=doc_id,
        )


@dataclass
class SearchHit:
    """单条检索命中结果。"""
    chunk: IndexedChunk
    score: float


@dataclass
class DocumentRecord:
    """知识库文档记录。"""
    doc_id: str
    file_name: str
    source_type: SourceType
    chunk_count: int = 0
    status: ParseStatus = ParseStatus.UPLOADED


# =============================================================================
# 抽象接口
# =============================================================================

class VectorStore(ABC):
    """向量存储抽象基类。"""

    @abstractmethod
    def insert_batch(self, chunks: list[Chunk], doc_id: str = "") -> list[str]:
        """
        批量写入 Chunk（含 embedding）。

        Returns:
            写入的 chunk_id 列表。
        """
        ...

    @abstractmethod
    def search(
        self,
        query_vec: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
        source_type: Optional[SourceType] = None,
    ) -> list[SearchHit]:
        """向量相似度检索。"""
        ...

    @abstractmethod
    def delete_by_doc(self, doc_id: str) -> int:
        """按文档 ID 删除所有关联分块，返回删除数。"""
        ...

    @abstractmethod
    def delete_by_chunk_id(self, chunk_id: str) -> bool:
        """删除单个分块。"""
        ...

    @abstractmethod
    def get_chunk(self, chunk_id: str) -> Optional[IndexedChunk]:
        """按 ID 获取单条记录。"""
        ...

    @abstractmethod
    def count(self) -> int:
        """总 chunk 数。"""
        ...

    @abstractmethod
    def list_documents(self) -> list[DocumentRecord]:
        """列出所有文档。"""
        ...


# =============================================================================
# 内存实现
# =============================================================================

class InMemoryVectorStore(VectorStore):
    """
    内存向量存储，开发/测试用。

    特点：
      - 零外部依赖，无需 pgvector
      - 全量遍历计算余弦相似度（数据量大时性能不如 pgvector HNSW）
      - 进程重启后数据丢失
    """

    def __init__(self):
        self._chunks: dict[str, IndexedChunk] = {}     # chunk_id → IndexedChunk
        self._doc_chunks: dict[str, list[str]] = {}     # doc_id → [chunk_id, ...]
        self._documents: dict[str, DocumentRecord] = {} # doc_id → DocumentRecord

    # ---- VectorStore 实现 ----

    def insert_batch(self, chunks: list[Chunk], doc_id: str = "") -> list[str]:
        if not doc_id:
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"

        chunk_ids: list[str] = []
        doc_chunk_ids: list[str] = []

        for ch in chunks:
            indexed = IndexedChunk.from_chunk(ch, doc_id=doc_id)
            self._chunks[indexed.chunk_id] = indexed
            chunk_ids.append(indexed.chunk_id)
            doc_chunk_ids.append(indexed.chunk_id)

        self._doc_chunks[doc_id] = doc_chunk_ids

        # 创建/更新文档记录
        sample = chunks[0] if chunks else None
        self._documents[doc_id] = DocumentRecord(
            doc_id=doc_id,
            file_name=sample.source_ref if sample else "",
            source_type=sample.source_type if sample else SourceType.TEXT,
            chunk_count=len(chunks),
            status=ParseStatus.INDEXED,
        )
        return chunk_ids

    def search(
        self,
        query_vec: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
        source_type: Optional[SourceType] = None,
    ) -> list[SearchHit]:
        if not query_vec:
            return []

        hits: list[SearchHit] = []
        for indexed in self._chunks.values():
            if source_type is not None and indexed.source_type != source_type:
                continue
            if not indexed.embedding:
                continue
            score = cosine_similarity(query_vec, indexed.embedding)
            if score >= min_score:
                hits.append(SearchHit(chunk=indexed, score=score))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def delete_by_doc(self, doc_id: str) -> int:
        chunk_ids = self._doc_chunks.pop(doc_id, [])
        for cid in chunk_ids:
            self._chunks.pop(cid, None)
        self._documents.pop(doc_id, None)
        return len(chunk_ids)

    def delete_by_chunk_id(self, chunk_id: str) -> bool:
        if chunk_id in self._chunks:
            indexed = self._chunks.pop(chunk_id)
            doc_chunks = self._doc_chunks.get(indexed.doc_id, [])
            if chunk_id in doc_chunks:
                doc_chunks.remove(chunk_id)
            return True
        return False

    def get_chunk(self, chunk_id: str) -> Optional[IndexedChunk]:
        return self._chunks.get(chunk_id)

    def count(self) -> int:
        return len(self._chunks)

    def list_documents(self) -> list[DocumentRecord]:
        return list(self._documents.values())

    # ---- 额外方法 ----

    def clear(self) -> None:
        """清空所有数据。"""
        self._chunks.clear()
        self._doc_chunks.clear()
        self._documents.clear()
