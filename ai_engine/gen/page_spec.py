"""S3 页面内容 IR —— 「这一页该画什么」的单一事实来源。

背景
----
课件内容页此前有**三个渲染器各画一套**：
  - gen/preview.py      → 要点 + 正文(content/summary) + 讲授文本(script) + 分段(segments)
  - gen/export_ppt.py   → 教学内容(content/summary/要点) + 讲授分段(恒空)
  - gen/svg_renderer.py → 核心要点 + 教学内容(content/summary)

局部修改（gen/partial_content.py）只覆盖 `script` / `segments`，后两个渲染器恰好
都不读它们，于是「改了看不见」，且两端内容对不上。

本模块把「页面由哪些区块构成、每个区块什么角色」抽成一份中间表示（IR），
让渲染器只负责**摆版**、不负责**决定内容**。与 gen/presentation.py 对样式层
做的事同构 —— 那里统一了「长什么样」，这里统一「画什么」。

关于 `content` 字段
------------------
真实生成链路里 `content` 从不被赋值（schema.py 的 normalize_stage2_nodes 与
normalize_stage3_scripts 都不产出它），有值的是 `summary`（stage2）与
`script` / `segments`（stage3）。但仍把它保留为正文来源之一：历史课件与手工
编辑会写它，且 test_preview_export_consistency 断言它必须出现在预览里。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any

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

#: 区块角色：primary 占主位（大字号、宽栏），secondary 降为小字注记
ROLE_PRIMARY = "primary"
ROLE_SECONDARY = "secondary"


# ---- IR ----

@dataclass
class Block:
    """页面上的一块内容。渲染器只看 kind / role，不解析节点字段。"""

    kind: str                      # segments | text | script | bullets | questions | cover_points | section_list
    role: str = ROLE_PRIMARY
    heading: str = ""
    segments: list[dict] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    items: list[Any] = field(default_factory=list)
    cls: str = ""                  # 覆盖默认 class（cover-points / section-list）
    with_index: bool = False


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
    """内容页正文来源：content 优先，其次 summary。均为空时返回 []。"""
    paragraphs: list[str] = []
    for key in ("content", "summary"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            paragraphs.append(value.strip())
        elif isinstance(value, list):
            paragraphs.extend(str(v).strip() for v in value if str(v).strip())
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


def _questions_html(block: Block) -> str:
    if not block.items:
        return ""
    items = "".join(render_question_html(q) for q in block.items)
    return f'<ol class="questions">{items}</ol>'


def block_to_html(block: Block) -> str:
    """把一个 Block 渲染成 HTML 片段（供 SVG 的 foreignObject 承载）。"""
    if block.kind == "segments":
        return _segments_html(block)
    if block.kind == "bullets":
        return _key_points_html(block.items, cls=block.cls or "key-points", with_index=block.with_index)
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

    讲稿分段为主体、要点降为次要 —— 这是「PPT 内容不再是核心要点而是灵活的文字」
    的落点。正文（content/summary）与讲授文本（script）都在，但只占次要位，
    避免与分段重复争主位。
    """
    blocks: list[Block] = []

    segments = normalize_segments(node)
    if segments:
        blocks.append(Block(kind="segments", role=ROLE_PRIMARY, heading="讲授内容", segments=segments))

    paragraphs = body_paragraphs(node)
    if paragraphs:
        blocks.append(Block(kind="text", role=ROLE_PRIMARY, paragraphs=paragraphs))

    script = str(node.get("script") or "").strip()
    if script:
        # 无分段时讲稿就是正文，升为主位；有分段时它是分段的拼接，
        # 降为次要小字，保留下来是为了「讲授文本」区块不消失（既有契约）。
        role = ROLE_SECONDARY if segments else ROLE_PRIMARY
        blocks.append(Block(kind="script", role=role, heading="讲授文本", paragraphs=[script]))

    points = extract_key_points(node)
    if points:
        blocks.append(Block(kind="bullets", role=ROLE_SECONDARY, heading="核心要点", items=points))

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
        spec.subtitle = str(node.get("subtitle") or node.get("content") or node.get("summary") or "").strip()
        points = extract_key_points(node)
        if points:
            spec.blocks.append(Block(kind="bullets", cls="cover-points", items=points))

    elif kind == "section":
        spec.subtitle = str(node.get("content") or node.get("summary") or "").strip()
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
        segments = normalize_segments(node)
        if segments:
            spec.blocks.append(Block(kind="segments", role=ROLE_SECONDARY, segments=segments))
        script = str(node.get("script") or "").strip()
        if script:
            spec.blocks.append(Block(kind="script", role=ROLE_SECONDARY, paragraphs=[script]))

    elif kind == "summary":
        points = extract_key_points(node)
        if points:
            spec.blocks.append(Block(kind="bullets", items=points))
        segments = normalize_segments(node)
        if segments:
            spec.blocks.append(Block(kind="segments", role=ROLE_SECONDARY, segments=segments))
        script = str(node.get("script") or "").strip()
        if script:
            spec.blocks.append(Block(kind="script", role=ROLE_SECONDARY, paragraphs=[script]))

    else:  # content 及其兜底
        spec.blocks.extend(_content_blocks(node))

    return spec
