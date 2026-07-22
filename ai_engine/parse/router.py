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
import os
import traceback
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from ai_engine.core.schema import (
    ParseProcessRequest,
    ParseProcessResponse,
    ParseStatusResponse,
    ParseVideoRequest,
)
from ai_engine.parse.task_manager import TaskManager

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

    # 验证文件存在
    missing = [fp for fp in req.file_paths if not os.path.exists(fp)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"文件不存在: {', '.join(missing)}",
        )

    try:
        # 创建任务
        response = task_manager.create_task(
            session_id=req.session_id,
            file_paths=req.file_paths,
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

    if not os.path.exists(req.file_path):
        raise HTTPException(status_code=400, detail=f"文件不存在: {req.file_path}")

    try:
        # 复用 process 逻辑，传入单个视频路径
        parse_req = ParseProcessRequest(
            session_id=req.session_id,
            file_paths=[req.file_path],
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
