"""
文档解析器 (doc_parser.py)

使用成熟开源方案解析各类文档格式：
  - PDF:   Marker（一键转为含 LaTeX 公式的高质量 Markdown）
  - PPTX:  Unstructured（自动提取结构化元素与图表）
  - DOCX:  Unstructured（自动提取结构化元素与图表）

依赖安装：
    pip install marker-pdf
    pip install "unstructured[pptx,docx]"

使用方式：
    from ai_engine.parse.doc_parser import DocumentParser

    parser = DocumentParser("path/to/file.pdf", source_type=SourceType.PDF)
    result = parser.parse()
    # -> [{"type": "text", "page": 1, "content": "### 标题\\n正文..."}, ...]
"""

import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from ai_engine.core.schema import SourceType


def _is_valid_office_file(file_path: str) -> bool:
    """
    检查文件是否为有效的 Office Open XML 格式（DOCX/PPTX 均为 ZIP 压缩包）。

    通过读取文件头判断是否为 ZIP 格式（PK\x03\x04），
    如果是纯文本文件（如用户误将 .txt 重命名为 .docx），返回 False。
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(4)
        return header == b"PK\x03\x04"
    except Exception:
        return False


def _is_valid_pdf(file_path: str) -> bool:
    """
    检查文件是否为有效的 PDF 格式。

    PDF 文件以 '%PDF' 开头（十六进制 25 50 44 46）。
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(4)
        return header == b"%PDF"
    except Exception:
        return False


def _read_as_plain_text(file_path: str) -> list[dict[str, Any]]:
    """
    将任意文件作为纯文本读取（最终回退方案）。

    适用场景：
      - 文件是纯文本但扩展名为 .docx/.pptx 等
      - 结构化解析器均无法处理该文件

    Returns:
        [{"type": "text", "page": 1, "content": str, "metadata": {...}}]
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="gbk") as f:
                text = f.read()
        except Exception:
            text = f"(无法解码文件内容: {file_path})"

    if not text.strip():
        return []

    return [{
        "type": "text",
        "page": 1,
        "content": text.strip(),
        "metadata": {
            "source_type": "plain_text",
            "tool": "fallback",
            "chars": len(text),
        },
    }]


def _image_content_type_to_ext(content_type: str) -> str:
    """MIME content-type → 文件扩展名映射。"""
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
    }
    return mapping.get(content_type, ".png")


class DocumentParser:
    """
    文档解析器，基于开源方案处理 PDF / PPTX / DOCX。

    返回统一的原始块列表（供 ChunkNormalizer 进一步标准化）：
        [
            {
                "type": "text|slide|table",
                "page": int,
                "content": str,       # Markdown 格式文本
                "metadata": {...},    # 格式特有元数据
            },
            ...
        ]
    """

    def __init__(self, file_path: str, source_type: SourceType = SourceType.PDF):
        self.file_path = file_path
        self.source_type = source_type
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件未找到: {file_path}")

    # ======================================================================
    # 主入口
    # ======================================================================

    def parse(self) -> list[dict[str, Any]]:
        """根据 source_type 派发到具体的解析方法。"""
        dispatcher = {
            SourceType.PDF: self._parse_pdf,
            SourceType.PPTX: self._parse_pptx,
            SourceType.DOCX: self._parse_docx,
        }
        parser = dispatcher.get(self.source_type)
        if parser is None:
            raise ValueError(f"DocumentParser 不支持该格式: {self.source_type}")
        return parser()

    # ======================================================================
    # PDF → Marker (主) / PyMuPDF (备) / 纯文本 (最终回退)
    # ======================================================================

    def _parse_pdf(self) -> list[dict[str, Any]]:
        """
        解析 PDF 文件。

        解析链（依次尝试，任一成功即返回）：
          1. Marker — 高质量 Markdown 转换（LaTeX 公式、表格、标题层级）
          2. PyMuPDF — 轻量级页面文本提取
          3. 纯文本回退 — 当文件不是有效 PDF 时
        """
        if not _is_valid_pdf(self.file_path):
            return _read_as_plain_text(self.file_path)

        # 1) Marker 主方案
        try:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict

            converter = PdfConverter(artifact_dict=create_model_dict())
            rendered = converter(self.file_path)

            full_markdown = rendered.markdown or ""
            page_count = rendered.metadata.get("page_count", 0) if hasattr(rendered, "metadata") else 0
            pages = self._split_marker_pages(full_markdown, page_count)

            result: list[dict[str, Any]] = []
            for page_num, content in pages:
                has_math = "\\(" in content or "\\[" in content or "$$" in content
                result.append({
                    "type": "text",
                    "page": page_num,
                    "content": content.strip(),
                    "metadata": {
                        "source_type": "pdf",
                        "tool": "marker",
                        "has_math": has_math,
                        "total_pages": page_count,
                    },
                })

            if result and any(r["content"] for r in result):
                return result

        except ImportError:
            pass  # 降级到 PyMuPDF
        except Exception:
            pass  # 降级到 PyMuPDF

        # 2) PyMuPDF 备选方案
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(self.file_path)
            result: list[dict[str, Any]] = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text().strip()
                if text:
                    result.append({
                        "type": "text",
                        "page": page_num + 1,
                        "content": text,
                        "metadata": {
                            "source_type": "pdf",
                            "tool": "pymupdf",
                            "total_pages": len(doc),
                            "page_chars": len(text),
                        },
                    })

            doc.close()
            if result:
                return result

        except ImportError:
            pass  # 降级到纯文本
        except Exception:
            pass  # 降级到纯文本

        # 3) 最终回退：纯文本读取
        return _read_as_plain_text(self.file_path)

    @staticmethod
    def _split_marker_pages(markdown: str, page_count: int) -> list[tuple[int, str]]:
        """
        将 Marker 输出的连续 Markdown 按页面拆分。

        尝试以下分页标记：
          1. HTML 注释式分页符
          2. Markdown 水平线分隔
          3. 无标记时按段落数均分
        """
        if not markdown.strip():
            return [(1, "")]

        # 尝试各种分页符
        for sep in ["<!-- Page break -->", "<!-- PAGE BREAK -->", "\n---\n", "\n___\n"]:
            if sep in markdown:
                parts = markdown.split(sep)
                return [(i + 1, p) for i, p in enumerate(parts) if p.strip()]

        # 没有显式分页 → 按段落数大致分页
        paragraphs = markdown.split("\n\n")
        if len(paragraphs) <= 1:
            return [(1, markdown)]

        if page_count > 0 and len(paragraphs) >= page_count:
            chunk_size = max(1, len(paragraphs) // page_count)
            pages: list[tuple[int, str]] = []
            for i in range(page_count):
                start = i * chunk_size
                end = start + chunk_size if i < page_count - 1 else len(paragraphs)
                content = "\n\n".join(paragraphs[start:end]).strip()
                if content:
                    pages.append((i + 1, content))
            return pages if pages else [(1, markdown)]

        return [(1, markdown)]

    # ======================================================================
    # PPTX → Unstructured (主) / python-pptx (备) / 纯文本 (最终回退)
    # ======================================================================

    @staticmethod
    def _extract_ppt_images(slide: Any, tmp_dir: str) -> list[dict[str, Any]]:
        """
        从 PPTX 幻灯片中提取嵌入图片，保存为临时文件。

        Args:
            slide: python-pptx Slide 对象。
            tmp_dir: 临时目录路径。

        Returns:
            list[dict]: [
                {"path": "/tmp/.../image_001.jpg", "left": 100, "top": 50,
                 "width": 300, "height": 200, "content_type": "image/jpeg"},
                ...
            ]
        """
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        images: list[dict[str, Any]] = []
        img_idx = 0

        for shape in slide.shapes:
            # 图片形状
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                img_idx += 1
                try:
                    image = shape.image
                    blob = image.blob
                    ext = _image_content_type_to_ext(image.content_type)
                    img_path = os.path.join(tmp_dir, f"ppt_img_{img_idx:03d}{ext}")
                    with open(img_path, "wb") as f:
                        f.write(blob)
                    images.append({
                        "path": img_path,
                        "left": shape.left,
                        "top": shape.top,
                        "width": shape.width,
                        "height": shape.height,
                        "content_type": image.content_type,
                    })
                except Exception:
                    continue

            # 组合形状（group）→ 递归查找内部图片
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                try:
                    for child in shape.shapes:
                        if child.shape_type == MSO_SHAPE_TYPE.PICTURE:
                            img_idx += 1
                            try:
                                image = child.image
                                blob = image.blob
                                ext = _image_content_type_to_ext(image.content_type)
                                img_path = os.path.join(tmp_dir, f"ppt_img_{img_idx:03d}{ext}")
                                with open(img_path, "wb") as f:
                                    f.write(blob)
                                images.append({
                                    "path": img_path,
                                    "left": child.left,
                                    "top": child.top,
                                    "width": child.width,
                                    "height": child.height,
                                    "content_type": image.content_type,
                                })
                            except Exception:
                                continue
                except Exception:
                    continue

        return images

    @staticmethod
    def _describe_image(img_path: str) -> str:
        """
        描述图片内容。

        解析链：
          1. PaddleOCR — 提取图片中的文字（OCR 文本）
          2. Qwen-VL   — 生成图片的视觉描述（VLM Caption）
          3. 标记      — 均不可用时记录图片存在

        Args:
            img_path: 图片文件路径。

        Returns:
            str: 描述文本。
        """
        # 1) PaddleOCR 提取文字
        ocr_text = ""
        try:
            from ai_engine.parse.ocr_engine import OCREngine
            ocr = OCREngine()
            ocr_result = ocr.process(img_path)
            if ocr_result:
                full_text = ocr_result[0].get("content", "").strip()
                if full_text:
                    ocr_text = full_text
        except Exception:
            pass

        # 2) Qwen-VL 视觉描述
        vlm_desc = ""
        try:
            from ai_engine.core.llm import LLMClient
            import base64

            vlm_model = os.getenv("AI_VLM_MODEL", "qwen-vl-plus")
            client = LLMClient(model=vlm_model, temperature=0.1)
            with open(img_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")

            response = client.chat_messages([
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}},
                        {"type": "text",
                         "text": "这是PPT幻灯片中的一张图片。请用中文简要描述："
                                 "1）画面主要内容；2）是否有文字、公式、图表或数据；"
                                 "3）这张图片可能表达什么教学信息。"},
                    ],
                }
            ])
            vlm_desc = response.content.strip()
        except Exception:
            pass

        # 3) 组合描述
        parts: list[str] = []
        if ocr_text:
            parts.append(f"[图片文字]\n{ocr_text}")
        if vlm_desc:
            parts.append(f"[图片描述]\n{vlm_desc}")
        if not parts:
            parts.append("[图片]（无法提取该图片内容）")

        return "\n\n".join(parts)

    def _parse_pptx(self) -> list[dict[str, Any]]:
        """
        解析 PPTX 文件。

        解析链（依次尝试，任一成功即返回）：
          1. Unstructured — 高质量结构化提取（标题/正文/图表/备注）
          2. python-pptx   — 轻量级提取（每张幻灯片文本+备注）
          3. 纯文本回退    — 当文件不是有效 ZIP-PPTX 时
        """
        if not _is_valid_office_file(self.file_path):
            return _read_as_plain_text(self.file_path)

        # 1) Unstructured 主方案
        try:
            from unstructured.partition.pptx import partition_pptx

            elements = partition_pptx(self.file_path)
            if elements:
                return self._build_pptx_result(elements, tool="unstructured")
        except ImportError:
            pass  # 降级到 python-pptx
        except Exception:
            pass  # 降级到 python-pptx

        # 2) python-pptx 备选方案
        try:
            from pptx import Presentation

            prs = Presentation(self.file_path)
            result: list[dict[str, Any]] = []
            tmp_dir = tempfile.mkdtemp(prefix="pptx_images_")

            try:
                for slide_idx, slide in enumerate(prs.slides, start=1):
                    lines: list[str] = []
                    has_table = False
                    has_notes = False
                    image_count = 0

                    for shape in slide.shapes:
                        if shape.has_text_frame:
                            for para in shape.text_frame.paragraphs:
                                text = para.text.strip()
                                if not text:
                                    continue
                                if para == shape.text_frame.paragraphs[0] and len(text) < 80:
                                    lines.append(f"# {text}")
                                else:
                                    lines.append(text)

                        if shape.has_table:
                            has_table = True
                            table = shape.table
                            rows: list[str] = []
                            for row in table.rows:
                                cells = [cell.text.strip() for cell in row.cells]
                                rows.append(" | ".join(cells))
                            lines.append("[表格]\n" + "\n".join(rows))

                    # 备注
                    if slide.has_notes_slide:
                        notes_text = slide.notes_slide.notes_text_frame.text.strip()
                        if notes_text:
                            has_notes = True
                            lines.append(f"[备注]\n{notes_text}")

                    # === 图片提取与描述 ===
                    ppt_images = self._extract_ppt_images(slide, tmp_dir)
                    for img_info in ppt_images:
                        image_count += 1
                        img_path = img_info["path"]
                        description = self._describe_image(img_path)
                        lines.append(f"[图片 {image_count}]\n{description}")

                    content = "\n\n".join(lines)
                    result.append({
                        "type": "slide",
                        "page": slide_idx,
                        "content": content,
                        "metadata": {
                            "source_type": "pptx",
                            "tool": "python-pptx",
                            "has_table": has_table,
                            "has_notes": has_notes,
                            "image_count": image_count,
                        },
                    })
            finally:
                # 清理临时图片文件
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)

            if result:
                return result

        except ImportError:
            pass  # 降级到纯文本
        except Exception:
            pass  # 降级到纯文本

        # 3) 最终回退：纯文本读取
        return _read_as_plain_text(self.file_path)

    @staticmethod
    def _build_pptx_result(elements: list, tool: str = "unstructured") -> list[dict[str, Any]]:
        """将 Unstructured elements 统一构建为 PPTX 输出块列表。"""
        page_elements: dict[int, list[Any]] = {}
        for el in elements:
            page = getattr(el.metadata, "page_number", 1) or 1
            if page not in page_elements:
                page_elements[page] = []
            page_elements[page].append(el)

        result: list[dict[str, Any]] = []
        for page_num in sorted(page_elements.keys()):
            els = page_elements[page_num]
            lines: list[str] = []
            has_table = False
            has_notes = False

            for el in els:
                text = (el.text or "").strip()
                if not text:
                    continue

                category = getattr(el, "category", "") or ""

                if category == "Table":
                    has_table = True
                    lines.append(f"[表格]\n{text}")
                elif category in ("Title", "Header"):
                    lines.append(f"# {text}")
                elif category == "ListItem":
                    lines.append(f"- {text}")
                elif "Note" in category or "Comment" in category:
                    has_notes = True
                    lines.append(f"[备注]\n{text}")
                else:
                    lines.append(text)

            result.append({
                "type": "slide",
                "page": page_num,
                "content": "\n\n".join(lines),
                "metadata": {
                    "source_type": "pptx",
                    "tool": tool,
                    "has_table": has_table,
                    "has_notes": has_notes,
                    "total_elements": len(els),
                },
            })

        return result

    # ======================================================================
    # DOCX → Unstructured (主) / python-docx (备) / 纯文本 (最终回退)
    # ======================================================================

    def _parse_docx(self) -> list[dict[str, Any]]:
        """
        解析 DOCX 文件。

        解析链（依次尝试，任一成功即返回）：
          1. Unstructured — 高质量结构化提取（标题/段落/表格）
          2. python-docx   — 轻量级提取（段落+样式+表格）
          3. 纯文本回退    — 当文件不是有效 ZIP-DOCX 时（如 .txt 重命名）
        """
        # 先检查是否真的是 ZIP 格式的 Office 文件
        if not _is_valid_office_file(self.file_path):
            return _read_as_plain_text(self.file_path)

        # 1) Unstructured 主方案
        try:
            from unstructured.partition.docx import partition_docx

            elements = partition_docx(self.file_path)
            if elements:
                return self._build_docx_result(elements, tool="unstructured")
        except ImportError:
            pass  # 降级到 python-docx
        except Exception:
            pass  # 降级到 python-docx

        # 2) python-docx 备选方案
        try:
            from docx import Document

            doc = Document(self.file_path)
            result: list[dict[str, Any]] = []
            lines: list[str] = []
            table_idx = 0
            current_heading_level = 0

            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue

                style_name = para.style.name.lower() if para.style else ""
                if "heading" in style_name:
                    # 标题另起一块
                    if lines:
                        result.append(self._make_docx_chunk("\n\n".join(lines), len(result) + 1))
                        lines = []
                    # 提取标题级别
                    level = 1
                    for ch in style_name:
                        if ch.isdigit():
                            level = int(ch)
                            break
                    lines.append(f"{'#' * level} {text}")
                else:
                    lines.append(text)

            if lines:
                result.append(self._make_docx_chunk("\n\n".join(lines), len(result) + 1))

            # 表格提取
            for table in doc.tables:
                table_idx += 1
                rows: list[str] = []
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    rows.append(" | ".join(cells))
                table_text = f"[表格 {table_idx}]\n" + "\n".join(rows)
                result.append({
                    "type": "text",
                    "page": len(result) + 1,
                    "content": table_text,
                    "metadata": {
                        "source_type": "docx",
                        "tool": "python-docx",
                        "tables_found": table_idx,
                        "paragraphs": len(doc.paragraphs),
                    },
                })

            if result:
                return result

        except ImportError:
            pass  # 降级到纯文本
        except Exception:
            pass  # 降级到纯文本

        # 3) 最终回退：纯文本读取
        return _read_as_plain_text(self.file_path)

    def _make_docx_chunk(self, content: str, page: int) -> dict[str, Any]:
        """构造 DOCX 解析块（消除重复样板代码）。"""
        return {
            "type": "text",
            "page": page,
            "content": content,
            "metadata": {
                "source_type": "docx",
                "tool": "python-docx",
            },
        }

    @staticmethod
    def _build_docx_result(elements: list, tool: str = "unstructured") -> list[dict[str, Any]]:
        """将 Unstructured elements 统一构建为输出块列表。"""
        page_elements: dict[int, list[Any]] = {}
        for el in elements:
            page = getattr(el.metadata, "page_number", 1) or 1
            if page not in page_elements:
                page_elements[page] = []
            page_elements[page].append(el)

        result: list[dict[str, Any]] = []
        for page_num in sorted(page_elements.keys()):
            els = page_elements[page_num]
            lines: list[str] = []
            tables_found = 0

            for el in els:
                text = (el.text or "").strip()
                if not text:
                    continue

                category = getattr(el, "category", "") or ""

                if category == "Table":
                    tables_found += 1
                    lines.append(f"[表格 {tables_found}]\n{text}")
                elif category in ("Title", "Header"):
                    lines.append(f"# {text}")
                elif category == "ListItem":
                    lines.append(f"- {text}")
                else:
                    lines.append(text)

            result.append({
                "type": "text",
                "page": page_num,
                "content": "\n\n".join(lines),
                "metadata": {
                    "source_type": "docx",
                    "tool": tool,
                    "total_elements": len(els),
                    "tables_found": tables_found,
                },
            })

        return result
