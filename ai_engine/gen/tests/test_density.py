"""H5 疏密排版三档 —— 参数表 / SVG 预览 / PPTX 导出 三处联动的自动化对比。

验收要求：三档导出的 PPTX（或 page_spec 几何值）有明显差异断言。
本文件锁三件事：
  1. 参数表三档取值互不相同（且 comfortable 档 = 改造前既有行为）；
  2. 同一节点在 compact / loose 下渲染出的 SVG 几何（区块平移量）不同；
  3. 同一节点三档导出的 PPTX 正文字号（随 body_font_scale 缩放）严格递增。
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine.gen.page_spec import (  # noqa: E402
    DENSITY_ALIASES,
    DENSITY_PROFILES,
    DENSITY_TIERS,
    FALLBACK_DENSITY,
    density_profile,
    pptx_line_height_factor,
    resolve_density,
)
from ai_engine.gen.export_ppt import PPTExporter  # noqa: E402
from ai_engine.gen.presentation import DENSITY_PADDING, FALLBACK_DENSITY_PADDING  # noqa: E402
from ai_engine.gen.svg_renderer import render_page_spec_to_svg  # noqa: E402
from ai_engine.gen.page_spec import build_page_spec  # noqa: E402
from ai_engine.gen.templates import get_theme  # noqa: E402


# =============================================================================
# 1. 参数表
# =============================================================================

def test_density_table_has_three_distinct_tiers():
    assert DENSITY_TIERS == ("compact", "comfortable", "loose")
    # 越松：间距/边距/行距/段距越大
    for key in ("block_gap_px", "region_padding_px", "line_spacing",
                "paragraph_gap_pt", "point_card_pad_px", "point_card_gap_px"):
        assert DENSITY_PROFILES["compact"][key] < DENSITY_PROFILES["comfortable"][key] < \
            DENSITY_PROFILES["loose"][key], f"{key} 三档应严格递增"
    # 越松：每页容量系数越小
    assert DENSITY_PROFILES["compact"]["body_fill"] > DENSITY_PROFILES["comfortable"]["body_fill"] \
        > DENSITY_PROFILES["loose"]["body_fill"]
    # 三档 css_padding 互不相同
    assert len({DENSITY_PROFILES[t]["css_padding"] for t in DENSITY_TIERS}) == 3


def test_resolve_density_normalizes_and_keeps_legacy_minimal():
    assert resolve_density("compact") == "compact"
    assert resolve_density("COMFORTABLE ") == "comfortable"
    assert resolve_density("minimal") == "loose", "历史 minimal（大留白）映射到 loose"
    assert resolve_density("nonsense") == FALLBACK_DENSITY
    assert resolve_density(None) == FALLBACK_DENSITY
    assert DENSITY_ALIASES["minimal"] == "loose"


def test_comfortable_matches_preexisting_export_behavior():
    """comfortable 档必须等于改造前的写死值，未选密度的课件导出不变。"""
    profile = density_profile("comfortable")
    assert profile["block_gap_px"] == 10.0
    assert profile["region_padding_px"] == 16.0
    assert profile["line_spacing"] == pytest.approx(1.13)
    assert profile["paragraph_gap_pt"] == 7.0
    assert profile["body_fill"] == pytest.approx(0.97)
    # 行高系数 ≈ 改造前的 1.35（1.2 × 1.13 = 1.356）
    assert pptx_line_height_factor("comfortable") == pytest.approx(1.356)
    # presentation.DENSITY_PADDING（预览 CSS）与参数表同源
    assert DENSITY_PADDING["comfortable"] == FALLBACK_DENSITY_PADDING
    assert DENSITY_PADDING["loose"] == DENSITY_PROFILES["loose"]["css_padding"]


# =============================================================================
# 2. SVG 预览几何随密度变化
# =============================================================================

def _layout_node() -> dict:
    return {
        "node_id": "n1",
        "type": "content",
        "title": "冒泡排序",
        "key_points": ["每轮确定一个最大值", "相邻元素两两比较"],
        "point_details": [
            {"point": "每轮确定一个最大值", "detail": "第 i 轮结束后，末尾 i 个元素已就位。"},
            {"point": "相邻元素两两比较", "detail": "比较发生在相邻元素之间，逆序即交换。"},
        ],
    }


def _svg_translates(density: str) -> list[tuple[float, float]]:
    spec = build_page_spec(_layout_node(), 1)
    svg = render_page_spec_to_svg(spec, get_theme("default"), density=density)
    pairs = re.findall(r'translate\((-?[\d.]+), (-?[\d.]+)\)', svg)
    return [(float(x), float(y)) for x, y in pairs]


def test_preview_svg_geometry_differs_by_density():
    compact = _svg_translates("compact")
    loose = _svg_translates("loose")
    assert compact and loose
    assert compact != loose, "compact 与 loose 的 SVG 区块平移量应有明显差异"


def test_preview_svg_comfortable_matches_legacy_geometry():
    """comfortable 档（默认不传）的几何必须与改造前完全一致。"""
    assert _svg_translates("comfortable") == _svg_translates(FALLBACK_DENSITY)


def test_preview_html_carries_density_attribute():
    from ai_engine.gen.preview import PreviewRenderer

    node = {**_layout_node(), "metadata": {"presentation": {"density": "loose"}}}
    html_out = PreviewRenderer().render([node], course_name="密度预览")
    assert 'data-density="loose"' in html_out


# =============================================================================
# 3. PPTX 导出几何随密度变化
# =============================================================================

@pytest.mark.parametrize("density,expected_size", [
    ("compact", 14),   # round(15 × 0.94)
    ("comfortable", 15),
    ("loose", 16),     # round(15 × 1.06)
])
def test_pptx_body_font_size_follows_density(density, expected_size):
    node = {
        "node_id": "n1",
        "type": "content",
        "title": "冒泡排序",
        "content": "这是一个用于验证疏密排版三档的正文段落，长度足够撑起一个正文面板。",
        "metadata": {"presentation": {"density": density}},
    }
    buf = PPTExporter().export_to_bytes([node], "密度导出")
    assert buf.getbuffer().nbytes > 0

    from pptx import Presentation

    prs = Presentation(io.BytesIO(buf.getvalue()))
    sizes = set()
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for paragraph in shape.text_frame.paragraphs:
                if "疏密排版三档" in paragraph.text:
                    for run in paragraph.runs:
                        if run.font.size is not None:
                            sizes.add(run.font.size.pt)
    assert sizes == {float(expected_size)}, f"{density} 档正文字号应为 {expected_size}pt"


def test_pptx_three_distributions_differ_in_bytes_layout():
    """同一份内容三档导出的正文面板字号互不相同（验收：有明显差异断言）。"""
    sizes = []
    for density in ("compact", "comfortable", "loose"):
        node = {
            "node_id": "n1",
            "type": "content",
            "title": "冒泡排序",
            "content": "三档对比正文。",
            "metadata": {"presentation": {"density": density}},
        }
        buf = PPTExporter().export_to_bytes([node], "三档对比")
        from pptx import Presentation

        prs = Presentation(io.BytesIO(buf.getvalue()))
        found = set()
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame and "三档对比正文" in shape.text_frame.text:
                    for run in shape.text_frame.paragraphs[0].runs:
                        if run.font.size is not None:
                            found.add(run.font.size.pt)
        assert found, f"{density} 档未找到正文文本框"
        sizes.append(sorted(found)[0])
    assert sizes[0] < sizes[1] < sizes[2], f"三档字号应严格递增，实际 {sizes}"
