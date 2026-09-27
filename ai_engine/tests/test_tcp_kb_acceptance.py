import os
import importlib

os.environ.setdefault("AI_GEN_MODE", "mock")
os.environ.setdefault("RAG_STORE_BACKEND", "memory")

from fastapi.testclient import TestClient

from ai_engine.main import app

rag_router = importlib.import_module("ai_engine.rag.router")


client = TestClient(app)


def test_tcp_seed_can_be_ingested_and_retrieved():
    rag_router._store.clear()
    seed_text = """
    # TCP 三次握手
    第一次客户端发送 SYN 和初始序列号 x。
    第二次服务端返回 SYN、ACK、序列号 y 和确认号 x+1。
    第三次客户端返回 ACK 与确认号 y+1，双方进入 ESTABLISHED。
    第三次确认让服务端知道客户端已经收到同步响应，因此不能简化为两次握手。
    """
    uploaded = client.post("/api/v1/knowledge/upload", json={
        "knowledge_base_id": "kb_tcp_acceptance",
        "texts": [seed_text],
    })
    assert uploaded.status_code == 200
    assert uploaded.json()["chunk_count"] > 0

    searched = client.post("/api/v1/rag/search", json={
        "query": "TCP 三次握手",
        "knowledge_base_ids": ["kb_tcp_acceptance"],
        "top_k": 5,
        "min_score": 0.0,
    })
    assert searched.status_code == 200
    results = searched.json()["results"]
    assert results
    assert any("三次握手" in item["content"] for item in results)
    rag_router._store.clear()
