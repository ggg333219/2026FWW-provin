"""标准教案生成缓存。

Word 导出沿用 QOKIK 的 LessonPlanGenerator + LessonPlanDOCExporter 设计，
但同一个版本重复导出时不应该重复请求 LLM。缓存只保存已经规范化的
LessonPlan 字典，不保存 API key 或原始请求头；内存缓存用于当前进程，
磁盘缓存用于 AI Engine 重启后的同版本再次导出。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from ai_engine.gen.lesson_plan import LessonPlanGenerator

logger = logging.getLogger(__name__)

_CACHE_FORMAT_VERSION = "lesson-plan-qokik-v4-provider-shape"
_MAX_MEMORY_ITEMS = 16
_cache_lock = threading.RLock()
_memory_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
_inflight: dict[str, threading.Event] = {}


def _cache_dir() -> Path:
    configured = (os.getenv("LESSON_PLAN_CACHE_DIR") or "").strip()
    return Path(configured or "data/exports/.lesson_plan_cache")


def _as_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _as_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _as_jsonable(value.model_dump(mode="json"))
    if hasattr(value, "to_dict"):
        return _as_jsonable(value.to_dict())
    return str(value)


def lesson_plan_cache_key(
    nodes: list[dict[str, Any]],
    intent: dict[str, Any] | None,
    generation_instruction_set: dict[str, Any] | None,
) -> str:
    """为会影响教案内容的输入生成稳定 key。"""
    payload = {
        "format": _CACHE_FORMAT_VERSION,
        "nodes": _as_jsonable(nodes or []),
        "intent": _as_jsonable(intent or {}),
        "generation_instruction_set": _as_jsonable(generation_instruction_set or {}),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_disk(key: str) -> dict[str, Any] | None:
    path = _cache_dir() / f"{key}.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        # 兜底 / mock 结果不能复用：模型或网络恢复后，必须让同一版本
        # 有机会重新走 LLM，而不是永久沿用一次超时留下的模板内容。
        if not isinstance(value, dict) or value.get("data_source") != "llm":
            return None
        return value
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _write_disk(key: str, plan: dict[str, Any]) -> None:
    directory = _cache_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{key}.json"
        temporary = directory / f".{key}.{os.getpid()}.tmp"
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, separators=(",", ":"))
        temporary.replace(target)
    except OSError as exc:
        # 缓存失败不影响导出主流程；导出仍然使用刚刚生成的 plan。
        logger.warning("[lesson_plan_cache] 写入缓存失败: %s", exc)


def _remember(key: str, plan: dict[str, Any]) -> None:
    with _cache_lock:
        _memory_cache[key] = plan
        _memory_cache.move_to_end(key)
        while len(_memory_cache) > _MAX_MEMORY_ITEMS:
            _memory_cache.popitem(last=False)


def generate_lesson_plan_cached(
    nodes: list[dict[str, Any]],
    intent: dict[str, Any] | None = None,
    generation_instruction_set: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成或复用标准教案，返回可直接交给 DOCX exporter 的 dict。"""
    normalized_nodes = _as_jsonable(nodes or [])
    normalized_intent = _as_jsonable(intent or {})
    normalized_instructions = _as_jsonable(generation_instruction_set or {})
    key = lesson_plan_cache_key(
        normalized_nodes, normalized_intent, normalized_instructions,
    )

    with _cache_lock:
        cached = _memory_cache.get(key)
        if cached is not None:
            _memory_cache.move_to_end(key)
            return cached

    disk_cached = _read_disk(key)
    if disk_cached is not None:
        _remember(key, disk_cached)
        return disk_cached

    # 同一版本同时触发多个导出时，只允许一个线程访问 LLM，其余线程等待结果。
    with _cache_lock:
        event = _inflight.get(key)
        is_owner = event is None
        if is_owner:
            event = threading.Event()
            _inflight[key] = event

    if not is_owner:
        event.wait()
        with _cache_lock:
            cached = _memory_cache.get(key)
            if cached is not None:
                _memory_cache.move_to_end(key)
                return cached
        # 主线程生成失败时，等待者再独立生成，保证缓存不是单点故障。

    try:
        plan = LessonPlanGenerator().generate(
            normalized_nodes,
            normalized_intent,
            None,
            normalized_instructions,
        )
        plan_dict = _as_jsonable(plan)
        if not isinstance(plan_dict, dict):
            raise TypeError("LessonPlanGenerator 未返回对象")
        if plan_dict.get("data_source") == "llm":
            _remember(key, plan_dict)
            _write_disk(key, plan_dict)
        else:
            # 保留本次导出的可用 fallback 文件，但不把它存成下一次的答案。
            logger.info(
                "[lesson_plan_cache] skip non-LLM plan cache: source=%s",
                plan_dict.get("data_source", "unknown"),
            )
        return plan_dict
    finally:
        if is_owner:
            with _cache_lock:
                waiter = _inflight.pop(key, None)
                if waiter is not None:
                    waiter.set()


def clear_lesson_plan_cache() -> None:
    """测试或明确要求重新生成时清理当前进程缓存。"""
    with _cache_lock:
        _memory_cache.clear()
