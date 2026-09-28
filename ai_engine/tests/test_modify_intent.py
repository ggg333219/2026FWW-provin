import unittest

from ai_engine.gen.modify_intent import ModifyIntentParser, build_modify_intent_schema


class _FakeLLM:
    def __init__(self, result):
        self.result = result

    def chat_with_schema(self, *_args, **_kwargs):
        return self.result


class ModifyIntentContractTests(unittest.TestCase):
    def test_schema_requires_structured_presentation(self):
        schema = build_modify_intent_schema()["schema"]
        self.assertIn("presentation", schema["properties"])
        self.assertIn("presentation", schema["required"])
        self.assertEqual(
            set(schema["properties"]["presentation"]["properties"]),
            {"template_id", "palette", "layout", "font_family", "density"},
        )

    def test_restyle_normalizes_presentation_and_keeps_node_target_empty(self):
        parser = ModifyIntentParser()
        parser._llm = _FakeLLM({
            "target_type": "style",
            "target_ids": [],
            "action": "restyle",
            "secondary_actions": [],
            "constraints": ["科技感"],
            "confidence": 0.92,
            "clarification_needed": False,
            "clarification_question": "",
            "presentation": {
                "template_id": "deck-swiss-edu",
                "palette": "klein-blue",
                "layout": "visual",
                "font_family": "system",
                "density": "minimal",
                "content": "must be ignored",
            },
        })

        result = parser.parse("整体换成科技感", [{"node_id": "node_1", "title": "引言"}])

        self.assertEqual(result["action"], "restyle")
        self.assertEqual(result["target_type"], "style")
        self.assertEqual(result["presentation"]["palette"], "klein-blue")
        self.assertNotIn("content", result["presentation"])

    def test_content_action_cannot_smuggle_presentation_fields(self):
        parser = ModifyIntentParser()
        parser._llm = _FakeLLM({
            "target_type": "node",
            "target_ids": ["node_1"],
            "action": "simplify",
            "secondary_actions": [],
            "constraints": ["保留核心知识点"],
            "confidence": 0.9,
            "clarification_needed": False,
            "clarification_question": "",
            "presentation": {"palette": "klein-blue"},
        })

        result = parser.parse("第一部分精简", [{"node_id": "node_1", "title": "引言"}])

        self.assertEqual(result["presentation"], {
            "template_id": "",
            "palette": "",
            "layout": "",
            "font_family": "",
            "density": "",
        })


class ActiveNodeTargetingTests(unittest.TestCase):
    """「这页」的所指由界面选中决定，不让模型从标题里猜。

    模型只拿到 {node_id, title, summary, node_type, order}——「这页」对它是一句
    无从回答的话。选中页由前端透传，在这里覆盖模型结果。
    """

    NODES = [
        {"node_id": "node_1", "title": "引言"},
        {"node_id": "node_2", "title": "冒泡排序"},
        {"node_id": "node_3", "title": "空间复杂度"},
    ]

    @staticmethod
    def _llm(target_ids, action="expand", confidence=0.9):
        return _FakeLLM({
            "target_type": "node",
            "target_ids": target_ids,
            "action": action,
            "secondary_actions": [],
            "constraints": [],
            "confidence": confidence,
            "clarification_needed": False,
            "clarification_question": "",
            "presentation": {},
        })

    def test_deictic_instruction_uses_selected_page(self):
        """「这页」+ 选中第 3 页 → 改第 3 页，且不追问。

        这是「这页改不动」的直接回归：修好之前，模型选不中 → target_ids 为空
        → _normalize 回一句「请说明是哪一页」。
        """
        parser = ModifyIntentParser()
        parser._llm = self._llm([])  # 模型定位不到 —— 正是需要选中页兜底的场景

        result = parser.parse("这页加个生活案例", self.NODES, active_node_id="node_3")

        self.assertEqual(result["target_ids"], ["node_3"])
        self.assertFalse(result["clarification_needed"])
        self.assertEqual(result["action"], "expand")

    def test_deictic_overrides_model_pick(self):
        """模型猜了另一页，但指令说的是「这页」→ 以选中页为准。"""
        parser = ModifyIntentParser()
        parser._llm = self._llm(["node_1"], action="simplify")

        result = parser.parse("这页减少文字", self.NODES, active_node_id="node_3")

        self.assertEqual(result["target_ids"], ["node_3"])

    def test_explicit_page_number_still_wins(self):
        """显式页号不带指示代词 → 听指令的，不被选中页带偏。"""
        parser = ModifyIntentParser()
        parser._llm = self._llm(["node_3"], action="simplify")

        result = parser.parse("第三页精简", self.NODES, active_node_id="node_1")

        self.assertEqual(result["target_ids"], ["node_3"])

    def test_stale_active_node_is_ignored(self):
        """选中页已不在节点树里（换过版本 / 删过页）→ 忽略它，退回追问。"""
        parser = ModifyIntentParser()
        parser._llm = self._llm([])

        result = parser.parse("这页加个生活案例", self.NODES, active_node_id="node_99")

        self.assertEqual(result["target_ids"], [])
        self.assertTrue(result["clarification_needed"])

    def test_without_active_node_behaviour_is_unchanged(self):
        """不传选中页 → 与加这个字段之前逐字一致（防回归）。"""
        parser = ModifyIntentParser()
        parser._llm = self._llm(["node_2"], action="simplify")

        result = parser.parse("第二页精简", self.NODES)

        self.assertEqual(result["target_ids"], ["node_2"])
        self.assertFalse(result["clarification_needed"])

        # 没选中、模型也定位不到 → 仍然追问，不该凭空挑一页
        parser._llm = self._llm([])
        blank = parser.parse("改一下", self.NODES)
        self.assertEqual(blank["target_ids"], [])
        self.assertTrue(blank["clarification_needed"])

    def test_reorder_does_not_fall_back_to_active_node(self):
        """reorder 的目标是「哪两页」，套用单个选中页只会改错 —— 不兜底。"""
        parser = ModifyIntentParser()
        parser._llm = self._llm([], action="reorder", confidence=0.9)

        result = parser.parse("调整一下顺序", self.NODES, active_node_id="node_3")

        self.assertEqual(result["target_ids"], [])


if __name__ == "__main__":
    unittest.main()
