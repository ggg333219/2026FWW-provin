"""S1 意图理解 FastAPI 路由。"""

from fastapi import APIRouter, HTTPException, Query, Request

from ai_engine.core import IntentConfirmRequest, IntentExtractRequest, LLMClient, settings
from ai_engine.core.llm import resolve_llm_timeout
from ai_engine.intent.intent_engine import IntentEngine, LLMIntentEngine
from ai_engine.intent.service import (
    IntentNotReady,
    IntentSessionExpired,
    IntentSessionLocked,
    IntentSessionNotFound,
    IntentUnderstandingService,
)


router = APIRouter(prefix="/intent", tags=["S1-Intent"])

# 请求级模型配置的硬上限：防止超长值撑爆日志，也避免任意地址被当作模型端点。
_MAX_API_KEY_CHARS = 512
_MAX_MODEL_CHARS = 128
_MAX_BASE_URL_CHARS = 300


def _request_llm_config(req: IntentExtractRequest) -> tuple[str, str, str]:
    """校验并清洗请求级 LLM 配置，返回 ``(api_key, base_url, model)``。

    本产品**不提供模型服务**：这三项由使用者自带，只在本请求的内存中使用，
    不落盘、不写日志、不回显到响应。三项留空时返回空串，引擎沿用部署环境的
    ``AI_*`` 配置 —— 此时仍可能走 mock / 规则兜底，响应里的 ``model_source``
    会如实说明，不会把它伪装成真实模型成功。
    """
    api_key = (req.api_key or "").strip()
    base_url = (req.base_url or "").strip().rstrip("/")
    model = (req.model or "").strip()
    if not api_key:
        return "", "", ""
    if (
        len(api_key) > _MAX_API_KEY_CHARS
        or len(model) > _MAX_MODEL_CHARS
        or len(base_url) > _MAX_BASE_URL_CHARS
    ):
        raise HTTPException(status_code=400, detail="模型配置超长，请检查后重试")
    if base_url and not (base_url.startswith("https://") or base_url.startswith("http://")):
        raise HTTPException(status_code=400, detail="模型 base_url 必须是 http(s) 地址")
    return api_key, base_url, model


@router.post("/extract")
async def extract(
    req: IntentExtractRequest,
    request: Request,
    mode: str | None = Query(None, description="兼容参数：rule 或 llm"),
) -> dict[str, object]:
    """一次提取并推进 S1 会话；同一 session_id 支持完整多轮对话。"""
    api_key, base_url, model = _request_llm_config(req)
    selected_mode = (mode or settings.GEN_MODE or "llm").strip().lower()
    # 使用者显式自带 Key 时以真实模型路径为准：部署级 AI_GEN_MODE=mock 只是
    # 本地演示开关，不该让"填了 Key"的请求静默拿到桩数据。
    # 显式 mode=rule/mock 仍保留优先级，方便验收脚本强制走规则引擎。
    if api_key and (mode or "").strip().lower() not in {"rule", "mock"}:
        selected_mode = "llm"

    client = None
    if selected_mode in {"rule", "mock"}:
        engine = IntentEngine()
    elif api_key:
        client = LLMClient(
            model=model or settings.MODEL,
            api_key=api_key,
            base_url=base_url or None,
            temperature=0.1,
            timeout=min(resolve_llm_timeout(), 90),
            max_attempts=1,
            disable_sdk_retries=True,
            stop_schema_fallback_on_error=True,
            force_real_model=True,
        )
        engine = LLMIntentEngine(client=client)
    else:
        engine = LLMIntentEngine()
    # client 为空时保持旧调用形状（只传 engine），避免影响已有调用方 / 测试桩。
    service = (
        IntentUnderstandingService(engine=engine, client=client)
        if client is not None
        else IntentUnderstandingService(engine=engine)
    )
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
