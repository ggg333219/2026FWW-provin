"""
证据合成器 (evidence.py)

将混合检索 + 重排序的结果融合为结构化 EvidencePacket。

流程（来自 KB-knowledge-base.md §7）：
    query → hybrid_retrieve(k=20) → rerank(k=5)
         → synthesize(retrieved, query, intent_context) → evidence_packet

EvidencePacket 结构：
    {
      "relevant_chunks": [top-5 Chunks],
      "synthesized_context": "LLM 生成的上下文摘要...",
      "citations": [{"chunk_id", "text_snippet", "source_ref"}]
    }

使用方式：
    from ai_engine.rag.evidence import EvidenceSynthesizer

    synth = EvidenceSynthesizer(llm_client=client)
    packet = synth.synthesize(search_results, query="...", context={...})
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ai_engine.core.llm import LLMClient
from ai_engine.core.schema import (
    Chunk,
    Citation,
    EvidencePacket,
    EvidenceResponse,
    SearchResult,
    SourceType,
)

# ---- LLM 提示词 ----

_SYNTHESIS_SYSTEM = """你是一个教学知识库的证据合成助手。

你的任务：根据检索到的多段参考材料，为课件生成系统合成一份结构化证据包。

要求：
1. **synthesized_context**：将多段材料浓缩为一整段连贯的上下文摘要（200-500字），包含关键概念、定义、案例和知识点之间的关联。
   如果材料涉及同一主题的不同方面，尝试将它们串联起来。
2. **citations**：为每个被引用的材料片段生成引用标注，包含原文片段和来源。

输出严格 JSON：
{
  "synthesized_context": "...",
  "citations": [
    {"chunk_id": "...", "text_snippet": "原文关键句（≤100字）", "source_ref": "..."}
  ]
}"""


# =============================================================================
# EvidenceSynthesizer
# =============================================================================

class EvidenceSynthesizer:
    """
    证据合成器：检索结果 + LLM → EvidencePacket。

    输入：SearchResult 列表（来自 HybridRetriever + ReRanker）
    输出：EvidencePacket（传递给 S3 生成管道）

    使用示例：
        synth = EvidenceSynthesizer(llm_client=LLMClient())
        packet = synth.synthesize(
            search_results=results,
            query="排序算法的时间复杂度对比",
            context={"topic": "排序算法", "duration_minutes": 45},
        )
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        max_chunk_chars: int = 3000,
    ):
        """
        Args:
            llm_client: LLM 客户端（None 时自动创建）。
            max_chunk_chars: 传入 LLM 的单个 chunk 内容最大字符数。
        """
        self.llm = llm_client or LLMClient(temperature=0.1)
        self.max_chunk_chars = max_chunk_chars

    # ---- 公开 API ----

    def synthesize(
        self,
        search_results: list[SearchResult],
        query: str = "",
        context: Optional[dict[str, Any]] = None,
    ) -> EvidencePacket:
        """
        合成 EvidencePacket。

        Args:
            search_results: 检索 + 重排序后的结果（通常 3-5 条）。
            query: 原始查询文本。
            context: 意图上下文 {"topic": "...", "intent": {...}, "current_nodes": [...]}。

        Returns:
            EvidencePacket 包含合成上下文和引用。
        """
        if not search_results:
            return EvidencePacket(
                relevant_chunks=[],
                synthesized_context="",
                citations=[],
                query=query,
            )

        # 1. 构建 relevant_chunks
        relevant = self._build_relevant_chunks(search_results)

        # 2. LLM 合成（带回退）
        try:
            synthesized, citations = self._llm_synthesize(
                search_results, query, context or {}
            )
        except Exception:
            # LLM 调用异常时回退
            synthesized, citations = "", []

        # 如果 LLM 返回了空结果（mock 模式常见），回退为简单拼接
        if not synthesized and search_results:
            synthesized, citations = self._fallback_synthesize(search_results)

        return EvidencePacket(
            relevant_chunks=relevant,
            synthesized_context=synthesized,
            citations=citations,
            query=query,
        )

    def synthesize_to_response(
        self,
        search_results: list[SearchResult],
        query: str = "",
        context: Optional[dict[str, Any]] = None,
    ) -> EvidenceResponse:
        """合成并包装为 API 响应。"""
        packet = self.synthesize(search_results, query, context)
        return EvidenceResponse(evidence_packet=packet)

    # ---- 内部 ----

    def _build_relevant_chunks(self, results: list[SearchResult]) -> list[Chunk]:
        """从 SearchResult 构建 Chunk 列表。"""
        chunks: list[Chunk] = []
        for r in results:
            source_type_str = r.source.get("type", "text") if r.source else "text"
            try:
                source_type = SourceType(source_type_str)
            except ValueError:
                source_type = SourceType.TEXT

            chunks.append(Chunk(
                chunk_id=r.chunk_id,
                source_type=source_type,
                source_ref=r.source.get("file_name", ""),
                content=r.content,
                page_ref=r.source.get("page"),
                metadata=dict(r.metadata),
            ))
        return chunks

    def _llm_synthesize(
        self,
        results: list[SearchResult],
        query: str,
        context: dict[str, Any],
    ) -> tuple[str, list[Citation]]:
        """LLM 合成上下文和引用。"""
        # 构建用户提示
        user_parts = [f"## 用户查询\n{query or '(未提供)'}"]

        if context:
            ctx_str = json.dumps(context, ensure_ascii=False, indent=2)
            user_parts.append(f"## 教学意图上下文\n```json\n{ctx_str}\n```")

        materials_parts: list[str] = []
        for i, r in enumerate(results, 1):
            content = r.content[:self.max_chunk_chars]
            materials_parts.append(
                f"### 材料 {i}\n"
                f"- 来源: {r.source.get('file_name', '')} "
                f"(第{r.source.get('page', '?')}页)\n"
                f"- 内容:\n{content}\n"
            )
        user_parts.append("## 检索到的参考材料\n" + "\n---\n".join(materials_parts))

        user_prompt = "\n".join(user_parts)

        result = self.llm.chat_json(
            system=_SYNTHESIS_SYSTEM,
            user=user_prompt,
            temperature=0.1,
        )

        synthesized = result.get("synthesized_context", "")
        raw_citations = result.get("citations", [])

        citations = [
            Citation(
                chunk_id=c.get("chunk_id", ""),
                text_snippet=c.get("text_snippet", ""),
                source_ref=c.get("source_ref", ""),
            )
            for c in raw_citations
            if isinstance(c, dict)
        ]

        return synthesized, citations

    def _fallback_synthesize(
        self,
        results: list[SearchResult],
    ) -> tuple[str, list[Citation]]:
        """LLM 不可用时的回退合成：简单拼接。"""
        parts: list[str] = []
        citations: list[Citation] = []

        for r in results:
            parts.append(r.content[:500])
            citations.append(Citation(
                chunk_id=r.chunk_id,
                text_snippet=r.content[:100],
                source_ref=r.source.get("file_name", ""),
            ))

        synthesized = "\n\n---\n\n".join(parts)
        return synthesized, citations
