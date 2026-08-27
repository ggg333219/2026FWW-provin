"""
内容自适应校验模块 (gen/validator.py)

职责：
  - 检测节点内容是否超出单页容量
  - 自适应计算缩放字号（内容过长时自动调小）
  - 超长内容自动分页（拆分为多个子节点）
  - 输出结构化校验报告，供渲染器和导出器消费

使用方式：
    from ai_engine.gen.validator import ContentValidator, ValidationResult

    validator = ContentValidator()
    result = validator.validate(node_dict)
    if result.oversized:
        scaled = validator.compute_scaled_font(node_dict, result)
        paginated = validator.paginate(node_dict, result)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


# =============================================================================
# 常量与阈值
# =============================================================================

MAX_CHARS_PER_SLIDE = 400
FORCE_PAGINATE_CHARS = 800

NODE_TYPE_CHAR_LIMITS: dict[str, int] = {
    "cover": 50,
    "title": 30,
    "section": 40,
    "content": MAX_CHARS_PER_SLIDE,
    "quiz": 200,
    "summary": MAX_CHARS_PER_SLIDE,
    "divider": 20,
    "interactive": 300,
}

DEFAULT_FONT_SIZE = 24
MIN_FONT_SIZE = 12
MAX_FONT_SIZE = 44
CHARS_PER_LINE_ESTIMATE = 40


# =============================================================================
# 校验结果
# =============================================================================

@dataclass
class ValidationResult:
    """节点内容校验结果。"""
    node_id: str
    node_type: str
    total_chars: int
    char_limit: int
    oversized: bool = False
    excess_chars: int = 0
    font_size_hint: Optional[str] = None
    text_alignment: Optional[str] = None
    needs_pagination: bool = False
    page_count: int = 1
    split_mode: Optional[str] = None
    validation_warnings: list[str] = field(default_factory=list)

    @property
    def scale_ratio(self) -> float:
        """内容压缩比（字号需要缩小的比例）。"""
        if not self.oversized or self.excess_chars <= 0:
            return 1.0
        ratio = self.char_limit / max(self.total_chars, 1)
        return max(0.5, min(1.0, ratio))


@dataclass
class PaginatedNode:
    """分页后的子节点。"""
    index: int
    total: int
    title: str
    content: str
    key_points: list[str]
    segments: list[dict]
    node_type: str
    layout_hint: Optional[str] = None
    font_size_hint: Optional[str] = None


# =============================================================================
# 核心校验器
# =============================================================================

class ContentValidator:
    """
    内容自适应校验器。

    校验流程：
      validate() → 检测是否超出容量
      compute_scaled_font() → 计算自适应字号
      paginate() → 超长内容拆分为多个子节点
    """

    def validate(self, node: dict[str, Any]) -> ValidationResult:
        """
        校验节点内容是否超出单页容量。

        判断逻辑：
          1. 统计 content + script + key_points + segments.text 总字符数
          2. 与 node_type 对应 char_limit 比较
          3. oversize = total > char_limit
          4. excess = total - char_limit（>0 时生效）
          5. needs_pagination = total > FORCE_PAGINATE_CHARS
        """
        node_id = str(node.get("node_id") or "")
        node_type = str(node.get("type") or node.get("node_type") or "content")

        # 统计总字符数
        total_chars = self._count_chars(node)

        # 获取该类型的字数上限
        char_limit = NODE_TYPE_CHAR_LIMITS.get(node_type, MAX_CHARS_PER_SLIDE)

        oversized = total_chars > char_limit
        excess_chars = max(0, total_chars - char_limit)
        needs_pagination = total_chars > FORCE_PAGINATE_CHARS

        # 计算字号建议
        font_hint, alignment = self._compute_text_hints(node_type, total_chars, char_limit)

        warnings = []
        if oversized and excess_chars > char_limit * 0.5:
            warnings.append(f"内容超出 {excess_chars} 字符，建议分页或精简")
        if node_type == "summary" and total_chars > MAX_CHARS_PER_SLIDE * 1.5:
            warnings.append("小结内容过长，建议拆分为多个小结节点")

        return ValidationResult(
            node_id=node_id,
            node_type=node_type,
            total_chars=total_chars,
            char_limit=char_limit,
            oversized=oversized,
            excess_chars=excess_chars,
            font_size_hint=font_hint,
            text_alignment=alignment,
            needs_pagination=needs_pagination,
            page_count=self._estimate_page_count(total_chars, char_limit),
            validation_warnings=warnings,
        )

    def compute_scaled_font(self, node: dict[str, Any], result: ValidationResult) -> dict[str, Any]:
        """
        根据校验结果计算自适应字号，返回更新后的节点副本。

        字号策略：
          - 超出 0-20%：hint = "small"，字号降 1 档
          - 超出 20-50%：hint = "small"，字号降 2 档
          - 超出 >50%：返回原节点（需分页，不强缩放）
        """
        if not result.oversized:
            return {**node, "font_size_hint": "medium"}

        # 超出比例
        ratio = result.excess_chars / max(result.char_limit, 1)
        if ratio > 0.5:
            # 超出超过 50%，建议分页而非强制缩放
            return {**node, "font_size_hint": result.font_size_hint}

        # 按超出比例决定缩放级别
        if ratio > 0.2:
            size_hint = "small"
        else:
            size_hint = "small"  # 任何超出都建议 small

        # 对齐方式：内容型节点默认左对齐，标题/封面居中
        alignment = result.text_alignment or ("center" if result.node_type in ("cover", "title") else "left")

        updated = {**node}
        updated["font_size_hint"] = size_hint
        updated["text_alignment"] = alignment

        # 如果节点有 segments，同时更新每个 segment 的提示
        if "segments" in updated and isinstance(updated["segments"], list):
            updated["segments"] = [
                {**seg, "font_size_hint": size_hint}
                if isinstance(seg, dict) else seg
                for seg in updated["segments"]
            ]

        return updated

    def paginate(self, node: dict[str, Any], result: ValidationResult) -> list[PaginatedNode]:
        """
        将超长节点拆分为多个 PaginatedNode。

        拆分策略：
          1. 优先按 segments 拆分（每段本身已有语义边界）
          2. 次选按段落拆分（content/script 中的 \\n\\n）
          3. 最后按字数均分
        """
        if not result.needs_pagination and not result.oversized:
            return [self._make_paginated_node(node, 1, 1)]

        node_type = result.node_type
        title_base = str(node.get("title") or "未命名节点")
        page_count = max(2, result.page_count)

        # 尝试按 segments 拆分
        segments = node.get("segments") or []
        if len(segments) >= 2:
            return self._paginate_by_segments(node, segments, title_base, page_count)

        # 尝试按段落拆分
        content = self._extract_text_content(node)
        paragraphs = re.split(r"\n\s*\n", content)
        if len(paragraphs) >= 2:
            return self._paginate_by_paragraphs(node, paragraphs, title_base, page_count)

        # 按字数均分
        return self._paginate_by_chars(node, content, title_base, page_count)

    # ── 内部工具 ─────────────────────────────────────────────────────────────

    def _count_chars(self, node: dict[str, Any]) -> int:
        """统计节点所有文本内容的总字符数。"""
        total = 0
        for field_name in ("content", "script", "summary"):
            val = node.get(field_name) or ""
            total += len(str(val))

        # key_points
        for kp in (node.get("key_points") or node.get("core_points") or []):
            total += len(str(kp))

        # segments.text
        for seg in (node.get("segments") or []):
            if isinstance(seg, dict):
                total += len(str(seg.get("text", "")))

        # questions
        for q in (node.get("questions") or node.get("interactive_questions") or []):
            total += len(str(q))

        return total

    def _extract_text_content(self, node: dict[str, Any]) -> str:
        """提取节点主要文本内容。"""
        parts = []
        for field_name in ("content", "script"):
            val = node.get(field_name)
            if val:
                parts.append(str(val))
        return "\n".join(parts)

    def _compute_text_hints(self, node_type: str, total: int, limit: int) -> tuple[Optional[str], Optional[str]]:
        """计算字号提示文本对齐方式。"""
        if total <= limit:
            return "medium", None

        ratio = total / max(limit, 1)
        if ratio > 1.5:
            return "small", "left"
        elif ratio > 1.2:
            return "small", "left"
        return "medium", None

    def _estimate_page_count(self, total: int, limit: int) -> int:
        """估算所需页数。"""
        if total <= limit:
            return 1
        return max(2, (total // limit) + 1)

    def _make_paginated_node(self, node: dict[str, Any], index: int, total: int) -> PaginatedNode:
        """从原节点创建单个 PaginatedNode。"""
        return PaginatedNode(
            index=index,
            total=total,
            title=str(node.get("title") or ""),
            content=self._extract_text_content(node),
            key_points=node.get("key_points") or node.get("core_points") or [],
            segments=node.get("segments") or [],
            node_type=str(node.get("type") or node.get("node_type") or "content"),
            layout_hint=node.get("layout_hint"),
            font_size_hint=node.get("font_size_hint"),
        )

    def _paginate_by_segments(self, node: dict, segments: list, title_base: str, page_count: int) -> list[PaginatedNode]:
        """按 segments 语义边界拆分。"""
        import math
        segs_per_page = math.ceil(len(segments) / page_count)
        pages: list[PaginatedNode] = []
        for pg in range(page_count):
            start = pg * segs_per_page
            page_segs = segments[start:start + segs_per_page]
            if not page_segs:
                continue
            texts = [str(s.get("text", "")) if isinstance(s, dict) else str(s) for s in page_segs]
            content = "\n".join(texts)
            title_suffix = f"（{pg + 1}/{page_count}）" if page_count > 1 else ""
            pages.append(PaginatedNode(
                index=pg + 1,
                total=page_count,
                title=f"{title_base}{title_suffix}",
                content=content,
                key_points=[],
                segments=page_segs,
                node_type=str(node.get("type") or node.get("node_type") or "content"),
                layout_hint=node.get("layout_hint"),
                font_size_hint=node.get("font_size_hint"),
            ))
        return pages

    def _paginate_by_paragraphs(self, node: dict, paragraphs: list, title_base: str, page_count: int) -> list[PaginatedNode]:
        """按段落拆分。"""
        import math
        paras_per_page = math.ceil(len(paragraphs) / page_count)
        pages: list[PaginatedNode] = []
        for pg in range(page_count):
            start = pg * paras_per_page
            page_paras = paragraphs[start:start + paras_per_page]
            if not page_paras:
                continue
            content = "\n\n".join(str(p).strip() for p in page_paras if str(p).strip())
            title_suffix = f"（{pg + 1}/{page_count}）" if page_count > 1 else ""
            pages.append(PaginatedNode(
                index=pg + 1,
                total=page_count,
                title=f"{title_base}{title_suffix}",
                content=content,
                key_points=[],
                segments=[],
                node_type=str(node.get("type") or node.get("node_type") or "content"),
                layout_hint=node.get("layout_hint"),
                font_size_hint=node.get("font_size_hint"),
            ))
        return pages

    def _paginate_by_chars(self, node: dict, content: str, title_base: str, page_count: int) -> list[PaginatedNode]:
        """按字数均分。"""
        import math
        total_len = len(content)
        chunk_size = math.ceil(total_len / page_count)
        pages: list[PaginatedNode] = []
        for pg in range(page_count):
            start = pg * chunk_size
            chunk = content[start:start + chunk_size]
            title_suffix = f"（{pg + 1}/{page_count}）" if page_count > 1 else ""
            pages.append(PaginatedNode(
                index=pg + 1,
                total=page_count,
                title=f"{title_base}{title_suffix}",
                content=chunk.strip(),
                key_points=[],
                segments=[],
                node_type=str(node.get("type") or node.get("node_type") or "content"),
                layout_hint=node.get("layout_hint"),
                font_size_hint=node.get("font_size_hint"),
            ))
        return pages
