"""SVG渲染中间层：把教学节点+版式配置渲染成标准SVG矢量图，
前端可以直接渲染做实时预览，版式骨架和PPT导出保持一致，后续逐步对齐可视化元素。
"""
import xml.sax.saxutils as saxutils
from .templates import get_theme, get_layout
def resolve_key_points(node):
    points = node.get('key_points') or node.get('core_points') or node.get('key_difficulties') or []
    return [str(p).strip() for p in points if str(p).strip()]

def resolve_node_type(node):
    t = str(node.get('type') or node.get('node_type') or 'content').lower()
    alias = {'title': 'cover', 'toc': 'section', 'question': 'quiz'}
    return alias.get(t, t)


def _esc(text: str) -> str:
    """XML转义，避免&<>导致SVG非法"""
    return saxutils.escape(str(text or ""))


def _color(theme, color_name: str) -> str:
    """统一处理颜色值，自动去掉#前缀避免##FFFFFF"""
    val = str(getattr(theme, color_name, "ffffff")).lstrip("#").upper()
    return f"#{val}"


# 槽位名 → 从node取字段的映射，和export_ppt.py保持一致
_SLOT_VALUE_MAP = {
    "title_text": lambda node, idx, theme: str(node.get("title") or f"第{idx}页"),
    "subtitle_text": lambda node, idx, theme: str(node.get("summary") or ""),
    "section_title": lambda node, idx, theme: str(node.get("title") or ""),
    "section_summary": lambda node, idx, theme: str(node.get("summary") or ""),
    "section_number": lambda node, idx, theme: f"{idx:02d}",
    "brand_text": lambda node, idx, theme: getattr(theme, "display_name", "AI教学智能体"),
    "footer_text": lambda node, idx, theme: "多模态AI互动式教学智能体",
    "ending_text": lambda node, idx, theme: "本节内容结束",
}


def render_node_to_svg(node: dict, page_index: int = 1, theme_id: str = "default") -> str:
    theme = get_theme(theme_id)
    node_type = resolve_node_type(node)
    if node_type == "cover":
        layout = get_layout("cover")
    elif node_type == "section":
        layout = get_layout("section")
    elif node_type == "summary":
        layout = get_layout("summary")
    else:
        layout = get_layout("content_left_right")
    sw, sh = layout["slide_size"]
    W, H = sw*96, sh*96
    svg = [f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<rect width="{W}" height="{H}" fill="{_color(theme, "background")}"/>')
    elements = layout["elements"]

    # 按element类型渲染，x/y/w/h按类型取，缺失时兜底
    for elem_name, elem in elements.items():
        etype = elem.get("type")
        x = elem.get("x", 0)*96
        y = elem.get("y", 0)*96
        w = elem.get("width", 0)*96
        h = elem.get("height", 0)*96

        if etype == "rect":
            fill = _color(theme, elem.get("fill_theme", "primary"))
            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}"/>')
        elif etype == "rounded_rect":
            fill = _color(theme, elem.get("fill_theme", "surface"))
            line = _color(theme, elem.get("line_theme", "muted"))
            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" fill="{fill}" stroke="{line}" stroke-width="1"/>')
        elif etype == "text":
            # 从槽位映射取内容
            if elem_name in _SLOT_VALUE_MAP:
                raw_text = _SLOT_VALUE_MAP[elem_name](node, page_index, theme)
            else:
                raw_text = ""
            # 先截断再转义，避免截断&am;的非法XML
            if elem_name == "title_text":
                raw_text = raw_text[:40]
            raw_text = raw_text[:80]
            fill = _color(theme, elem.get("color_theme", "text"))
            fs = elem.get("font_size", 14)*4/3
            weight = "bold" if elem.get("bold") else "normal"
            align = elem.get("align", "left")
            anchor = {"center": "middle", "right": "end"}.get(align, "start")
            tx = x + w/2 if align == "center" else x
            svg.append(
                f'<text x="{tx:.1f}" y="{y + h/2 + fs/3:.1f}" '
                f'font-family="Microsoft YaHei, 微软雅黑, PingFang SC, sans-serif" '
                f'font-size="{fs:.1f}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{_esc(raw_text)}</text>'
            )
        # 渲染summary页的卡片列表
        if etype == "card_list":
            cards_y = elem.get("y", 0.4)*96
            card_h = elem.get("card_height", 0.7)*96
            gap = elem.get("card_gap", 0.12)*96
            max_cards = elem.get("max_cards", 5)
            points = resolve_key_points(node)[:max_cards]
            for i, point in enumerate(points):
                cy = cards_y + i*(card_h + gap)
                svg.append(f'<rect x="{x:.1f}" y="{cy:.1f}" width="{w:.1f}" height="{card_h:.1f}" rx="6" fill="{_color(theme, "surface")}" stroke="{_color(theme, "muted")}" stroke-width="1"/>')
                svg.append(f'<text x="{x+16:.1f}" y="{cy + card_h/2 + 6:.1f}" font-family="Microsoft YaHei, 微软雅黑, sans-serif" font-size="14" fill="{_color(theme, "text")}">• {_esc(str(point)[:50])}</text>')
        # text_list类型暂跳过，内容页后面单独渲染
        elif etype in ("text_list",):
            continue

    # 内容页渲染左右面板内容
    if node_type not in ("cover", "section", "summary"):
        left_panel = elements["left_panel"]
        right_panel = elements["right_panel"]
        secondary_color = _color(theme, "secondary")
        svg.append(f'<text x="{left_panel["x"]*96+20}" y="{left_panel["y"]*96+40:.1f}" font-family="Microsoft YaHei, 微软雅黑, sans-serif" font-size="14" font-weight="bold" fill="{secondary_color}">核心要点</text>')
        y = left_panel["y"]*96 + 80
        points = resolve_key_points(node)[:5]
        for point in points:
            raw_point = str(point)[:30]  # 先截断再转义
            svg.append(f'<text x="{left_panel["x"]*96+20}" y="{y:.1f}" font-family="Microsoft YaHei, 微软雅黑, sans-serif" font-size="13" fill="{_color(theme, "text")}">• {_esc(raw_point)}</text>')
            y += 26
        svg.append(f'<text x="{right_panel["x"]*96+20}" y="{right_panel["y"]*96+40:.1f}" font-family="Microsoft YaHei, 微软雅黑, sans-serif" font-size="14" font-weight="bold" fill="{secondary_color}">教学内容</text>')
        content = str(node.get("content") or node.get("summary") or "")
        y = right_panel["y"]*96 + 80
        line = ""
        for char in content:
            line += char
            if len(line) > 32:
                svg.append(f'<text x="{right_panel["x"]*96+20}" y="{y:.1f}" font-family="Microsoft YaHei, 微软雅黑, sans-serif" font-size="14" fill="{_color(theme, "text")}">{_esc(line)}</text>')
                line = ""
                y += 24
                if y > right_panel["y"]*96 + right_panel["height"]*96 - 20:
                    break
        if line and y <= right_panel["y"]*96 + right_panel["height"]*96 - 20:
            svg.append(f'<text x="{right_panel["x"]*96+20}" y="{y:.1f}" font-family="Microsoft YaHei, 微软雅黑, sans-serif" font-size="14" fill="{_color(theme, "text")}">{_esc(line)}</text>')

    svg.append("</svg>")
    return "\n".join(svg)
