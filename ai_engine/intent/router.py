"""S1 意图理解 FastAPI 路由。"""

from fastapi import APIRouter, HTTPException, Query, Request

from ai_engine.core import IntentExtractRequest, IntentConfirmRequest, settings
from ai_engine.intent.intent_engine import IntentEngine, LLMIntentEngine
from ai_engine.intent.service import (
    IntentNotReady,
    IntentSessionExpired,
    IntentSessionLocked,
    IntentSessionNotFound,
    IntentUnderstandingService,
)


router = APIRouter(prefix="/intent", tags=["S1-Intent"])


@router.post("/extract")
async def extract(
    req: IntentExtractRequest,
    request: Request,
    mode: str | None = Query(None, description="兼容参数：rule 或 llm"),
) -> dict[str, object]:
    """一次提取并推进 S1 会话；同一 session_id 支持完整多轮对话。"""
    selected_mode = (mode or settings.GEN_MODE or "llm").strip().lower()
    engine = IntentEngine() if selected_mode in {"rule", "mock"} else LLMIntentEngine()
    service = IntentUnderstandingService(engine=engine)
    try:
        request_id = req.request_id or request.headers.get("x-request-id", "")
        return service.extract_intent(req.session_id, req.messages, request_id=request_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntentSessionExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except IntentSessionLocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/confirm")
async def confirm(req: IntentConfirmRequest) -> dict[str, object]:
    """确认当前意图，返回供后续 Skill 使用的 intent_id。"""
    service = IntentUnderstandingService()
    try:
        return service.confirm_intent(req.session_id)
    except IntentSessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntentSessionExpired as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except IntentSessionLocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntentNotReady as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "missing_fields": exc.missing_fields},
        ) from exc
