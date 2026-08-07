"""
S2 多模态解析 FastAPI Router (router.py)

对应 Go 端已注册的 S2 路由：
  POST /api/v1/parse/process  → ParseHandler.ProcessFile
  GET  /api/v1/parse/status/:task_id → ParseHandler.ParseStatus
  POST /api/v1/parse/video    → ParseHandler.ProcessVideo

Python 端实际提供服务，Go 端通过 HTTP 调用本 router。

遵循开发规范：
  - 所有数据模型引用 ai_engine.core.schema
  - LLM 调用使用 ai_engine.core.LLMClient
  - 配置使用 ai_engine.core.settings
"""

import asyncio
import json
import os
import traceback
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ai_engine.core.schema import (
    ParseProcessRequest,
    ParseProcessResponse,
    ParseStatusResponse,
    ParseVideoRequest,
)
from ai_engine.parse.task_manager import TaskManager
from ai_engine.parse.minio_client import MinioClient

# =============================================================================
# Router 定义
# =============================================================================

router = APIRouter(prefix="/api/v1/parse", tags=["S2-MultimodalParse"])

# 全局 TaskManager 实例（单例，生命周期同应用）
task_manager = TaskManager()

# 后台任务引用缓存，防止被 GC
_background_tasks: dict[str, asyncio.Task] = {}


# =============================================================================
# 端点
# =============================================================================

@router.post("/process", response_model=ParseProcessResponse)
async def process_files(req: ParseProcessRequest) -> ParseProcessResponse:
    """
    POST /api/v1/parse/process

    接收文件路径列表，创建解析任务并异步执行。

    请求体:
        {
            "session_id": "uuid",
            "file_paths": ["path/to/file1.pdf", "path/to/file2.pptx"],
            "intent_id": "uuid"  (可选)
        }

    响应:
        {
            "task_id": "uuid",
            "status": "processing",
            "assets": [...]
        }
    """
    if not req.file_paths:
        raise HTTPException(status_code=400, detail="file_paths 不能为空")

    # 处理可能的 minio:// URL：将其下载为本地临时文件
    minio_client = MinioClient()
    resolved_paths: list[str] = []
    for fp in req.file_paths:
        if isinstance(fp, str) and fp.startswith("minio://"):
            try:
                local = minio_client.download_file(fp)
                resolved_paths.append(local)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"下载 MinIO 文件失败: {fp} — {e}")
        else:
            resolved_paths.append(fp)

    # 验证文件在本地是否存在
    missing = [fp for fp in resolved_paths if not os.path.exists(fp)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"文件不存在: {', '.join(missing)}",
        )

    try:
        # 创建任务
        response = task_manager.create_task(
            session_id=req.session_id,
            file_paths=resolved_paths,
            intent_id=req.intent_id,
        )

        # 后台异步执行
        task = asyncio.create_task(
            task_manager.run_task(response.task_id),
            name=f"parse_{response.task_id}",
        )
        _background_tasks[response.task_id] = task

        # 任务完成时自动清理缓存引用
        task.add_done_callback(lambda _: _background_tasks.pop(response.task_id, None))

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建解析任务失败: {e}")


@router.get("/status/{task_id}", response_model=ParseStatusResponse)
async def get_parse_status(task_id: str) -> ParseStatusResponse:
    """
    GET /api/v1/parse/status/{task_id}

    查询解析任务状态。

    响应:
        {
            "task_id": "uuid",
            "status": "done|parsing|failed",
            "chunks": [...],
            "error": null
        }
    """
    try:
        return task_manager.get_task_status(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询解析状态失败: {e}")


@router.post("/video", response_model=ParseProcessResponse)
async def process_video(req: ParseVideoRequest) -> ParseProcessResponse:
    """
    POST /api/v1/parse/video

    视频专用解析端点。

    请求体:
        {
            "session_id": "uuid",
            "file_path": "path/to/video.mp4",
            "language": "zh"  (可选)
        }

    响应:
        {
            "task_id": "uuid",
            "status": "processing",
            "assets": [...]
        }
    """
    if not req.file_path:
        raise HTTPException(status_code=400, detail="file_path 不能为空")

    # 支持 minio:// 视频路径（下载到本地）
    minio_client = MinioClient()
    video_path = req.file_path
    if isinstance(video_path, str) and video_path.startswith("minio://"):
        try:
            video_path = minio_client.download_file(video_path)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"下载 MinIO 视频失败: {req.file_path} — {e}")

    if not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail=f"文件不存在: {video_path}")

    try:
        # 复用 process 逻辑，传入单个视频路径
        parse_req = ParseProcessRequest(
            session_id=req.session_id,
            file_paths=[video_path],
        )
        response = task_manager.create_task(
            session_id=parse_req.session_id,
            file_paths=parse_req.file_paths,
        )

        # 后台执行
        task = asyncio.create_task(
            task_manager.run_task(response.task_id),
            name=f"parse_video_{response.task_id}",
        )
        _background_tasks[response.task_id] = task
        task.add_done_callback(lambda _: _background_tasks.pop(response.task_id, None))

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建视频解析任务失败: {e}")


# =============================================================================
# SSE 流式解析端点
# =============================================================================

async def _sse_event_generator(
    task_id: str,
) -> AsyncGenerator[str, None]:
    """
    SSE 事件生成器：将 task_manager.run_task_stream 的 dict 事件
    转为 text/event-stream 格式。
    """
    try:
        async for evt in task_manager.run_task_stream(task_id):
            data = json.dumps(evt["data"], ensure_ascii=False)
            yield f"event: {evt['event']}\ndata: {data}\n\n"
    except Exception as e:
        yield f"event: task_error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"


@router.post("/stream-process")
async def stream_parse_process(req: ParseProcessRequest):
    """
    POST /api/v1/parse/stream-process

    创建解析任务并立即以 SSE (text/event-stream) 流式返回进度和分块结果。

    请求体同 /api/v1/parse/process:
        {
            "session_id": "uuid",
            "file_paths": ["path/to/video.mp4", "path/to/doc.pdf"],
            "intent_id": "uuid"  (可选)
        }

    响应为 SSE 流，事件类型如下:

      事件                    data 字段                                        说明
      ──────────────────────────────────────────────────────────────────────────────
      event: task_start       {"task_id": "…", "file_count": 2, "files": […]}
      event: file_start       {"file_name": "…", "source_type": "VIDEO"}
      event: file_chunk_batch {"file_name": "…", "type": "frame|transcript|…",
                               "count": 5, "chunks": […]}
      event: file_done        {"file_name": "…", "chunk_count": 5,
                               "normalized_chunks": […]}
      event: file_error       {"file_name": "…", "error": "…"}
      event: task_done        {"task_id": "…", "status": "done",
                               "total_chunks": 12, "chunks": […]}
      event: task_error       {"error": "…"}

    前端使用示例（浏览器原生 EventSource / fetch ReadableStream）：

        const es = new EventSource("/api/v1/parse/stream-process?…");
        es.addEventListener("file_chunk_batch", (e) => {
            const data = JSON.parse(e.data);
            console.log(data.type, data.count, data.chunks);
        });
        es.addEventListener("task_done", (e) => {
            const data = JSON.parse(e.data);
            es.close();
        });

    提示：
      - 任务耗时较长时，前端应显示进度条并累积 chunk。
      - file_chunk_batch 中的 chunks 为原始块（未标准化）。
      - file_done 中的 normalized_chunks 为标准化后的 Chunk 模型。
      - task_done 中的 chunks 为全部标准化 Chunk。
    """
    if not req.file_paths:
        raise HTTPException(status_code=400, detail="file_paths 不能为空")

    # 处理可能的 minio:// URL：将其下载为本地临时文件（与 process_files 一致）
    minio_client = MinioClient()
    resolved_paths: list[str] = []
    for fp in req.file_paths:
        if isinstance(fp, str) and fp.startswith("minio://"):
            try:
                local = minio_client.download_file(fp)
                resolved_paths.append(local)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"下载 MinIO 文件失败: {fp} — {e}")
        else:
            resolved_paths.append(fp)

    # 验证文件在本地是否存在
    missing = [fp for fp in resolved_paths if not os.path.exists(fp)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"文件不存在: {', '.join(missing)}",
        )

    try:
        # 创建任务（与普通 process 共享同一个 TaskManager 实例）
        response = task_manager.create_task(
            session_id=req.session_id,
            file_paths=resolved_paths,
            intent_id=req.intent_id,
        )
        task_id = response.task_id

        return StreamingResponse(
            _sse_event_generator(task_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建流式解析任务失败: {e}")


@router.get("/stream/{task_id}")
async def stream_parse_status(task_id: str):
    """
    GET /api/v1/parse/stream/{task_id}

    对已存在的解析任务，以 SSE 流式返回当前进度和剩余分块结果。

    如果任务已在后台执行（通过 /api/v1/parse/process 创建），
    此端点可以"接入"同一任务，获取实时进度。

    响应格式同 /api/v1/parse/stream-process。
    """
    task = task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task_id {task_id} 不存在")

    return StreamingResponse(
        _sse_event_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
