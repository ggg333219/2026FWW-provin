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


if __name__ == "__main__":
    unittest.main()
