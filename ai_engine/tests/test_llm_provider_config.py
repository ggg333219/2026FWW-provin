"""思考模型空正文兜底的回归测试（S1 修复，离线、不触网、不含任何密钥）。

真实思考模型偶发把 JSON 全写在 ``reasoning_content``、``content`` 为空，
旧实现只取 ``content``，于是 ``json.loads("")`` 失败 → ``json_parse_failed``
→ S1 整包降级到规则引擎，尽管模型其实答对了。

本文件只覆盖这一修复。请求级 BYOK 配置校验 / ``force_real_model`` 相关用例
已随「使用者自带第三方模型」功能拆到独立 PR，不在本 MVP 分支内。
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ai_engine.core.llm import LLMClient


def fake_response(content="", reasoning=None):
    """构造 OpenAI 兼容响应对象（离线，不触网）。"""
    message = SimpleNamespace(content=content)
    if reasoning is not None:
        message.reasoning_content = reasoning
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


class EmptyContentTests(unittest.TestCase):
    """思考模型空正文：reasoning 兜底 + 一次重试 + 如实报解析失败。"""

    @staticmethod
    def _offline_client():
        # 用属性 patch 固定"未开全局 mock"，避免受运行环境 AI_GEN_MODE 影响。
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
