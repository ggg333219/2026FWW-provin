import os
import time

os.environ.setdefault("AI_GEN_MODE", "mock")

from fastapi.testclient import TestClient

from ai_engine.core.schema import Chunk, EvidenceResponse, SearchResult, SourceType
from ai_engine.main import app
from ai_engine.rag.router import _session_parsed_chunks

import importlib

rag_router_module = importlib.import_module("ai_engine.rag.router")


client = TestClient(app)


def _wait_content(content_id: str) -> dict:
    for _ in range(200):
        response = client.get(f"/gen/content/status/{content_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"done", "failed"}:
            return body
        time.sleep(0.01)
    raise AssertionError("内容生成任务未在测试窗口内完成")


def test_rag_search_filters_chunks_by_node_scope():
    session_id = "member_b_scope_test"
    _session_parsed_chunks.pop(session_id, None)
    rag_router_module._store.clear()
    chunks = [
        Chunk(
            chunk_id="scope_node_a",
            source_type=SourceType.TEXT,
            source_ref="scope.md",
            content="冒泡排序节点的相邻元素比较",
            page_ref=1,
            metadata={"node_id": "node_a", "page_id": "page_1"},
        ),
        Chunk(
            chunk_id="scope_node_b",
            source_type=SourceType.TEXT,
            source_ref="scope.md",
            content="快速排序节点的分区操作",
            page_ref=2,
            metadata={"node_id": "node_b", "page_id": "page_2"},
        ),
    ]
    _session_parsed_chunks[session_id] = {"chunks": chunks, "intent_id": None}

    uploaded = client.post("/api/v1/knowledge/upload", json={"session_id": session_id})
    assert uploaded.status_code == 200

    response = client.post(
        "/api/v1/rag/search",
        json={"query": "排序 节点", "scope": "node", "node_id": "node_a", "min_score": 0.0},
    )
    assert response.status_code == 200
    assert {item["chunk_id"] for item in response.json()["results"]} == {"scope_node_a"}

    _session_parsed_chunks.pop(session_id, None)
    rag_router_module._store.clear()


def test_rag_search_passes_offset_and_returns_total_result_count(monkeypatch):
    seen = {}

    class PagedRetriever:
        def search_page(self, **kwargs):
            seen.update(kwargs)
            return [SearchResult(chunk_id="page-2", content="第二页结果", score=0.9)], 27

    monkeypatch.setattr(rag_router_module, "_get_retriever", lambda: PagedRetriever())
    response = client.post("/api/v1/rag/search", json={
        "query": "分页检索", "top_k": 10, "offset": 10, "min_score": 0.0,
    })

    assert response.status_code == 200
    body = response.json()
    assert seen["top_k"] == 10
    assert seen["offset"] == 10
    assert body["total_results"] == 27
    assert [item["chunk_id"] for item in body["results"]] == ["page-2"]


def test_evidence_uses_only_teacher_confirmed_chunk_ids(monkeypatch):
    rag_router_module._store.clear()
    rag_router_module._store.insert_batch([Chunk(
        chunk_id="teacher-confirmed",
        source_type=SourceType.TEXT,
        source_ref="shared.pdf",
        content="已确认内容",
    )], doc_id="shared-doc")
    captured = {}

    class CapturingSynthesizer:
        def synthesize_to_response(self, **kwargs):
            captured.update(kwargs)
            return EvidenceResponse()

    monkeypatch.setattr(rag_router_module, "_synthesizer", CapturingSynthesizer())
    response = client.post("/api/v1/rag/evidence", json={
        "query": "课件主题", "selected_chunk_ids": ["teacher-confirmed"],
    })

    assert response.status_code == 200
    assert [item.chunk_id for item in captured["search_results"]] == ["teacher-confirmed"]
    assert captured["search_results"][0].content == "已确认内容"
    rag_router_module._store.clear()


def test_interactive_content_generation_returns_playable_html():
    response = client.post(
        "/gen/content",
        json={
            "nodes": [
                {
                    "node_id": "interactive_001",
                    "node_type": "interactive",
                    "type": "interactive",
                    "title": "冒泡排序互动题",
                    "content": "判断冒泡排序是否通过相邻元素比较完成排序。",
                }
            ],
            "mode": "mock",
        },
    )
    assert response.status_code == 200
    body = _wait_content(response.json()["content_id"])
    assert body["status"] == "done"
    node = body["nodes"][0]
    assert node["interactive_items"]
    assert "<!DOCTYPE html>" in node["content"]
    assert "冒泡排序互动题" in node["content"]


def test_preview_and_html5_export_share_interactive_content():
    node = {
        "node_id": "interactive_002",
        "node_type": "interactive",
        "type": "interactive",
        "title": "快速排序测验",
        "interactive_items": [
            {
                "type": "quiz",
                "title": "快速排序测验",
                "questions": [
                    {
                        "question": "快速排序的核心操作是什么？",
                        "options": ["分区", "合并"],
                        "answer": "A",
                    }
                ],
            }
        ],
    }

    preview = client.post("/api/v1/gen/preview", json={"nodes": [node]})
    assert preview.status_code == 200
    preview_html = preview.json()["html"]

    from ai_engine.gen.export_html5 import render_interactive_html, extract_interactive_items

    export_html = render_interactive_html(extract_interactive_items([node]), "快速排序")
    assert "快速排序的核心操作是什么？" in preview_html
    assert "快速排序的核心操作是什么？" in export_html
