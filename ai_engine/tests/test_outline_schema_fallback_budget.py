from ai_engine.core.llm import LLMClient, LLMResponse


def test_outline_client_stops_schema_fallback_after_first_provider_failure():
    client = LLMClient(
        api_key="test-key",
        stop_schema_fallback_on_error=True,
    )
    calls = []

    def failed_call(**_kwargs):
        calls.append(1)
        return LLMResponse(
            content="",
            model="test-model",
            used_fallback=True,
            fallback_reason="provider_error",
        )

    client._call = failed_call

    try:
        client.chat_with_schema("system", "user", {"type": "object"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("provider failure should be returned to outline fallback")

    assert len(calls) == 1


def test_outline_client_stops_schema_fallback_after_unparseable_response():
    client = LLMClient(
        api_key="test-key",
        stop_schema_fallback_on_error=True,
    )
    calls = []

    def invalid_call(**_kwargs):
        calls.append(1)
        return LLMResponse(content="not-json", model="test-model")

    client._call = invalid_call

    try:
        client.chat_with_schema("system", "user", {"type": "object"})
    except RuntimeError:
        pass
    else:
        raise AssertionError("invalid response should be returned to outline fallback")

    assert len(calls) == 1


def test_generic_client_keeps_schema_format_fallback_behavior():
    client = LLMClient(api_key="test-key")
    calls = []

    def fallback_then_success(**_kwargs):
        calls.append(1)
        if len(calls) == 1:
            return LLMResponse(
                content="",
                model="test-model",
                used_fallback=True,
                fallback_reason="provider_error",
            )
        return LLMResponse(content='{"ok": true}', model="test-model")

    client._call = fallback_then_success

    assert client.chat_with_schema("system", "user", {"type": "object"}) == {"ok": True}
    assert len(calls) == 2
