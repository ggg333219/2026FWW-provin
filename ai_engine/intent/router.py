"""S1 意图理解 FastAPI 路由。"""
from fastapi import APIRouter, Query
from ai_engine.core import settings
from typing import Any

from ai_engine.core import IntentExtractRequest, IntentConfirmRequest, IntentSummary, SessionStatus
from ai_engine.intent.service import IntentUnderstandingService, SESSIONS
from ai_engine.intent.intent_engine import IntentEngine, LLMIntentEngine

router = APIRouter(prefix="/intent", tags=["S1-Intent"])


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
