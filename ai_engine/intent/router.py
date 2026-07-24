"""S1 意图理解 FastAPI 路由。"""
import asyncio
import json
from queue import Queue

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from ai_engine.core import settings
from typing import Any

from ai_engine.core import IntentExtractRequest, IntentConfirmRequest, IntentSummary, SessionStatus
from ai_engine.intent.service import IntentUnderstandingService, SESSIONS
from ai_engine.intent.intent_engine import IntentEngine, LLMIntentEngine

router = APIRouter(prefix="/intent", tags=["S1-Intent"])


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Helper: format a dict as an SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/extract")
async def extract(req: IntentExtractRequest, mode: str | None = Query(None, description="engine: 'rule' or 'llm'")) -> dict[str, object]:
    """从对话消息中提取结构化教学意图。

    Query param `mode` 控制使用本地规则引擎还是 LLM 引擎。
    """
    # choose default from global settings if not provided
    if mode is None:
        mode = settings.GEN_MODE or "rule"

    if mode == "rule":
        engine = IntentEngine()
    else:
        engine = LLMIntentEngine()

    # run engine to get summary (engine may return dict or IntentSummary)
    res = engine.extract_intent(req.messages)
    if isinstance(res, IntentSummary):
        summary = res
    elif isinstance(res, dict):
        try:
            summary = IntentSummary(**res)
        except Exception:
            summary = IntentSummary()
    else:
        summary = IntentSummary()

    # compute followups and human summary via rule-based helper
    helper = IntentEngine()
    followups = helper.generate_followup_questions(summary)
    human_summary = helper.render_human_summary(summary)

    # persist via service (inject engine so it won't re-run LLM)
    service = IntentUnderstandingService(engine=engine)
    persist = service.extract_intent(req.session_id, req.messages)

    data: dict[str, object] = {
        "intent_summary": summary.model_dump(),
        "need_followup": len(followups) > 0,
        "followup_questions": followups,
        "human_summary": human_summary,
    }

    # merge persisted metadata (session_id, session_status)
    data.update({"session_id": persist.get("session_id"), "session_status": persist.get("session_status")})
    return data


@router.post("/confirm")
async def confirm(req: IntentConfirmRequest) -> dict[str, object]:
    """确认当前意图摘要并返回确认后的结构化意图。"""
    # read persisted session
    session = SESSIONS.get(req.session_id)
    if not session:
        # return minimal confirmation with empty intent
        return {"session_id": req.session_id, "confirmed": False, "message": "session not found"}

    service = IntentUnderstandingService()
    return service.confirm_intent(req.session_id, session.intent)


@router.post("/extract-stream")
async def extract_stream(req: IntentExtractRequest):
    """
    POST /intent/extract-stream

    流式意图提取端点，使用 SSE (text/event-stream) 实时推送 LLM 输出。

    请求体同 /intent/extract:
        {
            "session_id": "uuid",
            "messages": [
                {"role": "teacher", "content": "帮我做一份45分钟的排序算法课件..."}
            ]
        }

    SSE 事件类型:

      event: extract_start    data: {"session_id": "…", "message_count": N}
      event: extract_token    data: {"token": "…", "accumulated": "…"}
      event: extract_done     data: {"intent_summary": {…}, "followup_questions": […]}
      event: extract_error    data: {"error": "…"}

    前端使用示例 (fetch ReadableStream):

        const response = await fetch("/intent/extract-stream", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({session_id: "s1", messages: [...]}),
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, {stream: true});
            const parts = buffer.split("\\n\\n");
            buffer = parts.pop() || "";
            for (const part of parts) {
                const lines = part.split("\\n");
                const eventLine = lines.find(l => l.startsWith("event: "));
                const dataLine = lines.find(l => l.startsWith("data: "));
                if (eventLine && dataLine) {
                    const event = eventLine.slice(7);
                    const data = JSON.parse(dataLine.slice(6));
                    handleSseEvent(event, data);
                }
            }
        }
    """
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")

    async def _sse_generator():
        # 1) emit start
        yield _sse_event("extract_start", {
            "session_id": req.session_id,
            "message_count": len(req.messages),
        })

        # 2) 在线程池中运行同步 LLM 流式调用（通过 Queue 桥接同步→异步）
        engine = LLMIntentEngine()
        queue: Queue = Queue()
        loop = asyncio.get_running_loop()

        def _run_stream():
            """在独立线程中运行同步 Generator，将 token 写入队列。"""
            accumulated = ""
            try:
                for token in engine.extract_intent_stream(req.messages):
                    accumulated += token
                    queue.put(("token", token, accumulated))
                queue.put(("done", accumulated, None))
            except Exception as e:
                queue.put(("error", str(e), None))

        # 提交到线程池
        future = loop.run_in_executor(None, _run_stream)

        # 3) 从队列读取并 yield SSE 事件
        accumulated = ""
        while True:
            # 非阻塞检查队列
            try:
                item = await loop.run_in_executor(None, queue.get, True, 0.1)
            except Exception:
                # queue.Empty → 继续等待
                await asyncio.sleep(0.05)
                continue

            msg_type = item[0]

            if msg_type == "token":
                token, accumulated = item[1], item[2]
                yield _sse_event("extract_token", {
                    "token": token,
                    "accumulated": accumulated[-500:],
                })

            elif msg_type == "done":
                accumulated = item[1]
                break

            elif msg_type == "error":
                yield _sse_event("extract_error", {"error": item[1]})
                return

        # 等待线程完成
        await future

        # 4) 解析完整 JSON 结果并持久化
        try:
            from ai_engine.core.llm import extract_json

            try:
                result = extract_json(accumulated)
            except (ValueError, json.JSONDecodeError):
                result = {"topic": accumulated[:200], "error": "json_parse_partial"}

            summary = IntentSummary(**result) if isinstance(result, dict) else IntentSummary()

            helper = IntentEngine()
            followups = helper.generate_followup_questions(summary)
            human_summary = helper.render_human_summary(summary)

            service = IntentUnderstandingService(engine=engine)
            persist = service.extract_intent(req.session_id, req.messages)

            yield _sse_event("extract_done", {
                "session_id": req.session_id,
                "session_status": persist.get("session_status"),
                "intent_summary": summary.model_dump(),
                "need_followup": len(followups) > 0,
                "followup_questions": followups,
                "human_summary": human_summary,
            })

        except Exception as e:
            yield _sse_event("extract_error", {"error": str(e)})

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
