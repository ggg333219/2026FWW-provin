"""The initial outline must keep selected evidence when the model fails."""

from ai_engine.gen.outline import OutlineBuilder


class FailingLLM:
    def chat_with_schema(self, *_args, **_kwargs):
        raise TimeoutError("provider unavailable")


class CapturingLLM:
    def __init__(self):
        self.prompt = ""

    def chat_with_schema(self, _system, user, _schema, **_kwargs):
        self.prompt = user
        return {"nodes": [{
            "node_id": "node_001", "title": "冒泡排序", "summary": "比较相邻元素",
            "node_type": "slide", "key_points": ["冒泡排序"],
            "estimated_duration_minutes": 5,
        }]}


def test_fallback_uses_selected_chunk_and_keeps_its_reference():
    packet = {"relevant_chunks": [{
        "chunk_id": "chapter-2-page-3", "content": "冒泡排序通过比较相邻元素完成排序。",
        "source_ref": "排序教材.pdf#p3",
    }]}
    result = OutlineBuilder(llm_client=FailingLLM()).build(
        {"topic": "排序算法", "duration_minutes": 45,
         "knowledge_points": ["冒泡排序", "快速排序"]}, packet,
    )

    assert result["used_fallback"] is True
    by_title = {node["title"]: node for node in result["nodes"]}
    assert "比较相邻元素" in by_title["冒泡排序"]["summary"]
    assert by_title["冒泡排序"]["source_chunk_ids"] == ["chapter-2-page-3"]
    assert by_title["快速排序"]["source_chunk_ids"] == []


def test_citation_only_packet_reaches_model_prompt_and_fallback():
    packet = {"citations": [{
        "chunk_id": "citation-1", "text_snippet": "快速排序以枢轴划分序列。",
        "source_ref": "算法教材.pdf#p5",
    }]}
    llm = CapturingLLM()
    result = OutlineBuilder(llm_client=llm).build({"topic": "排序算法"}, packet)

    assert result["used_fallback"] is False
    assert "快速排序以枢轴划分序列" in llm.prompt
    assert "算法教材.pdf#p5" in llm.prompt

    fallback = OutlineBuilder(llm_client=FailingLLM()).build({"topic": "排序算法"}, packet)
    assert fallback["used_fallback"] is True
    assert any("快速排序" in node["title"] for node in fallback["nodes"])
    assert any("citation-1" in node["source_chunk_ids"] for node in fallback["nodes"])


def test_intent_only_fallback_does_not_fabricate_references():
    result = OutlineBuilder(llm_client=FailingLLM()).build(
        {"topic": "排序算法", "knowledge_points": ["冒泡排序"]}, None,
    )
    assert result["used_fallback"] is True
    assert all(not node["source_chunk_ids"] for node in result["nodes"])

    topic_only = OutlineBuilder(llm_client=FailingLLM()).build({"topic": "排序算法"})
    assert all("排序算法" in node["title"] for node in topic_only["nodes"])


def test_markdown_outline_also_uses_evidence_when_model_fails():
    packet = {"relevant_chunks": [{
        "chunk_id": "ref-2", "content": "分治法将问题拆成更小的子问题。",
    }]}
    result = OutlineBuilder(llm_client=FailingLLM()).build_from_markdown(
        "# 算法设计\n\n## 分治法", "算法设计", evidence_packet=packet,
    )
    assert result["used_fallback"] is True
    assert any("分治法" in node["title"] for node in result["nodes"])
    assert any(node["source_chunk_ids"] == ["ref-2"] for node in result["nodes"])
