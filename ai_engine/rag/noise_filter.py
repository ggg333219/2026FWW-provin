"""KB 灌库前的文档噪声过滤 (noise_filter.py)

背景
----
`DocumentChunker` 是纯切分原语，不做任何内容判断：每个 window 无条件变成一个
Chunk。但真实语料里混着大量「结构上合法、检索上无用」的文本：

  - 试卷页眉表单：`1 排序算法小题汇编  班级________ 姓名________ 学号________`
  - 答题横线、分隔线、装订线/密封线
  - 独立页码：`- 12 -`、`第 12 页 共 20 页`
  - 独立序号：`一、`、`3.`、`（2）`

这些东西会带来两个问题：
  1. 自己变成垃圾切片，占用检索结果位（用户报告的就是这一类）
  2. 挂在正常切片开头，污染嵌入向量与引用展示

过滤策略
--------
**先行剥离 + 兜底丢弃**，顺序很重要：

  1. `strip_noise_lines()` 在**切分之前**逐行剥离噪声 —— 噪声不再占用 512 token
     的窗口预算，正常段落能更紧凑地合并，切片数反而更少更干净。
     这解决上面第 2 个问题（页眉挂在好切片开头）。
  2. `drop_noise_chunks()` 在切分之后兜底 —— 整个窗口剥完只剩零星字符时丢弃。
     这解决第 1 个问题。

刻意保留的内容
--------------
  - `---` 独占一行：那是 SLIDE 策略的幻灯片分隔符（chunker.py:129），
    剥掉会让 pptx 的所有幻灯片粘成一块。`is_noise_line` 显式放行。
  - `# ` 开头的 Markdown 标题：SECTION 策略靠它切章节（chunker.py:112）。

接入点
------
只在 KB 文件的解析路径上启用（rag/router.py 的 `_process_file`）。手写 texts
（/knowledge/upload 的 req.texts）不过滤 —— 那是调用方自己写的内容，短文本
可能是刻意的，不该被最小长度规则误杀。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai_engine.core.schema import Chunk

# ---- 可调参数 ----

MIN_MEANINGFUL_CHARS = 12
"""切片剥离噪声后，有效字符（中日韩文字 + 字母 + 数字）少于此值则丢弃。

对 PDF/DOCX 这类走 PARAGRAPH/SECTION 策略、窗口会合并到 512 token 的语料，
一个窗口只剩十几个有效字，说明整窗都是噪声。默认值刻意保守 —— 主要收益来自
`strip_noise_lines`，这里只是兜底。想更激进可调高，想完全关闭传 0。
"""

_FILL_RATIO_THRESHOLD = 0.30
"""一行里填充符（下划线/横线/点）占比超过此值即判为噪声行。

用于抓「标题 + 一串下划线」这种混合行，例如
`1 排序算法小题汇编 班级__________ 姓名___________ 学号__________`（占比约 0.67）。
"""

# ---- 内部正则 ----

_FILL_CHARS = "_＿-—－=＝.．·"
_FILL_CHAR_SET = frozenset(_FILL_CHARS)

# 允许的填充符中排除 `-`，避免把 Markdown/幻灯片分隔符 `---` 当噪声（见模块 docstring）
_SLIDE_SEPARATOR_RE = re.compile(r"^-{3,}$")

_FORM_FIELD_RE = re.compile(
    r"(?:班级|姓名|学号|座号|考号|准考证号|学校|年级|得分|评分|评价)"
    r"[:：]?\s*[_＿\-—－.．·]{2,}"
)
"""表单字段 + 填充线：`班级____`、`姓名：____`。"""

_FORM_FIELD_EMPTY_RE = re.compile(
    r"^[\s]*(?:班级|姓名|学号|座号|考号|准考证号|学校|年级|得分|评分|评价)"
    r"[\s]*[:：][\s]*$"
)
"""冒号后留空的表单字段：`姓名：`。"""

_PURE_FILL_RE = re.compile(rf"^[{re.escape(_FILL_CHARS)}\s]+$")
"""整行都是填充符（含空白），如 `________`、`- - - -`。"""

_ASCII_PAGE_NUM_RE = re.compile(r"^\s*[-—－–]?\s*\d{1,4}\s*[-—－–]?\s*$")
"""独立阿拉伯数字页码：`12`、`- 12 -`。"""

_PAREN_PAGE_NUM_RE = re.compile(r"^\s*[（(]\s*\d{1,4}\s*[)）]\s*$")
"""括号页码：`（12）`。"""

_CN_PAGE_NUM_RE = re.compile(
    r"^\s*第\s*\d{1,4}\s*页(?:\s*[,，/]?\s*共\s*\d{1,4}\s*页)?\s*$"
)
"""中文页码：`第 12 页`、`第 12 页 共 20 页`。"""

_CN_PAGE_PREFIX_RE = re.compile(
    r"^\s*第\s*[一二三四五六七八九十百\d]{1,4}\s*页\s*$"
)
"""中文数字页码：`第 十二 页`。"""

_BARE_ORDINAL_RE = re.compile(
    r"^\s*[（(]?\s*(?:[一二三四五六七八九十]{1,3}|\d{1,3})\s*[)）]?\s*[、.．,，]?\s*$"
)
"""独立序号：`一、`、`3.`、`（2）`。"""

_BINDING_LINE_RE = re.compile(r"密封线|装订线")
"""试卷装订线/密封线提示。"""

_EXAM_VOLUME_RE = re.compile(r"^\s*第\s*[ⅠⅡⅢⅣⅤIVX]+\s*卷\s*$")
"""试卷卷标：`第Ⅰ卷`、`第 II 卷`。"""

_MEANINGFUL_CHAR_RE = re.compile(r"[一-鿿A-Za-z0-9]")
"""有效字符：中日韩统一表意文字 + 拉丁字母 + 数字。"""


@dataclass
class NoiseStats:
    """过滤统计，用于日志与灌库报告。"""

    lines_total: int = 0
    lines_removed: int = 0
    chunks_dropped: int = 0

    def merge(self, other: "NoiseStats") -> "NoiseStats":
        self.lines_total += other.lines_total
        self.lines_removed += other.lines_removed
        self.chunks_dropped += other.chunks_dropped
        return self

    def __str__(self) -> str:
        return (
            f"剥离噪声行 {self.lines_removed}/{self.lines_total}，"
            f"丢弃纯噪声切片 {self.chunks_dropped}"
        )


# ---- 判定 ----

def _fill_ratio(line: str) -> float:
    """填充符在整行中的占比。"""
    stripped = line.strip()
    if not stripped:
        return 0.0
    fills = sum(1 for ch in stripped if ch in _FILL_CHAR_SET)
    return fills / len(stripped)


def is_noise_line(line: str) -> bool:
    """判断单行是否为噪声行。"""
    if not line.strip():
        return False

    stripped = line.strip()

    # 显式放行：幻灯片分隔符（SLIDE 策略靠它切分）与 Markdown 标题（SECTION 策略靠它切分）
    if _SLIDE_SEPARATOR_RE.match(stripped):
        return False
    if stripped.startswith("#"):
        return False

    for pattern in (
        _FORM_FIELD_RE,
        _FORM_FIELD_EMPTY_RE,
        _PURE_FILL_RE,
        _BINDING_LINE_RE,
        _EXAM_VOLUME_RE,
        _ASCII_PAGE_NUM_RE,
        _PAREN_PAGE_NUM_RE,
        _CN_PAGE_NUM_RE,
        _CN_PAGE_PREFIX_RE,
        _BARE_ORDINAL_RE,
    ):
        if pattern.search(stripped):
            return True

    # 混合行：标题 + 大段下划线填充
    return _fill_ratio(stripped) >= _FILL_RATIO_THRESHOLD


def meaningful_char_count(text: str) -> int:
    """有效字符数（中日韩文字 + 字母 + 数字），忽略空白、标点、填充符。"""
    if not text:
        return 0
    return len(_MEANINGFUL_CHAR_RE.findall(text))


# ---- 过滤 ----

def strip_noise_lines(text: str) -> tuple[str, NoiseStats]:
    """逐行剥离噪声行，返回 (清洗后文本, 统计)。

    保留段落结构：噪声行被移除，但空行原样保留，`_split_paragraphs` 的
    段落边界（双换行）不受影响。
    """
    stats = NoiseStats()
    if not text:
        return text, stats

    kept: list[str] = []
    for line in text.splitlines():
        stats.lines_total += 1
        if is_noise_line(line):
            stats.lines_removed += 1
            continue
        kept.append(line)

    cleaned = "\n".join(kept)
    # 折叠 3 个以上连续空行，避免剥离后留下大片空白
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, stats


def drop_noise_chunks(
    chunks: list[Chunk],
    min_meaningful_chars: int = MIN_MEANINGFUL_CHARS,
) -> tuple[list[Chunk], int]:
    """兜底丢弃剥离后仍近乎空白的切片，返回 (保留的切片, 丢弃数)。

    `min_meaningful_chars <= 0` 时关闭本步，只做行剥离。
    """
    if min_meaningful_chars <= 0:
        return chunks, 0

    kept = [c for c in chunks if meaningful_char_count(c.content) >= min_meaningful_chars]
    return kept, len(chunks) - len(kept)
