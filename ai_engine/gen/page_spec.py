"""S3 页面内容 IR —— 「这一页该画什么」的单一事实来源。

背景
----
课件内容页此前有**三个渲染器各画一套**：
  - gen/preview.py      → 要点 + 正文(content/summary) + 讲授文本(script) + 分段(segments)
  - gen/export_ppt.py   → 教学内容(content/summary/要点) + 讲授分段(恒空)
  - gen/svg_renderer.py → 核心要点 + 教学内容(content/summary)

现在三者都只消费本模块的 ``build_page_spec``（导出侧原先的 ``_main_items`` /
``_select_visualization`` 已改为读区块），差异只剩**摆版方式**。

局部修改（gen/partial_content.py）曾经只覆盖 `script` / `segments`，后两个渲染器恰好
都不读它们，于是「改了看不见」，且两端内容对不上。现在那条路径按本模块的角色划分
回写：**ROLE_PRIMARY 的字段（summary / point_details）必须写回**，`script` /
`segments` 只是跟着走；`figure` / `key_conclusion` 由教学表达规划器重新决策
（见 main.py 的 _run_content_pipeline）—— 它们本来就只由规划阶段落盘。

本模块把「页面由哪些区块构成、每个区块什么角色」抽成一份中间表示（IR），
让渲染器只负责**摆版**、不负责**决定内容**。与 gen/presentation.py 对样式层
做的事同构 —— 那里统一了「长什么样」，这里统一「画什么」。

关于 `content` 字段
------------------
真实生成链路里 `content` 从不被赋值（schema.py 的 normalize_stage2_nodes 与
normalize_stage3_scripts 都不产出它），有值的是 `summary`（stage2）与
`script` / `segments`（stage3）。但仍把它保留为正文来源之一：历史课件与手工
编辑会写它，且 test_preview_export_consistency 断言它必须出现在预览里。

学生看的 vs 教师看的
-------------------
幻灯片是给学生看的，讲稿是给教师照着讲的，两者落点不同（`Block.role`）：

  primary / secondary  上幻灯片（图示、正文、要点展开、核心要点）
  teacher              不上幻灯片，由预览渲染进页下方的折叠区（讲稿、分段）

区分放在这里而不是让两个渲染器各挑各的，正是为了避免「同一个页面三处内容对不上」。
"""

from __future__ import annotations

import html
import re
import xml.sax.saxutils as saxutils
from dataclasses import dataclass, field
from typing import Any

# 要点展开的归一逻辑由 schema.py 持有（它不依赖任何 ai_engine 子模块，是唯一不会
# 引起循环导入的共享位置），这里只做「从节点上取字段」这一层。
from ..schema import normalize_point_details as _normalize_point_details_raw
from .deck_structure import is_auto_node


def xml_escape(text: Any) -> str:
    """XML 转义。除 `&<>` 外还转义引号 —— 这些值也会出现在属性里
    （aria-label / font-family），`saxutils.escape` 默认不管引号。

    HTML 片段与 SVG 属性共用这一个入口，避免两处各写一份慢慢漂移。
    """
    return saxutils.escape(str(text or ""), {'"': "&quot;", "'": "&apos;"})


# ---- 常量（原 preview.py，现为两端共用）----

#: 页面类型别名：老版 type 模板值与标准化 node_type 枚举的并集，
#: 命中后统一收敛为 6 套布局。
TYPE_ALIASES = {
    # 封面
    "cover": "cover",
    "title": "cover",
    # 目录 / 章节
    "section": "section",
    "divider": "section",
    "toc": "section",
    "chapter": "section",
    # 问答 / 互动（布局不同，分开渲染）
    "quiz": "quiz",
    "qa": "quiz",
    "question": "quiz",
    "interactive": "interactive",
    "activity": "interactive",
    # 总结
    "summary": "summary",
    "recap": "summary",
    # 通用
    "content": "content",
    "slide": "content",
}

#: 讲授分段类型 → 中文语义标签
SEGMENT_TYPE_LABELS = {
    "opening": "导入",
    "explanation": "讲解",
    "example": "示例",
    "interaction": "互动",
    "transition": "过渡",
    "summary": "小结",
}

#: 讲授分段难度 → 可视化图标
SEGMENT_DIFF_ICONS = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}

#: 分段兜底标签：未知类型 / 缺失类型，保证任何分段都有中文语义标签
SEG_LABEL_UNKNOWN = "其他"
SEG_LABEL_MISSING = "段落"

#: 正文兜底时要截取的最大句数 / 要点最多展示条数
MAX_FALLBACK_POINTS = 8
MAX_DISPLAY_POINTS = 10

#: 区块角色：
#:   primary   占主位（大字号、宽栏）—— 学生看的正文
#:   secondary 降为小字注记 —— 学生看的辅助信息
#:   teacher   **不进幻灯片**，只给教师看（讲稿原文、讲授分段）
#:
#: teacher 也留在同一份内容模型里，而不是被踢出 _content_blocks：page_spec 是
#: 「这一页有哪些内容」的单一事实来源，讲稿只是换了个落点（预览的折叠区），
#: 不该因此变成另一条平行的取数逻辑。
ROLE_PRIMARY = "primary"
ROLE_SECONDARY = "secondary"
ROLE_TEACHER = "teacher"

#: 图示种类白名单（渲染见 gen/diagrams.py）。表达形式由 gen/teaching_plan.py 决定，
#: 这里是它输出必须落在的合法集合 —— 未登记的一律当作「没有图示」。
FIGURE_KINDS = ("flow", "compare", "cycle", "hierarchy", "chart", "matrix")

#: 单张图示最多画几条。超出的丢弃 —— 这些标签是模型自己生成的，同样的内容在
#: 要点展开区还有一份，丢弃不会让任何原文消失（故不涉及 token 截断）。
MAX_FIGURE_ITEMS = 5

#: matrix（对比表）的行列上限：列是维度（3~4 个读得清），行是被比较的对象。
MAX_MATRIX_COLUMNS = 5
MAX_MATRIX_ROWS = 6

#: 大字结论的长度上限。结论必须是**一句话** —— 超长的（模型偶发把整段正文塞进
#: key_conclusion）判为不可用，宁可不显示，也不要一个占满半页的"结论"。
MAX_CONCLUSION_CHARS = 60


# ---- 疏密排版三档（H5）----
#
# 密度参数表是预览（svg_renderer）与导出（export_ppt）共用的**唯一**取值来源：
# 行距 / 段距 / 边距 / 每页容量都定义在这里，两个渲染器只负责把同一份 token
# 换算成自己的单位（px@96dpi 或 pt），不再各写各的数字。
#
# comfortable 一档对齐改造前的既有行为（svg 的 _BLOCK_GAP=10 / _REGION_PADDING=16、
# 导出的 line_spacing=1.13 / 段距 7pt / 要点卡 pad 7px gap 10px / _BODY_FILL=0.97），
# 因此「没选密度」的课件导出结果不变。
DENSITY_TIERS = ("compact", "comfortable", "loose")

#: 历史取值映射：presentation 层旧数据里的 "minimal"（极简，大留白）即宽松档
DENSITY_ALIASES = {"minimal": "loose"}

FALLBACK_DENSITY = "comfortable"

#: token 语义与单位：
#:   block_gap_px       区块之间的垂直间距（预览 px@96dpi；导出按段距联动）
#:   region_padding_px  版面区域内容距面板边缘的内边距（预览 px；导出面板内边距联动）
#:   line_spacing       行距倍数（预览 line-height；导出 PPTX paragraph.line_spacing）
#:   paragraph_gap_pt   段距（导出 PPTX space_after，磅）
#:   point_card_pad_px  要点卡片内边距（两端 px 同源，导出换算英寸）
#:   point_card_gap_px  要点卡片间距（两端 px 同源，导出换算英寸）
#:   body_fill          每页容量系数（导出正文面板分页容量 × 该值：越小每页放得越少）
#:   panel_units_scale  左栏要点面板的每页容量倍率（导出 _chunk_weighted）
#:   body_font_scale    正文字号缩放（1.0 = 现状；紧凑略小、宽松略大）
#:   css_padding        预览 .slide 的内边距（CSS，原 presentation.DENSITY_PADDING）
DENSITY_PROFILES: dict[str, dict[str, Any]] = {
    "compact": {
        "block_gap_px": 6.0,
        "region_padding_px": 12.0,
        "line_spacing": 1.06,
        "paragraph_gap_pt": 4.0,
        "point_card_pad_px": 5.0,
        "point_card_gap_px": 6.0,
        "body_fill": 1.0,
        "panel_units_scale": 1.15,
        "body_font_scale": 0.94,
        "css_padding": "36px 44px 40px",
    },
    "comfortable": {
        "block_gap_px": 10.0,
        "region_padding_px": 16.0,
        "line_spacing": 1.13,
        "paragraph_gap_pt": 7.0,
        "point_card_pad_px": 7.0,
        "point_card_gap_px": 10.0,
        "body_fill": 0.97,
        "panel_units_scale": 1.0,
        "body_font_scale": 1.0,
        "css_padding": "44px 52px 48px",
    },
    "loose": {
        "block_gap_px": 16.0,
        "region_padding_px": 20.0,
        "line_spacing": 1.24,
        "paragraph_gap_pt": 11.0,
        "point_card_pad_px": 10.0,
        "point_card_gap_px": 15.0,
        "body_fill": 0.88,
        "panel_units_scale": 0.82,
        "body_font_scale": 1.06,
        "css_padding": "56px 64px 60px",
    },
}


def resolve_density(value: Any) -> str:
    """把 presentation 层传来的 density 归一到三档之一。

    脏值 / 缺失一律回 comfortable（改造前行为），历史 "minimal" 映射到 loose。
    """
    raw = str(value or "").strip().lower()
    raw = DENSITY_ALIASES.get(raw, raw)
    return raw if raw in DENSITY_TIERS else FALLBACK_DENSITY


def density_profile(value: Any) -> dict[str, Any]:
    """取密度参数表（结果总是三档之一的同一份 dict，不复制）。"""
    return DENSITY_PROFILES[resolve_density(value)]


def pptx_line_height_factor(value: Any) -> float:
    """导出侧排版行高系数：1.2（单倍行距的基线高）× 行距倍数。

    comfortable ≈ 1.356，与改造前写死的 1.35 一致 —— 分页估算与渲染共用的
    那把尺子从此跟随密度档位，而不是固定值。
    """
    return 1.2 * float(density_profile(value)["line_spacing"])


# ---- IR ----

@dataclass
class Block:
    """页面上的一块内容。渲染器只看 kind / role，不解析节点字段。"""

    #: segments | text | script | bullets | questions | figure | details | conclusion
    kind: str
    role: str = ROLE_PRIMARY
    heading: str = ""
    segments: list[dict] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    items: list[Any] = field(default_factory=list)
    cls: str = ""                  # 覆盖默认 class（cover-points / section-list）
    with_index: bool = False
    figure: dict = field(default_factory=dict)   # kind=figure：图示描述（见 diagrams.py）


@dataclass
class PageSpec:
    """一页的内容模型。"""

    node_id: str
    index: int
    kind: str                      # cover | section | quiz | interactive | summary | content
    title: str
    subtitle: str = ""
    blocks: list[Block] = field(default_factory=list)


# ---- 字段提取（原 preview.py 的方法，改为模块函数供两端复用）----

def resolve_kind(node: dict[str, Any]) -> str:
    """双字段识别页面类型：type 优先，node_type 兜底，缺省 content。

    兼容 Pydantic 枚举（NodeType.SECTION）与纯字符串两种形态。
    """
    raw = node.get("type")
    if raw is None or str(raw).strip() == "":
        raw = node.get("node_type")
    if raw is None or str(raw).strip() == "":
        return "content"
    if hasattr(raw, "value"):  # Pydantic 枚举
        raw = raw.value
    return TYPE_ALIASES.get(str(raw).strip().lower(), "content")


def as_list(value: Any) -> list[str]:
    """把 list / 换行字符串统一转成干净的字符串列表。"""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [line.strip() for line in value.split("\n") if line.strip()]
    return []


def as_raw_list(value: Any) -> list[Any]:
    """取原始列表（保留 dict 元素，供题目对象渲染）；字符串退化为单元素列表。"""
    if isinstance(value, list):
        return [v for v in value if v]
    if isinstance(value, str) and value.strip():
        return [line.strip() for line in value.split("\n") if line.strip()]
    return []


def split_content_into_points(content: str, limit: int = MAX_FALLBACK_POINTS) -> list[str]:
    """正文兜底：先按行拆，再按句拆，保证得到尽量短小的要点。"""
    if not content:
        return []
    lines = [ln.strip().lstrip("•-*#· ").strip() for ln in content.split("\n") if ln.strip()]
    if len(lines) >= 2:
        return [ln for ln in lines if ln][:limit]
    sentences = [s.strip() for s in re.split(r"[。；;！？!?]\s*", content) if s.strip()]
    return sentences[:limit]


def extract_key_points(node: dict[str, Any]) -> list[str]:
    """要点字段双向兼容读取。

    优先级：key_points → core_points → key_difficulties → expected_outcomes
    → 正文（content / script / summary）拆分兜底。
    """
    for key in ("key_points", "core_points", "key_difficulties", "expected_outcomes"):
        points = as_list(node.get(key))
        if points:
            return points
    content = str(node.get("content") or node.get("script") or node.get("summary") or "").strip()
    return split_content_into_points(content)


def resolve_export_key_points(node: Any) -> list[str]:
    """合并 key_points/core_points，去重但不丢弃任一来源（导出侧口径）。"""
    item = node if isinstance(node, dict) else {}
    values: list[str] = []
    for field in ("key_points", "core_points"):
        raw = item.get(field) or []
        if isinstance(raw, str):
            raw = raw.splitlines()
        if isinstance(raw, (list, tuple)):
            for value in raw:
                text = str(value or "").strip()
                if text and text not in values:
                    values.append(text)
    return values


def body_paragraphs(node: dict[str, Any]) -> list[str]:
    """内容页正文来源：content 优先。

    M4：大纲节点的 ``summary`` 是「内容概述」，只供讲稿与教师侧使用，不再直接
    打进 PPT 正文 —— 学生看到的正文只来自 ``content``（真实生成链路不给它赋值，
    但历史课件与手工编辑会写）。

    deck_structure 的合成节点（node_id 以 ``__auto_`` 开头，如目录页）其
    content/summary 是**有意的版面文案**，保留 summary 兜底，避免误杀。
    """
    keys = ["content"]
    if is_auto_node(node):
        keys.append("summary")
    paragraphs: list[str] = []
    for key in keys:
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            paragraphs.append(value.strip())
        elif isinstance(value, list):
            paragraphs.extend(str(v).strip() for v in value if str(v).strip())
        if paragraphs:
            # 合成目录页的 content 与 summary 常是同一句话，取到即止，不重复排
            break
    return paragraphs


def normalize_segments(node: dict[str, Any]) -> list[dict]:
    """把节点上的 segments 归一成渲染所需的最小结构。

    未知/缺失 segment_type 保留原值（渲染时用兜底标签），不在这里改写语义。
    """
    normalized: list[dict] = []
    raw_segments = node.get("segments")
    if not isinstance(raw_segments, (list, tuple)):
        # 字符串会被逐字符迭代出满屏垃圾分段，直接当作无分段
        return normalized
    for raw in raw_segments:
        seg = raw if isinstance(raw, dict) else {"text": raw}
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        seg_type = str(seg.get("segment_type") or "").strip().lower()
        try:
            seconds = int(seg.get("estimated_seconds") or 0)
        except (TypeError, ValueError):
            seconds = 0
        difficulty = str(seg.get("difficulty") or "").strip().lower()
        normalized.append({
            "text": text,
            "segment_type": seg_type,
            "label": SEGMENT_TYPE_LABELS.get(
                seg_type, SEG_LABEL_UNKNOWN if seg_type else SEG_LABEL_MISSING
            ),
            "seconds": seconds,
            "difficulty": difficulty,
            "difficulty_icon": SEGMENT_DIFF_ICONS.get(difficulty, ""),
            "hint": str(seg.get("interaction_hint") or "").strip(),
            "knowledge_card": seg.get("knowledge_card"),
        })
    return normalized


def normalize_point_details(node: dict[str, Any]) -> list[dict]:
    """把节点上的 point_details 归一成 [{"point", "detail"}]。

    这是内容页的正文来源 —— 由 S3（讲稿阶段）为每个要点写 1~2 句展开，所以局部
    修改（partial_content 的 revise_slide 契约）能连它一起重生成，改动才在幻灯片上
    看得见。

    任一字段为空的条目直接丢弃；`point` 缺失时用 `detail` 兜底，避免出现只有标题
    没有展开的空壳。
    """
    return _normalize_point_details_raw(node.get("point_details"))


def _figure_items(value: Any) -> list[str]:
    """图示标签归一；dict 元素取 text/label 字段。"""
    if not isinstance(value, (list, tuple)):
        return []
    items: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("label") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            items.append(text)
    return items[:MAX_FIGURE_ITEMS]


def _figure_side(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    return {
        "title": str(raw.get("title") or "").strip(),
        "items": _figure_items(raw.get("items")),
    }


def _figure_series(value: Any) -> list[dict[str, Any]]:
    """chart 的数据点归一：label 为空或 value 非数的条目直接丢弃。

    value 用 float 收敛 —— 模型偶发给出 "45%" 或 "1,200" 这类带装饰的字符串，
    去干净再转，转不动就丢这一条（丢一条比画一根高度为 0 的柱子好）。
    """
    if not isinstance(value, (list, tuple)):
        return []
    series: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or "").strip()
        raw_value = str(item.get("value") if item.get("value") is not None else "").strip()
        cleaned = re.sub(r"[^0-9.\-]", "", raw_value.replace(",", ""))
        try:
            number = float(cleaned)
        except ValueError:
            continue
        if label:
            series.append({"label": label, "value": number})
    return series


def split_matrix_cells(value: Any) -> list[str]:
    """matrix 的一行/一列 → 单元格列表。

    列表直接取；字符串按换行与常见分隔符（顿号、逗号、竖线、制表符）拆 ——
    模型把一行写成 "冒泡排序、稳定、O(n²)" 是常态，整串当成一格会让表格错列。

    公开给 gen/teaching_plan.py 用：切分口径必须两端一致，否则规划器按 3 格
    校验、page_spec 按 1 格渲染，表格会静默变形。
    """
    if isinstance(value, (list, tuple)):
        raw_items = list(value)
    elif isinstance(value, str) and value.strip():
        raw_items = re.split(r"[、,，|\t\n]+", value)
    else:
        return []
    cells: list[str] = []
    for item in raw_items:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("label") or item.get("value") or "").strip()
        else:
            text = str(item or "").strip()
        cells.append(text)
    return cells


def normalize_figure(node: dict[str, Any]) -> dict[str, Any] | None:
    """节点的 figure 字段 → None 或规范化的图示描述。

    模型可能把 figure 输出成字符串、给出未登记的 kind、items 里混进 dict —— 一律
    当作「没有图示」（版面自然少一块），绝不在这里抛异常拖垮整页渲染。
    """
    raw = node.get("figure")
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in FIGURE_KINDS:
        return None

    base = {
        "kind": kind,
        "title": str(raw.get("title") or "").strip(),
        "caption": str(raw.get("caption") or "").strip(),
    }

    if kind == "compare":
        left = _figure_side(raw.get("left"))
        right = _figure_side(raw.get("right"))
        if not left["items"] and not right["items"]:
            return None
        return {**base, "left": left, "right": right}

    if kind == "chart":
        series = _figure_series(raw.get("series"))
        # 只有一根柱子谈不上"关系"—— 这正是 teaching_plan 判定该出图的最低门槛
        if len(series) < 2:
            return None
        return {**base, "series": series[:MAX_FIGURE_ITEMS]}

    if kind == "matrix":
        columns = split_matrix_cells(raw.get("columns"))[:MAX_MATRIX_COLUMNS]
        if not columns:
            return None
        rows: list[list[str]] = []
        for row in as_raw_list(raw.get("rows")):
            cells = split_matrix_cells(row)
            if not any(cells):
                continue
            # 模型经常给不齐列数：按 columns 长度补齐/截断，缺格留空
            rows.append((cells + [""] * len(columns))[:len(columns)])
        if not rows:
            return None
        # 首列常是被比较对象的名称（行头），渲染时加粗
        return {**base, "columns": columns, "rows": rows[:MAX_MATRIX_ROWS]}

    items = _figure_items(raw.get("items"))
    if not items:
        return None
    return {**base, "items": items}


# ---- Block → HTML ----
#
# 以下 markup 逐字保留原先 preview.py 的产物：scripts/verify_preview_render.py 与
# 前端 generationStore.test.js 都是按精确 class 名断言的，改一个字符就会破契约。

def _key_points_html(items: list[str], cls: str = "key-points", with_index: bool = False) -> str:
    rendered = []
    for i, point in enumerate(items[:MAX_DISPLAY_POINTS], start=1):
        idx = f'<span class="kp-idx">{i}</span>' if with_index else ""
        rendered.append(
            f'<li class="kp-item">{idx}<span class="kp-highlight">{html.escape(str(point))}</span></li>'
        )
    return f'<ul class="{cls}">{"".join(rendered)}</ul>'


def _knowledge_card_html(kc: Any) -> str:
    """知识卡片渲染：term / definition / formula / tags。"""
    if not isinstance(kc, dict):
        return ""
    term = str(kc.get("term") or "").strip()
    definition = str(kc.get("definition") or "").strip()
    formula = str(kc.get("formula") or "").strip()
    tags = [html.escape(str(t).strip()) for t in (kc.get("tags") or []) if str(t).strip()]
    if not any([term, definition, formula, tags]):
        return ""
    parts = []
    if definition:
        parts.append(f'<p class="kc-def">{html.escape(definition)}</p>')
    if formula:
        parts.append(f'<pre class="kc-formula">{html.escape(formula)}</pre>')
    if tags:
        parts.append(f'<div class="kc-tags">{"".join(f"<span>{t}</span>" for t in tags)}</div>')
    return (
        f'<div class="knowledge-card"><strong class="kc-term">📘 {html.escape(term or "知识卡片")}</strong>'
        f'{"".join(parts)}</div>'
    )


def _segments_html(block: Block) -> str:
    items = []
    for seg in block.segments:
        badge = (
            f'<span class="seg-badge seg-badge-{html.escape(seg["segment_type"] or "default")}">'
            f'{html.escape(seg["label"])}</span>'
        )
        dur_html = f'<span class="seg-dur">⏱ {seg["seconds"]}秒</span>' if seg["seconds"] else ""
        diff_html = (
            f'<span class="seg-diff diff-{html.escape(seg["difficulty"])}">'
            f'{seg["difficulty_icon"]}</span>' if seg["difficulty_icon"] else ""
        )
        hint_html = f'<p class="seg-hint">💬 {html.escape(seg["hint"])}</p>' if seg["hint"] else ""
        kc_html = _knowledge_card_html(seg["knowledge_card"])
        items.append(
            f'<li class="seg-item">{badge}{dur_html}{diff_html}'
            f'<p class="seg-text">{html.escape(seg["text"])}</p>{hint_html}{kc_html}</li>'
        )
    if not items:
        return ""
    return (
        '<section class="segments-block"><h4>讲授分段</h4>'
        f'<ol class="segments">{"".join(items)}</ol></section>'
    )


def _paragraphs_html(block: Block) -> str:
    parts = [f"<p>{html.escape(text)}</p>" for text in block.paragraphs]
    return f'<div class="body">{"".join(parts)}</div>' if parts else ""


def _script_html(block: Block) -> str:
    # 无正文时不产生空区块（legacy 节点契约）
    text = block.paragraphs[0].strip() if block.paragraphs else ""
    if not text:
        return ""
    return (
        '<section class="script-block"><h4>讲授文本</h4>'
        f'<div class="script-body">{html.escape(text)}</div></section>'
    )


def render_question_html(question: Any) -> str:
    """单题渲染：字符串题直接输出；dict 题展示题干 + 选项 + 答案 + 解析。"""
    if isinstance(question, dict):
        text = html.escape(str(question.get("question") or question.get("title") or "").strip())
        options = question.get("options")
        answer = str(question.get("answer") or "").strip()
        explanation = str(question.get("explanation") or "").strip()

        opt_html = ""
        if isinstance(options, list) and options:
            letters = "ABCDEFGH"
            opt_items = []
            for i, opt in enumerate(options[: len(letters)]):
                letter = letters[i]
                is_answer = bool(answer) and letter == answer.strip().upper()
                ans_cls = " q-option-answer" if is_answer else ""
                opt_items.append(
                    f'<li class="q-option{ans_cls}">'
                    f'<span class="q-opt-letter">{letter}</span>{html.escape(str(opt))}</li>'
                )
            opt_html = f'<ul class="q-options">{"".join(opt_items)}</ul>'

        exp_html = f'<p class="q-explanation">解析：{html.escape(explanation)}</p>' if explanation else ""
        return f'<li class="q-item"><p class="q-text">{text}</p>{opt_html}{exp_html}</li>'
    return f'<li class="q-item"><p class="q-text">{html.escape(str(question))}</p></li>'


def _details_html(block: Block) -> str:
    """要点展开块：要点原文作小标题，展开说明作正文（幻灯片的主内容）。

    要点原文仍以 `<span class="kp-highlight">` 原样输出 —— verify_preview_render.py
    按精确串断言它，`kp-item` / `kp-highlight` 也是前端依赖的 class，改一个字符就
    破契约。展开文字挂在下方的 `kp-detail` 上。
    """
    items = []
    for entry in block.items:
        point = html.escape(str(entry.get("point") or ""))
        detail = html.escape(str(entry.get("detail") or ""))
        body = f'<p class="kp-detail">{detail}</p>' if detail and detail != point else ""
        items.append(
            f'<li class="kp-item"><span class="kp-highlight">{point}</span>{body}</li>'
        )
    if not items:
        return ""
    return f'<ul class="point-details">{"".join(items)}</ul>'


def _questions_html(block: Block) -> str:
    if not block.items:
        return ""
    items = "".join(render_question_html(q) for q in block.items)
    return f'<ol class="questions">{items}</ol>'


def normalize_conclusion(node: dict[str, Any]) -> str:
    """节点上的大字结论。

    来源优先级：``key_conclusion`` → ``teaching_plan.key_conclusion``。两者都缺时
    返回空串，页面自然少一块 —— 老课件不会因此变形。

    结论是「总-分-总」里的那个"总"：它必须是一句话，所以超长的一律判为不可用，
    宁可不显示，也不要一个占满半页的"结论"。

    只认字符串：数字 / 列表等脏数据 str 化之后会变成「123」「['a']」这种更糟的
    内容，不如当作缺失（与 normalize_figure 对脏输入一律退化的口径一致）。
    空串与全空白同样算缺失，好让 teaching_plan 里的结论有机会补位。
    """
    raw = node.get("key_conclusion")
    if not isinstance(raw, str) or not raw.strip():
        plan = node.get("teaching_plan")
        raw = plan.get("key_conclusion") if isinstance(plan, dict) else ""
    conclusion = raw.strip() if isinstance(raw, str) else ""
    return conclusion if 0 < len(conclusion) <= MAX_CONCLUSION_CHARS else ""


def _conclusion_html(block: Block) -> str:
    """大字结论块。全文 markup 都是新增的 —— 不碰任何既有 class 契约。"""
    text = " ".join(str(p).strip() for p in block.paragraphs if str(p).strip())
    if not text:
        return ""
    return f'<section class="conclusion-block"><p class="conclusion-text">{html.escape(text)}</p></section>'


def block_to_html(block: Block) -> str:
    """把一个 Block 渲染成 HTML 片段（供 SVG 的 foreignObject 承载）。

    kind=figure 没有 HTML 形态 —— 它由 gen/diagrams.py 画成原生 SVG，
    见 svg_renderer._lay_out_blocks 的特判。这里返回空串。
    """
    if block.kind == "segments":
        return _segments_html(block)
    if block.kind == "bullets":
        return _key_points_html(block.items, cls=block.cls or "key-points", with_index=block.with_index)
    if block.kind == "details":
        return _details_html(block)
    if block.kind == "conclusion":
        return _conclusion_html(block)
    if block.kind == "questions":
        return _questions_html(block)
    if block.kind == "script":
        return _script_html(block)
    if block.kind == "text":
        return _paragraphs_html(block)
    return ""


# ---- 组装 ----

def _content_blocks(node: dict[str, Any]) -> list[Block]:
    """内容页区块（顺序即视觉优先级）。

    幻灯片是给学生看的：主体是「图示 + 正文 + 要点展开」，**讲稿与分段不上幻灯片**
    （降为 ROLE_TEACHER，由预览渲染进幻灯片下方的折叠区）。

    两个不能省的兜底：

    - 正文（content/summary）**始终保留**。它不能因为「有要点」就被挤掉 ——
      test_preview_export_consistency 的 n3 节点正是 `content` 有值而 key_points
      也有值，丢掉正文会让那条同源断言直接挂掉。
    - 要点展开缺失时退回要点列表，老课件不会整页空白。
    """
    blocks: list[Block] = []

    # 1) 图示：S3 给出的结构化描述，由 diagrams.py 画成原生 SVG
    figure = normalize_figure(node)
    if figure:
        blocks.append(Block(kind="figure", role=ROLE_PRIMARY, figure=figure))

    # 2) 正文（导语 / 摘要）
    paragraphs = body_paragraphs(node)
    if paragraphs:
        blocks.append(Block(kind="text", role=ROLE_PRIMARY, paragraphs=paragraphs))

    # 3) 大字结论：规划器给的 key_conclusion，学生一眼要记住的那句话。
    #    排在正文之后、细节之前 —— 先"总"后"分"，细节展开是给这句话作注脚的。
    conclusion = normalize_conclusion(node)
    if conclusion:
        blocks.append(Block(kind="conclusion", role=ROLE_PRIMARY, paragraphs=[conclusion]))

    # 4) 要点展开：本轮的主角，每个要点配 1~2 句展开
    details = normalize_point_details(node)
    if details:
        blocks.append(Block(kind="details", role=ROLE_PRIMARY, heading="要点展开", items=details))

    # 5) 核心要点：只在节点**显式**写了要点时才出。
    #    extract_key_points 在要点字段全缺时会拿正文拆句兜底，那会和第 2 步的正文
    #    重复一遍，所以这里先判有没有显式字段。
    has_explicit_points = any(
        as_list(node.get(key))
        for key in ("key_points", "core_points", "key_difficulties", "expected_outcomes")
    )
    if has_explicit_points:
        blocks.append(Block(
            kind="bullets",
            role=ROLE_SECONDARY if (details or paragraphs or conclusion) else ROLE_PRIMARY,
            heading="核心要点",
            items=extract_key_points(node),
        ))

    # 6) 讲稿与分段：教师用，不上幻灯片（预览的折叠区渲染它们）
    segments = normalize_segments(node)
    if segments:
        blocks.append(Block(kind="segments", role=ROLE_TEACHER, segments=segments))
    script = str(node.get("script") or "").strip()
    if script:
        blocks.append(Block(kind="script", role=ROLE_TEACHER, heading="讲授文本",
                            paragraphs=[script]))

    return blocks


def build_page_spec(node: dict[str, Any], index: int, kind: str | None = None) -> PageSpec:
    """节点 → 页面内容模型。

    Args:
        node: 结构化教学节点
        index: 页码（从 1 开始）
        kind: 页面类型；不传则按 type/node_type 推断
    """
    kind = kind or resolve_kind(node)
    title = str(node.get("title") or f"第{index}页").strip()
    spec = PageSpec(node_id=str(node.get("node_id") or ""), index=index, kind=kind, title=title)

    if kind == "cover":
        # M4：真实节点的 summary（内容概述）不上 PPT；合成封面保留 summary 兜底
        subtitle = str(node.get("subtitle") or node.get("content") or "").strip()
        if not subtitle and is_auto_node(node):
            subtitle = str(node.get("summary") or "").strip()
        spec.subtitle = subtitle
        points = extract_key_points(node)
        if points:
            spec.blocks.append(Block(kind="bullets", cls="cover-points", items=points))

    elif kind == "section":
        # M4：同封面 —— 章节页副标题只认 content，大纲概述不再直接上页面
        subtitle = str(node.get("content") or "").strip()
        if not subtitle and is_auto_node(node):
            subtitle = str(node.get("summary") or "").strip()
        spec.subtitle = subtitle
        # 目录项优先取 children（子节点标题），其次取要点
        children = as_list(node.get("children"))
        items = children or extract_key_points(node)
        if items:
            spec.blocks.append(Block(kind="bullets", cls="section-list", items=items, with_index=True))

    elif kind in ("quiz", "interactive"):
        questions = as_raw_list(node.get("questions") or node.get("interactive_questions"))
        if not questions:
            for item in node.get("interactive_items") or []:
                if isinstance(item, dict) and str(item.get("type") or "").lower() == "quiz":
                    questions.extend(as_raw_list(item.get("questions")))
        if not questions:
            questions = extract_key_points(node) or split_content_into_points(
                str(node.get("content") or node.get("summary") or "").strip()
            )
        spec.blocks.append(Block(kind="questions", items=questions))
        # 讲稿与分段不上幻灯片（学生看到的只有题面），移入教师折叠区
        segments = normalize_segments(node)
        if segments:
            spec.blocks.append(Block(kind="segments", role=ROLE_TEACHER, segments=segments))
        script = str(node.get("script") or "").strip()
        if script:
            spec.blocks.append(Block(kind="script", role=ROLE_TEACHER, paragraphs=[script]))

    elif kind == "summary":
        points = extract_key_points(node)
        if points:
            spec.blocks.append(Block(kind="bullets", items=points))
        segments = normalize_segments(node)
        if segments:
            spec.blocks.append(Block(kind="segments", role=ROLE_TEACHER, segments=segments))
        script = str(node.get("script") or "").strip()
        if script:
            spec.blocks.append(Block(kind="script", role=ROLE_TEACHER, paragraphs=[script]))

    else:  # content 及其兜底
        spec.blocks.extend(_content_blocks(node))

    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    if kind != "content" and metadata.get("show_modified_details"):
        details = normalize_point_details(node)
        if details:
            spec.blocks.append(Block(kind="details", role=ROLE_PRIMARY, heading="补充内容", items=details))

    return spec
