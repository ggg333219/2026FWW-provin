"""
异步任务调度器 (task_manager.py)

管理 S2 多模态解析的任务生命周期：

文件级状态机:
  UPLOADED → PARSING → CHUNKED → INDEXED → DONE
  UPLOADED → PARSING → FAILED (重试 2 次后)

任务级状态机:
  PENDING → PROCESSING → DONE | PARTIAL_FAIL

使用方式:
    manager = TaskManager()
    task = manager.create_task(session_id="s1", file_paths=["doc.pdf"])
    await manager.run_task(task.task_id)  # 异步执行
    status = manager.get_task_status(task.task_id)
"""

import asyncio
import json
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Optional

from ai_engine.core.schema import (
    Chunk,
    MaterialAsset,
    ParseStatus,
    SourceType,
    ParseProcessResponse,
    ParseStatusResponse,
)
from ai_engine.parse.doc_parser import DocumentParser
from ai_engine.parse.ocr_engine import OCREngine
from ai_engine.parse.video_processor import VideoProcessor
from ai_engine.parse.chunk_normalizer import ChunkNormalizer
from ai_engine.parse.material_mapper import MaterialMapper


# =============================================================================
# 内部状态类型
# =============================================================================

class FileTaskStatus(str, Enum):
    """单文件解析状态（比 ParseStatus 更细，含重试计数）。"""
    UPLOADED = "uploaded"
    PARSING = "parsing"
    CHUNKED = "chunked"
    INDEXED = "indexed"
    DONE = "done"
    FAILED = "failed"


class AggregateTaskStatus(str, Enum):
    """聚合任务状态。"""
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    PARTIAL_FAIL = "partial_fail"


# =============================================================================
# 内部数据结构
# =============================================================================

class FileTask:
    """单个文件的解析跟踪记录。"""
    def __init__(
        self,
        file_path: str,
        source_type: SourceType = SourceType.TEXT,
        retry_limit: int = 2,
    ):
        self.file_path = file_path
        self.source_type = source_type
        self.status = FileTaskStatus.UPLOADED
        self.retry_count = 0
        self.retry_limit = retry_limit
        self.chunks: list[Chunk] = []
        self.asset: Optional[MaterialAsset] = None
        self.error: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.retry_limit

    @property
    def is_terminal(self) -> bool:
        return self.status in (FileTaskStatus.DONE, FileTaskStatus.FAILED)


class AggregateTask:
    """多个文件的聚合跟踪记录。"""
    def __init__(self, session_id: str, intent_id: Optional[str] = None):
        self.task_id = f"parse_{uuid.uuid4().hex[:12]}"
        self.session_id = session_id
        self.intent_id = intent_id
        self.status = AggregateTaskStatus.PENDING
        self.files: list[FileTask] = []
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.error: Optional[str] = None

    @property
    def all_chunks(self) -> list[Chunk]:
        return [c for f in self.files for c in f.chunks]

    @property
    def failed_count(self) -> int:
        return sum(1 for f in self.files if f.status == FileTaskStatus.FAILED)

    @property
    def done_count(self) -> int:
        return sum(1 for f in self.files if f.status == FileTaskStatus.DONE)


# =============================================================================
# 文件类型推断
# =============================================================================

_FILE_EXT_MAP: dict[str, SourceType] = {
    ".pdf": SourceType.PDF,
    ".pptx": SourceType.PPTX,
    ".ppt": SourceType.PPTX,
    ".docx": SourceType.DOCX,
    ".doc": SourceType.DOCX,
    ".png": SourceType.IMAGE,
    ".jpg": SourceType.IMAGE,
    ".jpeg": SourceType.IMAGE,
    ".bmp": SourceType.IMAGE,
    ".tiff": SourceType.IMAGE,
    ".webp": SourceType.IMAGE,
    ".mp4": SourceType.VIDEO,
    ".avi": SourceType.VIDEO,
    ".mov": SourceType.VIDEO,
    ".mkv": SourceType.VIDEO,
    ".flv": SourceType.VIDEO,
    ".wmv": SourceType.VIDEO,
    ".mp3": SourceType.AUDIO,
    ".wav": SourceType.AUDIO,
    ".m4a": SourceType.AUDIO,
}


def _infer_source_type(file_path: str) -> SourceType:
    """根据文件扩展名推断 SourceType。"""
    import os
    _, ext = os.path.splitext(file_path)
    return _FILE_EXT_MAP.get(ext.lower(), SourceType.TEXT)


# =============================================================================
# TaskManager
# =============================================================================

class TaskManager:
    """
    S2 多模态解析任务管理器。

    职责：
      1. 创建解析任务（含文件列表）
      2. 异步执行所有文件的解析（含重试）
      3. 查询任务状态
      4. 返回解析结果（Chunk 列表 + 文件-块映射）

    线程安全说明：
      当前为单线程设计（FastAPI 异步 + 后台协程）。
      如需多线程并发，需加锁保护 _tasks 字典。
    """

    def __init__(self):
        # task_id → AggregateTask
        self._tasks: dict[str, AggregateTask] = {}

        # 子模块
        self._chunk_normalizer = ChunkNormalizer()
        self._material_mapper = MaterialMapper()

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def create_task(
        self,
        session_id: str,
        file_paths: list[str],
        intent_id: Optional[str] = None,
    ) -> ParseProcessResponse:
        """
        创建解析任务。

        对每个文件推断 SourceType，构造 FileTask，
        返回 task_id 和 MaterialAsset 列表。
        """
        task = AggregateTask(session_id=session_id, intent_id=intent_id)

        for fp in file_paths:
            source_type = _infer_source_type(fp)
            ft = FileTask(file_path=fp, source_type=source_type)
            ft.asset = MaterialAsset(
                asset_id=f"asset_{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                file_name=fp.split("/")[-1].split("\\")[-1],
                file_url=fp,
                source_type=source_type,
                parse_status=ParseStatus.UPLOADED,
            )
            task.files.append(ft)

        self._tasks[task.task_id] = task
        task.status = AggregateTaskStatus.PROCESSING
        task.updated_at = datetime.now()

        return ParseProcessResponse(
            task_id=task.task_id,
            status="processing",
            assets=[f.asset for f in task.files if f.asset is not None],
        )

    def get_task(self, task_id: str) -> Optional[AggregateTask]:
        """获取聚合任务对象。"""
        return self._tasks.get(task_id)

    def get_task_status(self, task_id: str) -> ParseStatusResponse:
        """查询任务状态，含已解析的 Chunk 列表。"""
        task = self._tasks.get(task_id)
        if task is None:
            return ParseStatusResponse(
                task_id=task_id,
                status=ParseStatus.FAILED,
                error=f"task_id {task_id} 不存在",
            )

        # 映射 AggregateTaskStatus → ParseStatus
        status_map = {
            AggregateTaskStatus.PENDING: ParseStatus.UPLOADED,
            AggregateTaskStatus.PROCESSING: ParseStatus.PARSING,
            AggregateTaskStatus.DONE: ParseStatus.DONE,
            AggregateTaskStatus.PARTIAL_FAIL: ParseStatus.DONE,
        }
        ps = status_map.get(task.status, ParseStatus.FAILED)

        return ParseStatusResponse(
            task_id=task_id,
            status=ps,
            chunks=task.all_chunks,
            error=task.error if task.status == AggregateTaskStatus.PARTIAL_FAIL else None,
        )

    # ------------------------------------------------------------------
    # 异步执行
    # ------------------------------------------------------------------

    async def run_task(self, task_id: str) -> None:
        """
        异步执行一个解析任务的所有文件。

        每个文件依次执行 → 重试逻辑 → 分块标准化 → 最终汇总。
        """
        task = self._tasks.get(task_id)
        if task is None:
            return

        for ft in task.files:
            await self._process_single_file(ft)
            task.updated_at = datetime.now()

        # 更新聚合状态
        all_done = all(f.is_terminal for f in task.files)
        if not all_done:
            return  # 还在处理中

        failed = [f for f in task.files if f.status == FileTaskStatus.FAILED]
        if failed and len(failed) < len(task.files):
            task.status = AggregateTaskStatus.PARTIAL_FAIL
            task.error = f"{len(failed)}/{len(task.files)} 文件解析失败"
        elif failed:
            task.status = AggregateTaskStatus.DONE  # 全部失败也算 done（含错误信息）
            task.error = "全部文件解析失败"
        else:
            task.status = AggregateTaskStatus.DONE

        task.updated_at = datetime.now()

        # 构建映射关系
        if task.all_chunks:
            self._material_mapper.build_mappings(
                task_id=task_id,
                chunks=task.all_chunks,
                intent_id=task.intent_id,
            )

    # ======================================================================
    # 流式执行（SSE）
    # ======================================================================

    async def run_task_stream(
        self,
        task_id: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        流式执行一个解析任务，逐文件 yield 事件（dict）。

        Yield 的事件:
          - {"event": "task_start",  "data": {...}}
          - {"event": "file_start",  "data": {...}}
          - {"event": "file_chunk_batch", "data": {"chunks": [...]}}
          - {"event": "file_done",   "data": {...}}
          - {"event": "file_error",  "data": {...}}
          - {"event": "task_done",   "data": {...}}
          - {"event": "task_error",  "data": {...}}

        Args:
            task_id: 已创建的 task_id（先调用 create_task 获得）。
        """
        task = self._tasks.get(task_id)
        if task is None:
            yield {"event": "task_error", "data": {"error": f"task_id {task_id} 不存在"}}
            return

        task.status = AggregateTaskStatus.PROCESSING
        task.updated_at = datetime.now()

        yield {
            "event": "task_start",
            "data": {
                "task_id": task_id,
                "file_count": len(task.files),
                "files": [
                    {
                        "file_name": f.file_path.split("/")[-1].split("\\")[-1],
                        "source_type": f.source_type.value,
                    }
                    for f in task.files
                ],
            },
        }

        for ft in task.files:
            async for evt in self._process_single_file_stream(ft):
                yield evt

        # 汇总状态
        all_terminal = all(f.is_terminal for f in task.files)
        if not all_terminal:
            return  # 不应该发生

        failed = [f for f in task.files if f.status == FileTaskStatus.FAILED]
        if failed and len(failed) < len(task.files):
            task.status = AggregateTaskStatus.PARTIAL_FAIL
            task.error = f"{len(failed)}/{len(task.files)} 文件解析失败"
        elif failed:
            task.status = AggregateTaskStatus.DONE
            task.error = "全部文件解析失败"
        else:
            task.status = AggregateTaskStatus.DONE

        task.updated_at = datetime.now()

        if task.all_chunks:
            self._material_mapper.build_mappings(
                task_id=task_id,
                chunks=task.all_chunks,
                intent_id=task.intent_id,
            )

        total_chunks = len(task.all_chunks)
        # 将 Chunk 模型转为可 JSON 序列化的字典
        chunk_dicts = [c.model_dump() for c in task.all_chunks]
        yield {
            "event": "task_done",
            "data": {
                "task_id": task_id,
                "status": task.status.value,
                "error": task.error,
                "total_chunks": total_chunks,
                "chunks": chunk_dicts,
            },
        }

    async def _process_single_file_stream(
        self,
        ft: FileTask,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式处理单个文件，yield 文件级事件。"""
        file_name = ft.file_path.split("/")[-1].split("\\")[-1]

        yield {
            "event": "file_start",
            "data": {
                "file_name": file_name,
                "source_type": ft.source_type.value,
                "file_path": ft.file_path,
            },
        }

        ft.status = FileTaskStatus.PARSING
        ft.started_at = datetime.now()

        try:
            # 1) 按文件类型解析 → 原始块
            raw_result = self._parse_by_type(ft)

            # 2) 分批 yield 原始块（按 type 分组）
            if raw_result:
                from itertools import groupby

                raw_result.sort(key=lambda r: r.get("type", "unknown"))
                for type_key, group in groupby(raw_result, key=lambda r: r.get("type", "unknown")):
                    group_list = list(group)
                    yield {
                        "event": "file_chunk_batch",
                        "data": {
                            "file_name": file_name,
                            "type": type_key,
                            "count": len(group_list),
                            "chunks": group_list,
                        },
                    }

            # 3) 标准化为 Chunk（落库）
            ft.chunks = self._chunk_normalizer.normalize(
                raw_chunks=raw_result,
                source_ref=ft.file_path,
                source_type=ft.source_type,
            )
            ft.status = FileTaskStatus.DONE
            ft.completed_at = datetime.now()
            if ft.asset:
                ft.asset.parse_status = ParseStatus.DONE

            # 4) 标准化后的 Chunk 也 yield 一份（供前端直接落库）
            yield {
                "event": "file_done",
                "data": {
                    "file_name": file_name,
                    "source_type": ft.source_type.value,
                    "chunk_count": len(ft.chunks),
                    "normalized_chunks": [c.model_dump() for c in ft.chunks],
                },
            }

        except Exception as e:
            ft.retry_count += 1
            ft.error = f"解析失败: {e}"
            ft.status = FileTaskStatus.FAILED
            ft.completed_at = datetime.now()
            if ft.asset:
                ft.asset.parse_status = ParseStatus.FAILED

            yield {
                "event": "file_error",
                "data": {
                    "file_name": file_name,
                    "source_type": ft.source_type.value,
                    "error": str(e),
                },
            }

    async def _process_single_file(self, ft: FileTask) -> None:
        """处理单个文件（含重试）。"""
        while ft.status not in (FileTaskStatus.DONE, FileTaskStatus.FAILED):
            try:
                ft.status = FileTaskStatus.PARSING
                ft.started_at = datetime.now()

                raw_result = self._parse_by_type(ft)

                ft.chunks = self._chunk_normalizer.normalize(
                    raw_chunks=raw_result,
                    source_ref=ft.file_path,
                    source_type=ft.source_type,
                )
                ft.status = FileTaskStatus.DONE
                ft.completed_at = datetime.now()

                # 更新 asset 状态
                if ft.asset:
                    ft.asset.parse_status = ParseStatus.DONE

            except Exception as e:
                ft.retry_count += 1
                ft.error = f"解析失败 (第{ft.retry_count}次): {e}"
                if ft.can_retry:
                    ft.status = FileTaskStatus.UPLOADED  # 重置，下次循环重试
                else:
                    ft.status = FileTaskStatus.FAILED
                    ft.completed_at = datetime.now()
                    if ft.asset:
                        ft.asset.parse_status = ParseStatus.FAILED

    def _parse_by_type(self, ft: FileTask) -> list[dict[str, Any]]:
        """根据 SourceType 派发到对应的解析器。"""
        st = ft.source_type

        if st in (SourceType.PDF, SourceType.PPTX, SourceType.DOCX):
            parser = DocumentParser(ft.file_path, source_type=st)
            return parser.parse()

        if st == SourceType.IMAGE:
            ocr = OCREngine()
            return ocr.process(ft.file_path)

        if st == SourceType.VIDEO:
            vp = VideoProcessor()
            return vp.process(ft.file_path)

        if st == SourceType.AUDIO:
            vp = VideoProcessor()
            return vp.process_audio(ft.file_path)

        raise ValueError(f"不支持的 SourceType: {st}")
