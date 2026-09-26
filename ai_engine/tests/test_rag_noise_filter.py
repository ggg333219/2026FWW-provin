"""KB 灌库噪声过滤测试 (test_rag_noise_filter.py)

覆盖 ai_engine/rag/noise_filter.py 与它在 rag/router.py 的接入点。
重点不只是「噪声被识别」，还有「正常内容不被误杀」—— 后者更容易出事故。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_engine.core.schema import Chunk, SourceType
from ai_engine.rag.chunker import DocumentChunker
from ai_engine.rag.noise_filter import (
    drop_noise_chunks,
    is_noise_line,
    meaningful_char_count,
    strip_noise_lines,
)


# =============================================================================
# 1. 噪声行识别
# =============================================================================

@pytest.mark.parametrize(
    "line",
    [
        # 用户实际报告的那一条
        "1 排序算法小题汇编  班级__________ 姓名___________ 学号__________",
        # 表单字段的其它写法
        "班级：________  姓名：________",
        "姓名：",
        "座号____",
        # 纯填充线
        "____________",
        "_ _ _ _ _ _",
        "................",
        # 独立页码
        "12",
        "- 12 -",
        "（12）",
        "第 12 页",
        "第 12 页 共 20 页",
        # 独立序号
        "一、",
        "3.",
        "（2）",
        # 试卷装订线
        "密封线内不要答题",
        "装订线",
        # 卷标
        "第Ⅰ卷",
    ],
)
def test_noise_lines_are_detected(line: str) -> None:
    assert is_noise_line(line), f"未识别为噪声行: {line!r}"


@pytest.mark.parametrize(
    "line",
    [
        # 幻灯片分隔符 —— SLIDE 策略靠它切分，剥掉会让 pptx 全部粘成一块
        "---",
        "-----",
        # Markdown 标题 —— SECTION 策略靠它切章节
        "# 第一章 算法概述",
        "## 3.2 冒泡排序",
        # 正常正文
        "冒泡排序的核心思想是相邻元素两两比较，逆序则交换。",
        "算法的时间复杂度为 O(n^2)，空间复杂度为 O(1)。",
        "在数据已基本有序的情况下，插入排序的效率接近 O(n)。",
        # 代码 / 数据行
        "=D3+E3+F3+H3",
        "=SUM(D3:F3,H3)",
        "def bubble_sort(arr):",
        # 带序号但内容完整的行（不是独立序号）
        "1. 冒泡排序：相邻元素比较，逆序交换，每轮确定一个最大值。",
        "3.3 简单算法及其程序实现",
        # 含「得分」「学校」等词但不是表单
        "得分点是算法的正确性与效率。",
        "高一年级的学生已经掌握了 Python 基础语法。",
    ],
)
def test_real_content_is_not_noise(line: str) -> None:
    assert not is_noise_line(line), f"正常内容被误判为噪声: {line!r}"


# =============================================================================
# 2. 行剥离
# =============================================================================

def test_strip_removes_header_keeps_content_and_paragraphs() -> None:
    """试卷页眉被剥离，正文与段落结构保留。"""
    text = (
        "1 排序算法小题汇编  班级__________ 姓名___________ 学号__________\n"
        "\n"
        "1. 冒泡排序的核心思想是相邻元素两两比较，逆序则交换。\n"
        "\n"
        "- 12 -\n"
        "\n"
        "2. 快速排序通过一趟划分将序列分为两部分，再分别递归处理。\n"
    )
    cleaned, stats = strip_noise_lines(text)

    assert "班级" not in cleaned
    assert "学号" not in cleaned
    assert "- 12 -" not in cleaned
    assert "冒泡排序的核心思想" in cleaned
    assert "快速排序通过一趟划分" in cleaned
    # 段间仍保留双换行，_split_paragraphs 才能正确分段
    assert "\n\n" in cleaned
    assert stats.lines_removed == 2   # 页眉 + 页码
    assert stats.lines_total == 7


def test_strip_preserves_slide_separator() -> None:
    """`---` 必须活下来，否则 pptx 幻灯片会粘成一块。"""
    text = "3.1 算法概述\n---\n3.2 冒泡排序\n---\n3.3 快速排序\n"
    cleaned, _ = strip_noise_lines(text)
    assert cleaned.count("---") == 2


def test_strip_empty_text() -> None:
    cleaned, stats = strip_noise_lines("")
    assert cleaned == ""
    assert stats.lines_total == 0


def test_strip_all_noise_yields_blank() -> None:
    cleaned, stats = strip_noise_lines("班级____ 姓名____\n\n____________\n")
    assert not cleaned.strip()
    assert stats.lines_removed == 2


# =============================================================================
# 3. 切片兜底丢弃
# =============================================================================

def test_meaningful_char_count() -> None:
    # 只数中日韩文字 + 字母 + 数字
    assert meaningful_char_count("排序算法") == 4
    assert meaningful_char_count("O(n^2)") == 3  # O, n, 2
    assert meaningful_char_count("___ ，。！ -—") == 0
    assert meaningful_char_count("") == 0


def _chunk(content: str, idx: int = 0) -> Chunk:
    return Chunk(
        chunk_id=f"t::s{idx:04d}",
        source_type=SourceType.PDF,
        source_ref="t.pdf",
        content=content,
        seq_index=idx,
    )


def test_drop_noise_chunks_keeps_real_content() -> None:
    chunks = [
        _chunk("排序", 0),                                   # 剥完只剩 2 字 → 丢
        _chunk("冒泡排序的核心思想是相邻元素两两比较，逆序则交换。", 1),
        _chunk("____ —— ……", 2),                            # 无有效字符 → 丢
    ]
    kept, dropped = drop_noise_chunks(chunks)
    assert dropped == 2
    assert len(kept) == 1
    assert "冒泡排序" in kept[0].content


def test_drop_noise_chunks_can_be_disabled() -> None:
    chunks = [_chunk("排序", 0)]
    kept, dropped = drop_noise_chunks(chunks, min_meaningful_chars=0)
    assert dropped == 0
    assert len(kept) == 1


# =============================================================================
# 4. 端到端：真实试卷页 → 切片
# =============================================================================

_EXAM_PAGE = """1 排序算法小题汇编  班级__________ 姓名___________ 学号__________

一、选择题

1. 对序列 (5, 3, 8, 1) 进行冒泡排序，第一趟结束后的结果是（  ）
A. (3, 5, 1, 8)    B. (3, 1, 5, 8)    C. (1, 3, 5, 8)    D. (5, 3, 1, 8)

解析：冒泡排序每趟将最大的元素移到末尾，第一趟比较相邻元素并交换逆序对，
因此最大值 8 会移动到序列末尾，结果为 (3, 5, 1, 8)。

- 12 -

2. 快速排序在平均情况下的时间复杂度是（  ）
A. O(n)    B. O(n log n)    C. O(n^2)    D. O(log n)

解析：快速排序每趟划分将序列分为两部分，平均需要 log n 层递归，每层比较 n 次，
因此平均时间复杂度为 O(n log n)；最坏情况（每次划分极不平衡）退化为 O(n^2)。
"""


def test_end_to_end_exam_page_produces_clean_chunks() -> None:
    """端到端：试卷页切出来的切片里不该再有页眉表单与独立页码。"""
    chunker = DocumentChunker()  # PDF → PARAGRAPH
    cleaned, strip_stats = strip_noise_lines(_EXAM_PAGE)
    chunks = chunker.chunk_text(cleaned, source_ref="试卷.pdf", source_type=SourceType.PDF)
    chunks, dropped = drop_noise_chunks(chunks)

    assert strip_stats.lines_removed >= 2   # 页眉 + 页码
    assert chunks, "有效内容不应被全部过滤掉"

    joined = "\n".join(c.content for c in chunks)
    assert "班级" not in joined
    assert "姓名" not in joined
    assert "学号" not in joined
    # 正文必须完整保留
    assert "冒泡排序" in joined
    assert "快速排序" in joined
    assert "O(n log n)" in joined


def test_end_to_end_pure_noise_page_yields_nothing() -> None:
    """整页都是噪声（如只有页眉页脚的空白页）→ 0 切片，而不是一条垃圾切片。"""
    page = "班级__________ 姓名___________ 学号__________\n\n____________\n\n- 12 -\n"
    cleaned, _ = strip_noise_lines(page)
    assert not cleaned.strip()
