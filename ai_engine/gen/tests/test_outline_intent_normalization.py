"""OutlineBuilder intent 字段归一化测试

覆盖 S1→S3 字段断链回归：
  - S1 意图使用 topic/knowledge_points，大纲生成器要求 title/key_points，
    OutlineBuilder.build 必须归一化，避免退化为「未命名课件」空提示。
  - title/topic 优先级、subtitle→description、knowledge_points→关键点。
  - LLM 空结果 / 异常时回退到兜底大纲。
  - evidence_packet（relevant_chunks）注入「参考材料」。
"""

import unittest

from ai_engine.gen.outline import OutlineBuilder
from ai_engine.gen.tests.mock_llm import MockLLMClient

_NODES_RESPONSE = {
    "nodes": [
        {
            "node_id": "node_001",
            "title": "真实节点一",
            "summary": "节点一摘要",
            "source_span": "span1",
            "prerequisites": [],
        },
        {
            "node_id": "node_002",
            "title": "真实节点二",
            "summary": "节点二摘要",
            "source_span": "span2",
            "prerequisites": ["node_001"],
        },
    ]
}


class TestIntentNormalization(unittest.TestCase):
    def setUp(self):
        self.mock = MockLLMClient()
        self.builder = OutlineBuilder(llm_client=self.mock)

    def _build_prompt(self):
        """取出最近一次 chat_with_schema 调用的 user prompt。"""
        last = self.mock.last_call()
        self.assertIsNotNone(last, "应已调用过 LLM")
        return last["user"]

    # ── 1. S1 字段归一化（断链回归） ──

    def test_s1_topic_knowledge_points_mapped(self):
        """S1 意图只给 topic/knowledge_points/subtitle 时，标题不再退化为未命名课件。"""
        self.mock.set_json_response(_NODES_RESPONSE)
        intent = {
            "topic": "初中数学·一元二次方程",
            "knowledge_points": ["配方法", "公式法"],
            "subtitle": "九年级上·第3章",
        }
        result = self.builder.build(intent)
        prompt = self._build_prompt()

        self.assertIn("# 初中数学·一元二次方程", prompt)
        self.assertNotIn("未命名课件", prompt)
        self.assertIn("九年级上·第3章", prompt)      # subtitle → description
        self.assertIn("配方法", prompt)             # knowledge_points → 关键点
        self.assertIn("公式法", prompt)
        self.assertEqual(len(result["nodes"]), 2)
        self.assertEqual(result["used_fallback"], False)

    def test_title_key_points_style_still_works(self):
        """旧风格 title/description/key_points 依然可用。"""
        self.mock.set_json_response(_NODES_RESPONSE)
        intent = {
            "title": "高等数学·导数",
            "description": "极限与连续之后的内容",
            "key_points": ["导数定义", "求导法则"],
        }
        self.builder.build(intent)
        prompt = self._build_prompt()

        self.assertIn("# 高等数学·导数", prompt)
        self.assertIn("极限与连续之后的内容", prompt)
        self.assertIn("导数定义", prompt)

    def test_title_preferred_over_topic(self):
        """title 与 topic 同时存在时，title 优先。"""
        self.mock.set_json_response(_NODES_RESPONSE)
        intent = {"title": "显式标题", "topic": "备用主题"}
        self.builder.build(intent)
        prompt = self._build_prompt()

        self.assertIn("# 显式标题", prompt)
        self.assertNotIn("备用主题", prompt)

    def test_both_missing_falls_back_unnamed(self):
        """title 与 topic 都缺失时才使用「未命名课件」兜底。"""
        self.mock.set_json_response(_NODES_RESPONSE)
        self.builder.build({"knowledge_points": ["点A"]})
        prompt = self._build_prompt()

        self.assertIn("未命名课件", prompt)

    def test_empty_knowledge_points_no_crash(self):
        """knowledge_points 为空时不应抛异常，仍产出节点。"""
        self.mock.set_json_response(_NODES_RESPONSE)
        result = self.builder.build({"topic": "只有主题"})
        self.assertEqual(len(result["nodes"]), 2)

    # ── 2. 兜底回退 ──

    def test_empty_llm_nodes_uses_fallback(self):
        """LLM 返回空 nodes 时回退到兜底大纲（节点以关键点为标题）。"""
        self.mock.set_json_response({"nodes": []})
        intent = {"topic": "数学", "knowledge_points": ["概念", "应用"]}
        result = self.builder.build(intent)

        self.assertEqual(len(result["nodes"]), 2)
        self.assertEqual(result["nodes"][0]["title"], "概念")
        self.assertEqual(result["nodes"][1]["title"], "应用")

    def test_llm_exception_uses_fallback(self):
        """LLM 抛异常时回退，used_fallback=True。"""
        self.mock.set_json_response(_NODES_RESPONSE)

        def boom(system, user, schema, *, temperature=None, model=None):
            raise RuntimeError("simulated LLM failure")

        self.mock.chat_with_schema = boom
        result = self.builder.build({"topic": "主题", "knowledge_points": ["点1"]})

        self.assertTrue(result["used_fallback"])
        self.assertEqual(result["nodes"][0]["title"], "点1")

    # ── 3. 证据包注入 ──

    def test_evidence_relevant_chunks_formatted(self):
        """evidence_packet.relevant_chunks 应被格式化为「参考材料」段落。"""
        self.mock.set_json_response(_NODES_RESPONSE)
        evidence = {
            "relevant_chunks": [
                {"content": "这是第一条知识库证据内容"},
                {"content": "第二条证据"},
            ]
        }
        self.builder.build({"topic": "主题"}, evidence_packet=evidence)
        prompt = self._build_prompt()

        self.assertIn("## 参考材料", prompt)
        self.assertIn("这是第一条知识库证据内容", prompt)

    def test_evidence_chunks_alias_supported(self):
        """evidence_packet.chunks（旧字段名）也应兼容。"""
        self.mock.set_json_response(_NODES_RESPONSE)
        evidence = {"chunks": [{"content": "旧字段证据"}]}
        self.builder.build({"topic": "主题"}, evidence_packet=evidence)
        prompt = self._build_prompt()

        self.assertIn("旧字段证据", prompt)


if __name__ == "__main__":
    unittest.main()
