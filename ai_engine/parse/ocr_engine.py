"""
OCR 引擎 (ocr_engine.py)

基于 PaddleOCR（百度开源）的图片文字提取 + 版面分析。

PaddleOCR 优势：
  - 中文识别效果业界领先（尤其公式、表格、手写体）
  - 内置版面分析 + 表格结构化能力
  - 支持 80+ 语言
  - 纯 Python 依赖，pip install 即用

使用方式：
    from ai_engine.parse.ocr_engine import OCREngine

    ocr = OCREngine()
    result = ocr.process("path/to/image.png")
    # -> [{"type": "text", "page": 1, "content": "...", "metadata": {...}}]

依赖安装：
    pip install paddlepaddle paddleocr
"""

import os
from typing import Any, Optional

from ai_engine.core.llm import LLMClient


class OCREngine:
    """
    基于 PaddleOCR 的图片 OCR 引擎。

    每个图片返回原始块列表供 ChunkNormalizer 进一步标准化。
    支持单张图片批量识别 + 内置版面分析 + 表格结构提取。
    """

    def __init__(self, lang: str = "ch", use_angle_cls: bool = True):
        """
        Args:
            lang: 识别语言，默认 "ch"（中文），支持 "en"、"fr"、"es" 等。
            use_angle_cls: 是否启用文字方向分类（增加精度，略微降低速度）。
        """
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self._ocr_instance = None

    # ======================================================================
    # PaddleOCR 实例（惰性加载）
    # ======================================================================

    @property
    def _ocr(self):
        """PaddleOCR 单例，首次使用时惰性初始化。"""
        if self._ocr_instance is None:
            try:
                from paddleocr import PaddleOCR

                self._ocr_instance = PaddleOCR(
                    use_angle_cls=self.use_angle_cls,
                    lang=self.lang,
                    show_log=False,
                    # 启用表格识别
                    use_space_before_char=True,
                )
            except ImportError:
                raise ImportError(
                    "需要 PaddleOCR: pip install paddlepaddle paddleocr\n"
                    "如果是 CPU 环境: pip install paddlepaddle paddleocr\n"
                    "如果是 GPU 环境: pip install paddlepaddle-gpu paddleocr"
                )
            except Exception as e:
                raise RuntimeError(f"PaddleOCR 初始化失败（可能是首次运行下载模型）: {e}")
        return self._ocr_instance

    # ======================================================================
    # 主入口
    # ======================================================================

    def process(self, image_path: str) -> list[dict[str, Any]]:
        """
        对图片执行 PaddleOCR 识别 + 版面分析。

        PaddleOCR 返回每行文字的详细信息，包括：
          - 文字内容（text）
          - 置信度（confidence）
          - 边界框（box: [左上, 右上, 右下, 左下] 四点坐标）

        本方法将这些信息与版面分析结果合并，返回统一的原始块。

        Args:
            image_path: 图片文件路径。

        Returns:
            list[dict]: 统一原始块列表，每块包含文字内容和元数据。

        Raises:
            FileNotFoundError: 图片文件不存在。
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件未找到: {image_path}")

        # 1. 执行 OCR
        raw = self._ocr.ocr(image_path, cls=True)

        # 2. 提取文字行 + 结构化信息
        lines, full_text, layout_regions = self._extract_lines(raw)

        # 3. 版面分析
        layout = self._analyze_layout(lines, layout_regions)

        return [
            {
                "type": "text",
                "page": 1,
                "content": full_text,
                "metadata": {
                    "ocr_method": "paddleocr",
                    "line_count": len(lines),
                    "layout": layout,
                    "source_file": image_path,
                    "regions": layout_regions,
                    "lines": lines[:50],  # 仅保留前 50 行元数据，避免 payload 过大
                },
            }
        ]

    # ======================================================================
    # 行提取与结构化
    # ======================================================================

    @staticmethod
    def _extract_lines(
        raw: list,
    ) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
        """
        从 PaddleOCR 原始输出中提取结构化的行信息。

        PaddleOCR 输出格式：
          [[[
              [[x1,y1],[x2,y2],[x3,y3],[x4,y4]],  # box 四点坐标
              ("text", confidence)                   # 文字与置信度
          ]]]

        Returns:
            (lines, full_text, regions) 三元组
              - lines:      每行的结构化信息列表
              - full_text:  所有行拼接的纯文本
              - regions:    版面区域划分
        """
        lines: list[dict[str, Any]] = []
        regions: list[dict[str, Any]] = []
        current_region: list[str] = []
        region_top = 0.0

        if not raw or not raw[0]:
            return lines, "", regions

        for idx, item in enumerate(raw[0]):
            box = item[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            text, confidence = item[1]

            # 边界框特征
            y_center = (box[0][1] + box[2][1]) / 2
            x_min = min(p[0] for p in box)
            x_max = max(p[0] for p in box)
            y_min = min(p[1] for p in box)
            y_max = max(p[1] for p in box)
            width = x_max - x_min
            height = y_max - y_min

            lines.append({
                "text": text,
                "confidence": round(confidence, 4),
                "box": {
                    "x_min": round(x_min, 1),
                    "x_max": round(x_max, 1),
                    "y_min": round(y_min, 1),
                    "y_max": round(y_max, 1),
                    "width": round(width, 1),
                    "height": round(height, 1),
                },
                "index": idx,
            })

            # 基于垂直位置做区域划分（简单版面分组）
            if idx == 0:
                region_top = y_center
                current_region.append(text)
            elif abs(y_center - region_top) > height * 1.5:
                # 垂直间距超过一倍行高 → 新区域
                if current_region:
                    regions.append({"type": "text_block", "content": " ".join(current_region)})
                current_region = [text]
                region_top = y_center
            else:
                current_region.append(text)

        # 最后一个区域
        if current_region:
            regions.append({"type": "text_block", "content": " ".join(current_region)})

        full_text = "\n".join(line["text"] for line in lines)
        return lines, full_text, regions

    # ======================================================================
    # 版面分析
    # ======================================================================

    @staticmethod
    def _analyze_layout(
        lines: list[dict[str, Any]],
        regions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        基于 OCR 结果做版面结构推断。

        分析的维度：
          - 文本块数（段落/区域数）
          - 是否有标题（首行较短 <= 30 字符）
          - 是否有表格（检测多行水平对齐的结构）
          - 文字总字符数
          - 平均置信度
        """
        if not lines:
            return {
                "paragraphs": 0,
                "has_title": False,
                "has_table": False,
                "total_chars": 0,
                "avg_confidence": 0.0,
            }

        first_lines_text = [l["text"] for l in lines[:3]]
        has_title = any(len(t) <= 30 for t in first_lines_text) if first_lines_text else False

        # 表格启发式检测：连续多行的 x_min 和 x_max 对齐
        has_table = False
        if len(lines) >= 4:
            aligned_x_min = sum(
                1 for i in range(1, len(lines))
                if abs(lines[i]["box"]["x_min"] - lines[i - 1]["box"]["x_min"]) < 20
            )
            aligned_x_max = sum(
                1 for i in range(1, len(lines))
                if abs(lines[i]["box"]["x_max"] - lines[i - 1]["box"]["x_max"]) < 20
            )
            total_pairs = len(lines) - 1
            if total_pairs > 0:
                has_table = (aligned_x_min / total_pairs > 0.6
                             and aligned_x_max / total_pairs > 0.6)

        total_chars = sum(len(l["text"]) for l in lines)
        avg_confidence = (
            sum(l["confidence"] for l in lines) / len(lines)
            if lines else 0.0
        )

        return {
            "paragraphs": len(regions),
            "has_title": has_title,
            "has_table": has_table,
            "total_chars": total_chars,
            "avg_confidence": round(avg_confidence, 4),
        }
