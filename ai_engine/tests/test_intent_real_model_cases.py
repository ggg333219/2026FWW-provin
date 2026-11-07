"""真实模型异常输入案例的回归测试（供 F01 归一化统筹覆盖）。

案例来源：团队提供的《S1 意图提取——GLM 真实模型异常输入案例及测试结果》。
固定样例为一裸句式教学需求，真实模型实测出现三类偏差：

- 案例 1（必现）：数组字段返回字符串（``output_format="课件"``、
  ``key_difficulties`` / ``expected_outcomes`` 时而数组时而字符串），
  旧 ``IntentSummary(**result)`` 整包抛 ValidationError → 降级；
- 案例 2（偶发）：思考模型空正文，输出全在 reasoning（在
  ``test_llm_provider_config.py`` 里覆盖）；
- 附带 quirk：``_merge_rule_evidence`` 让规则结论覆盖模型结果，
  导致 topic 带尾巴、知识点误收「至少2道互动选择题」。

同时锁定 ``normalization_notes`` 的正确契约：**干净模型输出被采用时它为空**，
所以不能用它判断是否调用/采用模型，来源判据是 ``model_source``。
"""

import unittest

from ai_engine.core import DialogueTurn, IntentSummary, TurnType
from ai_engine.intent.normalize import normalize_intent_payload
from ai_engine.intent.rules import (
    extract_explicit_knowledge_points,
    extract_topic_strict,
    filter_knowledge_point_fragments,
)
from ai_engine.intent.service import MODEL_SOURCE_REAL, IntentUnderstandingService

# 图片案例 1 的教师原话（裸句式，无「面向…学生」标签）。
TEACHER_TEXT = (
    "帮我做一份45分钟的课件，主题是冒泡排序与快速排序（算法章节），大一计算机专业。"
    "风格案例驱动，学生要有互动环节，包含至少2道互动选择题。"
    "重点讲清楚两种排序的性能差异和适用场景。"
)


def turn(content: str) -> DialogueTurn:
    return DialogueTurn(role="teacher", content=content, turn_type=TurnType.INITIAL)


class ModelCapableEngine:
    """具备模型能力的引擎桩。"""

    def __init__(self, payload: dict):
        self.payload = payload
        self.client = object()
        self.last_unavailable_reason = ""

    def extract_intent(self, _messages):
        return dict(self.payload)


class NormalizationCaseTests(unittest.TestCase):
    """案例 1：数组字段返回字符串，逐字段归一时不牵连其它字段。"""

    def test_string_typed_fields_are_normalized_not_dropped(self):
        raw = {
            "topic": "冒泡排序与快速排序",
            "duration_minutes": "45分钟",
            "style": "案例驱动",
            "target_student": "大一计算机专业",
            "knowledge_points": "冒泡排序、快速排序",
            "output_format": "课件",
            "with_interactive": "需要",
            "key_difficulties": "重点讲清楚两种排序的性能差异和适用场景",
            "expected_outcomes": "能说出两种排序的性能差异",
            "missing_fields": "knowledge_points",
        }
        normalized, notes = normalize_intent_payload(raw)
        summary = IntentSummary(**normalized)

        self.assertEqual(summary.topic, "冒泡排序与快速排序")
        self.assertEqual(summary.duration_minutes, 45)
        self.assertIs(summary.with_interactive, True)
        self.assertEqual(summary.output_format, ["ppt"])
        self.assertEqual(summary.knowledge_points, ["冒泡排序", "快速排序"])
        self.assertEqual(summary.key_difficulties, ["重点讲清楚两种排序的性能差异和适用场景"])
        self.assertEqual(summary.expected_outcomes, ["能说出两种排序的性能差异"])
        # 模型自报的 missing_fields 一律由服务层重算，不采信。
        self.assertEqual(summary.missing_fields, [])
        self.assertTrue(notes, "存在多处格式偏差时应留下归一说明")

    def test_plain_natural_language_format_is_mapped_by_keyword(self):
        for value, expected in (
            ("PPT演示文稿", ["ppt"]),
            ("Word教案", ["doc"]),
            ("一份课件", ["ppt"]),
        ):
            with self.subTest(value=value):
                normalized, _ = normalize_intent_payload({"output_format": value})
                self.assertEqual(IntentSummary(**normalized).output_format, expected)

    def test_clean_model_output_produces_no_notes(self):
        raw = {
            "topic": "冒泡排序与快速排序",
            "duration_minutes": 45,
            "style": "案例驱动",
            "target_student": "大一计算机专业",
            "knowledge_points": ["冒泡排序", "快速排序"],
            "output_format": ["ppt", "doc"],
            "with_interactive": True,
            "key_difficulties": ["性能差异"],
            "expected_outcomes": ["能说出差异"],
        }
        normalized, notes = normalize_intent_payload(raw)
        self.assertEqual(notes, [])
        self.assertEqual(IntentSummary(**normalized).topic, "冒泡排序与快速排序")


class MergePriorityCaseTests(unittest.TestCase):
    """附带 quirk：规则结论不应把尾巴 / 互动要求带进最终结果。"""

    def test_strict_topic_does_not_carry_the_next_field(self):
        topic = extract_topic_strict(TEACHER_TEXT)
        self.assertIsNotNone(topic)
        self.assertIn("冒泡排序", topic)
        self.assertNotIn("大一计算机专业", topic)
        self.assertNotIn("风格案例驱动", topic)

    def test_interaction_requirement_is_not_a_knowledge_point(self):
        self.assertEqual(extract_explicit_knowledge_points(TEACHER_TEXT), [])
        self.assertEqual(
            filter_knowledge_point_fragments(["至少2道互动选择题", "冒泡排序"]),
            ["冒泡排序"],
        )

    def test_merge_keeps_clean_topic_and_grounded_points(self):
        model_summary = IntentSummary(
            topic="冒泡排序与快速排序",
            duration_minutes=45,
            style="案例驱动",
            target_student="大一计算机专业",
            knowledge_points=["冒泡排序", "快速排序", "至少2道互动选择题"],
            output_format=["ppt", "doc"],
            with_interactive=True,
        )
        merged = IntentUnderstandingService()._merge_rule_evidence(
            model_summary, [{"role": "teacher", "content": TEACHER_TEXT}]
        )
        self.assertNotIn("大一计算机专业", merged.topic or "")
        self.assertNotIn("至少2道互动选择题", merged.knowledge_points)
        self.assertIn("冒泡排序", merged.knowledge_points)


class NotesContractTests(unittest.TestCase):
    """契约更正：干净模型输出被采用时 normalization_notes 为空。"""

    def test_clean_model_output_is_real_model_with_empty_notes(self):
        engine = ModelCapableEngine(
            {
                "topic": "冒泡排序与快速排序",
                "duration_minutes": 45,
                "style": "案例驱动",
                "target_student": "大一计算机专业",
                "knowledge_points": ["冒泡排序", "快速排序"],
                "output_format": ["ppt"],
                "with_interactive": True,
            }
        )
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent("contract_clean", [turn(TEACHER_TEXT)])

        self.assertEqual(result["model_source"], MODEL_SOURCE_REAL)
        self.assertFalse(result["used_fallback"])
        self.assertEqual(result["normalization_notes"], [])
        # 结论：该字段为空时不能反推"没用模型"，必须读 model_source。


if __name__ == "__main__":
    unittest.main()
