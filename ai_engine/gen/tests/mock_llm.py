"""
MockLLMClient — 确定性测试用的 LLM 客户端 mock。

用于 gen/ 模块的单元测试，替代真实 LLMClient，
支持注入预设响应，实现可重复的确定性测试。

用法：
    mock = MockLLMClient()
    mock.set_response("chat_with_schema", {"nodes": [...]})
    builder = OutlineBuilder(llm_client=mock)
    result = builder.build_outline(...)
"""

from typing import Any, Optional
from ai_engine.core.llm import LLMClient, LLMResponse


class MockLLMClient(LLMClient):
    """
    可注入的 LLM 客户端 mock，替换真实 LLMClient。

    调用对应方法时返回预设的响应，无需 API key 或网络请求。
    """

    def __init__(self, **kwargs):
        super().__init__(api_key="mock-key", base_url="http://mock.local", **kwargs)
        self._preset_responses: dict[str, Any] = {}
        self._call_log: list[dict[str, Any]] = []

    # ── 预设控制 ──

    def set_response(self, method: str, response: Any) -> None:
        """设置某方法的预设返回值。

        Args:
            method: 方法名（"chat", "chat_json", "chat_with_schema", "chat_messages", "embed"）
            response: 预设返回值
        """
        self._preset_responses[method] = response

    def set_chat_response(self, text: str, model: str = "mock-model") -> None:
        """设置 chat() 的预设文本响应。"""
        self._preset_responses["chat"] = LLMResponse(
            content=text, model=model, used_fallback=False
        )

    def set_json_response(self, data: dict) -> None:
        """设置 chat_json() 和 chat_with_schema() 的预设 JSON 响应。"""
        self._preset_responses["chat_json"] = data
        self._preset_responses["chat_with_schema"] = data

    def set_embed_response(self, vector: list[float]) -> None:
        """设置 embed() 的预设向量。"""
        self._preset_responses["embed"] = vector

    def clear_presets(self) -> None:
        """清除所有预设响应。"""
        self._preset_responses.clear()

    # ── 调用日志 ──

    @property
    def call_log(self) -> list[dict[str, Any]]:
        """返回所有调用的记录（用于断言）。"""
        return self._call_log

    def last_call(self) -> Optional[dict[str, Any]]:
        """返回最近一次调用记录。"""
        return self._call_log[-1] if self._call_log else None

    def reset_call_log(self) -> None:
        """清空调用日志。"""
        self._call_log = []

    # ── 重写 LLMClient 方法 ──

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        self._call_log.append({
            "method": "chat",
            "system": system,
            "user": user,
            "temperature": temperature,
            "model": model,
        })
        if "chat" in self._preset_responses:
            return self._preset_responses["chat"]
        return LLMResponse(
            content=f"[mock] {user[:60]}",
            model="mock-model",
            used_fallback=True,
            fallback_reason="no preset response",
        )

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        self._call_log.append({
            "method": "chat_json",
            "system": system,
            "user": user,
            "temperature": temperature,
            "model": model,
        })
        if "chat_json" in self._preset_responses:
            return self._preset_responses["chat_json"]
        return {"_mock": True, "message": user[:60]}

    def chat_with_schema(
        self,
        system: str,
        user: str,
        schema: dict,
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        self._call_log.append({
            "method": "chat_with_schema",
            "system": system,
            "user": user,
            "schema": schema,
            "temperature": temperature,
            "model": model,
        })
        if "chat_with_schema" in self._preset_responses:
            return self._preset_responses["chat_with_schema"]
        return {"_mock": True, "message": user[:60]}

    def chat_messages(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> LLMResponse:
        self._call_log.append({
            "method": "chat_messages",
            "messages": messages,
            "temperature": temperature,
            "model": model,
        })
        if "chat_messages" in self._preset_responses:
            return self._preset_responses["chat_messages"]
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        return LLMResponse(
            content=f"[mock messages] {last_user[:60]}",
            model="mock-model",
            used_fallback=True,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._call_log.append({
            "method": "embed",
            "texts": texts,
        })
        if "embed" in self._preset_responses:
            return self._preset_responses["embed"]
        return [[0.1] * 128 for _ in texts]