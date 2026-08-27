"""gen/ 模块单元测试 — S3 课件生成 + S4 个性化满足"""
import json
import os
import re
import unittest
from pathlib import Path

# ── 套件 1: 大纲构建 ──

from ai_engine.gen.outline import OutlineBuilder, OutlineConfig


class TestOutlineBuilder(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.builder = OutlineBuilder()

    def test_build_from_markdown_returns_nodes(self):
        result = self.builder.build_from_markdown("# 测试\n\n这是内容", "测试课")
        self.assertIn("nodes", result)
        self.assertGreater(len(result["nodes"]), 0)

    def test_every_node_has_required_fields(self):
        result = self.builder.build_from_markdown(
            "# AI导论\n\n## 1.1 定义\nAI是模拟人类智能的技术\n\n## 1.2 历史\n发展历程"
        )
        required = {"node_id", "title", "summary", "source_span", "prerequisites"}
        for node in result["nodes"]:
            with self.subTest(node_id=node.get("node_id")):
                self.assertTrue(required.issubset(node.keys()), f"缺少字段: {required - node.keys()}")

    def test_empty_markdown_fallback(self):
        result = self.builder.build_from_markdown("", "空课件")
        self.assertIn("nodes", result)

    def test_build_with_intent(self):
        intent = {"title": "测试", "description": "描述", "key_points": ["点1", "点2"]}
        result = self.builder.build(intent)
        self.assertIn("nodes", result)
        self.assertGreater(len(result["nodes"]), 0)


# ── 套件 2: 节点生成 ──

from ai_engine.gen.node import NodeGenerator, NodeGenConfig


class TestNodeGenerator(unittest.TestCase):
    def setUp(self):
        self.gen = NodeGenerator()

    def test_generate_all_returns_scripts(self):
        nodes = [
            {"node_id": "n1", "title": "定义", "summary": "AI定义"},
            {"node_id": "n2", "title": "历史", "summary": "AI历史"},
        ]
        result = self.gen.generate_all(nodes, "# 测试", "测试课")
        self.assertIn("scripts", result)
        self.assertEqual(len(result["scripts"]), 2)

    def test_every_script_binds_to_node(self):
        nodes = [
            {"node_id": "n1", "title": "定义", "summary": "AI定义"},
            {"node_id": "n2", "title": "历史", "summary": "AI历史"},
        ]
        result = self.gen.generate_all(nodes)
        nids = {n["node_id"] for n in nodes}
        for script in result["scripts"]:
            with self.subTest(node_id=script.get("node_id")):
                self.assertIn(script["node_id"], nids)

    def test_generate_single(self):
        node = {"node_id": "n1", "title": "测试节点", "summary": "摘要", "core_points": ["核心"]}
        result = self.gen.generate_single(node, "测试课")
        self.assertIn("script", result)
        self.assertEqual(result["node_id"], "n1")

    def test_empty_nodes_fallback(self):
        result = self.gen.generate_all([])
        self.assertIn("scripts", result)


# ── 套件 3: PPTX 导出 ──

from ai_engine.gen.export_ppt import PPTExporter, ExportPPTConfig


class TestPPTExporter(unittest.TestCase):
    def setUp(self):
        self.ppt = PPTExporter(ExportPPTConfig(output_dir="/tmp"))

    def test_export_returns_valid_pptx(self):
        nodes = [{"node_id": "n1", "title": "封面", "type": "title", "content": "标题"},
                 {"node_id": "n2", "title": "内容", "type": "content", "content": "正文"}]
        result = self.ppt.export(nodes, "测试")
        self.assertGreater(result["pages"], 0)
        self.assertGreater(result["file_size"], 0)
        import zipfile
        with zipfile.ZipFile(result["path"]) as z:
            self.assertIn("[Content_Types].xml", z.namelist())

    def test_export_to_bytes(self):
        nodes = [{"node_id": "n1", "title": "测试", "content": "内容"}]
        buf = self.ppt.export_to_bytes(nodes, "测试")
        self.assertGreater(buf.getbuffer().nbytes, 0)

    def test_export_with_quiz_and_summary(self):
        nodes = [
            {"node_id": "n1", "title": "测验", "type": "quiz", "questions": ["Q1?", "Q2?"]},
            {"node_id": "n2", "title": "小结", "type": "summary", "key_points": ["K1", "K2"]},
        ]
        result = self.ppt.export(nodes, "测试")
        self.assertEqual(result["pages"], 2)  # 节点同源：不额外插入预览中不存在的封面


# ── 套件 4: DOCX 导出 ──

from ai_engine.gen.export_doc import DOCExporter, ExportDocConfig


class TestDOCExporter(unittest.TestCase):
    def setUp(self):
        self.doc = DOCExporter(ExportDocConfig(output_dir="/tmp"))

    def test_export_returns_valid_docx(self):
        nodes = [{"node_id": "n1", "title": "第一节", "type": "content", "content": "正文"}]
        buf = self.doc.export_to_bytes(nodes, "测试")
        self.assertGreater(buf.getbuffer().nbytes, 0)
        import zipfile
        with zipfile.ZipFile(buf) as z:
            self.assertIn("word/document.xml", z.namelist())

    def test_export_all_types(self):
        nodes = [
            {"node_id": "n1", "title": "封面", "type": "title", "content": "封面"},
            {"node_id": "n2", "title": "内容", "type": "content", "content": "正文", "core_points": ["点1"]},
            {"node_id": "n3", "title": "测验", "type": "quiz", "questions": ["Q1"]},
            {"node_id": "n4", "title": "小结", "type": "summary", "key_points": ["K1"]},
        ]
        result = self.doc.export(nodes, "测试")
        self.assertGreater(result["sections"], 0)


# ── 套件 5: 预览渲染 ──

from ai_engine.gen.preview import PreviewRenderer


class TestPreviewRenderer(unittest.TestCase):
    def setUp(self):
        self.renderer = PreviewRenderer()

    def test_render_returns_html(self):
        nodes = [{"node_id": "n1", "title": "标题", "type": "content", "content": "内容"},
                 {"node_id": "n2", "title": "小结", "type": "summary", "key_points": ["K1"]}]
        html = self.renderer.render(nodes, "测试")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("class=\"slide", html)

    def test_render_quiz_slide(self):
        nodes = [{"node_id": "n1", "title": "测验", "type": "quiz", "questions": ["Q1", "Q2"]}]
        html = self.renderer.render(nodes, "测试")
        self.assertIn("quiz-slide", html)

    def test_render_summary_slide(self):
        nodes = [{"node_id": "n1", "title": "小结", "type": "summary", "key_points": ["K1"]}]
        html = self.renderer.render(nodes, "测试")
        self.assertIn("summary-slide", html)

    def test_render_empty_nodes(self):
        html = self.renderer.render([], "空")
        self.assertIn("<!DOCTYPE html>", html)


# ── 套件 6: 命令解析 ──

from ai_engine.gen.commands import CommandParser, CommandType


class TestCommandParser(unittest.TestCase):
    def setUp(self):
        self.parser = CommandParser()

    def test_parse_single_structured(self):
        result = self.parser.parse({"type": "update_node", "node_id": "n1", "content": "新内容"})
        self.assertTrue(result.is_structured)
        self.assertEqual(len(result.commands), 1)
        self.assertEqual(result.commands[0].type, CommandType.UPDATE_NODE)

    def test_parse_list(self):
        cmds = [
            {"type": "swap_nodes", "node_ids": ["n1", "n2"]},
            {"type": "delete_node", "node_id": "n3"},
        ]
        result = self.parser.parse(cmds)
        self.assertEqual(len(result.commands), 2)

    def test_parse_natural_language(self):
        result = self.parser.parse("把第一节内容改为新内容")
        self.assertFalse(result.is_structured)
        self.assertGreater(len(result.commands), 0)
        self.assertIn(result.commands[0].type, CommandType)

    def test_validate_valid(self):
        cmd = type("Cmd", (), {"type": CommandType.UPDATE_NODE, "params": {"node_id": "n1"}})()
        errors = self.parser.validate(cmd, {"n1", "n2"})
        self.assertEqual(len(errors), 0)

    def test_validate_invalid(self):
        cmd = type("Cmd", (), {"type": CommandType.UPDATE_NODE, "params": {"node_id": "n3"}})()
        errors = self.parser.validate(cmd, {"n1", "n2"})
        self.assertGreater(len(errors), 0)


# ── 套件 7: 节点修补 ──

from ai_engine.gen.patch import NodePatcher
from ai_engine.gen.commands import EditCommand, CommandType


def _cmd(tp, **params):
    return EditCommand(type=CommandType(tp), params=params)


class TestNodePatcher(unittest.TestCase):
    def setUp(self):
        self.patcher = NodePatcher()
        self.nodes = [
            {"node_id": "n1", "title": "第一节", "content": "A"},
            {"node_id": "n2", "title": "第二节", "content": "B"},
            {"node_id": "n3", "title": "第三节", "content": "C"},
        ]

    def test_swap(self):
        result = self.patcher.apply(self.nodes, [_cmd("swap_nodes", node_ids=["n1", "n3"])])
        self.assertEqual(result.nodes[0]["node_id"], "n3")
        self.assertEqual(result.nodes[2]["node_id"], "n1")

    def test_add(self):
        result = self.patcher.apply(self.nodes, [_cmd("add_node", after_node_id="n2", node_id="n4", title="D")])
        self.assertEqual(len(result.nodes), 4)
        self.assertEqual(result.nodes[2]["node_id"], "n4")

    def test_delete(self):
        result = self.patcher.apply(self.nodes, [_cmd("delete_node", node_id="n2")])
        self.assertEqual(len(result.nodes), 2)

    def test_update(self):
        result = self.patcher.apply(self.nodes, [_cmd("update_node", node_id="n1", content="新A")])
        self.assertEqual(result.nodes[0]["content"], "新A")

    def test_merge(self):
        result = self.patcher.apply(self.nodes, [_cmd("merge_nodes", node_ids=["n1", "n2"])])
        self.assertEqual(len(result.nodes), 2)  # merged + n3

    def test_split(self):
        nodes = [{"node_id": "n1", "title": "长内容", "content": "ABCDE"}]
        result = self.patcher.apply(nodes, [_cmd("split_node", node_id="n1", split_point=3)])
        self.assertEqual(len(result.nodes), 2)

    def test_change_template(self):
        result = self.patcher.apply(self.nodes, [_cmd("change_template", template_id="compact")])
        self.assertEqual(len(result.nodes), 3)  # 不改节点数
        self.assertEqual(len(result.changes), 1)


# ── 套件 8: 互动内容 ──

from ai_engine.gen.interactive import InteractiveBuilder


class TestInteractiveBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = InteractiveBuilder()

    def test_build_all_returns_items(self):
        items = self.builder.build_all({"title": "AI", "content": "人工智能"})
        self.assertGreater(len(items), 0)

    def test_build_quiz_returns_questions(self):
        node = {"title": "测试", "interactive_questions": ["Q1?", "Q2?"]}
        quiz = self.builder.build_quiz(node)
        self.assertGreater(len(quiz), 0)

    def test_build_flashcards(self):
        node = {"title": "AI", "segments": [
            {"knowledge_card": {"term": "AI", "definition": "人工智能", "tags": ["core"]}}
        ]}
        cards = self.builder.build_flashcards(node)
        self.assertGreater(len(cards), 0)

    def test_build_vote(self):
        node = {"title": "你对AI的理解是"}
        vote = self.builder.build_vote(node)
        self.assertIsNotNone(vote)


# ── 套件 9: 集成测试 — 全链路 ──

class TestFullPipeline(unittest.TestCase):
    """全链路集成测试"""

    def test_outline_to_preview(self):
        builder = OutlineBuilder()
        gen = NodeGenerator()
        renderer = PreviewRenderer()
        ppt = PPTExporter(ExportPPTConfig(output_dir="/tmp"))

        # 1. 大纲
        outline = builder.build_from_markdown("# AI\n\n## 定义\nAI是智能", "集成测试")
        self.assertGreater(len(outline["nodes"]), 0)

        # 2. 讲稿
        scripts = gen.generate_all(outline["nodes"])
        self.assertEqual(len(scripts["scripts"]), len(outline["nodes"]))

        # 3. 合并
        merged = []
        for n in outline["nodes"]:
            s = next((s for s in scripts["scripts"] if s["node_id"] == n["node_id"]), {})
            merged.append({**n, "script": s.get("script", "")})

        # 4. PPT
        result = ppt.export(merged, "集成测试")
        self.assertGreater(result["pages"], 0)

        # 5. 预览
        html = renderer.render(merged, "集成测试")
        self.assertIn("<!DOCTYPE html>", html)

        # 6. 修改
        patcher = NodePatcher()
        cmds = [_cmd("swap_nodes", node_ids=[merged[0]["node_id"], merged[1]["node_id"]])]
        patch_result = patcher.apply(merged, cmds)
        self.assertNotEqual(patch_result.nodes[0]["node_id"], merged[0]["node_id"])

    def test_api_routes_registered(self):
        from ai_engine.main import app
        routes = {r.path for r in app.routes if hasattr(r, "path")}
        expected = {"/gen/outline", "/gen/nodes", "/gen/export/ppt", "/api/v1/gen/preview",
                    "/api/v1/gen/modify", "/gen/interactive", "/gen/full-pipeline", "/gen/parse-command"}
        self.assertTrue(expected.issubset(routes), f"缺少路由: {expected - routes}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
