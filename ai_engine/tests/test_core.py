import tempfile
import unittest
from pathlib import Path

import fitz

from ai_engine.generator import LessonGenerator
from ai_engine.parser import DocumentParser
from ai_engine.qa import QAResponder, QAConfig
from ai_engine.reconstructor import LessonReconstructor


class ParserAndGeneratorTests(unittest.TestCase):
    def test_pdf_parser_keeps_paragraph_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "sample.pdf"
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Title\nPoint one\nPoint two")
            doc.save(str(pdf_path))
            doc.close()

            parsed = DocumentParser(str(pdf_path)).parse()

        self.assertEqual(parsed["total_pages"], 1)
        self.assertIn("Title", parsed["parsed_pages"][0]["content"])
        self.assertIn("\n", parsed["parsed_pages"][0]["content"])

    def test_extract_json_accepts_fenced_output(self):
        payload = """```json
        {"script": "讲稿", "mindmap_markdown": "- 主题"}
        ```"""
        result = LessonGenerator._extract_json(payload)
        self.assertEqual(result["script"], "讲稿")

    def test_fallback_generation_is_not_empty(self):
        generator = LessonGenerator()
        result = generator._fallback_generation(2, "线性回归\n损失函数\n梯度下降", "mock error")

        self.assertTrue(result["script"])
        self.assertTrue(result["mindmap_markdown"])
        self.assertTrue(result["used_fallback"])

    def test_reconstructor_builds_teaching_nodes(self):
        parsed = {
            "doc_id": "doc_test",
            "doc_name": "sample.pdf",
            "doc_type": "pdf",
            "parsed_pages": [
                {"page": 1, "content": "第一章 线性回归\n定义\n应用场景"},
                {"page": 2, "content": "损失函数\n最小二乘\n梯度下降"},
            ],
        }
        reconstructed = LessonReconstructor().reconstruct(parsed)

        self.assertEqual(len(reconstructed["teaching_nodes"]), 2)
        self.assertTrue(reconstructed["chapters"])
        self.assertEqual(reconstructed["teaching_nodes"][0]["next_node_id"], "node_002")

    def test_generate_node_script_fallback_without_api(self):
        generator = LessonGenerator()
        node = {
            "node_id": "node_001",
            "title": "线性回归",
            "summary": "介绍线性回归的基本概念",
            "core_points": ["线性关系", "最小二乘", "预测任务"],
            "examples": ["房价预测"],
            "common_confusions": ["为什么叫线性回归"],
        }
        result = generator.generate_node_script(node, "机器学习")

        self.assertEqual(result["node_id"], "node_001")
        self.assertTrue(result["interactive_questions"])
        self.assertTrue(result["reteach_script"])

    def test_qa_fallback_without_api(self):
        responder = QAResponder(
            parsed_document={"parsed_pages": [{"page": 1, "content": "线性回归用于建模输入和输出关系"}]},
            config=QAConfig(mode="llm"),
        )
        answer = responder.answer("为什么要用线性回归", 1)
        self.assertIn("线性回归", answer["answer"])


if __name__ == "__main__":
    unittest.main()