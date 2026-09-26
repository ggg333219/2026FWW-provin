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
from docx.oxml.ns import qn


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
    output_dir: str = "data/exports"


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
        _format_normalizer(doc)

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
        _format_normalizer(doc)
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
        if node_type == "slide":
            # node.py 数据层已把 "content" 统一映射为 "slide"（与 export_ppt.py /
            # preview.py 的别名处理对齐），这里收敛回 "content"，否则新版课件
            # 导出 DOCX 时正文/segments/key_points 会静默丢失。
            node_type = "content"
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


# =============================================================================
# 标准教案导出（A12 赛题 4b）
#
# 与上方节点排版导出相互独立：节点导出保持原样（回归测试依赖），
# 教案导出走 LessonPlan 模型 + 标准教案版式。
# WPS 兼容红线：只用基础特性（段落/表格/加粗/对齐），中文字体微软雅黑
# （ascii/hAnsi/eastAsia 三处同时设置）。
# =============================================================================

# 统一字体规范：中文正文宋体，西文/数字Times New Roman，标题黑体
FONT_CN_BODY = "宋体"
FONT_CN_HEADING = "黑体"
FONT_EN_BODY = "Times New Roman"


def _apply_run_font(run: Any, cn_name: str = FONT_CN_BODY, en_name: str = FONT_EN_BODY) -> None:
    """统一设置Run的中英文字体，同时写ascii/hAnsi/eastAsia三个属性，WPS/Word全兼容。"""
    run.font.name = en_name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:ascii"), en_name)
    rfonts.set(qn("w:hAnsi"), en_name)
    rfonts.set(qn("w:eastAsia"), cn_name)


def _format_normalizer(doc: Document) -> None:
    """全局格式清洗：遍历所有段落、Run、表格，强制统一字体，不修改粗体/颜色/字号。"""
    # 1. 统一文档默认Style
    styles = doc.styles
    for style_name, cn_font in [("Normal", FONT_CN_BODY), ("List Bullet", FONT_CN_BODY), ("List Number", FONT_CN_BODY)]:
        try:
            st = styles[style_name]
            st.font.name = FONT_EN_BODY
            st.font.size = Pt(12)
            rpr = st.element.get_or_add_rPr()
            rfonts = rpr.get_or_add_rFonts()
            rfonts.set(qn("w:ascii"), FONT_EN_BODY)
            rfonts.set(qn("w:hAnsi"), FONT_EN_BODY)
            rfonts.set(qn("w:eastAsia"), cn_font)
        except:
            pass
    for h_level in [1,2,3]:
        try:
            st = styles[f"Heading {h_level}"]
            st.font.name = FONT_EN_BODY
            rpr = st.element.get_or_add_rPr()
            rfonts = rpr.get_or_add_rFonts()
            rfonts.set(qn("w:ascii"), FONT_EN_BODY)
            rfonts.set(qn("w:hAnsi"), FONT_EN_BODY)
            rfonts.set(qn("w:eastAsia"), FONT_CN_HEADING)
        except:
            pass

    # 2. 遍历所有段落Run
    for para in doc.paragraphs:
        is_heading = para.style.name.startswith("Heading") or para.style.name == "Title"
        cn_font = FONT_CN_HEADING if is_heading else FONT_CN_BODY
        for run in para.runs:
            _apply_run_font(run, cn_font=cn_font)

    # 3. 遍历所有表格单元格Run
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    for run in para.runs:
                        _apply_run_font(run, cn_font=FONT_CN_BODY)

    # 4. 遍历页眉页脚
    for section in doc.sections:
        for hf in [section.header, section.footer]:
            for para in hf.paragraphs:
                for run in para.runs:
                    _apply_run_font(run, cn_font=FONT_CN_BODY)


def _set_run(run: Any, text: str | None = None, size: float | None = None, bold: bool = False) -> None:
    if text is not None:
        run.text = text
    cn_font = FONT_CN_HEADING if bold and size >= 14 else FONT_CN_BODY
    _apply_run_font(run, cn_name=cn_font)
    if size is not None:
        run.font.size = Pt(size)
    if bold:
        run.font.bold = True


class LessonPlanDOCExporter:
    """标准教案（LessonPlan）→ .docx 导出器。

    版式（WPS 兼容基础特性）：
      标题居中 → 基本信息表（课程/学科/授课对象/课时）→
      一、教学目标（三维编号列表）→ 二、教学重点与难点 →
      三、教学方法 → 四、教学过程（阶段/教师活动/学生活动/设计意图/时长 5 列表格）→
      五、课堂活动设计 → 六、课后作业 → 七、板书设计（可选）
    """

    def __init__(self, config: ExportDocConfig | None = None):
        self.config = config or ExportDocConfig()

    def export(self, plan: Any, file_name: str | None = None) -> dict[str, Any]:
        """导出教案到本地文件。

        Args:
            plan: LessonPlan 或等价 dict
            file_name: 输出文件名（默认 "{course_name}教案.docx"）

        Returns:
            {"path": 输出路径, "sections": 章节数, "file_size": 字节数}
        """
        doc = self._build_document(plan)
        _format_normalizer(doc)
        plan_dict = _plan_as_mapping(plan)
        safe_name = "".join(
            c if c.isalnum() or c in " _-" else "_" for c in plan_dict.get("course_name") or "教案"
        )
        name = file_name or f"{safe_name}教案.docx"
        output_path = Path(self.config.output_dir) / name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))
        return {
            "path": str(output_path),
            "sections": len(plan_dict.get("teaching_process") or []),
            "file_size": output_path.stat().st_size,
        }

    def export_to_bytes(self, plan: Any) -> io.BytesIO:
        """导出为内存字节流（供上传 MinIO）。"""
        doc = self._build_document(plan)
        _format_normalizer(doc)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return buf

    # ---- 版式构建 ----

    def _build_document(self, plan: Any) -> Document:
        p = _plan_as_mapping(plan)
        doc = Document()

        # 标题（居中）
        title = doc.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_run(title.add_run(f"{p.get('course_name') or '课程'}教案"), size=16, bold=True)

        # 基本信息表（2 行 4 列）
        info = doc.add_table(rows=2, cols=4)
        info.style = "Table Grid"
        info_rows = [
            ["课程名称", p.get("course_name") or "—", "学科", p.get("subject") or "—"],
            ["授课对象", p.get("grade_level") or "—",
             "课时", f"{p.get('duration_minutes') or 45} 分钟"],
        ]
        for r, row_vals in enumerate(info_rows):
            for c, val in enumerate(row_vals):
                cell = info.cell(r, c)
                cell.text = ""
                _set_run(cell.paragraphs[0].add_run(str(val)), size=10.5, bold=(c % 2 == 0))

        self._add_section(doc, "一、教学目标")
        objectives = p.get("teaching_objectives") or []
        for i, obj in enumerate(objectives, start=1):
            dim = str(obj.get("dimension") or "").strip()
            content = str(obj.get("content") or "").strip()
            text = f"{i}. {dim}：{content}" if dim else f"{i}. {content}"
            _set_run(doc.add_paragraph().add_run(text), size=12)

        self._add_section(doc, "二、教学重点与难点")
        kd = p.get("key_difficulties") or {}
        key_points = _as_str_list(kd.get("key_points") if isinstance(kd, dict) else kd)
        difficult_points = _as_str_list(
            kd.get("difficult_points") if isinstance(kd, dict) else []
        )
        _set_run(doc.add_paragraph().add_run("教学重点："), size=12, bold=True)
        for i, item in enumerate(key_points, start=1):
            _set_run(doc.add_paragraph().add_run(f"（{i}）{item}"), size=12)
        _set_run(doc.add_paragraph().add_run("教学难点："), size=12, bold=True)
        for i, item in enumerate(difficult_points, start=1):
            _set_run(doc.add_paragraph().add_run(f"（{i}）{item}"), size=12)
        if not key_points and not difficult_points:
            _set_run(doc.add_paragraph().add_run("（依教学实际填写）"), size=12)

        self._add_section(doc, "三、教学方法")
        methods = _as_str_list(p.get("teaching_methods"))
        if methods:
            _set_run(doc.add_paragraph().add_run("、".join(methods)), size=12)
        else:
            _set_run(doc.add_paragraph().add_run("讲授法"), size=12)

        self._add_section(doc, "四、教学过程")
        self._add_process_table(doc, p.get("teaching_process") or [])

        self._add_section(doc, "五、课堂活动设计")
        activities = p.get("classroom_activities") or []
        activity_lines = [
            (f"{i}. {a.get('name') or '课堂活动'}"
             + (f"：{a.get('description')}" if str(a.get('description') or '').strip() else ""))
            for i, a in enumerate(activities, start=1) if isinstance(a, dict)
        ]
        activity_lines += [
            f"{len(activity_lines) + 1}. {a}"
            for a in _as_str_list(activities)
        ]
        if activity_lines:
            for line in activity_lines:
                _set_run(doc.add_paragraph().add_run(line), size=12)
        else:
            _set_run(doc.add_paragraph().add_run("结合课堂互动环节灵活组织。"), size=12)

        self._add_section(doc, "六、课后作业")
        homework = _as_str_list(p.get("homework"))
        if homework:
            for i, item in enumerate(homework, start=1):
                _set_run(doc.add_paragraph().add_run(f"{i}. {item}"), size=12)
        else:
            _set_run(doc.add_paragraph().add_run("完成教材配套练习，复习本节要点。"), size=12)

        board_design = str(p.get("board_design") or "").strip()
        if board_design:
            self._add_section(doc, "七、板书设计")
            for line in board_design.splitlines():
                if line.strip():
                    _set_run(doc.add_paragraph().add_run(line.strip()), size=12)

        return doc

    def _add_section(self, doc: Document, text: str) -> None:
        """章节标题（加粗段落，避免依赖内置 heading 样式字体，WPS 更稳）。"""
        para = doc.add_paragraph()
        para.paragraph_format.space_before = Pt(8)
        para.paragraph_format.space_after = Pt(4)
        _set_run(para.add_run(text), size=14, bold=True)

    def _add_process_table(self, doc: Document, phases: list[Any]) -> None:
        """教学过程 5 列表格：阶段 / 教师活动 / 学生活动 / 设计意图 / 时长（分钟）。"""
        headers = ["阶段", "教师活动", "学生活动", "设计意图", "时长（分钟）"]
        rows = [_as_phase_mapping(ph) for ph in (phases or [])]
        if not rows:
            # 永不空：保证表格至少有一行有效内容
            rows = [{
                "phase": "新授", "teacher_activity": "讲授本节核心内容",
                "student_activity": "听讲并记录要点", "design_intent": "达成知识目标",
                "duration_minutes": 45,
            }]

        table = doc.add_table(rows=1 + len(rows), cols=len(headers))
        table.style = "Table Grid"
        for c, header in enumerate(headers):
            cell = table.cell(0, c)
            cell.text = ""
            _set_run(cell.paragraphs[0].add_run(header), size=10.5, bold=True)
        for r, ph in enumerate(rows, start=1):
            values = [
                str(ph.get("phase") or "—"),
                str(ph.get("teacher_activity") or "—"),
                str(ph.get("student_activity") or "—"),
                str(ph.get("design_intent") or "—"),
                str(ph.get("duration_minutes") if ph.get("duration_minutes") is not None else "—"),
            ]
            for c, val in enumerate(values):
                cell = table.cell(r, c)
                cell.text = ""
                _set_run(cell.paragraphs[0].add_run(val), size=10.5)


def _plan_as_mapping(plan: Any) -> dict[str, Any]:
    """LessonPlan / dict 输入统一为 dict。"""
    if isinstance(plan, dict):
        return plan
    if hasattr(plan, "to_dict"):
        return plan.to_dict()
    if hasattr(plan, "model_dump"):
        return plan.model_dump()
    return dict(vars(plan))


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _as_phase_mapping(phase: Any) -> dict[str, Any]:
    if isinstance(phase, dict):
        return phase
    if hasattr(phase, "to_dict"):
        return phase.to_dict()
    if hasattr(phase, "model_dump"):
        return phase.model_dump()
    return dict(vars(phase))
