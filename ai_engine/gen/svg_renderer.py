"""SVG 渲染层：把「一页该画什么」（page_spec.PageSpec）画成标准 SVG。

分工
----
  page_spec.py  决定**画什么**（区块的构成与优先级）
  presentation  决定**用什么色/字体**（样式层单一事实来源）
  本模块         只决定**怎么摆**（版式 JSON 的几何 + 区块分配）

历史问题是三者混在一起：渲染器自己去 node 里挑字段，于是同一个页面在预览、
导出、SVG 三处各挑各的，内容对不上。现在字段挑选只在 page_spec 里发生。

文字用 <foreignObject> 承载 HTML
------------------------------
SVG 的 <text> 不换行，旧实现靠 `title[:40]` / 每行 32 字硬切 —— 切点落在一句话
中间会把语义词切碎（导出预览一致性测试正是按完整 token 断言的）。改为把区块
HTML 放进 <foreignObject>：浏览器自己排版换行，HTML 源码里文本始终连续，
既不必做字体度量，也不会切碎 token。

取舍：<foreignObject> 在部分「SVG → 位图」转换器里不渲染。导出的 .pptx 用的是
原生形状（且测试禁止 PICTURE 形状），不经过这条路径，所以预览侧无此顾虑；
若日后要把 SVG 交给外部转换器，这几个区块需换成 <tspan> + 按标点断行。
"""

from __future__ import annotations

import math
import xml.sax.saxutils as saxutils
from typing import Any

from .page_spec import (
    Block,
    PageSpec,
    ROLE_PRIMARY,
    ROLE_SECONDARY,
    block_to_html,
    build_page_spec,
    extract_key_points,
    resolve_kind,
)
from .presentation import presentation_from_nodes, presentation_to_theme
from .templates import PPTTheme, get_layout

#: 1 英寸 = 96px，与 CSS 参考像素一致（版式 JSON 的坐标单位是英寸）
_PX_PER_INCH = 96.0

#: 字号换算：版式 JSON 里的 font_size 是磅值，SVG/CSS 用像素
_PT_TO_PX = 4 / 3

#: 区块最小高度（px），避免次要区块被挤压到不可读
_MIN_BLOCK_HEIGHT = 0.55 * _PX_PER_INCH

#: 区块之间的垂直间距（px）
_BLOCK_GAP = 10.0

#: 区域内容距面板边缘的内边距（px）
_REGION_PADDING = 16.0

#: 页面类型 → 版式 JSON。summary 走自己的卡片版式，quiz/interactive 共用骨架。
_LAYOUT_BY_KIND = {
    "cover": "cover",
    "section": "section",
    "summary": "summary",
    "quiz": "quiz",
    "interactive": "interactive",
    "content": "content_left_right",
}

#: 页面类型 → (主区块区域元素名, 次区块区域元素名)。None 表示该页无此区域。
_REGIONS_BY_KIND = {
    "cover": ("cover_points_region", None),
    "section": ("section_list_region", None),
    "summary": ("summary_card_list", "notes_region"),
    "quiz": ("main_content", None),
    "interactive": ("main_content", None),
    "content": ("right_panel_content", "left_panel_content"),
}

#: 区域元素名 → 该区域标题元素名（标题画在区域左上角）
_REGION_TITLE_ELEMENTS = {
    "right_panel_content": "right_panel_title",
    "left_panel_content": "left_panel_title",
}

#: 版式里这些元素不画自己 —— 它们的位置交给 Block 填充
_CONTENT_BEARING_TYPES = {"text_list", "card_list"}

#: 页型 → 标题前缀。切到 SVG 之前这些 emoji 挂在各页的 <h2> 上，
#: 现在标题画在版式 title_bar 里，前缀在这里补齐以保持观感。
_TITLE_BADGES = {"quiz": "💡 ", "interactive": "🎯 ", "summary": "📌 "}


def _title_text(spec: PageSpec, theme: PPTTheme) -> str:
    return _TITLE_BADGES.get(spec.kind, "") + spec.title


#: 版式槽位 → 取值函数（入参：PageSpec, 主题）
_SLOT_VALUE_MAP = {
    "title_text": _title_text,
    "subtitle_text": lambda spec, theme: spec.subtitle,
    "section_title": _title_text,
    "section_summary": lambda spec, theme: spec.subtitle,
    "section_number": lambda spec, theme: f"{spec.index:02d}",
    "brand_text": lambda spec, theme: getattr(theme, "display_name", "AI教学智能体"),
    "footer_text": lambda spec, theme: "多模态AI互动式教学智能体",
    "ending_text": lambda spec, theme: "本节内容结束",
}


# ---- 兼容旧接口（test_pipeline.py 与历史调用方）----

def resolve_node_type(node: dict[str, Any]) -> str:
    """页面类型识别。保留此名以兼容既有调用方，实现已收敛到 page_spec。"""
    return resolve_kind(node)


#: 历史调用方（fix_preview.py 等）用过这个名字，转发到 page_spec 的实现
resolve_key_points = extract_key_points


# ---- 基础工具 ----

def _esc(text: Any) -> str:
    """XML 转义。除 `&<>` 外还转义引号 —— 这些值也会出现在属性里
    （aria-label / font-family），`saxutils.escape` 默认不管引号。
    """
    return saxutils.escape(str(text or ""), {'"': "&quot;", "'": "&apos;"})


def _color(theme: PPTTheme, token: str) -> str:
    """取主题令牌并补上 #，令牌本身不带 # 前缀。"""
    value = str(getattr(theme, token, "") or "FFFFFF").lstrip("#").upper()
    return f"#{value}"


def _font(theme: PPTTheme) -> str:
    return getattr(theme, "body_font", None) or "Microsoft YaHei"


def _geom(elem: dict) -> tuple[float, float, float, float]:
    """版式元素几何 → 像素 (x, y, w, h)。"""
    return (
        float(elem.get("x", 0)) * _PX_PER_INCH,
        float(elem.get("y", 0)) * _PX_PER_INCH,
        float(elem.get("width", 0)) * _PX_PER_INCH,
        float(elem.get("height", 0)) * _PX_PER_INCH,
    )


def _text_anchor(align: str) -> tuple[str, str]:
    """对齐方式 → (text-anchor, x 计算方式)。"""
    return {"center": ("middle", "center"), "right": ("end", "right")}.get(align, ("start", "left"))


# ---- 原生 SVG 图元 ----

def _render_rect(elem: dict, theme: PPTTheme) -> str:
    x, y, w, h = _geom(elem)
    fill = _color(theme, elem.get("fill_theme", "primary"))
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}"/>'


def _render_rounded_rect(elem: dict, theme: PPTTheme) -> str:
    x, y, w, h = _geom(elem)
    fill = _color(theme, elem.get("fill_theme", "surface"))
    line = _color(theme, elem.get("line_theme", "muted"))
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" '
        f'fill="{fill}" stroke="{line}" stroke-width="1"/>'
    )


def _render_slot_text(elem_name: str, elem: dict, spec: PageSpec, theme: PPTTheme) -> str:
    """版式里的文字槽位（标题、副标题、页码、页脚……）画成原生 <text>。"""
    resolver = _SLOT_VALUE_MAP.get(elem_name)
    raw = resolver(spec, theme) if resolver else ""
    if not str(raw).strip():
        return ""

    x, y, w, h = _geom(elem)
    anchor, align_mode = _text_anchor(str(elem.get("align", "left")))
    tx = x + w / 2 if align_mode == "center" else (x + w if align_mode == "right" else x)
    font_size = float(elem.get("font_size", 14)) * _PT_TO_PX
    weight = "bold" if elem.get("bold") else "normal"
    fill = _color(theme, elem.get("color_theme", "text"))
    # 纵向居中：SVG 的 y 是基线，用「盒中心 + 约 1/3 字高」近似光学居中
    ty = y + h / 2 + font_size / 3
    return (
        f'<text x="{tx:.1f}" y="{ty:.1f}" font-family="{_esc(_font(theme))}, sans-serif" '
        f'font-size="{font_size:.1f}" font-weight="{weight}" text-anchor="{anchor}" '
        f'fill="{fill}">{_esc(raw)}</text>'
    )


def _render_slot_label(
    elem: dict, text: str, theme: PPTTheme, origin: tuple[float, float]
) -> str:
    """用版式元素的位置画一个区块标题（内容来自 Block.heading）。

    origin 是所在 <g> 的平移量：元素坐标是页面绝对的，必须减掉它，
    否则会画到区域之外（标题元素在版式里是绝对定位的）。
    """
    if not text.strip():
        return ""
    x, y, _w, _h = _geom(elem)
    font_size = float(elem.get("font_size", 15)) * _PT_TO_PX
    fill = _color(theme, elem.get("color_theme", "secondary"))
    return (
        f'<text x="{x - origin[0]:.1f}" y="{y - origin[1] + font_size:.1f}" '
        f'font-family="{_esc(_font(theme))}, sans-serif" '
        f'font-size="{font_size:.1f}" font-weight="bold" fill="{fill}">{_esc(text)}</text>'
    )


# ---- 区块摆版 ----

def _block_units(block: Block) -> float:
    """估算区块需要多少纵向空间（相对单位），用于按内容量分配区域高度。

    宁可估宽一点：估窄了内容会被 foreignObject 裁掉，估宽了只是留白。
    """
    if block.kind == "segments":
        # 每段 = 一行徽标 + 正文行数
        return sum(1.2 + math.ceil(len(seg["text"]) / 34) for seg in block.segments) or 1.0
    if block.kind == "questions":
        return sum(
            1.4 + (math.ceil(len(str(q)) / 46) if not isinstance(q, dict) else 2.4)
            for q in block.items
        ) or 1.0
    if block.kind in ("script", "text"):
        chars = sum(len(p) for p in block.paragraphs)
        return max(1.0, math.ceil(chars / 44))
    if block.kind == "bullets":
        return max(1.0, len(block.items) * 0.62)
    return 1.0


def _foreign_object(x: float, y: float, w: float, h: float, html: str, role: str) -> str:
    """把区块 HTML 放进 foreignObject。内层 div 必须显式声明 XHTML 命名空间。"""
    if not html:
        return ""
    return (
        f'<foreignObject x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}">'
        f'<div xmlns="http://www.w3.org/1999/xhtml" class="svg-block svg-block-{role}">'
        f"{html}</div></foreignObject>"
    )


def _allocate_heights(blocks: list[Block], available: float) -> list[float]:
    """按内容量把可用高度分给各区块，并保证每个区块不低于最小高度。"""
    min_h = _MIN_BLOCK_HEIGHT
    gaps = _BLOCK_GAP * (len(blocks) - 1)
    distributable = max(available - gaps, min_h * len(blocks))

    weights = [_block_units(b) for b in blocks]
    total = sum(weights) or 1.0
    heights = [max(min_h, distributable * weight / total) for weight in weights]

    # 抬高到最小高度的区块会撑破总量，从还有余量的区块里等比回收
    overflow = sum(heights) - distributable
    if overflow > 0:
        slack = [hh - min_h for hh in heights]
        total_slack = sum(slack)
        if total_slack > 0:
            heights = [hh - overflow * (s / total_slack) for hh, s in zip(heights, slack)]
    return heights


def _lay_out_blocks(
    blocks: list[Block],
    width: float,
    height: float,
    theme: PPTTheme,
    title_elem: dict | None = None,
    origin: tuple[float, float] = (0.0, 0.0),
) -> str:
    """在 (0,0,width,height) 内纵向堆叠区块；调用方负责用 <g transform> 平移。

    区块 HTML 自带 <h4> 的（segments / script）不再另画标题；
    不带的（bullets / questions）用版式里的标题元素位置补一个。
    origin 仅用于把「绝对定位的版式标题元素」换算到本区域的相对坐标。
    """
    blocks = [b for b in blocks if b]
    if not blocks or width <= 0 or height <= 0:
        return ""

    parts: list[str] = []
    cursor = 0.0
    available = height

    # 区域标题：只画一次，文字取该区域第一个 bullets 区块的 heading
    if title_elem is not None:
        heading = next((b.heading for b in blocks if b.heading and b.kind == "bullets"), "")
        label = _render_slot_label(title_elem, heading, theme, origin)
        if label:
            reserved = float(title_elem.get("height", 0.36)) * _PX_PER_INCH + _BLOCK_GAP
            parts.append(label)
            cursor += reserved
            available -= reserved

    for block, block_height in zip(blocks, _allocate_heights(blocks, available)):
        parts.append(
            _foreign_object(0.0, cursor, width, block_height, block_to_html(block), block.role)
        )
        cursor += block_height + _BLOCK_GAP

    return "".join(parts)


# ---- 主渲染 ----

def _lay_out_region(
    blocks: list[Block],
    region_elem: dict,
    theme: PPTTheme,
    title_elem: dict | None = None,
) -> str:
    """区域 = 一个 <g> 平移 + 内边距，内部按矩形摆区块。"""
    if not blocks:
        return ""

    x, y, w, h = _geom(region_elem)
    if region_elem.get("type") == "card_list":
        # 卡片列表区域：把「最多几张卡」的可视范围当作边界，与版式观感一致
        card_h = float(region_elem.get("card_height", 0.78))
        gap = float(region_elem.get("card_gap", 0.12))
        max_cards = int(region_elem.get("max_cards", 5))
        h = (card_h * max_cards + gap * (max_cards - 1)) * _PX_PER_INCH

    inner = _lay_out_blocks(
        blocks,
        w - _REGION_PADDING * 2,
        h - _REGION_PADDING,
        theme,
        title_elem,
        origin=(x + _REGION_PADDING, y + _REGION_PADDING),
    )
    if not inner:
        return ""
    return f'<g transform="translate({x + _REGION_PADDING:.1f}, {y + _REGION_PADDING:.1f})">{inner}</g>'


def render_page_spec_to_svg(
    spec: PageSpec,
    theme: PPTTheme,
    *,
    paint_background: bool = False,
    responsive: bool = True,
) -> str:
    """把一个 PageSpec 渲染成完整 SVG 字符串。

    Args:
        spec: 页面内容模型
        theme: 样式令牌（来自 gen/presentation.py）
        paint_background: 是否画整页底色。嵌在 HTML 里时由 .slide 卡片提供背景，
            所以默认 False；需要独立成图时传 True。
        responsive: 宽度用 100% 由 CSS 定高，还是写死像素尺寸。嵌 iframe 用前者。
    """
    layout = get_layout(_LAYOUT_BY_KIND.get(spec.kind, "content_left_right"))
    elements: dict[str, dict] = layout.get("elements", {})
    slide_w, slide_h = layout.get("slide_size", [13.333, 7.5])
    width, height = slide_w * _PX_PER_INCH, slide_h * _PX_PER_INCH
    slide_area = width * height

    primary_region, secondary_region = _REGIONS_BY_KIND.get(spec.kind, (None, None))
    primary_blocks = [b for b in spec.blocks if b.role == ROLE_PRIMARY]
    secondary_blocks = [b for b in spec.blocks if b.role == ROLE_SECONDARY]

    sizing = 'width="100%"' if responsive else f'width="{width:.0f}" height="{height:.0f}"'
    parts = [
        f'<svg {sizing} viewBox="0 0 {width:.0f} {height:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{_esc(spec.title)}" '
        f'preserveAspectRatio="xMidYMid meet">'
    ]
    if paint_background:
        parts.append(
            f'<rect width="{width:.0f}" height="{height:.0f}" fill="{_color(theme, "background")}"/>'
        )

    # 版式骨架：面板底色、分隔条、标题/页码/页脚等文字槽位
    for elem_name, elem in elements.items():
        etype = elem.get("type")
        if etype in _CONTENT_BEARING_TYPES:
            continue  # 内容区块区域由下方按 Block 填充
        if etype == "rect":
            # 铺满整页的底色块交给外层卡片/CSS 渐变，画上去会把它们盖掉
            _, _, ew, eh = _geom(elem)
            if not paint_background and ew * eh >= slide_area * 0.95:
                continue
            parts.append(_render_rect(elem, theme))
        elif etype == "rounded_rect":
            parts.append(_render_rounded_rect(elem, theme))
        elif etype == "text":
            parts.append(_render_slot_text(elem_name, elem, spec, theme))

    for region_name, region_blocks in (
        (primary_region, primary_blocks),
        (secondary_region, secondary_blocks),
    ):
        if not region_name or not region_blocks:
            continue
        region_elem = elements.get(region_name)
        if not region_elem:
            continue
        parts.append(
            _lay_out_region(
                region_blocks,
                region_elem,
                theme,
                elements.get(_REGION_TITLE_ELEMENTS.get(region_name, "")),
            )
        )

    parts.append("</svg>")
    return "\n".join(p for p in parts if p)


def render_node_to_svg(node: dict, page_index: int = 1, theme_id: str = "default") -> str:
    """单节点渲染入口（兼容旧签名）。

    样式按节点自身的 metadata.presentation 取；没选过样式时回落到
    catalog 里 template_id 对应的既有主题，配色与改动前一致。
    """
    values, explicit = presentation_from_nodes([node])
    theme, _styled = presentation_to_theme(values, explicit, theme_id)
    spec = build_page_spec(node, page_index)
    return render_page_spec_to_svg(spec, theme)
