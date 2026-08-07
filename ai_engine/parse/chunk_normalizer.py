"""
Chunk normalizer.

Converts raw parser output into Chunk models and lightly formats content
for preview/search per source type.
"""

import re
import uuid
from typing import Any

from ai_engine.core.schema import Chunk, SourceType


class ChunkNormalizer:
    """Normalize raw parser output into Chunk objects."""

    def __init__(self, max_content_chars: int = 0):
        self.max_content_chars = max_content_chars

    def normalize(
        self,
        raw_chunks: list[dict[str, Any]],
        source_ref: str,
        source_type: SourceType = SourceType.TEXT,
    ) -> list[Chunk]:
        from ai_engine.core.config import settings

        max_chars = self.max_content_chars or settings.MAX_CONTENT_CHARS
        chunks: list[Chunk] = []

        for idx, raw in enumerate(raw_chunks):
            content = self._format_content(raw, source_type)
            if len(content) > max_chars:
                content = content[:max_chars] + "\n...(截断)"

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

    @staticmethod
    def _format_content(raw: dict[str, Any], source_type: SourceType) -> str:
        """Format chunk content for its source type."""
        content = str(raw.get("content", "") or "")
        page = raw.get("page")
        metadata = raw.get("metadata", {}) if isinstance(raw.get("metadata", {}), dict) else {}
        raw_type = str(raw.get("type", "") or "").lower()

        content = re.sub(r"\r\n?", "\n", content).strip()
        if not content:
            return ""

        if source_type == SourceType.PDF:
            if page and not content.startswith("#"):
                return f"# 第{page}页\n\n{content}"
            return content

        if source_type == SourceType.PPTX:
            slide_no = page or metadata.get("slide") or metadata.get("page_number")
            if slide_no and not content.startswith("#"):
                return f"# 幻灯片 {slide_no}\n\n{content}"
            return content

        if source_type == SourceType.DOCX:
            section = page or metadata.get("section") or metadata.get("page_number")
            if section and not content.startswith("#"):
                return f"# 文档段落 {section}\n\n{content}"
            return content

        if source_type == SourceType.IMAGE:
            if raw_type == "ocr":
                return f"【OCR识别】\n{content}"
            if raw_type == "caption":
                return f"【图像描述】\n{content}"
            return f"【图片内容】\n{content}"

        if source_type == SourceType.VIDEO:
            time_range = metadata.get("timestamp_range")
            if isinstance(time_range, list) and len(time_range) >= 2:
                return f"【视频片段 {time_range[0]}s-{time_range[1]}s】\n{content}"
            return f"【视频内容】\n{content}"

        if source_type == SourceType.AUDIO:
            time_range = metadata.get("timestamp_range")
            if isinstance(time_range, list) and len(time_range) >= 2:
                return f"【音频片段 {time_range[0]}s-{time_range[1]}s】\n{content}"
            return f"【音频内容】\n{content}"

        return content
