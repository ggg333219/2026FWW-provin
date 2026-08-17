"""
PPTX 导出模块 — S3 课件生成

职责：
  结构化节点数组 → .pptx 文件

流程：
  template_manager.load(template_id)
  → ppt_exporter.create_presentation(template_path)
  → for each node: 选择布局 → 填充内容
  → 保存 → 上传 MinIO → 返回 URL
"""

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN


@dataclass
class ExportPPTConfig:
    """PPTX 导出配置"""
    template_dir: str = ""
    default_template: str = "default"
    output_dir: str = "uploads/exports"


class PPTExporter:
    """结构化节点 → .pptx 导出器"""

    def __init__(self, config: ExportPPTConfig | None = None):
        self.config = config or ExportPPTConfig()

    # ── 公开入口 ──

    def export(self, nodes: list[dict[str, Any]], course_name: str = "课件",
               template_id: str = "default") -> dict[str, Any]:
        """将节点数组导出为 .pptx

        Args:
            nodes: 结构化节点数组 [{node_id, title, content, type, ...}]
            course_name: 课程名（用作标题）
            template_id: 模板 ID

        Returns:
            {"path": "输出路径", "pages": N, "file_size": N}
        """
        prs = self._create_presentation(template_id)
        slide_count = 0

        # 标题页
        self._add_title_slide(prs, course_name)
        slide_count += 1

        # 节点页
        for node in nodes:
            node_type = node.get("type") or "content"
            handler = self._get_slide_handler(node_type)
            handler(prs, node)
            slide_count += 1

        # 保存
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in course_name)
        output_path = Path(self.config.output_dir) / f"{safe_name}.pptx"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(output_path))

        return {
            "path": str(output_path),
            "pages": slide_count,
            "file_size": output_path.stat().st_size,
        }

    def export_to_bytes(self, nodes: list[dict[str, Any]], course_name: str = "课件",
                        template_id: str = "default") -> io.BytesIO:
        """导出为内存字节流（供直接上传 MinIO）"""
        prs = self._create_presentation(template_id)

        self._add_title_slide(prs, course_name)
        for node in nodes:
            handler = self._get_slide_handler(node.get("type") or "content")
            handler(prs, node)

        buf = io.BytesIO()
        prs.save(buf)
        buf.seek(0)
        return buf

    # ── 幻灯片创建 ──

    def _create_presentation(self, template_id: str) -> Presentation:
        """创建或加载模板"""
        # 如果有模板目录，优先从模板文件加载
        if self.config.template_dir:
            tmpl_path = Path(self.config.template_dir) / f"{template_id}.pptx"
            if tmpl_path.exists():
                return Presentation(str(tmpl_path))
        return Presentation()  # 空白

    def _add_title_slide(self, prs: Presentation, title: str) -> None:
        slide = prs.slides.add_slide(prs.slide_layouts[0])  # 标题布局
        if slide.shapes.title:
            slide.shapes.title.text = title
        if slide.placeholders and len(slide.placeholders) > 1:
            slide.placeholders[1].text = "AI 智能生成课件"

    # ── 节点类型 → 幻灯片处理器 ──

    def _get_slide_handler(self, node_type: str):
        handlers = {
            "title": self._add_title_content_slide,
            "section": self._add_section_slide,
            "content": self._add_content_slide,
            "two_column": self._add_two_column_slide,
            "quiz": self._add_quiz_slide,
            "summary": self._add_summary_slide,
        }
        return handlers.get(node_type, self._add_content_slide)

    def _add_content_slide(self, prs: Presentation, node: dict[str, Any]) -> None:
        """标准内容页：标题 + 正文"""
        slide = prs.slides.add_slide(prs.slide_layouts[1])  # 内容布局
        if slide.shapes.title:
            slide.shapes.title.text = node.get("title", "")
        body = ""
        for key in ("content", "script", "summary", "core_points"):
            val = node.get(key)
            if isinstance(val, list):
                body += "\n".join(f"• {item}" for item in val) + "\n"
            elif isinstance(val, str):
                body += val + "\n"
        if slide.placeholders and len(slide.placeholders) > 1:
            tf = slide.placeholders[1].text_frame
            tf.text = body.strip()

    def _add_title_content_slide(self, prs: Presentation, node: dict[str, Any]) -> None:
        """标题型内容页"""
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        if slide.shapes.title:
            slide.shapes.title.text = node.get("title", "")
        if slide.placeholders and len(slide.placeholders) > 1:
            slide.placeholders[1].text = node.get("content") or node.get("summary") or ""

    def _add_section_slide(self, prs: Presentation, node: dict[str, Any]) -> None:
        """章节分隔页"""
        slide = prs.slides.add_slide(prs.slide_layouts[2])  # 空白布局
        title = node.get("title", "新章节")
        txBox = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(8), Inches(2))
        tf = txBox.text_frame
        tf.text = title
        tf.paragraphs[0].font.size = Pt(36)
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER

    def _add_two_column_slide(self, prs: Presentation, node: dict[str, Any]) -> None:
        """双栏内容页"""
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        if slide.shapes.title:
            slide.shapes.title.text = node.get("title", "")
        content = node.get("content") or node.get("script") or ""
        parts = content.split("\n---\n") if "---" in content else [content, ""]
        if slide.placeholders and len(slide.placeholders) > 1:
            tf = slide.placeholders[1].text_frame
            tf.text = parts[0].strip()

    def _add_quiz_slide(self, prs: Presentation, node: dict[str, Any]) -> None:
        """互动问答页"""
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        if slide.shapes.title:
            slide.shapes.title.text = f"💡 互动: {node.get('title', '随堂测验')}"
        questions = node.get("questions") or node.get("interactive_questions") or ["思考一下?"]
        if slide.placeholders and len(slide.placeholders) > 1:
            tf = slide.placeholders[1].text_frame
            tf.text = "\n".join(f"❓ {q}" for q in questions)

    def _add_summary_slide(self, prs: Presentation, node: dict[str, Any]) -> None:
        """总结页"""
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        if slide.shapes.title:
            slide.shapes.title.text = "📌 本节小结"
        points = node.get("key_points") or node.get("summary", "").split("\n") or ["本节要点"]
        if slide.placeholders and len(slide.placeholders) > 1:
            tf = slide.placeholders[1].text_frame
            tf.text = "\n".join(f"✅ {p}" for p in points[:6])
