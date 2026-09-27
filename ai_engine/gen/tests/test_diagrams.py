"""程序化图示（gen/diagrams.py）的单元测试。

图示的做法是「LLM 出结构、我们确定性地画」：模型只给 kind 与标签，几何与配色由
本模块决定。因此这里锁的是**给定结构必有确定输出**，以及脏输入一律退化成「没有
图示」而不是抛异常拖垮整页渲染。

为什么不是贴图：导出侧禁止 PICTURE 形状（test_preview_export_consistency 断言
`shape_type != 13`），且仓库没有任何文生图能力。原生 SVG 图元是唯一同时能进预览
与 .pptx 的形态。
"""

from __future__ import annotations

import sys
import re
import xml.dom.minidom as minidom
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine.gen.diagrams import render_figure_svg  # noqa: E402
from ai_engine.gen.page_spec import MAX_FIGURE_ITEMS, normalize_figure  # noqa: E402
from ai_engine.gen.templates import get_theme  # noqa: E402

_W, _H = 520.0, 240.0


def _svg(fig, width: float = _W, height: float = _H) -> str:
    return render_figure_svg(fig, get_theme("default"), width, height)


def _assert_parses(fragment: str) -> None:
    """片段必须能作为 XML 解析 —— 否则整页 SVG 会渲染失败。"""
    minidom.parseString(f'<svg xmlns="http://www.w3.org/2000/svg">{fragment}</svg>')


def _figure(kind: str) -> dict:
    """按 kind 造一份规范化后的图示描述。"""
    raw: dict = {"kind": kind, "title": f"{kind} 标题", "caption": "图 1"}
    if kind == "compare":
        raw["left"] = {"title": "左栏", "items": ["甲", "乙"]}
        raw["right"] = {"title": "右栏", "items": ["丙"]}
    else:
        raw["items"] = ["甲", "乙", "丙"]
    return normalize_figure({"figure": raw})


# =============================================================================
# 1. 四种图形都能画
# =============================================================================

@pytest.mark.parametrize("kind", ["flow", "compare", "cycle", "hierarchy"])
def test_each_kind_renders_well_formed_svg(kind):
    fig = _figure(kind)
    assert fig and fig["kind"] == kind

    fragment = _svg(fig)

    _assert_parses(fragment)
    for label in ("甲", "乙", "丙"):
        assert label in fragment, f"{kind} 缺标签 {label}"
    assert f"{kind} 标题" in fragment and "图 1" in fragment, "标题/说明行没画出来"


def test_flow_draws_numbered_steps_and_arrows():
    fragment = _svg(_figure("flow"))

    assert fragment.count("<circle") == 3, "三个步骤应各有一个序号徽标"
    assert fragment.count("<path") == 2, "三个步骤之间应有两条箭头"


def test_compare_keeps_sides_independent():
    """对比图的两栏各自取值，一边空不影响另一边。"""
    fig = normalize_figure({"figure": {
        "kind": "compare",
        "left": {"title": "冒泡排序", "items": ["稳定"]},
        "right": {"title": "快速排序", "items": ["不稳定"]},
    }})
    fragment = _svg(fig)

    _assert_parses(fragment)
    assert "冒泡排序" in fragment and "快速排序" in fragment
    assert "稳定" in fragment and "不稳定" in fragment


def test_cycle_draws_ring_and_direction_arrows():
    fragment = _svg(_figure("cycle"))

    assert "<ellipse" in fragment, "环形轨道没画出来"
    assert fragment.count("<path") == 3, "每一步都应有指向下一步的箭头"


def test_hierarchy_with_single_item_renders_one_box():
    """只有一项时不硬凑成层级，当一个居中主块画。"""
    fragment = _svg({"kind": "hierarchy", "items": ["唯一的一层"]})

    _assert_parses(fragment)
    assert "唯一的一层" in fragment


def test_chart_draws_track_bar_and_value():
    """横向条形图：每行一条轨道 + 一根实心条。

    轨道是必要的 —— 只画实心条的话，占比 3% 与"数据缺失"看起来一模一样。
    """
    fig = normalize_figure({"figure": {
        "kind": "chart", "title": "复杂度增长", "caption": "图 2",
        "series": [{"label": "冒泡", "value": 45}, {"label": "快排", "value": 12},
                   {"label": "归并", "value": 10}],
    }})
    fragment = _svg(fig)

    _assert_parses(fragment)
    for token in ("复杂度增长", "图 2", "冒泡", "快排", "归并", "45", "12", "10"):
        assert token in fragment, f"缺 {token}"
    assert fragment.count("<rect") == 6, "三行各一条轨道 + 一根实心条"


def test_chart_scales_bars_against_the_peak():
    """条形长度按最大值归一 —— 最大的那根占满轨道。"""
    fig = normalize_figure({"figure": {"kind": "chart", "series": [
        {"label": "甲", "value": 100}, {"label": "乙", "value": 50},
    ]}})
    fragment = _svg(fig)

    widths = [float(w) for w in re.findall(r'<rect[^>]*width="([\d.]+)"', fragment)]
    assert max(widths) > min(widths), "两根柱子一样长就说明没按数值缩放"


def test_matrix_draws_header_row_and_grid():
    """对比表：表头一行 + 每个对象一行，隔行换底色以便横向读。"""
    fig = normalize_figure({"figure": {
        "kind": "matrix", "title": "排序算法对比",
        "columns": ["算法", "稳定性", "平均复杂度"],
        "rows": [["冒泡排序", "稳定", "O(n²)"], ["快速排序", "不稳定", "O(n log n)"]],
    }})
    fragment = _svg(fig)

    _assert_parses(fragment)
    for token in ("算法", "稳定性", "平均复杂度", "冒泡排序", "稳定", "O(n log n)"):
        assert token in fragment, f"缺 {token}"
    assert fragment.count("<rect") == 3, "表头 + 两行"


def test_matrix_fills_ragged_rows():
    """模型给的行经常长短不一：短行补空格、长行截断，表格不会错列。"""
    fig = normalize_figure({"figure": {
        "kind": "matrix", "columns": ["甲", "乙"],
        "rows": [["只有一格"], ["甲", "乙", "多出来的"]],
    }})
    assert fig["rows"] == [["只有一格", ""], ["甲", "乙"]]
    _assert_parses(_svg(fig))


# =============================================================================
# 2. 文本策略：不切碎 token
# =============================================================================

def test_labels_go_through_foreignobject_without_truncation():
    """长标签原样进 foreignObject，由浏览器换行 —— 硬切会把 token 切碎
    （预览/导出一致性测试是按完整串断言的）。"""
    long_text = "这是一个相当长的图示标签，用来验证渲染时不会被截断。" * 4
    fragment = _svg({"kind": "flow", "items": [long_text, "短"]})

    assert long_text in fragment, "标签被截断或折行切碎"
    assert "<foreignObject" in fragment


def test_labels_are_xml_escaped():
    """标签含尖括号时必须转义，否则 SVG 会被解析成非法 XML。"""
    fragment = _svg({"kind": "flow", "items": ["a < b & c"]})

    assert "&lt;" in fragment and "&amp;" in fragment and "<b" not in fragment
    _assert_parses(fragment)


# =============================================================================
# 3. 脏数据一律退化成「没有图示」
# =============================================================================

@pytest.mark.parametrize("raw", [
    None, "flow", [], 42,
    {"kind": "flow"},                        # 没有 items
    {"kind": "flow", "items": []},
    {"kind": "treemap", "items": ["甲"]},    # 未登记的 kind
    {"kind": "compare"},                     # 两栏都空
    {"kind": "compare", "left": {}, "right": {}},
])
def test_normalize_figure_rejects_dirty_input(raw):
    assert normalize_figure({"figure": raw}) is None


def test_normalize_figure_caps_items_and_accepts_dicts():
    fig = normalize_figure({"figure": {
        "kind": "flow",
        "items": [{"text": "甲"}, {"label": "乙"}, "", "丙", "丁", "戊", "己"],
    }})

    assert fig["items"] == ["甲", "乙", "丙", "丁", "戊"], "空值应丢弃、dict 应取 text/label"
    assert len(fig["items"]) == MAX_FIGURE_ITEMS


@pytest.mark.parametrize("width,height", [(0, 200), (500, 0), (-1, -1)])
def test_render_returns_empty_for_degenerate_box(width, height):
    assert _svg(_figure("flow"), width, height) == ""


def test_render_returns_empty_for_unusable_input():
    theme = get_theme("default")

    assert render_figure_svg(None, theme, _W, _H) == ""
    assert render_figure_svg({"kind": "treemap", "items": ["甲"]}, theme, _W, _H) == ""
    # 盒高小于标题行 + 说明行时没有可画的空间
    assert render_figure_svg({"kind": "flow", "title": "标题", "caption": "说明",
                              "items": ["甲"]}, theme, _W, 40.0) == ""
