"""
版本管理模块 — S4 个性化满足核心组件

职责：
  保存课件生成快照、支持版本历史查看、对比差异、回滚、锁定。

存储结构：
  data/versions/{generation_id}/
    ├── versions.json        # 版本列表元数据
    ├── v_1.json             # 版本1完整快照
    ├── v_2.json
    └── ...

API 端点：
  GET  /api/v1/version/{gen_id}/history   — 版本历史
  POST /api/v1/version/{gen_id}/rollback  — 回滚到指定版本
  POST /api/v1/version/{gen_id}/lock      — 锁定版本
  GET  /api/v1/version/{gen_id}/diff      — 对比两个版本（?v1=1&v2=2）
  GET  /api/v1/version/{gen_id}           — 加载指定版本（?v=3）
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..core.schema import GenerationVersion, GenerationStatus, ExportStatus


# =============================================================================
# 路径与目录
# =============================================================================

def _versions_dir(gen_id: str) -> Path:
    base = Path("data/versions") / gen_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def _versions_meta_path(gen_id: str) -> Path:
    return _versions_dir(gen_id) / "versions.json"


def _version_file_path(gen_id: str, version_no: int) -> Path:
    return _versions_dir(gen_id) / f"v_{version_no}.json"


# =============================================================================
# 锁（本地线程锁 + Redis SETNX 分布式锁）
# =============================================================================

_version_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()

_VERSION_LOCK_TTL = 30  # 锁超时秒数，防止持锁进程崩溃后死锁
_version_redis_client: Optional[Any] = None


def _get_redis_client() -> Optional[Any]:
    """惰性获取 Redis 客户端，不可用则返回 None。"""
    global _version_redis_client
    if _version_redis_client is not None:
        return _version_redis_client
    import os
    if os.getenv("REDIS_ENABLED", "1") == "0":
        return None
    try:
        import redis
        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "127.0.0.1"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
        )
        client.ping()
        _version_redis_client = client
        return _version_redis_client
    except Exception:
        _version_redis_client = None
        return None


class _RedisLock:
    """Redis SETNX 分布式锁（NX+EX 原子获取，Lua 原子释放）。"""

    def __init__(self, key: str, ttl: int = _VERSION_LOCK_TTL):
        self.key = f"ai_engine:lock:{key}"
        self.ttl = ttl
        self._token: Optional[str] = None

    def acquire(self, max_retries: int = 3) -> bool:
        import time as _time
        client = _get_redis_client()
        if client is None:
            return False
        import uuid
        token = str(uuid.uuid4())
        delay = 0.1  # 100ms
        for attempt in range(max_retries):
            try:
                ok = client.set(self.key, token, nx=True, ex=self.ttl)
                if ok:
                    self._token = token
                    return True
            except Exception:
                pass
            if attempt < max_retries - 1:
                _time.sleep(delay)
                delay *= 2  # 100ms -> 200ms -> 400ms
        return False

    def release(self) -> None:
        """安全释放：仅 token 匹配时删除（Redis Lua 原子脚本）。"""
        if self._token is None:
            return
        client = _get_redis_client()
        if client is None:
            self._token = None
            return
        # Redis Lua 脚本：仅当 token 相等才 del，防止误删他人持有的锁
        lua = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
        try:
            client.eval(lua, 1, self.key, self._token)
        except Exception:
            pass
        finally:
            self._token = None

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *args) -> None:
        self.release()


def _lock_for(gen_id: str) -> threading.Lock:
    """获取本地线程锁。"""
    with _locks_guard:
        if gen_id not in _version_locks:
            _version_locks[gen_id] = threading.Lock()
        return _version_locks[gen_id]


class _DistributedLock:
    """
    两层锁：优先 Redis 分布式锁，Redis 不可用时降级为本地线程锁。
    """

    def __init__(self, gen_id: str):
        self._rlock = _RedisLock(f"version:{gen_id}")
        self._llock = _lock_for(gen_id)
        self._using_redis = False
        self._llock_pid = os.getpid()

    def __enter__(self) -> "_DistributedLock":
        current_pid = os.getpid()
        if current_pid != self._llock_pid:
            # 进程已重启（崩溃恢复），重置本地锁
            self._llock = _lock_for(self._rlock.key.split(":")[-1])
            self._llock_pid = current_pid
        if self._rlock.acquire(max_retries=3):
            self._using_redis = True
            return self
        self._llock.acquire()
        self._using_redis = False
        return self

    def __exit__(self, *args) -> None:
        if self._using_redis:
            self._rlock.release()
        else:
            self._llock.release()


def _get_title(node: Any) -> str:
    """安全获取节点标题，兼容 dict 和 Pydantic model"""
    if hasattr(node, "title"):
        return node.title or ""
    if isinstance(node, dict):
        return node.get("title", "")
    return ""


def _get_field(node: Any, field: str) -> Any:
    """安全获取节点字段，兼容 dict 和 Pydantic model"""
    if hasattr(node, field):
        return getattr(node, field, "")
    if isinstance(node, dict):
        return node.get(field, "")
    return ""


# =============================================================================
# 核心类
# =============================================================================

class VersionManager:
    """
    版本管理器。

    支持：
      save_snapshot   — 保存新版本快照
      list_versions   — 列出所有版本
      load_version    — 加载指定版本
      diff            — 对比两个版本差异
      revert_to       — 回滚到指定版本（克隆为目标版本）
      lock_version    — 锁定指定版本
    """

    def __init__(self):
        pass

    # -------------------------------------------------------------------------
    # 快照保存
    # -------------------------------------------------------------------------

    def save_snapshot(
        self,
        generation_id: str,
        nodes: list[dict],
        summary: str = "",
        parent_version: Optional[int] = None,
        metadata: Optional[dict] = None,
        page_bindings: Optional[list[dict[str, Any]]] = None,
        presentation: Optional[dict[str, Any]] = None,
    ) -> GenerationVersion:
        """
        保存当前节点树为新版本快照。

        Returns:
            GenerationVersion 新版本对象（含 version_number）
        """
        lock = _DistributedLock(generation_id)
        with lock:
            # 读取当前版本列表
            versions_meta = self._read_meta(generation_id)
            next_no = versions_meta["latest_version"] + 1
            previous_no = parent_version or versions_meta["latest_version"]
            previous = self._read_snapshot(generation_id, previous_no) if previous_no else None
            if previous is not None:
                if metadata is None:
                    metadata = dict(previous.metadata)
                if page_bindings is None:
                    page_bindings = list(previous.page_bindings)
                if presentation is None:
                    presentation = dict(previous.presentation)

            # 构建版本对象
            version = GenerationVersion(
                id=f"{generation_id}_v{next_no}",
                generation_id=generation_id,
                version_number=next_no,
                nodes_snapshot=nodes,
                page_bindings=page_bindings if page_bindings is not None else [],
                presentation=presentation if presentation is not None else {},
                summary=summary or f"版本 {next_no}",
                parent_version=parent_version,
                locked=False,
                created_at=datetime.now(),
                metadata=metadata or {},
            )

            # 写快照文件
            path = _version_file_path(generation_id, next_no)
            path.write_text(version.model_dump_json(indent=2), encoding="utf-8")

            # 更新元数据
            versions_meta["latest_version"] = next_no
            versions_meta["latest_unlocked"] = next_no
            versions_meta["versions"].append({
                "version_number": next_no,
                "id": version.id,
                "summary": version.summary,
                "locked": False,
                "created_at": version.created_at.isoformat(),
            })
            self._write_meta(generation_id, versions_meta)

            return version

    # -------------------------------------------------------------------------
    # 查询
    # -------------------------------------------------------------------------

    def list_versions(self, generation_id: str) -> list[GenerationVersion]:
        """返回指定 generation_id 的所有版本，按 version_number 升序。"""
        lock = _DistributedLock(generation_id)
        with lock:
            meta = self._read_meta(generation_id)
            result = []
            for vinfo in meta["versions"]:
                # 懒加载：只读快照文件
                snap = self._read_snapshot(generation_id, vinfo["version_number"])
                if snap:
                    result.append(snap)
            return result

    def load_version(self, generation_id: str, version: Optional[int] = None) -> Optional[GenerationVersion]:
        """
        加载指定 generation_id 的版本。

        Args:
            generation_id: 课件 ID
            version: 版本号，传 None 则加载最新版

        Returns:
            GenerationVersion 或 None
        """
        lock = _DistributedLock(generation_id)
        with lock:
            meta = self._read_meta(generation_id)
            if not meta["versions"]:
                return None
            target = version if version is not None else meta["latest_version"]
            return self._read_snapshot(generation_id, target)

    def get_version_number(self, generation_id: str) -> int:
        """返回当前最新版本号，无版本则返回 0。"""
        meta = self._read_meta(generation_id)
        return meta["latest_version"]

    # -------------------------------------------------------------------------
    # 差异对比
    # -------------------------------------------------------------------------

    def diff(self, generation_id: str, v1: int, v2: int) -> dict:
        """
        对比两个版本的差异。

        Returns:
            {
                "v1": int, "v2": int,
                "added": [{"node_id": ..., "title": ...}, ...],
                "removed": [...],
                "changed": [{"node_id": ..., "title": ..., "changes": ["内容", "顺序"]}, ...],
                "same": [...],
            }
        """
        snap1 = self._read_snapshot(generation_id, v1)
        snap2 = self._read_snapshot(generation_id, v2)
        if not snap1 or not snap2:
            return {"error": "version_not_found", "v1": v1, "v2": v2}

        nodes1 = {n.node_id if hasattr(n, "node_id") else n.get("node_id"): n for n in snap1.nodes_snapshot}
        nodes2 = {n.node_id if hasattr(n, "node_id") else n.get("node_id"): n for n in snap2.nodes_snapshot}

        all_ids = set(nodes1) | set(nodes2)

        result = {"v1": v1, "v2": v2, "added": [], "removed": [], "changed": [], "same": []}
        for nid in all_ids:
            n1 = nodes1.get(nid)
            n2 = nodes2.get(nid)
            if n1 and not n2:
                result["removed"].append({"node_id": nid, "title": _get_title(n1)})
            elif not n1 and n2:
                result["added"].append({"node_id": nid, "title": _get_title(n2)})
            elif n1 and n2:
                # 比较内容
                changes = []
                for field in ("title", "content", "node_type"):
                    if _get_field(n1, field) != _get_field(n2, field):
                        changes.append(field)
                # 比较顺序（通过列表位置判断）
                keys1 = list(nodes1.keys())
                keys2 = list(nodes2.keys())
                if keys1 != keys2:
                    changes.append("order")
                if changes:
                    result["changed"].append({"node_id": nid, "title": _get_title(n2), "changes": changes})
                else:
                    result["same"].append({"node_id": nid, "title": _get_title(n2)})

        return result

    # -------------------------------------------------------------------------
    # 回滚
    # -------------------------------------------------------------------------

    def revert_to(self, generation_id: str, target_version: int) -> GenerationVersion:
        """
        回滚到指定版本（克隆为目标版本，生成新版本号）。

        行为：
          克隆 target_version 的快照，创建一个新的可编辑版本（locked=False）。
          如果目标版本已锁定，仍可回滚，回滚出的新版本默认不锁定。
        """
        lock = _DistributedLock(generation_id)
        with lock:
            # 读取目标快照
            target = self._read_snapshot(generation_id, target_version)
            if not target:
                raise ValueError(f"版本 {target_version} 不存在")

            meta = self._read_meta(generation_id)
            new_no = meta["latest_version"] + 1

            new_version = GenerationVersion(
                id=f"{generation_id}_v{new_no}",
                generation_id=generation_id,
                version_number=new_no,
                nodes_snapshot=deepcopy(target.nodes_snapshot),
                page_bindings=deepcopy(target.page_bindings),
                presentation=deepcopy(target.presentation),
                summary=f"回滚自版本 {target_version}",
                parent_version=target_version,
                locked=False,
                created_at=datetime.now(),
                metadata={**deepcopy(target.metadata), "reverted_from": target_version},
            )

            # 写快照
            path = _version_file_path(generation_id, new_no)
            path.write_text(new_version.model_dump_json(indent=2), encoding="utf-8")

            # 更新元数据
            meta["latest_version"] = new_no
            meta["latest_unlocked"] = new_no
            meta["versions"].append({
                "version_number": new_no,
                "id": new_version.id,
                "summary": new_version.summary,
                "locked": False,
                "created_at": new_version.created_at.isoformat(),
            })
            self._write_meta(generation_id, meta)

            return new_version

    # -------------------------------------------------------------------------
    # 锁定
    # -------------------------------------------------------------------------

    def lock_version(self, generation_id: str, version: Optional[int] = None) -> GenerationVersion:
        """
        锁定指定版本（或最新版）。

        锁定后的版本不可直接修改，只能通过回滚再生成新版本。
        """
        lock = _DistributedLock(generation_id)
        with lock:
            target_no = version if version is not None else self._read_meta(generation_id)["latest_version"]
            if target_no == 0:
                raise ValueError("无可用版本")

            snap = self._read_snapshot(generation_id, target_no)
            if not snap:
                raise ValueError(f"版本 {target_no} 不存在")

            # 更新快照文件（写入 locked=True）
            snap.locked = True
            snap.summary = snap.summary or f"版本 {target_no}（已锁定）"
            path = _version_file_path(generation_id, target_no)
            path.write_text(snap.model_dump_json(indent=2), encoding="utf-8")

            # 更新元数据
            meta = self._read_meta(generation_id)
            for vinfo in meta["versions"]:
                if vinfo["version_number"] == target_no:
                    vinfo["locked"] = True
                    break
            self._write_meta(generation_id, meta)

            return snap

    # -------------------------------------------------------------------------
    # 内部工具
    # -------------------------------------------------------------------------

    def _read_meta(self, gen_id: str) -> dict:
        """读取元数据文件，不存在则返回默认空结构。"""
        path = _versions_meta_path(gen_id)
        if not path.exists():
            return {"latest_version": 0, "latest_unlocked": 0, "versions": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"latest_version": 0, "latest_unlocked": 0, "versions": []}

    def _write_meta(self, gen_id: str, meta: dict) -> None:
        """写入元数据文件。"""
        path = _versions_meta_path(gen_id)
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_snapshot(self, gen_id: str, version_no: int) -> Optional[GenerationVersion]:
        """读取指定版本的快照文件。"""
        path = _version_file_path(gen_id, version_no)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return GenerationVersion(**data)
        except (json.JSONDecodeError, OSError, Exception):
            return None


# =============================================================================
# 全局单例（main.py 级别共享）
# =============================================================================

_version_manager: Optional[VersionManager] = None


def get_version_manager() -> VersionManager:
    global _version_manager
    if _version_manager is None:
        _version_manager = VersionManager()
    return _version_manager
