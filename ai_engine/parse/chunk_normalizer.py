"""
分块标准化器 (chunk_normalizer.py)

将各解析器产出的原始块（raw chunks）统一标准化为 Chunk 模型。

对接下游：
  - KB 知识库 RAG（Chunk → 向量化 → 索引）
  - Agent Orchestrator（解析上下文）

使用方式：
    from ai_engine.parse.chunk_normalizer import ChunkNormalizer

    normalizer = ChunkNormalizer()
    chunks = normalizer.normalize(raw_chunks=[...], source_ref="doc_uuid", source_type=SourceType.PDF)
"""

import uuid
from typing import Any, Optional

from ai_engine.core.schema import Chunk, SourceType


class ChunkNormalizer:
    """
    将各解析器的原始输出统一标准化为 Chunk 模型。

    处理规则：
      - 按 type 赋予不同的 metadata（page_ref、timestamp_range 等）
      - 每个原始块生成一个 Chunk
      - 自动分配 chunk_id 和 seq_index
      - 大文本自动截断（由 settings.MAX_CONTENT_CHARS 控制）
    """

    def __init__(self, max_content_chars: int = 0):
        """max_content_chars=0 表示使用 settings 中的值。"""
        self.max_content_chars = max_content_chars

    def normalize(
        self,
        raw_chunks: list[dict[str, Any]],
        source_ref: str,
        source_type: SourceType = SourceType.TEXT,
    ) -> list[Chunk]:
        """
        标准化原始块列表为 Chunk 列表。

        Args:
            raw_chunks: 解析器输出的原始块列表。
            source_ref: 来源标识（如 "doc_uuid"、"video_uuid"）。
            source_type: 来源类型。

        Returns:
            list[Chunk]: 标准化后的 Chunk 列表。
        """
        from ai_engine.core.config import settings

        max_chars = self.max_content_chars or settings.MAX_CONTENT_CHARS
        chunks: list[Chunk] = []

        for idx, raw in enumerate(raw_chunks):
            content = raw.get("content", "")
            if len(content) > max_chars:
                content = content[:max_chars] + "\n...(截断)"

            raw_type = raw.get("type", "text")
            page = raw.get("page")
            metadata = raw.get("metadata", {})
            seq = raw.get("seq_index", idx)

            chunk = Chunk(
                chunk_id=f"chunk_{uuid.uuid4().hex[:12]}",
                source_type=source_type,
                source_ref=source_ref,
                content=content,
                page_ref=page if isinstance(page, int) else None,
                seq_index=seq,
                metadata=metadata,
            )
            chunks.append(chunk)

        return chunks
