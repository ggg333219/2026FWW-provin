"""课件页面结构扩展（deck structure）— 封面 / 目录 / 总结页的默认注入。

M3 需求：默认输出的 PPT 必须包含 封面 / 目录（节点较多时）/ 总结页。
教师编辑的大纲保持干净（不塞进合成的假节点），注入只发生在渲染装配层，
因此预览（preview.py → svg_renderer）与导出（export_ppt.py → python-pptx）
共用本模块的同一个 expand_deck_pages，保证两端页面结构同源。

合成节点约定：
  - node_id 带 ``__auto_`` 前缀，前端"改一页换一页"锚点不会与真实节点冲突；
  - node_type 使用两端已支持的渲染类型（cover / agenda / summary）；
  - agenda 在预览端回退为要点列表版式（SVG 端暂无独立目录版式），
    导出端走 python-pptx 的编号目录页。
"""

from __future__ import annotations

from typing import Any

AUTO_COVER_ID = "__auto_cover__"
AUTO_TOC_ID = "__auto_toc__"
AUTO_SUMMARY_ID = "__auto_summary__"

#: 内容节点数超过该阈值时才自动加目录页（后期调整1 M3：大纲节点>5 时自动加目录）
TOC_MIN_CONTENT_NODES = 5

#: 总结页最多收集的要点条数
SUMMARY_MAX_POINTS = 5


def resolve_kind(node: dict[str, Any]) -> str:
    """与 page_spec.resolve_kind 同口径的轻量判定（避免循环导入）。"""
    raw = str(node.get("node_type") or node.get("type") or "content").strip().lower()
    return raw or "content"


def _as_mapping(node: Any) -> dict[str, Any]:
    if isinstance(node, dict):
        return node
    if hasattr(node, "model_dump"):
        return node.model_dump()
    if hasattr(node, "dict"):
        return node.dict()
    return vars(node)


def _is_auto(node: dict[str, Any]) -> bool:
    return str(node.get("node_id") or "").startswith("__auto_")


def is_auto_node(node: dict[str, Any]) -> bool:
    """公开判定：是否为 deck_structure 注入的合成节点（node_id 以 ``__auto_`` 开头）。

    page_spec（M4）用它区分「大纲节点的内容概述」与「合成节点的版面文案」：
    前者的 summary 不再进 PPT，后者的 content/summary 是有意文案，保留。
    """
    return _is_auto(node)


def _collect_key_points(node: dict[str, Any]) -> list[str]:
    for field in ("key_points", "core_points"):
        raw = node.get(field) or []
        if isinstance(raw, list):
            values = [str(item).strip() for item in raw if str(item).strip()]
            if values:
                return values
    return []


def _toc_titles(nodes: list[dict[str, Any]]) -> list[str]:
    """目录条目 = 除封面/已有目录页外的每个节点标题。"""
    titles: list[str] = []
    for index, node in enumerate(nodes, start=1):
        if resolve_kind(node) == "cover":
            continue
        title = str(node.get("title") or "").strip()
        titles.append(title or f"第 {index} 页")
    return titles


def _summary_points(nodes: list[dict[str, Any]]) -> list[str]:
    """总结要点：按顺序收集各节点第一个要点，去重并截断。"""
    points: list[str] = []
    for node in nodes:
        kind = resolve_kind(node)
        if kind in ("cover", "summary", "agenda"):
            continue
        values = _collect_key_points(node)
        if not values:
            title = str(node.get("title") or "").strip()
            if title:
                values = [title]
        if values and values[0] not in points:
            points.append(values[0])
        if len(points) >= SUMMARY_MAX_POINTS:
            break
    return points


def expand_deck_pages(
    nodes: list[Any],
    course_name: str = "课件",
    *,
    include_cover: bool = True,
    include_toc: bool = True,
    include_summary: bool = True,
    toc_min_content_nodes: int = TOC_MIN_CONTENT_NODES,
) -> list[dict[str, Any]]:
    """
    按默认结构补齐课件页面：封面 → （目录）→ 原内容页 → （总结）。

    规则：
      - 原始首节点已是封面时不重复注入封面；
      - 内容页数 > toc_min_content_nodes 时注入目录页（紧跟封面/首页之前的位置之后）；
      - 末节点已是总结页时不重复注入总结；
      - 传入空节点列表时仅注入封面，保证导出永不空白。

    Returns:
        新的节点列表（不修改入参），合成节点带 ``__auto_`` 前缀 node_id。
    """
    normalized = [_as_mapping(node) for node in (nodes or [])]
    expanded: list[dict[str, Any]] = list(normalized)

    content_count = sum(
        1 for node in expanded if resolve_kind(node) not in ("cover", "summary", "agenda")
    )
    leading_is_cover = bool(expanded) and resolve_kind(expanded[0]) == "cover"

    # ① 封面
    if include_cover and not leading_is_cover:
        expanded.insert(0, {
            "node_id": AUTO_COVER_ID,
            "title": str(course_name or "课件").strip() or "课件",
            "content": "AI 智能生成课件",
            "node_type": "cover",
            "summary": "",
            "key_points": [],
        })

    # ② 目录（紧跟封面之后；无封面时才作为首页）
    # 目录页被教师接管后 node_id 为 __auto_toc__，已在树里，再注入一次就会出现两个目录。
    has_agenda = any(resolve_kind(node) == "agenda" for node in expanded)
    if include_toc and not has_agenda and content_count > toc_min_content_nodes:
        titles = _toc_titles(normalized)
        if titles:
            # 首位已是封面（注入的或用户自己的）→ 目录排在其后；否则目录作为首页
            insert_at = 1 if (expanded and resolve_kind(expanded[0]) == "cover") else 0
            expanded.insert(insert_at, {
                "node_id": AUTO_TOC_ID,
                "title": "目录",
                "content": f"本次课程共 {content_count} 个环节",
                "summary": f"本次课程共 {content_count} 个环节",
                "node_type": "agenda",
                "key_points": titles,
            })

    # ③ 总结（末节点不是 summary 时注入）
    if include_summary and expanded:
        tail_kind = resolve_kind(expanded[-1])
        if tail_kind != "summary":
            points = _summary_points(normalized)
            expanded.append({
                "node_id": AUTO_SUMMARY_ID,
                "title": "本节小结",
                "content": "回顾本次课程的核心要点",
                "summary": "回顾本次课程的核心要点",
                "node_type": "summary",
                "key_points": points or ["本节要点"],
            })

    return expanded
