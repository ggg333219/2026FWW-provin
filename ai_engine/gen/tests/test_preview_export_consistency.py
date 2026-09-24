"""预览 HTML 与 PPTX 导出的同源语义一致性回归测试。"""

from pptx import Presentation

from ai_engine.gen.export_ppt import PPTExporter, resolve_node_type
from ai_engine.gen.preview import PreviewRenderer


def _six_node_snapshot() -> list[dict]:
    return [
        {
            "node_id": "n1", "type": "cover", "node_type": "cover",
            "title": "排序算法课堂", "content": "六节点同源验收",
        },
        {
            "node_id": "n2", "type": "section", "node_type": "section",
            "title": "学习目录", "content": "从概念到实践",
            "key_points": ["理解复杂度", "比较典型算法"],
        },
        {
            "node_id": "n3", "type": "content", "node_type": "content",
            "title": "复杂度基础", "content": "复杂度描述算法规模增长趋势。",
            "key_points": ["时间复杂度", "空间复杂度"],
            "core_points": ["时间复杂度", "空间复杂度"],
            "segments": [
                {"segment_type": "opening", "text": "从查找成绩的耗时问题导入。", "estimated_seconds": 45},
                {"segment_type": "explanation", "text": "讲解大O表示法。", "estimated_seconds": 90},
            ],
        },
        {
            "node_id": "n4", "type": "two_column", "node_type": "two_column",
            "title": "算法对比", "content": "比较不同排序算法。",
            "key_points": ["冒泡排序稳定", "快速排序平均更快"],
            "core_points": ["冒泡排序稳定", "快速排序平均更快"],
            "segments": [
                {"segment_type": "example", "text": "对比O(n²)与O(n log n)。", "estimated_seconds": 60},
            ],
        },
        {
            "node_id": "n5", "type": "quiz", "node_type": "quiz",
            "title": "课堂检测", "questions": ["哪种算法平均复杂度为O(n log n)？"],
        },
        {
            "node_id": "n6", "type": "summary", "node_type": "summary",
            "title": "课程小结", "key_points": ["选择算法要结合数据规模", "关注时间与空间权衡"],
            "core_points": ["选择算法要结合数据规模", "关注时间与空间权衡"],
        },
    ]


def _ppt_text(nodes: list[dict]) -> tuple[Presentation, str]:
    prs = Presentation(PPTExporter().export_to_bytes(nodes, "六节点同源验收"))
    text = "\n".join(
        shape.text
        for slide in prs.slides
        for shape in slide.shapes
        if hasattr(shape, "text")
    )
    return prs, text


def test_conflicting_type_resolution_matches_preview():
    node = {
        "node_id": "conflict", "title": "冲突兼容样本",
        "type": "quiz", "node_type": "cover", "questions": ["预览以哪个字段为准？"],
    }
    preview_type = PreviewRenderer()._resolve_type(node)
    assert preview_type == "quiz"
    assert resolve_node_type(node) == preview_type


def test_six_node_snapshot_keeps_authored_semantics_in_preview_and_ppt():
    nodes = _six_node_snapshot()
    preview_html = PreviewRenderer().render(nodes, "六节点同源验收")
    prs, ppt_text = _ppt_text(nodes)

    authored_tokens = [
        "排序算法课堂", "六节点同源验收", "学习目录", "从概念到实践",
        "复杂度基础", "复杂度描述算法规模增长趋势。", "时间复杂度", "空间复杂度",
        "从查找成绩的耗时问题导入。", "讲解大O表示法。",
        "算法对比", "比较不同排序算法。", "冒泡排序稳定", "快速排序平均更快",
        "对比O(n²)与O(n log n)。", "课堂检测", "哪种算法平均复杂度为O(n log n)？",
        "课程小结", "选择算法要结合数据规模", "关注时间与空间权衡",
    ]
    for token in authored_tokens:
        assert token in preview_html, f"preview missing: {token}"
        assert token in ppt_text, f"ppt missing: {token}"

    assert len(prs.slides) == 6
    assert all(shape.shape_type != 13 for slide in prs.slides for shape in slide.shapes)
    assert resolve_node_type(nodes[3]) == "two_column"


def test_preview_applies_presentation_style_from_nodes():
    nodes = [{
        "node_id": "styled",
        "type": "content",
        "title": "样式预览",
        "content": "样式应反映到实时预览。",
        "metadata": {"presentation": {
            "palette": "klein-blue",
            "layout": "text",
            "font_family": "serif",
            "density": "minimal",
        }},
    }]

    html = PreviewRenderer().render(nodes, "样式预览")

    assert 'data-palette="klein-blue"' in html
    assert "font-family: 'Songti SC'" in html
    assert "--preview-slide-padding: 56px 64px 60px" in html
