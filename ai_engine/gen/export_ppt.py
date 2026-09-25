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
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from .templates import get_theme


SLIDE_WIDTH = Inches(13.333333)
SLIDE_HEIGHT = Inches(7.5)

# 东亚字体：python-pptx 的 font.name 只写入 a:latin（西文字形），
# WPS / 中文 Office 渲染中文时读取 a:ea 字形，缺失会回退默认宋体。
EA_FONT_NAME = "微软雅黑"

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

# ── 内容可视化特征检测 ──
# 流程特征：正文出现顺序词时，把句子抽取为横向流程条（矩形序列 + "→" 连接）。
_FLOW_KEYWORDS = ("步骤", "流程", "首先", "然后", "接着", "其次", "最后",
                  "第一", "第二", "第三", "随后", "最终")
_FLOW_LEADING_RE = re.compile(
    r"^(首先|然后|接着|其次|最后|随后|最终|第[一二三四五六]步|步骤[一二三四五六]?)[，,：:、\s]*")
# 数值对比特征：出现 ≥2 个百分比时渲染为按数值比例的条形对比块。
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[%％]")


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
    """与预览侧一致：优先读取 type，回退 node_type。"""
    item = _as_mapping(node)
    raw = _enum_value(item.get("type")) or _enum_value(item.get("node_type"))
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
    # 图文并茂增强（默认关闭，保持既有导出页数与预览节点同源）：
    include_auto_toc: bool = False      # 封面后自动插入目录页（条目=节点标题列表）
    include_closing_slide: bool = False # 末节点为 summary 时追加"感谢聆听"结束页


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
        auto_cover = self.config.include_auto_cover or not normalized
        toc_entries = self._toc_entries(normalized) if self.config.include_auto_toc else []
        leading_cover = auto_cover or (normalized and resolve_node_type(normalized[0]) == "cover")
        if toc_entries and not leading_cover:
            # 全程无封面时，目录作为首页
            self._add_auto_toc_slides(prs, toc_entries)
            toc_entries = []
        if auto_cover:
            self._add_cover_slide(prs, {"title": course_name, "content": "AI 智能生成课件"})
            if toc_entries:
                self._add_auto_toc_slides(prs, toc_entries)
                toc_entries = []
        for index, node in enumerate(normalized, start=1):
            self._get_slide_handler(resolve_node_type(node))(prs, node, index)
            if toc_entries and index == 1 and resolve_node_type(node) == "cover":
                self._add_auto_toc_slides(prs, toc_entries)
                toc_entries = []
        if self.config.include_closing_slide and normalized \
                and resolve_node_type(normalized[-1]) == "summary":
            self._add_ending_slide(prs)
        prs.core_properties.title = str(course_name or "课件")
        prs.core_properties.subject = "多模态 AI 互动式教学课件"
        prs.core_properties.author = "多模态 AI 互动式教学智能体"
        return prs

    @staticmethod
    def _toc_entries(normalized: list[dict[str, Any]]) -> list[str]:
        """目录条目 = 每个教学节点的标题（条目数与节点数一一对应）。"""
        entries: list[str] = []
        for index, node in enumerate(normalized, start=1):
            title = str(node.get("title") or "").strip()
            entries.append(title or f"第 {index} 页")
        return entries

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

    def _blank_slide(self, prs: Presentation, page_number: int | None = None,
                     footer: bool = True):
        """创建空白页。page_number 仅用于兼容旧调用，页码统一由标题条渲染。"""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        self._set_background(slide, self._theme.background)
        if footer:
            self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0.72, 7.14, 11.88, 0.012,
                            self._theme.muted)
            self._add_textbox(slide, "多模态 AI 互动式教学智能体 · 教学课件", 0.72, 7.0,
                              5.2, 0.3, font_size=9, color=self._theme.muted)
        return slide

    def _add_cover_slide(self, prs: Presentation, node: dict[str, Any], index: int = 1) -> None:
        slide = self._blank_slide(prs, footer=False)
        self._set_background(slide, self._theme.primary)
        # 几何装饰：左侧强调条 + 底部色带 + 错落圆形（纯形状，WPS 兼容）
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, 0.23, 7.5, self._theme.accent)
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0.23, 6.92, 13.11, 0.58, self._theme.secondary)
        self._add_shape(slide, MSO_SHAPE.OVAL, 10.55, -1.35, 3.7, 3.7,
                        self._blend(self._theme.primary, self._theme.inverse, 0.14))
        self._add_shape(slide, MSO_SHAPE.OVAL, 11.95, 4.55, 2.6, 2.6,
                        self._blend(self._theme.secondary, self._theme.inverse, 0.22))
        self._add_shape(slide, MSO_SHAPE.OVAL, -0.95, 5.35, 2.3, 2.3,
                        self._blend(self._theme.primary, self._theme.inverse, 0.10))
        title = str(node.get("title") or node.get("content") or "课件").strip()
        subtitle = str(node.get("content") or node.get("summary") or "").strip()
        if subtitle == title:
            subtitle = ""
        # 标题上下居中：主标题 + 副标题整体居中排布，配短装饰条
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 5.92, 1.72, 1.5, 0.075, self._theme.accent)
        self._add_textbox(slide, title, 1.05, 2.05, 11.23, 1.75,
                          font_size=self._fit_font(title, 34, 50, 18), color=self._theme.inverse,
                          bold=True, align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
        if subtitle:
            self._add_textbox(slide, subtitle, 1.6, 4.0, 10.13, 0.95,
                              font_size=self._fit_font(subtitle, 20, 28, 32),
                              color=self._theme.inverse, align=PP_ALIGN.CENTER)
            self._add_shape(slide, MSO_SHAPE.RECTANGLE, 5.92, 5.12, 1.5, 0.05,
                            self._blend(self._theme.accent, self._theme.inverse, 0.25))
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
        self._add_textbox(slide, f"{index:02d}", 12.05, 6.98, 0.95, 0.32,
                          font_size=10, color=self._theme.muted, align=PP_ALIGN.RIGHT)

    def _add_auto_toc_slides(self, prs: Presentation, entries: list[str]) -> None:
        """自动目录页：两栏卡片式，每页 8 条（4 行 × 2 列），条目与节点一一对应。"""
        chunks = self._chunk_items(entries, 8)
        col_x = (0.85, 6.95)
        card_w, card_h, gap_y = 5.55, 1.02, 0.24
        for chunk_index, chunk in enumerate(chunks):
            slide = self._blank_slide(prs)
            title = "目录" + ("（续）" if chunk_index else "")
            self._add_page_title(slide, title, "CONTENTS")
            start = chunk_index * 8
            for offset, text in enumerate(chunk):
                row, col = divmod(offset, 2)
                x, y = col_x[col], 1.6 + row * (card_h + gap_y)
                self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, card_w, card_h,
                                self._theme.surface, line=self._theme.muted)
                self._add_shape(slide, MSO_SHAPE.OVAL, x + 0.2, y + 0.26, 0.5, 0.5,
                                self._theme.accent)
                number = start + offset + 1
                self._add_textbox(slide, f"{number:02d}", x + 0.2, y + 0.34, 0.5, 0.36,
                                  font_size=14, color=self._theme.inverse, bold=True,
                                  align=PP_ALIGN.CENTER)
                self._add_textbox(slide, text, x + 0.88, y + 0.25, card_w - 1.1, 0.56,
                                  font_size=self._fit_font(text, 14, 19, 15),
                                  color=self._theme.text, valign=MSO_ANCHOR.MIDDLE)

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
            self._add_page_title(slide, title, "AGENDA", index)
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
        viz = self._select_visualization(node)
        scale = self._viz_body_scale(viz)
        main_cpl = max(16, int((72 if not segment_items else 37) * scale))
        seg_cpl = max(12, int(37 * scale))
        main_chunks = self._chunk_weighted(main_items, 12 if segment_items else 22, main_cpl)
        segment_chunks = self._chunk_weighted(segment_items, 13, seg_cpl)
        page_count = max(len(main_chunks), len(segment_chunks), 1)
        title = str(node.get("title") or f"第 {index} 页")
        for page_index in range(page_count):
            slide = self._blank_slide(prs, index)
            page_title = title + (f"（续 {page_index + 1}）" if page_index else "")
            self._add_page_title(slide, page_title, "CONTENT", index)
            body_y, body_h = 1.42, 5.35
            if viz and page_index == 0:
                zone_h = self._render_visualization(slide, viz, 1.42)
                body_y = 1.42 + zone_h + 0.16
                body_h = max(5.35 - zone_h - 0.16, 1.3)
            main_chunk = main_chunks[page_index] if page_index < len(main_chunks) else []
            seg_chunk = segment_chunks[page_index] if page_index < len(segment_chunks) else []
            if main_chunk and seg_chunk:
                self._add_panel(slide, "教学内容", main_chunk, 0.72, body_y, 5.86, body_h)
                self._add_panel(slide, "讲授分段", seg_chunk, 6.78, body_y, 5.82, body_h)
            elif seg_chunk:
                self._add_panel(slide, "讲授分段", seg_chunk, 0.72, body_y, 11.88, body_h)
            else:
                self._add_panel(slide, "教学内容", main_chunk, 0.72, body_y, 11.88, body_h)

    # ── 内容可视化：流程条 / 数值对比条 / 序号要点条 ──

    @staticmethod
    def _node_body_text(node: dict[str, Any]) -> str:
        parts = []
        for field in ("content", "summary"):
            value = node.get(field)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return "\n".join(parts)

    @classmethod
    def _detect_flow_steps(cls, node: dict[str, Any]) -> list[str]:
        """正文含顺序词时抽取 2-4 步流程；否则返回空。"""
        text = cls._node_body_text(node)
        if not text or not any(keyword in text for keyword in _FLOW_KEYWORDS):
            return []
        sentences = [part.strip() for part in re.split(r"[。！？；;.!?\n]", text) if part.strip()]
        steps = [s for s in sentences if any(keyword in s for keyword in _FLOW_KEYWORDS)]
        if len(steps) < 2:
            steps = sentences if 2 <= len(sentences) <= 4 else []
        if len(steps) < 2:
            return []
        cleaned: list[str] = []
        for step in steps[:4]:
            step = _FLOW_LEADING_RE.sub("", step)
            if step:
                cleaned.append(step[:34])
        return cleaned if len(cleaned) >= 2 else []

    @classmethod
    def _detect_comparison_bars(cls, node: dict[str, Any]) -> list[tuple[str, float]]:
        """正文/要点含 ≥2 个百分比时返回（标签, 数值）列表，供条形对比渲染。"""
        text = cls._node_body_text(node)
        points = resolve_key_points(node)
        if points:
            text = "\n".join([text, *points]).strip()
        if not text:
            return []
        items: list[tuple[str, float]] = []
        for match in list(_PERCENT_RE.finditer(text))[:4]:
            value = float(match.group(1))
            context = text[max(0, match.start() - 12):match.start()]
            context = re.sub(r"^[\s，,。；;：:、()（）\-—*•]*", "", context)[-8:].strip()
            items.append((context or "占比", value))
        if len(items) < 2 or all(value <= 0 for _, value in items):
            return []
        return items

    def _select_visualization(self, node: dict[str, Any]) -> tuple[str, Any] | None:
        """可视化优先级：流程条 > 数值对比条 > 序号要点条（3-5 条要点）。"""
        flow = self._detect_flow_steps(node)
        if flow:
            return ("flow", flow)
        bars = self._detect_comparison_bars(node)
        if bars:
            return ("bars", bars)
        points = resolve_key_points(node)
        if 3 <= len(points) <= 5:
            return ("points", points[:5])
        return None

    @staticmethod
    def _viz_body_scale(viz: tuple[str, Any] | None) -> float:
        """图示区占据首页空间后，正文按剩余高度比例折算每行字数。"""
        if not viz:
            return 1.0
        return {"flow": 0.64, "bars": 0.58, "points": 0.5}.get(viz[0], 0.6)

    def _render_visualization(self, slide, viz: tuple[str, Any], y: float) -> float:
        """在 (0.72, y, 11.88, zone) 区域渲染图示，返回占用高度。"""
        kind, payload = viz
        if kind == "flow":
            return self._render_flow(slide, payload, y)
        if kind == "bars":
            return self._render_bars(slide, payload, y)
        return self._render_point_bars(slide, payload, y)

    def _render_zone_label(self, slide, text: str, y: float) -> None:
        self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.72, y, 1.4, 0.34,
                        self._theme.secondary)
        self._add_textbox(slide, text, 0.72, y + 0.04, 1.4, 0.28, font_size=11,
                          color=self._theme.inverse, bold=True, align=PP_ALIGN.CENTER)

    def _render_flow(self, slide, steps: list[str], y: float) -> float:
        """横向流程条：矩形步骤框 + "→" 连接符（纯文本符号，WPS 兼容）。"""
        self._render_zone_label(slide, "流程图示", y)
        zone_h = 1.78
        count = len(steps)
        arrow_w = 0.42
        box_w = (11.88 - (count - 1) * arrow_w) / count
        box_y, box_h = y + 0.52, 1.1
        for i, step in enumerate(steps):
            x = 0.72 + i * (box_w + arrow_w)
            self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, box_y, box_w, box_h,
                            self._theme.surface, line=self._theme.secondary)
            self._add_shape(slide, MSO_SHAPE.OVAL, x + box_w / 2 - 0.16, box_y + 0.1,
                            0.32, 0.32, self._theme.accent)
            self._add_textbox(slide, str(i + 1), x + box_w / 2 - 0.16, box_y + 0.14,
                              0.32, 0.26, font_size=11, color=self._theme.inverse,
                              bold=True, align=PP_ALIGN.CENTER)
            self._add_textbox(slide, step, x + 0.12, box_y + 0.5, box_w - 0.24, 0.55,
                              font_size=self._fit_font(step, 10, 13, 14),
                              color=self._theme.text, align=PP_ALIGN.CENTER)
            if i < count - 1:
                self._add_textbox(slide, "→", x + box_w, box_y + 0.36, arrow_w, 0.5,
                                  font_size=20, color=self._theme.accent, bold=True,
                                  align=PP_ALIGN.CENTER)
        return zone_h

    def _render_bars(self, slide, items: list[tuple[str, float]], y: float) -> float:
        """条形对比块：矩形宽度按数值比例，数值文本标注在条末。"""
        self._render_zone_label(slide, "数据对比", y)
        count = len(items)
        zone_h = 0.52 + 0.55 * count + 0.12
        max_value = max(value for _, value in items) or 1.0
        label_w, bar_x, bar_max_w = 2.4, 3.3, 8.0
        row_y = y + 0.52
        for i, (label, value) in enumerate(items):
            width = max(0.4, bar_max_w * (value / max_value))
            fill = self._theme.accent if i % 2 == 0 else self._theme.secondary
            self._add_textbox(slide, label, 0.72, row_y + 0.03, label_w, 0.4,
                              font_size=12, color=self._theme.text, align=PP_ALIGN.RIGHT)
            self._add_shape(slide, MSO_SHAPE.RECTANGLE, bar_x, row_y + 0.06, width, 0.34, fill)
            self._add_textbox(slide, f"{value:g}%", bar_x + width + 0.12, row_y + 0.05,
                              1.4, 0.38, font_size=13, color=self._theme.text, bold=True)
            row_y += 0.55
        return zone_h

    def _render_point_bars(self, slide, points: list[str], y: float) -> float:
        """序号要点条：圆角矩形 + 编号圆，逐条排布。"""
        count = len(points)
        zone_h = min(0.52 + 0.62 * count, 3.85)
        row_h = min(0.52, (zone_h - 0.52) / max(count, 1))
        row_y = y + 0.52
        for i, point in enumerate(points):
            text = point if len(point) <= 40 else point[:39] + "…"
            self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.72, row_y, 11.88, row_h,
                            self._theme.surface, line=self._theme.muted)
            self._add_shape(slide, MSO_SHAPE.OVAL, 0.94, row_y + row_h / 2 - 0.16,
                            0.32, 0.32, self._theme.accent)
            self._add_textbox(slide, str(i + 1), 0.94, row_y + row_h / 2 - 0.12,
                              0.32, 0.26, font_size=11, color=self._theme.inverse,
                              bold=True, align=PP_ALIGN.CENTER)
            self._add_textbox(slide, text, 1.52, row_y + row_h / 2 - 0.16, 10.9, 0.36,
                              font_size=13, color=self._theme.text,
                              valign=MSO_ANCHOR.MIDDLE)
            row_y += row_h + 0.1
        return zone_h

    def _add_two_column_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        """固定双栏页：左栏核心要点，右栏讲授分段或内容展开。"""
        key_items = [("要点", point, True) for point in resolve_key_points(node)]
        if not key_items:
            summary = str(node.get("summary") or "暂无核心要点").strip()
            key_items = [("摘要", summary, False)]

        body_items: list[tuple[str, str, bool]] = []
        for label, field in (("正文", "content"),):
            value = node.get(field)
            if isinstance(value, str) and value.strip():
                body_items.append((label, value.strip(), False))
        segment_items = []
        right_items = body_items + segment_items
        if body_items and segment_items:
            right_heading = "内容与讲授分段"
        elif segment_items:
            right_heading = "讲授分段"
        else:
            right_heading = "内容展开"
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
        items = self._quiz_question_items(node)
        chunks = self._chunk_quiz_items(items)
        number = 0
        for chunk_index, chunk in enumerate(chunks):
            slide = self._blank_slide(prs, index)
            title = str(node.get("title") or "课堂互动") + ("（续）" if chunk_index else "")
            self._add_page_title(slide, title, "INTERACTION", index)
            y = 1.55
            for question, options, answer in chunk:
                number += 1
                self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE,
                                0.85, y, 0.58, 0.58, self._theme.accent)
                self._add_textbox(slide, str(number), 0.85, y + 0.02, 0.58, 0.42,
                                  font_size=17, color=self._theme.inverse, bold=True,
                                  align=PP_ALIGN.CENTER)
                self._add_textbox(slide, question, 1.68, y - 0.02, 10.55, 0.82,
                                  font_size=self._fit_font(question, 18, 24, 42),
                                  color=self._theme.text, bold=True)
                if options:
                    opt_text = "    ".join(
                        f"{chr(65 + i)}．{opt}" for i, opt in enumerate(options[:6]))
                    self._add_textbox(slide, opt_text, 1.68, y + 0.82, 10.55, 0.62,
                                      font_size=self._fit_font(opt_text, 14, 18, 46),
                                      color=self._theme.text)
                    if answer:
                        self._add_textbox(slide, f"参考答案：{answer}", 1.68, y + 1.52,
                                          10.55, 0.4, font_size=13,
                                          color=self._theme.secondary, bold=True)
                    y += 2.45
                else:
                    y += 1.02

    _QUIZ_PLAIN_PER_PAGE = 5

    @classmethod
    def _quiz_question_items(cls, node: dict[str, Any]) -> list[tuple[str, list[str], str]]:
        """归一化 quiz 题目：兼容 dict（question/options/answer）与纯文本。"""
        raw = node.get("questions") or node.get("interactive_questions") or []
        if isinstance(raw, str):
            raw = [line for line in raw.splitlines() if line.strip()]
        items: list[tuple[str, list[str], str]] = []
        for question in raw:
            if isinstance(question, dict):
                text = str(question.get("question") or question.get("title")
                           or question.get("content") or "").strip()
                options = [str(opt).strip() for opt in (question.get("options") or [])
                           if str(opt).strip()]
                answer = str(question.get("answer") or "").strip()
            else:
                text, options, answer = str(question).strip(), [], ""
            if text:
                items.append((text, options, answer))
        return items

    @classmethod
    def _chunk_quiz_items(cls, items: list[tuple[str, list[str], str]]
                          ) -> list[list[tuple[str, list[str], str]]]:
        """带选项的题目占位大（每页 2 题），纯题目每页 5 题；
        一旦页面内含选项题，整页容量按 2 题计算，避免混排溢出。"""
        if not items:
            items = [("请结合本节内容提出一个关键问题。", [], "")]
        chunks: list[list[tuple[str, list[str], str]]] = []
        current: list[tuple[str, list[str], str]] = []
        for item in items:
            capacity = 2 if (item[1] or any(prev[1] for prev in current)) \
                else cls._QUIZ_PLAIN_PER_PAGE
            if current and len(current) >= capacity:
                chunks.append(current)
                current = []
            current.append(item)
        if current:
            chunks.append(current)
        return chunks

    def _add_summary_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        points = resolve_key_points(node)
        if not points:
            raw = node.get("content") or node.get("summary") or "本节要点"
            points = [line.strip(" -•\t") for line in str(raw).splitlines() if line.strip()]
        points = points or ["本节要点"]
        chunks = self._chunk_items(points, 5)
        tint = self._blend(self._theme.background, self._theme.primary, 0.07)
        for chunk_index, chunk in enumerate(chunks):
            slide = self._blank_slide(prs, index)
            self._set_background(slide, tint)  # 总结版式：浅色主题底，区隔内容页
            title = str(node.get("title") or "本节小结") + ("（续）" if chunk_index else "")
            self._add_page_title(slide, title, "SUMMARY", index)
            y = 1.62
            for offset, text in enumerate(chunk):
                number = chunk_index * 5 + offset + 1
                self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.72, y, 11.88, 0.78,
                                self._theme.surface, line=self._theme.muted)
                self._add_shape(slide, MSO_SHAPE.OVAL, 1.0, y + 0.19, 0.4, 0.4,
                                self._theme.secondary)
                self._add_textbox(slide, str(number), 1.0, y + 0.24, 0.4, 0.32,
                                  font_size=12, color=self._theme.inverse, bold=True,
                                  align=PP_ALIGN.CENTER)
                self._add_textbox(slide, text, 1.66, y + 0.16, 10.7, 0.5,
                                  font_size=self._fit_font(text, 15, 19, 34),
                                  color=self._theme.text, valign=MSO_ANCHOR.MIDDLE)
                y += 0.9
            if chunk_index == len(chunks) - 1:
                # 结尾收束条：致谢语固定在末页底部
                self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, 0.72, 6.2, 11.88, 0.6,
                                self._theme.primary)
                self._add_textbox(slide, "感谢聆听 · 本节内容到此结束", 0.72, 6.32, 11.88, 0.4,
                                  font_size=14, color=self._theme.inverse, bold=True,
                                  align=PP_ALIGN.CENTER)

    def _add_ending_slide(self, prs: Presentation) -> None:
        """结束页：深色底 + 居中致谢，仅 include_closing_slide 开启时追加。"""
        slide = self._blank_slide(prs, footer=False)
        self._set_background(slide, self._theme.primary)
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, 0.23, 7.5, self._theme.accent)
        self._add_shape(slide, MSO_SHAPE.OVAL, 10.9, -1.2, 3.3, 3.3,
                        self._blend(self._theme.primary, self._theme.inverse, 0.14))
        self._add_shape(slide, MSO_SHAPE.OVAL, -1.0, 5.2, 2.6, 2.6,
                        self._blend(self._theme.secondary, self._theme.inverse, 0.2))
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 5.92, 2.45, 1.5, 0.075, self._theme.accent)
        self._add_textbox(slide, "感谢聆听", 1.05, 2.85, 11.23, 1.3, font_size=44,
                          color=self._theme.inverse, bold=True, align=PP_ALIGN.CENTER)
        self._add_textbox(slide, "多模态 AI 互动式教学智能体 · 谢谢观看", 1.6, 4.3, 10.13, 0.6,
                          font_size=16, color=self._theme.inverse, align=PP_ALIGN.CENTER)

    def _main_items(self, node: dict[str, Any]) -> list[tuple[str, str, bool]]:
        items: list[tuple[str, str, bool]] = []
        for label, field in (("正文", "content"), ("摘要", "summary")):
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
        # 按需求：导出PPT不展示讲稿分段内容，仅保留核心要点
        return []

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

    def _add_page_title(self, slide, title: str, kicker: str,
                        page_number: int | None = None) -> None:
        """统一顶部标题条：主题色带 + kicker + 标题 + 页码，底部强调色细条。"""
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, 13.34, 1.16, self._theme.primary)
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0, 1.16, 13.34, 0.05, self._theme.accent)
        self._add_textbox(slide, kicker, 0.78, 0.18, 3.2, 0.26,
                          font_size=10, color=self._theme.accent, bold=True)
        self._add_textbox(slide, title, 0.75, 0.44, 10.4, 0.6,
                          font_size=self._fit_font(title, 24, 32, 22), color=self._theme.inverse,
                          bold=True)
        if page_number is not None:
            self._add_textbox(slide, f"{page_number:02d}", 12.1, 0.44, 0.9, 0.44,
                              font_size=14, color=self._theme.inverse, bold=True,
                              align=PP_ALIGN.RIGHT)

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
            # 先确定最终文本再设 run 样式：paragraph.text 赋值会重建 run
            paragraph.text = f"• {label}｜{text}" if bullet and label \
                else f"• {text}" if bullet \
                else f"{label}｜{text}" if label else text
            paragraph.level = 0
            paragraph.space_after = Pt(7)
            paragraph.line_spacing = 1.13
            paragraph.font.name = self._theme.body_font
            paragraph.font.size = Pt(size)
            paragraph.font.color.rgb = self._rgb(self._theme.text)
            self._apply_ea_font(paragraph.font)
            for run in paragraph.runs:
                run.font.name = self._theme.body_font
                run.font.size = Pt(size)
                run.font.color.rgb = self._rgb(self._theme.text)
                self._apply_ea_font(run.font)

    @staticmethod
    def _fit_font(text: str, minimum: int, maximum: int, chars_per_line: int) -> int:
        lines = max(1, math.ceil(len(str(text or "")) / chars_per_line))
        return max(minimum, min(maximum, maximum - max(0, lines - 1) * 3))

    def _add_shape(self, slide, shape_type, x: float, y: float, width: float,
                   height: float, fill: str, line: str | None = None):
        shape = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(width), Inches(height))
        shape.fill.solid()
        shape.fill.fore_color.rgb = self._rgb(fill)
        # Keep rendering deterministic across Office/WPS. Inheriting theme
        # shadows makes edge-aligned decorations bleed outside the canvas.
        shape.shadow.inherit = False
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
        self._apply_ea_font(paragraph.font)
        for run in paragraph.runs:
            run.font.name = self._theme.title_font if bold else self._theme.body_font
            run.font.size = Pt(font_size)
            run.font.bold = bold
            run.font.color.rgb = self._rgb(color)
            self._apply_ea_font(run.font)
        return box

    @staticmethod
    def _apply_ea_font(font) -> None:
        """补充东亚字体（a:ea）：WPS/中文 Office 用 ea 字形渲染中文，
        仅设置 latin 字形时中文会回退为默认宋体。"""
        try:
            rPr = font._rPr
        except AttributeError:
            return
        ea = rPr.find(qn("a:ea"))
        if ea is None:
            ea = rPr.makeelement(qn("a:ea"), {})
            latin = rPr.find(qn("a:latin"))
            if latin is not None:
                latin.addnext(ea)
            else:
                rPr.append(ea)
        ea.set("typeface", EA_FONT_NAME)

    @staticmethod
    def _set_background(slide, color: str) -> None:
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = PPTExporter._rgb(color)

    @staticmethod
    def _rgb(value: str) -> RGBColor:
        return RGBColor.from_string(value.lstrip("#").upper())

    @staticmethod
    def _blend(color: str, toward: str, ratio: float) -> str:
        """把 color 按 ratio 比例混向 toward，用于纯形状的浅色装饰（不用透明度）。"""
        source = color.lstrip("#")
        target = toward.lstrip("#")
        channels = []
        for i in (0, 2, 4):
            base = int(source[i:i + 2], 16)
            other = int(target[i:i + 2], 16)
            channels.append(max(0, min(255, round(base * (1 - ratio) + other * ratio))))
        return "{:02X}{:02X}{:02X}".format(*channels)
