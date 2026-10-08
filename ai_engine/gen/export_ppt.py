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
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

try:  # 老版本 python-pptx 没有 dash_style：环形的辅助椭圆退化成实线，仍读得懂
    from pptx.enum.dml import MSO_LINE_DASH_STYLE
except ImportError:  # pragma: no cover
    MSO_LINE_DASH_STYLE = None

from .page_spec import (
    MAX_FIGURE_ITEMS,
    ROLE_SECONDARY,
    ROLE_TEACHER,
    build_page_spec,
    resolve_export_key_points,
)
from .deck_structure import TOC_MIN_CONTENT_NODES, expand_deck_pages
from .presentation import presentation_from_nodes, presentation_to_theme
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

# ── 内容可视化 ──
# 原先这里的流程/数值特征检测（_FLOW_KEYWORDS / _PERCENT_RE）已上移到
# gen/teaching_plan.py 的启发式兜底。导出侧不再自己"看正文猜图示"：表达形式由
# 规划器决定一次，导出只负责把 page_spec 给出的 figure 画出来。

# ── 内容页版式（英寸）──
# 数字取自 gen/templates/layouts/content_left_right.json。预览与导出显示的是
# "同一页"，摆版就不能各写各的：核心要点在左栏、图示与正文上下分居右栏。
# 改版式 JSON 时这几个常量要一起改。
_LAYOUT_PANEL_TOP = 1.42          # 右栏顶端，也是整页内容区的顶
_LAYOUT_PANEL_FULL_H = 5.35       # 内容区总高（左栏与"无图示"的右栏）
_LAYOUT_LEFT_PANEL = (0.72, 3.60)  # 左栏 (x, w)；高同 _LAYOUT_PANEL_FULL_H
_LAYOUT_RIGHT_COLUMN = (4.52, 8.08)       # 右栏 (x, w)
# 没有核心要点时左栏整栏抹掉，右栏左移并撑满：4.52-3.8=0.72，8.08+3.8=11.88。
# 与 svg_renderer._widen_right_column 是同一笔账，改一处必须改两处。
_LAYOUT_RIGHT_COLUMN_WIDE = (0.72, 11.88)
_LAYOUT_FIGURE_PANEL_H = 2.45     # 右栏上半（图示面板）
_LAYOUT_BODY_PANEL = (4.01, 2.76)  # 右栏下半 (y, h)；无图示时不存在
# 图示作画区：figure_region 相对 figure_panel 内缩 (0.14, 0.10)，再减掉渲染器的
# 区域留白 _REGION_PADDING（16px = 0.167in）—— 预览的图示实际就画在这个框里。
_LAYOUT_FIGURE_OFFSET = (0.14 + 0.167, 0.10 + 0.167)
_LAYOUT_FIGURE_SHRINK = (0.28 + 0.333, 0.20 + 0.167)

#: 面板圆角（英寸）。预览的圆角是**固定 8px**（svg_renderer._render_rounded_rect 的
#: rx="8"），与面板多大无关；而 PowerPoint 的 ROUNDED_RECTANGLE 默认取短边的 1/6 ——
#: 3.6in 宽的左栏会圆到 0.6in，观感从"卡片"变成"枕头"，两边一眼就能看出不是同一个东西。
_PANEL_RADIUS = 8.0 / 96.0

#: 核心要点卡片的纵向内边距与卡片间距（英寸）。预览是 padding 7px、卡片间 gap 10px
#: （preview.py 的 .svg-block-secondary .key-points li 与 .key-points 的 grid gap）。
_POINT_CARD_PAD = 7.0 / 96.0
_POINT_CARD_GAP = 10.0 / 96.0

#: 正文面板的填充比例。排版模型按 1.35 × 字号算行高，而 PowerPoint 用字体自身的
#: 行距（中文 Office 上略高于此），真按 100% 撑满，最后一行会压到面板下沿。留 3%
#: 的余量：条目高度多在 0.38in 上下，这点余量基本不会把谁挤到下一页，却能让最后
#: 一行离边框还有一线呼吸。
_BODY_FILL = 0.97


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
    """合并 key_points/core_points，去重但不丢弃任一来源。

    口径统一到 `page_spec.resolve_export_key_points`（预览侧同一函数），两端不再
    各判一次"什么算要点"。但必须先过 `_as_mapping`：导出侧的调用方允许传 Pydantic
    节点对象，而 page_spec 的实现只认 dict，直接转发会让对象入参静默变成空列表。
    """
    return resolve_export_key_points(_as_mapping(node))


@dataclass
class ExportPPTConfig:
    """PPTX 导出配置。"""
    template_dir: str = ""
    default_template: str = "default"
    output_dir: str = "data/exports"
    # M3：默认结构 = 封面 / 目录（内容节点数超阈值时）/ 总结页。
    # 注入由 deck_structure.expand_deck_pages 在装配层完成（预览端同源调用），
    # 教师编辑的大纲不受污染。
    include_auto_cover: bool = True
    include_auto_toc: bool = True       # 内容节点数超阈值时自动插入目录页（条目=节点标题）
    include_auto_summary: bool = True   # 末节点非 summary 时自动追加"本节小结"
    include_closing_slide: bool = True  # 末节点为 summary 时追加"感谢聆听"结束页
    # 目录页阈值：内容节点数超过该值才加目录
    toc_min_content_nodes: int = TOC_MIN_CONTENT_NODES


class PPTExporter:
    """将标准化教学节点导出为专业、可编辑的 16:9 PPTX。"""

    def __init__(self, config: ExportPPTConfig | None = None):
        self.config = config or ExportPPTConfig()
        # 构造期的兜底主题，_render 会按节点的样式层重算
        self._theme = get_theme(self.config.default_template)
        self._panel_shape = MSO_SHAPE.ROUNDED_RECTANGLE

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
        prs = self._create_presentation(template_id)
        normalized = [_as_mapping(node) for node in (nodes or [])]
        # 样式层与预览同源，都读节点 metadata.presentation。取润色前的节点做判定，
        # 避免润色参与样式决策。取值顺序与预览一致：显式 palette → 模板自带 palette
        # → 默认调色板 classic（见 presentation.presentation_to_theme）。
        presentation, explicit_keys = presentation_from_nodes(normalized)
        self._theme, _ = presentation_to_theme(
            presentation, explicit_keys, template_id or self.config.default_template)
        # 面板永远是圆角：预览的版式面板写的都是 rounded_rect（rx=8），与用户选了
        # 哪套调色板无关。以前这里按"样式层是否启用"切成方角 —— 那是导出侧自己的
        # "瑞士风方角"设计语言，预览里并没有，于是选了样式反而更像不了。
        self._panel_shape = MSO_SHAPE.ROUNDED_RECTANGLE
        # 导出前自动润色内容 + 全量质量检查
        from .polish import polish_nodes
        from .quality_checker import run_full_check
        normalized = polish_nodes(normalized)
        check_result = run_full_check(normalized)
        warnings = check_result.get('warnings', [])
        if warnings:
            print(f'[PPT导出] 质量检查警告: {warnings}')
        # M3 默认结构：封面 / 目录（内容节点超阈值时）/ 总结 —— 与预览端共用同一扩展器，
        # 在润色之后注入，合成页不参与内容润色。
        expanded = expand_deck_pages(
            normalized,
            course_name,
            # 兜底"导出永不空白"：节点为空时即使关掉封面开关也注入封面
            include_cover=self.config.include_auto_cover or not normalized,
            include_toc=self.config.include_auto_toc,
            include_summary=self.config.include_auto_summary,
            toc_min_content_nodes=self.config.toc_min_content_nodes,
        )
        for index, node in enumerate(expanded, start=1):
            self._get_slide_handler(resolve_node_type(node))(prs, node, index)
        if self.config.include_closing_slide and expanded \
                and resolve_node_type(expanded[-1]) == "summary":
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
            self._add_page_title(slide, title)
            start = chunk_index * 8
            for offset, text in enumerate(chunk):
                row, col = divmod(offset, 2)
                x, y = col_x[col], 1.6 + row * (card_h + gap_y)
                self._add_shape(slide, self._panel_shape, x, y, card_w, card_h,
                                self._theme.surface, line=self._theme.muted)
                self._add_shape(slide, MSO_SHAPE.OVAL, x + 0.2, y + 0.26, 0.5, 0.5,
                                self._theme.accent)
                number = start + offset + 1
                self._add_textbox(slide, f"{number:02d}", x + 0.2, y + 0.34, 0.5, 0.36,
                                  font_size=14, color=self._theme.inverse, bold=True,
                                  align=PP_ALIGN.CENTER)
                self._add_textbox(slide, text, x + 0.88, y + 0.25, card_w - 1.1, 0.56,
                                  font_size=self._fit_font(text, 14, 19, 15),
                                  color=self._theme.text, valign=MSO_ANCHOR.MIDDLE,
                                  fit_to_shape=True)

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
            self._add_page_title(slide, title, index)
            y = 1.55
            for offset, text in enumerate(chunk, start=chunk_index * 7 + 1):
                self._add_textbox(slide, f"{offset:02d}", 0.95, y, 0.7, 0.48,
                                  font_size=19, color=self._theme.accent, bold=True)
                self._add_textbox(slide, text, 1.85, y - 0.02, 10.25, 0.58,
                                  font_size=self._fit_font(text, 19, 25, 36), color=self._theme.text,
                                  fit_to_shape=True)
                self._add_shape(slide, MSO_SHAPE.RECTANGLE, 1.85, y + 0.54, 9.95, 0.012, self._theme.muted)
                y += 0.77

    def _add_content_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        """内容页：与预览的 content_left_right 同版式 —— 左栏核心要点，右栏图示 + 正文。

        改动前这里是"单栏大面板 + 每行带「正文｜」「结论｜」标签"。那套排版读起来正
        是用户说的"演讲稿提纲卡片"：预览里正文就是正文、结论是一句大字，行首没有任
        何字段名。所以这里按预览的双栏重排，并把结论单独画成大字段落
        （见 _add_body_panel）。

        正文与要点分走两条区块流，与预览一致：key_points 在 page_spec 里被降为
        ROLE_SECONDARY 进左栏，其余进右栏。
        """
        spec = build_page_spec(node, index)
        body_items = self._main_items(node, spec)
        side_points = self._side_points(spec)
        if not body_items:
            body_items = [("text", "暂无正文内容", False)]
        figure = self._spec_figure(spec)

        col_x, col_w = _LAYOUT_RIGHT_COLUMN if side_points else _LAYOUT_RIGHT_COLUMN_WIDE
        first_body = _LAYOUT_BODY_PANEL if figure else (_LAYOUT_PANEL_TOP, _LAYOUT_PANEL_FULL_H)

        # 分页容量按正文面板的**实际**高度算，并且与渲染共用 _body_item_box 一把
        # 尺子。以前这里是两套算法：分页按"字符数 ÷ 每行字数 + 1"估权重，渲染按
        # "行数 × 行高 + 段距"排。刻度对不上 —— 分页给每个条目多算了段距（按一整行
        # 0.28in 计，实际只有 0.1in），又给结论块少算了（按 15pt/36 字估，实际是
        # 22pt/23 字）。于是面板里明明还剩一行的地方，那行就被推到了下一页。
        body_chunks = self._chunk_body_items(body_items, first_body[1] - 0.71, col_w - 0.58)
        point_chunks = self._chunk_weighted(side_points, 13, 34)
        page_count = max(len(body_chunks), len(point_chunks), 1)

        title = str(node.get("title") or f"第 {index} 页")
        for page_index in range(page_count):
            slide = self._blank_slide(prs, index)
            page_title = title + (f"（续 {page_index + 1}）" if page_index else "")
            self._add_page_title(slide, page_title, index)

            if side_points:
                # 续页重复核心要点：预览一页只画一次，而续页是本页正文的延续，
                # 让学生一直看得见这页在讲哪几个要点。
                chunk = point_chunks[min(page_index, len(point_chunks) - 1)]
                left_x, left_w = _LAYOUT_LEFT_PANEL
                self._add_panel(slide, "核心要点", chunk, left_x, _LAYOUT_PANEL_TOP,
                                left_w, _LAYOUT_PANEL_FULL_H, cards=True)

            first = page_index == 0
            if figure and first:
                # 图示只上第一页；续页腾出的整块右栏还给正文（同预览的
                # _merge_right_column：缺一样就按缺了的样子重算，不留空面板）
                self._add_shape(slide, self._panel_shape, col_x, _LAYOUT_PANEL_TOP,
                                col_w, _LAYOUT_FIGURE_PANEL_H,
                                self._theme.surface, line=self._theme.muted)
                self._render_visualization(
                    slide, figure,
                    col_x + _LAYOUT_FIGURE_OFFSET[0],
                    _LAYOUT_PANEL_TOP + _LAYOUT_FIGURE_OFFSET[1],
                    col_w - _LAYOUT_FIGURE_SHRINK[0],
                    _LAYOUT_FIGURE_PANEL_H - _LAYOUT_FIGURE_SHRINK[1],
                )
                panel_y, panel_h = first_body
            else:
                panel_y, panel_h = _LAYOUT_PANEL_TOP, _LAYOUT_PANEL_FULL_H
            chunk = body_chunks[page_index] if page_index < len(body_chunks) else []
            self._add_body_panel(slide, chunk, col_x, panel_y, col_w, panel_h)

    # ── 内容可视化：由 page_spec 的 figure 区块驱动 ──
    #
    # 导出侧不再"看正文猜图示"。原先的 _detect_flow_steps / _detect_comparison_bars
    # 已上移进 teaching_plan 的启发式兜底，表达形式由规划器决定**一次**；这里只负责
    # 把归一后的六种 kind 画出来。全部使用原生形状与文本框，不引入 PICTURE
    # （契约 #1：导出的 .pptx 必须保持可编辑）。

    @staticmethod
    def _spec_figure(spec) -> dict[str, Any] | None:
        """取 page_spec 的图示区块；没有就返回 None（版面自然少一块）。

        预览侧把 figure 当独立区块单独取值（svg_renderer 不按 role 过滤它），导出侧
        照做 —— 不在导出阶段再判一次"这页要不要图"。
        """
        for block in spec.blocks:
            if block.kind == "figure" and block.figure:
                return block.figure
        return None

    @staticmethod
    def _fig_items(figure: dict[str, Any]) -> list[str]:
        return [str(v).strip() for v in (figure.get("items") or []) if str(v).strip()]

    def _render_visualization(self, slide, figure: dict[str, Any],
                              x: float, y: float, w: float, h: float) -> None:
        """在 (x, y, w, h) 框内画图示 —— 几何与配色对齐预览的 diagrams.py。

        六个渲染器收同一个框：预览把图示当"一块固定大小的画布"，各 kind 在框内按
        比例自己摆；导出侧照做，两端的图才是同一张，而不是各按各的内容撑高。
        """
        renderer = {
            "flow": self._render_flow,
            "chart": self._render_chart,
            "compare": self._render_compare,
            "matrix": self._render_matrix,
            "cycle": self._render_cycle,
            "hierarchy": self._render_hierarchy,
        }.get(str(figure.get("kind") or "").strip().lower())
        # normalize_figure 已经裁过一遍，未登记的 kind 不该走到这里；真到了也只是
        # 不画图 —— 绝不能让一块图示把整页导出带崩。
        if renderer is not None:
            renderer(slide, figure, x, y, w, h)

    def _add_connector(self, slide, x1: float, y1: float, x2: float, y2: float,
                       color: str | None = None) -> None:
        """两点之间的细线，表示结构关系。

        用**旋转的细矩形**而不是 add_connector：复用 _add_shape 的填充/描边处理，
        不依赖 python-pptx 的连接符 API，也不碰 a:tailEnd 的 XML。矩形放在两点
        中点，PowerPoint 绕中心旋转，正好落成这条线段。
        """
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= 0.01:
            return
        thickness = 0.03
        line = self._add_shape(
            slide, MSO_SHAPE.RECTANGLE,
            (x1 + x2) / 2 - length / 2, (y1 + y2) / 2 - thickness / 2,
            length, thickness, color or self._theme.muted,
        )
        line.rotation = math.degrees(math.atan2(y2 - y1, x2 - x1))

    def _fig_label_size(self, text: str, box_w: float, maximum: int) -> int:
        """图示标签字号：预览把字号写死在 SVG 里，导出侧按框宽折算。

        SVG 的 px 与幻灯片英寸是 96:1，故预览的 13px ≈ 9.75pt。中文字宽约等于字号，
        一行放不下就缩，缩到 8pt 为止 —— 再小投出来就看不见了。
        """
        chars = max(len(str(text or "")), 1)
        per_line = max(4.0, box_w * 72.0 / maximum)
        lines = math.ceil(chars / per_line)
        return max(8, min(maximum, maximum - max(0, lines - 1) * 2))

    def _add_arrow_head(self, slide, tip_x: float, cy: float, color: str,
                        size: float = 0.13) -> None:
        """三角箭头（朝右）。等腰三角形默认朝上，转 90° 让顶点指向 +x。"""
        head = self._add_shape(slide, MSO_SHAPE.ISOSCELES_TRIANGLE,
                               tip_x - size, cy - size / 2, size, size, color)
        head.rotation = 90

    def _render_flow(self, slide, figure: dict[str, Any],
                     x: float, y: float, w: float, h: float) -> None:
        """横向流程条：圆角步骤框 + 序号徽标 + 实心三角箭头。

        与 diagrams._render_flow 同一套账：间距 24px=0.25in，框高
        min(h, max(76px, min(124px, h*0.66)))，整条在框内垂直居中；徽标是 primary
        实心圆，箭头是 accent 实心三角 —— 两端配色因此逐项对得上。
        """
        items = self._fig_items(figure)
        if not items:
            return
        count, gap = len(items), 0.25
        box_w = max(0.42, (w - gap * (count - 1)) / count)
        box_h = min(h, max(0.79, min(1.29, h * 0.66)))
        box_y = y + (h - box_h) / 2
        badge_r = 0.115
        for i, step in enumerate(items):
            bx = x + i * (box_w + gap)
            cx = bx + box_w / 2
            self._add_shape(slide, self._panel_shape, bx, box_y, box_w, box_h,
                            self._theme.surface, line=self._theme.muted)
            self._add_shape(slide, MSO_SHAPE.OVAL, cx - badge_r, box_y + 0.094,
                            badge_r * 2, badge_r * 2, self._theme.primary)
            self._add_textbox(slide, str(i + 1), cx - badge_r, box_y + 0.094,
                              badge_r * 2, badge_r * 2, font_size=9,
                              color=self._theme.inverse, bold=True,
                              align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
            label_y = box_y + badge_r * 2 + 0.167
            self._add_textbox(slide, step, bx + 0.08, label_y, box_w - 0.16,
                              box_h - (label_y - box_y) - 0.06,
                              font_size=self._fig_label_size(step, box_w - 0.16, 10),
                              color=self._theme.text, align=PP_ALIGN.CENTER,
                              valign=MSO_ANCHOR.MIDDLE)
            if i < count - 1:
                cy = box_y + box_h / 2
                self._add_connector(slide, bx + box_w + 0.05, cy,
                                    bx + box_w + gap - 0.05, cy, self._theme.accent)
                self._add_arrow_head(slide, bx + box_w + gap - 0.02, cy, self._theme.accent)

    def _render_chart(self, slide, figure: dict[str, Any],
                      x: float, y: float, w: float, h: float) -> None:
        """横向条形图：标签 | 轨道 | 实心条 | 数值。

        与 diagrams._render_chart 同一套账。轨道（空槽）不是装饰：画出轨道才能让
        "占比很小"和"数据缺失"看起来不一样 —— 只画实心条的话，一个 3% 和一条没
        数据的行会长得一模一样。条是 primary、轨道是 surface，配色也与预览一致。

        数值不带单位：chart 的数值可以是人数、秒数、倍数，规划器给的是数字，
        导出侧替它假设成百分比在多数页面上直接是错的。
        """
        series = [(str(s.get("label") or "").strip(), float(s.get("value") or 0))
                  for s in (figure.get("series") or [])
                  if isinstance(s, dict) and str(s.get("label") or "").strip()]
        if not series:
            return
        row_h = h / len(series)
        bar_h = min(0.271, max(0.104, row_h * 0.58))
        value_w = 0.625
        # 标签列吃掉三成宽、但不小于 0.75in，且给条形与数值各留出至少 0.625in
        label_w = min(max(0.75, w * 0.3), max(0.625, w - value_w * 2))
        bar_x = label_w + 0.104
        bar_max = max(0.25, w - bar_x - value_w)
        peak = max((abs(value) for _, value in series), default=0.0)
        for i, (label, value) in enumerate(series):
            cy = y + i * row_h + row_h / 2
            self._add_textbox(slide, label, x, y + i * row_h, label_w, row_h,
                              font_size=self._fig_label_size(label, label_w, 9),
                              color=self._theme.text, align=PP_ALIGN.RIGHT,
                              valign=MSO_ANCHOR.MIDDLE)
            self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x + bar_x,
                            cy - bar_h / 2, bar_max, bar_h, self._theme.surface)
            width = bar_max * (abs(value) / peak if peak else 0.0)
            if width > 0.01:
                self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x + bar_x,
                                cy - bar_h / 2, width, bar_h, self._theme.primary)
            self._add_textbox(slide, f"{value:g}", x + bar_x + bar_max + 0.06,
                              cy - row_h / 2, value_w, row_h, font_size=9,
                              color=self._theme.text, bold=True,
                              valign=MSO_ANCHOR.MIDDLE)

    def _render_compare(self, slide, figure: dict[str, Any],
                        x: float, y: float, w: float, h: float) -> None:
        """左右对比：两个面板 + 顶部标题条（primary / secondary 区分两方）。

        与 diagrams._render_compare 同一套账：间距 18px=0.19in，标题条 36px=0.375in，
        条目行高 min(40px, 剩余高度/条数)，每条前面一枚 token 色小圆点 —— 左栏的点
        是 primary、右栏是 secondary，与标题条同色，两侧因此一眼分得开。
        """
        gap, head_h = 0.19, 0.375
        col_w = max(0.63, (w - gap) / 2)
        for i, key in enumerate(("left", "right")):
            side = figure.get(key) if isinstance(figure.get(key), dict) else {}
            items = [str(v).strip() for v in (side.get("items") or []) if str(v).strip()]
            items = items[:MAX_FIGURE_ITEMS]
            title = str(side.get("title") or "").strip() or ("左" if i == 0 else "右")
            token = self._theme.primary if i == 0 else self._theme.secondary
            cx = x + i * (col_w + gap)
            self._add_shape(slide, self._panel_shape, cx, y, col_w, h,
                            self._theme.surface, line=self._theme.muted)
            top = y
            if title:
                self._add_shape(slide, MSO_SHAPE.RECTANGLE, cx, y, col_w, head_h, token)
                self._add_textbox(slide, title, cx + 0.1, y, col_w - 0.2, head_h,
                                  font_size=self._fig_label_size(title, col_w - 0.2, 11),
                                  color=self._theme.inverse, bold=True,
                                  align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
                top = y + head_h
            avail = y + h - top - 0.167
            if not items or avail <= 0:
                continue
            row_h = min(0.42, avail / len(items))
            for j, item in enumerate(items):
                row_y = top + 0.083 + j * row_h
                self._add_shape(slide, MSO_SHAPE.OVAL, cx + 0.151,
                                row_y + row_h / 2 - 0.037, 0.073, 0.073, token)
                self._add_textbox(slide, item, cx + 0.313, row_y, col_w - 0.44, row_h,
                                  font_size=self._fig_label_size(item, col_w - 0.44, 10),
                                  color=self._theme.text, valign=MSO_ANCHOR.MIDDLE)

    def _render_matrix(self, slide, figure: dict[str, Any],
                       x: float, y: float, w: float, h: float) -> None:
        """对比表：表头行（primary 底 + inverse 字）+ 网格行（隔行 surface/background）。

        与 diagrams._render_matrix 同一套账：表头高 min(40px, max(26px, h*0.22))，
        行高把剩余高度均分。首列是行头（被比较对象的名称）—— 加粗、左对齐；其余
        单元格居中。行高不随内容伸缩：表格的意义就在于对齐，让它随内容长高反而
        失去了可比性。
        """
        columns = [str(c).strip() for c in (figure.get("columns") or [])]
        rows = [[str(c).strip() for c in row] for row in (figure.get("rows") or [])]
        if not columns or not rows:
            return
        head_h = min(0.417, max(0.271, h * 0.22))
        row_h = max(0.1875, (h - head_h) / len(rows))
        col_w = w / len(columns)
        pad = min(0.125, col_w * 0.12)
        for j, name in enumerate(columns):
            cx = x + j * col_w
            self._add_shape(slide, MSO_SHAPE.RECTANGLE, cx, y, col_w, head_h,
                            self._theme.primary)
            self._add_textbox(slide, name, cx + pad, y, col_w - pad * 2, head_h,
                              font_size=self._fig_label_size(name, col_w - pad * 2, 10),
                              color=self._theme.inverse, bold=True,
                              align=PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER,
                              valign=MSO_ANCHOR.MIDDLE)
        for i, row in enumerate(rows):
            row_y = y + head_h + i * row_h
            for j, cell in enumerate(row):
                cx = x + j * col_w
                self._add_shape(slide, MSO_SHAPE.RECTANGLE, cx, row_y, col_w, row_h,
                                self._theme.surface if i % 2 == 0 else self._theme.background,
                                line=self._theme.muted)
                if not cell:
                    continue
                self._add_textbox(slide, cell, cx + pad, row_y, col_w - pad * 2, row_h,
                                  font_size=self._fig_label_size(cell, col_w - pad * 2, 10),
                                  color=self._theme.text, bold=(j == 0),
                                  align=PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER,
                                  valign=MSO_ANCHOR.MIDDLE)

    def _render_cycle(self, slide, figure: dict[str, Any],
                      x: float, y: float, w: float, h: float) -> None:
        """环形循环：节点沿椭圆均匀分布 + 虚线椭圆 + 切线方向的实心箭头。

        与 diagrams._render_cycle 同一套账。少于 3 个节点时不画环 —— 两点"循环"在
        几何上就是一条来回的直线，硬摆成圆环只会挤成一团，退化成流程条反而读得懂。
        """
        items = self._fig_items(figure)
        if len(items) < 3:
            self._render_flow(slide, figure, x, y, w, h)
            return
        n = len(items)
        cx0, cy0 = x + w / 2, y + h / 2
        box_w = min(max(0.75, w / (n + 1.4)), 1.77)
        box_h = min(0.5625, max(0.396, h * 0.32))
        rx = max(box_w / 2 + 0.042, w / 2 - box_w / 2 - 0.125)
        ry = max(box_h / 2 + 0.042, h / 2 - box_h / 2 - 0.104)

        ring = self._add_shape(slide, MSO_SHAPE.OVAL, cx0 - rx, cy0 - ry, rx * 2, ry * 2,
                               self._theme.background)
        ring.fill.background()
        ring.line.color.rgb = self._rgb(self._theme.muted)
        ring.line.width = Pt(1.5)
        if MSO_LINE_DASH_STYLE is not None:
            ring.line.dash_style = MSO_LINE_DASH_STYLE.DASH

        for i, item in enumerate(items):
            angle = -math.pi / 2 + 2 * math.pi * i / n
            bx = cx0 + rx * math.cos(angle) - box_w / 2
            by = cy0 + ry * math.sin(angle) - box_h / 2
            self._add_shape(slide, self._panel_shape, bx, by, box_w, box_h,
                            self._theme.surface, line=self._theme.muted)
            self._add_textbox(slide, item, bx + 0.08, by, box_w - 0.16, box_h,
                              font_size=self._fig_label_size(item, box_w - 0.16, 9),
                              color=self._theme.text, align=PP_ALIGN.CENTER,
                              valign=MSO_ANCHOR.MIDDLE)

        # 箭头画在相邻两块之间的中间角度上，沿椭圆切线指向下一个节点
        for i in range(n):
            mid = -math.pi / 2 + 2 * math.pi * (i + 0.5) / n
            ax, ay = cx0 + rx * math.cos(mid), cy0 + ry * math.sin(mid)
            tx, ty = -rx * math.sin(mid), ry * math.cos(mid)
            norm = math.hypot(tx, ty) or 1.0
            tx, ty = tx / norm, ty / norm
            size = 0.115
            head = self._add_shape(slide, MSO_SHAPE.ISOSCELES_TRIANGLE,
                                   ax - size / 2, ay - size / 2, size, size,
                                   self._theme.accent)
            # 等腰三角形默认朝上（atan2 里的 -90°），故再 +90° 即转到切线方向
            head.rotation = math.degrees(math.atan2(ty, tx)) + 90

    def _render_hierarchy(self, slide, figure: dict[str, Any],
                          x: float, y: float, w: float, h: float) -> None:
        """层级结构：父块居中（primary 底 + inverse 字），子块排成一行（surface）。

        与 diagrams._render_hierarchy 同一套账：父块底部一条竖线接到中间的总线，
        总线再分叉到各子块 —— 总线画在父子之间的中间高度，不是为了好看，是为了
        让"哪些子块属于同一个父"一眼看得出来。只有一项时当一个居中主块画，
        不硬凑成层级。
        """
        items = self._fig_items(figure)
        if not items:
            return
        parent, children = items[0], items[1:1 + MAX_FIGURE_ITEMS]
        parent_h = min(0.479, max(0.333, h * 0.3))
        if not children:
            parent_w = min(w * 0.7, 3.33)
            px, py = x + (w - parent_w) / 2, y + (h - parent_h) / 2
            self._add_shape(slide, self._panel_shape, px, py, parent_w, parent_h,
                            self._theme.primary)
            self._add_textbox(slide, parent, px + 0.1, py, parent_w - 0.2, parent_h,
                              font_size=self._fig_label_size(parent, parent_w - 0.2, 11),
                              color=self._theme.inverse, bold=True,
                              align=PP_ALIGN.CENTER, valign=MSO_ANCHOR.MIDDLE)
            return

        gap = 0.167
        child_w = max(0.5, (w - gap * (len(children) - 1)) / len(children))
        child_h = min(0.79, max(0.479, h * 0.42))
        parent_w = min(w * 0.46, 2.92)
        parent_x = x + (w - parent_w) / 2
        child_y = y + h - child_h
        bus_y = y + (parent_h + (child_y - y)) / 2
        total_w = len(children) * child_w + (len(children) - 1) * gap
        centers = [x + (w - total_w) / 2 + j * (child_w + gap) + child_w / 2
                   for j in range(len(children))]

        # 先连线后画块：线被块盖住，只露出中间那一段
        parent_cx = parent_x + parent_w / 2
        self._add_connector(slide, parent_cx, y + parent_h, parent_cx, bus_y,
                            self._theme.muted)
        if len(centers) > 1:
            self._add_connector(slide, centers[0], bus_y, centers[-1], bus_y,
                                self._theme.muted)
        for cx in centers:
            self._add_connector(slide, cx, bus_y, cx, child_y, self._theme.muted)

        self._add_shape(slide, self._panel_shape, parent_x, y, parent_w, parent_h,
                        self._theme.primary)
        self._add_textbox(slide, parent, parent_x + 0.1, y, parent_w - 0.2, parent_h,
                          font_size=self._fig_label_size(parent, parent_w - 0.2, 11),
                          color=self._theme.inverse, bold=True, align=PP_ALIGN.CENTER,
                          valign=MSO_ANCHOR.MIDDLE)
        for cx, child in zip(centers, children):
            bx = cx - child_w / 2
            self._add_shape(slide, self._panel_shape, bx, child_y, child_w, child_h,
                            self._theme.surface, line=self._theme.muted)
            self._add_textbox(slide, child, bx + 0.08, child_y, child_w - 0.16, child_h,
                              font_size=self._fig_label_size(child, child_w - 0.16, 9),
                              color=self._theme.text, align=PP_ALIGN.CENTER,
                              valign=MSO_ANCHOR.MIDDLE)

    def _add_two_column_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        """固定双栏页：左栏核心要点，右栏讲授分段或内容展开。"""
        key_items = [("要点", point, True) for point in resolve_key_points(node)]
        if not key_items:
            summary = str(node.get("summary") or "暂无核心要点").strip()
            key_items = [("摘要", summary, False)]

        body_items: list[tuple[str, str, bool]] = []
        value = node.get("content")
        if isinstance(value, str) and value.strip():
            # 标签留空：预览里正文就是正文，没有「正文｜」这种行首（同 _add_body_panel）
            body_items.append(("", value.strip(), False))
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
            self._add_page_title(slide, page_title)
            left_chunk = left_chunks[page_index] if page_index < len(left_chunks) else []
            right_chunk = right_chunks[page_index] if page_index < len(right_chunks) else []
            self._add_panel(slide, "核心要点", left_chunk, 0.72, 1.42, 5.58, 5.35,
                            cards=True)
            self._add_panel(slide, right_heading, right_chunk, 6.72, 1.42, 5.88, 5.35)

    def _add_quiz_slide(self, prs: Presentation, node: dict[str, Any], index: int) -> None:
        items = self._quiz_question_items(node)
        chunks = self._chunk_quiz_items(items)
        number = 0
        for chunk_index, chunk in enumerate(chunks):
            slide = self._blank_slide(prs, index)
            title = str(node.get("title") or "课堂互动") + ("（续）" if chunk_index else "")
            self._add_page_title(slide, title, index)
            y = 1.55
            for question, options, answer in chunk:
                number += 1
                # 序号圆点取 primary：预览的 .quiz-slide .questions .q-item::before
                # 用的是 var(--preview-accent)，而预览的 accent 就是调色板强调色，
                # 也就是 theme_from_palette 里的 primary。
                self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE,
                                0.85, y, 0.58, 0.58, self._theme.primary)
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
            self._add_page_title(slide, title, index)
            y = 1.62
            for offset, text in enumerate(chunk):
                number = chunk_index * 5 + offset + 1
                self._add_shape(slide, self._panel_shape, 0.72, y, 11.88, 0.78,
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
                self._add_shape(slide, self._panel_shape, 0.72, 6.2, 11.88, 0.6,
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

    def _main_items(self, node: dict[str, Any],
                    spec: Any | None = None) -> list[tuple[str, str, bool]]:
        """右栏正文条目 —— 从 page_spec 的区块读，导出侧不再自己挑字段。

        第一项是区块**种类**而不是人看的标签（见 _add_body_panel）：正文排在右栏，
        要点在左栏由 _side_points 收走，两边各读各的区块。

        取 ``role != ROLE_TEACHER`` 的区块：讲稿与分段是 ROLE_TEACHER，本来就不上
        幻灯片（``_segment_items`` 也返回 []），在这里跳过即可，不需要别处再过滤。
        """
        spec = spec if spec is not None else build_page_spec(node)
        items: list[tuple[str, str, bool]] = []
        for block in spec.blocks:
            if block.role == ROLE_TEACHER:
                continue
            if block.kind == "text":
                items.extend(("text", text, False) for text in block.paragraphs if text)
            elif block.kind == "conclusion":
                items.extend(("conclusion", text, False) for text in block.paragraphs if text)
            elif block.kind == "details":
                for entry in block.items:
                    # point_details 是 [{point, detail}]；脏条目由 page_spec 归一过了
                    point = str(entry.get("point") or "").strip()
                    detail = str(entry.get("detail") or "").strip()
                    text = f"{point}：{detail}" if point and detail else (point or detail)
                    if text:
                        items.append(("point", text, True))
            elif block.kind == "bullets":
                # 有正文时 bullets 已被降为 SECONDARY（进左栏），这里只接 PRIMARY 的
                items.extend(("point", str(point).strip(), True)
                             for point in block.items if str(point).strip())
        if items:
            return items
        # 兜底：page_spec 一个区块都没吐出条目时（老课件、字段形状出乎意料），
        # 仍按改动前的口径直读节点字段，宁可重复也绝不出现"空白内容页"。
        for field in ("content", "summary"):
            value = node.get(field)
            if isinstance(value, str) and value.strip():
                items.append(("text", value.strip(), False))
            elif isinstance(value, list):
                for entry in value:
                    text = str(entry or "").strip()
                    if text:
                        items.append(("point", text, True))
        for point in resolve_key_points(node):
            items.append(("point", point, True))
        return items

    @staticmethod
    def _side_points(spec: Any) -> list[tuple[str, str, bool]]:
        """左栏核心要点 —— page_spec 判为 ROLE_SECONDARY 的要点区块。

        节点同时有正文与 key_points 时，page_spec 会把 bullets 降为 SECONDARY
        （"正文讲完再补要点"的从属关系）。导出侧若只认 PRIMARY，这些要点会在 .pptx
        里整块消失 —— 预览里还在、error 列表却是空的，教师只会觉得导出少了东西。
        契约 #2 正是拿 n3 这个形状断言的。

        标签留空：预览的左栏就是一列圆点，没有「要点｜」这样的前缀。
        """
        points: list[tuple[str, str, bool]] = []
        for block in spec.blocks:
            if block.role != ROLE_SECONDARY or block.kind != "bullets":
                continue
            points.extend(("", str(point).strip(), True)
                          for point in block.items if str(point).strip())
        return points

    def _segment_items(self, node: dict[str, Any]) -> list[tuple[str, str, bool]]:
        """按需求：导出PPT不展示讲稿分段内容，仅保留核心要点。

        讲稿只进预览的折叠区（契约 #3 双向断言）。这是**唯一**决定讲稿不上幻灯片的
        地方 —— _add_content_slide 已经没有"讲授分段"面板了，要恢复得先改这里。
        """
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

    def _add_page_title(self, slide, title: str,
                        page_number: int | None = None) -> None:
        """顶部标题条：主题色底 + 标题 + 页码。

        几何与内容取自预览版式 content_left_right.json 的 title_bar(0,0,13.333,1.16)
        与 title_text(0.75,0.44,10.4,0.6, 24pt bold inverse)。

        这里以前还画两样预览**任何版式里都没有**的东西：标题条下的 0.05in 强调色带，
        以及左上角的 kicker（"CONTENT"/"AGENDA"/"SUMMARY"…）。全英文标签既没有来由，
        色带又抢在标题和正文之间 —— 学生看到的是导出独有的一层装饰。
        """
        self._add_shape(slide, MSO_SHAPE.RECTANGLE, 0, 0, 13.34, 1.16, self._theme.primary)
        self._add_textbox(slide, title, 0.75, 0.44, 10.4, 0.6,
                          font_size=self._fit_font(title, 24, 32, 22), color=self._theme.inverse,
                          bold=True)
        if page_number is not None:
            self._add_textbox(slide, f"{page_number:02d}", 12.1, 0.44, 0.9, 0.44,
                              font_size=14, color=self._theme.inverse, bold=True,
                              align=PP_ALIGN.RIGHT)

    def _add_panel(self, slide, heading: str, items: list[tuple[str, str, bool]],
                   x: float, y: float, width: float, height: float,
                   *, cards: bool = False) -> None:
        self._add_shape(slide, self._panel_shape, x, y, width, height,
                        self._theme.surface, line=self._theme.muted)
        self._add_textbox(slide, heading, x + 0.28, y + 0.18, width - 0.56, 0.36,
                          font_size=15, color=self._theme.secondary, bold=True)
        if cards:
            # 核心要点栏：预览把它画成一叠浅色小卡片，不是一列裸文本
            self._add_point_cards(slide, items, x + 0.27, y + 0.68,
                                  width - 0.54, height - 0.9)
            return
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

    def _add_point_cards(self, slide, items: list[tuple[str, str, bool]],
                         x: float, y: float, width: float, height: float) -> None:
        """核心要点：照预览的 `.content-slide .key-points li` 画成一叠浅色卡片。

        预览里每条要点是一块圆角浅底（白 → accent-soft 的渐变）+ 一道极淡描边 +
        「·」前缀（preview.py 的 .key-points li，再被 .content-slide 覆写底色）。
        导出原先是裸的「• 文本」——左栏两条并排看，根本不像同一页。
        """
        if not items or width <= 0 or height <= 0:
            return
        gap, pad = _POINT_CARD_GAP, _POINT_CARD_PAD
        size = self._points_font_size(items, width, height, gap, pad)
        per_line = max(6, int((width - 0.24) * 72 / size))

        texts = [f"· {text}" for _label, text, _bullet in items]
        heights = [
            max(1, math.ceil(len(text) / per_line)) * size * 1.35 / 72.0 + pad * 2
            for text in texts
        ]
        # 估算偏乐观时（长英文词、标点避头尾）整体压缩卡片高度，宁可挤一点也不让
        # 最后一张压到页脚上 —— 预览那边是 overflow:hidden，直接切掉更糟。
        slots = max(0.01, height - gap * (len(items) - 1))
        total = sum(heights)
        if total > slots:
            heights = [h * slots / total for h in heights]

        fill = self._blend("#FFFFFF", self._theme.surface, 0.55)
        line = self._blend(self._theme.background, self._theme.text, 0.07)
        cursor = y
        for text, card_h in zip(texts, heights):
            self._add_shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, cursor, width, card_h,
                            fill, line=line)
            self._add_textbox(slide, text, x + 0.12, cursor, width - 0.24, card_h,
                              font_size=size, color=self._theme.text,
                              valign=MSO_ANCHOR.MIDDLE)
            cursor += card_h + gap

    @staticmethod
    def _points_font_size(items: list[tuple[str, str, bool]], width: float,
                          height: float, gap: float, pad: float) -> int:
        """在「卡片数 × 每张行数」放得进面板高度的前提下取最大字号。"""
        usable = height - gap * (len(items) - 1) - pad * 2 * len(items)
        for size in (17, 16, 15, 14, 13, 12, 11):
            if usable <= 0:
                break
            per_line = max(6, int((width - 0.24) * 72 / size))
            lines = sum(max(1, math.ceil(len(text) / per_line)) for _l, text, _b in items)
            if lines * size * 1.35 / 72.0 <= usable:
                return size
        return 11

    # ── 正文面板：分页与渲染共用一把尺子 ──

    def _body_item_box(self, item: tuple[str, str, bool],
                       inner_w: float) -> tuple[float, float, int, str]:
        """一个正文条目渲染后的 (框高, 含段距的推进量, 字号, 实际文本)。

        分页（_chunk_body_items）问它要推进量，渲染（_add_body_panel）问它要框高 ——
        两处共用同一份排版算术，是"面板里还有地方、最后一行却被推到下一页"的修法。
        改这里的任何数字，分页与渲染会一起变，不会再分叉。
        """
        kind, text, _bullet = item
        if kind == "conclusion":
            # 高度跟着字号算：结论最长 60 字（page_spec.MAX_CONCLUSION_CHARS），
            # 写死一个框高会让长结论溢到面板外
            text_w = inner_w - 0.42
            size = self._fig_label_size(text, text_w, 22)
            lines = max(1, math.ceil(len(text) / max(6, int(text_w * 72 / size))))
            box_h = lines * size * 1.35 / 72.0 + 0.12
            return box_h, box_h + 0.08, size, text
        size = 15 if kind == "text" else 14
        body = text if kind == "text" else f"• {text}"
        # 一行放得下多少字：汉字宽约等于字号，故 cw*72/size
        lines = max(1, math.ceil(len(body) / max(8, int(inner_w * 72 / size))))
        line_h = lines * size * 1.35 / 72.0
        return line_h + 0.08, line_h + 0.1, size, body

    @staticmethod
    def _body_split_metrics(kind: str, inner_w: float) -> tuple[int, int]:
        """切分超长条目时用的 (字号, 每行字数)。

        结论的字号随长度收缩（_fig_label_size），这里按最大字号 22pt 估 —— 低估字数
        只会把一条切得偏碎，不会让某一条永远放不下一页。
        """
        if kind == "conclusion":
            size, text_w = 22, inner_w - 0.42
        else:
            size = 15 if kind == "text" else 14
            text_w = inner_w
        # "• " 前缀也占宽度，切分时一并扣掉
        prefix = 0 if kind in ("text", "conclusion") else 2
        return size, max(6, int(text_w * 72 / size) - prefix)

    def _chunk_body_items(self, items: list[tuple[str, str, bool]],
                          max_height: float, inner_w: float
                          ) -> list[list[tuple[str, str, bool]]]:
        """按渲染后的**实际高度**分页。

        超长条目先按句子切开（仍是 _split_text，续段完整保留原文，不会腰斩一句话），
        再逐条累加 _body_item_box 的推进量；放不下就翻页。容量就是渲染器可用的高度
        （面板高 - 0.71）乘 _BODY_FILL —— 分页算的就是渲染要画的高度，面板不会再
        "还剩一行却被推走"。
        """
        if not items or max_height <= 0 or inner_w <= 0:
            return []
        capacity = max_height * _BODY_FILL

        expanded: list[tuple[str, str, bool]] = []
        for kind, text, bullet in items:
            size, cpl = self._body_split_metrics(kind, inner_w)
            # 单条最多占几行：即使整页只放它一条也必须放得下，否则会切出永远溢出的碎片
            room = max(1, int((capacity - 0.12) / (size * 1.35 / 72.0)))
            # 第一项留着**种类**，续段也不挂「（续）」标签：正文面板不显示标签
            # （_add_body_panel 只按种类决定排版），而挂上去会让续段被当成 point ——
            # 字号掉到 14pt、行首多出一个圆点，与分页时按 15pt 无前缀算的高度对不上。
            expanded.extend((kind, piece, bullet)
                            for piece in self._split_text(text, cpl * room))

        chunks: list[list[tuple[str, str, bool]]] = []
        current: list[tuple[str, str, bool]] = []
        used = 0.0
        for item in expanded:
            advance = self._body_item_box(item, inner_w)[1]
            if current and used + advance > capacity:
                chunks.append(current)
                current, used = [], 0.0
            current.append(item)
            used += advance
        if current:
            chunks.append(current)
        return chunks

    def _add_body_panel(self, slide, items: list[tuple[str, str, bool]],
                        x: float, y: float, width: float, height: float) -> None:
        """右栏正文面板：正文段落 / 大字结论 / 要点展开。

        与 _add_panel 的关键区别是**不把字段名当行首**。预览里正文就是正文、结论是
        一句大字，没有「正文｜」「结论｜」这样的前缀 —— 每行都挂一个字段名，整页读
        起来就像讲稿提纲，而不是课件（这正是用户指出的问题）。

        所以这里的 items 第一项是区块**种类**（text / conclusion / point），不是给人
        看的标签：text 直接排、point 前面加圆点、conclusion 画成大字并配一条左侧
        强调条 —— 让"这是结论"靠版式说，而不是靠"结论"两个字说。
        """
        self._add_shape(slide, self._panel_shape, x, y, width, height,
                        self._theme.surface, line=self._theme.muted)
        inner_x, inner_w = x + 0.28, width - 0.58
        cursor, limit = y + 0.61, y + height - 0.1
        for item in items:
            if cursor >= limit:
                break
            # 高度与推进量一律取自 _body_item_box —— 分页用的就是这份算术
            box_h, advance, size, body = self._body_item_box(item, inner_w)
            if item[0] == "conclusion":
                # 配色照抄预览的 .conclusion-block / .conclusion-text：左侧强调条取
                # var(--preview-accent)、正文取 var(--preview-ink)。预览的
                # --preview-accent 就是调色板的强调色，也就是 theme_from_palette 里的
                # primary（不是 theme.accent —— 那个令牌在 theme_from_palette 里等于
                # 深色版 secondary）。
                self._add_shape(slide, MSO_SHAPE.RECTANGLE, inner_x, cursor + 0.06,
                                0.055, box_h - 0.18, self._theme.primary)
                self._add_textbox(
                    slide, body, inner_x + 0.2, cursor, inner_w - 0.42, box_h,
                    font_size=size, color=self._theme.text, bold=True,
                    valign=MSO_ANCHOR.MIDDLE, fit_to_shape=True)
                cursor += advance
                continue
            self._add_textbox(slide, body, inner_x, cursor, inner_w, box_h,
                              font_size=size, color=self._theme.text, fit_to_shape=True)
            cursor += advance

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
        if shape_type == MSO_SHAPE.ROUNDED_RECTANGLE:
            # 圆角按预览的绝对半径折算成比例。python-pptx 的 adjustments[0] 是相对
            # 短边的**比例**，所以同一个 8px 在不同尺寸的面板上得到不同的比例值。
            # 拿不到 adjustments 的形状（老版本 python-pptx）就保持默认 —— 圆角大
            # 一点总比导出失败强。
            try:
                shape.adjustments[0] = max(
                    0.0, min(0.5, _PANEL_RADIUS / max(0.01, min(width, height)))
                )
            except (IndexError, TypeError, ValueError):
                pass
        if line:
            # 1px 实线描边。预览的版式面板就是 stroke-width="1" 的实线
            # （svg_renderer._render_rounded_rect），而 python-pptx 默认的 60% 透明
            # 描边在页面上几乎看不见 —— 边线一没，面板就只剩一块没有轮廓的色块。
            # 1px @96dpi = 0.75pt。
            shape.line.color.rgb = self._rgb(line)
            shape.line.width = Pt(0.75)
        else:
            shape.line.fill.background()
        return shape

    def _add_textbox(self, slide, text: str, x: float, y: float, width: float,
                     height: float, *, font_size: int, color: str, bold: bool = False,
                     align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.TOP, fit_to_shape: bool = False):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
        frame = box.text_frame
        frame.clear()
        frame.word_wrap = True
        frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE if fit_to_shape else MSO_AUTO_SIZE.NONE
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
