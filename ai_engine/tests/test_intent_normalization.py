"""F01 / F02 回归测试。

F01：真实模型输出的格式校验与逐字段归一。
     断言"单个字段类型偏差不再丢弃整包模型结果"，且归一过程可观测。

F02：知识点合并而非覆盖。
     断言"教师已给出的知识点不再被规则清空"，同时"模型脑补的知识点仍被拒绝"。
"""

import unittest

from ai_engine.core import DialogueTurn, TurnType
from ai_engine.intent.normalize import normalize_intent_payload
from ai_engine.intent.rules import (
    extract_knowledge_points,
    filter_knowledge_point_fragments,
    is_grounded_knowledge_point,
)
from ai_engine.intent.service import IntentUnderstandingService, SESSIONS


def turn(content: str) -> DialogueTurn:
    return DialogueTurn(role="teacher", content=content, turn_type=TurnType.INITIAL)


class StubEngine:
    """模拟真实模型引擎：返回固定字典。"""

    def __init__(self, payload: dict):
        self.payload = payload

    def extract_intent(self, _messages):
        return dict(self.payload)


class F01NormalizationTests(unittest.TestCase):
    """F01：模型输出格式归一。"""

    def test_chinese_bool_is_normalized_instead_of_discarding_payload(self):
        # 模型把 with_interactive 说成中文"需要"——这是真实模型的常见输出。
        payload = {
            "topic": "快速排序",
            "duration_minutes": 45,
            "style": "讲练结合",
            "target_student": "大一计算机",
            "knowledge_points": ["分治思想", "枢轴选择"],
            "output_format": ["ppt"],
            "with_interactive": "需要",
        }
        normalized, notes = normalize_intent_payload(payload)

        self.assertTrue(normalized["with_interactive"])
        self.assertEqual(normalized["topic"], "快速排序")
        self.assertEqual(normalized["knowledge_points"], ["分治思想", "枢轴选择"])
        self.assertTrue(any("with_interactive" in note for note in notes))

    def test_duration_with_unit_suffix_is_normalized(self):
        normalized, _ = normalize_intent_payload({"topic": "排序", "duration_minutes": "45分钟"})

        self.assertEqual(normalized["duration_minutes"], 45)

    def test_out_of_range_duration_is_dropped_not_accepted(self):
        # 0 与 9999 都能通过 pydantic 校验，但都不是合理课时。
        for value in (0, 9999):
            with self.subTest(value=value):
                normalized, notes = normalize_intent_payload({"topic": "排序", "duration_minutes": value})
                self.assertIsNone(normalized["duration_minutes"])
                self.assertTrue(any("duration_minutes" in note for note in notes))

    def test_string_knowledge_points_are_split_into_list(self):
        normalized, notes = normalize_intent_payload(
            {"topic": "排序", "knowledge_points": "冒泡排序、快速排序"}
        )

        self.assertEqual(normalized["knowledge_points"], ["冒泡排序", "快速排序"])
        self.assertTrue(any("knowledge_points" in note for note in notes))

    def test_non_string_list_items_are_dropped_but_siblings_survive(self):
        normalized, notes = normalize_intent_payload(
            {"topic": "排序", "knowledge_points": ["冒泡排序", 123, None, "快速排序"]}
        )

        self.assertEqual(normalized["knowledge_points"], ["冒泡排序", "快速排序"])
        self.assertTrue(any("knowledge_points" in note for note in notes))

    def test_output_format_aliases_are_mapped(self):
        normalized, _ = normalize_intent_payload({"topic": "排序", "output_format": ["PPT", "Word"]})

        self.assertEqual(normalized["output_format"], ["ppt", "doc"])

    def test_unknown_output_format_is_dropped(self):
        normalized, notes = normalize_intent_payload({"topic": "排序", "output_format": ["flash"]})

        self.assertEqual(normalized["output_format"], [])
        self.assertTrue(any("output_format" in note for note in notes))

    def test_undeclared_fields_are_ignored(self):
        normalized, notes = normalize_intent_payload(
            {"topic": "排序", "reasoning": "模型自述的推理过程"}
        )

        self.assertNotIn("reasoning", normalized)
        self.assertTrue(any("未声明字段" in note for note in notes))

    def test_model_missing_fields_is_not_trusted(self):
        # 模型自报 missing_fields 会被服务层按最终摘要重算，不应被带进来。
        normalized, _ = normalize_intent_payload(
            {"topic": "排序", "duration_minutes": 45, "missing_fields": ["topic", "duration_minutes"]}
        )

        self.assertNotIn("missing_fields", normalized)


class F01ServiceBehaviourTests(unittest.TestCase):
    """F01 在服务层的实际表现。"""

    def setUp(self):
        SESSIONS.clear()

    def test_single_bad_field_no_longer_discards_whole_model_result(self):
        engine = StubEngine({
            "topic": "快速排序",
            "duration_minutes": 45,
            "style": "讲练结合",
            "target_student": "大一计算机",
            "knowledge_points": ["分治思想", "枢轴选择"],
            "output_format": ["ppt"],
            "with_interactive": "需要",
        })
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent(
            "f01_single_bad_field",
            [turn("请做45分钟快速排序课件，面向大一计算机专业学生，讲练结合，知识点：分治思想、枢轴选择。")],
        )

        # 关键断言：不再因为 with_interactive 类型偏差就整包降级。
        self.assertFalse(result["used_fallback"])
        self.assertFalse(result["degraded"])
        self.assertIsNone(result["fallback_reason"])
        summary = result["intent_summary"]
        self.assertEqual(summary["topic"], "快速排序")
        self.assertEqual(summary["duration_minutes"], 45)
        self.assertEqual(summary["knowledge_points"], ["分治思想", "枢轴选择"])
        self.assertTrue(result["normalization_notes"])

    def test_clean_model_output_reports_no_normalization_notes(self):
        engine = StubEngine({
            "topic": "快速排序",
            "duration_minutes": 45,
            "style": "讲练结合",
            "target_student": "大一计算机",
            "knowledge_points": ["分治思想"],
            "output_format": ["ppt"],
            "with_interactive": True,
        })
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent("f01_clean_output", [turn("请做45分钟快速排序课件，知识点：分治思想。")])

        self.assertFalse(result["used_fallback"])
        self.assertEqual(result["normalization_notes"], [])

    def test_completely_unusable_output_still_degrades(self):
        # 归一是"救得回就救"，但整包确实不可用时仍必须降级到规则引擎。
        engine = StubEngine({"topic": None, "duration_minutes": None})
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent("f01_unusable_output", [turn("帮我设计课件")])

        self.assertTrue(result["used_fallback"])
        self.assertTrue(result["degraded"])
        self.assertEqual(result["fallback_reason"], "invalid_model_response")

    def test_missing_topic_after_normalization_degrades(self):
        engine = StubEngine({"topic": "   ", "duration_minutes": 45})
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent("f01_blank_topic", [turn("帮我设计课件")])

        self.assertTrue(result["used_fallback"])


class F02KnowledgePointMergeTests(unittest.TestCase):
    """F02：知识点合并而非覆盖。"""

    def setUp(self):
        SESSIONS.clear()

    def test_teacher_stated_knowledge_points_survive_when_rules_miss(self):
        # 教师没有用"知识点/包括"等触发词，规则抽不到；模型抽对了，不能被清空。
        engine = StubEngine({
            "topic": "快速排序",
            "duration_minutes": 45,
            "style": "讲练结合",
            "target_student": "大一学生",
            "knowledge_points": ["分治思想", "枢轴选择"],
            "output_format": ["ppt"],
            "with_interactive": True,
        })
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent(
            "f02_teacher_stated",
            [turn("帮我做一节45分钟的快速排序课，面向大一学生，讲练结合，讲清楚分治思想和枢轴选择。")],
        )

        summary = result["intent_summary"]
        self.assertEqual(summary["knowledge_points"], ["分治思想", "枢轴选择"])
        # 知识点齐了就不应再追问教师。
        self.assertNotIn("knowledge_points", summary["missing_fields"])

    def test_rule_wins_when_teacher_explicitly_labels_knowledge_points(self):
        engine = StubEngine({
            "topic": "快速排序",
            "duration_minutes": 45,
            "style": "讲练结合",
            "target_student": "大一学生",
            "knowledge_points": ["模型多说的一个"],
            "output_format": ["ppt"],
            "with_interactive": True,
        })
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent(
            "f02_rule_priority",
            [turn("帮我做一节45分钟的快速排序课，知识点：分治思想、枢轴选择。")],
        )

        summary = result["intent_summary"]
        # 教师明确标注的清单以规则为准，模型多说的应被舍弃。
        self.assertEqual(summary["knowledge_points"], ["分治思想", "枢轴选择"])

    def test_hallucinated_knowledge_points_are_rejected(self):
        # 教师从未提及"红黑树"，模型自行脑补 —— 必须丢弃。
        engine = StubEngine({
            "topic": "快速排序",
            "duration_minutes": 45,
            "style": "讲练结合",
            "target_student": "大一学生",
            "knowledge_points": ["红黑树", "跳表"],
            "output_format": ["ppt"],
            "with_interactive": True,
        })
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent(
            "f02_hallucination",
            [turn("帮我做一节45分钟的快速排序课，面向大一学生，讲练结合。")],
        )

        self.assertEqual(result["intent_summary"]["knowledge_points"], [])

    def test_style_fragment_is_not_kept_as_knowledge_point(self):
        engine = StubEngine({
            "topic": "快速排序",
            "duration_minutes": 45,
            "style": "活泼",
            "target_student": "大一学生",
            "knowledge_points": ["风格活泼一点"],
            "output_format": ["ppt"],
            "with_interactive": True,
        })
        service = IntentUnderstandingService(engine=engine)
        result = service.extract_intent(
            "f02_style_fragment",
            [turn("我想给大一学生做一节关于快速排序的课，讲课时间45，风格活泼一点。")],
        )

        summary = result["intent_summary"]
        self.assertEqual(summary["knowledge_points"], [])
        self.assertEqual(summary["style"], "活泼")

    def test_interaction_clause_not_polluted_into_knowledge_points(self):
        # 规则把"互动设计：需要"切进了知识点列表 —— 跨字段污染必须消除。
        points = extract_knowledge_points("知识点：分治思想、枢轴选择，互动设计：需要")

        self.assertEqual(points, ["分治思想", "枢轴选择"])
        self.assertNotIn("互动设计：需要", points)


class F02HelperTests(unittest.TestCase):
    """F02 辅助函数。"""

    def test_grounding_requires_teacher_text_evidence(self):
        self.assertTrue(is_grounded_knowledge_point("分治思想", "我们讲清楚分治思想和枢轴选择"))
        self.assertFalse(is_grounded_knowledge_point("红黑树", "我们讲清楚分治思想和枢轴选择"))

    def test_grounding_ignores_punctuation_spacing(self):
        self.assertTrue(is_grounded_knowledge_point("快速排序", "我们讲 快速排序 这个算法"))

    def test_short_teacher_text_does_not_ground_unrelated_points(self):
        # 教师原话过短时，反向包含会让毫不相关的知识点"接地"，等于没校验。
        self.assertFalse(is_grounded_knowledge_point("红黑树", "45"))
        self.assertFalse(is_grounded_knowledge_point("红黑树", "讲排序"))
        # 教师原话足够具体时，反向包含仍然成立（教师说"分治策略"，模型说"分治策略详解"）。
        self.assertTrue(is_grounded_knowledge_point("分治策略详解", "分治策略"))

    def test_fragment_filter_removes_field_clauses_and_fragments(self):
        filtered = filter_knowledge_point_fragments(
            ["分治思想", "互动设计：需要", "风格活泼一点", "大一学生", "课堂小游戏"],
            style="活泼",
            target_student="大一学生",
        )

        self.assertEqual(filtered, ["分治思想"])


if __name__ == "__main__":
    unittest.main()
