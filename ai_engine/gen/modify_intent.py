"""Deterministic first-pass parser for teacher courseware modifications."""

from __future__ import annotations

import re
from typing import Any


_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _number(value: str) -> int:
    if value.isdigit():
        return int(value)
    if value in _CN_DIGITS:
        return _CN_DIGITS[value]
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        return (_CN_DIGITS.get(left, 1) * 10) + _CN_DIGITS.get(right, 0)
    return 0


def _target_ids(nodes: list[dict[str, Any]], text: str) -> list[str]:
    explicit = re.findall(r"(?:node|节点)[_ -]?(\d+|[零〇一二两三四五六七八九十]+)", text, flags=re.I)
    page = re.search(r"(?:第\s*)?(\d+|[零〇一二两三四五六七八九十]+)\s*(?:页|page)", text, flags=re.I)
    numbers = [_number(n) for n in explicit] or ([_number(page.group(1))] if page else [])
    result: list[str] = []
    for number in numbers:
        for index, node in enumerate(nodes):
            if any(node.get(key) == number for key in ("page_ref", "page", "order")) or index + 1 == number:
                node_id = str(node.get("node_id", ""))
                if node_id and node_id not in result: result.append(node_id)
                break
    return result


def parse_modify_instruction(project_id: str, instruction: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    text = instruction.strip()
    if re.search(r"(?:整体|全局|全部).*(?:风格|样式|主题)|(?:风格|样式|主题).*(?:整体|全局|科技感|商务|简约)", text, re.I):
        return {"project_id": project_id, "target_type": "style", "target_ids": [], "actions": ["restyle"], "action": "restyle", "constraints": [text], "confidence": 0.95, "clarification_needed": False, "clarification": None}
    target_ids = _target_ids(nodes, text)
    actions: list[str] = []
    if re.search(r"减少|精简|简化|太复杂|文字太多|压缩", text): actions.append("simplify")
    if re.search(r"增加|扩充|补充|案例|例子|详细", text): actions.append("expand")
    if re.search(r"删除|移除|去掉", text): actions.append("delete")
    if re.search(r"新增|添加|插入", text): actions.append("add")
    if re.search(r"换一下|交换|调换|顺序|前后", text): actions.append("reorder")
    if re.search(r"风格|样式|主题|配色|字体", text): actions.append("restyle")
    if not actions: actions = ["rewrite"]
    if "reorder" in actions:
        pair = re.findall(r"(?:第\s*)?(\d+|[零〇一二两三四五六七八九十]+)\s*(?:部分|页|节点)?\s*(?:和|与)\s*(?:第\s*)?(\d+|[零〇一二两三四五六七八九十]+)", text)
        if pair: target_ids = _target_ids(nodes, f"第{pair[0][0]}页") + _target_ids(nodes, f"第{pair[0][1]}页")
    constraints: list[str] = []
    if re.search(r"保留|核心|知识点", text): constraints.append("保留核心知识点")
    if re.search(r"案例|例子", text): constraints.append("增加生活案例")
    if re.search(r"减少|精简|压缩", text): constraints.append("减少文字量")
    clarification_needed = not target_ids and "restyle" not in actions
    return {"project_id": project_id, "target_type": "node" if target_ids else "global", "target_ids": target_ids, "actions": actions, "action": actions[0], "constraints": constraints, "confidence": 0.88 if target_ids else 0.52, "clarification_needed": clarification_needed, "clarification": "请指定要修改的页面或节点，以及希望进行的修改。" if clarification_needed else None}
