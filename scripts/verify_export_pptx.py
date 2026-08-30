# -*- coding: utf-8 -*-
"""PPTX 导出质量离线验证脚本 (verify_export_pptx.py)

构造 2-3 个样例节点（含 slide 内容页与 quiz 互动页，quiz 覆盖 dict 题目
与纯文本题目两种形态），调用 PPTExporter 生成 PPTX 到
docs/导出验证/sample_export.pptx，再用 python-pptx 重新打开断言：
  A1  文件可正常打开且页数正确（封面 + 章节 + 内容 + 摘要 + quiz 2 页）
  A2  每页均有非空文本（无空文本页）
  A3  quiz dict 题目的选项（A．B．C．D．）与参考答案已渲染
  A4  中文字体带 a:ea（微软雅黑）东亚字形设置（WPS 兼容红线）
  A5  仅使用基础特性：无外部图片、无 SmartArt（graphicFrame）等

运行：python scripts/verify_export_pptx.py   （退出码 0 = PASS）
"""

import io
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pptx import Presentation
from pptx.oxml.ns import qn

from ai_engine.gen.export_ppt import EA_FONT_NAME, PPTExporter

OUTPUT = Path(PROJECT_ROOT) / "docs" / "导出验证" / "sample_export.pptx"

SAMPLE_NODES = [
    {
        "node_type": "section",
        "title": "第一章 排序算法概述",
        "summary": "理解常见排序算法的思想与复杂度差异。",
    },
    {
        "node_type": "content",
        "title": "冒泡排序与快速排序",
        "content": "冒泡排序通过相邻元素两两比较将最大值逐步移动到末尾，实现简单但平均复杂度为 O(n²)。"
                   "快速排序采用分治思想，选取基准元素将序列划分为两部分，平均复杂度 O(n log n)。",
        "key_points": ["冒泡排序：稳定，O(n²)", "快速排序：不稳定，平均 O(n log n)"],
        "segments": [
            {"segment_type": "explanation", "text": "先演示冒泡排序的一轮比较过程。",
             "estimated_seconds": 120},
            {"segment_type": "interaction", "text": "请学生手动模拟对 [5, 3, 8, 1] 的一轮冒泡。",
             "estimated_seconds": 180},
        ],
    },
    {
        "node_type": "quiz",
        "title": "课堂练习：排序算法",
        "questions": [
            {"question": "快速排序的平均时间复杂度是？",
             "options": ["O(n)", "O(n log n)", "O(n²)", "O(log n)"],
             "answer": "B", "explanation": "快排平均 O(n log n)，最坏 O(n²)。"},
            {"question": "下列哪种排序算法是稳定的？",
             "options": ["快速排序", "堆排序", "冒泡排序", "选择排序"],
             "answer": "C"},
            "开放题：结合本节内容说明什么场景下应选择插入排序。",
        ],
    },
    {
        "node_type": "summary",
        "title": "本节小结",
        "key_points": ["冒泡排序简单但慢", "快排分治高效", "稳定性影响工程选型"],
    },
]

EXPECTED_PAGES = 5  # section + content + quiz(3题中2题带选项各占1页) + summary
# 说明：带选项题目每页 2 题 → quiz 需要 2 页（2 题选项页 + 1 题开放题页）

RESULTS = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


def slide_text(slide) -> str:
    parts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            parts.append(shape.text_frame.text)
    return "\n".join(parts)


def main():
    # 生成 PPTX
    exporter = PPTExporter()
    buf = exporter.export_to_bytes(SAMPLE_NODES, "排序算法教学课件")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(buf.getvalue())
    print(f"已生成: {OUTPUT} ({OUTPUT.stat().st_size} bytes)\n")

    # 重新打开验证
    prs = Presentation(str(OUTPUT))
    slides = list(prs.slides)

    # A1 页数
    check("A1 页数正确", len(slides) == EXPECTED_PAGES,
          f"expect {EXPECTED_PAGES}, got {len(slides)}")

    # A2 无空文本页
    empty = [i + 1 for i, s in enumerate(slides) if not slide_text(s).strip()]
    check("A2 无空文本页", not empty, f"空页: {empty}" if empty else "每页均有文本")

    # A3 quiz 选项与参考答案
    all_text = "\n".join(slide_text(s) for s in slides)
    check("A3 选项已渲染", "B．O(n log n)" in all_text or "B．" in all_text)
    check("A3 参考答案已渲染", "参考答案：B" in all_text)
    check("A3 开放题已渲染", "开放题" in all_text)
    check("A3 页码编号连续", "1" in all_text and "2" in all_text and "3" in all_text)

    # A4 东亚字体 a:ea（WPS 兼容红线）
    ea_count = 0
    latin_count = 0
    for s in slides:
        for shape in s.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for rPr in para._p.iter():
                    if rPr.tag == qn("a:ea") and rPr.get("typeface") == EA_FONT_NAME:
                        ea_count += 1
                    if rPr.tag == qn("a:latin"):
                        latin_count += 1
    check("A4 a:ea 东亚字体已写入", ea_count > 0, f"ea={ea_count}, latin={latin_count}")

    # A5 仅基础特性：无外部图片 / 无 SmartArt / 无图表
    bad_parts = []
    for s in slides:
        for shape in s.shapes:
            if shape.shape_type is not None and "PICTURE" in str(shape.shape_type):
                bad_parts.append(f"slide{s}: picture")
            if shape.has_chart if hasattr(shape, "has_chart") else False:
                bad_parts.append(f"slide{s}: chart")
    graphic_frames = sum(
        1 for s in slides for shape in s.shapes
        if shape._element.tag == qn("p:graphicFrame"))
    check("A5 无图片/图表/SmartArt", not bad_parts and graphic_frames == 0,
          f"{bad_parts}, graphicFrame={graphic_frames}")

    failed = [r for r in RESULTS if r[1] == "FAIL"]
    print()
    print(f"===== verify_export_pptx: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS =====")
    if failed:
        for name, _, detail in failed:
            print(f"  FAIL: {name} {detail}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
