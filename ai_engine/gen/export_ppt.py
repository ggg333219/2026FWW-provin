"""PPTX 导出模块 — 结构化教学节点到可编辑 PowerPoint。

导出器只消费现有节点字段，不改变底层 Schema。页面类型、要点和讲授分段均采用
与预览侧相同的兼容读取策略，并以原生文本/形状生成 Office、WPS 可编辑文件。
"""

from __future__ import annotations

import io
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Inches, Pt

from .templates import get_theme


SLIDE_WIDTH = Inches(13.333333)
SLIDE_HEIGHT = Inches(7.5)

_TYPE_ALIASES = {
    "cover": "cover", "title": "cover", "title_slide": "cover",
    "agenda": "agenda", "toc": "agenda", "directory": "agenda", "目录": "agenda",
    "section": "section", "divider": "section", "chapter": "section",
    "summary": "summary", "conclusion": "summary", "recap": "summary",
    "quiz": "quiz", "interactive": "quiz", "question": "quiz",
    "two_column": "two_column", "content": "content", "slide": "content",
    "opening": "content", "explain": "content", "explanation": "content",
    "transition": "content",
}

_SEGMENT_LABELS = {
    "opening": "导入", "exclamation": "强调", "explanation": "讲解", "explain": "讲解",
    "example": "示例", "interaction": "互动", "interactive": "互动",
    "transition": "过渡", "summary": "小结",
}


def _as_mapping(node: Any) -> dict[str, Any]:
    """兼容 dict、Pydantic v1/v2 和普通对象。"""
    if isinstance(node, dict):
        return node
    if hasattr(node, "model_dump"):
        return node.model_dump()
    if hasattr(node, "dict"):
        return node.dict()
    return vars(node)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def resolve_node_type(node: Any) -> str:
    """优先标准字段 node_type，回退历史字段 type；未知值按内容页处理。"""
    item = _as_mapping(node)
    raw = _enum_value(item.get("node_type")) or _enum_value(item.get("type"))
    return _TYPE_ALIASES.get(raw, "content")


def resolve_key_points(node: Any) -> list[str]:
    """合并 key_points/core_points，去重但不丢弃任一来源。"""
    item = _as_mapping(node)
    values: list[str] = []
    for field in ("key_points", "core_points"):
        raw = item.get(field) or []
        if isinstance(raw, str):
            raw = raw.splitlines()
        if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, dict)):
            for value in raw:
                text = str(value or "").strip()
                if text and text not in values:
                    values.append(text)
    return values


@dataclass
class ExportPPTConfig:
    """PPTX 导出配置。"""
    template_dir: str = ""
    default_template: str = "default"
    output_dir: str = "data/exports"
    include_auto_cover: bool = False


class PPTExporter:
    """将标准化教学节点导出为专业、可编辑的 16:9 PPTX。"""

    def __init__(self, config: ExportPPTConfig | None = None):
        self.config = config or ExportPPTConfig()
        self._theme = get_theme(self.config.default_template)

    def export(self, nodes: list[dict[str, Any]], course_name: str = "课件",
               template_id: str = "default") -> dict[str, Any]:
        prs = self._render(nodes, course_name, template_id)
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in course_name).strip() or "课件"
        output_dir = Path(self.config.output_dir)
        # 既有测试和部分 Linux 配置使用 /tmp；Windows 下映射到系统临时目录。
        if os.name == "nt" and output_dir.as_posix().startswith("/tmp"):
            relative = output_dir.as_posix()[len("/tmp"):].lstrip("/")
            output_dir = Path(tempfile.gettempdir()) / relative
        output_path = output_dir / f"{safe_name}.pptx"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(output_path))
        return {
            "path": str(output_path), "pages": len(prs.slides),
            "file_size": output_path.stat().st_size, "template_id": self._theme.template_id,
        }

    def export_to_bytes(self, nodes: list[dict[str, Any]], course_name: str = "课件",
                        template_id: str = "default") -> io.BytesIO:
        prs = self._render(nodes, course_name, template_id)
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        return buf

    def _render(self, nodes: list[dict[str, Any]], course_name: str,
                template_id: str) -> Presentation:
        self._theme = get_theme(template_id or self.config.default_template)
        prs = self._create_presentation(template_id)
        normalized = [_as_mapping(node) for node in (nodes or [])]
        if self.config.include_auto_cover or not normalized:
            self._add_cover_slide(prs, {"title": course_name, "content": "AI 智能生成课件"})
        for index, node in enumerate(normalized, start=1):
            self._get_slide_handler(resolve_node_type(node))(prs, node, index)
        prs.core_properties.title = str(course_name or "课件")
        prs.core_properties.subject = "多模态 AI 互动式教学课件"
        prs.core_properties.author = "多模态 AI 互动式教学智能体"
        return prs

    def _create_presentation(self, template_id: str) -> Presentation:
        """加载可选母版并清除示例页；默认创建干净 16:9 文件。"""
        template_path: Path | None = None
        if self.config.template_dir:
            candidate = Path(self.config.template_dir) / f"{template_id}.pptx"
            if candidate.exists():
                template_path = candidate
        prs = Presentation(str(template_path)) if template_path else Presentation()
        if template_path:
            self._remove_all_slides(prs)
        prs.slide_width = SLIDE_WIDTH
        prs.slide_height = SLIDE_HEIGHT
        return prs

    @staticmethod
    def _remove_all_slides(prs: Presentation) -> None:
        slide_ids = prs.slides._sldIdLst  # python-pptx 暂无公开删除幻灯片 API
        for slide_id in list(slide_ids):
            prs.part.drop_rel(slide_id.rId)
            slide_ids.remove(slide_id)

    def _get_slide_handler(self, node_type: str):
        return {
            "cover": self._add_cover_slide, "agenda": self._add_agenda_slide,
            "section": self._add_section_slide, "summary": self._add_summary_slide,
            "quiz": self._add_quiz_slide, "two_column": self._add_two_column_slide,
            "content": self._add_content_slide,
        }.get(node_type, self._add_content_slide)

    def _blank_slide(self, prs: Presentation, page_number: int | None = None):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        self._set_background(slide, self._theme.background)
        if page_number is not None:
            self._add_textbox(slide, str(page_number), 12.35, 7.05, 0.45, 0.22,
                              font_size=9, color=self._theme.muted, align=PP_ALIGN.RIGHT)
        return slide

    def _add_cover_slide(self, prs: Presentation, node: dict[str, Any], index: int = 1) -> None:
        slide = self._blank_slide(prs)
        self._set_background(slide, self._theme.primary)
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, 0.23, 7.5, self._theme.accent)
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0.23, 6.92, 13.1, 0.58, self._theme.secondary)
        title = str(node.get("title") or node.get("content") or "课件").strip()
        subtitle = str(node.get("content") or node.get("summary") or "").strip()
        if subtitle == title:
            subtitle = ""
        self._add_textbox(slide, title, 1.05, 2.15, 11.1, 1.65,
                          font_size=self._fit_font(title, 34, 50, 18), color=self._theme.inverse,
                          bold=True, valign=MSO_ANCHOR.MIDDLE)
        if subtitle:
            self._add_textbox(slide, subtitle, 1.08, 4.05, 9.8, 0.95,
                              font_size=self._fit_font(subtitle, 20, 28, 32), color=self._theme.inverse)
        self._add_textbox(slide, self._theme.display_name, 1.08, 6.19, 3.4, 0.3,
                          font_size=11, color=self._theme.inverse, bold=True)

    def _add_section_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        slide = self._blank_slide(prs, index)
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, 4.2, 7.5, self._theme.primary)
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 4.2, 0, 0.12, 7.5, self._theme.accent)
        self._add_textbox(slide, f"{index:02d}", 0.75, 1.35, 2.3, 1.0,
                          font_size=46, color=self._theme.inverse, bold=True)
        title = str(node.get("title") or "新章节")
        self._add_textbox(slide, title, 4.95, 2.25, 7.45, 1.7,
                          font_size=self._fit_font(title, 30, 42, 14), color=self._theme.text,
                          bold=True, valign=MSO_ANCHOR.MIDDLE)
        summary = str(node.get("summary") or node.get("content") or "").strip()
        if summary:
            self._add_textbox(slide, summary, 5.0, 4.15, 6.9, 1.0,
                              font_size=self._fit_font(summary, 17, 23, 36), color=self._theme.muted)

    def _add_agenda_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        items = resolve_key_points(node)
        if not items:
            raw = node.get("content") or node.get("summary") or ""
            items = [line.strip(" -•\t") for line in str(raw).splitlines() if line.strip()]
        items = items or ["课程导入", "核心内容", "课堂实践", "总结提升"]
        chunks = self._chunk_items(items, 7)
        for chunk_index, chunk in enumerate(chunks):
            slide = self._blank_slide(prs, index)
            title = str(node.get("title") or "课程目录") + ("（续）" if chunk_index else "")
            self._add_page_title(slide, title, "AGENDA")
            y = 1.55
            for offset, text in enumerate(chunk, start=chunk_index * 7 + 1):
                self._add_textbox(slide, f"{offset:02d}", 0.95, y, 0.7, 0.48,
                                  font_size=19, color=self._theme.accent, bold=True)
                self._add_textbox(slide, text, 1.85, y - 0.02, 10.25, 0.58,
                                  font_size=self._fit_font(text, 19, 25, 36), color=self._theme.text)
                self._add_shape(slide, MSO_SHAPE.RECTANGLE, 1.85, y + 0.54, 9.95, 0.012, self._theme.muted)
                y += 0.77

    def _add_content_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        main_items = self._main_items(node)
        segment_items = self._segment_items(node)
        if not main_items and not segment_items:
            main_items = [("正文", "暂无正文内容", False)]
        main_chunks = self._chunk_weighted(main_items, 12 if segment_items else 22,
                                           37 if segment_items else 72)
        segment_chunks = self._chunk_weighted(segment_items, 13, 35)
        page_count = max(len(main_chunks), len(segment_chunks), 1)
        title = str(node.get("title") or f"第 {index} 页")
        for page_index in range(page_count):
            slide = self._blank_slide(prs, index)
            page_title = title + (f"（续 {page_index + 1}）" if page_index else "")
            self._add_page_title(slide, page_title, "CONTENT")
            main_chunk = main_chunks[page_index] if page_index < len(main_chunks) else []
            seg_chunk = segment_chunks[page_index] if page_index < len(segment_chunks) else []
            if main_chunk and seg_chunk:
                self._add_panel(slide, "教学内容", main_chunk, 0.72, 1.42, 5.86, 5.35)
                self._add_panel(slide, "讲授分段", seg_chunk, 6.78, 1.42, 5.82, 5.35)
            elif seg_chunk:
                self._add_panel(slide, "讲授分段", seg_chunk, 0.72, 1.42, 11.88, 5.35)
            else:
                self._add_panel(slide, "教学内容", main_chunk, 0.72, 1.42, 11.88, 5.35)

    def _add_two_column_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        """固定双栏页：左栏核心要点，右栏讲授分段或内容展开。"""
        key_items = [("要点", point, True) for point in resolve_key_points(node)]
        if not key_items:
            summary = str(node.get("summary") or "暂无核心要点").strip()
            key_items = [("摘要", summary, False)]

        right_items = self._segment_items(node)
        right_heading = "讲授分段"
        if not right_items:
            right_heading = "内容展开"
            right_items = []
            for label, field in (("正文", "content"), ("讲稿", "script")):
                value = node.get(field)
                if isinstance(value, str) and value.strip():
                    right_items.append((label, value.strip(), False))
            if not right_items:
                right_items = [("正文", "暂无展开内容", False)]

        left_chunks = self._chunk_weighted(key_items, 13, 34)
        right_chunks = self._chunk_weighted(right_items, 13, 36)
        page_count = max(len(left_chunks), len(right_chunks), 1)
        title = str(node.get("title") or f"第 {index} 页")

        for page_index in range(page_count):
            slide = self._blank_slide(prs, index)
            page_title = title + (f"（续 {page_index + 1}）" if page_index else "")
            self._add_page_title(slide, page_title, "TWO COLUMN")
            left_chunk = left_chunks[page_index] if page_index < len(left_chunks) else []
            right_chunk = right_chunks[page_index] if page_index < len(right_chunks) else []
            self._add_panel(slide, "核心要点", left_chunk, 0.72, 1.42, 5.58, 5.35)
            self._add_panel(slide, right_heading, right_chunk, 6.72, 1.42, 5.88, 5.35)

    def _add_quiz_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        questions = node.get("questions") or node.get("interactive_questions") or []
        if isinstance(questions, str):
            questions = [line for line in questions.splitlines() if line.strip()]
        questions = [str(q).strip() for q in questions if str(q).strip()] or ["请结合本节内容提出一个关键问题。"]
        chunks = self._chunk_items(questions, 5)
        for chunk_index, chunk in enumerate(chunks):
            slide = self._blank_slide(prs, index)
            title = str(node.get("title") or "课堂互动") + ("（续）" if chunk_index else "")
            self._add_page_title(slide, title, "INTERACTION")
            y = 1.6
            for number, question in enumerate(chunk, start=chunk_index * 5 + 1):
                self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.85, y, 0.58, 0.58, self._theme.accent)
                self._add_textbox(slide, str(number), 0.85, y + 0.02, 0.58, 0.42,
                                  font_size=17, color=self._theme.inverse, bold=True, align=PP_ALIGN.CENTER)
                self._add_textbox(slide, question, 1.68, y - 0.02, 10.55, 0.82,
                                  font_size=self._fit_font(question, 18, 24, 42), color=self._theme.text)
                y += 1.02

    def _add_summary_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        points = resolve_key_points(node)
        if not points:
            raw = node.get("content") or node.get("summary") or "本节要点"
            points = [line.strip(" -•\t") for line in str(raw).splitlines() if line.strip()]
        chunks = self._chunk_items(points or ["本节要点"], 6)
        for chunk_index, chunk in enumerate(chunks):
            slide = self._blank_slide(prs, index)
            title = str(node.get("title") or "本节小结") + ("（续）" if chunk_index else "")
            self._add_page_title(slide, title, "SUMMARY")
            self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0.72, 1.48, 0.09, 5.15, self._theme.accent)
            y = 1.62
            for text in chunk:
                self._add_shape(slide, MSO_SHAPE.OVAL, 1.08, y + 0.13, 0.18, 0.18, self._theme.secondary)
                self._add_textbox(slide, text, 1.52, y, 10.45, 0.67,
                                  font_size=self._fit_font(text, 18, 25, 42), color=self._theme.text)
                y += 0.78

    def _main_items(self, node: dict[str, Any]) -> list[tuple[str, str, bool]]:
        items: list[tuple[str, str, bool]] = []
        for label, field in (("正文", "content"), ("讲稿", "script"), ("摘要", "summary")):
            value = node.get(field)
            if isinstance(value, str) and value.strip():
                items.append((label, value.strip(), False))
            elif isinstance(value, list):
                for entry in value:
                    text = str(entry or "").strip()
                    if text:
                        items.append((label, text, True))
        for point in resolve_key_points(node):
            items.append(("要点", point, True))
        return items

    def _segment_items(self, node: dict[str, Any]) -> list[tuple[str, str, bool]]:
        items: list[tuple[str, str, bool]] = []
        for segment in node.get("segments") or []:
            segment = _as_mapping(segment)
            text = str(segment.get("text") or segment.get("content") or "").strip()
            if not text:
                continue
            raw_type = _enum_value(segment.get("segment_type")) or "explanation"
            label = _SEGMENT_LABELS.get(raw_type, raw_type or "讲解")
            seconds = segment.get("estimated_seconds")
            if seconds in (None, "", 0):
                seconds = segment.get("duration_seconds") or segment.get("estimated_duration")
            duration = self._format_duration(seconds)
            heading = f"{label} · {duration}" if duration else label
            items.append((heading, text, False))
        return items

    @staticmethod
    def _format_duration(value: Any) -> str:
        try:
            seconds = int(float(value))
        except (TypeError, ValueError):
            return ""
        if seconds <= 0:
            return ""
        if seconds >= 60:
            minutes, remain = divmod(seconds, 60)
            return f"{minutes}分{remain}秒" if remain else f"{minutes}分钟"
        return f"{seconds}秒"

    @staticmethod
    def _chunk_items(items: list[str], count: int) -> list[list[str]]:
        return [items[i:i + count] for i in range(0, len(items), count)] or [[]]

    @staticmethod
    def _chunk_weighted(items: list[tuple[str, str, bool]], max_units: int,
                        chars_per_line: int) -> list[list[tuple[str, str, bool]]]:
        if not items:
            return []
        chunks: list[list[tuple[str, str, bool]]] = []
        current: list[tuple[str, str, bool]] = []
        used = 0
        expanded: list[tuple[str, str, bool]] = []
        max_chars = chars_per_line * max(2, max_units - 2)
        for label, text, bullet in items:
            pieces = PPTExporter._split_text(text, max_chars)
            for piece_index, piece in enumerate(pieces):
                piece_label = f"{label}（续）" if piece_index else label
                expanded.append((piece_label, piece, bullet))
        for item in expanded:
            units = max(1, math.ceil(len(item[1]) / chars_per_line)) + 1
            if current and used + units > max_units:
                chunks.append(current)
                current = []
                used = 0
            current.append(item)
            used += units
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
        """按句子优先切分超长字段，保证续页完整保留原文。"""
        normalized = str(text or "").strip()
        if len(normalized) <= max_chars:
            return [normalized]
        sentences = [part for part in re.split(r"(?<=[。！？；;.!?])", normalized) if part]
        pieces: list[str] = []
        current = ""
        for sentence in sentences:
            while len(sentence) > max_chars:
                if current:
                    pieces.append(current)
                    current = ""
                pieces.append(sentence[:max_chars])
                sentence = sentence[max_chars:]
            if current and len(current) + len(sentence) > max_chars:
                pieces.append(current)
                current = ""
            current += sentence
        if current:
            pieces.append(current)
        return pieces or [normalized]

    def _add_page_title(self, slide, title: str, kicker: str) -> None:
        self._add_textbox(slide, kicker, 0.75, 0.4, 2.2, 0.24,
                          font_size=10, color=self._theme.accent, bold=True)
        self._add_textbox(slide, title, 0.72, 0.7, 11.75, 0.56,
                          font_size=self._fit_font(title, 26, 34, 20), color=self._theme.text, bold=True)
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0.72, 1.27, 11.88, 0.02, self._theme.secondary)

    def _add_panel(self, slide, heading: str, items: list[tuple[str, str, bool]],
                   x: float, y: float, width: float, height: float) -> None:
        self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, width, height,
                        self._theme.surface, line=self._theme.muted)
        self._add_textbox(slide, heading, x + 0.28, y + 0.18, width - 0.56, 0.36,
                          font_size=15, color=self._theme.secondary, bold=True)
        box = slide.shapes.add_textbox(Inches(x + 0.27), Inches(y + 0.68),
                                       Inches(width - 0.54), Inches(height - 0.9))
        frame = box.text_frame
        frame.clear()
        frame.word_wrap = True
        frame.auto_size = MSO_AUTO_SIZE.NONE
        frame.margin_left = frame.margin_right = Inches(0.03)
        frame.margin_top = frame.margin_bottom = Inches(0.02)
        total_chars = sum(len(text) for _, text, _ in items)
        size = 16 if total_chars > 500 else 17 if total_chars > 300 else 18
        for item_index, (label, text, bullet) in enumerate(items):
            paragraph = frame.paragraphs[0] if item_index == 0 else frame.add_paragraph()
            paragraph.text = f"{label}｜{text}" if label else text
            paragraph.level = 0
            paragraph.space_after = Pt(7)
            paragraph.line_spacing = 1.13
            paragraph.font.name = self._theme.body_font
            paragraph.font.size = Pt(size)
            paragraph.font.color.rgb = self._rgb(self._theme.text)
            if bullet:
                paragraph.text = f"• {paragraph.text}"

    @staticmethod
    def _fit_font(text: str, minimum: int, maximum: int, chars_per_line: int) -> int:
        lines = max(1, math.ceil(len(str(text or "")) / chars_per_line))
        return max(minimum, min(maximum, maximum - max(0, lines - 1) * 3))

    def _add_shape(self, slide, shape_type, x: float, y: float, width: float,
                   height: float, fill: str, line: str | None = None):
        shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(width), Inches(height))
        shape.fill.solid()
        shape.fill.fore_color.rgb = self._rgb(fill)
        if line:
            shape.line.color.rgb = self._rgb(line)
            shape.line.transparency = 60
        else:
            shape.line.fill.background()
        return shape

    def _add_textbox(self, slide, text: str, x: float, y: float, width: float,
                     height: float, *, font_size: int, color: str, bold: bool = False,
                     align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
        frame = box.text_frame
        frame.clear()
        frame.word_wrap = True
        frame.auto_size = MSO_AUTO_SIZE.NONE
        frame.vertical_anchor = valign
        frame.margin_left = frame.margin_right = Inches(0.02)
        frame.margin_top = frame.margin_bottom = Inches(0.01)
        paragraph = frame.paragraphs[0]
        paragraph.text = str(text or "")
        paragraph.alignment = align
        paragraph.font.name = self._theme.title_font if bold else self._theme.body_font
        paragraph.font.size = Pt(font_size)
        paragraph.font.bold = bold
        paragraph.font.color.rgb = self._rgb(color)
        return box

    @staticmethod
    def _set_background(slide, color: str) -> None:
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = PPTExporter._rgb(color)

    @staticmethod
    def _rgb(value: str) -> RGBColor:
        return RGBColor.from_string(value.lstrip("#").upper())
