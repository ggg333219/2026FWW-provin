"""
MockLLMClient 集成测试 — 验证 MockLLMClient 在各 gen 模块中的使用。

测试内容包括：
1. MockLLMClient 自身功能（预设响应、调用日志、fallback）
2. 注入 OutlineBuilder 验证确定性大纲生成
3. 注入 NodeGenerator 验证确定性节点生成
"""

import sys
import unittest
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_engine.gen.tests.mock_llm import MockLLMClient
from ai_engine.gen.outline import OutlineBuilder, OutlineConfig
from ai_engine.gen.node import NodeGenerator, NodeGenConfig


class TestMockLLMClient(unittest.TestCase):
    """MockLLMClient 自身功能测试"""

    def setUp(self):
        self.mock = MockLLMClient()

    def test_chat_fallback_returns_text(self):
        resp = self.mock.chat("system", "user message")
        self.assertTrue(resp.used_fallback)
        self.assertIn("[mock]", resp.content)

    def test_chat_with_schema_preset(self):
        preset = {"nodes": [{"title": "test_node", "summary": "test"}]}
        self.mock.set_json_response(preset)
        result = self.mock.chat_with_schema("sys", "usr", {"type": "object"})
        self.assertEqual(result["nodes"][0]["title"], "test_node")

    def test_call_log_records_method_name(self):
        self.mock.chat("s", "u")
        self.mock.chat_json("s", "u")
        self.mock.chat_with_schema("s", "u", {"type": "object"})
        self.assertEqual(len(self.mock.call_log), 3)
        self.assertEqual(self.mock.call_log[0]["method"], "chat")
        self.assertEqual(self.mock.call_log[1]["method"], "chat_json")
        self.assertEqual(self.mock.call_log[2]["method"], "chat_with_schema")

    def test_last_call_returns_most_recent(self):
        self.mock.chat("s1", "u1")
        self.mock.chat("s2", "u2")
        last = self.mock.last_call()
        self.assertEqual(last["user"], "u2")

    def test_clear_presets_removes_all(self):
        self.mock.set_chat_response("hello")
        self.mock.clear_presets()
        resp = self.mock.chat("s", "u")
        self.assertNotEqual(resp.content, "hello")

    def test_embed_fallback(self):
        vecs = self.mock.embed(["hello", "world"])
        self.assertEqual(len(vecs), 2)
        self.assertEqual(len(vecs[0]), 128)

    def test_embed_preset(self):
        self.mock.set_embed_response([[0.5] * 64])
        vecs = self.mock.embed(["text"])
        self.assertEqual(len(vecs[0]), 64)
        self.assertEqual(vecs[0][0], 0.5)

    def test_chat_messages_fallback(self):
        msgs = [{"role": "user", "content": "hello"}]
        resp = self.mock.chat_messages(msgs)
        self.assertIn("[mock messages]", resp.content)

    def test_json_response_also_sets_chat_with_schema(self):
        preset = {"key": "value"}
        self.mock.set_json_response(preset)
        r1 = self.mock.chat_json("s", "u")
        r2 = self.mock.chat_with_schema("s", "u", {})
        self.assertEqual(r1, preset)
        self.assertEqual(r2, preset)


class TestMockLLMInOutlineBuilder(unittest.TestCase):
    """注入 MockLLMClient 到 OutlineBuilder 的集成测试"""

    def setUp(self):
        self.mock = MockLLMClient()
        self.builder = OutlineBuilder(
            config=OutlineConfig(temperature=0),
            llm_client=self.mock,
        )

    def test_build_outline_with_preset(self):
        """预设响应 → OutlineBuilder 返回确定性结果"""
        expected_nodes = [
            {"title": "课程导入", "summary": "概念引入", "node_type": "title"},
            {"title": "核心知识", "summary": "讲解", "node_type": "content"},
        ]
        self.mock.set_json_response({"nodes": expected_nodes})

        intent = {"title": "测试课程", "description": "测试描述", "key_points": ["知识点1", "知识点2"]}
        # build_outline 内部调用 LLM 并捕获异常，预设响应会走 LLM 路径
        result = self.builder.build(intent)

        # 即使 mock 返回了预设值，需要 normalize_stage2_nodes 处理，可能改变结构
        self.assertIn("nodes", result)
        self.assertIn("used_fallback", result)
        # 确认调用日志中有记录
        self.assertIn("chat_with_schema", [c["method"] for c in self.mock.call_log])

    def test_build_outline_fallback_on_empty_preset(self):
        """无预设响应 → OutlineBuilder 应使用 fallback 大纲"""
        self.mock.clear_presets()
        intent = {"title": "测试课程", "description": "测试描述", "key_points": ["知识点1"]}
        result = self.builder.build(intent)
        # fallback 模式应返回至少 1 个节点
        self.assertIn("nodes", result)
        self.assertGreater(len(result["nodes"]), 0)
        # 调用日志应记录 chat_with_schema
        last = self.mock.last_call()
        self.assertEqual(last["method"], "chat_with_schema")
        self.assertIn("测试课程", last["user"])

    def test_call_log_contains_user_message(self):
        """调用日志应包含给 LLM 的用户提示词"""
        self.mock.set_json_response({"nodes": []})
        self.builder.build({"title": "数学", "description": "代数", "key_points": ["代数"]})
        last = self.mock.last_call()
        self.assertIn("数学", last["user"])


class TestMockLLMInNodeGenerator(unittest.TestCase):
    """注入 MockLLMClient 到 NodeGenerator 的集成测试"""

    def setUp(self):
        self.mock = MockLLMClient()
        self.generator = NodeGenerator(
            config=NodeGenConfig(temperature=0),
            llm_client=self.mock,
        )

    def test_generate_single_node_with_preset(self):
        """预设响应 → NodeGenerator 返回确定性节点内容"""
        expected = {"script": "这是预设的教学脚本内容。", "mindmap_markdown": "## 测试", "interactive_questions": [], "reteach_script": "", "transition": ""}
        self.mock.set_json_response(expected)

        node = {"title": "测试节点", "summary": "测试", "content": "测试内容", "node_type": "content"}
        result = self.generator.generate_single(node)

        self.assertEqual(result["script"], "这是预设的教学脚本内容。")
        last = self.mock.last_call()
        self.assertEqual(last["method"], "chat_json")

    def test_generate_single_node_fallback(self):
        """无预设 → NodeGenerator 使用 fallback 文本"""
        node = {"title": "测试节点", "summary": "测试", "content": "测试内容", "node_type": "content"}
        result = self.generator.generate_single(node)
        # fallback 应返回含 script 字段的字典
        self.assertIn("script", result)
        self.assertGreater(len(result["script"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)