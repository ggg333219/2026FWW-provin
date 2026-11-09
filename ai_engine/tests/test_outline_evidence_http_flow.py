"""Exercise the real RAG and outline HTTP routes with a controlled model failure."""

import importlib

from fastapi.testclient import TestClient

from ai_engine import main as main_module
from ai_engine.gen.outline import OutlineBuilder
from ai_engine.rag.retrieve import HybridRetriever
from ai_engine.rag.store import InMemoryVectorStore


rag_module = importlib.import_module("ai_engine.rag.router")


class FailingLLM:
    def chat_with_schema(self, *_args, **_kwargs):
        raise TimeoutError("controlled model timeout")


class FallbackBuilder(OutlineBuilder):
    def __init__(self):
        super().__init__(llm_client=FailingLLM())


def test_successful_model_outline_binds_only_matching_evidence_ids():
    class SuccessfulLLM:
        def chat_with_schema(self, *_args, **_kwargs):
            titles = ["排序算法导入", "冒泡排序原理", "快速排序原理", "课堂练习", "总结"]
            return {"nodes": [
                {"node_id": f"node_{index:03d}", "title": title,
                 "summary": title, "node_type": "slide",
                 "key_points": [title], "estimated_duration_minutes": 9}
                for index, title in enumerate(titles, start=1)
            ]}

    result = OutlineBuilder(llm_client=SuccessfulLLM()).build(
        intent={"topic": "排序算法", "duration_minutes": 45,
                "knowledge_points": ["冒泡排序", "快速排序"]},
        evidence_packet={"relevant_chunks": [
            {"chunk_id": "bubble_ref", "content": "冒泡排序比较并交换相邻元素。"},
            {"chunk_id": "quick_ref", "content": "快速排序通过枢轴划分序列。"},
        ], "citations": [
            {"chunk_id": "invented_ref", "text_snippet": "冒泡排序比较并交换相邻元素。"},
        ]},
    )
    assert result["used_fallback"] is False
    by_title = {node["title"]: node["source_chunk_ids"] for node in result["nodes"]}
    assert by_title["冒泡排序原理"] == ["bubble_ref"]
    assert by_title["快速排序原理"] == ["quick_ref"]
    assert by_title["排序算法导入"] == []
    assert by_title["课堂练习"] == []
    assert all("invented_ref" not in refs for refs in by_title.values())


def test_indexed_material_flows_into_initial_outline_fallback(monkeypatch):
    store = InMemoryVectorStore()
    monkeypatch.setattr(rag_module, "_store", store)
    monkeypatch.setattr(
        rag_module, "_retriever",
        HybridRetriever(store=store, embed_service=rag_module._embed_service),
    )

    def embed_locally(chunks):
        for chunk in chunks:
            chunk.embedding = [0.0, 0.0]
        return chunks

    monkeypatch.setattr(rag_module._embed_service, "embed_chunks", embed_locally)
    monkeypatch.setattr(rag_module._embed_service, "embed_text", lambda _text: [0.0, 0.0])
    monkeypatch.setattr(main_module, "OutlineBuilder", FallbackBuilder)
    client = TestClient(main_module.app)

    upload = client.post("/api/v1/knowledge/upload", json={
        "session_id": "outline-http-flow",
        "texts": ["冒泡排序通过比较相邻元素完成排序。快速排序以枢轴划分序列。"],
    })
    assert upload.status_code == 200, upload.text
    document_id = upload.json()["document_id"]
    chunk_ids = store.list_chunk_ids(document_id)
    assert chunk_ids

    # S3's first entry uses automatic retrieval, without selected_chunk_ids.
    evidence = client.post("/api/v1/rag/evidence", json={"query": "冒泡排序"})
    assert evidence.status_code == 200, evidence.text
    packet = evidence.json()["evidence_packet"]
    assert packet["relevant_chunks"][0]["content"]
    assert packet["relevant_chunks"][0]["chunk_id"] in chunk_ids

    unrelated = client.post("/api/v1/rag/evidence", json={"query": "牛顿第二定律 力与加速度 质量"})
    assert unrelated.status_code == 200, unrelated.text
    assert unrelated.json()["evidence_packet"]["relevant_chunks"] == []

    outline = client.post("/gen/outline", json={
        "intent": {
            "topic": "排序算法",
            "duration_minutes": 45,
            "knowledge_points": ["冒泡排序", "快速排序"],
        },
        "evidence_packet": packet,
    })
    assert outline.status_code == 200, outline.text
    result = outline.json()
    assert result["used_fallback"] is True
    assert result["fallback_reason"] == "timeout"
    assert any(
        node["title"] == "冒泡排序" and node["source_chunk_ids"] == chunk_ids
        and "比较相邻元素" in node["summary"]
        for node in result["nodes"]
    )
