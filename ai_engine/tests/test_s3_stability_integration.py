import asyncio

from ai_engine.core.redis_client import RedisTaskStore
from ai_engine.gen.validator import ContentValidator
from ai_engine.gen.version import _DistributedLock


def test_redis_task_store_falls_back_to_memory(monkeypatch):
    monkeypatch.setenv("REDIS_ENABLED", "0")
    store = RedisTaskStore()

    async def round_trip():
        payload = {"status": "done", "nodes": [{"title": "示例"}]}
        await store.save_task("task-smoke", payload)
        return await store.load_task("task-smoke")

    restored = asyncio.run(round_trip())
    assert restored == {"status": "done", "nodes": [{"title": "示例"}]}


def test_content_validator_marks_oversized_content():
    node = {"node_id": "n1", "type": "content", "content": "x" * 500}
    validator = ContentValidator()
    result = validator.validate(node)

    assert result.oversized is True
    assert validator.compute_scaled_font(node, result)["font_size_hint"] == "small"


def test_distributed_lock_does_not_release_unacquired_local_lock():
    class RedisLockStub:
        released = False

        def acquire(self, max_retries=3):
            return True

        def release(self):
            self.released = True

    class LocalLockStub:
        def acquire(self):
            raise AssertionError("local lock must not be acquired")

        def release(self):
            raise AssertionError("local lock must not be released")

    lock = _DistributedLock("generation-smoke")
    lock._rlock = RedisLockStub()
    lock._llock = LocalLockStub()

    with lock:
        pass

    assert lock._rlock.released is True
