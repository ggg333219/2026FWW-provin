from ai_engine.gen.elements import (
    apply_element_update,
    build_element_snapshot,
    resolve_element_candidates,
)


def _nodes():
    return [{
        "node_id": "node_001",
        "title": "快速排序",
        "summary": "理解分治思想",
        "content": "选择基准并递归划分数组。",
        "script": "讲解快速排序。",
        "metadata": {},
    }, {
        "node_id": "node_002",
        "title": "复杂度分析",
        "summary": "比较时间复杂度",
        "content": "平均复杂度为 O(n log n)。",
        "script": "讲解复杂度。",
        "metadata": {},
    }]


def test_build_snapshot_assigns_stable_semantic_element_ids():
    first = build_element_snapshot(_nodes())
    second = build_element_snapshot(first)

    first_ids = [element["element_id"] for element in first[0]["metadata"]["elements"]]
    second_ids = [element["element_id"] for element in second[0]["metadata"]["elements"]]
    assert first_ids == second_ids
    assert first_ids[0] == "el_node_001_title"
    assert {item["element_type"] for item in first[0]["metadata"]["elements"]} >= {"text"}


def test_resolve_candidates_returns_ambiguous_matches_without_guessing():
    nodes = build_element_snapshot(_nodes())
    result = resolve_element_candidates("把标题改短", nodes)

    assert result["status"] == "ambiguous"
    assert len(result["candidates"]) == 2
    assert result["requires_confirmation"] is True


def test_resolve_candidates_uses_page_and_role():
    nodes = build_element_snapshot(_nodes())
    result = resolve_element_candidates("第二页左侧标题改短", nodes)

    assert result["status"] == "resolved"
    assert result["target_element_ids"] == ["el_node_002_title"]


def test_apply_element_update_changes_text_and_preserves_other_nodes():
    nodes = build_element_snapshot(_nodes())
    updated = apply_element_update(
        nodes,
        ["el_node_001_title"],
        action="rewrite",
        replacement="快速排序：分治与划分",
    )

    assert updated[0]["title"] == "快速排序：分治与划分"
    assert updated[0]["metadata"]["elements"][0]["content"] == "快速排序：分治与划分"
    assert updated[1]["title"] == "复杂度分析"
