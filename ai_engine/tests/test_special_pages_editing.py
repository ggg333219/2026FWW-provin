from __future__ import annotations

from ai_engine.gen.deck_structure import expand_deck_pages
from ai_engine.gen.partial_content import apply_page_revision


def _content_nodes(count: int = 6) -> list[dict]:
    return [
        {
            "node_id": f"node_{index}",
            "title": f"第 {index} 节",
            "node_type": "content",
            "summary": f"内容 {index}",
            "key_points": [f"要点 {index}"],
        }
        for index in range(1, count + 1)
    ]


def test_explicit_agenda_is_not_duplicated() -> None:
    nodes = [
        {"node_id": "__auto_cover__", "title": "排序算法", "node_type": "cover"},
        {"node_id": "__auto_toc__", "title": "目录", "node_type": "agenda", "key_points": ["第一节"]},
        *_content_nodes(),
        {"node_id": "__auto_summary__", "title": "本节小结", "node_type": "summary"},
    ]

    expanded = expand_deck_pages(nodes, "排序算法")

    assert [node["node_id"] for node in expanded].count("__auto_toc__") == 1
    assert [node["node_id"] for node in expanded].count("__auto_summary__") == 1


def test_special_page_revision_updates_visible_fields() -> None:
    page = {
        "node_id": "__auto_cover__",
        "title": "排序算法",
        "content": "AI 智能生成课件",
        "summary": "",
        "node_type": "cover",
        "key_points": [],
    }

    updated = apply_page_revision(page, {
        "title": "算法设计基础",
        "content": "从问题建模到复杂度分析",
        "summary": "从问题建模到复杂度分析",
    })

    assert updated["title"] == "算法设计基础"
    assert updated["content"] == "从问题建模到复杂度分析"
    assert updated["summary"] == "从问题建模到复杂度分析"


def test_normal_page_identity_remains_protected() -> None:
    page = {"node_id": "node_1", "title": "原标题", "node_type": "content", "summary": "原文"}

    updated = apply_page_revision(page, {"title": "模型误改标题", "summary": "新正文"})

    assert updated["title"] == "原标题"
    assert updated["summary"] == "新正文"
