"""节点时长 + Go 大纲契约 测试

覆盖 M1-4C 边界问题：AI Engine 产出的大纲必须能通过 Go 侧
`validateOutlineNodes`（backend/internal/service/outline_service.go）：
  - node_type ∈ {content, section, quiz, interactive, summary}
  - estimated_duration_minutes > 0
  - summary 非空

分三层验证：
  1. schema.py 的时长工具（normalize_duration_minutes / assign_node_durations）
  2. schema.py 的契约映射（to_outline_contract_node_type / to_outline_contract_nodes）
  3. OutlineBuilder 三个入口（build / build_from_markdown / revise）的端到端输出
"""

import math
import unittest
from unittest.mock import patch

from ai_engine.schema import (
    DEFAULT_NODE_DURATION_MINUTES,
    DEFAULT_TOTAL_DURATION_MINUTES,
    assign_node_durations,
    normalize_duration_minutes,
    normalize_stage2_nodes,
    to_outline_contract_node_type,
    to_outline_contract_nodes,
)
from ai_engine.gen.outline import OutlineBuilder
from ai_engine.gen.tests.mock_llm import MockLLMClient

# Go 大纲确认接口允许的 node_type 枚举
GO_OUTLINE_NODE_TYPES = {"content", "section", "quiz", "interactive", "summary"}


def _node(node_id="node_001", title="节点", node_type="slide", **extra):
    node = {"node_id": node_id, "title": title, "node_type": node_type}
    node.update(extra)
    return node


class TestNormalizeDurationMinutes(unittest.TestCase):
    """单值时长归一化：只接受「有限的正数」。"""

    def test_accepts_positive_numbers(self):
        self.assertEqual(normalize_duration_minutes(5), 5.0)
        self.assertEqual(normalize_duration_minutes(7.5), 7.5)
        self.assertEqual(normalize_duration_minutes("12"), 12.0)
        self.assertEqual(normalize_duration_minutes(" 3.5 "), 3.5)

    def test_rejects_non_positive(self):
        for value in (0, -1, "-5", 0.0):
            self.assertIsNone(normalize_duration_minutes(value), f"{value!r} 应判为非法")

    def test_rejects_non_finite(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            self.assertIsNone(normalize_duration_minutes(value))

    def test_rejects_bool_and_non_numeric(self):
        # bool 是 int 子类，必须显式排除，否则 True 会被当成 1 分钟
        self.assertIsNone(normalize_duration_minutes(True))
        self.assertIsNone(normalize_duration_minutes(False))
        for value in (None, "", "  ", "五分钟", [], {}):
            self.assertIsNone(normalize_duration_minutes(value))


class TestAssignNodeDurations(unittest.TestCase):
    """节点时长分配：保证每个��点都是正数，且总课时可控。"""

    def test_even_split_sums_to_total(self):
        nodes = [_node(f"node_{i:03d}") for i in range(1, 4)]
        assign_node_durations(nodes, 45)
        durations = [n["estimated_duration_minutes"] for n in nodes]
        self.assertEqual(durations, [15, 15, 15])
        self.assertEqual(sum(durations), 45)

    def test_remainder_goes_to_leading_nodes(self):
        nodes = [_node(f"node_{i:03d}") for i in range(1, 4)]
        assign_node_durations(nodes, 50)
        durations = [n["estimated_duration_minutes"] for n in nodes]
        self.assertEqual(sum(durations), 50)
        self.assertEqual(durations, [17, 17, 16])

    def test_total_smaller_than_node_count_never_yields_zero(self):
        nodes = [_node(f"node_{i:03d}") for i in range(1, 6)]
        assign_node_durations(nodes, 2)
        for node in nodes:
            self.assertGreater(node["estimated_duration_minutes"], 0)

    def test_trusts_llm_durations_when_all_present(self):
        """全部节点都带合法时长时不做均分，保留差异（测验/互动不该被抹平）。"""
        nodes = [
            _node("node_001", estimated_duration_minutes=3),
            _node("node_002", estimated_duration_minutes=20),
            _node("node_003", estimated_duration_minutes=5),
        ]
        assign_node_durations(nodes, 45)
        self.assertEqual(
            [n["estimated_duration_minutes"] for n in nodes], [3, 20, 5]
        )

    def test_partial_durations_fall_back_to_even_split(self):
        nodes = [
            _node("node_001", estimated_duration_minutes=3),
            _node("node_002"),  # 缺失
        ]
        assign_node_durations(nodes, 30)
        self.assertEqual(
            [n["estimated_duration_minutes"] for n in nodes], [15, 15]
        )

    def test_without_total_fills_default_and_is_idempotent(self):
        nodes = [_node("node_001"), _node("node_002")]
        assign_node_durations(nodes)
        self.assertEqual(
            [n["estimated_duration_minutes"] for n in nodes],
            [DEFAULT_NODE_DURATION_MINUTES, DEFAULT_NODE_DURATION_MINUTES],
        )
        # 二次调用结果不变（修订路径反复调用不应漂移）
        assign_node_durations(nodes)
        self.assertEqual(
            [n["estimated_duration_minutes"] for n in nodes],
            [DEFAULT_NODE_DURATION_MINUTES, DEFAULT_NODE_DURATION_MINUTES],
        )

    def test_without_total_keeps_existing_and_reads_legacy_aliases(self):
        nodes = [
            _node("node_001", estimated_duration_minutes=8),
            _node("node_002", duration_minutes=6),        # 历史字段名
            _node("node_003", estimated_duration="4"),    # 历史字段名（字符串）
            _node("node_004", estimated_duration_minutes=0),  # 非法 → 默认
        ]
        assign_node_durations(nodes)
        self.assertEqual(
            [n["estimated_duration_minutes"] for n in nodes], [8, 6, 4, DEFAULT_NODE_DURATION_MINUTES]
        )

    def test_rounds_fractional_durations(self):
        nodes = [_node("node_001", estimated_duration_minutes=2.4)]
        assign_node_durations(nodes)
        self.assertEqual(nodes[0]["estimated_duration_minutes"], 2)

    def test_empty_nodes_is_noop(self):
        self.assertEqual(assign_node_durations([], 45), [])

    def test_nan_string_total_falls_back_to_defaults(self):
        nodes = [_node("node_001")]
        assign_node_durations(nodes, float("nan"))
        self.assertEqual(nodes[0]["estimated_duration_minutes"], DEFAULT_NODE_DURATION_MINUTES)


class TestNormalizeStage2Duration(unittest.TestCase):
    """normalize_stage2_nodes 的时长透传。"""

    def test_missing_duration_filled(self):
        nodes = normalize_stage2_nodes([_node("node_001"), _node("node_002")], 40)
        self.assertEqual([n["estimated_duration_minutes"] for n in nodes], [20, 20])

    def test_invalid_duration_replaced(self):
        raw = [
            _node("node_001", estimated_duration_minutes=0),
            _node("node_002", estimated_duration_minutes="abc"),
        ]
        nodes = normalize_stage2_nodes(raw, 10)
        self.assertEqual([n["estimated_duration_minutes"] for n in nodes], [5, 5])

    def test_no_total_still_positive(self):
        nodes = normalize_stage2_nodes([_node("node_001")])
        self.assertGreater(nodes[0]["estimated_duration_minutes"], 0)

    def test_all_node_types_stay_in_engine_whitelist(self):
        """引擎内部白名单不变（slide/section/...），契约映射在出口单独做。"""
        raw = [_node("node_001", node_type="content"), _node("node_002", node_type="weird")]
        nodes = normalize_stage2_nodes(raw, 10)
        self.assertEqual([n["node_type"] for n in nodes], ["slide", "slide"])


class TestOutlineContractMapping(unittest.TestCase):
    """引擎 node_type → Go 大纲契约枚举的边界映射。"""

    def test_engine_types_map_to_go_enum(self):
        self.assertEqual(to_outline_contract_node_type("slide"), "content")
        self.assertEqual(to_outline_contract_node_type("cover"), "content")
        self.assertEqual(to_outline_contract_node_type("divider"), "content")
        self.assertEqual(to_outline_contract_node_type("section"), "section")
        self.assertEqual(to_outline_contract_node_type("quiz"), "quiz")
        self.assertEqual(to_outline_contract_node_type("interactive"), "interactive")
        self.assertEqual(to_outline_contract_node_type("summary"), "summary")

    def test_unknown_and_empty_fall_back_to_content(self):
        for value in (None, "", "unknown", "  ", 123):
            self.assertEqual(to_outline_contract_node_type(value), "content")

    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(to_outline_contract_node_type(" QUIZ "), "quiz")
        self.assertEqual(to_outline_contract_node_type("Section"), "section")

    def test_contract_nodes_fill_summary_and_duration(self):
        nodes = [
            _node("node_001", title="标题一", node_type="slide"),
            _node("node_002", title="标题二", node_type="content", summary="已有摘要"),
        ]
        contracted = to_outline_contract_nodes(nodes)
        for node in contracted:
            self.assertIn(node["node_type"], GO_OUTLINE_NODE_TYPES)
            self.assertTrue(str(node["summary"]).strip(), "summary 不得为空")
            self.assertGreater(node["estimated_duration_minutes"], 0)
            self.assertFalse(math.isnan(node["estimated_duration_minutes"]))
        self.assertEqual(contracted[1]["summary"], "已有摘要")

    def test_contract_nodes_handles_empty_and_bad_input(self):
        self.assertEqual(to_outline_contract_nodes([]), [])
        self.assertEqual(to_outline_contract_nodes(None), [])
        contracted = to_outline_contract_nodes([{}])
        self.assertIn(contracted[0]["node_type"], GO_OUTLINE_NODE_TYPES)
        self.assertGreater(contracted[0]["estimated_duration_minutes"], 0)


class TestOutlineBuilderDurationEndToEnd(unittest.TestCase):
    """OutlineBuilder 三个入口的输出都必须满足 Go 大纲契约。"""

    def setUp(self):
        self.mock = MockLLMClient()
        self.builder = OutlineBuilder(llm_client=self.mock)

    def _assert_go_contract(self, nodes, expected_count=None):
        self.assertTrue(nodes, "不应产出空节点列表")
        if expected_count is not None:
            self.assertEqual(len(nodes), expected_count)
        for node in nodes:
            self.assertIn(
                node["node_type"], GO_OUTLINE_NODE_TYPES,
                f"node_type={node['node_type']!r} 不在 Go 白名单内",
            )
            duration = node["estimated_duration_minutes"]
            self.assertIsInstance(duration, int)
            self.assertGreater(duration, 0, "Go validateOutlineNodes 要求时长 > 0")
            self.assertTrue(str(node["summary"]).strip(), "Go 侧要求 summary 非空")

    def test_build_uses_intent_duration(self):
        self.mock.set_json_response(
            {
                "nodes": [
                    {"node_id": "node_001", "title": "导入", "node_type": "cover"},
                    {"node_id": "node_002", "title": "核心", "node_type": "content"},
                    {"node_id": "node_003", "title": "小结", "node_type": "summary"},
                ]
            }
        )
        result = self.builder.build(
            {"topic": "一元二次方程", "knowledge_points": ["配方"], "duration_minutes": 45}
        )
        self.assertFalse(result["used_fallback"])
        self._assert_go_contract(result["nodes"], expected_count=3)
        self.assertEqual(
            sum(n["estimated_duration_minutes"] for n in result["nodes"]), 45
        )
        # cover → content（Go 侧不认 cover）
        self.assertEqual(result["nodes"][0]["node_type"], "content")

    def test_build_prompt_carries_total_duration(self):
        self.mock.set_json_response({"nodes": [{"node_id": "node_001", "title": "A"}]})
        self.builder.build({"topic": "主题", "duration_minutes": 60})
        call = self.mock.last_call()
        # 总课时写进 user prompt（Markdown 上下文），字段约束写进 system prompt
        self.assertIn("60", call["user"])
        self.assertIn("estimated_duration_minutes", call["system"])

    def test_build_accepts_duration_alias(self):
        self.mock.set_json_response({"nodes": [{"node_id": "node_001", "title": "A"}]})
        result = self.builder.build({"topic": "主题", "estimated_duration_minutes": 30})
        self._assert_go_contract(result["nodes"])

    def test_build_without_duration_still_positive(self):
        self.mock.set_json_response({"nodes": [{"node_id": "node_001", "title": "A"}]})
        result = self.builder.build({"topic": "主题"})
        self._assert_go_contract(result["nodes"])
        self.assertEqual(
            result["nodes"][0]["estimated_duration_minutes"], DEFAULT_NODE_DURATION_MINUTES
        )

    def test_build_trusts_llm_per_node_durations(self):
        self.mock.set_json_response(
            {
                "nodes": [
                    {"node_id": "node_001", "title": "测验", "node_type": "quiz",
                     "estimated_duration_minutes": 3},
                    {"node_id": "node_002", "title": "讲授", "node_type": "content",
                     "estimated_duration_minutes": 27},
                ]
            }
        )
        result = self.builder.build({"topic": "主题", "duration_minutes": 30})
        self.assertEqual(
            [n["estimated_duration_minutes"] for n in result["nodes"]], [3, 27]
        )

    def test_build_zero_duration_from_llm_is_repaired(self):
        self.mock.set_json_response(
            {
                "nodes": [
                    {"node_id": "node_001", "title": "A", "estimated_duration_minutes": 0},
                    {"node_id": "node_002", "title": "B", "estimated_duration_minutes": -5},
                ]
            }
        )
        result = self.builder.build({"topic": "主题", "duration_minutes": 20})
        self._assert_go_contract(result["nodes"], expected_count=2)
        self.assertEqual(
            sum(n["estimated_duration_minutes"] for n in result["nodes"]), 20
        )

    def test_fallback_outline_satisfies_contract(self):
        self.mock.set_json_response({"nodes": []})
        result = self.builder.build(
            {"topic": "主题", "knowledge_points": ["概念", "应用"], "duration_minutes": 20}
        )
        self._assert_go_contract(result["nodes"], expected_count=2)
        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["fallback_reason"], "empty_model_response")
        self.assertEqual(
            sum(n["estimated_duration_minutes"] for n in result["nodes"]), 20
        )

    def test_exception_fallback_satisfies_contract(self):
        def boom(system, user, schema, *, temperature=None, model=None):
            raise RuntimeError("simulated LLM failure")

        self.mock.chat_with_schema = boom
        result = self.builder.build({"topic": "主题", "knowledge_points": ["点1"]})
        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["fallback_reason"], "model_error")
        self._assert_go_contract(result["nodes"])

    def test_timeout_fallback_has_safe_reason_category(self):
        def timeout(*_args, **_kwargs):
            raise TimeoutError("provider timed out with internal detail")

        self.mock.chat_with_schema = timeout
        result = self.builder.build({"topic": "主题", "knowledge_points": ["点1"]})

        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["fallback_reason"], "timeout")
        self.assertNotIn("internal detail", result["fallback_reason"])

    def test_outline_llm_timeout_is_capped_at_90_seconds(self):
        with patch("ai_engine.gen.outline.resolve_llm_timeout", return_value=120):
            llm = OutlineBuilder()._get_llm()

        self.assertEqual(llm.timeout, 90)
        self.assertEqual(llm.max_attempts, 1)
        self.assertTrue(llm.disable_sdk_retries)
        self.assertTrue(llm.stop_schema_fallback_on_error)

    def test_outline_respects_an_explicitly_lower_timeout(self):
        with patch("ai_engine.gen.outline.resolve_llm_timeout", return_value=15):
            llm = OutlineBuilder()._get_llm()

        self.assertEqual(llm.timeout, 15)

    def test_build_from_markdown_satisfies_contract(self):
        self.mock.set_json_response(
            {"nodes": [{"node_id": "node_001", "title": "A"}, {"node_id": "node_002", "title": "B"}]}
        )
        result = self.builder.build_from_markdown("# 课件", course_name="课程")
        self._assert_go_contract(result["nodes"], expected_count=2)
        self.assertEqual(
            sum(n["estimated_duration_minutes"] for n in result["nodes"]),
            DEFAULT_TOTAL_DURATION_MINUTES,
        )

    def test_build_from_markdown_fallback_satisfies_contract(self):
        self.mock.set_json_response({"nodes": []})
        result = self.builder.build_from_markdown("# 课件")
        self._assert_go_contract(result["nodes"])

    def test_revise_keeps_original_durations(self):
        """教师改文案不该把手工调过的节点时长抹平。"""
        self.mock.set_json_response(
            {"nodes": [{"node_id": "node_001", "title": "改后标题"}]}
        )
        original = [
            {"node_id": "node_001", "title": "原标题", "node_type": "slide",
             "summary": "原摘要", "estimated_duration_minutes": 18},
        ]
        result = self.builder.revise(original, "把标题改一下")
        self._assert_go_contract(result["nodes"], expected_count=1)
        self.assertEqual(result["nodes"][0]["estimated_duration_minutes"], 18)

    def test_revise_new_node_gets_default_duration(self):
        self.mock.set_json_response(
            {
                "nodes": [
                    {"node_id": "node_001", "title": "标题"},
                    {"node_id": "node_002", "title": "新增节点"},
                ]
            }
        )
        original = [
            {"node_id": "node_001", "title": "标题", "node_type": "slide",
             "summary": "摘要", "estimated_duration_minutes": 20},
        ]
        result = self.builder.revise(original, "加一个节点")
        self._assert_go_contract(result["nodes"], expected_count=2)
        self.assertEqual(result["nodes"][0]["estimated_duration_minutes"], 20)
        self.assertEqual(
            result["nodes"][1]["estimated_duration_minutes"], DEFAULT_NODE_DURATION_MINUTES
        )

    def test_revise_llm_duration_wins_over_original(self):
        self.mock.set_json_response(
            {"nodes": [{"node_id": "node_001", "title": "标题",
                        "estimated_duration_minutes": 25}]}
        )
        original = [
            {"node_id": "node_001", "title": "标题", "node_type": "slide",
             "summary": "摘要", "estimated_duration_minutes": 20},
        ]
        result = self.builder.revise(original, "这个节点讲久一点")
        self.assertEqual(result["nodes"][0]["estimated_duration_minutes"], 25)

    def test_revise_empty_llm_nodes_falls_back_to_original(self):
        self.mock.set_json_response({"nodes": []})
        original = [
            {"node_id": "node_001", "title": "标题", "node_type": "slide",
             "summary": "摘要", "estimated_duration_minutes": 12},
        ]
        result = self.builder.revise(original, "随便改改")
        self._assert_go_contract(result["nodes"], expected_count=1)
        self.assertEqual(result["nodes"][0]["estimated_duration_minutes"], 12)

    def test_revise_add_interactive_inserts_one_node_without_retyping_existing_nodes(self):
        """新增互动环节不能把原有内容节点批量改成 interactive。"""
        original = [
            {"node_id": "node_001", "title": "概念讲解", "node_type": "content",
             "summary": "介绍概念", "key_points": ["定义"], "estimated_duration_minutes": 10},
            {"node_id": "node_002", "title": "冒泡排序", "node_type": "content",
             "summary": "讲解流程", "key_points": ["交换"], "estimated_duration_minutes": 15},
        ]
        result = self.builder.revise(
            original,
            "请在冒泡排序之后增加一个互动环节，用投票检验学生是否理解时间复杂度",
        )
        revised = result["nodes"]
        self.assertEqual(len(revised), 3)
        self.assertEqual([n["node_id"] for n in revised], ["node_001", "node_002", "node_003"])
        self.assertEqual([n["node_type"] for n in revised[:2]], ["content", "content"])
        self.assertEqual(revised[2]["node_type"], "interactive")
        self.assertEqual(revised[2]["interactive_plan"]["kind"], "poll")
        self.assertTrue(revised[2]["interactive_plan"]["enabled"])
        self.assertEqual(revised[2]["interactive_plan"]["delivery"], "html5_link")

    def test_revise_add_choice_interactive_inserts_before_numbered_node(self):
        original = [
            {"node_id": "node_001", "title": "定义", "node_type": "content", "summary": "摘要"},
            {"node_id": "node_002", "title": "复杂度", "node_type": "content", "summary": "摘要"},
        ]
        result = self.builder.revise(original, "在第2页之前增加一个选择题互动环节")
        revised = result["nodes"]
        self.assertEqual([n["node_id"] for n in revised], ["node_001", "node_003", "node_002"])
        self.assertEqual(revised[1]["interactive_plan"]["kind"], "quiz")
        self.assertEqual(revised[1]["interactive_plan"]["question_count"], 2)


if __name__ == "__main__":
    unittest.main()
