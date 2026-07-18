"""
SSE (Server-Sent Events) 协议支持 (core/sse.py)

提供标准化的 SSE 事件发送工具，用于流式响应场景（如 LLM 流式生成）。

使用方式：
    from ai_engine.core.sse import SSEMessage, sse_stream, sse_end

    # 在 FastAPI 路由中：
    from fastapi.responses import StreamingResponse
    from ai_engine.core.sse import sse_stream, sse_end

    async def generate():
        for chunk in llm_stream():
            yield sse_stream(chunk)
        yield sse_end({"status": "done", "total_chunks": n})

    return StreamingResponse(generate(), media_type="text/event-stream")
"""

import json
from typing import Any, Optional


class SSEMessage:
    """
    SSE 事件消息。

    SSE 协议格式：
        event: {event_type}
        data: {json_data}

    每个消息以双换行结束。
    """

    def __init__(
        self,
        data: Any,
        event_type: str = "message",
        id: Optional[str] = None,
        retry: Optional[int] = None,
    ):
        self.data = data
        self.event_type = event_type
        self.id = id
        self.retry = retry

    def to_string(self) -> str:
        """序列化为 SSE 文本格式。"""
        lines: list[str] = []

        if self.event_type != "message":
            lines.append(f"event: {self.event_type}")
        if self.id is not None:
            lines.append(f"id: {self.id}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")

        serialized = json.dumps(self.data, ensure_ascii=False)
        for line in serialized.split("\n"):
            lines.append(f"data: {line}")

        lines.append("")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"SSEMessage(event={self.event_type}, data={json.dumps(self.data, ensure_ascii=False)[:80]})"


# ---- 便捷函数 ----

def sse_stream(text: str, index: Optional[int] = None) -> str:
    """流式文本块。"""
    data: dict[str, Any] = {"text": text}
    if index is not None:
        data["index"] = index
    return SSEMessage(data, event_type="stream").to_string()


def sse_end(result: Optional[dict[str, Any]] = None) -> str:
    """流结束信号。"""
    return SSEMessage(result or {"status": "done"}, event_type="end").to_string()


def sse_error(code: int, message: str, details: Optional[str] = None) -> str:
    """错误事件。"""
    data: dict[str, Any] = {"code": code, "message": message}
    if details:
        data["details"] = details
    return SSEMessage(data, event_type="error").to_string()


def sse_progress(percent: int, stage: str, message: str) -> str:
    """进度事件。"""
    return SSEMessage(
        {"percent": percent, "stage": stage, "message": message},
        event_type="progress",
    ).to_string()