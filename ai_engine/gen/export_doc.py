"""
DOCX 导出模块 — S3 课件生成

职责：
  结构化节点数组 → .docx 文件

流程：
  节点数组 → doc_exporter → .docx → MinIO / 本地
"""

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE


def _as_mapping(node: Any) -> dict[str, Any]:
    """Normalize dict and Pydantic TeachingNode inputs for export rendering."""
    if isinstance(node, dict):
        return node
    if hasattr(node, "model_dump"):
        return node.model_dump()
    if hasattr(node, "dict"):
        return node.dict()
    return vars(node)


@dataclass
class ExportDocConfig:
    """DOCX 导出配置"""
    output_dir: str = "uploads/exports"


class DOCExporter:
    """结构化节点 → .docx 导出器"""

    def __init__(self, config: ExportDocConfig | None = None):
        self.config = config or ExportDocConfig()

    def export(self, nodes: list[dict[str, Any]], course_name: str = "课件") -> dict[str, Any]:
        """将节点数组导出为 .docx

        Args:
            nodes: 结构化节点数组
            course_name: 课程名

        Returns:
            {"path": "输出路径", "sections": N, "file_size": N}
        """
        doc = self._build_document(nodes, course_name)

        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in course_name)
        output_path = Path(self.config.output_dir) / f"{safe_name}.docx"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))

        return {
            "path": str(output_path),
            "sections": len(nodes),
            "file_size": output_path.stat().st_size,
        }

    def export_to_bytes(self, nodes: list[dict[str, Any]], course_name: str = "课件") -> io.BytesIO:
        """导出为内存字节流（供直接上传 MinIO）"""
        doc = self._build_document(nodes, course_name)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf

    def _build_document(self, nodes: list[dict[str, Any]], course_name: str) -> Document:
        doc = Document()

        # 封面
        title_para = doc.add_heading(course_name, level=0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph("")  # 空行

        # 每个节点生成一节
        for idx, node in enumerate(nodes, start=1):
            self._add_node_section(doc, node, idx)

        return doc

    def _add_node_section(self, doc: Document, node: dict[str, Any], index: int) -> None:
        node = _as_mapping(node)
        node_type = node.get("type") or "content"
        title = node.get("title") or f"第{index}节"
        content = node.get("content") or node.get("script") or node.get("summary") or ""

        # 节点标题
        doc.add_heading(f"{index}. {title}", level=1)

        # 根据类型渲染
        if node_type == "title":
            subtitle = node.get("content") or node.get("summary") or ""
            if subtitle:
                para = doc.add_paragraph(subtitle)
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif node_type == "section":
            doc.add_paragraph(content)
            doc.add_paragraph("")  # 分隔
        elif node_type == "content":
            # 内容正文
            doc.add_paragraph(content)

            # 讲授分段
            segments = node.get("segments") or []
            for seg in segments:
                seg_text = str(seg.get("text") or "").strip()
                seg_type = seg.get("segment_type", "")
                if seg_text:
                    p = doc.add_paragraph(seg_text, style="List Bullet")
                    if seg_type:
                        p.style = doc.styles["List Bullet"]
            # 要点
            core_points = node.get("core_points") or []
            if not core_points and isinstance(node.get("key_points"), list):
                core_points = node["key_points"]
            if core_points:
                doc.add_heading("要点", level=2)
                for pt in core_points:
                    doc.add_paragraph(str(pt), style="List Bullet")
            # 例子
            examples = node.get("examples") or []
            if examples:
                doc.add_heading("案例", level=2)
                for ex in examples:
                    doc.add_paragraph(str(ex), style="List Bullet")
        elif node_type == "quiz" or node_type == "interactive":
            doc.add_heading("互动问题", level=2)
            questions = node.get("questions") or node.get("interactive_questions") or []
            for q in questions:
                doc.add_paragraph(str(q), style="List Number")
        elif node_type == "summary":
            points = node.get("key_points") or node.get("content", "").split("\n")
            doc.add_paragraph("本节要点:")
            for p in points[:6]:
                if str(p).strip():
                    doc.add_paragraph(str(p).strip(), style="List Bullet")
