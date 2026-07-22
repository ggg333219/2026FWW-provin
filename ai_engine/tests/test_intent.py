import pytest

from ai_engine.intent.intent_engine import IntentEngine


def test_extract_intent_basic():
    messages = [
        {"role": "teacher", "content": "帮我做一份45分钟的排序算法课件，面向大一计算机专业，讲练结合。包括冒泡排序, 快速排序"}
    ]
    engine = IntentEngine()
    intent = engine.extract_intent(messages)
    assert intent.topic and "排序" in intent.topic
    assert intent.duration_minutes == 45
    assert intent.target_student and "大一" in intent.target_student
    assert "topic" not in intent.missing_fields


def test_generate_followups_when_missing():
    messages = [{"role": "teacher", "content": "请帮我做一份课件"}]
    engine = IntentEngine()
    intent = engine.extract_intent(messages)
    followups = engine.generate_followup_questions(intent)
    assert len(followups) >= 1
import unittest

from ai_engine.core import IntentSummary, DialogueTurn, TurnType
from ai_engine.intent.service import IntentUnderstandingService


class IntentUnderstandingTests(unittest.TestCase):
    def test_extract_intent_returns_summary_with_missing_fields(self):
        service = IntentUnderstandingService()
        messages = [
            DialogueTurn(role="teacher", content="帮我做一节关于排序算法的课", turn_type=TurnType.INITIAL),
            DialogueTurn(role="assistant", content="我可以帮您生成一节课程", turn_type=TurnType.CLARIFYING_ANSWER),
        ]

        result = service.extract_intent("session_001", messages)
        summary = IntentSummary(**result["intent_summary"])

        self.assertEqual(summary.topic, "排序算法")
        self.assertIn("duration_minutes", summary.missing_fields)
        self.assertIn("style", summary.missing_fields)

    def test_followup_questions_are_generated_for_missing_fields(self):
        service = IntentUnderstandingService()
        summary = IntentSummary(topic="排序算法")

        questions = service.build_followup_questions(summary)

        self.assertTrue(questions)
        self.assertIn("这节课预计多长时间？", questions)


if __name__ == "__main__":
    unittest.main()
