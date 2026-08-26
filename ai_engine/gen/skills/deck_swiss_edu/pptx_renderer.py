"""
PPTXDesignRenderer — deck-swiss-edu 设计规范注入 PPTX 渲染器

职责：
  将 deck 布局（S01-S26）+ 配色（Klein Blue 等）翻译为 python-pptx 的格式，
  替代 export_ppt.py 中无设计系统的默认处理器。

设计规范来源：
  ai_engine/gen/skills/deck_swiss_edu/SKILL.md

配色（RGB）：
  Klein Blue   accent=#002FA7 paper=#fafaf8 ink=#0a0a0a light=#e8e8ec
  Lemon Yellow accent=#FFD500 paper=#f7f5ee ink=#0a0a0a light=#f0edda
  Neon Green   accent=#C5E003 paper=#f7f5ee ink=#0a0a0a light=#eef5d8
  Safety Orange accent=#FF6B35 paper=#f7f5ee ink=#ffffff light=#fde8df
"""

from __future__ import annotations

from typing import Any

from pptygen import Presentation  # type: ignore
from pptygen.utils import Pt
from pptygen.color import RGBColor
from pptygen.text import TextFrame, TextPara, TextItem
from pptygen.enum.shapes import PP_PLACEHOLDER

# ---------------------------------------------------------------------------
# 配色表
# ---------------------------------------------------------------------------

PALETTES = {
    "klein-blue": {
        "accent": RGBColor(0x00, 0x2F, 0xA7),
        "paper": RGBColor(0xFA, 0xFA, 0xF8),
        "ink": RGBColor(0x0A, 0x0A, 0x0A),
        "light": RGBColor(0xE8, 0xE8, 0xEC),
    },
    "lemon-yellow": {
        "accent": RGBColor(0xFF, 0xD5, 0x00),
        "paper": RGBColor(0xF7, 0xF5, 0xEE),
        "ink": RGBColor(0x0A, 0x0A, 0x0A),
        "light": RGBColor(0xF0, 0xED, 0xDA),
    },
    "neon-green": {
        "accent": RGBColor(0xC5, 0xE0, 0x03),
        "paper": RGBColor(0xF7, 0xF5, 0xEE),
        "ink": RGBColor(0x0A, 0x0A, 0x0A),
        "light": RGBColor(0xEE, 0xF5, 0xD8),
    },
    "safety-orange": {
        "accent": RGBColor(0xFF, 0x6B, 0x35),
        "paper": RGBColor(0xF7, 0xF5, 0xEE),
        "ink": RGBColor(0xFF, 0xFF, 0xFF),
        "light": RGBColor(0xFD, 0xE8, 0xDF),
    },
}

DEFAULT_PALETTE = "klein-blue"

# ---------------------------------------------------------------------------
# 16:9 幻灯片尺寸（单位：英寸）
# ---------------------------------------------------------------------------
SLIDE_W = 13.33  # 英寸（16:9 标准）
SLIDE_H = 7.5


def _rgb(hex_str: str) -> RGBColor:
    """#RRGGBB → RGBColor"""
    h = hex_str.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _esc(s: str) -> str:
    """基础 HTML 转义（用于 PPTX 文本）"""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# 布局 → 幻灯片处理器
# ---------------------------------------------------------------------------

class PPTXDesignRenderer:
    """
    将 deck 布局 + 配色规范注入 PPTX。
    使用 pptygen（与 pptx 库兼容但支持更丰富的布局 API）。
    """

    def __init__(self, palette_key: str = DEFAULT_PALETTE):
        self.palette = PALETTES.get(palette_key, PALETTES[DEFAULT_PALETTE])
        self.palette_key = palette_key

    # ── 公开入口 ────────────────────────────────────────────────────────────

    def render(self, slides: list[dict[str, Any]], course_name: str = "课件") -> bytes:
        """
        slides（deck JSON）+ 配色 → .pptx 字节流

        Args:
            slides: [{"layout": "S01", "title": "...", ...}, ...]
            course_name: 课程名（封面用）

        Returns:
            .pptx 字节流
        """
        prs = Presentation(width=SLIDE_W, height=SLIDE_H)
        # 16:9
        prs.set_slide_width(SLIDE_W)
        prs.set_slide_height(SLIDE_H)

        accent = self.palette["accent"]
        paper = self.palette["paper"]
        ink = self.palette["ink"]

        for idx, slide_data in enumerate(slides):
            layout = str(slide_data.get("layout", "S03"))
            handler = self._get_handler(layout)
            handler(prs, slide_data, idx, len(slides))

        import io
        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        return buf.read()

    # ── 处理器分派 ──────────────────────────────────────────────────────────

    def _get_handler(self, layout: str):
        handlers = {
            "S01": self._cover,
            "S02": self._timeline,
            "S03": self._statement,
            "S04": self._six_cells,
            "S05": self._three_sub_cards,
            "S06": self._kpi_tower,
            "S07": self._h_bar_chart,
            "S08": self._duo_compare,
            "S09": self._closing_manifesto,
            "S10": self._dot_matrix,
            "S11": self._horizontal_timeline,
            "S12": self._manifesto_banner,
            "S13": self._three_forces,
            "S14": self._loop_diagram,
            "S15": self._image_matrix,
            "S16": self._multi_card,
            "S17": self._system_diagram,
            "S18": self._why_now,
            "S19": self._four_cards,
            "S20": self._stacked_kpi,
            "S21": self._tech_spec,
            "S22": self._image_hero,
            "S23": self._concept_definition,
            "S24": self._quiz,
            "S25": self._code_example,
            "S26": self._section_divider,
        }
        return handlers.get(layout, self._content_fallback)

    # ── 通用工具 ────────────────────────────────────────────────────────────

    def _add_folio(self, slide, idx: int, total: int, color: RGBColor) -> None:
        """右下角页码：№N/M"""
        txf = slide.add_text_frame()
        txf.add_paragraph()
        txf.text_frame.text = f"№{idx + 1}/{total}"
        txf.text_frame.paragraphs[0].font.size = Pt(9)
        txf.text_frame.paragraphs[0].font.color.rgb = color
        txf.text_frame.paragraphs[0].font.name = "Inter"
        # 放右下角
        txf.left = int(SLIDE_W * 9144) - int(1.2 * 9144)  # EMU
        txf.top = int(SLIDE_H * 9144) - int(0.5 * 9144)
        txf.width = int(1.2 * 9144)
        txf.height = int(0.4 * 9144)

    def _add_topic_tag(self, slide, topic: str, color: RGBColor) -> None:
        """左下角 topic 标签"""
        if not topic:
            return
        txf = slide.add_text_frame()
        txf.add_paragraph()
        txf.text_frame.text = topic.upper()
        txf.text_frame.paragraphs[0].font.size = Pt(8)
        txf.text_frame.paragraphs[0].font.color.rgb = color
        txf.text_frame.paragraphs[0].font.name = "Inter"
        txf.text_frame.paragraphs[0].space_before = Pt(4)
        txf.left = int(0.4 * 9144)
        txf.top = int(SLIDE_H * 9144) - int(0.6 * 9144)
        txf.width = int(2 * 9144)
        txf.height = int(0.35 * 9144)

    def _accent_border_left(self, slide, accent: RGBColor, height_ratio: float = 1.0) -> None:
        """左侧 4px accent 色竖线（hairline border 效果）"""
        h = int(SLIDE_H * 9144 * height_ratio)
        w = int(0.04 * 9144)
        line = slide.add_shape(
            1,  # rectangle
            int(0.4 * 9144),
            int((SLIDE_H - height_ratio * SLIDE_H) * 9144 / 2),
            w,
            h,
        )
        line.fill.solid()
        line.fill.fore_color.rgb = accent
        line.line.color.rgb = accent

    def _set_bg(self, slide, color: RGBColor) -> None:
        try:
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = color
        except Exception:
            pass

    # ── 布局处理器 ─────────────────────────────────────────────────────────

    def _cover(self, prs: Presentation, data: dict, idx: int, total: int) -> None:
        accent = self.palette["accent"]
        paper = self.palette["paper"]
        ink = self.palette["ink"]

        slide = prs.add_slide()
        self._set_bg(slide, accent)

        title = _esc(data.get("title", ""))
        subtitle = _esc(data.get("subtitle", ""))
        meta = data.get("meta", {})
        date = _esc(meta.get("date", "2026"))
        topic = _esc(meta.get("topic", ""))

        # 主标题
        txf = slide.add_text_frame()
        txf.add_paragraph()
        txf.text_frame.text = title
        txf.text_frame.paragraphs[0].font.size = Pt(60)
        txf.text_frame.paragraphs[0].font.color.rgb = paper
        txf.text_frame.paragraphs[0].font.name = "Inter Tight"
        txf.text_frame.paragraphs[0].bold = True
        txf.left = int(0.8 * 9144)
        txf.top = int(3.5 * 9144)
        txf.width = int(11 * 9144)
        txf.height = int(1.2 * 9144)

        # 副标题
        if subtitle:
            txf2 = slide.add_text_frame()
            txf2.add_paragraph()
            txf2.text_frame.text = subtitle
            txf2.text_frame.paragraphs[0].font.size = Pt(20)
            txf2.text_frame.paragraphs[0].font.color.rgb = paper
            txf2.text_frame.paragraphs[0].font.color.brightness = 0.3
            txf2.left = int(0.8 * 9144)
            txf2.top = int(4.8 * 9144)
            txf2.width = int(11 * 9144)
            txf2.height = int(0.5 * 9144)

        # 日期
        if date:
            txf3 = slide.add_text_frame()
            txf3.add_paragraph()
            txf3.text_frame.text = date
            txf3.text_frame.paragraphs[0].font.size = Pt(10)
            txf3.text_frame.paragraphs[0].font.color.rgb = paper
            txf3.text_frame.paragraphs[0].font.color.brightness = 0.5
            txf3.left = int(0.8 * 9144)
            txf3.top = int(5.4 * 9144)
            txf3.width = int(4 * 9144)

        # topic 标签
        if topic:
            txf4 = slide.add_text_frame()
            txf4.add_paragraph()
            txf4.text_frame.text = topic.upper()
            txf4.text_frame.paragraphs[0].font.size = Pt(9)
            txf4.text_frame.paragraphs[0].font.color.rgb = paper
            txf4.text_frame.paragraphs[0].space_before = Pt(4)
            txf4.left = int(0.8 * 9144)
            txf4.top = int(6.4 * 9144)
            txf4.width = int(3 * 9144)

        # 页码
        self._add_folio(slide, idx, total, paper)

    def _concept_definition(self, prs: Presentation, data: dict, idx: int, total: int) -> None:
        """S23 — 概念定义页"""
        accent = self.palette["accent"]
        paper = self.palette["paper"]
        ink = self.palette["ink"]

        slide = prs.add_slide()
        self._set_bg(slide, paper)

        title = _esc(data.get("title", ""))
        content = _esc(data.get("content", ""))
        examples = data.get("examples", [])
        key_points = data.get("key_points", [])

        # 左侧 accent 竖线
        self._accent_border_left(slide, accent, height_ratio=0.6)

        # 页码
        self._add_folio(slide, idx, total, ink)

        # 标题
        txf = slide.add_text_frame()
        txf.add_paragraph()
        txf.text_frame.text = title
        txf.text_frame.paragraphs[0].font.size = Pt(32)
        txf.text_frame.paragraphs[0].font.color.rgb = accent
        txf.text_frame.paragraphs[0].font.name = "Inter Tight"
        txf.text_frame.paragraphs[0].bold = True
        txf.left = int(0.8 * 9144)
        txf.top = int(0.6 * 9144)
        txf.width = int(11 * 9144)
        txf.height = int(0.8 * 9144)

        # 正文
        if content:
            txf2 = slide.add_text_frame()
            txf2.add_paragraph()
            txf2.text_frame.text = content
            txf2.text_frame.paragraphs[0].font.size = Pt(14)
            txf2.text_frame.paragraphs[0].font.color.rgb = ink
            txf2.text_frame.paragraphs[0].font.name = "Inter"
            txf2.text_frame.paragraphs[0].line_spacing = 1.6
            txf2.left = int(0.8 * 9144)
            txf2.top = int(1.5 * 9144)
            txf2.width = int(5.8 * 9144)
            txf2.height = int(2 * 9144)

        # 示例（右侧）
        if examples:
            ex_title = slide.add_text_frame()
            ex_title.add_paragraph()
            ex_title.text_frame.text = "示例"
            ex_title.text_frame.paragraphs[0].font.size = Pt(10)
            ex_title.text_frame.paragraphs[0].font.color.rgb = accent
            ex_title.text_frame.paragraphs[0].font.name = "Inter"
            ex_title.text_frame.paragraphs[0].bold = True
            ex_title.left = int(7 * 9144)
            ex_title.top = int(1.5 * 9144)
            ex_title.width = int(5.5 * 9144)

            ex_items = "\n".join(f"• {str(e)}" for e in examples[:4])
            ex_body = slide.add_text_frame()
            ex_body.add_paragraph()
            ex_body.text_frame.text = ex_items
            ex_body.text_frame.paragraphs[0].font.size = Pt(12)
            ex_body.text_frame.paragraphs[0].font.color.rgb = ink
            ex_body.text_frame.paragraphs[0].font.name = "JetBrains Mono"
            ex_body.text_frame.paragraphs[0].line_spacing = 1.5
            ex_body.left = int(7 * 9144)
            ex_body.top = int(1.9 * 9144)
            ex_body.width = int(5.5 * 9144)

        # 要点（底部）
        if key_points:
            kp_title = slide.add_text_frame()
            kp_title.add_paragraph()
            kp_title.text_frame.text = "要点"
            kp_title.text_frame.paragraphs[0].font.size = Pt(10)
            kp_title.text_frame.paragraphs[0].font.color.rgb = accent
            kp_title.text_frame.paragraphs[0].font.name = "Inter"
            kp_title.text_frame.paragraphs[0].bold = True
            kp_title.left = int(0.8 * 9144)
            kp_title.top = int(4.2 * 9144)
            kp_title.width = int(11 * 9144)

            kp_items = "\n".join(f"• {str(k)}" for k in key_points[:5])
            kp_body = slide.add_text_frame()
            kp_body.add_paragraph()
            kp_body.text_frame.text = kp_items
            kp_body.text_frame.paragraphs[0].font.size = Pt(12)
            kp_body.text_frame.paragraphs[0].font.color.rgb = ink
            kp_body.text_frame.paragraphs[0].font.name = "Inter"
            kp_body.text_frame.paragraphs[0].line_spacing = 1.6
            kp_body.left = int(0.8 * 9144)
            kp_body.top = int(4.6 * 9144)
            kp_body.width = int(11 * 9144)

    def _quiz(self, prs: Presentation, data: dict, idx: int, total: int) -> None:
        """S24 — 互动问答页"""
        accent = self.palette["accent"]
        paper = self.palette["paper"]
        ink = self.palette["ink"]

        slide = prs.add_slide()
        self._set_bg(slide, paper)

        title = _esc(data.get("title", "互动问答"))
        questions = data.get("questions", ["思考一下？"])

        # 左侧 accent 竖线
        self._accent_border_left(slide, accent)

        # 页码
        self._add_folio(slide, idx, total, ink)

        # 标题
        txf = slide.add_text_frame()
        txf.add_paragraph()
        txf.text_frame.text = "💡 " + title
        txf.text_frame.paragraphs[0].font.size = Pt(28)
        txf.text_frame.paragraphs[0].font.color.rgb = accent
        txf.text_frame.paragraphs[0].font.name = "Inter Tight"
        txf.text_frame.paragraphs[0].bold = True
        txf.left = int(0.8 * 9144)
        txf.top = int(0.6 * 9144)
        txf.width = int(11 * 9144)
        txf.height = int(0.8 * 9144)

        # 问题列表
        q_items = "\n".join(f"❓ {str(q)}" for q in questions)
        txf2 = slide.add_text_frame()
        txf2.add_paragraph()
        txf2.text_frame.text = q_items
        txf2.text_frame.paragraphs[0].font.size = Pt(16)
        txf2.text_frame.paragraphs[0].font.color.rgb = ink
        txf2.text_frame.paragraphs[0].font.name = "Inter"
        txf2.text_frame.paragraphs[0].line_spacing = 2.0
        txf2.left = int(0.8 * 9144)
        txf2.top = int(1.8 * 9144)
        txf2.width = int(11 * 9144)

    def _section_divider(self, prs: Presentation, data: dict, idx: int, total: int) -> None:
        """S26 — 章节过渡页"""
        accent = self.palette["accent"]
        paper = self.palette["paper"]

        slide = prs.add_slide()
        self._set_bg(slide, accent)

        title = _esc(data.get("title", "新章节"))

        txf = slide.add_text_frame()
        txf.add_paragraph()
        txf.text_frame.text = title
        txf.text_frame.paragraphs[0].font.size = Pt(54)
        txf.text_frame.paragraphs[0].font.color.rgb = paper
        txf.text_frame.paragraphs[0].font.name = "Inter Tight"
        txf.text_frame.paragraphs[0].bold = True
        txf.text_frame.paragraphs[0].alignment = 1  # center
        txf.left = int(1 * 9144)
        txf.top = int(3 * 9144)
        txf.width = int(11 * 9144)
        txf.height = int(1.5 * 9144)

        # 页码
        self._add_folio(slide, idx, total, paper)

    def _six_cells(self, prs: Presentation, data: dict, idx: int, total: int) -> None:
        """S04 — 6 要点网格"""
        accent = self.palette["accent"]
        paper = self.palette["paper"]
        ink = self.palette["ink"]
        light = self.palette["light"]

        slide = prs.add_slide()
        self._set_bg(slide, paper)

        title = _esc(data.get("title", ""))
        items = data.get("items", [])[:6]

        # 页码
        self._add_folio(slide, idx, total, ink)

        # 标题
        txf = slide.add_text_frame()
        txf.add_paragraph()
        txf.text_frame.text = title
        txf.text_frame.paragraphs[0].font.size = Pt(22)
        txf.text_frame.paragraphs[0].font.color.rgb = ink
        txf.text_frame.paragraphs[0].font.name = "Inter Tight"
        txf.text_frame.paragraphs[0].bold = True
        # 左侧 accent 线
        txf.text_frame.paragraphs[0].space_before = Pt(6)
        txf.left = int(0.8 * 9144)
        txf.top = int(0.5 * 9144)
        txf.width = int(11 * 9144)
        txf.height = int(0.6 * 9144)

        # 左侧 accent 竖线
        self._accent_border_left(slide, accent, height_ratio=0.08)

        # 3×2 网格
        for i, item in enumerate(items):
            col = i % 3
            row = i // 3
            x = int((0.8 + col * 4.0) * 9144)
            y = int((1.4 + row * 2.8) * 9144)

            # 单元格背景
            cell = prs.add_shape(
                1, x, y, int(3.6 * 9144), int(2.4 * 9144)
            )
            cell.fill.solid()
            cell.fill.fore_color.rgb = light
            cell.line.color.rgb = RGBColor(0xE0, 0xE0, 0xE0)
            cell.line.width = 0.5

            # 编号
            num_tx = slide.add_text_frame()
            num_tx.add_paragraph()
            num_tx.text_frame.text = str(i + 1)
            num_tx.text_frame.paragraphs[0].font.size = Pt(9)
            num_tx.text_frame.paragraphs[0].font.color.rgb = accent
            num_tx.text_frame.paragraphs[0].font.name = "Inter"
            num_tx.text_frame.paragraphs[0].bold = True
            num_tx.left = x + int(0.15 * 9144)
            num_tx.top = y + int(0.15 * 9144)
            num_tx.width = int(0.4 * 9144)

            # 标题
            item_title = _esc(str(item.get("title", "")))
            t_tx = slide.add_text_frame()
            t_tx.add_paragraph()
            t_tx.text_frame.text = item_title
            t_tx.text_frame.paragraphs[0].font.size = Pt(14)
            t_tx.text_frame.paragraphs[0].font.color.rgb = ink
            t_tx.text_frame.paragraphs[0].font.name = "Inter"
            t_tx.text_frame.paragraphs[0].bold = True
            t_tx.left = x + int(0.15 * 9144)
            t_tx.top = y + int(0.5 * 9144)
            t_tx.width = int(3.3 * 9144)

            # 描述
            item_desc = _esc(str(item.get("desc", ""))[:80])
            d_tx = slide.add_text_frame()
            d_tx.add_paragraph()
            d_tx.text_frame.text = item_desc
            d_tx.text_frame.paragraphs[0].font.size = Pt(10)
            d_tx.text_frame.paragraphs[0].font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            d_tx.text_frame.paragraphs[0].font.name = "Inter"
            d_tx.left = x + int(0.15 * 9144)
            d_tx.top = y + int(1.0 * 9144)
            d_tx.width = int(3.3 * 9144)

    def _statement(self, prs: Presentation, data: dict, idx: int, total: int) -> None:
        """S03 — 核心概念大字页"""
        accent = self.palette["accent"]
        paper = self.palette["paper"]
        ink = self.palette["ink"]

        slide = prs.add_slide()
        self._set_bg(slide, paper)

        title = _esc(data.get("title", ""))
        content = _esc(data.get("content", ""))

        # 页码
        self._add_folio(slide, idx, total, ink)

        # 大字
        txf = slide.add_text_frame()
        txf.add_paragraph()
        txf.text_frame.text = title
        txf.text_frame.paragraphs[0].font.size = Pt(54)
        txf.text_frame.paragraphs[0].font.color.rgb = ink
        txf.text_frame.paragraphs[0].font.name = "Inter Tight"
        txf.text_frame.paragraphs[0].bold = True
        txf.text_frame.paragraphs[0].line_spacing = 1.1
        txf.left = int(0.8 * 9144)
        txf.top = int(2.0 * 9144)
        txf.width = int(11 * 9144)
        txf.height = int(2.0 * 9144)

        # hairline 分隔线
        line = prs.add_shape(
            1, int(0.8 * 9144), int(4.2 * 9144), int(0.8 * 9144), int(0.04 * 9144)
        )
        line.fill.solid()
        line.fill.fore_color.rgb = accent
        line.line.fill.background()

        # 正文
        if content:
            txf2 = slide.add_text_frame()
            txf2.add_paragraph()
            txf2.text_frame.text = content
            txf2.text_frame.paragraphs[0].font.size = Pt(14)
            txf2.text_frame.paragraphs[0].font.color.rgb = RGBColor(0x44, 0x44, 0x44)
            txf2.text_frame.paragraphs[0].font.name = "Inter"
            txf2.text_frame.paragraphs[0].line_spacing = 1.6
            txf2.left = int(0.8 * 9144)
            txf2.top = int(4.5 * 9144)
            txf2.width = int(9 * 9144)

    def _content_fallback(self, prs: Presentation, data: dict, idx: int, total: int) -> None:
        """默认内容页"""
        accent = self.palette["accent"]
        paper = self.palette["paper"]
        ink = self.palette["ink"]

        slide = prs.add_slide()
        self._set_bg(slide, paper)

        title = _esc(data.get("title", f"第{idx + 1}页"))
        content = _esc(data.get("content", ""))

        # 左侧 accent 竖线
        self._accent_border_left(slide, accent)

        # 页码
        self._add_folio(slide, idx, total, ink)

        # 标题
        txf = slide.add_text_frame()
        txf.add_paragraph()
        txf.text_frame.text = title
        txf.text_frame.paragraphs[0].font.size = Pt(26)
        txf.text_frame.paragraphs[0].font.color.rgb = accent
        txf.text_frame.paragraphs[0].font.name = "Inter Tight"
        txf.text_frame.paragraphs[0].bold = True
        txf.left = int(0.8 * 9144)
        txf.top = int(0.5 * 9144)
        txf.width = int(11 * 9144)
        txf.height = int(0.7 * 9144)

        # 正文
        if content:
            txf2 = slide.add_text_frame()
            txf2.add_paragraph()
            txf2.text_frame.text = content
            txf2.text_frame.paragraphs[0].font.size = Pt(14)
            txf2.text_frame.paragraphs[0].font.color.rgb = ink
            txf2.text_frame.paragraphs[0].font.name = "Inter"
            txf2.text_frame.paragraphs[0].line_spacing = 1.7
            txf2.left = int(0.8 * 9144)
            txf2.top = int(1.5 * 9144)
            txf2.width = int(11 * 9144)

    # ── 存根布局（后续可扩展）─────────────────────────────────────────────

    def _timeline(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _three_sub_cards(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _kpi_tower(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _h_bar_chart(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _duo_compare(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _closing_manifesto(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _dot_matrix(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _horizontal_timeline(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _manifesto_banner(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _three_forces(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _loop_diagram(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _image_matrix(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _multi_card(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _system_diagram(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _why_now(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _four_cards(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _stacked_kpi(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _tech_spec(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _image_hero(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
    def _code_example(self, prs, data, idx, total): self._content_fallback(prs, data, idx, total)
