"""程序化教学图示 —— 把结构化的图示描述画成原生 SVG。

背景
----
幻灯片要呈现「要点延伸出来的东西」，其中一块是图示。仓库里没有任何文生图 / 图库
能力（`ai_engine/parse/` 下的 image 代码全是**读图**：OCR 与 VLM 描述），导出侧又
禁止 PICTURE 形状（test_preview_export_consistency 断言 `shape_type != 13`），
「渲一张位图贴上去」这条路走不通。

于是采用「LLM 出结构、我们程序化画」：模型在讲稿阶段顺带给出一个 figure 描述
（哪种图形、有哪些标签），本模块确定性地把它画成**原生 SVG 图元**。好处是同一份
figure 描述将来可以原样交给 PPTX 导出，用 MSO_SHAPE 复刻出同一张图 —— 两个渲染器
共享的是结构而不是像素。

四种图形
--------
  flow       流程：横向步骤链 + 箭头
  compare    对比：左右两栏对照
  cycle      循环：首尾相接
  hierarchy  层级：上一下多
  chart      数值：横向条形（中文标签长，竖柱状会挤）
  matrix     多维对比：表头 + 网格

本模块只负责**怎么画**（几何与配色）。「这一页有没有图示、图示里有哪些标签」由
gen/page_spec.normalize_figure 决定，而「这一页该不该有图示」由 gen/teaching_plan.py
决定 —— 与 page_spec / presentation / 本模块 三者的分工一致：画什么、长什么样、
怎么摆，各管一段。

文本策略
--------
内容标签一律走 ``<foreignObject>``（与 svg_renderer 一致）：框宽固定时让浏览器自己
换行，HTML 源码里文本保持连续，不会把 token 切碎（预览导出一致性测试按完整 token
断言）。只有**由我们生成**的短文本（序号）才用原生 ``<text>``。
"""

from __future__ import annotations

import math
from typing import Any

from .page_spec import xml_escape
from .templates import PPTTheme

#: 标题条 / 说明行高度（px）
_TITLE_H = 26.0
_CAPTION_H = 22.0

#: 文本对齐 → flex 的 justify-content
_JUSTIFY = {"left": "flex-start", "center": "center", "right": "flex-end"}


# ---- 基础工具 ----

def _c(theme: PPTTheme, token: str) -> str:
    """取主题令牌并补上 #。令牌本身不带 # 前缀。"""
    value = str(getattr(theme, token, "") or "FFFFFF").lstrip("#").upper()
    return f"#{value}"


def _font(theme: PPTTheme) -> str:
    return getattr(theme, "body_font", None) or "Microsoft YaHei"


def _svg_text(x: float, y: float, text: str, theme: PPTTheme, *,
              size: float = 12.0, color: str = "#FFFFFF", weight: str = "normal",
              anchor: str = "middle") -> str:
    """短小且由我们生成的文本（序号）用原生 <text>。

    内容标签请走 `_label` —— 原生 <text> 不换行，长文本只能硬切，切点落在一句话
    中间会把 token 切碎。
    """
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{xml_escape(_font(theme))}, sans-serif" '
        f'font-size="{size:.1f}" font-weight="{weight}" text-anchor="{anchor}" '
        f'fill="{color}">{xml_escape(text)}</text>'
    )


def _label(x: float, y: float, w: float, h: float, text: Any, theme: PPTTheme, *,
           size: float = 13.0, weight: str = "600", color: str = "",
           align: str = "center") -> str:
    """把一段标签放进 foreignObject，由浏览器负责换行。"""
    text = str(text or "").strip()
    if not text or w <= 0 or h <= 0:
        return ""
    style = (
        "width:100%;height:100%;box-sizing:border-box;display:flex;"
        f"align-items:center;justify-content:{_JUSTIFY.get(align, 'center')};"
        f"font:{weight} {size:.0f}px/1.35 {_font(theme)},sans-serif;"
        f"color:{color or _c(theme, 'text')};text-align:{align};"
        "overflow:hidden;word-break:break-word;"
    )
    return (
        f'<foreignObject x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}">'
        f'<div xmlns="http://www.w3.org/1999/xhtml" style="{style}">{xml_escape(text)}</div>'
        f"</foreignObject>"
    )


def _box(x: float, y: float, w: float, h: float, *, fill: str,
         stroke: str = "", radius: float = 10.0) -> str:
    stroke_attr = f' stroke="{stroke}" stroke-width="1"' if stroke else ""
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'rx="{radius:.1f}" fill="{fill}"{stroke_attr}/>'
    )


def _arrow_h(x1: float, x2: float, y: float, color: str) -> str:
    """水平箭头（线 + 实心三角头）。"""
    head = 6.0
    if x2 - x1 <= head * 2:
        return ""
    return (
        f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2 - head:.1f}" y2="{y:.1f}" '
        f'stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
        f'<path d="M{x2:.1f},{y:.1f} L{x2 - head:.1f},{y - head * 0.7:.1f} '
        f'L{x2 - head:.1f},{y + head * 0.7:.1f} Z" fill="{color}"/>'
    )


# ---- 各图形 ----

def _render_flow(fig: dict, theme: PPTTheme, w: float, h: float) -> str:
    items = fig["items"]
    n = len(items)
    surface, muted = _c(theme, "surface"), _c(theme, "muted")
    primary, inverse, accent = _c(theme, "primary"), _c(theme, "inverse"), _c(theme, "accent")

    gap = 24.0
    box_w = max(40.0, (w - gap * (n - 1)) / n)
    box_h = min(h, max(76.0, min(124.0, h * 0.66)))
    y = (h - box_h) / 2
    badge_r = 11.0

    parts: list[str] = []
    for i, text in enumerate(items):
        x = i * (box_w + gap)
        parts.append(_box(x, y, box_w, box_h, fill=surface, stroke=muted))
        cx, cy = x + box_w / 2, y + badge_r + 9
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{badge_r}" fill="{primary}"/>')
        parts.append(_svg_text(cx, cy + 4.5, str(i + 1), theme, size=12,
                               color=inverse, weight="700"))
        parts.append(_label(x + 8, y + badge_r * 2 + 16, box_w - 16,
                            box_h - badge_r * 2 - 22, text, theme, size=13))
        if i < n - 1:
            parts.append(_arrow_h(x + box_w + 5, x + box_w + gap - 5, y + box_h / 2, accent))
    return "".join(parts)


def _render_compare(fig: dict, theme: PPTTheme, w: float, h: float) -> str:
    surface, muted = _c(theme, "surface"), _c(theme, "muted")
    inverse = _c(theme, "inverse")

    gap = 18.0
    col_w = max(60.0, (w - gap) / 2)
    head_h = 36.0

    parts: list[str] = []
    for x, side, token in ((0.0, fig["left"], "primary"),
                           (col_w + gap, fig["right"], "secondary")):
        token_color = _c(theme, token)
        parts.append(_box(x, 0.0, col_w, h, fill=surface, stroke=muted))
        top = 0.0
        if side["title"]:
            parts.append(_box(x, 0.0, col_w, head_h, fill=token_color))
            parts.append(_label(x + 10, 0.0, col_w - 20, head_h, side["title"], theme,
                                size=14, weight="700", color=inverse))
            top = head_h
        items = side["items"]
        avail = h - top - 16.0
        if items and avail > 0:
            row_h = min(40.0, avail / len(items))
            for j, text in enumerate(items):
                yy = top + 8 + j * row_h
                parts.append(
                    f'<circle cx="{x + 18:.1f}" cy="{yy + row_h / 2:.1f}" r="3.5" '
                    f'fill="{token_color}"/>'
                )
                parts.append(_label(x + 30, yy, col_w - 42, row_h, text, theme,
                                    size=13, align="left"))
    return "".join(parts)


def _render_cycle(fig: dict, theme: PPTTheme, w: float, h: float) -> str:
    items = fig["items"]
    n = len(items)
    surface, muted, accent = _c(theme, "surface"), _c(theme, "muted"), _c(theme, "accent")

    cx, cy = w / 2, h / 2
    box_w = min(max(72.0, w / (n + 1.4)), 170.0)
    box_h = min(54.0, max(38.0, h * 0.32))
    rx = max(box_w / 2 + 4, w / 2 - box_w / 2 - 12)
    ry = max(box_h / 2 + 4, h / 2 - box_h / 2 - 10)

    parts = [
        f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="none" '
        f'stroke="{muted}" stroke-width="2" stroke-dasharray="6 6"/>'
    ]
    for i, text in enumerate(items):
        angle = -math.pi / 2 + 2 * math.pi * i / n
        bx = cx + rx * math.cos(angle) - box_w / 2
        by = cy + ry * math.sin(angle) - box_h / 2
        parts.append(_box(bx, by, box_w, box_h, fill=surface, stroke=muted))
        parts.append(_label(bx + 8, by, box_w - 16, box_h, text, theme, size=12))

    # 方向箭头：画在相邻两块的中间角度上，沿椭圆切线指向下一个
    for i in range(n):
        mid = -math.pi / 2 + 2 * math.pi * (i + 0.5) / n
        ax, ay = cx + rx * math.cos(mid), cy + ry * math.sin(mid)
        tx, ty = -rx * math.sin(mid), ry * math.cos(mid)
        norm = math.hypot(tx, ty) or 1.0
        tx, ty = tx / norm, ty / norm
        size = 7.0
        p1 = (ax + tx * size, ay + ty * size)
        p2 = (ax - tx * size * 0.4 + ty * size * 0.75, ay - ty * size * 0.4 - tx * size * 0.75)
        p3 = (ax - tx * size * 0.4 - ty * size * 0.75, ay - ty * size * 0.4 + tx * size * 0.75)
        parts.append(
            f'<path d="M{p1[0]:.1f},{p1[1]:.1f} L{p2[0]:.1f},{p2[1]:.1f} '
            f'L{p3[0]:.1f},{p3[1]:.1f} Z" fill="{accent}"/>'
        )
    return "".join(parts)


def _render_hierarchy(fig: dict, theme: PPTTheme, w: float, h: float) -> str:
    items = fig["items"]
    parent, children = items[0], items[1:]
    surface, muted = _c(theme, "surface"), _c(theme, "muted")
    primary, inverse = _c(theme, "primary"), _c(theme, "inverse")

    parent_h = min(46.0, max(32.0, h * 0.3))
    if not children:
        # 只有一项：当一个居中主块画，不硬凑成层级
        parent_w = min(w * 0.7, 320.0)
        x = (w - parent_w) / 2
        y = (h - parent_h) / 2
        return (
            _box(x, y, parent_w, parent_h, fill=primary)
            + _label(x + 10, y, parent_w - 20, parent_h, parent, theme,
                     size=14, weight="700", color=inverse)
        )

    gap = 16.0
    child_w = max(48.0, (w - gap * (len(children) - 1)) / len(children))
    child_h = min(76.0, max(46.0, h * 0.42))
    parent_w = min(w * 0.46, 280.0)
    parent_x = (w - parent_w) / 2
    child_y = h - child_h

    parts = [
        _box(parent_x, 0.0, parent_w, parent_h, fill=primary),
        _label(parent_x + 10, 0.0, parent_w - 20, parent_h, parent, theme,
               size=14, weight="700", color=inverse),
    ]

    # 竖线下行 → 横向总线 → 各子块竖线
    bus_y = (parent_h + child_y) / 2
    parts.append(f'<line x1="{w / 2:.1f}" y1="{parent_h:.1f}" x2="{w / 2:.1f}" '
                 f'y2="{bus_y:.1f}" stroke="{muted}" stroke-width="2"/>')
    centers = [j * (child_w + gap) + child_w / 2 for j in range(len(children))]
    if len(centers) > 1:
        parts.append(f'<line x1="{centers[0]:.1f}" y1="{bus_y:.1f}" '
                     f'x2="{centers[-1]:.1f}" y2="{bus_y:.1f}" '
                     f'stroke="{muted}" stroke-width="2"/>')
    for j, text in enumerate(children):
        cx = centers[j]
        parts.append(f'<line x1="{cx:.1f}" y1="{bus_y:.1f}" x2="{cx:.1f}" '
                     f'y2="{child_y:.1f}" stroke="{muted}" stroke-width="2"/>')
        parts.append(_box(cx - child_w / 2, child_y, child_w, child_h,
                          fill=surface, stroke=muted))
        parts.append(_label(cx - child_w / 2 + 8, child_y, child_w - 16, child_h,
                            text, theme, size=12))
    return "".join(parts)


def _format_number(value: float) -> str:
    """数值标签：整数不带小数点（45 而不是 45.0），其余保留有效位。"""
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f"{value:g}"


def _render_chart(fig: dict, theme: PPTTheme, w: float, h: float) -> str:
    """横向条形图。中文标签普遍偏长，竖柱状的 x 轴标签会互相挤，故取横向。

    每行都是「标签右对齐 | 轨道 | 实心条 | 数值」：画出轨道是为了让"占比很小"
    也读得出来 —— 只画实心条的话，一个 3% 和"数据缺失"看起来一模一样。
    """
    series = fig["series"]
    n = len(series)
    primary, surface = _c(theme, "primary"), _c(theme, "surface")
    text_color = _c(theme, "text")

    row_h = h / n
    bar_h = min(26.0, max(10.0, row_h * 0.58))
    value_w = 60.0
    # 标签列吃掉三成宽、但不小于 72px，且给条形与数值留出至少 60px
    label_w = min(max(72.0, w * 0.3), max(60.0, w - value_w - 60.0))
    bar_x = label_w + 10.0
    bar_max = max(24.0, w - bar_x - value_w)
    peak = max((abs(float(s["value"])) for s in series), default=0.0)

    parts: list[str] = []
    for i, item in enumerate(series):
        y = i * row_h
        cy = y + row_h / 2
        parts.append(_label(0.0, y, label_w, row_h, item["label"], theme,
                            size=12, align="right"))
        parts.append(_box(bar_x, cy - bar_h / 2, bar_max, bar_h,
                          fill=surface, radius=bar_h / 2))
        width = bar_max * (abs(float(item["value"])) / peak if peak else 0.0)
        if width > 1.0:
            parts.append(_box(bar_x, cy - bar_h / 2, width, bar_h,
                              fill=primary, radius=bar_h / 2))
        parts.append(_svg_text(bar_x + bar_max + 6.0, cy + 4.0,
                               _format_number(float(item["value"])), theme,
                               size=12, color=text_color, weight="600", anchor="start"))
    return "".join(parts)


def _render_matrix(fig: dict, theme: PPTTheme, w: float, h: float) -> str:
    """对比表：表头行 + 网格行。

    首列是行头（被比较对象的名称）—— 加粗、左对齐；其余单元格居中。隔行换底色，
    行多时不至于看串行。行高不随内容伸缩（`_label` 自带 overflow:hidden），
    表格的意义就在于对齐，让它随内容长高反而失去可比性。
    """
    columns, rows = fig["columns"], fig["rows"]
    primary, inverse = _c(theme, "primary"), _c(theme, "inverse")
    surface, background, muted = _c(theme, "surface"), _c(theme, "background"), _c(theme, "muted")

    head_h = min(40.0, max(26.0, h * 0.22))
    row_h = max(18.0, (h - head_h) / len(rows))
    col_w = w / len(columns)
    pad = min(12.0, col_w * 0.12)

    parts = [_box(0.0, 0.0, w, head_h, fill=primary, radius=0.0)]
    for j, name in enumerate(columns):
        parts.append(_label(j * col_w + pad, 0.0, col_w - pad * 2, head_h, name, theme,
                            size=12, weight="700", color=inverse,
                            align="left" if j == 0 else "center"))
    for i, row in enumerate(rows):
        y = head_h + i * row_h
        parts.append(_box(0.0, y, w, row_h, fill=surface if i % 2 == 0 else background,
                          stroke=muted, radius=0.0))
        for j, cell in enumerate(row):
            parts.append(_label(j * col_w + pad, y, col_w - pad * 2, row_h, cell, theme,
                                size=12, weight="700" if j == 0 else "400",
                                align="left" if j == 0 else "center"))
    return "".join(parts)


_RENDERERS = {
    "flow": _render_flow,
    "compare": _render_compare,
    "cycle": _render_cycle,
    "hierarchy": _render_hierarchy,
    "chart": _render_chart,
    "matrix": _render_matrix,
}


# ---- 入口 ----

def render_figure_svg(fig: Any, theme: PPTTheme, width: float, height: float) -> str:
    """把 figure 画成 **SVG 片段**（不是完整 <svg> 文档），坐标原点在 (0,0)。

    调用方负责用 ``<g transform="translate(x, y)">`` 把它放到页面上 —— 与
    svg_renderer 里其余区块的摆版方式一致。

    返回空串表示没有可画的内容，调用方应据此跳过整个区块。
    """
    if not isinstance(fig, dict) or width <= 0 or height <= 0:
        return ""
    renderer = _RENDERERS.get(fig.get("kind"))
    if renderer is None:
        return ""

    top = _TITLE_H if fig.get("title") else 0.0
    bottom = _CAPTION_H if fig.get("caption") else 0.0
    body_h = height - top - bottom
    if body_h <= 0:
        return ""

    parts: list[str] = []
    if top:
        parts.append(_label(0.0, 0.0, width, _TITLE_H, fig["title"], theme,
                            size=13, weight="700", color=_c(theme, "secondary")))
    parts.append(
        f'<g transform="translate(0, {top:.1f})">'
        f"{renderer(fig, theme, width, body_h)}</g>"
    )
    if bottom:
        parts.append(_label(0.0, height - bottom, width, bottom, fig["caption"], theme,
                            size=11, weight="400", color=_c(theme, "muted")))
    return "".join(parts)
