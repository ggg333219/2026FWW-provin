"""F04: index S2 session chunks by ID without replacing their source."""

import importlib

import pytest
from docx import Document
from fastapi import HTTPException

from ai_engine.core.schema import Chunk, SourceType
from ai_engine.parse.task_manager import TaskManager
from ai_engine.rag.store import InMemoryVectorStore


rag_router = importlib.import_module("ai_engine.rag.router")


class SessionStoreDouble:
    def __init__(self):
        self.saved = {}

    def save_session_data(self, session_id, data):
        self.saved[session_id] = data

    def load_session_data(self, session_id):
        return self.saved.get(session_id)


def run_coroutine(coroutine):
    # These two coroutines have no suspending await points in this test path.
    with pytest.raises(StopIteration) as completed:
        coroutine.send(None)
    return completed.value.value


def invoke_upload(request):
    return run_coroutine(rag_router.knowledge_upload(request))


@pytest.fixture
def indexed_session(monkeypatch):
    session_store = SessionStoreDouble()
    vector_store = InMemoryVectorStore()
    monkeypatch.setattr(rag_router, "_session_parsed_chunks", {})
    monkeypatch.setattr(rag_router, "get_redis_task_store", lambda: session_store)
    monkeypatch.setattr(rag_router, "_store", vector_store)
    monkeypatch.setattr(rag_router._embed_service, "embed_chunks", lambda chunks: chunks)
    monkeypatch.setattr(rag_router._retriever, "rebuild_bm25", lambda: None)

    chunks = [
        Chunk(chunk_id="f04-a", source_type=SourceType.DOCX,
              source_ref="lesson.docx", content="第一段", seq_index=0),
        Chunk(chunk_id="f04-b", source_type=SourceType.DOCX,
              source_ref="lesson.docx", content="第二段", seq_index=1),
    ]
    rag_router.register_session_chunks("session-f04", chunks)
    # Simulate a new worker loading the registered chunks from shared storage.
    rag_router._session_parsed_chunks.clear()
    return vector_store


def test_chunk_ids_preserve_source_and_limit_deleted_material(indexed_session):
    response = invoke_upload(rag_router.KnowledgeUploadRequest(
        session_id="session-f04", chunk_ids=["f04-a"]
    ))
    assert response.status == "done"
    assert response.chunk_count == 1
    stored = indexed_session.get_chunk("f04-a")
    assert stored.source_ref == "lesson.docx"
    assert stored.source_type == SourceType.DOCX
    assert indexed_session.get_chunk("f04-b") is None


def test_docx_status_ids_match_registered_chunks_and_can_be_indexed(
    indexed_session, tmp_path
):
    path = tmp_path / "f04-lesson.docx"
    document = Document()
    document.add_heading("F04 资料", level=1)
    document.add_paragraph("可重建的 DOCX 来源测试内容。")
    document.save(path)

    manager = TaskManager()
    task = manager.create_task(session_id="docx-session-f04", file_paths=[str(path)])
    run_coroutine(manager.run_task(task.task_id))
    status = manager.get_task_status(task.task_id)
    registered = rag_router._find_session_chunks("docx-session-f04")
    status_ids = [chunk.chunk_id for chunk in status.chunks]
    assert status_ids
    assert status_ids == [chunk.chunk_id for chunk in registered]

    response = invoke_upload(rag_router.KnowledgeUploadRequest(
        session_id="docx-session-f04", chunk_ids=status_ids
    ))
    assert response.chunk_count == len(status_ids)
    assert all(indexed_session.get_chunk(chunk_id).source_ref == str(path) for chunk_id in status_ids)


def test_explicit_empty_chunk_ids_do_not_fall_back_to_session(indexed_session):
    request = rag_router.KnowledgeUploadRequest(session_id="session-f04", chunk_ids=[])
    assert request.chunk_ids == []
    assert rag_router.KnowledgeUploadRequest(session_id="session-f04").chunk_ids is None
    response = invoke_upload(request)
    assert response.chunk_count == 0
    assert response.document_id == ""
    assert indexed_session.count() == 0


def test_unknown_chunk_id_fails_without_partial_index(indexed_session):
    with pytest.raises(HTTPException) as error:
        invoke_upload(rag_router.KnowledgeUploadRequest(
            session_id="session-f04", chunk_ids=["f04-a", "missing"]
        ))
    assert error.value.status_code == 400
    assert "missing" in error.value.detail
    assert indexed_session.count() == 0


def test_legacy_texts_upload_remains_available(indexed_session):
    response = invoke_upload(rag_router.KnowledgeUploadRequest(
        session_id="session-f04", texts=["手动添加文本"]
    ))
    assert response.chunk_count > 0
    stored = indexed_session.get_chunk("manual_0::s0000")
    assert stored.source_ref == "manual_0"
    assert indexed_session.get_chunk("f04-a") is None


def test_legacy_session_only_request_still_indexes_registered_chunks(indexed_session):
    response = invoke_upload(rag_router.KnowledgeUploadRequest(session_id="session-f04"))
    assert response.chunk_count == 2
    assert indexed_session.get_chunk("f04-a").source_ref == "lesson.docx"
    assert indexed_session.get_chunk("f04-b").source_ref == "lesson.docx"
