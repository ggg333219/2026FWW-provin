import unittest

from ai_engine.core.schema import normalize_generation_nodes


class TestGenerationNodeNormalization(unittest.TestCase):
    def test_outline_aliases_are_valid_internal_types(self):
        nodes = normalize_generation_nodes([
            {"node_id": "n1", "node_type": "content"},
            {"node_id": "n2", "node_type": "summary"},
            {"node_id": "n3", "type": "quiz"},
            {"node_id": "n4", "node_type": "unknown"},
        ])

        self.assertEqual([node["node_type"] for node in nodes], ["slide", "slide", "quiz", "slide"])
        self.assertEqual([node["type"] for node in nodes], ["slide", "slide", "quiz", "slide"])

    def test_normalization_does_not_mutate_input(self):
        source = [{"node_id": "n1", "node_type": "content"}]
        normalized = normalize_generation_nodes(source)

        self.assertEqual(source[0]["node_type"], "content")
        self.assertEqual(normalized[0]["node_type"], "slide")
