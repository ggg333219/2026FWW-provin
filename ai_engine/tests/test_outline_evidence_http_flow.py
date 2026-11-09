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


def test_indexed_material_flows_into_initial_outline_fallback(monkeypatch):
    store = InMemoryVectorStore()
    monkeypatch.setattr(rag_module, "_store", store)
    monkeypatch.setattr(
        rag_module, "_retriever",
        HybridRetriever(store=store, embed_service=rag_module._embed_service),
    )

    def embed_locally(chunks):
        for chunk in chunks:
            chunk.embedding = [1.0, 0.0]
        return chunks

    monkeypatch.setattr(rag_module._embed_service, "embed_chunks", embed_locally)
    monkeypatch.setattr(rag_module._embed_service, "embed_text", lambda _text: [1.0, 0.0])
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
