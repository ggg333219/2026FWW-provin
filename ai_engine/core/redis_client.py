"""
Redis 任务持久化客户端 (core/redis_client.py)

为 S3 生成任务和 S4 导出任务提供跨进程持久化存储。

使用方式：
    from ai_engine.core.redis_client import get_redis_task_store

    store = get_redis_task_store()
    await store.save_task("task_001", task_data)
    data = await store.load_task("task_001")

环境变量：
    REDIS_HOST     — Redis 地址（默认 127.0.0.1）
    REDIS_PORT     — Redis 端口（默认 6379）
    REDIS_PASSWORD — 密码（默认空）
    REDIS_DB       — 数据库编号（默认 0）
    REDIS_PREFIX   — key 前缀（默认 ai_engine:）
    REDIS_ENABLED  — 设为 0 强制禁用 Redis，改用内存回退（默认 1）

当 Redis 不可用时，自动回退到进程内 dict，不影响正常业务。
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any, Optional

_TASKS_KEY_PREFIX = "tasks"
_EXPORT_KEY_PREFIX = "exports"


# =============================================================================
# Redis 客户端（懒初始化 + 回退）
# =============================================================================

class _RedisClient:
    """Redis 客户端，含连接失败回退到内存 dict 的保护机制。"""

    def __init__(self):
        self._client: Optional[Any] = None
        self._available: bool | None = None  # None=未检测，True=可用，False=不可用
        self._host = os.getenv("REDIS_HOST", "127.0.0.1")
        self._port = int(os.getenv("REDIS_PORT", "6379"))
        self._password = os.getenv("REDIS_PASSWORD") or None
        self._db = int(os.getenv("REDIS_DB", "0"))
        self._prefix = os.getenv("REDIS_PREFIX", "ai_engine:")
        self._enabled = os.getenv("REDIS_ENABLED", "1") != "0"

    @property
    def client(self) -> Optional[Any]:
        """惰性获取 Redis 客户端，不可用则返回 None。"""
        if not self._enabled:
            return None
        if self._available is False:
            return None
        if self._client is None:
            self._connect()
        return self._client

    def _connect(self) -> None:
        """尝试连接 Redis，失败则标记为不可用。"""
        try:
            import redis
            self._client = redis.Redis(
                host=self._host,
                port=self._port,
                password=self._password,
                db=self._db,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=5,
            )
            self._client.ping()
            self._available = True
        except Exception:
            self._available = False
            self._client = None

    def hmset(self, key: str, mapping: dict[str, str]) -> bool:
        """Hash multi-set。失败返回 False（不抛异常）。"""
        try:
            if self.client is None:
                return False
            full_key = f"{self._prefix}{key}"
            self.client.hset(full_key, mapping=mapping)
            return True
        except Exception:
            self._available = False
            return False

    def hgetall(self, key: str) -> dict[str, str]:
        """Hash get all fields。失败返回空 dict。"""
        try:
            if self.client is None:
                return {}
            full_key = f"{self._prefix}{key}"
            return self.client.hgetall(full_key) or {}
        except Exception:
            self._available = False
            return {}

    def delete(self, key: str) -> bool:
        """Delete key。失败返回 False。"""
        try:
            if self.client is None:
                return False
            full_key = f"{self._prefix}{key}"
            self.client.delete(full_key)
            return True
        except Exception:
            self._available = False
            return False

    @property
    def is_available(self) -> bool:
        """当前 Redis 是否可用。"""
        if not self._enabled:
            return False
        if self._available is False:
            return False
        if self._client is None:
            self._connect()
        return self._available is True


# =============================================================================
# 内存回退存储（同步 + 线程安全）
# =============================================================================

class _InMemoryTaskStore:
    """纯内存任务存储（Redis 不可用时的同步回退）。"""

    def __init__(self):
        self._tasks: dict[str, str] = {}
        self._exports: dict[str, str] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _json_str(data: dict) -> str:
        return json.dumps(data, ensure_ascii=False, default=str)

    @staticmethod
    def _parse(raw: Optional[str]) -> Optional[dict]:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def save_task(self, task_id: str, data: dict) -> None:
        with self._lock:
            self._tasks[task_id] = self._json_str(data)

    def load_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            return self._parse(self._tasks.get(task_id))

    def delete_task(self, task_id: str) -> None:
        with self._lock:
            self._tasks.pop(task_id, None)

    def save_export(self, job_id: str, data: dict) -> None:
        with self._lock:
            self._exports[job_id] = self._json_str(data)

    def load_export(self, job_id: str) -> Optional[dict]:
        with self._lock:
            return self._parse(self._exports.get(job_id))


# =============================================================================
# Redis 任务存储（异步 API，内部用线程池调用同步 redis-py）
# =============================================================================

class RedisTaskStore:
    """
    Redis 任务持久化存储（异步接口）。

    - Redis 可用时：任务写入 Redis Hash，跨进程/跨 worker 共享
    - Redis 不可用时：自动降级到进程内 dict，不影响本地运行
    """

    def __init__(self):
        self._redis = _RedisClient()
        self._mem = _InMemoryTaskStore()
        self._use_redis = True  # 运行时动态判断，首次失败降级

    @property
    def is_redis_available(self) -> bool:
        return self._use_redis and self._redis.is_available

    def _key_tasks(self, task_id: str) -> str:
        return f"{_TASKS_KEY_PREFIX}:{task_id}"

    def _key_export(self, job_id: str) -> str:
        return f"{_EXPORT_KEY_PREFIX}:{job_id}"

    # ── 序列化 ────────────────────────────────────────────────────────────────

    @staticmethod
    def _serialize(data: dict) -> dict[str, str]:
        """将任务 dict 转为字符串 dict（适应 Redis Hash）。"""
        result: dict[str, str] = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = v
            elif isinstance(v, (list, dict)):
                result[k] = json.dumps(v, ensure_ascii=False, default=str)
            elif v is None:
                result[k] = ""
            else:
                result[k] = str(v)
        return result

    @staticmethod
    def _deserialize(raw: dict[str, str]) -> dict:
        """反序列化任务。"""
        result: dict = {}
        for k, v in raw.items():
            if v.startswith(("[", "{", "\"")):
                try:
                    result[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    result[k] = v
            else:
                result[k] = v
        return result

    # ── 生成任务（异步）────────────────────────────────────────────────────────

    async def save_task(self, task_id: str, task_data: dict) -> None:
        """保存生成任务（含 status/nodes/intent 等）。"""
        payload = self._serialize(task_data)
        if self._use_redis:
            ok = await asyncio.to_thread(self._redis.hmset, self._key_tasks(task_id), payload)
            if not ok:
                self._use_redis = False
        if not self._use_redis:
            self._mem.save_task(task_id, task_data)

    async def load_task(self, task_id: str) -> Optional[dict]:
        """加载生成任务。"""
        if self._use_redis:
            raw = await asyncio.to_thread(self._redis.hgetall, self._key_tasks(task_id))
            if raw:
                return self._deserialize(raw)
        return self._mem.load_task(task_id)

    async def delete_task(self, task_id: str) -> None:
        """删除生成任务。"""
        if self._use_redis:
            await asyncio.to_thread(self._redis.delete, self._key_tasks(task_id))
        self._mem.delete_task(task_id)

    # ── 导出任务（异步）──────────────────────────────────────────────────────

    async def save_export(self, job_id: str, export_data: dict) -> None:
        """保存导出任务（含 status/minio_path 等）。"""
        payload = self._serialize(export_data)
        if self._use_redis:
            ok = await asyncio.to_thread(self._redis.hmset, self._key_export(job_id), payload)
            if not ok:
                self._use_redis = False
        if not self._use_redis:
            self._mem.save_export(job_id, export_data)

    async def load_export(self, job_id: str) -> Optional[dict]:
        """加载导出任务。"""
        if self._use_redis:
            raw = await asyncio.to_thread(self._redis.hgetall, self._key_export(job_id))
            if raw:
                data = self._deserialize(raw)
                for field in (
                    "completed_at", "download_url", "error", "file_size",
                    "minio_path", "quality_report",
                ):
                    if data.get(field) == "":
                        data[field] = None
                return data
        return self._mem.load_export(job_id)


# =============================================================================
# 全局单例
# =============================================================================

_redis_task_store: Optional[RedisTaskStore] = None


def get_redis_task_store() -> RedisTaskStore:
    """获取 Redis 任务存储单例（同步获取，异步方法）。"""
    global _redis_task_store
    if _redis_task_store is None:
        _redis_task_store = RedisTaskStore()
    return _redis_task_store
