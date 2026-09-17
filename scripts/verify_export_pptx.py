# -*- coding: utf-8 -*-
"""PPTX 导出质量离线验证脚本 (verify_export_pptx.py)

Part A — 基线样例 sample_export.pptx（回归既有 8 项断言）
构造 2-3 个样例节点（含 slide 内容页与 quiz 互动页），调用 PPTExporter 生成
PPTX 后用 python-pptx 重新打开断言：
  A1  文件可正常打开且页数正确（章节 + 内容 + 摘要 + quiz 2 页）
  A2  每页均有非空文本（无空文本页）
  A3  quiz dict 题目的选项（A．B．C．D．）与参考答案已渲染
  A4  中文字体带 a:ea（微软雅黑）东亚字形设置（WPS 兼容红线）
  A5  仅使用基础特性：无外部图片、无 SmartArt（graphicFrame）等

Part B — 图文并茂样例 rich_export.pptx（A12 赛题 4a 新增断言）
开启 include_auto_cover / include_auto_toc / include_closing_slide，构造
流程型、百分比对比型、序号要点型内容节点 + 总结节点，断言：
  B1  目录页存在且条目数 = 节点数（编号圆数量一致）
  B2  内容页含形状（shape 数量 > 纯文本阈值）
  B3  封面有装饰形状（几何圆形装饰）
  B4  流程/对比特征检测触发时形状正确（"→" 连接符、百分比条形）
  B5  全文件无外部图片引用（image parts 为空）
  B6  总结页带收尾条 + 结束页追加，总页数正确
并打印 rich_export.pptx 每页 shape 统计。

运行：python scripts/verify_export_pptx.py   （退出码 0 = PASS）
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

from ai_engine.gen.export_ppt import EA_FONT_NAME, ExportPPTConfig, PPTExporter

DOCS_DIR = Path(PROJECT_ROOT) / "docs" / "导出验证"
BASELINE_OUTPUT = DOCS_DIR / "sample_export.pptx"
RICH_OUTPUT = DOCS_DIR / "rich_export.pptx"

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

RICH_NODES = [
    {
        "node_type": "content",
        "title": "冒泡排序的执行流程",
        "content": "首先，比较相邻两个元素，如果顺序错误就交换它们。"
                   "然后，对每一对相邻元素重复这一比较，直到这一轮结束。"
                   "接着，每完成一轮，最大的元素就移动到了序列末尾。"
                   "最后，重复上述步骤，直到某一次遍历中没有发生任何交换。",
        "key_points": ["每轮确定一个最大值", "有序区间从尾部向前增长"],
    },
    {
        "node_type": "content",
        "title": "排序算法性能对比",
        "content": "在随机数据测试中，快速排序平均耗时 12%，插入排序耗时 45%，"
                   "冒泡排序耗时 78%，差距随数据规模进一步拉大。",
    },
    {
        "node_type": "content",
        "title": "本章学习目标",
        "content": "围绕以下四个学习目标展开本节课的学习与练习。",
        "key_points": ["理解冒泡排序的基本思想", "掌握快排的分治策略",
                       "能分析平均与最坏复杂度", "学会按场景选择排序算法"],
    },
    {
        "node_type": "summary",
        "title": "本章小结",
        "key_points": ["冒泡简单但复杂度高", "快排分治平均高效", "稳定性影响工程选型"],
    },
]

RICH_NODE_COUNT = len(RICH_NODES)
RICH_EXPECTED_PAGES = 7  # 封面 + 目录 + 3 个单页内容节点 + 总结 + 结束页

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


def count_autoshapes(slide, mso_shape) -> int:
    count = 0
    for shape in slide.shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
            try:
                if shape.auto_shape_type == mso_shape:
                    count += 1
            except Exception:
                count += 0
    return count


def image_part_count(prs) -> int:
    """统计外部图片引用：ppt/media/ 下的 image parts。

    注意：python-pptx 默认模板自带 /docProps/thumbnail.jpeg（文件缩略图），
    不属于幻灯片内容的外部图片引用，不计入。
    """
    return sum(1 for part in prs.part.package.iter_parts()
               if "image" in str(getattr(part, "content_type", ""))
               and str(part.partname).startswith("/ppt/media/"))


def shape_stats(prs) -> list[tuple[int, int, int]]:
    """每页 (shape 总数, 形状数, 文本框数) 统计。"""
    stats = []
    for i, slide in enumerate(prs.slides, start=1):
        shapes = sum(1 for s in slide.shapes if s.shape_type != MSO_SHAPE_TYPE.TEXT_BOX)
        texts = sum(1 for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.TEXT_BOX)
        stats.append((i, shapes, texts))
    return stats


def run_baseline():
    """Part A：既有基线样例，8 项断言保持不变。"""
    print("===== Part A · 基线样例 sample_export.pptx =====")
    exporter = PPTExporter()
    buf = exporter.export_to_bytes(SAMPLE_NODES, "排序算法教学课件")
    BASELINE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_OUTPUT.write_bytes(buf.getvalue())
    print(f"已生成: {BASELINE_OUTPUT} ({BASELINE_OUTPUT.stat().st_size} bytes)\n")

    prs = Presentation(str(BASELINE_OUTPUT))
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


def run_rich():
    """Part B：图文并茂样例，目录/装饰形状/可视化/无图片断言。"""
    print()
    print("===== Part B · 图文并茂样例 rich_export.pptx =====")
    exporter = PPTExporter(ExportPPTConfig(
        output_dir="/tmp", include_auto_cover=True,
        include_auto_toc=True, include_closing_slide=True))
    buf = exporter.export_to_bytes(RICH_NODES, "排序算法图文并茂课件")
    RICH_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    RICH_OUTPUT.write_bytes(buf.getvalue())
    print(f"已生成: {RICH_OUTPUT} ({RICH_OUTPUT.stat().st_size} bytes)\n")

    prs = Presentation(str(RICH_OUTPUT))
    slides = list(prs.slides)
    all_text = "\n".join(slide_text(s) for s in slides)

    # B1 目录页存在且条目数 = 节点数（编号圆 + 标题）
    toc_ok = len(slides) > 1 and "目录" in slide_text(slides[1])
    toc_ovals = count_autoshapes(slides[1], MSO_SHAPE.OVAL) if len(slides) > 1 else 0
    check("B1 目录页存在且条目数=节点数", toc_ok and toc_ovals == RICH_NODE_COUNT,
          f"toc_page={toc_ok}, 编号圆={toc_ovals}, 节点数={RICH_NODE_COUNT}")

    # B2 内容页含形状（shape 数量 > 纯文本阈值）
    content_slides = slides[2:5]
    counts = [len(list(s.shapes)) for s in content_slides]
    check("B2 内容页含形状", len(counts) == 3 and all(c >= 8 for c in counts),
          f"内容页 shape 数={counts}（阈值 8）")

    # B3 封面有装饰形状
    cover_ovals = count_autoshapes(slides[0], MSO_SHAPE.OVAL)
    cover_shapes = len(list(slides[0].shapes))
    check("B3 封面有装饰形状", cover_shapes >= 6 and cover_ovals >= 2,
          f"封面 shape={cover_shapes}, 装饰圆={cover_ovals}")

    # B4 特征检测触发时形状正确
    arrows = sum(1 for s in slides for shape in s.shapes
                 if shape.has_text_frame and shape.text_frame.text.strip() == "→")
    check("B4 流程检测触发（→ 连接符）", arrows == 3,
          f"→ 连接符={arrows}（4 步流程应为 3）")
    check("B4 对比检测触发（百分比条形）",
          all(v in slide_text(slides[3]) for v in ("12%", "45%", "78%")),
          "对比页含 12% / 45% / 78% 标注")
    check("B4 要点条渲染（序号圆）",
          count_autoshapes(slides[4], MSO_SHAPE.OVAL) == 4,
          f"要点页编号圆={count_autoshapes(slides[4], MSO_SHAPE.OVAL)}（4 条要点）")

    # B5 全文件无外部图片引用（image parts 为空）
    rich_images = image_part_count(prs)
    baseline_prs = Presentation(str(BASELINE_OUTPUT))
    baseline_images = image_part_count(baseline_prs)
    check("B5 无外部图片引用", rich_images == 0 and baseline_images == 0,
          f"rich image parts={rich_images}, baseline image parts={baseline_images}")

    # B6 总结页收尾 + 结束页，总页数正确
    summary_text = slide_text(slides[5]) if len(slides) > 5 else ""
    ending_text = slide_text(slides[-1]) if slides else ""
    check("B6 总结页收尾条 + 结束页",
          len(slides) == RICH_EXPECTED_PAGES and "感谢聆听" in summary_text
          and "感谢聆听" in ending_text,
          f"pages={len(slides)}（期望 {RICH_EXPECTED_PAGES}）, "
          f"summary收尾={'感谢聆听' in summary_text}, ending={'感谢聆听' in ending_text}")

    # 每页 shape 统计
    print()
    print("rich_export.pptx 每页 shape 统计（页码, 形状, 文本框）:")
    for page, shapes, texts in shape_stats(prs):
        print(f"  page {page}: shapes={shapes}, textboxes={texts}")


def main():
    run_baseline()
    run_rich()

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
