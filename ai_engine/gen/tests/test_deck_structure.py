"""deck_structure 合成页（封面 / 目录 / 小结）的装配与幂等。

教师可以在 S3「课件首尾页」里接管这三页，接管后它们以 ``__auto_`` 前缀
进入节点树。装配层必须认出它们、不再重复注入一份，否则 PPT 里会出现两个
封面 / 两个目录。
"""

from __future__ import annotations

import pytest

from ai_engine.gen.deck_structure import (
    AUTO_COVER_ID,
    AUTO_SUMMARY_ID,
    AUTO_TOC_ID,
    expand_deck_pages,
)


def _content_nodes(count: int) -> list[dict]:
    return [
        {
            "node_id": f"n{i}",
            "title": f"第 {i} 节",
            "node_type": "content",
            "key_points": [f"要点 {i}"],
        }
        for i in range(1, count + 1)
    ]


def test_auto_pages_injected_for_plain_outline():
    """普通大纲（6 个内容节点）：封面 → 目录 → 内容 → 小结。"""
    expanded = expand_deck_pages(_content_nodes(6), "数据结构")
    ids = [node["node_id"] for node in expanded]
    assert ids[0] == AUTO_COVER_ID
    assert ids[1] == AUTO_TOC_ID
    assert ids[-1] == AUTO_SUMMARY_ID
    assert len(expanded) == 9


def test_toc_skipped_when_teacher_took_over():
    """教师接管目录页后已在树里：不得再注入第二个目录。"""
    nodes = _content_nodes(6)
    taken = {
        "node_id": AUTO_TOC_ID,
        "title": "本课程目录",
        "content": "教师改过的引导语",
        "node_type": "agenda",
        "key_points": ["教师改过的条目"],
    }
    # 教师接管的目录页已在树里（前端保证它排在封面之后），装配层不得再补一个
    expanded = expand_deck_pages([taken, *nodes], "数据结构")

    toc_pages = [n for n in expanded if n["node_id"] == AUTO_TOC_ID]
    assert len(toc_pages) == 1
    # 教师写的内容必须原样保留，不能被默认值覆盖
    assert toc_pages[0]["content"] == "教师改过的引导语"
    assert toc_pages[0]["key_points"] == ["教师改过的条目"]


def test_cover_not_duplicated_when_taken_over():
    nodes = _content_nodes(3)
    taken = {
        "node_id": AUTO_COVER_ID,
        "title": "教师改的封面标题",
        "content": "教师改的副标题",
        "node_type": "cover",
    }
    expanded = expand_deck_pages([taken, *nodes], "数据结构")
    assert [n for n in expanded if n["node_id"] == AUTO_COVER_ID][0]["title"] == "教师改的封面标题"
    assert len([n for n in expanded if n["node_id"] == AUTO_COVER_ID]) == 1


def test_summary_not_duplicated_when_taken_over():
    nodes = _content_nodes(3)
    taken = {
        "node_id": AUTO_SUMMARY_ID,
        "title": "课后回顾",
        "content": "教师改的引导语",
        "node_type": "summary",
        "key_points": ["教师改的要点"],
    }
    expanded = expand_deck_pages([*nodes, taken], "数据结构")
    assert len([n for n in expanded if n["node_id"] == AUTO_SUMMARY_ID]) == 1
    assert expanded[-1]["title"] == "课后回顾"


def test_empty_nodes_still_yields_cover():
    """空节点也要出封面 —— 导出永不空白。"""
    expanded = expand_deck_pages([], "课件")
    assert expanded
    assert expanded[0]["node_id"] == AUTO_COVER_ID


@pytest.mark.parametrize("count", [1, 5, 6])
def test_toc_threshold(count: int):
    """目录页只在内容节点数超过阈值（5）时出现。"""
    expanded = expand_deck_pages(_content_nodes(count), "课件")
    has_toc = any(n["node_id"] == AUTO_TOC_ID for n in expanded)
    assert has_toc is (count > 5)


def test_input_not_mutated():
    nodes = _content_nodes(6)
    snapshot = [dict(n) for n in nodes]
    expand_deck_pages(nodes, "课件")
    assert nodes == snapshot
