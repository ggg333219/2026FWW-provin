import json
import unittest
from unittest.mock import patch

from ai_engine.core import DialogueTurn, IntentSummary, LLMClient, SessionStatus, TurnType
from ai_engine.intent.intent_engine import IntentEngine, LLMIntentEngine
from ai_engine.intent.service import (
    IntentNotReady,
    IntentSessionNotFound,
    IntentUnderstandingService,
    SESSIONS,
)


class IntentEngineTests(unittest.TestCase):
    def test_extract_intent_basic(self):
        messages = [{
            "role": "teacher",
            "content": "帮我做一份45分钟的排序算法课件，面向大一计算机专业学生，讲练结合。包括冒泡排序、快速排序。",
        }]
        intent = IntentEngine.extract_intent(messages)
        self.assertIn("排序算法", intent.topic)
        self.assertEqual(intent.duration_minutes, 45)
        self.assertIn("大一", intent.target_student)
        self.assertEqual(intent.style, "讲练结合")
        self.assertIn("冒泡排序", intent.knowledge_points)
        self.assertEqual(intent.output_format, ["ppt"])

    def test_extract_topic_from_design_request(self):
        intent = IntentEngine.extract_intent([{
            "role": "teacher",
            "content": "请设计一节45分钟的排序算法课件，面向大一学生。",
        }])
        self.assertEqual(intent.topic, "排序算法")

    def test_extracts_natural_teacher_request_without_polluting_knowledge_points(self):
        content = "我想给大一学生做一节关于快速排序的课，讲课时间45，风格活泼一点，最好有动画演示和课堂小游戏。"
        intent = IntentEngine.extract_intent([{"role": "teacher", "content": content}])

        self.assertEqual(intent.topic, "快速排序")
        self.assertEqual(intent.duration_minutes, 45)
        self.assertEqual(intent.target_student, "大一学生")
        self.assertEqual(intent.style, "活泼")
        self.assertTrue(intent.with_interactive)
        self.assertEqual(intent.knowledge_points, [])

    def test_latest_explicit_correction_overrides_previous_values(self):
        messages = [
            {"role": "teacher", "content": "请设计一节45分钟的排序算法课，面向大一学生，采用讲练结合。"},
            {
                "role": "teacher",
                "content": "请更新教学意图：课程主题：快速排序；授课时长：50分钟；授课对象：大二软件工程学生；教学风格：沉稳专业；知识点：分治思想、枢轴选择、分区过程；互动设计：需要。",
            },
        ]
        intent = IntentEngine.extract_intent(messages)

        self.assertEqual(intent.topic, "快速排序")
        self.assertEqual(intent.duration_minutes, 50)
        self.assertEqual(intent.target_student, "大二软件工程学生")
        self.assertEqual(intent.style, "沉稳专业")
        self.assertEqual(intent.knowledge_points, ["分治思想", "枢轴选择", "分区过程"])
        self.assertTrue(intent.with_interactive)

    def test_explicit_knowledge_points_split_conjunction_and_exclude_interaction(self):
        intent = IntentEngine.extract_intent([{
            "role": "teacher",
            "content": "请设计45分钟的排序算法课，重点包括冒泡排序、快速排序和复杂度对比，并加入课堂小测。",
        }])

        self.assertEqual(intent.knowledge_points, ["冒泡排序", "快速排序", "复杂度对比"])
        self.assertTrue(intent.with_interactive)

    def test_mock_llm_uses_same_rule_extraction(self):
        content = "我想给大一学生做一节关于快速排序的课，讲课时间45，风格活泼一点，最好有动画演示和课堂小游戏。"
        result = json.loads(LLMClient()._mock_response([{"role": "teacher", "content": content}]))

        self.assertEqual(result["duration_minutes"], 45)
        self.assertEqual(result["target_student"], "大一学生")
        self.assertEqual(result["style"], "活泼")
        self.assertEqual(result["knowledge_points"], [])
        self.assertTrue(result["with_interactive"])

    def test_generate_followups_when_missing(self):
        intent = IntentEngine.extract_intent([{"role": "teacher", "content": "请帮我做一份课件"}])
        followups = IntentEngine.generate_followup_questions(intent)
        self.assertGreaterEqual(len(followups), 1)


class IntentUnderstandingTests(unittest.TestCase):
    def setUp(self):
        SESSIONS.clear()
        self.service = IntentUnderstandingService(engine=IntentEngine())

    @staticmethod
    def _turn(content: str) -> DialogueTurn:
        return DialogueTurn(role="teacher", content=content, turn_type=TurnType.INITIAL)

    def test_incomplete_intent_stays_collecting_and_cannot_confirm(self):
        result = self.service.extract_intent("session_001", [self._turn("我想做排序算法课件")])
        summary = IntentSummary(**result["intent_summary"])
        self.assertIn("duration_minutes", summary.missing_fields)
        self.assertEqual(result["session_status"], SessionStatus.COLLECTING.value)
        self.assertFalse(result["can_confirm"])
        with self.assertRaises(IntentNotReady):
            self.service.confirm_intent("session_001")

    def test_multiturn_intent_enters_confirming_and_confirms(self):
        messages = [
            self._turn("我要做排序算法课件，面向大一计算机专业学生。"),
            DialogueTurn(role="assistant", content="这节课计划安排多少分钟？", turn_type=TurnType.CLARIFYING_QUESTION),
            self._turn("45分钟，讲练结合，包括冒泡排序、快速排序。"),
        ]
        result = self.service.extract_intent("session_002", messages)
        self.assertEqual(result["session_status"], SessionStatus.CONFIRMING.value)
        self.assertTrue(result["can_confirm"])
        self.assertEqual(result["turn_count"], 2)
        confirmed = self.service.confirm_intent("session_002")
        self.assertTrue(confirmed["confirmed"])
        self.assertTrue(confirmed["intent_id"].startswith("intent_"))
        self.assertEqual(confirmed["next_step"], "material_upload")

    def test_rule_evidence_repairs_incomplete_engine_result(self):
        class IncompleteEngine:
            @staticmethod
            def extract_intent(_messages):
                return {
                    "topic": "快速排序",
                    "duration_minutes": None,
                    "style": None,
                    "target_student": None,
                    "knowledge_points": ["风格活泼一点"],
                    "output_format": ["ppt"],
                    "with_interactive": False,
                }

        service = IntentUnderstandingService(engine=IncompleteEngine())
        result = service.extract_intent("session_rule_repair", [self._turn(
            "我想给大一学生做一节关于快速排序的课，讲课时间45，风格活泼一点，最好有动画演示和课堂小游戏。"
        )])
        summary = IntentSummary(**result["intent_summary"])

        self.assertEqual(summary.duration_minutes, 45)
        self.assertEqual(summary.target_student, "大一学生")
        self.assertEqual(summary.style, "活泼")
        self.assertEqual(summary.knowledge_points, [])
        self.assertTrue(summary.with_interactive)

    def test_failed_llm_engine_returns_safe_fallback_reason(self):
        class FailedEngine:
            @staticmethod
            def extract_intent(_messages):
                return {"error": "llm_call_failed", "reason": "secret-bearing provider details"}

        service = IntentUnderstandingService(engine=FailedEngine())
        with self.assertLogs("ai_engine.intent.service", level="WARNING") as captured:
            result = service.extract_intent(
                "session_fallback_reason",
                [self._turn("我想讲快速排序，45分钟")],
                request_id="req-s1-test",
            )

        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["fallback_reason"], "model_error")
        self.assertNotIn("secret-bearing", str(result))
        self.assertIn("req-s1-test", captured.output[0])
        self.assertNotIn("secret-bearing", captured.output[0])

    def test_timeout_engine_failure_has_specific_safe_category(self):
        class TimedOutEngine:
            @staticmethod
            def extract_intent(_messages):
                return {"error": "llm_call_failed", "reason": "ReadTimeout provider token=secret"}

        service = IntentUnderstandingService(engine=TimedOutEngine())
        result = service.extract_intent("session_timeout_reason", [self._turn("排序算法45分钟")])

        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["fallback_reason"], "timeout")
        self.assertNotIn("secret", str(result))

    def test_connection_failure_has_specific_safe_category(self):
        class DisconnectedEngine:
            @staticmethod
            def extract_intent(_messages):
                return {"error": "llm_call_failed", "reason": "Connection refused: secret"}

        service = IntentUnderstandingService(engine=DisconnectedEngine())
        result = service.extract_intent("session_connection_reason", [self._turn("排序算法45分钟")])

        self.assertEqual(result["fallback_reason"], "engine_unavailable")
        self.assertNotIn("secret", str(result))

    def test_successful_extraction_has_no_fallback_reason(self):
        result = self.service.extract_intent("session_success_reason", [self._turn("我想讲快速排序，45分钟")])

        self.assertFalse(result["used_fallback"])
        self.assertIsNone(result["fallback_reason"])

    def test_intent_llm_uses_bounded_single_attempt_client(self):
        with patch("ai_engine.intent.intent_engine.LLMClient") as client_type, patch(
            "ai_engine.intent.intent_engine.resolve_llm_timeout", return_value=120
        ):
            LLMIntentEngine()

        client_type.assert_called_once()
        self.assertEqual(client_type.call_args.kwargs["timeout"], 90)
        self.assertEqual(client_type.call_args.kwargs["max_attempts"], 1)
        self.assertTrue(client_type.call_args.kwargs["disable_sdk_retries"])

    def test_intent_llm_respects_lower_operator_timeout(self):
        with patch("ai_engine.intent.intent_engine.LLMClient") as client_type, patch(
            "ai_engine.intent.intent_engine.resolve_llm_timeout", return_value=25
        ):
            LLMIntentEngine()

        self.assertEqual(client_type.call_args.kwargs["timeout"], 25)

    def test_incomplete_model_response_is_reported_as_degraded(self):
        class IncompleteEngine:
            @staticmethod
            def extract_intent(_messages):
                return {"topic": None, "duration_minutes": None}

        service = IntentUnderstandingService(engine=IncompleteEngine())
        result = service.extract_intent("session_invalid_response", [self._turn("帮我设计课件")])

        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["fallback_reason"], "invalid_model_response")

    def test_confirm_unknown_session_raises(self):
        with self.assertRaises(IntentSessionNotFound):
            self.service.confirm_intent("missing")


if __name__ == "__main__":
    unittest.main()
