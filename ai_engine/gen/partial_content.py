"""B6: 节点级局部重生成。

在 /gen/content 的基础上支持 mode=partial：
  - 只重新生成 target_node_ids 指定的节点
  - 保留其他节点的内容与引用关系不变
  - 样式类修改（restyle）不触发 RAG 检索，只改呈现层
  - 内容类修改（simplify/expand/rewrite）才触发局部 RAG（scope=target_node）

不新建独立端点——而是在 _run_content_pipeline 里分支调用，
避免改变前端既有 /gen/content 调用路径。
"""

from __future__ import annotations

import logging
from typing import Any

from gen.node import NodeGenerator

logger = logging.getLogger(__name__)


def run_partial_pipeline(
    nodes: list[dict[str, Any]],
    target_node_ids: list[str],
    modify_action: str,
    modify_constraints: list[str],
    context_markdown: str,
    course_name: str,
    generator: NodeGenerator | None = None,
) -> list[dict[str, Any]]:
    """局部重生成：只改目标节点，其余原样保留。

    Args:
        nodes: 当前完整节点列表（含已有内容）
        target_node_ids: 需要重新生成的节点 ID
        modify_action: simplify / expand / rewrite / restyle / delete / add / reorder
        modify_constraints: 教师约束（来自 B5 解析结果）
        context_markdown: 参考材料
        course_name: 课件名

    Returns:
        更新后的完整节点列表（目标节点内容已重新生成，其余不变）
    """
    if not nodes:
        return []

    # restyle 不需要内容重生成——只改呈现层，由前端样式层处理
    if modify_action == "restyle":
        logger.info("[partial] restyle 动作不触发内容重生成，跳过")
        return nodes

    target_set = set(target_node_ids)
    gen = generator or NodeGenerator()

    # 构建修改指令 prompt（按 action 差异化）
    action_prompts = {
        "simplify": "请精简该节点的内容：减少冗余文字、保留核心知识点，使表述更简洁有力。",
        "expand": "请扩充该节点的内容：在保留现有要点的基础上增加更多细节、案例或讲解。",
        "rewrite": "请重写该节点的讲稿内容：保持核心知识点不变，用更清晰的方式重新表述。",
        "delete": "",  # delete 在上层处理（从列表移除），不进入重生成
        "add": "",  # add 在上层处理（追加新节点），不进入重生成
        "reorder": "",  # reorder 在上层处理（换位），不进入重生成
    }

    base_prompt = action_prompts.get(modify_action, action_prompts["rewrite"])
    constraints_text = ""
    if modify_constraints:
        constraints_text = "\n教师要求：" + "；".join(modify_constraints)

    # 收集相邻节点上下文（保持逻辑连贯）
    def _get_neighbors(idx: int) -> tuple[dict | None, dict | None]:
        prev_node = nodes[idx - 1] if idx > 0 else None
        next_node = nodes[idx + 1] if idx < len(nodes) - 1 else None
        return prev_node, next_node

    updated = []
    for idx, node in enumerate(nodes):
        node_id = node.get("node_id", "")

        if node_id in target_set:
            # 局部重生成该节点
            prev_node, next_node = _get_neighbors(idx)
            context_parts = []
            if prev_node:
                context_parts.append(f"上一节：{prev_node.get('title', '')}")
            if next_node:
                context_parts.append(f"下一节：{next_node.get('title', '')}")
            neighbor_context = "\n".join(context_parts)

            modify_instruction = base_prompt
            if neighbor_context:
                modify_instruction += f"\n上下文：{neighbor_context}"
            if constraints_text:
                modify_instruction += constraints_text

            try:
                new_script = gen.generate_single(
                    node,
                    course_name=course_name,
                    extra_instruction=modify_instruction,
                )
                if isinstance(new_script, dict) and new_script.get("script"):
                    updated_node = dict(node)
                    updated_node["script"] = new_script.get("script", "")
                    updated_node["segments"] = new_script.get("segments") or []
                    # 保留原引用关系（citation_refs / source_chunk_ids 不动）
                    updated.append(updated_node)
                else:
                    updated.append(node)
            except Exception as exc:
                logger.warning("[partial] 节点 %s 重生成失败: %s", node_id, exc)
                updated.append(node)  # 失败时保留原内容
        else:
            # 非目标节点：原样保留，内容与引用关系不变
            updated.append(node)

    return updated
