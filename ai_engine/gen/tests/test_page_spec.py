"""页面内容 IR（gen/page_spec.py）与 SVG 渲染的单元测试。

这里锁的是「这一页该画什么」—— 此前预览 / 导出 / SVG 三个渲染器各自去 node
里挑字段，导致同一页面三处内容对不上、局部修改只在预览里可见。本文件断言
字段挑选已收敛到单一入口，且内容页以「图示 + 要点展开」为主体、讲稿不上幻灯片。
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
    ROLE_TEACHER,
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
    ({"type": "toc"}, "agenda"),
    ({"node_type": "agenda"}, "agenda"),
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
#
# 幻灯片是给学生看的：主体是「图示 + 正文 + 要点展开」；
# 讲稿与分段是教师用的，标成 ROLE_TEACHER，由 preview 渲染进页下方折叠区。
# =============================================================================

def _content_node() -> dict:
    return {
        "node_id": "n1",
        "type": "content",
        "title": "冒泡排序",
        "summary": "相邻比较，逆序交换。",
        "key_points": ["每轮确定一个最大值"],
        "point_details": [
            {"point": "每轮确定一个最大值", "detail": "第 i 轮结束后，末尾 i 个元素已就位。"},
        ],
        "figure": {"kind": "flow", "title": "一轮比较", "items": ["比较", "交换", "后移"]},
        "script": "第一段讲稿。第二段讲稿。",
        "segments": [
            {"segment_id": "seg_001", "text": "我们先看一个例子。", "segment_type": "opening",
             "estimated_seconds": 30},
            {"segment_id": "seg_002", "text": "每一轮把最大值冒到末尾。", "segment_type": "explanation",
             "estimated_seconds": 90},
        ],
    }


def _kinds(spec, role: str) -> list[str]:
    return [b.kind for b in spec.blocks if b.role == role]


def test_content_page_slide_shows_figure_and_point_details():
    """幻灯片主体是「图示 + 要点展开」—— 呈现要点延伸出来的东西。"""
    spec = build_page_spec(_content_node(), 1)
    primary = _kinds(spec, ROLE_PRIMARY)

    assert "figure" in primary, "图示没上幻灯片"
    assert "details" in primary, "要点展开没上幻灯片"
    assert primary.index("figure") < primary.index("details"), "图示应排在要点展开之前"


def test_content_page_keeps_script_and_segments_off_the_slide():
    """讲稿与分段是教师用的：primary / secondary 里都不该有。"""
    spec = build_page_spec(_content_node(), 1)
    on_slide = _kinds(spec, ROLE_PRIMARY) + _kinds(spec, ROLE_SECONDARY)

    assert "script" not in on_slide
    assert "segments" not in on_slide
    assert sorted(_kinds(spec, ROLE_TEACHER)) == ["script", "segments"]


def test_content_page_demotes_key_points_when_anything_else_is_primary():
    """要点只在「整页没有别的正文」时才占主位。

    有展开（details）或正文（text）时它都让位 —— 幻灯片的主位是给学生看的
    实质内容，要点清单本身不是内容，是索引。
    """
    assert "bullets" in _kinds(build_page_spec(_content_node(), 1), ROLE_SECONDARY)

    # 去掉展开、但仍有正文：正文占主位，要点仍让位
    node = _content_node()
    node.pop("point_details")
    assert "bullets" in _kinds(build_page_spec(node, 1), ROLE_SECONDARY)

    # 展开与正文都没有：要点顶上主位，不能整页没有内容
    bare = _content_node()
    bare.pop("point_details")
    bare.pop("summary")
    bare.pop("figure")
    spec = build_page_spec(bare, 1)
    assert "bullets" in _kinds(spec, ROLE_PRIMARY)


def test_content_page_keeps_body_even_when_points_exist():
    """content/summary 不能被要点挤掉 —— n3 节点两者都有，且 content 有同源断言。"""
    node = _content_node()
    node.pop("point_details")
    spec = build_page_spec(node, 1)

    text_blocks = [b for b in spec.blocks if b.kind == "text"]
    assert text_blocks and "相邻比较，逆序交换。" in block_to_html(text_blocks[0])
    # 正文与要点各出一次：要点块不能因为正文兜底又被拆一遍
    bullets = block_to_html(next(b for b in spec.blocks if b.kind == "bullets"))
    assert bullets.count("kp-item") == 1


def test_content_page_without_new_fields_degrades_gracefully():
    """老课件没有 point_details / figure：退化成要点列表，不出现空白页。"""
    spec = build_page_spec({"type": "content", "title": "旧课件", "key_points": ["甲"]}, 1)

    assert not [b for b in spec.blocks if b.kind in ("figure", "details")]
    assert block_to_html(next(b for b in spec.blocks if b.kind == "bullets"))


def test_partial_modification_changes_slide_content():
    """回归：局部修改只覆盖 script/segments，于是「改了看不见」。

    幻灯片现在画的是 point_details 与 figure，局部修改必须回写这两个字段
    才看得见 —— 这里锁住「改了就看得到」。
    """
    node = _content_node()
    before = render_page_spec_to_svg(build_page_spec(node, 1), get_theme("default"))

    modified = {
        **node,
        "point_details": [{"point": "每轮确定一个最大值", "detail": "改后的展开说明。"}],
        "figure": {"kind": "flow", "title": "改后的图示", "items": ["甲", "乙"]},
    }
    after = render_page_spec_to_svg(build_page_spec(modified, 1), get_theme("default"))

    assert "改后的展开说明。" in after and "改后的展开说明。" not in before
    assert "改后的图示" in after and "改后的图示" not in before
    assert "第 i 轮结束后" not in after


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

def test_svg_is_well_formed_xml_and_carries_student_content():
    import xml.dom.minidom as minidom

    svg = render_page_spec_to_svg(build_page_spec(_content_node(), 1), get_theme("default"))

    minidom.parseString(svg)  # 抛异常即失败
    assert 'xmlns="http://www.w3.org/1999/xhtml"' in svg, "foreignObject 内层必须声明 XHTML 命名空间"
    assert "每轮确定一个最大值" in svg
    assert "第 i 轮结束后" in svg


def test_svg_omits_teacher_blocks():
    """讲稿与分段不上幻灯片 —— 它们由 preview 渲染进折叠区，不在 SVG 里。"""
    svg = render_page_spec_to_svg(build_page_spec(_content_node(), 1), get_theme("default"))

    assert "第一段讲稿。第二段讲稿。" not in svg
    assert "我们先看一个例子。" not in svg
    assert '<section class="script-block">' not in svg
    assert '<section class="segments-block">' not in svg


def test_svg_does_not_truncate_long_text():
    """旧实现按 32 字硬折行、标题截断 40 字，会把一句话切碎。"""
    long_title = "冒泡排序的稳定性与时间复杂度分析以及常见误区辨析" * 3
    long_detail = "这是一段很长的展开说明，用来验证渲染时不会在中途被截断。" * 6
    node = {"type": "content", "title": long_title,
            "point_details": [{"point": "要点", "detail": long_detail}]}

    svg = render_page_spec_to_svg(build_page_spec(node, 1), get_theme("default"))

    assert long_title in svg, "标题被截断"
    assert long_detail in svg, "展开说明被截断或折行切碎"


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


@pytest.mark.parametrize("kind,prefix", [
    ("quiz", "💡 "), ("interactive", "🎯 "), ("summary", "📌 "), ("content", ""),
])
def test_title_badge_matches_pre_svg_look(kind, prefix):
    """标题前缀与切 SVG 前各页 <h2> 上的 emoji 一致（纯文字页则无前缀）。

    参数里带 emoji 后面的那个空格 —— _TITLE_BADGES 的取值就是「emoji + 空格」，
    断言照抄取值，别在这里另写一份前缀。
    """
    svg = render_page_spec_to_svg(
        build_page_spec({"type": kind, "title": "页面标题"}, 1), get_theme("default")
    )
    assert f">{prefix}页面标题<" in svg


# =============================================================================
# 8. 版式 JSON
# =============================================================================

@pytest.mark.parametrize("layout_id", ["cover", "section", "summary", "quiz", "interactive", "content_left_right"])
def test_layouts_load(layout_id):
    layout = get_layout(layout_id)
    assert layout["layout_id"] == layout_id
    assert layout["slide_size"] == [13.333, 7.5]
    assert layout["elements"]


def test_content_layout_has_dedicated_figure_region():
    """图示有专属区域，不与正文抢同一段空间。"""
    elements = get_layout("content_left_right")["elements"]
    assert elements["figure_region"]["type"] == "figure"
    # 图示区在右栏上半，正文区在下半，二者不重叠
    figure, content = elements["figure_region"], elements["right_panel_content"]
    assert figure["y"] + figure["height"] <= content["y"]


def test_svg_renders_figure_as_native_svg():
    """图示走原生图元而非 foreignObject —— 它正是最需要「SVG→位图」也活下来的部分。"""
    svg = render_page_spec_to_svg(build_page_spec(_content_node(), 1), get_theme("default"))

    assert "<circle" in svg, "流程图的序号徽标没画出来"
    assert "一轮比较" in svg
    assert "比较" in svg


def test_svg_merges_right_column_without_figure():
    """没有图示时右栏上下合并成一整块，不留一块空白面板。"""
    node = _content_node()
    node.pop("figure")
    svg = render_page_spec_to_svg(build_page_spec(node, 1), get_theme("default"))

    # 图示面板（y=1.42in、高 2.45in）不该再画；正文面板从 1.42in 起、高 5.35in
    assert 'y="136.3" width="775.7" height="235.2"' not in svg, "图示面板没被合并掉"
    assert 'y="136.3" width="775.7" height="513.6"' in svg, "正文面板没有占满右栏"


# =============================================================================
# 9. 预览的讲稿折叠区（教师用，默认收起）
# =============================================================================

def _preview_html(node: dict) -> str:
    from ai_engine.gen.preview import PreviewRenderer

    return PreviewRenderer().render([node], course_name="测试")


def test_preview_puts_script_and_segments_in_collapsible_panel():
    html_out = _preview_html(_content_node())

    panel_at = html_out.index('<details class="script-panel">')
    assert panel_at > html_out.index('class="slide content-slide"'), "折叠区应在幻灯片之后"
    assert '<section class="script-block"><h4>讲授文本</h4>' in html_out
    assert '<section class="segments-block"><h4>讲授分段</h4>' in html_out
    # 讲稿原文只出现在折叠区里，幻灯片区读不到
    assert html_out.index("第一段讲稿。第二段讲稿。") > panel_at
    assert html_out.index("我们先看一个例子。") > panel_at


def test_preview_omits_panel_for_legacy_node():
    """无讲稿无分段时整块不输出，不能多出一条空折叠条。"""
    html_out = _preview_html({"type": "content", "title": "旧课件", "content": "只有正文。"})

    assert '<details class="script-panel">' not in html_out
    assert "只有正文。" in html_out
