"""请求级模型配置与思考模型空正文兜底的回归测试。

覆盖两类问题：

1. 产品不提供模型服务，使用者自带的第三方 Key 必须能在**部署级 mock 开关打开时**
   依然真实生效（否则"填了 Key 却静默拿到桩数据"）；
2. 真实思考模型偶发把 JSON 全写在 reasoning_content、content 为空，
   旧实现直接 ``json_parse_failed`` → S1 整包降级，尽管模型其实答对了。

本文件全部为离线单测，不发起任何真实网络请求、不含任何真实密钥。
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from ai_engine.core.llm import LLMClient
from ai_engine.core.schema import IntentExtractRequest
from ai_engine.intent.router import _request_llm_config


def fake_response(content="", reasoning=None):
    """构造 OpenAI 兼容响应对象（离线，不触网）。"""
    message = SimpleNamespace(content=content)
    if reasoning is not None:
        message.reasoning_content = reasoning
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


class RequestLlmConfigTests(unittest.TestCase):
    """请求级配置：只做清洗与校验，不落盘、不回显。"""

    def test_defaults_are_empty(self):
        req = IntentExtractRequest(session_id="s1", messages=[])
        self.assertEqual(_request_llm_config(req), ("", "", ""))

    def test_values_are_stripped(self):
        req = IntentExtractRequest(
            api_key="  local-test-key  ",
            base_url=" https://api.example.com/v1/ ",
            model="  unit-model  ",
        )
        self.assertEqual(
            _request_llm_config(req),
            ("local-test-key", "https://api.example.com/v1", "unit-model"),
        )

    def test_key_required_before_anything_is_forwarded(self):
        req = IntentExtractRequest(base_url="https://api.example.com/v1", model="m")
        self.assertEqual(_request_llm_config(req), ("", "", ""))

    def test_rejects_non_http_base_url(self):
        req = IntentExtractRequest(api_key="local-test-key", base_url="file:///etc/passwd")
        with self.assertRaises(HTTPException) as ctx:
            _request_llm_config(req)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_rejects_oversized_values(self):
        req = IntentExtractRequest(api_key="k" * 600)
        with self.assertRaises(HTTPException) as ctx:
            _request_llm_config(req)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_existing_fields_are_untouched(self):
        req = IntentExtractRequest(session_id="s1", messages=[], api_key="local-test-key")
        self.assertEqual(req.session_id, "s1")
        self.assertEqual(req.messages, [])


class ForceRealModelTests(unittest.TestCase):
    """自带 Key 的请求必须绕开部署级 mock 开关，但不绕开"缺 Key 底线"。"""

    def test_global_mock_is_bypassed_for_request_owned_key(self):
        client = LLMClient(api_key="local-test-key", force_real_model=True)
        with patch("ai_engine.core.llm.settings") as fake:
            fake.is_mock = True
            self.assertFalse(client.is_mock_effective)
            self.assertEqual(client.unavailable_reason(), "")

    def test_global_mock_still_applies_without_force(self):
        client = LLMClient(api_key="local-test-key")
        with patch("ai_engine.core.llm.settings") as fake:
            fake.is_mock = True
            self.assertTrue(client.is_mock_effective)
            self.assertEqual(client.unavailable_reason(), "mock_mode")

    def test_missing_key_still_reports_mock_even_with_force(self):
        client = LLMClient(api_key="", force_real_model=True)
        with patch("ai_engine.core.llm.settings") as fake:
            fake.is_mock = False
            with patch.object(LLMClient, "api_key", property(lambda self: "")):
                self.assertEqual(client.unavailable_reason(), "missing_api_key_mock")


class EmptyContentTests(unittest.TestCase):
    """思考模型空正文：reasoning 兜底 + 一次重试 + 如实报解析失败。"""

    @staticmethod
    def _offline_client():
        # 用类级 property patch 固定"未开全局 mock"，避免受运行环境 AI_GEN_MODE 影响。
        return LLMClient(api_key="local-test-key", max_attempts=1)

    def test_reasoning_content_is_used_when_content_empty(self):
        client = self._offline_client()
        thinking = '先分析教师需求…… {"topic": "冒泡排序", "duration_minutes": 45} 思考结束'
        with patch.object(client, "_post_chat_completions", return_value=fake_response(content="", reasoning=thinking)), \
             patch.object(LLMClient, "is_mock_effective", property(lambda self: False)):
            result = client.chat_json(system="s", user="u")
        self.assertEqual(result.get("topic"), "冒泡排序")
        self.assertEqual(result.get("duration_minutes"), 45)

    def test_empty_content_retries_once(self):
        client = self._offline_client()
        calls = []

        def fake_post(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                return fake_response(content="")
            return fake_response(content='{"topic": "快速排序"}')

        with patch.object(client, "_post_chat_completions", side_effect=fake_post), \
             patch.object(LLMClient, "is_mock_effective", property(lambda self: False)):
            result = client.chat_json(system="s", user="u")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.get("topic"), "快速排序")

    def test_persistent_empty_content_is_reported_not_faked(self):
        client = self._offline_client()
        with patch.object(client, "_post_chat_completions", return_value=fake_response(content="")), \
             patch.object(LLMClient, "is_mock_effective", property(lambda self: False)):
            result = client.chat_json(system="s", user="u")
        self.assertEqual(result.get("error"), "json_parse_failed")

    def test_normal_content_is_unchanged(self):
        client = self._offline_client()
        with patch.object(client, "_post_chat_completions",
                          return_value=fake_response(content='{"topic": "分治"}')), \
             patch.object(LLMClient, "is_mock_effective", property(lambda self: False)):
            result = client.chat_json(system="s", user="u")
        self.assertEqual(result.get("topic"), "分治")


if __name__ == "__main__":
    unittest.main()
