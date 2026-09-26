"""页面内容 IR（gen/page_spec.py）与 SVG 渲染的单元测试。

这里锁的是「这一页该画什么」—— 此前预览 / 导出 / SVG 三个渲染器各自去 node
里挑字段，导致同一页面三处内容对不上、局部修改只在预览里可见。本文件断言
字段挑选已收敛到单一入口，且内容页以讲稿分段为主体。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine.gen.page_spec import (  # noqa: E402
    ROLE_PRIMARY,
    ROLE_SECONDARY,
    SEG_LABEL_MISSING,
    SEG_LABEL_UNKNOWN,
    block_to_html,
    body_paragraphs,
    build_page_spec,
    extract_key_points,
    normalize_segments,
    resolve_kind,
    split_content_into_points,
)
from ai_engine.gen.svg_renderer import render_node_to_svg, render_page_spec_to_svg  # noqa: E402
from ai_engine.gen.templates import get_layout, get_theme  # noqa: E402


# =============================================================================
# 1. 页面类型识别
# =============================================================================

@pytest.mark.parametrize("node,expected", [
    ({"type": "cover"}, "cover"),
    ({"node_type": "cover"}, "cover"),
    ({"type": "title"}, "cover"),          # 老版模板值
    ({"type": "quiz"}, "quiz"),
    ({"type": "question"}, "quiz"),
    ({"type": "interactive"}, "interactive"),
    ({"type": "activity"}, "interactive"),
    ({"type": "toc"}, "section"),
    ({"type": "divider"}, "section"),
    ({"type": "summary"}, "summary"),
    ({"type": "slide"}, "content"),
    ({"type": "two_column"}, "content"),   # 未登记的页型兜底为内容页
    ({}, "content"),
    ({"type": "  QUIZ  "}, "quiz"),
])
def test_resolve_kind(node, expected):
    assert resolve_kind(node) == expected


def test_resolve_kind_prefers_type_over_node_type():
    """两字段冲突时以 type 为准 —— 与 preview._resolve_type 的历史行为一致。"""
    assert resolve_kind({"type": "quiz", "node_type": "cover"}) == "quiz"


def test_resolve_kind_handles_pydantic_enum():
    """node_type 可能是 Pydantic 枚举，需取其 value。"""
    class _Enum:
        value = "section"

    assert resolve_kind({"node_type": _Enum()}) == "section"


# =============================================================================
# 2. 字段提取
# =============================================================================

def test_extract_key_points_priority_and_fallback():
    node = {"key_points": ["A"], "core_points": ["B"], "content": "C。D。"}
    assert extract_key_points(node) == ["A"]

    node.pop("key_points")
    assert extract_key_points(node) == ["B"]

    # 要点全缺时按正文拆分兜底
    assert extract_key_points({"content": "C。D。"}) == ["C", "D"]


def test_extract_key_points_accepts_newline_string():
    assert extract_key_points({"key_difficulties": "甲\n乙"}) == ["甲", "乙"]


def test_split_content_into_points_prefers_lines_then_sentences():
    assert split_content_into_points("第一行\n第二行") == ["第一行", "第二行"]
    assert split_content_into_points("一句话。另一句话。") == ["一句话", "另一句话"]
    assert split_content_into_points("") == []


def test_body_paragraphs_keeps_content_then_summary():
    """content 在真实链路里从不被赋值，但仍要读它 —— 历史课件与手工编辑写它。"""
    assert body_paragraphs({"content": "正文", "summary": "摘要"}) == ["正文", "摘要"]
    assert body_paragraphs({"summary": "摘要"}) == ["摘要"]
    assert body_paragraphs({}) == []


# =============================================================================
# 3. 分段归一
# =============================================================================

def test_normalize_segments_labels_and_fallbacks():
    segs = normalize_segments({"segments": [
        {"text": "开场", "segment_type": "opening", "estimated_seconds": 30},
        {"text": "无类型"},
        {"text": "未知类型", "segment_type": "demo_type"},
    ]})

    assert [s["label"] for s in segs] == ["导入", SEG_LABEL_MISSING, SEG_LABEL_UNKNOWN]
    assert segs[0]["seconds"] == 30
    assert segs[1]["seconds"] == 0


def test_normalize_segments_drops_empty_and_tolerates_non_dict():
    segs = normalize_segments({"segments": ["纯字符串分段", {"text": "   "}, "", {"no_text": 1}]})
    assert [s["text"] for s in segs] == ["纯字符串分段"]


def test_normalize_segments_keeps_difficulty_icon():
    segs = normalize_segments({"segments": [
        {"text": "难", "difficulty": "hard"},
        {"text": "未知难度", "difficulty": "??"},
    ]})
    assert segs[0]["difficulty_icon"] == "🔴"
    assert segs[1]["difficulty_icon"] == ""


# =============================================================================
# 4. 内容页区块模型（本次需求的核心）
# =============================================================================

def _content_node() -> dict:
    return {
        "node_id": "n1",
        "type": "content",
        "title": "冒泡排序",
        "summary": "相邻比较，逆序交换。",
        "key_points": ["每轮确定一个最大值"],
        "script": "第一段讲稿。第二段讲稿。",
        "segments": [
            {"segment_id": "seg_001", "text": "我们先看一个例子。", "segment_type": "opening",
             "estimated_seconds": 30},
            {"segment_id": "seg_002", "text": "每一轮把最大值冒到末尾。", "segment_type": "explanation",
             "estimated_seconds": 90},
        ],
    }


def test_content_page_puts_segments_first_and_demotes_key_points():
    """内容页：讲稿分段是主体（primary），核心要点降为次要（secondary）。"""
    spec = build_page_spec(_content_node(), 1)

    primary = [b.kind for b in spec.blocks if b.role == ROLE_PRIMARY]
    secondary = [b.kind for b in spec.blocks if b.role == ROLE_SECONDARY]

    assert primary[0] == "segments", "分段必须是首个主区块"
    assert "bullets" in secondary, "核心要点应降到次要位"
    assert "bullets" not in primary


def test_content_page_promotes_script_when_segments_absent():
    """没有分段时，讲稿原文接过主体位置 —— 不能因此整页没有主内容。"""
    node = _content_node()
    node.pop("segments")
    spec = build_page_spec(node, 1)

    primary = [(b.kind, b.role) for b in spec.blocks if b.role == ROLE_PRIMARY]
    assert ("script", ROLE_PRIMARY) in primary


def test_content_page_script_demoted_when_segments_present():
    """有分段时 script 是分段文本的拼接，降为次要避免与分段重复占主位。"""
    spec = build_page_spec(_content_node(), 1)
    script_blocks = [b for b in spec.blocks if b.kind == "script"]
    assert script_blocks and script_blocks[0].role == ROLE_SECONDARY


def test_partial_modification_changes_primary_block():
    """回归：局部修改只覆盖 script/segments，必须落在主区块上才看得见。

    改动前分段不在内容页主体里（导出的内容页甚至完全不读它），
    于是「改了看不见」。这里锁住「改了就看得到」。
    """
    node = _content_node()
    before = build_page_spec(node, 1)
    before_text = block_to_html(next(b for b in before.blocks if b.kind == "segments"))

    modified = {
        **node,
        "script": "改后的讲稿。",
        "segments": [{"segment_id": "seg_001", "text": "改后的第一段。",
                      "segment_type": "summary", "estimated_seconds": 45}],
    }
    after = build_page_spec(modified, 1)
    after_html = block_to_html(next(b for b in after.blocks if b.kind == "segments"))

    assert "我们先看一个例子。" in before_text and "改后的第一段。" not in before_text
    assert "改后的第一段。" in after_html and "我们先看一个例子。" not in after_html
    assert after_html != before_text


# =============================================================================
# 5. 其余页型的区块
# =============================================================================

def test_cover_uses_subtitle_and_points():
    spec = build_page_spec({"type": "cover", "title": "排序算法", "content": "副标题",
                            "key_points": ["甲", "乙"]}, 1)
    assert spec.kind == "cover" and spec.subtitle == "副标题"
    assert [b.cls for b in spec.blocks] == ["cover-points"]


def test_section_prefers_children_over_points():
    spec = build_page_spec({"type": "section", "title": "目录", "content": "本章",
                            "children": ["第一节", "第二节"], "key_points": ["忽略我"]}, 2)
    assert spec.subtitle == "本章"
    assert spec.blocks[0].items == ["第一节", "第二节"]
    assert spec.blocks[0].cls == "section-list" and spec.blocks[0].with_index is True


def test_quiz_flattens_interactive_items_when_questions_missing():
    spec = build_page_spec({
        "type": "interactive", "title": "互动",
        "interactive_items": [
            {"type": "quiz", "questions": ["Q1"]},
            {"type": "video", "questions": ["不该出现"]},
        ],
    }, 3)
    assert spec.blocks[0].kind == "questions"
    assert spec.blocks[0].items == ["Q1"]


def test_summary_blocks_order():
    spec = build_page_spec({"type": "summary", "title": "小结",
                            "key_points": ["甲"], "script": "讲稿"}, 4)
    assert [b.kind for b in spec.blocks] == ["bullets", "script"]

    # 分段存在时追加在讲稿之前
    spec2 = build_page_spec({"type": "summary", "title": "小结", "key_points": ["甲"],
                             "script": "讲稿",
                             "segments": [{"text": "段", "segment_type": "opening"}]}, 4)
    assert [b.kind for b in spec2.blocks] == ["bullets", "segments", "script"]


def test_page_spec_title_and_index_fallbacks():
    spec = build_page_spec({}, 7)
    assert spec.title == "第7页" and spec.index == 7 and spec.kind == "content"


# =============================================================================
# 6. block_to_html 的 markup 契约
# =============================================================================

def test_segments_markup_contract():
    """class 名是既有契约（scripts/verify_preview_render.py 按精确串断言）。"""
    spec = build_page_spec(_content_node(), 1)
    html = block_to_html(next(b for b in spec.blocks if b.kind == "segments"))

    assert '<section class="segments-block"><h4>讲授分段</h4>' in html
    assert '<ol class="segments">' in html
    assert '<li class="seg-item">' in html
    assert '<p class="seg-text">我们先看一个例子。</p>' in html
    assert '>导入</span>' in html
    assert '<span class="seg-dur">⏱ 30秒</span>' in html


def test_bullets_markup_contract():
    spec = build_page_spec(_content_node(), 1)
    html = block_to_html(next(b for b in spec.blocks if b.kind == "bullets"))
    assert '<li class="kp-item"><span class="kp-highlight">每轮确定一个最大值</span></li>' in html


def test_script_markup_contract():
    spec = build_page_spec(_content_node(), 1)
    html = block_to_html(next(b for b in spec.blocks if b.kind == "script"))
    assert html.startswith('<section class="script-block"><h4>讲授文本</h4>')
    assert '第一段讲稿。第二段讲稿。' in html


def test_question_markup_contract():
    spec = build_page_spec({"type": "quiz", "title": "测验", "questions": [
        {"question": "选哪个？", "options": ["A项", "B项"], "answer": "A", "explanation": "因为A"},
    ]}, 1)
    html = block_to_html(spec.blocks[0])

    assert '<ol class="questions">' in html
    assert '<li class="q-item"><p class="q-text">选哪个？</p>' in html
    assert '<li class="q-option q-option-answer">' in html
    assert '<li class="q-option">' in html
    assert '解析：因为A' in html


def test_text_escapes_html():
    """正文含尖括号时要转义，否则 SVG 会被解析成非法 XML。"""
    spec = build_page_spec({"type": "content", "title": "T", "content": "a < b & c"}, 1)
    html = block_to_html(next(b for b in spec.blocks if b.kind == "text"))
    assert "&lt;" in html and "&amp;" in html and "<b" not in html


# =============================================================================
# 7. SVG 渲染
# =============================================================================

def test_svg_is_well_formed_xml_and_carries_content():
    import xml.dom.minidom as minidom

    svg = render_page_spec_to_svg(build_page_spec(_content_node(), 1), get_theme("default"))

    minidom.parseString(svg)  # 抛异常即失败
    assert 'xmlns="http://www.w3.org/1999/xhtml"' in svg, "foreignObject 内层必须声明 XHTML 命名空间"
    assert "我们先看一个例子。" in svg
    assert "每轮确定一个最大值" in svg


def test_svg_does_not_truncate_long_text():
    """旧实现按 32 字硬折行、标题截断 40 字，会把一句话切碎。"""
    long_title = "冒泡排序的稳定性与时间复杂度分析以及常见误区辨析" * 3
    long_text = "这是一段很长的讲稿内容，用来验证渲染时不会在中途被截断。" * 6
    node = {"type": "content", "title": long_title, "script": long_text}

    svg = render_page_spec_to_svg(build_page_spec(node, 1), get_theme("default"))

    assert long_title in svg, "标题被截断"
    assert long_text in svg, "讲稿被截断或折行切碎"


def test_svg_skips_full_bleed_background_overlay():
    """嵌在 HTML 卡片里时不能画整页底色，否则会盖掉卡片的圆角与渐变。"""
    spec = build_page_spec({"type": "cover", "title": "封面"}, 1)
    embedded = render_page_spec_to_svg(spec, get_theme("default"))
    standalone = render_page_spec_to_svg(
        spec, get_theme("default"), paint_background=True, responsive=False
    )

    assert standalone.count("<rect") > embedded.count("<rect")
    assert 'width="100%"' in embedded and 'width="100%"' not in standalone


def test_render_node_to_svg_keeps_legacy_signature():
    """test_pipeline.py 仍按 (node, index, theme_id) 调用。"""
    svg = render_node_to_svg({"title": "TCP三次握手原理", "type": "content",
                              "core_points": ["SYN"]}, 1, "default")
    assert "<svg" in svg and "TCP三次握手原理" in svg


def test_svg_uses_presentation_style_of_node():
    """节点自带样式层时，SVG 配色应随之变化（导出与预览同源）。"""
    node = {"type": "content", "title": "样式", "summary": "正文",
            "metadata": {"presentation": {"palette": "klein-blue"}}}
    svg = render_node_to_svg(node, 1, "default")
    assert "#315FD4" in svg.upper(), "样式层配色未落到 SVG"


# =============================================================================
# 8. 版式 JSON
# =============================================================================

@pytest.mark.parametrize("layout_id", ["cover", "section", "summary", "quiz", "interactive", "content_left_right"])
def test_layouts_load(layout_id):
    layout = get_layout(layout_id)
    assert layout["layout_id"] == layout_id
    assert layout["slide_size"] == [13.333, 7.5]
    assert layout["elements"]
