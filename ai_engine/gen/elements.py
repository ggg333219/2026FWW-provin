"""Stable, semantic PPT element snapshots for natural-language modification.

The generation pipeline still uses teaching nodes as its public content unit.
This module adds a lossless element layer in node metadata so element identity
survives regeneration, preview rendering, versioning, and export.
"""

from __future__ import annotations

import copy
import re
from typing import Any


_ROLE_WORDS = {
    "title": ("标题", "题目"),
    "body": ("正文", "内容", "文字", "文本", "讲稿"),
    "list": ("列表", "要点", "清单"),
    "notes": ("备注", "讲授备注", "演讲者备注"),
    "image": ("图片", "图像", "照片"),
    "chart": ("图表", "柱状图", "折线图", "饼图"),
    "shape": ("形状", "色块", "线条"),
}
_POSITION_WORDS = {
    "left": ("左", "左侧"),
    "right": ("右", "右侧"),
    "top": ("上", "顶部", "上方"),
    "bottom": ("下", "底部", "下方"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _element_id(node_id: str, role: str, ordinal: int = 1) -> str:
    suffix = role if ordinal == 1 else f"{role}_{ordinal}"
    return f"el_{node_id}_{suffix}"


def _new_element(node_id: str, role: str, element_type: str, content: Any,
                 *, ordinal: int = 1, position: str = "") -> dict[str, Any]:
    return {
        "element_id": _element_id(node_id, role, ordinal),
        "page_id": node_id,
        "element_type": element_type,
        "role": role,
        "content": content,
        "geometry": {"x": 0, "y": 0, "width": 0, "height": 0, "position": position},
        "style": {},
        "group_id": None,
        "source_refs": [],
        "parent_element_id": None,
    }


def _derived_elements(node: dict[str, Any]) -> list[dict[str, Any]]:
    node_id = _text(node.get("node_id"))
    elements: list[dict[str, Any]] = []
    title = _text(node.get("title"))
    if title:
        elements.append(_new_element(node_id, "title", "text", title, position="top"))

    points = node.get("key_points") or node.get("core_points") or []
    if points:
        elements.append(_new_element(node_id, "list", "text", list(points), position="left"))
    else:
        body = _text(node.get("content") or node.get("summary") or node.get("script"))
        if body:
            elements.append(_new_element(node_id, "body", "text", body, position="right"))

    notes = _text(node.get("notes") or node.get("speaker_notes"))
    if notes:
        elements.append(_new_element(node_id, "notes", "notes", notes, position="bottom"))

    figure = node.get("figure") or (node.get("metadata") or {}).get("figure")
    if isinstance(figure, dict):
        kind = _text(figure.get("kind")) or "shape"
        element_type = "chart" if kind == "chart" else "shape"
        elements.append(_new_element(node_id, kind, element_type, copy.deepcopy(figure), position="right"))

    media = (node.get("metadata") or {}).get("media")
    if isinstance(media, list):
        for index, item in enumerate(media, start=1):
            if isinstance(item, dict):
                elements.append(_new_element(node_id, "image", "image", copy.deepcopy(item), ordinal=index, position="right"))
    return elements


def build_element_snapshot(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return nodes with normalized, stable semantic elements in metadata."""
    result = copy.deepcopy(nodes or [])
    for node in result:
        metadata = node.setdefault("metadata", {})
        existing = metadata.get("elements")
        elements = existing if isinstance(existing, list) else _derived_elements(node)
        normalized: list[dict[str, Any]] = []
        role_counts: dict[str, int] = {}
        for raw in elements:
            if not isinstance(raw, dict):
                continue
            item = copy.deepcopy(raw)
            role = _text(item.get("role")) or "body"
            role_counts[role] = role_counts.get(role, 0) + 1
            item["page_id"] = _text(item.get("page_id")) or _text(node.get("node_id"))
            item["element_id"] = _text(item.get("element_id")) or _element_id(
                item["page_id"], role, role_counts[role]
            )
            item["element_type"] = _text(item.get("element_type")) or "text"
            item["role"] = role
            item.setdefault("geometry", {})
            item.setdefault("style", {})
            item.setdefault("group_id", None)
            item.setdefault("source_refs", [])
            item.setdefault("parent_element_id", None)
            normalized.append(item)
        metadata["elements"] = normalized
    return result


def _page_number(node: dict[str, Any], index: int) -> int:
    value = node.get("page_ref")
    try:
        return int(value) if int(value) > 0 else index + 1
    except (TypeError, ValueError):
        return index + 1


_CN_NUMBERS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _requested_page(instruction: str) -> int | None:
    match = re.search(r"第\s*(\d+|[一二三四五六七八九十]+)\s*页", instruction)
    if not match:
        return None
    raw = match.group(1)
    if raw.isdigit():
        return int(raw)
    if raw == "十":
        return 10
    if len(raw) == 2 and raw[0] == "十":
        return 10 + _CN_NUMBERS.get(raw[1], 0)
    if len(raw) == 2 and raw[1] == "十":
        return _CN_NUMBERS.get(raw[0], 0) * 10
    return _CN_NUMBERS.get(raw)


def _requested_roles(instruction: str) -> set[str]:
    return {role for role, words in _ROLE_WORDS.items() if any(word in instruction for word in words)}


def _requested_position(instruction: str) -> str | None:
    for position, words in _POSITION_WORDS.items():
        if any(word in instruction for word in words):
            return position
    return None


def resolve_element_candidates(instruction: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve natural language to zero, one, or multiple element candidates."""
    normalized = build_element_snapshot(nodes)
    page = _requested_page(instruction)
    roles = _requested_roles(instruction)
    position = _requested_position(instruction)
    lowered = instruction.lower()
    candidates: list[dict[str, Any]] = []
    for index, node in enumerate(normalized):
        if page is not None and _page_number(node, index) != page:
            continue
        for element in node.get("metadata", {}).get("elements", []):
            content = element.get("content")
            haystack = _text(content if isinstance(content, str) else " ".join(map(str, content or []))).lower()
            role_match = not roles or element.get("role") in roles or element.get("element_type") in roles
            # Semantic role is stronger than a generated layout hint. A title
            # may move from top to left without changing its identity.
            position_match = (
                not position
                or position in _text(element.get("geometry", {}).get("position"))
                or (bool(roles) and element.get("role") in roles)
            )
            text_match = bool(haystack and any(token in haystack for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", lowered)))
            if role_match and position_match and (page is not None or text_match or roles or position):
                candidates.append({
                    "element_id": element["element_id"],
                    "page_id": element["page_id"],
                    "page_number": _page_number(node, index),
                    "element_type": element["element_type"],
                    "role": element["role"],
                    "position": element.get("geometry", {}).get("position", ""),
                    "content_preview": _text(content)[:120],
                })

    status = "resolved" if len(candidates) == 1 else "ambiguous" if len(candidates) > 1 else "unresolved"
    return {
        "status": status,
        "candidates": candidates,
        "target_element_ids": [item["element_id"] for item in candidates] if status == "resolved" else [],
        "requires_confirmation": len(candidates) != 1,
    }


def apply_element_update(nodes: list[dict[str, Any]], target_element_ids: list[str],
                         *, action: str, replacement: Any = None,
                         style: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Apply a deterministic element update while preserving unrelated nodes."""
    result = build_element_snapshot(nodes)
    targets = set(target_element_ids)
    for node in result:
        for element in node.get("metadata", {}).get("elements", []):
            if element.get("element_id") not in targets:
                continue
            if replacement is not None:
                element["content"] = copy.deepcopy(replacement)
                role = element.get("role")
                if role == "title":
                    node["title"] = _text(replacement)
                elif role in {"body", "list"} and isinstance(replacement, str):
                    node["content"] = replacement
                    node["summary"] = replacement
            if style:
                element.setdefault("style", {}).update(copy.deepcopy(style))
    return result


__all__ = ["apply_element_update", "build_element_snapshot", "resolve_element_candidates"]
