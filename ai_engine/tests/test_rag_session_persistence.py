"""Regression tests for S2-to-KB session handoff persistence."""

import importlib

from ai_engine.core.redis_client import RedisTaskStore
from ai_engine.core.schema import Chunk, SourceType

rag_router = importlib.import_module("ai_engine.rag.router")


class SharedHashClient:
    """Small Redis hash double shared by independently-created store clients."""

    def __init__(self, hashes: dict[str, dict[str, str]]) -> None:
        self.hashes = hashes

    def hmset(self, key: str, mapping: dict[str, str]) -> bool:
        self.hashes[key] = dict(mapping)
        return True

    def hgetall(self, key: str) -> dict[str, str]:
        return self.hashes.get(key, {})


def test_session_chunks_recover_from_shared_store_after_local_state_is_lost(monkeypatch):
    shared_hashes: dict[str, dict[str, str]] = {}
    writer = RedisTaskStore()
    writer._redis = SharedHashClient(shared_hashes)
    reader = RedisTaskStore()
    reader._redis = SharedHashClient(shared_hashes)
    monkeypatch.setattr(rag_router, "get_redis_task_store", lambda: writer)

    session_id = "session-persist-test"
    chunk = Chunk(
        chunk_id="chunk-persist-test",
        source_type=SourceType.PDF,
        source_ref="lesson.pdf",
        page_ref=3,
        content="可跨进程恢复的教学证据。",
        metadata={"knowledge_base_id": "shared-kb"},
    )
    rag_router._session_parsed_chunks.pop(session_id, None)
    rag_router.register_session_chunks(session_id, [chunk], intent_id="intent-1")

    rag_router._session_parsed_chunks.pop(session_id, None)
    monkeypatch.setattr(rag_router, "get_redis_task_store", lambda: reader)
    restored = rag_router._find_session_chunks(session_id)

    assert len(restored) == 1
    assert restored[0].chunk_id == chunk.chunk_id
    assert restored[0].source_ref == "lesson.pdf"
    assert restored[0].page_ref == 3
    assert restored[0].metadata["knowledge_base_id"] == "shared-kb"
