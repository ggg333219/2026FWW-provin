"""F03: a 45-minute outline must be teachable before it is marked model-successful."""

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
