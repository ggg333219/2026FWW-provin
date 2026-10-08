from ai_engine.gen.lesson_plan import LessonPlanGenerator


def test_lesson_plan_llm_client_has_a_bounded_single_attempt(monkeypatch):
    import ai_engine.core.llm as llm_module

    captured = {}

    class FakeLLMClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_module, "LLMClient", FakeLLMClient)

    LessonPlanGenerator()._get_llm_client()

    assert captured == {
        "max_attempts": 1,
        "timeout": 25,
        "stop_schema_fallback_on_error": True,
    }
