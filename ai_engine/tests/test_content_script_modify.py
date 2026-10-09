import asyncio

import pytest
from fastapi import HTTPException

from ai_engine import main
from ai_engine.core.llm import LLMClient, LLMResponse


def test_modify_script_returns_only_current_node(monkeypatch):
    seen = {}

    def fake_chat(self, system, user):
        seen["user"] = user
        return LLMResponse(content="精简后的讲稿", model="test")

    monkeypatch.setattr(LLMClient, "chat", fake_chat)
    result = asyncio.run(main.modify_content_script(main.GenScriptModifyRequest(
        node_id="node-1", title="冒泡排序", script="原讲稿", message="精简", course_name="排序算法",
    )))
    assert result == {"node_id": "node-1", "script": "精简后的讲稿", "used_fallback": False}
    assert "原讲稿" in seen["user"] and "精简" in seen["user"]


def test_modify_script_rejects_llm_fallback(monkeypatch):
    monkeypatch.setattr(LLMClient, "chat", lambda *_: LLMResponse(
        content="占位内容", model="test", used_fallback=True,
    ))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.modify_content_script(main.GenScriptModifyRequest(
            node_id="node-1", script="原讲稿", message="精简",
        )))
    assert exc.value.status_code == 503
