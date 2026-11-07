"""S1 结果来源可观测性回归测试（V04）。

背景：方案要求"真实模型成功、规则兜底成功、离线测试通过、模拟链路通过不能混为一谈"，
并且"不把 HTTP 200 等同于真实模型成功"。此前 S1 响应里没有能区分这几种情况的字段：

- 走真实模型、模型失败后兜底、压根没调模型（mock / 缺 API Key），
  在响应上可能长得一样（``used_fallback=False`` + ``fallback_reason=None``）。

本文件锁定新契约 ``model_source``，并锁定"缺 Key 时降级原因必须是真实根因，
不能被记成 invalid_model_response（'模型输出无效'）"。
"""

import unittest
from unittest.mock import patch

from ai_engine.core import DialogueTurn, TurnType
from ai_engine.intent.service import (
    MODEL_SOURCE_MOCK,
    MODEL_SOURCE_REAL,
    MODEL_SOURCE_RULE_ENGINE,
    MODEL_SOURCE_RULE_FALLBACK,
    IntentUnderstandingService,
)


def turn(content: str) -> DialogueTurn:
    return DialogueTurn(role="teacher", content=content, turn_type=TurnType.INITIAL)


class ModelCapableEngine:
    """具备调用模型能力的引擎桩（带 client 属性 + unavailable_reason 状态）。"""

    def __init__(self, payload: dict, unavailable_reason: str = ""):
        self.payload = payload
        self.last_unavailable_reason = unavailable_reason
        self.client = object()

    def extract_intent(self, _messages):
        return dict(self.payload)


class RuleEngineStub:
    """无 client 属性的规则引擎桩。"""

    def extract_intent(self, _messages):
        return {"error": "not_used"}


class ModelSourceTests(unittest.TestCase):
    """model_source 契约。"""

    def test_real_model_output_is_marked_as_real_model(self):
        engine = ModelCapableEngine(
            {
                "topic": "冒泡排序与快速排序",
                "duration_minutes": 45,
                "style": "讲练结合",
                "knowledge_points": ["冒泡排序", "快速排序"],
                "output_format": ["ppt"],
                "with_interactive": True,
            }
        )
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent("src_real", [turn("我要做排序算法课件，45分钟")])

        self.assertEqual(result["model_source"], MODEL_SOURCE_REAL)
        self.assertFalse(result["used_fallback"])
        self.assertIsNone(result["fallback_reason"])

    def test_mock_without_api_key_is_not_reported_as_model_success(self):
        # 缺 API Key：LLMClient 会静默返回桩数据。若不区分，响应会显示
        # "模型成功"，与真实模型跑通完全无法分辨。
        engine = ModelCapableEngine(
            {"topic": None, "duration_minutes": None},
            unavailable_reason="missing_api_key_mock",
        )
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent("src_mock", [turn("我要做排序算法课件，45分钟")])

        self.assertEqual(result["model_source"], MODEL_SOURCE_MOCK)
        self.assertTrue(result["used_fallback"])
        # 真实根因是"没接模型"，不能记成"模型输出无效"。
        self.assertEqual(result["fallback_reason"], "missing_api_key_mock")
        self.assertNotEqual(result["fallback_reason"], "invalid_model_response")

    def test_model_failure_reports_rule_fallback(self):
        engine = ModelCapableEngine({"error": "llm_call_failed", "reason": "ReadTimeout"})
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent("src_fail", [turn("我要做排序算法课件，45分钟")])

        self.assertEqual(result["model_source"], MODEL_SOURCE_RULE_FALLBACK)
        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["fallback_reason"], "timeout")

    def test_rule_engine_without_model_is_marked_rule_engine(self):
        class PlainRuleEngine:
            def extract_intent(self, _messages):
                from ai_engine.core import IntentSummary

                summary = IntentSummary()
                summary.topic = "排序算法"
                summary.duration_minutes = 45
                return summary

        service = IntentUnderstandingService(engine=PlainRuleEngine())
        result = service.extract_intent("src_rule", [turn("我要做排序算法课件，45分钟")])

        self.assertEqual(result["model_source"], MODEL_SOURCE_RULE_ENGINE)
        self.assertFalse(result["used_fallback"])


class SystemMockModeTests(unittest.TestCase):
    """系统级 mock 模式（服务器部署默认值 AI_GEN_MODE=mock）。"""

    def test_system_mock_mode_is_reported_as_mock_not_as_success(self):
        class PlainRuleEngine:
            def extract_intent(self, _messages):
                from ai_engine.core import IntentSummary

                summary = IntentSummary()
                summary.topic = "冒泡排序与快速排序"
                summary.duration_minutes = 45
                return summary

        service = IntentUnderstandingService(engine=PlainRuleEngine())
        with patch("ai_engine.intent.service.settings") as fake_settings:
            fake_settings.GEN_MODE = "mock"
            result = service.extract_intent("src_sys_mock", [turn("我要做排序算法课件，45分钟")])

        self.assertEqual(result["model_source"], MODEL_SOURCE_MOCK)
        # 关键：mock 模式下不能出现"一切正常"的信号。
        self.assertFalse(result["used_fallback"])  # 语义不变：模型输出未被采用
        self.assertIsNot(result["model_source"], MODEL_SOURCE_REAL)


class ClientUnavailableReasonTests(unittest.TestCase):
    """LLMClient.unavailable_reason 契约。"""

    def test_mock_mode_reports_mock_mode(self):
        from ai_engine.core.llm import LLMClient

        client = LLMClient(api_key="sk-test")
        with patch("ai_engine.core.llm.settings") as fake_settings:
            fake_settings.is_mock = True
            self.assertEqual(client.unavailable_reason(), "mock_mode")

    def test_missing_api_key_reports_missing_api_key_mock(self):
        from ai_engine.core.llm import LLMClient

        client = LLMClient(api_key="")
        with patch("ai_engine.core.llm.settings") as fake_settings:
            fake_settings.is_mock = False
            with patch.object(LLMClient, "api_key", property(lambda self: "")):
                self.assertEqual(client.unavailable_reason(), "missing_api_key_mock")

    def test_real_model_setup_reports_empty_reason(self):
        from ai_engine.core.llm import LLMClient

        client = LLMClient(api_key="sk-test")
        with patch("ai_engine.core.llm.settings") as fake_settings:
            fake_settings.is_mock = False
            with patch.object(LLMClient, "api_key", property(lambda self: "sk-test")):
                self.assertEqual(client.unavailable_reason(), "")


if __name__ == "__main__":
    unittest.main()
