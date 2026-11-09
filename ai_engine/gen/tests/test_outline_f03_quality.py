"""F03: a 45-minute outline must be teachable before it is marked model-successful."""

import json
from pathlib import Path

import pytest

from ai_engine.gen.outline import OutlineBuilder


INTENT = {
    "topic": "排序算法",
    "duration_minutes": 45,
    "target_student": "大一计算机专业",
    "style": "讲练结合",
    "knowledge_points": ["冒泡排序", "快速排序", "复杂度对比"],
    "expected_outcomes": ["能选择合适的排序算法"],
}


def _nodes(titles, durations=None):
    durations = durations or [9] * len(titles)
    return [
        {
            "node_id": f"node_{index:03d}",
            "title": title,
            "summary": f"讲解{title}",
            "node_type": "slide",
            "key_points": [title],
            "estimated_duration_minutes": duration,
        }
        for index, (title, duration) in enumerate(zip(titles, durations), start=1)
    ]


GOOD = _nodes(["排序导入", "冒泡排序", "快速排序", "复杂度对比", "课堂练习", "总结"])


class SequenceLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def chat_with_schema(self, system, user, schema, **kwargs):
        self.calls.append((system, user))
        return self.responses.pop(0)


def test_single_node_is_retried_with_quality_feedback():
    llm = SequenceLLM({"nodes": _nodes(["排序算法"])}, {"nodes": GOOD})
    result = OutlineBuilder(llm_client=llm).build(INTENT)

    assert result["used_fallback"] is False
    assert len(result["nodes"]) == 6
    assert sum(node["estimated_duration_minutes"] for node in result["nodes"]) == 45
    assert "节点只有 1 个" in llm.calls[1][1]
    assert "大一计算机专业" in llm.calls[0][1]
    assert "讲练结合" in llm.calls[0][1]
    assert "能选择合适的排序算法" in llm.calls[0][1]


def test_duplicate_titles_and_missing_points_trigger_retry():
    bad = _nodes(["排序导入", "冒泡排序", "冒泡排序", "课堂练习", "总结"])
    llm = SequenceLLM({"nodes": bad}, {"nodes": GOOD})
    result = OutlineBuilder(llm_client=llm).build(INTENT)

    assert result["used_fallback"] is False
    assert "重复标题" in llm.calls[1][1]
    assert "快速排序" in llm.calls[1][1]
    assert "复杂度对比" in llm.calls[1][1]
    assert len({node["title"] for node in result["nodes"]}) == len(result["nodes"])


def test_persistently_bad_model_output_is_not_reported_as_success():
    llm = SequenceLLM({"nodes": _nodes(["排序算法"])}, {"nodes": _nodes(["排序算法"])})
    result = OutlineBuilder(llm_client=llm).build(INTENT)

    assert result["used_fallback"] is True
    assert result["fallback_reason"] == "low_quality_model_response"
    assert len(result["nodes"]) >= 5
    assert {"冒泡排序", "快速排序", "复杂度对比"}.issubset(
        {node["title"] for node in result["nodes"]}
    )


def test_model_durations_are_scaled_to_the_lesson_length():
    llm = SequenceLLM({"nodes": _nodes(
        ["排序导入", "冒泡排序", "快速排序", "复杂度对比", "课堂练习", "总结"],
        [5, 15, 15, 15, 10, 5],
    )})
    result = OutlineBuilder(llm_client=llm).build(INTENT)

    assert result["used_fallback"] is False
    assert sum(node["estimated_duration_minutes"] for node in result["nodes"]) == 45
    assert result["nodes"][1]["estimated_duration_minutes"] > result["nodes"][0]["estimated_duration_minutes"]


def test_markdown_path_also_rejects_a_single_node_lesson():
    llm = SequenceLLM({"nodes": _nodes(["排序算法"])}, {"nodes": GOOD})
    result = OutlineBuilder(llm_client=llm).build_from_markdown(
        "# 排序算法\n\n课程总时长：45分钟\n\n## 冒泡排序\n\n## 快速排序", "排序算法"
    )

    assert result["used_fallback"] is False
    assert len(result["nodes"]) == 6
    assert len(llm.calls) == 2


def test_short_markdown_keeps_a_valid_two_node_model_outline():
    llm = SequenceLLM({"nodes": _nodes(["概念", "例子"], [3, 4])})
    result = OutlineBuilder(llm_client=llm).build_from_markdown(
        "# 简短说明\n\n## 概念\n一句定义。\n\n## 例子\n一个例子。", "简短说明"
    )

    assert result["used_fallback"] is False
    assert len(result["nodes"]) == 2
    assert [node["estimated_duration_minutes"] for node in result["nodes"]] == [3, 4]
    assert len(llm.calls) == 1


def test_short_markdown_keeps_a_valid_single_node_model_outline():
    llm = SequenceLLM({"nodes": _nodes(["概念速览"], [5])})
    result = OutlineBuilder(llm_client=llm).build_from_markdown(
        "# 概念速览\n\n这是一个简短的概念说明。", "概念速览"
    )

    assert result["used_fallback"] is False
    assert [node["title"] for node in result["nodes"]] == ["概念速览"]
    assert result["nodes"][0]["estimated_duration_minutes"] == 5
    assert len(llm.calls) == 1


def test_markdown_with_intent_duration_still_requires_a_full_lesson_outline():
    llm = SequenceLLM({"nodes": _nodes(["排序算法"])}, {"nodes": GOOD})
    result = OutlineBuilder(llm_client=llm).build_from_markdown(
        "# 排序算法\n\n## 冒泡排序\n\n## 快速排序",
        duration_minutes=45,
    )

    assert result["used_fallback"] is False
    assert len(result["nodes"]) == 6
    assert len(llm.calls) == 2


def test_authentication_failure_is_not_reported_as_bad_model_json():
    class UnauthorizedLLM:
        def chat_with_schema(self, *_args, **_kwargs):
            raise RuntimeError("schema call failed: Error code: 401 invalid_api_key")

    result = OutlineBuilder(llm_client=UnauthorizedLLM()).build(INTENT)
    assert result["used_fallback"] is True
    assert result["fallback_reason"] == "model_error"


@pytest.mark.parametrize("titles, details", [
    (
        ["课程导入", "排序概览", "冒泡法原理", "冒泡法练习", "快排原理", "快排演示",
         "运行耗时分析", "等值元素顺序", "算法选型练习", "课堂总结"],
        {6: "比较不同输入规模下的时间开销", 7: "相等元素的相对顺序是否保持"},
    ),
    (
        ["导入", "排序问题", "Bubble Sort 原理", "相邻交换练习", "Quick Sort 分区",
         "分治练习", "算法运行耗时", "排序稳定性", "归纳与检测"],
        {6: "分析各算法的时间开销", 7: "稳定排序与不稳定排序"},
    ),
])
def test_rephrased_points_across_nine_or_ten_nodes_are_accepted(titles, details):
    intent = {**INTENT, "knowledge_points": ["冒泡排序", "快速排序", "时间复杂度与稳定性"]}
    nodes = _nodes(titles)
    for index, detail in details.items():
        nodes[index]["key_points"] = [detail]
    llm = SequenceLLM({"nodes": nodes})

    result = OutlineBuilder(llm_client=llm).build(intent)

    assert result["used_fallback"] is False
    assert len(result["nodes"]) == len(titles)
    assert len(llm.calls) == 1


@pytest.mark.parametrize("titles, missing", [
    (["时间复杂度", "排序练习", "总结", "复习", "算法导入"], "时间复杂度与稳定性"),
    (["排序稳定性", "空间复杂度", "排序练习", "复习", "算法导入"], "时间复杂度与稳定性"),
    (["快速排序", "排序练习", "总结", "复习", "算法导入"], "冒泡排序"),
])
def test_missing_component_or_only_shared_keywords_still_trigger_repair(titles, missing):
    nodes = _nodes(titles)
    builder = OutlineBuilder(llm_client=SequenceLLM())

    assert "缺少明确知识点：" + missing in builder._quality_issues(nodes, [missing], 45)


def test_complexity_comparison_requires_both_concepts_in_the_same_node():
    builder = OutlineBuilder(llm_client=SequenceLLM())
    nodes = _nodes(["时间复杂度", "比较排序操作", "冒泡法", "快排", "总结"])

    assert "复杂度对比" in "；".join(builder._quality_issues(nodes, ["复杂度对比"], 45))
    nodes[1]["key_points"] = ["比较两种算法的时间开销"]
    assert builder._quality_issues(nodes, ["复杂度对比"], 45) == []


def test_persistently_missing_one_composite_component_keeps_fallback():
    intent = {**INTENT, "knowledge_points": ["时间复杂度与稳定性"]}
    nodes = _nodes(["导入", "排序原理", "时间复杂度", "课堂练习", "总结"])
    llm = SequenceLLM({"nodes": nodes}, {"nodes": nodes})

    result = OutlineBuilder(llm_client=llm).build(intent)

    assert result["used_fallback"] is True
    assert result["fallback_reason"] == "low_quality_model_response"
    assert "时间复杂度与稳定性" in llm.calls[1][1]


_DIAGNOSTIC = json.loads(
    (Path(__file__).parent / "fixtures" / "pr16_outline_diagnostic_replay.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("attempt_index", [0, 1])
def test_pr16_real_model_outline_replay_is_accepted_without_retry(attempt_index):
    attempt = _DIAGNOSTIC["generation_attempts"][attempt_index]
    llm = SequenceLLM({"nodes": attempt["nodes"]})
    intent = {
        "topic": "冒泡排序",
        "duration_minutes": 45,
        "knowledge_points": _DIAGNOSTIC["requested_knowledge_points"],
    }

    result = OutlineBuilder(llm_client=llm).build(intent)

    assert result["used_fallback"] is False
    assert len(result["nodes"]) == len(attempt["nodes"])
    assert len(llm.calls) == 1


@pytest.mark.parametrize("before, after, missing", [
    ("相邻", "远距离", "冒泡排序的相邻比较与交换"),
    ("稳定", "平稳", "冒泡排序的时间复杂度与稳定性"),
    ("最大值", "当前值", "冒泡排序每轮最大值归位"),
    ("课堂练习", "课堂讲授", "用数组示例演示并设计课堂练习"),
])
def test_pr16_replay_rejects_missing_required_facet(before, after, missing):
    attempt = _DIAGNOSTIC["generation_attempts"][0]
    nodes = [
        {
            **node,
            "title": node["title"].replace(before, after),
            "summary": node["summary"].replace(before, after),
            "key_points": [value.replace(before, after) for value in node["key_points"]],
        }
        for node in attempt["nodes"]
    ]

    issues = OutlineBuilder()._quality_issues(nodes, [missing], 45)

    assert "缺少明确知识点：" + missing in issues
