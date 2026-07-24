"""导出模块单元测试 — test_export_task.py

测试目标：
  PPTExporter / DOCExporter 导出输出正确格式的文件。
  各种节点类型覆盖。
  异常情况（空节点、非串行化内容）。
"""

import os
import json
import zipfile
import unittest
from pathlib import Path
from io import BytesIO

from ai_engine.gen.export_ppt import PPTExporter, ExportPPTConfig
from ai_engine.gen.export_doc import DOCExporter, ExportDocConfig

# =============================================================================
# 公共测试夹具
# =============================================================================

def _content_nodes() -> list[dict]:
    """生成一组典型的教学节点"""
    return [
        {"node_id": "n1", "title": "课程封面", "type": "title",
         "content": "人工智能导论", "summary": "AI入门课程"},
        {"node_id": "n2", "title": "什么是AI", "type": "content",
         "content": "人工智能（AI）是模拟人类智能的技术。\n包括机器学习、深度学习等。",
         "core_points": ["定义", "范畴"], "summary": "AI基本概念"},
        {"node_id": "n3", "title": "课堂测验", "type": "quiz",
         "questions": ["AI的中文全称是？", "以下哪个不是AI技术？"],
         "summary": "检验理解"},
        {"node_id": "n4", "title": "本章小结", "type": "summary",
         "key_points": ["AI=模拟人类智能", "三大技术分支"],
         "summary": "核心回顾"},
    ]


def _empty_content_nodes() -> list[dict]:
    """带空字段的节点"""
    return [
        {"node_id": "n1", "title": "", "type": "content", "content": ""},
    ]


def _minimal_nodes() -> list[dict]:
    """最小节点"""
    return [{"node_id": "n1", "title": "测试"}]


def _node_with_segments() -> list[dict]:
    """带 segments 的节点（增强模式输出）"""
    return [
        {"node_id": "n1", "title": "开场", "type": "content", "content": "欢迎",
         "segments": [
             {"segment_id": "seg_1", "text": "欢迎来到AI课堂", "segment_type": "opening"},
             {"segment_id": "seg_2", "text": "这是主要内容", "segment_type": "explanation"},
         ]},
    ]


# =============================================================================
# PPTExporter 测试
# =============================================================================

class TestPPTExporter(unittest.TestCase):
    """PPTX 导出功能测试"""

    def setUp(self):
        self.ppt = PPTExporter(ExportPPTConfig(output_dir="/tmp"))

    # ── 基础功能 ──

    def test_export_minimal_nodes(self):
        """最少节点也能导出有效 PPTX"""
        result = self.ppt.export(_minimal_nodes(), "最小测试")
        self.assertGreater(result["pages"], 0)
        self.assertGreater(result["file_size"], 0)
        self.assertTrue(os.path.exists(result["path"]))

    def test_export_content_nodes(self):
        """典型教学节点导出为多页 PPTX"""
        result = self.ppt.export(_content_nodes(), "内容测试")
        self.assertGreaterEqual(result["pages"], 3)
        with zipfile.ZipFile(result["path"]) as z:
            self.assertIn("[Content_Types].xml", z.namelist())
            slide_files = [n for n in z.namelist() if n.startswith("ppt/slides/slide")]
            self.assertGreaterEqual(len(slide_files), 2)

    def test_export_empty_content_still_creates_slides(self):
        """空内容节点仍生成有效幻灯片"""
        result = self.ppt.export(_empty_content_nodes(), "空内容")
        self.assertGreater(result["pages"], 0)
        self.assertGreater(result["file_size"], 100)

    # ── export_to_bytes ──

    def test_export_to_bytes_returns_valid_zip(self):
        """字节流输出是有效 ZIP"""
        buf = self.ppt.export_to_bytes(_content_nodes(), "字节测试")
        self.assertGreater(buf.getbuffer().nbytes, 0)
        with zipfile.ZipFile(buf) as z:
            self.assertIn("[Content_Types].xml", z.namelist())

    def test_export_to_bytes_content_types(self):
        """字节流包含幻灯片内容"""
        buf = self.ppt.export_to_bytes(_content_nodes(), "内容检查")
        with zipfile.ZipFile(buf) as z:
            slides = [n for n in z.namelist() if n.startswith("ppt/slides/slide")]
            self.assertGreaterEqual(len(slides), 2)

    def test_export_to_bytes_minimal(self):
        """最少节点字节流"""
        buf = self.ppt.export_to_bytes(_minimal_nodes(), "最小字节")
        self.assertGreater(buf.getbuffer().nbytes, 100)

    def test_export_to_bytes_segments(self):
        """带 segments 的节点正常输出"""
        buf = self.ppt.export_to_bytes(_node_with_segments(), "分段节点")
        self.assertGreater(buf.getbuffer().nbytes, 0)
        with zipfile.ZipFile(buf) as z:
            self.assertIn("[Content_Types].xml", z.namelist())

    # ── 模板 ──

    def test_export_with_default_template(self):
        """默认模板 id = 'default'"""
        result = self.ppt.export(_content_nodes(), "默认模板", template_id="default")
        self.assertGreater(result["pages"], 0)

    # ── 文件名 ──

    def test_export_filename_contains_course_name(self):
        """输出文件名包含课程名"""
        result = self.ppt.export(_content_nodes(), "文件名测试")
        self.assertIn("文件名测试", result["path"])

    # ── 批量 / 多种节点混合 ──

    def test_export_mixed_types(self):
        """title + content + quiz + summary 混合"""
        nodes = [
            {"node_id": "n1", "title": "封面", "type": "title", "content": "标题"},
            {"node_id": "n2", "title": "正文", "type": "content", "content": "内容", "core_points": ["A"]},
            {"node_id": "n3", "title": "问答", "type": "quiz", "questions": ["Q1"]},
            {"node_id": "n4", "title": "总结", "type": "summary", "key_points": ["K1"]},
        ]
        result = self.ppt.export(nodes, "混合")
        self.assertGreaterEqual(result["pages"], 3)

    def test_export_large_number_of_nodes(self):
        """20个节点快速导出不报错"""
        nodes = [{"node_id": f"n{i}", "title": f"第{i}节", "type": "content", "content": f"这是第{i}节内容"}
                 for i in range(20)]
        result = self.ppt.export(nodes, "大批量")
        self.assertGreaterEqual(result["pages"], 19)

    def test_export_no_type_field(self):
        """节点没有 type 字段也正常处理"""
        nodes = [{"node_id": "n1", "title": "第一节", "content": "内容"}]
        buf = self.ppt.export_to_bytes(nodes, "无类型")
        self.assertGreater(buf.getbuffer().nbytes, 0)

    # ── 一致性 ──

    def test_export_idempotent(self):
        """相同输入两次导出，都生成有效文件"""
        nodes = _content_nodes()
        r1 = self.ppt.export(nodes, "幂等")
        r2 = self.ppt.export(nodes, "幂等")
        self.assertGreater(r1["pages"], 0)
        self.assertGreater(r2["pages"], 0)

    def test_export_no_course_name(self):
        """course_name 为空时不崩溃"""
        nodes = _minimal_nodes()
        result = self.ppt.export(nodes, "")
        self.assertGreater(result["pages"], 0)


# =============================================================================
# DOCExporter 测试
# =============================================================================

class TestDOCExporter(unittest.TestCase):
    """DOCX 导出功能测试"""

    def setUp(self):
        self.doc = DOCExporter(ExportDocConfig(output_dir="/tmp"))

    # ── 基础功能 ──

    def test_export_minimal_nodes(self):
        """最少节点也能导出有效 DOCX"""
        buf = self.doc.export_to_bytes(_minimal_nodes(), "最小测试")
        self.assertGreater(buf.getbuffer().nbytes, 0)
        with zipfile.ZipFile(buf) as z:
            self.assertIn("word/document.xml", z.namelist())

    def test_export_content_nodes(self):
        """典型教学节点导出 DOCX"""
        result = self.doc.export(_content_nodes(), "内容测试")
        self.assertGreater(result["sections"], 0)
        self.assertGreater(result["file_size"], 0)

    def test_export_empty_content_still_creates_doc(self):
        """空内容节点仍生成有效文档"""
        result = self.doc.export(_empty_content_nodes(), "空内容")
        self.assertGreater(result["sections"], 0)

    # ── export_to_bytes ──

    def test_export_to_bytes_returns_valid_docx_zip(self):
        """字节流输出是有效 DOCX ZIP"""
        buf = self.doc.export_to_bytes(_content_nodes(), "字节测试")
        self.assertGreater(buf.getbuffer().nbytes, 0)
        with zipfile.ZipFile(buf) as z:
            self.assertIn("word/document.xml", z.namelist())

    def test_export_to_bytes_minimal(self):
        """最少节点字节流"""
        buf = self.doc.export_to_bytes(_minimal_nodes(), "最小字节")
        self.assertGreater(buf.getbuffer().nbytes, 100)

    def test_export_to_bytes_segments(self):
        """带 segments 的节点正常输出"""
        buf = self.doc.export_to_bytes(_node_with_segments(), "分段节点")
        self.assertGreater(buf.getbuffer().nbytes, 0)
        with zipfile.ZipFile(buf) as z:
            self.assertIn("word/document.xml", z.namelist())

    # ── 混合类型 ──

    def test_export_mixed_types(self):
        """title + content + quiz + summary 混合"""
        nodes = [
            {"node_id": "n1", "title": "封面", "type": "title", "content": "标题"},
            {"node_id": "n2", "title": "正文", "type": "content", "content": "内容"},
            {"node_id": "n3", "title": "问答", "type": "quiz", "questions": ["Q1"]},
            {"node_id": "n4", "title": "总结", "type": "summary", "key_points": ["K1"]},
        ]
        result = self.doc.export(nodes, "混合")
        self.assertGreater(result["sections"], 0)

    def test_export_large_number_of_nodes(self):
        """20个节点快速导出不报错"""
        nodes = [{"node_id": f"n{i}", "title": f"第{i}节", "type": "content", "content": f"这是第{i}节内容"}
                 for i in range(20)]
        result = self.doc.export(nodes, "大批量")
        self.assertGreater(result["sections"], 0)

    def test_export_no_type_field(self):
        """节点没有 type 字段也正常处理"""
        nodes = [{"node_id": "n1", "title": "第一节", "content": "内容"}]
        buf = self.doc.export_to_bytes(nodes, "无类型")
        self.assertGreater(buf.getbuffer().nbytes, 0)

    def test_export_idempotent(self):
        """相同输入两次导出，都生成有效文件"""
        nodes = _content_nodes()
        r1 = self.doc.export(nodes, "幂等")
        r2 = self.doc.export(nodes, "幂等")
        self.assertGreater(r1["sections"], 0)
        self.assertGreater(r2["sections"], 0)


# =============================================================================
# 交叉格式一致性测试
# =============================================================================

class TestExportConsistency(unittest.TestCase):
    """同一组节点同时导出 PPTX 和 DOCX，均有效"""

    def test_pptx_and_docx_both_valid(self):
        """两种格式同时导出，内容一致"""
        nodes = _content_nodes()
        ppt = PPTExporter(ExportPPTConfig(output_dir="/tmp"))
        doc = DOCExporter(ExportDocConfig(output_dir="/tmp"))

        ppt_result = ppt.export(nodes, "交叉验证")
        doc_result = doc.export(nodes, "交叉验证")
        doc_buf = doc.export_to_bytes(nodes, "交叉验证")

        self.assertGreater(ppt_result["pages"], 0)
        self.assertGreater(doc_result["sections"], 0)
        self.assertGreater(doc_buf.getbuffer().nbytes, ppt_result["file_size"] // 2)

    def test_pptx_export_to_bytes_is_deterministic_format(self):
        """export_to_bytes 输出始终是 application/vnd.openxmlformats PPTX"""
        nodes = _minimal_nodes()
        ppt = PPTExporter(ExportPPTConfig(output_dir="/tmp"))
        buf = ppt.export_to_bytes(nodes, "格式检查")
        # 第一个字节是 PK (ZIP 签名)
        self.assertEqual(buf.getvalue()[:2], b"PK")


# =============================================================================
# 导出任务生命周期测试（不依赖 main.py 端点，直接使用 exporter 对象）
# =============================================================================

class TestExportLifecycle(unittest.TestCase):
    """模拟导出任务的生命周期"""

    def test_export_then_read_back_file(self):
        """导出后文件可读"""
        ppt = PPTExporter(ExportPPTConfig(output_dir="/tmp"))
        result = ppt.export(_content_nodes(), "生命周期测试")
        self.assertTrue(os.path.exists(result["path"]))
        self.assertGreater(os.path.getsize(result["path"]), 0)

    def test_export_to_bytes_then_save(self):
        """字节流保存为文件后有效"""
        ppt = PPTExporter(ExportPPTConfig(output_dir="/tmp"))
        buf = ppt.export_to_bytes(_content_nodes(), "字节保存")
        tmp = Path("/tmp") / f"_test_export_bytes_{hash(str(_content_nodes()))}.pptx"
        tmp.write_bytes(buf.getvalue())
        self.assertTrue(tmp.exists())
        self.assertGreater(tmp.stat().st_size, 0)
        # 验证是有效 ZIP
        with zipfile.ZipFile(str(tmp)) as z:
            self.assertIn("[Content_Types].xml", z.namelist())
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
