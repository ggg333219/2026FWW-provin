"""
文档分块器 (chunker.py)

将原始文本按文档类型采用不同策略切分为适合嵌入的 Chunk。

分块策略（来自 KB-knowledge-base.md §5）：
  - PDF (教材):   按段落 + 标题层级，512 tokens / 64 overlap
  - PPTX (课件):   按幻灯片独立分块，0 overlap
  - DOCX (教案):   按章节 (§) 切分，512 tokens / 64 overlap
  - IMAGE (OCR):   图片块按版面区域，无 overlap
  - VIDEO (ASR):   按时间窗口，30s 段落 / 5s overlap

chunk_id 决定论：
  chunk_id 必须是稳定的 (source_ref, seq_index) 函数，使得同一份语料重复灌库
  时落到同一 chunk_id 上，配合 store 层的 ON CONFLICT DO UPDATE 语义保证
  向量库可幂等重建（启动引导等固定语料场景），不会产生重复切片。
  ID 字符限定 [A-Za-z0-9._-] + `::s{seq:04d}`，最长 64 字符以适配 PG VARCHAR(64)。

使用方式：
    from ai_engine.rag.chunker import DocumentChunker, ChunkingStrategy

    chunker = DocumentChunker(strategy=ChunkingStrategy.PARAGRAPH)
    chunks = chunker.chunk(text="...", source_ref="doc_001", source_type=SourceType.PDF)
"""

from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Optional

from ai_engine.core.schema import Chunk, SourceType


# ---- 分块策略枚举 ----

class ChunkingStrategy(str, Enum):
    """KB 级分块策略。"""
    PARAGRAPH = "paragraph"       # 按段落切分（PDF/DOCX 默认）
    SLIDE = "slide"               # 按幻灯片切分（PPTX 专用）
    SECTION = "section"           # 按章节标题切分
    WINDOW = "window"             # 固定窗口 + overlap（视频 ASR / 通用回退）
    SENTENCE = "sentence"         # 按句子切分（细粒度）


# ---- 各文档类型 → 策略映射 ----

_SOURCE_TYPE_STRATEGY: dict[SourceType, ChunkingStrategy] = {
    SourceType.PDF: ChunkingStrategy.PARAGRAPH,
    SourceType.PPTX: ChunkingStrategy.SLIDE,
    SourceType.DOCX: ChunkingStrategy.SECTION,
    SourceType.IMAGE: ChunkingStrategy.SENTENCE,
    SourceType.VIDEO: ChunkingStrategy.WINDOW,
    SourceType.AUDIO: ChunkingStrategy.WINDOW,
    SourceType.TEXT: ChunkingStrategy.PARAGRAPH,
}

# ---- 各策略默认参数 ----

_STRATEGY_PARAMS: dict[ChunkingStrategy, dict] = {
    ChunkingStrategy.PARAGRAPH: {"chunk_size": 512, "overlap": 64},
    ChunkingStrategy.SLIDE: {"chunk_size": 0, "overlap": 0},       # 0 = 不限制
    ChunkingStrategy.SECTION: {"chunk_size": 0, "overlap": 0},       # 每章节独立
    ChunkingStrategy.WINDOW: {"chunk_size": 256, "overlap": 32},
    ChunkingStrategy.SENTENCE: {"chunk_size": 256, "overlap": 0},
}


# ---- 简易中英文分词 ----

_WORD_SPLIT_RE = re.compile(
    r"[一-鿿]|"          # 中文字符（每个字 = 1 token 近似）
    r"[a-zA-Z0-9]+|"             # 英文单词 / 数字
    r"[^\s一-鿿]",       # 标点等
)


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数。中文按 1 字 ≈ 1 token，英文按 1 词 ≈ 1.3 token。"""
    if not text:
        return 0
    tokens = _WORD_SPLIT_RE.findall(text)
    # 简单启发式：英文字母串 >1 个字符算 1.3 token
    count = 0
    for t in tokens:
        if re.fullmatch(r"[a-zA-Z]+", t):
            count += max(1, round(len(t) / 3.0 * 1.3))
        else:
            count += 1
    return count


def _split_paragraphs(text: str) -> list[str]:
    """按双换行（段落边界）拆分。"""
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_sentences(text: str) -> list[str]:
    """按中英文句子分隔符拆分。"""
    pattern = re.compile(
        r"(?<=[。！？\.\!\?\n])\s*"
    )
    parts = pattern.split(text)
    return [p.strip() for p in parts if p.strip()]


def _split_sections(text: str) -> list[str]:
    """按 Markdown 标题（# / ## / ###）或中文序号拆分。"""
    # 先尝试按 # 标题拆分（使用 flags=re.MULTILINE）
    heading_pattern = re.compile(r"(?=^#{1,6}\s)", flags=re.MULTILINE)
    sections = heading_pattern.split(text)
    if len(sections) <= 1:
        # 回退：按中文序号（一、二、/ 1. / 第X章）拆分
        alt_pattern = re.compile(
            r"(?:^|\n)\s*(?:[一二三四五六七八九十]+[、．.]|"
            r"\d+[\.\、]|"
            r"第[一二三四五六七八九十\d]+[章节篇])",
            flags=re.MULTILINE,
        )
        # 用 capture group 保留分隔符
        sections = alt_pattern.split(text)
    return [s.strip() for s in sections if s.strip()]


def _split_slides(text: str) -> list[str]:
    """按幻灯片分隔符拆分（--- 或 slide 标记）。"""
    parts = re.split(r"\n---+\n|\[\[slide\]\]|\*\*\*", text, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]


# ---- chunk_id 决定论工具 ----

_CHUNK_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
"""chunk_id 允许的字符集。"""

_CHUNK_ID_MAX_LEN = 64
"""适配 PostgreSQL VARCHAR(64)。"""


def _sanitize_source_ref(source_ref: str, max_keep: int = 48) -> str:
    """清洗 source_ref，使其仅含 [A-Za-z0-9._-] 并截断到 max_keep 字符。

    被清洗或截断的 source_ref 加 md5 前缀，避免 Unicode/特殊字符归一化碰撞。
    """
    if not source_ref:
        return "anon"
    safe = _CHUNK_ID_SAFE_RE.sub("_", source_ref)
    if safe == source_ref and len(safe) <= max_keep:
        return safe
    digest = hashlib.md5(source_ref.encode("utf-8")).hexdigest()[:12]
    return f"h{digest}_{safe[:max_keep - 13]}"


def _make_deterministic_chunk_id(source_ref: str, seq_index: int) -> str:
    """生成稳定的 chunk_id：`{safe_source_ref}::s{seq_index:04d}`。

    幂等性保证：同一 (source_ref, seq_index) 永远得到同一 chunk_id，
    从而支持上游 store 的 ON CONFLICT DO UPDATE 语义。
    """
    safe = _sanitize_source_ref(source_ref)
    return f"{safe}::s{seq_index:04d}"


def _sliding_window(
    segments: list[str],
    chunk_size: int,
    overlap: int,
    prefix: str = "",
) -> list[str]:
    """
    将段落列表合并为固定 token 窗口 + overlap。
    当 chunk_size=0 时每段独立返回（不合并）。
    当单个段落超过 chunk_size 时，先按句子拆分为子段再滑窗。
    """
    if chunk_size <= 0:
        return segments

    # 拆分超长段落
    split_segments: list[str] = []
    for seg in segments:
        if _estimate_tokens(seg) > chunk_size:
            # 按句子拆分子段
            subs = _split_sentences(seg)
            split_segments.extend(subs)
        else:
            split_segments.append(seg)

    chunks: list[str] = []
    i = 0
    while i < len(split_segments):
        window: list[str] = []
        token_count = 0
        j = i
        while j < len(split_segments):
            seg_tokens = _estimate_tokens(split_segments[j])
            if token_count + seg_tokens > chunk_size and window:
                break
            window.append(split_segments[j])
            token_count += seg_tokens
            j += 1
        chunk_text = (prefix + "\n" + "\n\n".join(window)).strip() if prefix else "\n\n".join(window)
        if chunk_text:
            chunks.append(chunk_text)

        # 计算 overlap：回退到使得剩余 tokens ≈ overlap
        if overlap > 0 and j < len(split_segments):
            back_tokens = 0
            next_i = j
            for k in range(len(window) - 1, -1, -1):
                back_tokens += _estimate_tokens(window[k])
                next_i -= 1
                if back_tokens >= overlap:
                    break
            i = max(i + 1, next_i)
        else:
            i = j

    return chunks


# =============================================================================
# DocumentChunker
# =============================================================================

class DocumentChunker:
    """
    文档分块器：根据来源类型选择分块策略，将文本转为 Chunk 列表。

    支持两种输入模式：
      1. 直接传入原始文本 → chunk_text()
      2. 传入已有的 Chunk 列表（S2 产出）→ rechunk()  做二次细粒度切分

    使用示例：
        chunker = DocumentChunker()
        chunks = chunker.chunk_text(
            text="第一章...", source_ref="doc_001", source_type=SourceType.PDF
        )
    """

    def __init__(
        self,
        strategy: Optional[ChunkingStrategy] = None,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None,
    ):
        """
        Args:
            strategy: 分块策略（None 则根据 source_type 自动选择）。
            chunk_size: 覆盖默认块大小（token 数）。
            overlap: 覆盖默认重叠量（token 数）。
        """
        self._strategy = strategy
        self._chunk_size_override = chunk_size
        self._overlap_override = overlap

    # ---- 公开 API ----

    def chunk_text(
        self,
        text: str,
        source_ref: str,
        source_type: SourceType = SourceType.TEXT,
        metadata: Optional[dict] = None,
    ) -> list[Chunk]:
        """
        将原始文本切分为 Chunk 列表。

        Args:
            text: 原始文本内容。
            source_ref: 来源标识（如 doc_id + page）。
            source_type: 文档类型。
            metadata: 附加元数据（传递到每个 Chunk）。

        Returns:
            list[Chunk]: 切分后的 Chunk 列表（含 chunk_id、seq_index）。
        """
        strategy = self._resolve_strategy(source_type)
        params = self._resolve_params(strategy)
        segments = self._segment(text, strategy)
        windows = _sliding_window(
            segments,
            chunk_size=params["chunk_size"],
            overlap=params["overlap"],
        )
        return self._build_chunks(windows, source_ref, source_type, metadata or {})

    def rechunk(
        self,
        chunks: list[Chunk],
        strategy: Optional[ChunkingStrategy] = None,
    ) -> list[Chunk]:
        """
        对已有 Chunk 列表做二次细粒度切分。

        适用场景：S2 产出粗粒度 Chunk → KB 再切为更适合检索的粒度。

        Args:
            chunks: S2 产出的 Chunk 列表。
            strategy: 覆盖自动策略。

        Returns:
            list[Chunk]: 细粒度 Chunk 列表。
        """
        result: list[Chunk] = []
        for ch in chunks:
            sub = self.chunk_text(
                text=ch.content,
                source_ref=ch.source_ref,
                source_type=ch.source_type,
                metadata=dict(ch.metadata),
            )
            result.extend(sub)
        return result

    # ---- 内部方法 ----

    def _resolve_strategy(self, source_type: SourceType) -> ChunkingStrategy:
        if self._strategy is not None:
            return self._strategy
        return _SOURCE_TYPE_STRATEGY.get(source_type, ChunkingStrategy.PARAGRAPH)

    def _resolve_params(self, strategy: ChunkingStrategy) -> dict:
        defaults = dict(_STRATEGY_PARAMS.get(strategy, {"chunk_size": 512, "overlap": 64}))
        if self._chunk_size_override is not None:
            defaults["chunk_size"] = self._chunk_size_override
        if self._overlap_override is not None:
            defaults["overlap"] = self._overlap_override
        return defaults

    def _segment(self, text: str, strategy: ChunkingStrategy) -> list[str]:
        """按策略将文本拆为初始段落列表。"""
        if not text or not text.strip():
            return []

        if strategy == ChunkingStrategy.PARAGRAPH:
            return _split_paragraphs(text)
        elif strategy == ChunkingStrategy.SENTENCE:
            return _split_sentences(text)
        elif strategy == ChunkingStrategy.SECTION:
            return _split_sections(text)
        elif strategy == ChunkingStrategy.SLIDE:
            return _split_slides(text)
        elif strategy == ChunkingStrategy.WINDOW:
            # WINDOW 策略：先按段落拆，再滑窗
            paras = _split_paragraphs(text)
            if not paras:
                return [text.strip()]
            return paras
        else:
            return [text.strip()]

    def _build_chunks(
        self,
        windows: list[str],
        source_ref: str,
        source_type: SourceType,
        metadata: dict,
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
        for idx, content in enumerate(windows):
            chunks.append(Chunk(
                chunk_id=_make_deterministic_chunk_id(source_ref, idx),
                source_type=source_type,
                source_ref=source_ref,
                content=content,
                seq_index=idx,
                metadata=dict(metadata),
            ))
        return chunks
