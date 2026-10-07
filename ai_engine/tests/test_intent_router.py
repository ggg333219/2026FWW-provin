import asyncio
import importlib

from starlette.requests import Request

from ai_engine.core.schema import DialogueTurn, IntentExtractRequest


def test_extract_forwards_request_id_header_to_service(monkeypatch):
    router_module = importlib.import_module("ai_engine.intent.router")
    observed = {}

    class IntentServiceStub:
        def __init__(self, engine=None):
            pass

        def extract_intent(self, session_id, messages, request_id=""):
            observed["session_id"] = session_id
            observed["request_id"] = request_id
            return {"session_id": session_id}

    monkeypatch.setattr(router_module, "IntentUnderstandingService", IntentServiceStub)
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/intent/extract",
        "headers": [(b"x-request-id", b"req-s1-42")],
        "query_string": b"",
    })
    payload = IntentExtractRequest(
        session_id="session-42",
        messages=[DialogueTurn(role="teacher", content="排序算法课")],
    )

    asyncio.run(router_module.extract(payload, request, mode="rule"))

    assert observed == {"session_id": "session-42", "request_id": "req-s1-42"}
