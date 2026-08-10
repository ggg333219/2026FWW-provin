import unittest

from ai_engine.core import DialogueTurn, IntentSummary, SessionStatus, TurnType
from ai_engine.intent.intent_engine import IntentEngine
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

    def test_confirm_unknown_session_raises(self):
        with self.assertRaises(IntentSessionNotFound):
            self.service.confirm_intent("missing")


if __name__ == "__main__":
    unittest.main()
