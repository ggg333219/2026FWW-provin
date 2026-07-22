# S1 — 意图理解 (Intent Understanding)

This package implements the S1 intent understanding skill used by the AI Engine.

Endpoints (via `ai_engine/main.py`):

- `POST /intent/extract?mode=rule|llm` — extract structured `IntentSummary` from dialogue messages. Use `mode=rule` to force the local rule-based extractor, `mode=llm` to call `LLMIntentEngine` (falls back to rule engine on error). If `mode` is omitted the default engine is taken from `ai_engine.core.settings.GEN_MODE`.
- `POST /intent/confirm` — confirm and persist the intent for the session (in-memory persistence currently).

Usage examples

Request body for `/intent/extract`:

{
  "session_id": "conv_1",
  "messages": [
    {"role": "teacher", "content": "帮我做一份45分钟的排序算法课件，面向大一计算机专业，讲练结合。包括冒泡排序, 快速排序"}
  ]
}

The service returns a JSON with `intent_summary`, `need_followup`, and `followup_questions`.

Notes

- Current implementation stores session state in memory at `ai_engine.intent.service.SESSIONS`. For production, replace with DB persistence.
- `LLMIntentEngine` demonstrates how to use `ai_engine.core.LLMClient.chat_json` with a JSON schema; `LLMIntentEngine` is conservative and returns a dict or an error object on failure.
