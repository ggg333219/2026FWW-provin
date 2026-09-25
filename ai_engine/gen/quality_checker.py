"""PPT导出前自动质量检查"""
from typing import List, Dict

from .export_ppt import resolve_node_type


def check_node(node: dict, page_index: int) -> List[str]:
    warnings = []
    title = str(node.get("title") or "").strip()
    if not title:
        warnings.append(f"第{page_index}页缺少标题")
    # 正文优先取summary，和生产节点字段对齐
    content = str(node.get("content") or node.get("summary") or "").strip()
    points = node.get("core_points") or node.get("key_points") or []
    node_type = resolve_node_type(node)
    if not content and not points and node_type not in ("cover", "section"):
        warnings.append(f"第{page_index}页无正文/要点内容")
    if len(content) > 500:
        warnings.append(f"第{page_index}页正文过长（{len(content)}字），建议拆分页面")
    if len(points) > 5:
        warnings.append(f"第{page_index}页要点过多（{len(points)}条），建议拆分页面")
    # 互动页检查
    if node_type == "quiz":
        questions = node.get("questions") or node.get("interactive_questions") or []
        if not questions:
            warnings.append(f"第{page_index}页为互动页但无题目内容")
    return warnings


def run_full_check(nodes: List[Dict]) -> dict:
    all_warnings = []
    for idx, node in enumerate(nodes, 1):
        all_warnings.extend(check_node(node, idx))
    return {
        "total_pages": len(nodes),
        "warning_count": len(all_warnings),
        "warnings": all_warnings,
        "passed": len(all_warnings) == 0
    }
